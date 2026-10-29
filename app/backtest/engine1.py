

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import uuid
import warnings

# محرك الاستراتيجية (decision engine) الذي ينفذه هذا المحرك
from app.services.strategy.strategy_engine1 import StrategyEngine, Decision, DecisionAction

# الـ Schemas والخدمات المساعدة
from app.backtest.schemas import BacktestConfig, BacktestResult, Trade, VisualCandle
from app.services.data_service import DataService
from app.services.strategy.schemas import StrategyConfig as StrategyConfigSchema
from app.backtest.metrics import PerformanceMetrics

warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

# حدود قصوى للحفاظ على زمن تشغيل معقول (Runtime bounds)
MAX_WALK_FORWARD_WINDOWS = 20
MAX_MONTE_CARLO_SIMULATIONS = 500

class BacktestEngine:
    """محرك الباك-تيست التاريخي (يعمل الآن كمحرك تنفيذي للقرارات)"""
    
    def __init__(self, data_service: DataService):
        self.data_service = data_service
        self.metrics_calculator = PerformanceMetrics()

    @staticmethod
    def _normalize_candle_index(data: pd.DataFrame) -> pd.DataFrame:
        """ضمان فهرس زمني DatetimeIndex للمحاكاة.

        ✅ إصلاح: كان DataService يعيد فهرساً رقمياً (0..n) مع عمود 'time' بالمللي
        ثانية — ومحرك القرارات يحتاج DatetimeIndex (timestamps_sec, visual candles)
        فكان يفشل بصمت ويعيد نتائج فارغة. نحوله هنا مركزياً.
        """
        if isinstance(data.index, pd.DatetimeIndex):
            return data
        if "time" in data.columns:
            t = pd.to_datetime(data["time"], unit="ms", utc=True, errors="coerce")
            if t.notna().all():
                out = data.copy()
                out.index = pd.DatetimeIndex(t, name="time")
                return out.drop(columns=["time"])
        try:
            coerced = pd.to_datetime(data.index, utc=True, errors="raise")
            out = data.copy()
            out.index = pd.DatetimeIndex(coerced)
            return out
        except Exception:
            return data
        



    
    async def run_backtest(self, config: BacktestConfig) -> BacktestResult:  
        start_time = datetime.utcnow()
        logger.info(f"Starting backtest (Strategy-Driven): {config.name}")
        
        try:
            # 1. جلب البيانات (Data Fetching)
            all_data = {}
            for symbol in config.symbols:
                try:
                   
                    data = await self.data_service.get_historicallastvirsion(
                        symbol=symbol, 
                        timeframe=config.timeframe,
                        market=config.market, 
                        start_date=config.start_date,
                        end_date=config.end_date,
                        use_cache=True
                    )
                    
                    if data.empty:
                        logger.warning(f"No data returned for {symbol}")
                        continue

                    data = self._normalize_candle_index(data)
                    all_data[symbol] = data
                    logger.info(f"Loaded {len(data)} candles for {symbol} "
                                f"({data.index[0]} → {data.index[-1]})")

                except Exception as e:
                    logger.warning(f"Error fetching data for {symbol}: {e}")
                 
            if not all_data:
                raise ValueError("No data available for any symbol")
            
            # 2. محاكاة التداول (Simulation)
            trades = []

            equity_curve = [config.initial_capital]
            visual_candles_all = []
            trade_points_all = []

            current_capital = config.initial_capital
            
            for symbol, data in all_data.items():
 
                symbol_trades, symbol_equity, symbol_visual_candles, symbol_trade_points = await self._simulate_with_strategy(
                    symbol, data, config, current_capital
                )                
                trades.extend(symbol_trades)
                visual_candles_all.extend(symbol_visual_candles)
                trade_points_all.extend(symbol_trade_points)                
                # تحديث منحنى رأس المال
                if len(symbol_equity) > 0:
                    # نبدأ من الفهرس 1 لتجنب تكرار القيمة الأولية
                    equity_curve.extend(symbol_equity[1:]) 
                    current_capital = symbol_equity[-1]

            # 3. حساب المقاييس والنتيجة النهائية (Metrics & Result)
            result = await self._create_backtest_result(
                config=config, 
                trades=trades, 
                equity_curve=equity_curve, 
                visual_candles=visual_candles_all,  # إضافة البيانات البصرية
                trade_points=trade_points_all,                  
                execution_start=start_time
            )
            
            return result

        except Exception as e:
            logger.exception(f"Backtest failed: {e}")
            raise


    async def _simulate_with_strategy(
        self,
        symbol: str,
        data: pd.DataFrame,
        config: BacktestConfig,
        initial_capital: float
    ) -> Tuple[List[Trade], List[float], List[VisualCandle], List[dict]]:
        """
        نموذج "Next Bar Open" (مثل TradingView)
        يمنع دخول وخروج الصفقة في نفس الشمعة.
        يحلل مشكلة الـ Commission والحقول المفقودة.
        """
        trades = []
        equity_curve = [initial_capital]
        current_capital = initial_capital
        visual_candles = []
        trade_points = []
        render_data = {}
        volume_bars_dict = {}
        climax_points_dict = {}
        
        if len(data) < 50:
            return trades, equity_curve, visual_candles, trade_points


        # ✅ float64 وليس float32 — دقة الحسابات للعملات الرقمية (أسعار كبيرة + كسور صغيرة)
        open_prices = data['open'].values.astype(np.float64)
        high_prices = data['high'].values.astype(np.float64)
        low_prices = data['low'].values.astype(np.float64)
        close_prices = data['close'].values.astype(np.float64)
        volume_vals = data['volume'].values.astype(np.float64)

        # تحويل التواريخ مرة واحدة
        timestamps_sec = [int(ts.timestamp()) for ts in data.index]

        # ✅ عينات بصرية: على البيانات الضخمة نبني VisualCandle لكل شمعة رقمها
        # من مضاعفات visual_step (أو شموع فيها صفقات/أولى/أخيرة) — بقية الشموع
        # تُتخطى من مرحلة العرض فقط. النتائج المالية لا تتأثر إطلاقاً.
        _VISUAL_CAP = 20000
        visual_step = 1
        if len(data) > _VISUAL_CAP:
            visual_step = int(np.ceil(len(data) / _VISUAL_CAP))



        try:
            strategy_config_obj = StrategyConfigSchema(**config.strategy_config)
            strategy_engine = StrategyEngine(strategy_config_obj)
            full_calculated_data = await strategy_engine._prepare_indicators(data)
            strategy_engine.full_data = full_calculated_data


            render_data = {}
            volume_bars_dict = {}
            climax_points_dict = {}


        except Exception as e:
            logger.exception(f"CRITICAL ERROR IN STRATEGY INIT: {e}")
            return trades, equity_curve, visual_candles, trade_points



        # ✅ بيانات render الآن على المحرك (render_metadata) بدل df.attrs —
        # df.attrs كان يسبب deepcopy لكل وصول عمود (O(n²) إجمالاً)
        render_data = {}
        engine_render = getattr(strategy_engine, 'render_metadata', None)
        if engine_render:
            render_data = engine_render
        elif hasattr(full_calculated_data, 'attrs'):
            render_data = full_calculated_data.attrs.get('volume_climax_render', {})
            
        if render_data:
            # إنشاء قواميس للبحث السريع
            for bar in render_data.get('volume_bars', []):
                # الوقت في render_data هو بالثواني (كما طبع: 1767560400)
                volume_bars_dict[bar['time']] = bar
            
            for point in render_data.get('climax_points', []):
                climax_points_dict[point['time']] = point
            
    
        # حالة المحفظة (Portfolio State)
        current_state = 'NEUTRAL'
        entry_price = 0.0
        entry_time = None
        position_size = 0.0
        trade_id = None
        sl_price = 0.0
        tp_price = 0.0
        cumulative_pnl = 0.0
        account_balance = initial_capital

        # متغيرات النموذج المتقدم (Pending Decision)
        pending_decision = None  # سيحمل القرار من الشمعة السابقة للتنفيذه الآن
        executed_decision = None  # القرار الذي تم تنفيذه في هذه الشمعة

        # حلقة المحاكاة (Bar-by-Bar Simulation)
        import time
        t_total_start = time.perf_counter()
        t_strategy = 0.0
        t_visual = 0.0
        t_loop = 0.0
        elapsed = 0.0

        for i in range(len(data)):
            t_loop_start = time.perf_counter()
            # current_bar = data.iloc[i]
            # current_time = data.index[i]
            # current_time_sec = int(pd.to_datetime(current_time).timestamp())


            current_time = data.index[i]  # ✅ نحتاج هذا للـ timestamp فقط
            current_time_sec = timestamps_sec[i]  # ✅ من المصفوفة المحضرة
            open_price = open_prices[i]      # ✅
            high_price = high_prices[i]      # ✅
            low_price = low_prices[i]        # ✅  
            close_price = close_prices[i]    # ✅
            volume_val = volume_vals[i]      # ✅

            # متغيرات مؤقتة لهذه الشمعة
            entering_trade = False
            exiting_trade = False
            exit_price = None
            exit_reason = None
            pnl = 0.0
            pnl_percentage = 0.0
            balance_before_exit = account_balance 

            
            volume_bar = volume_bars_dict.get(current_time_sec)
            climax_point = climax_points_dict.get(current_time_sec)            
            
            closed_trade_id = None
            closed_position_type = None

            # حساب الربح غير المتحقق إذا كان هناك مركز مفتوح
            unrealized_pnl = 0.0
            if current_state != 'NEUTRAL' and entry_price > 0:
                if current_state == 'LONG':
                    unrealized_pnl = (close_price - entry_price) * position_size
                else:
                    unrealized_pnl = (entry_price - close_price) * position_size
            
            current_account_balance = account_balance + unrealized_pnl

            # ==========================================================
            # المرحلة 1: التنفيذ (Execution) - عند فتح الشمعة
            # ==========================================================
            
            # تسجيل القرار المنفذ حالياً
            executed_decision = pending_decision

            # ✅ إصلاح جوهري: إشارة الخروج من قواعد الاستراتيجية (exit_rules)
            # تعود كـ HOLD مع metadata.trigger == "exit_rule" — كان المحرك
            # يتجاهلها تماماً فلا يُغلق المركز أبداً إلا عبر SL/TP!
            exit_signal_triggered = bool(
                pending_decision
                and pending_decision.action == DecisionAction.HOLD
                and current_state != 'NEUTRAL'
                and isinstance(getattr(pending_decision, "metadata", None), dict)
                and pending_decision.metadata.get("trigger") == "exit_rule"
            )

            target_state = 'NEUTRAL'
            
            if pending_decision:
                if pending_decision.action == DecisionAction.BUY:
                    target_state = 'LONG'
                elif pending_decision.action == DecisionAction.SELL:
                    if not config.enable_short_selling:
                        target_state = 'NEUTRAL'
                    else:
                        target_state = 'SHORT'
                # الأحوال الأخرى (Hold) تبقى NEUTRAL
            
            # تنفيذ إغلاق مركز قديم (Signal Reversal أو Exit Signal)
            # ✅ إصلاح: لم نعد نعيد تعيين close_price (كان يشوّه بقية حسابات الشمعة).
            # نستخدم متغيراً منفصلاً execution_price مع الحفاظ على دلالات Next-Bar-Open
            should_close_position = (
                (target_state != 'NEUTRAL' and current_state != 'NEUTRAL' and current_state != target_state)
                or exit_signal_triggered
            )
            if should_close_position:
                execution_price = open_price
                
                initial_investment = entry_price * position_size
                if current_state == 'LONG':
                    pnl_close = (execution_price - entry_price) * position_size
                else:
                    pnl_close = (entry_price - execution_price) * position_size
                
                pnl_percentage = (pnl_close / initial_investment) * 100 if initial_investment != 0 else 0
                
                exiting_trade = True
                pnl = pnl_close
                exit_price = execution_price
                exit_reason = (
                    f"Exit Signal: {executed_decision.reason}"
                    if exit_signal_triggered
                    else f"Signal Reversal: {target_state}"
                )
                
                # حفظ البيانات قبل المسح
                closed_trade_id = trade_id
                closed_position_type = current_state
                
                balance_before_exit = account_balance
                
                net_pnl_closed = self._close_trade_logic(trades, trade_id, execution_price, current_time, exit_reason, pnl_close, pnl_percentage, config)
                
                account_balance += net_pnl_closed
                cumulative_pnl += net_pnl_closed
                pnl = net_pnl_closed
                pnl_percentage = (net_pnl_closed / initial_investment) * 100 if initial_investment != 0 else 0
                equity_curve.append(account_balance)
                
                # تصفير الحالة
                current_state = 'NEUTRAL'
                trade_id = None
                entry_price = 0.0
                position_size = 0.0
                sl_price = 0.0
                tp_price = 0.0
            
            # فتح مركز جديد
            if target_state != 'NEUTRAL' and current_state == 'NEUTRAL':
                entry_price = open_price
                entry_time = current_time
                
                risk_amount = account_balance * config.position_size_percent
                position_size = risk_amount / entry_price 
                
                if config.stop_loss_percent:
                    sl_offset = entry_price * (config.stop_loss_percent / 100)
                    if target_state == 'LONG':
                        sl_price = entry_price - sl_offset
                    else:
                        sl_price = entry_price + sl_offset
                
                if config.take_profit_percent:
                    tp_offset = entry_price * (config.take_profit_percent / 100)
                    if target_state == 'LONG':
                        tp_price = entry_price + tp_offset
                    else:
                        tp_price = entry_price - tp_offset

                current_state = target_state
                trade_id = str(uuid.uuid4())
                entering_trade = True
                
                risk_reward_ratio = 0.0
                if sl_price > 0 and tp_price > 0:
                    if target_state == 'LONG':
                        risk = entry_price - sl_price
                        reward = tp_price - entry_price
                    else:
                        risk = sl_price - entry_price
                        reward = entry_price - tp_price
                    risk_reward_ratio = reward / risk if risk != 0 else 0
                
                commission = entry_price * position_size * config.commission_rate
                trade = Trade(
                    id=trade_id,
                    symbol=symbol,
                    entry_time=entry_time,
                    exit_time=None,
                    entry_price=entry_price,
                    exit_price=None,
                    position_type='long' if target_state == 'LONG' else 'short',
                    position_size=position_size,
                    pnl=None,
                    pnl_percentage=None,
                    commission=commission,
                    slippage=0,
                    stop_loss=sl_price if config.stop_loss_percent else None,
                    take_profit=tp_price if config.take_profit_percent else None,
                    exit_reason=None,
                    metadata={
                        'strategy': config.strategy_config.get('name', 'Unknown'),
                        'decision_reason': executed_decision.reason if executed_decision else None,
                        'confidence': executed_decision.confidence if executed_decision else None,
                        'risk_reward_ratio': risk_reward_ratio
                    }
                )
                trades.append(trade)

            # ==========================================================
            # المرحلة 2: إدارة المخاطر (SL/TP) - داخل الشمعة
            # ==========================================================
            
            if current_state != 'NEUTRAL':
                stop_hit = False
                take_profit_hit = False
                
                if current_state == 'LONG':
                    if low_price <= sl_price:
                        exit_price = sl_price
                        exit_reason = "Stop Loss Hit"
                        stop_hit = True
                    elif high_price >= tp_price:
                        exit_price = tp_price
                        exit_reason = "Take Profit Hit"
                        take_profit_hit = True
                elif current_state == 'SHORT':
                    if high_price >= sl_price:
                        exit_price = sl_price
                        exit_reason = "Stop Loss Hit"
                        stop_hit = True
                    elif low_price <= tp_price:
                        exit_price = tp_price
                        exit_reason = "Take Profit Hit"
                        take_profit_hit = True
                
                if stop_hit or take_profit_hit:
                    if current_state == 'LONG':
                        pnl = (exit_price - entry_price) * position_size
                    else:
                        pnl = (entry_price - exit_price) * position_size
                    
                    initial_investment = entry_price * position_size
                    pnl_percentage = (pnl / initial_investment) * 100 if initial_investment != 0 else 0
                    
                    exiting_trade = True
                    balance_before_exit = account_balance
                    
                    # ✅ حفظ البيانات قبل إعادة التعيين (مهم جداً للمرحلة 4)
                    closed_trade_id = trade_id
                    closed_position_type = current_state
                    
                    net_pnl_closed = self._close_trade_logic(trades, trade_id, exit_price, current_time, exit_reason, pnl, pnl_percentage, config)
                    
                    current_state = 'NEUTRAL'
                    account_balance += net_pnl_closed
                    cumulative_pnl += net_pnl_closed
                    pnl = net_pnl_closed
                    pnl_percentage = (net_pnl_closed / initial_investment) * 100 if initial_investment != 0 else 0
                    equity_curve.append(account_balance)
                    
                    # تصفير المتغيرات
                    trade_id = None
                    entry_price = 0.0
                    position_size = 0.0
                    sl_price = 0.0
                    tp_price = 0.0
                    
                    # ✅ تمت إزالة 'continue' للسماح بتسجيل البيانات البصرية للشمعة الحالية
                    # إذا أردت منع فتح صفقة جديدة في نفس الشمعة بعد إغلاق، يمكن إضافة flag هنا.
                    pending_decision = None

            # ==========================================================
            # المرحلة 3: التحليل (Strategy Analysis)
            # ==========================================================
            # ✅ السطر الذهبي: نمرر البيانات الكاملة + رقم الشمعة الحالية
            # هذا سيجعل الـ Identity Check في _prepare_indicators يعمل (Zero Time)
            # ولن يحتاج النظام لأي نسخ أو قص للبيانات
            
            try:
                t0 = time.perf_counter()
                # ✅ تمرير حالة المركز: قواعد الخروج تُقيَّم فقط مع مركز مفتوح،
                # وقواعد الدخول تُقيَّم دائماً (للسماح بانعكاس الاتجاه LONG↔SHORT)
                decision = await strategy_engine.run(
                    strategy_engine.full_data,
                    current_index=i,
                    in_position=(current_state != 'NEUTRAL'),
                )
                elapsed = time.perf_counter() - t0
                t_strategy += elapsed

                if i % 1000 == 0:
                    logger.debug(
                        f"[{symbol}] candle={i+1}/{len(data)} | "
                        f"strategy_time={elapsed:.4f}s"
                    )
                
                pending_decision = decision
            except Exception as inner_e:
                pending_decision = None



            # ==========================================================
            # المرحلة 4: البيانات البصرية (Visuals) — تُبنى لعينات فقط على البيانات الضخمة
            # ==========================================================
            create_visual = (
                visual_step == 1
                or (i % visual_step == 0)
                or entering_trade or exiting_trade
                or i == 0 or i == len(data) - 1
            )
            if create_visual:
                # ==========================================================
                # المرحلة 4: البيانات البصرية (Visuals)
                # ==========================================================
            
                indicators = {}
                if hasattr(strategy_engine, 'current_data_frame'):
                    processed_df = strategy_engine.current_data_frame
                    if processed_df is not None and len(processed_df) > 0:
                        # ✅ جلب الشمعة الحالية بدقة
                        last_row = processed_df.iloc[i]
                    
                        for col in processed_df.columns:
                            if col not in ['open', 'high', 'low', 'close', 'volume']:
                                val = last_row[col]
                            
                                # ✅ الإصلاح الجذري: التعامل مع مشكلة تضارب الأعمدة (Duplicate Columns)
                                # إذا كان المتغير Series (لأن الاسم مكرر)، سنقوم بأخذ أول قيمة صالحة (Scalar)
                                # هذا يحل مشكلة Pydantic التي ترفض Series وتتطلب Float
                                if isinstance(val, pd.Series):
                                    # نحاول جلب أول قيمة غير NaN من السلسلة
                                    val = val.dropna().iloc[0] if not val.dropna().empty else None
                            
                                if pd.notna(val):
                                    if isinstance(val, (int, float, np.number)):
                                        indicators[col] = float(val)
                                    # ✅ التأكد من تحويل Timestamp لقيمة مقبولة إذا لزم الأمر
                                    elif isinstance(val, pd.Timestamp):
                                        indicators[col] = float(val.timestamp())
                                    else:
                                        # إذا كان أي نوع آخر غير رقمي (مثل Dict) نتركه كما هو فقط إذا كان مطلوباً
                                        # لكن الأفضل تجنب المشاكل بإغلاقها هنا
                                        indicators[col] = val


                # حسابات الحقول الإضافية
                price_change_percent = 0.0
                if open_price != 0:
                    price_change_percent = ((close_price - open_price) / open_price) * 100
            
                volatility = indicators.get('atr', 0.0)
                if volatility == 0.0 and close_price != 0:
                    volatility = ((high_price - close_price) / close_price) * 100
            
                market_condition = "Neutral"
                if 'ema1' in indicators and 'ema2' in indicators:
                    market_condition = "Bullish Trend" if indicators['ema1'] > indicators['ema2'] else "Bearish Trend"
                elif price_change_percent > 0.5:
                    market_condition = "Strong Bullish"
                elif price_change_percent < -0.5:
                    market_condition = "Strong Bearish"
            
                signal_strength = pending_decision.confidence if pending_decision else 0.0
            
                leverage_used = getattr(config, 'leverage', 1.0)
                margin_used = 0.0
                if current_state != 'NEUTRAL':
                    margin_used = (position_size * close_price) / leverage_used
            
                free_margin = current_account_balance - margin_used
                roi = (cumulative_pnl / config.initial_capital * 100) if config.initial_capital > 0 else 0.0

                t0 = time.perf_counter()





                visual_candle = VisualCandle(
                    timestamp=current_time,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume_val,
                    indicators=indicators,
                    strategy_decision=pending_decision.action.value if pending_decision else None,
                    triggered_rules=getattr(pending_decision, 'triggered_rules', []) if pending_decision else [],
                    confidence=pending_decision.confidence if pending_decision else None,
                    position_state=current_state,
                    account_balance=current_account_balance,
                    cumulative_pnl=cumulative_pnl,
                    position_size=position_size,
                    entry_price=entry_price,
                    stop_loss=sl_price,
                    take_profit=tp_price,
                    risk_reward_ratio=0.0,
                    current_pnl=unrealized_pnl,
                    unrealized_pnl=unrealized_pnl,
                    market_condition=market_condition,
                    signal_strength=signal_strength,
                    price_change_percent=float(price_change_percent),
                    volatility=float(volatility),
                    leverage_used=float(leverage_used),
                    margin_used=float(margin_used),
                    free_margin=float(free_margin),
                    return_on_investment=float(roi),
                    volume_bar=volume_bar,
                    climax_point=climax_point
                )
            
                # تسجيل صفقات الدخول
                if entering_trade:
                    visual_candle.trade_action = f"ENTRY_{current_state}"
                    visual_candle.trade_id = trade_id
                    visual_candle.trade_price = float(entry_price)
                    visual_candle.trade_size = float(position_size)
                
                    trade_points.append({
                        "timestamp": current_time,
                        "type": "entry",
                        "trade_id": trade_id,
                        "price": float(entry_price),
                        "position_type": current_state.lower(),
                        "position_size": float(position_size),
                        "entry_price": float(entry_price),
                        "stop_loss": float(sl_price),
                        "take_profit": float(tp_price),
                        "indicators_snapshot": indicators,
                        "decision_reason": executed_decision.reason if executed_decision else None,
                        "confidence": executed_decision.confidence if executed_decision else None,
                        "account_balance_before": account_balance,
                        "commission": float(entry_price * position_size * config.commission_rate)
                    })
            
                # تسجيل صفقات الإغلاق (مع استخدام المتغيرات المحفوظة)
                if exiting_trade:
                    # استخدام المتغيرات المحفوظة إذا كنا أغلقنا الصفقة في هذه الدورة
                    # وإلا استخدام القيم الحالية (لإغلاق نهاية البيانات)
                    record_trade_id = closed_trade_id if closed_trade_id else trade_id
                    record_position_type = closed_position_type if closed_position_type else current_state
                
                    visual_candle.trade_action = f"EXIT_{record_position_type.upper()}"
                    visual_candle.trade_id = record_trade_id
                    visual_candle.trade_price = float(exit_price)
                    visual_candle.pnl = float(pnl)
                    visual_candle.pnl_percentage = float(pnl_percentage)
                
                    exit_commission = exit_price * position_size * config.commission_rate if exit_price and position_size > 0 else 0.0
                
                    trade_points.append({
                        "timestamp": current_time,
                        "type": "exit",
                        "trade_id": record_trade_id,
                        "price": float(exit_price),
                        "exit_price": float(exit_price),
                        "exit_reason": exit_reason,
                        "pnl": float(pnl),
                        "pnl_percentage": float(pnl_percentage),
                        "entry_price": float(entry_price),
                        "position_size": float(position_size),
                        "position_type": record_position_type.lower(),
                        "holding_period": (current_time - entry_time).total_seconds() / 3600 if entry_time else 0,
                        "account_balance_before": float(balance_before_exit),
                        "account_balance_after": account_balance,
                        "cumulative_pnl": cumulative_pnl,
                        "commission": float(exit_commission),
                        "stop_loss": float(sl_price),
                        "take_profit": float(tp_price)
                    })
            
                visual_candles.append(visual_candle)
                t_visual += time.perf_counter() - t0
                t_loop += time.perf_counter() - t_loop_start

        # إغلاق في نهاية البيانات
        if current_state != 'NEUTRAL' and trade_id:
            exit_price = data['close'].iloc[-1]
            exit_reason = "End of Data"
            
            if current_state == 'LONG':
                pnl = (exit_price - entry_price) * position_size
            else:
                pnl = (entry_price - exit_price) * position_size
            
            initial_investment = entry_price * position_size
            pnl_percentage = (pnl / initial_investment) * 100 if initial_investment != 0 else 0
            
            net_pnl_closed = self._close_trade_logic(trades, trade_id, exit_price, data.index[-1], exit_reason, pnl, pnl_percentage, config)
            account_balance += net_pnl_closed
            cumulative_pnl += net_pnl_closed
            pnl = net_pnl_closed
            pnl_percentage = (net_pnl_closed / initial_investment) * 100 if initial_investment != 0 else 0
            equity_curve.append(account_balance)
            
            # تحديث آخر شمعة بالبيانات
            if visual_candles:
                last_candle = visual_candles[-1]
                last_candle.trade_action = f"EXIT_{current_state}"
                last_candle.trade_id = trade_id
                last_candle.trade_price = float(exit_price)
                last_candle.pnl = float(pnl)
                last_candle.pnl_percentage = float(pnl_percentage)
                last_candle.account_balance = account_balance
                last_candle.cumulative_pnl = cumulative_pnl
                
                # إضافة نقطة خروج للنهاية
                trade_points.append({
                    "timestamp": data.index[-1],
                    "type": "exit",
                    "trade_id": trade_id,
                    "price": float(exit_price),
                    "exit_price": float(exit_price),
                    "exit_reason": "End of Data",
                    "pnl": float(pnl),
                    "pnl_percentage": float(pnl_percentage),
                    "entry_price": float(entry_price),
                    "position_size": float(position_size),
                    "position_type": current_state.lower(),
                    "holding_period": (data.index[-1] - entry_time).total_seconds() / 3600 if entry_time else 0,
                    "account_balance_before": account_balance - pnl,
                    "account_balance_after": account_balance,
                    "cumulative_pnl": cumulative_pnl,
                    "commission": float(exit_price * position_size * config.commission_rate),
                    "stop_loss": float(sl_price),
                    "take_profit": float(tp_price)
                })

        return trades, equity_curve, visual_candles, trade_points


    def _convert_to_serializable(self, obj):
        """تحويل الكائنات إلى صيغة قابلة للتسلسل (لـ JSON)"""
        import numpy as np
        import pandas as pd
        from datetime import datetime
        
        if isinstance(obj, (np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, (np.int32, np.int64)):
            return int(obj)
        elif isinstance(obj, np.ndarray):
            return [self._convert_to_serializable(x) for x in obj.tolist()]
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._convert_to_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_serializable(x) for x in obj]
        elif pd.isna(obj):  # للتعامل مع NaN
            return None
        else:
            return obj



    def _close_trade_logic(self, trades: List[Trade], trade_id: str, exit_price: float, 
                          exit_time: datetime, reason: str, pnl: float, pnl_percentage: float,
                          config: Optional[BacktestConfig] = None) -> float:
        """دالة مساعدة لتحديث بيانات الصفقة عند الإغلاق.

        ✅ إصلاح جوهري: كان يحسب العمولة للسجل فقط بينما يحدّث المحرك الرصيد
        بالـ pnl الخام (بدون رسوم) — فتُهمل commission/slippage من كل النتائج.
        الآن يعيد صافي الربح بعد خصم:
          - عمولة الدخول (config.commission_rate) — كانت مسجلة عند الفتح
          - عمولة الخروج (config.commission_rate بدل 0.001 hardcoded)
          - تكلفة الانزلاق (config.slippage_percent) على الطرفين
        """
        net_pnl = pnl
        for trade in trades:
            if trade.id == trade_id and trade.exit_time is None:
                trade.exit_time = exit_time
                trade.exit_price = exit_price
                trade.exit_reason = reason
                trade.pnl = pnl
                trade.pnl_percentage = pnl_percentage
                
                commission_rate = float(getattr(config, "commission_rate", 0.001) if config else 0.001)
                # ✅ slippage_percent يُعامل ككسر (0.001 = 0.1%) اتساقاً مع commission_rate
                slippage_rate = float(getattr(config, "slippage_percent", 0.0) if config else 0.0)
                
                # عمولة الخروج (بدل 0.001 الثابتة)
                commission_exit = exit_price * trade.position_size * commission_rate
                trade.commission += commission_exit
                
                # تكلفة الانزلاق على الطرفين (سوء تنفيذ افتراضي)
                slippage_cost = (
                    trade.entry_price * trade.position_size * slippage_rate
                    + exit_price * trade.position_size * slippage_rate
                )
                trade.slippage = slippage_cost
                
                # صافي الربح بعد كل التكاليف
                net_pnl = pnl - trade.commission - slippage_cost
                trade.pnl = net_pnl
                
                if trade.entry_price > 0:
                    trade.pnl_percentage = (net_pnl / (trade.entry_price * trade.position_size)) * 100
                break
        return net_pnl






    def _update_capital(self, trades: List[Trade], initial_capital: float) -> float:
        """دالة مساعدة لحساب رأس المال الحالي بناءً على جميع الصفقات المغلقة"""
        current_capital = initial_capital
        for trade in trades:
            # نجمع الربح/الخسارة من الصفقات المغلقة فقط
            if trade.exit_time is not None and trade.pnl is not None:
                current_capital += trade.pnl
        return current_capital











    async def _create_backtest_result(
        self,
        config: BacktestConfig,
        trades: List[Trade],
        equity_curve: List[float],
        visual_candles: List[VisualCandle],
        trade_points: List[Dict[str, Any]],        
        execution_start: datetime
    ) -> BacktestResult:
        """إنشاء كائن النتيجة النهائية وحساب المقاييس"""
        import uuid
        from datetime import datetime
        from typing import Dict
        
        # 1. استخدام حاسبة المقاييس
        metrics = self.metrics_calculator.calculate(trades, config.initial_capital)
        
        execution_time = (datetime.utcnow() - execution_start).total_seconds()
        
        # 2. حساب القيم الأساسية
        final_capital = equity_curve[-1] if equity_curve else config.initial_capital
        total_pnl = final_capital - config.initial_capital
        total_pnl_percent = (total_pnl / config.initial_capital * 100) if config.initial_capital > 0 else 0
        
        # 3. حساب منحنى الانخفاض
        drawdown_curve = self.metrics_calculator._calculate_drawdown_curve(equity_curve)
        
        # 4. حساب الحقول الإضافية المطلوبة
        basic_metrics = self.metrics_calculator._calculate_basic_metrics(trades)
        risk_metrics = self.metrics_calculator._calculate_risk_metrics(equity_curve, drawdown_curve)
        timing_metrics = self.metrics_calculator._calculate_timing_metrics(trades)
        advanced_metrics = self.metrics_calculator._calculate_advanced_metrics(trades, equity_curve)
        
        # 5. حساب العوائد الشهرية والسنوية (مبسطة)
        monthly_returns = self._calculate_monthly_returns(equity_curve, config)
        yearly_returns = self._calculate_yearly_returns(equity_curve, config)
        
        # 6. حساب أداء الرموز
        symbols_performance = self._calculate_symbols_performance(trades, config, visual_candles)

        indicator_data = {}
        if visual_candles:
            # استخراج أسماء جميع المؤشرات من أول شمعة
            first_candle = visual_candles[0]
            for indicator_name in first_candle.indicators.keys():


                sample_val = first_candle.indicators.get(indicator_name)
                
                if isinstance(sample_val, dict):
                    continue
                timestamps_list = [float(c.timestamp.timestamp()) for c in visual_candles]

                values_list = [self._convert_to_serializable(c.indicators.get(indicator_name)) for c in visual_candles]

                indicator_data[indicator_name] = {
                    "values": values_list,            # ✅ القيم المعالجة
                    "timestamps": timestamps_list      # ✅ التواريخ المحولة لـ Float
                }
                # indicator_data[indicator_name] = {
                #     "values": [candle.indicators.get(indicator_name) for candle in visual_candles],
                #     "timestamps": [candle.timestamp for candle in visual_candles]
                # }


        # 7. إنشاء BacktestResult الكامل
        return BacktestResult(
            # ★ الحقول الأساسية
            id=str(uuid.uuid4()),
            config=config,
            execution_time_seconds=execution_time,
            timestamp=datetime.utcnow(),


            
            visual_candles=visual_candles,
            trade_points=trade_points,
            indicator_data=indicator_data,
            # ★ الأداء العام
            initial_capital=config.initial_capital,
            final_capital=final_capital,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,  # ★ الاسم الصحيح من schemas.py
            annual_return_percent=metrics.get('annual_return_percent', 0.0),
            
            # ★ العائد المعدل بالمخاطرة
            sharpe_ratio=metrics.get('sharpe_ratio', 0.0),
            sortino_ratio=metrics.get('sortino_ratio', 0.0),
            calmar_ratio=metrics.get('calmar_ratio', 0.0),
            
            # ★ المقاييس الأساسية
            total_trades=len(trades),
            winning_trades=basic_metrics.get('winning_trades', 0),
            losing_trades=basic_metrics.get('losing_trades', 0),
            win_rate=basic_metrics.get('win_rate', 0.0),
          
            profit_factor=(
                basic_metrics.get('profit_factor')
                if basic_metrics.get('profit_factor') not in (float('inf'), float('-inf'))
                else None
            ),

            expectancy=basic_metrics.get('expectancy', 0.0),
            
            # ★ المخاطرة
            max_drawdown_percent=risk_metrics.get('max_drawdown_percent', 0.0),
            max_drawdown_duration_days=risk_metrics.get('max_drawdown_duration_days', 0),
            volatility_annual=risk_metrics.get('volatility_annual', 0.0),
            var_95=risk_metrics.get('var_95', 0.0),
            cvar_95=risk_metrics.get('cvar_95', 0.0),
            
            # ★ التفاصيل
            trades=trades,  # ★ الصفقات نفسها (مهم!)
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            monthly_returns=monthly_returns,
            yearly_returns=yearly_returns,
            
            # ★ تحليل الصفقات
            avg_winning_trade=basic_metrics.get('avg_winning_trade', 0.0),
            avg_losing_trade=basic_metrics.get('avg_losing_trade', 0.0),
            largest_winning_trade=basic_metrics.get('largest_winning_trade', 0.0),
            largest_losing_trade=basic_metrics.get('largest_losing_trade', 0.0),
            avg_trade_duration_hours=timing_metrics.get('avg_trade_duration_hours', 0.0),
            
            # ★ ربحية الرموز
            symbols_performance=symbols_performance,
            
            # ★ الكفاءة
            system_quality_number=advanced_metrics.get('system_quality_number', 0.0),
            kelly_criterion=advanced_metrics.get('kelly_criterion', 0.0),
            
            # ★ الحقول الاختيارية
            recovery_factor=advanced_metrics.get('recovery_factor'),
            ulcer_index=advanced_metrics.get('ulcer_index'),
            raw_data=None
        )





    def _calculate_monthly_returns(self, equity_curve: List[float], config: BacktestConfig) -> Dict[str, float]:
        """
        حساب العوائد الشهرية الحقيقية بناءً على منحنى الأسهم والبيانات التاريخية
        
        Args:
            equity_curve: منحنى رأس المال عبر الوقت
            config: إعدادات الباك-تست
        
        Returns:
            Dict[str, float]: قاموس بالعوائد الشهرية بنسبة مئوية {yyyy-mm: return%}
        """
        if len(equity_curve) < 10:  # الحد الأدنى للمعنى الإحصائي
            return {}
        
        try:

            
            # 1. إنشاء تواريخ واقعية بناءً على timeframe
            timeframes = {
                '1m': 'T', '5m': '5T', '15m': '15T', '30m': '30T',
                '1h': 'H', '2h': '2H', '4h': '4H', '6h': '6H', '8h': '8H', '12h': '12H',
                '1d': 'D', '3d': '3D', '1w': 'W', '1M': 'M'
            }
            
            freq = timeframes.get(config.timeframe, 'H')  # افتراضي ساعة
            
            # حساب عدد البارات بناءً على الفترة الزمنية
            start_date = config.start_date
            end_date = config.end_date
            
            # إنشاء التواريخ لكل نقطة في equity_curve
            if len(equity_curve) == 1:
                dates = [start_date]
            else:
                dates = pd.date_range(
                    start=start_date, 
                    end=end_date, 
                    periods=len(equity_curve),
                    tz=start_date.tzinfo
                )
            
            # 2. إنشاء DataFrame للتحليل
            df = pd.DataFrame({
                'date': dates,
                'equity': equity_curve
            })
            df.set_index('date', inplace=True)
            
            # 3. إعادة عينة إلى نهاية كل شهر
            monthly_equity = df['equity'].resample('M').last()
            
            if len(monthly_equity) < 3:  # نحتاج شهرين على الأقل لحساب العائد
                return {}
            
            # 4. حساب العوائد الشهرية
            monthly_returns = {}
            for i in range(1, len(monthly_equity)):
                current_date = monthly_equity.index[i]
                prev_date = monthly_equity.index[i-1]
                
                current_equity = monthly_equity.iloc[i]
                prev_equity = monthly_equity.iloc[i-1]
                
                if prev_equity > 0:
                    monthly_return = ((current_equity - prev_equity) / prev_equity) * 100
                    key = current_date.strftime("%Y-%m")
                    monthly_returns[key] = float(monthly_return)
            

            if monthly_returns:
                returns_list = list(monthly_returns.values())
                stats = {
                    'avg_monthly_return': float(np.mean(returns_list)),
                    'std_monthly_return': float(np.std(returns_list)),
                    'best_month': max(monthly_returns.items(), key=lambda x: x[1])[0] if monthly_returns else None,
                    'worst_month': min(monthly_returns.items(), key=lambda x: x[1])[0] if monthly_returns else None,
                    'positive_months': int(sum(1 for r in returns_list if r > 0)),
                    'negative_months': int(sum(1 for r in returns_list if r < 0)),
                    'consistency_rate': float((sum(1 for r in returns_list if r > 0) / len(returns_list) * 100) if returns_list else 0)
                }
                
                # تحويل كل القيم إلى Python types
                monthly_returns_clean = {}
                for k, v in monthly_returns.items():
                    monthly_returns_clean[k] = float(v) if isinstance(v, (np.float32, np.float64, float)) else v
                
                monthly_returns_clean['_stats'] = stats
                return self._convert_to_serializable(monthly_returns_clean)
            
            return {}
        

        except Exception as e:
            logger.exception(f"خطأ في حساب العوائد الشهرية: {e}")
            return {}

    def _calculate_yearly_returns(self, equity_curve: List[float], config: BacktestConfig) -> Dict[str, float]:
        """
        حساب العوائد السنوية الحقيقية بناءً على منحنى الأسهم
        
        Args:
            equity_curve: منحنى رأس المال عبر الوقت
            config: إعدادات الباك-تست
        
        Returns:
            Dict[str, float]: قاموس بالعوائد السنوية بنسبة مئوية {yyyy: return%}
        """
        if len(equity_curve) < 50:  # الحد الأدنى للمعنى الإحصائي
            return {}
        
        try:

            
            # 1. إنشاء تواريخ واقعية
            start_date = config.start_date
            end_date = config.end_date
            
            if len(equity_curve) == 1:
                dates = [start_date]
            else:
                dates = pd.date_range(
                    start=start_date, 
                    end=end_date, 
                    periods=len(equity_curve),
                    tz=start_date.tzinfo
                )
            
            # 2. إنشاء DataFrame
            df = pd.DataFrame({
                'date': dates,
                'equity': equity_curve
            })
            df.set_index('date', inplace=True)
            
            # 3. استخراج السنوات الموجودة في البيانات
            df['year'] = df.index.year
            yearly_data = df.groupby('year')['equity'].agg(['first', 'last'])
            
            yearly_returns = {}
            for year, row in yearly_data.iterrows():
                if row['first'] > 0:
                    yearly_return = ((row['last'] - row['first']) / row['first']) * 100
                    yearly_returns[str(year)] = float(yearly_return)
            
            # 4. حساب العائد السنوي المعدل (Annualized)
            if len(equity_curve) >= 2:
                total_return = ((equity_curve[-1] - equity_curve[0]) / equity_curve[0]) * 100 if equity_curve[0] > 0 else 0
                
                # حساب عدد السنوات الكسرية
                days_diff = (end_date - start_date).days
                years_diff = days_diff / 365.25
                
                if years_diff > 0:
                    annualized_return = ((1 + total_return/100) ** (1/years_diff) - 1) * 100
                    yearly_returns['annualized'] = float(annualized_return)
                    yearly_returns['cagr'] = float(annualized_return)  # معدل النمو السنوي المركب
            
            # 5. إضافة إحصائيات إضافية
            if yearly_returns and len(yearly_returns) > 1:

                yearly_returns_only = [v for k, v in yearly_returns.items() if k.isdigit()]
                if yearly_returns_only:
                    stats = {
                        'avg_yearly_return': float(np.mean(yearly_returns_only)),
                        'std_yearly_return': float(np.std(yearly_returns_only)),
                        'best_year': max((k for k in yearly_returns if k.isdigit()), 
                                    key=lambda x: yearly_returns[x]),
                        'worst_year': min((k for k in yearly_returns if k.isdigit()), 
                                        key=lambda x: yearly_returns[x]),
                        'positive_years': int(sum(1 for r in yearly_returns_only if r > 0)),
                        'max_consecutive_positive': int(self._max_consecutive_positive(yearly_returns_only)),
                        'max_consecutive_negative': int(self._max_consecutive_negative(yearly_returns_only))
                    }
                    
                    yearly_returns['_stats'] = stats
            
            # تحويل كل القيم إلى Python types
            yearly_returns_clean = {}
            for k, v in yearly_returns.items():
                if isinstance(v, (np.float32, np.float64, float, int)):
                    yearly_returns_clean[k] = float(v)
                elif isinstance(v, dict):
                    yearly_returns_clean[k] = self._convert_to_serializable(v)
                else:
                    yearly_returns_clean[k] = v
            
            return self._convert_to_serializable(yearly_returns_clean)
            

            
        except Exception as e:
            logger.exception(f"خطأ في حساب العوائد السنوية: {e}")
            return {}

    def _calculate_symbols_performance(self, trades: List[Trade], config: BacktestConfig, visual_candles: List[VisualCandle] = None) -> Dict[str, Dict[str, Any]]:
        """
        حساب أداء متقدم لكل رمز على حدة
        
        Args:
            trades: قائمة الصفقات
            config: إعدادات الباك-تست
        
        Returns:
            Dict[str, Dict[str, Any]]: قاموس بالأداء التفصيلي لكل رمز
        """
        symbols_performance = {}


        last_available_price = None
        if visual_candles and len(visual_candles) > 0:
            # نفترض هنا أن آخر شمعة في القائمة تمثل نهاية فترة الباك تست
            last_available_price = visual_candles[-1].close

            
        for symbol in config.symbols:
            # تصفية صفقات الرمز
            symbol_trades = [t for t in trades if t.symbol == symbol]
            
            if not symbol_trades:
                continue
            
            # الصفقات المكتملة فقط
            completed_trades = [t for t in symbol_trades 
                            if t.exit_time is not None 
                            and t.pnl is not None 
                            and t.entry_price is not None]
            
            if not completed_trades:
                # تحليل الصفقات المفتوحة (إذا وجدت)
                open_trades = [t for t in symbol_trades if t.exit_time is None]
                if open_trades:
                    symbols_performance[symbol] = self._analyze_open_trades(symbol, open_trades, config, last_available_price)
                continue
            
            # 1. المقاييس الأساسية
            total_trades = len(completed_trades)
            winning_trades = [t for t in completed_trades if t.pnl > 0]
            losing_trades = [t for t in completed_trades if t.pnl <= 0]
            breakeven_trades = [t for t in completed_trades if t.pnl == 0]
            
            winning_count = len(winning_trades)
            losing_count = len(losing_trades)
            breakeven_count = len(breakeven_trades)
            
            # 2. إحصائيات الربح/الخسارة
            gross_profit = sum(t.pnl for t in winning_trades)
            gross_loss = abs(sum(t.pnl for t in losing_trades))
            net_profit = gross_profit - gross_loss
            
            # 3. حساب القيمة المستثمرة (مبني على الدخول)
            total_invested = sum(t.entry_price * t.position_size for t in completed_trades)
            avg_position_size = np.mean([t.position_size for t in completed_trades]) if completed_trades else 0
            
            # 4. نسب الأداء
            win_rate = (winning_count / total_trades * 100) if total_trades > 0 else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
            avg_loss = np.mean([abs(t.pnl) for t in losing_trades]) if losing_trades else 0
            
            # 5. نسبة المخاطرة/العائد (Risk/Reward Ratio)
            avg_rr_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            
            # 6. تحليل الصفقات الفردية
            pnls = [t.pnl for t in completed_trades]
            pnl_percentages = [t.pnl_percentage for t in completed_trades if t.pnl_percentage is not None]
            
            # 7. تحليل التوقيت
            durations = []
            for trade in completed_trades:
                if trade.entry_time and trade.exit_time:
                    duration = (trade.exit_time - trade.entry_time).total_seconds() / 3600  # ساعات
                    durations.append(duration)
            
            avg_duration = np.mean(durations) if durations else 0
            
            # 8. تحليل التوزيع الزمني
            monthly_trades = self._analyze_trades_by_month(completed_trades)
            hourly_trades = self._analyze_trades_by_hour(completed_trades)
            
            # 9. حساب الحد الأقصى للانخفاض لكل رمز
            symbol_equity_curve = self._build_symbol_equity_curve(symbol, completed_trades, config.initial_capital)
            symbol_drawdown_curve = self.metrics_calculator._calculate_drawdown_curve(symbol_equity_curve)
            max_drawdown = max(symbol_drawdown_curve) if symbol_drawdown_curve else 0
            
            # 10. حساب تقلبات الرمز
            returns = self.metrics_calculator._calculate_returns(symbol_equity_curve)
            volatility = np.std(returns) * np.sqrt(252) * 100 if returns else 0
            


            performance_data = {
                # الأساسية
                'total_trades': int(len(symbol_trades)),
                'completed_trades': int(len(completed_trades)),
                'open_trades': int(len(symbol_trades) - len(completed_trades)),
                'winning_trades': int(winning_count),
                'losing_trades': int(losing_count),
                'breakeven_trades': int(breakeven_count),
                
                # الأداء المالي
                'gross_profit': float(gross_profit),
                'gross_loss': float(gross_loss),
                'net_profit': float(net_profit),
                'total_invested': float(total_invested),
                'avg_position_size': float(avg_position_size),
                
                # النسب
                'win_rate': float(win_rate),
                'profit_factor': float(profit_factor) if profit_factor != float('inf') else None,
                'avg_win': float(avg_win),
                'avg_loss': float(avg_loss),
                'avg_rr_ratio': float(avg_rr_ratio),
                
                # الإحصائيات
                'best_trade': float(max(pnls)) if pnls else 0.0,
                'worst_trade': float(min(pnls)) if pnls else 0.0,
                'avg_pnl': float(np.mean(pnls)) if pnls else 0.0,
                'std_pnl': float(np.std(pnls)) if len(pnls) > 1 else 0.0,
                'sharpe_ratio': float((np.mean(pnls) / np.std(pnls) * np.sqrt(252)) if len(pnls) > 1 and np.std(pnls) > 0 else 0.0),
                
                # التوقيت
                'avg_trade_duration_hours': float(avg_duration),
                'min_duration': float(min(durations)) if durations else 0.0,
                'max_duration': float(max(durations)) if durations else 0.0,
                
                # المخاطرة
                'max_drawdown_percent': float(max_drawdown),
                'volatility_percent': float(volatility),
                'var_95': float(self._calculate_symbol_var(completed_trades, 0.95)),
                'cvar_95': float(self._calculate_symbol_cvar(completed_trades, 0.95)),
                
                # تحليل متقدم
                'expectancy': float((win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)) if avg_loss > 0 else 0.0,
                'kelly_criterion': float(win_rate/100 - ((100-win_rate)/100) / (avg_win/avg_loss)) if avg_loss > 0 and avg_win > 0 else None,
                'system_quality_number': float(self._calculate_symbol_sqn(completed_trades)),
                
                # تحليل التوزيع (تحويل الأنواع)
                'monthly_distribution': {str(k): int(v) for k, v in monthly_trades.items()} if monthly_trades else None,
                'hourly_distribution': {int(k): int(v) for k, v in hourly_trades.items()} if hourly_trades else None,
                # ✅ كان يتم تمرير كلاس PnlDistribution نفسه هنا (يكسر JSON لاحقاً)
                'pnl_distribution': None,
                
                # بيانات إضافية للرسم البياني
                '_equity_curve': [float(x) for x in symbol_equity_curve],
                '_drawdown_curve': [float(x) for x in symbol_drawdown_curve]
            }
            
            symbols_performance[symbol] = self._convert_to_serializable(performance_data)


        return symbols_performance    
    


    def _max_consecutive_positive(self, values: List[float]) -> int:
        """حساب أقصى عدد متتالي من القيم الموجبة"""
        max_streak = 0
        current_streak = 0
        
        for value in values:
            if value > 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        
        return max_streak

    def _max_consecutive_negative(self, values: List[float]) -> int:
        """حساب أقصى عدد متتالي من القيم السالبة"""
        max_streak = 0
        current_streak = 0
        
        for value in values:
            if value < 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        
        return max_streak

    def _build_symbol_equity_curve(self, symbol: str, trades: List[Trade], initial_capital: float) -> List[float]:
        """بناء منحنى الأسهم لرمز معين"""
        if not trades:
            return [initial_capital]
        
        # ترتيب الصفقات حسب وقت الدخول
        sorted_trades = sorted(trades, key=lambda x: x.entry_time)
        
        curve = [initial_capital]
        current_equity = initial_capital
        
        for trade in sorted_trades:
            # تحديث عند الدخول (العمولة)
            entry_cost = trade.commission if trade.commission else 0
            current_equity -= entry_cost
            curve.append(current_equity)
            
            # تحديث عند الخروج
            if trade.exit_time and trade.pnl is not None:
                current_equity += trade.pnl
                curve.append(current_equity)
        
        return curve

    def _analyze_trades_by_month(self, trades: List[Trade]) -> Dict[str, int]:
        """تحليل الصفقات حسب الشهر"""
        monthly_counts = {}
        
        for trade in trades:
            if trade.entry_time:
                month_key = trade.entry_time.strftime("%Y-%m")
                monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
        
        return monthly_counts

    def _analyze_trades_by_hour(self, trades: List[Trade]) -> Dict[int, int]:
        """تحليل الصفقات حسب ساعة اليوم"""
        hourly_counts = {hour: 0 for hour in range(24)}
        
        for trade in trades:
            if trade.entry_time:
                hour = trade.entry_time.hour
                hourly_counts[hour] = hourly_counts.get(hour, 0) + 1
        
        return hourly_counts

    def _calculate_symbol_var(self, trades: List[Trade], confidence_level: float = 0.95) -> float:
        """حساب Value at Risk للرمز"""
        if not trades:
            return 0.0
        
        pnls = [t.pnl_percentage for t in trades if t.pnl_percentage is not None]
        if not pnls:
            return 0.0
        
        sorted_pnls = np.sort(pnls)
        var_index = int((1 - confidence_level) * len(sorted_pnls))
        
        if var_index < len(sorted_pnls):
            return float(-sorted_pnls[var_index])  # نرجع القيمة الإيجابية للخسارة
        else:
            return float(-sorted_pnls[-1] if sorted_pnls else 0)

    def _calculate_symbol_cvar(self, trades: List[Trade], confidence_level: float = 0.95) -> float:
        """حساب Conditional VaR للرمز"""
        if not trades:
            return 0.0
        
        pnls = [t.pnl_percentage for t in trades if t.pnl_percentage is not None]
        if not pnls:
            return 0.0
        
        sorted_pnls = np.sort(pnls)
        var_index = int((1 - confidence_level) * len(sorted_pnls))
        
        if var_index > 0:
            cvar = np.mean(sorted_pnls[:var_index])
            return float(-cvar)  # نرجع القيمة الإيجابية
        else:
            return 0.0

    def _calculate_symbol_sqn(self, trades: List[Trade]) -> float:
        """حساب System Quality Number للرمز"""
        if not trades:
            return 0.0
        
        pnls = [t.pnl_percentage for t in trades if t.pnl_percentage is not None]
        if not pnls or len(pnls) < 2:
            return 0.0
        
        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls)
        
        if std_pnl == 0:
            return 0.0
        
        return float((mean_pnl / std_pnl) * np.sqrt(len(pnls)))

    def _analyze_pnl_distribution(self, pnls: List[float]) -> Dict[str, Any]:
        """تحليل توزيع الربح/الخسارة"""
        if not pnls:
            return {}
        
        from scipy import stats
        
        distribution = {
            'mean': float(np.mean(pnls)),
            'median': float(np.median(pnls)),
            'std': float(np.std(pnls)),
            'skewness': float(stats.skew(pnls)) if len(pnls) > 2 else 0,
            'kurtosis': float(stats.kurtosis(pnls)) if len(pnls) > 3 else 0,
            'q1': float(np.percentile(pnls, 25)),
            'q3': float(np.percentile(pnls, 75)),
            'iqr': float(np.percentile(pnls, 75) - np.percentile(pnls, 25)),
            'outliers': self._find_outliers(pnls)
        }
        
        return distribution

    def _find_outliers(self, data: List[float]) -> List[float]:
        """العثور على القيم المتطرفة"""
        if len(data) < 4:
            return []
        
        q1 = np.percentile(data, 25)
        q3 = np.percentile(data, 75)
        iqr = q3 - q1
        
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        return [float(x) for x in data if x < lower_bound or x > upper_bound]

    def _analyze_open_trades(self, symbol: str, open_trades: List[Trade], config: BacktestConfig, current_price: float = None) -> Dict[str, Any]:
        """تحليل الصفقات المفتوحة"""
        if not open_trades:
            return {}
        
        current_values = []
        unrealized_pnls = []
        
        for trade in open_trades:
            # ✅ التحسين: استخدام السعر الممرر، والعودة لسعر الدخول فقط إذا لم يتوفر
            calc_price = current_price if current_price is not None else trade.entry_price
            
            if trade.position_type == 'long':
                unrealized_pnl = (calc_price - trade.entry_price) * trade.position_size
            else:  # short
                unrealized_pnl = (trade.entry_price - calc_price) * trade.position_size
            
            current_value = trade.entry_price * trade.position_size + unrealized_pnl
            
            current_values.append(current_value)
            unrealized_pnls.append(unrealized_pnl)
        
        total_unrealized_pnl = sum(unrealized_pnls)
        total_current_value = sum(current_values)
        
        return {
            'open_trades_count': len(open_trades),
            'total_unrealized_pnl': float(total_unrealized_pnl),
            'total_current_value': float(total_current_value),
            'avg_unrealized_pnl': float(np.mean(unrealized_pnls)) if unrealized_pnls else 0,
            'max_unrealized_pnl': float(max(unrealized_pnls)) if unrealized_pnls else 0,
            'min_unrealized_pnl': float(min(unrealized_pnls)) if unrealized_pnls else 0,
            'open_positions_summary': [
                {
                    'id': t.id,
                    'entry_price': t.entry_price,
                    'position_size': t.position_size,
                    'position_type': t.position_type,
                    'unrealized_pnl': float((calc_price - t.entry_price) * t.position_size 
                                        if t.position_type == 'long' 
                                        else (t.entry_price - calc_price) * t.position_size)
                }
                for t in open_trades
            ]
        }

    # ==============================================================
    # Walk-Forward Analysis / Monte Carlo Simulation
    # (منقول من المحرك المرجعي القديم engine.py ومكيّف على محرك
    #  القرارات strategy_engine1 + مخطط BacktestConfig الحالي)
    # ==============================================================

    def _summarize_result(self, result: BacktestResult) -> Dict[str, Any]:
        """ملخص JSON-آمن لنتيجة باك-تست (نافذة تدريب/اختبار)"""
        return {
            "total_pnl_percent": float(result.total_pnl_percent or 0.0),
            "total_pnl": float(result.total_pnl or 0.0),
            "win_rate": float(result.win_rate or 0.0),
            "total_trades": int(result.total_trades or 0),
            "final_capital": float(result.final_capital or 0.0),
            "max_drawdown_percent": float(result.max_drawdown_percent or 0.0),
            "sharpe_ratio": float(result.sharpe_ratio or 0.0),
            "profit_factor": (
                float(result.profit_factor)
                if result.profit_factor is not None
                else None
            ),
        }

    def _distribution_stats(self, values: np.ndarray) -> Dict[str, Any]:
        """إحصاءات توزيع: المتوسط/الانحراف/المدي/القيم القصوى/المئينيات 5-95"""
        if values.size == 0:
            return {}
        return {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "percentile_5": float(np.percentile(values, 5)),
            "percentile_25": float(np.percentile(values, 25)),
            "percentile_50": float(np.percentile(values, 50)),
            "percentile_75": float(np.percentile(values, 75)),
            "percentile_95": float(np.percentile(values, 95)),
        }

    async def run_walk_forward_analysis(
        self,
        config: BacktestConfig,
        train_days: Optional[int] = None,
        test_days: Optional[int] = None,
        max_windows: int = MAX_WALK_FORWARD_WINDOWS,
    ) -> Dict[str, Any]:
        """
        تحليل المشي للأمام (Anchored Walk-Forward):

        - تُقسّم فترة الإعداد إلى نوافذ اختبار متتالية طول كل منها test_days
          (الافتراضي: تقسيم الفترة على عدد النوافذ).
        - لكل نافذة اختبار تُشغَّل نافذة تدريب سابقة عليها (anchored) طولها
          train_days (الافتراضي: 3 أضعاف نافذة الاختبار، وإن لم تتوفر بيانات
          كافية تُتخطى نافذة التدريب).
        - تُشغَّل كل نافذة عبر run_backtest (محرك القرارات نفسه) وتُجمَّع
          النتائج لكل نافذة + إحصاءات إجمالية.

        الحد الأقصى لعدد النوافذ MAX_WALK_FORWARD_WINDOWS = 20 (حد زمني للتشغيل).
        """
        n_windows_cap = max(1, min(int(max_windows or MAX_WALK_FORWARD_WINDOWS), MAX_WALK_FORWARD_WINDOWS))
        total_days = max((config.end_date - config.start_date).days, 1)

        if not test_days or int(test_days) <= 0:
            test_days = max(1, total_days // n_windows_cap)
        else:
            test_days = int(test_days)

        if not train_days or int(train_days) <= 0:
            train_days = test_days * 3  # نسبة تدريب:اختبار الافتراضية 3:1
        else:
            train_days = int(train_days)

        logger.info(
            f"Walk-Forward: total={total_days}d, train={train_days}d, "
            f"test={test_days}d, cap={n_windows_cap} windows"
        )

        windows: List[Dict[str, Any]] = []
        test_start = config.start_date

        while test_start < config.end_date and len(windows) < n_windows_cap:
            test_end = min(test_start + timedelta(days=test_days), config.end_date)
            train_end = test_start
            train_start = max(config.start_date, train_end - timedelta(days=train_days))

            window_entry: Dict[str, Any] = {
                "window": len(windows) + 1,
                "train_start": train_start.isoformat(),
                "train_end": train_end.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
                "in_sample": None,      # نافذة التدريب
                "out_of_sample": None,  # نافذة الاختبار
                "error": None,
            }

            # 1) نافذة التدريب (in-sample) — تُتخطى بصمت إن لم تتوفر بيانات كافية
            if (train_end - train_start).days >= 1:
                try:
                    train_cfg = config.model_copy(
                        update={"start_date": train_start, "end_date": train_end}
                    )
                    train_result = await self.run_backtest(train_cfg)
                    window_entry["in_sample"] = self._summarize_result(train_result)
                except Exception as e:
                    logger.warning(f"Walk-Forward window {len(windows) + 1}: train run failed: {e}")

            # 2) نافذة الاختبار (out-of-sample)
            try:
                test_cfg = config.model_copy(
                    update={"start_date": test_start, "end_date": test_end}
                )
                test_result = await self.run_backtest(test_cfg)
                window_entry["out_of_sample"] = self._summarize_result(test_result)
            except Exception as e:
                logger.warning(f"Walk-Forward window {len(windows) + 1}: test run failed: {e}")
                window_entry["error"] = "Backtest failed for this window (see server logs)"

            windows.append(window_entry)
            test_start = test_end

        # ---- التجميع الإجمالي (على نافذة الاختبار out-of-sample) ----
        oos = [w["out_of_sample"] for w in windows if w.get("out_of_sample")]
        ins = [w["in_sample"] for w in windows if w.get("in_sample")]

        overall: Dict[str, Any] = {
            "total_windows": len(windows),
            "evaluated_windows": len(oos),
            "avg_test_pnl_percent": float(np.mean([r["total_pnl_percent"] for r in oos])) if oos else 0.0,
            "avg_train_pnl_percent": float(np.mean([r["total_pnl_percent"] for r in ins])) if ins else None,
            "avg_test_win_rate": float(np.mean([r["win_rate"] for r in oos])) if oos else 0.0,
            "avg_test_max_drawdown_percent": float(np.mean([r["max_drawdown_percent"] for r in oos])) if oos else 0.0,
            "total_test_trades": int(sum(r["total_trades"] for r in oos)) if oos else 0,
            "profitable_windows": int(sum(1 for r in oos if r["total_pnl_percent"] > 0)),
            "consistency_rate": float(sum(1 for r in oos if r["total_pnl_percent"] > 0) / len(oos)) if oos else 0.0,
        }

        # كفاءة out-of-sample مقابل in-sample (مؤشر المتانة/الإفراط في الملاءمة)
        if ins and overall["avg_train_pnl_percent"]:
            overall["train_test_efficiency"] = float(
                overall["avg_test_pnl_percent"] / overall["avg_train_pnl_percent"]
            )
        else:
            overall["train_test_efficiency"] = None

        if oos:
            best = max(oos, key=lambda r: r["total_pnl_percent"])
            worst = min(oos, key=lambda r: r["total_pnl_percent"])
            overall["best_window"] = best
            overall["worst_window"] = worst

        return {
            "method": "walk_forward",
            "train_days": train_days,
            "test_days": test_days,
            "windows": windows,
            "overall": overall,
        }

    async def run_monte_carlo_simulation(
        self,
        config: BacktestConfig,
        n_simulations: int = 100,
        random_seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        محاكاة مونت كارلو:

        - يُشغَّل باك-تست أساسي واحد للحصول على صفقات حقيقية (من trade_points).
        - ثم يُعاد أخذ عينات (bootstrap with replacement) من أرباح/خسائر
          الصفقات n مرة لبناء توزيع رأس المال النهائي ونسبة العائد
          وتوزيع أقصى الانخفاض (max drawdown).
        - مئينيات 5/25/50/75/95 + احتمال الربح.

        ملاحظة: النسخة المرجعية القديمة كانت تستخدم permutation على نفس
        المجموعة — وهذا لا يغيّر المجموع أبداً (توزيع منحل). هنا نستخدم
        bootstrap حقيقي (عينات مع إرجاع) فتتنوع النتائج فعلياً.

        الحد الأقصى MAX_MONTE_CARLO_SIMULATIONS = 500.
        """
        n = max(1, min(int(n_simulations or 100), MAX_MONTE_CARLO_SIMULATIONS))

        logger.info(f"Monte Carlo: running base backtest then {n} bootstrap simulations")
        base_result = await self.run_backtest(config)
        initial_capital = float(config.initial_capital)

        # أرباح الصفقات المغلقة من نقاط التداول (BacktestResult لا يعرض trades)
        base_pnls = np.array(
            [
                float(tp["pnl"])
                for tp in (base_result.trade_points or [])
                if tp.get("type") == "exit" and tp.get("pnl") is not None
            ],
            dtype=np.float64,
        )

        if base_pnls.size == 0:
            logger.warning("Monte Carlo: no closed trades from base backtest")
            return {
                "method": "monte_carlo",
                "n_simulations": 0,
                "base_trades_used": 0,
                "note": "Not enough closed trades to run the simulation",
                "final_equity": {},
                "return_percent": {},
                "max_drawdown_percent": {},
                "probability_of_profit": 0.0,
                "probability_of_loss": 0.0,
                "value_at_risk_5_percent": 0.0,
            }

        rng = np.random.default_rng(random_seed)
        final_equities = np.empty(n, dtype=np.float64)
        max_drawdowns = np.empty(n, dtype=np.float64)

        for i in range(n):
            sample = rng.choice(base_pnls, size=base_pnls.size, replace=True)
            path = initial_capital + np.cumsum(sample)
            final_equities[i] = path[-1]

            peak = np.maximum.accumulate(path)
            with np.errstate(divide="ignore", invalid="ignore"):
                drawdown = np.where(peak > 0, (peak - path) / peak * 100.0, 0.0)
            max_drawdowns[i] = float(drawdown.max()) if drawdown.size else 0.0

        return_percent = (final_equities / initial_capital - 1.0) * 100.0

        stats = {
            "method": "monte_carlo",
            "n_simulations": n,
            "base_trades_used": int(base_pnls.size),
            "initial_capital": initial_capital,
            "random_seed": random_seed,
            "final_equity": self._distribution_stats(final_equities),
            "return_percent": self._distribution_stats(return_percent),
            "max_drawdown_percent": self._distribution_stats(max_drawdowns),
            "probability_of_profit": float(np.sum(final_equities > initial_capital) / n),
            "probability_of_loss": float(np.sum(final_equities <= initial_capital) / n),
            "value_at_risk_5_percent": float(np.percentile(return_percent, 5)),
        }

        logger.info(
            f"Monte Carlo done: mean_return={stats['return_percent']['mean']:.2f}%, "
            f"prob_of_profit={stats['probability_of_profit'] * 100:.1f}%"
        )
        return stats



