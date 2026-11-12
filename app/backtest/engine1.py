

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


def _resolve_risk_fraction(config: "BacktestConfig") -> float:
    """✅ R58 — توحيد دلالات حجم المركز بين الواجهة والمحرك.

    البلاغ الحي (#10000042 — سولانا): الواجهة ترسل position_size_percent=1
    بمعنى «1%» بينما المحرك كان يضرب القيمة مباشرة ككسر ⇒ 1.0 = 100% من
    الرصيد لكل مركز (أول صفقة: 300$ بالضبط من رأس مال 300$، ومع
    max_positions=3 صارت رافعة خفية 3x ⇒ Drawdown 256% وأحجام سالبة).

    العقد الجديد الموحّد (نفس منطق SL/TP الذي يقبل نسبة مئوية 49 = 49%):
      • position_sizing="percentage" ⇒ القيمة نسبة مئوية حقيقية:
          1 = 1% ، 50 = 50% ، 100 = كامل الرصيد.
      • أي وضع آخر (fixed/افتراضي) ⇒ يبقى الكسر التاريخي (1.0 = 100%)
        بت-بت — فلا يتغير أي سلوك قديم غير الواجهة.
    القيمة تُقصّ نهائياً إلى [0, 1] (لا يمكن للحجم أن يتجاوز الرصيد أو يكون سالباً).

    ✅ R60 — وضع «رأس المال الكامل والربح التزايدي» (compounding):
      طلب المستخدم الحرفي: زر تفعيل يجعل كل صفقة تدخل بكامل الرصيد
    الجاري (رأس المال + كل الأرباح المتراكمة) — الصفقة الأولى 100$،
    ربحها 15$ ⇒ التالية تدخل بـ115$ وهكذا (نمط التشغيلة التاريخية
    #10000010: +804.77%). عند التفعيل: الكسر = 1.0 دائماً مهما كان
    position_size_percent، ومركز مفتوح واحد فقط (max_concurrent=1).
    """
    # ✅ R62 — المراكز المتعددة التراكمية تعلو فوق R60: كل مركز جديد
    # بحجم الرصيد الجاري ÷ عدد المراكز (يتجدد مع كل إقفال ربحاً أو خسارة).
    _multi_n = _multi_position_compounding_enabled(config)
    if _multi_n is not None:
        return 1.0 / float(_multi_n)
    # ✅ R60 — التراكم يعلو فوق كل دلالات الحجم الأخرى
    if bool(getattr(config, "compounding", False)):
        return 1.0
    try:
        _v = float(getattr(config, "position_size_percent", 0.0) or 0.0)
    except (TypeError, ValueError):
        _v = 0.0
    _mode = str(getattr(config, "position_sizing", "") or "").strip().lower()
    _frac = (_v / 100.0) if _mode == "percentage" else _v
    if _frac < 0.0:
        _frac = 0.0
    if _frac > 1.0:
        _frac = 1.0
    return _frac


def _compounding_enabled(config: "BacktestConfig") -> bool:
    """✅ R60 — هل وضع «رأس المال الكامل والربح التزايدي» مفعّل؟

    دالة واحدة مصدر الحقيقة — يستخدمها محلل الكسر وسقف المراكز
    وصدى المخاطر حتى يظل الثلاثة متطابقين دائماً بلا انحراف.
    """
    try:
        return bool(getattr(config, "compounding", False))
    except Exception:  # noqa: BLE001 — القراءة الدفاعية لا تنكسر أبداً
        return False


def _multi_position_compounding_enabled(config: "BacktestConfig") -> "int | None":
    """✅ R62 — هل وضع «المراكز المتعددة والرصيد التراكمي» مفعّل؟

    يعيد عدد الخانات الفعّال (1..10) أو None إن كان معطلاً.
    دالة واحدة مصدر الحقيقة — يستخدمها محلل الكسر وسقف المراكز
    وصدى المخاطر حتى يظل الثلاثة متطابقين دائماً بلا انحراف.
    الوضع يعلو فوق R60 عند تفعيلهما معاً (طلب المستخدم الحرفي:
    الأرباح تعود للرصيد وتشارك في الصفقات التالية مع تعدد المراكز).
    """
    try:
        _on = bool(getattr(config, "multi_position_compounding", False))
    except Exception:  # noqa: BLE001 — القراءة الدفاعية لا تنكسر أبداً
        return None
    if not _on:
        return None
    try:
        _n = int(getattr(config, "max_positions", 0) or 0)
    except (TypeError, ValueError):
        _n = 0
    if _n < 1:
        _n = 1
    if _n > 10:
        _n = 10
    return _n


class _NoopStrategyEngine:
    """
    ✅ الجولة 12 (هوت-فكس): محرك استراتيجية محايد للحمولات الفارغة.

    عندما ترسل الواجهة strategy_config بلا مؤشرات وقواعد (مثل اختبار قبول
    WINUSDT في بند 5-ب.2 لفحص دقة الأسعار تحت السنت) كان التهيئة تفشل في
    StrategyConfig ("At least one entry rule is required") ويفشل التشغيل كله.
    هذا المحرك يُرجع HOLD دائماً — الشموع تُعالج وتُعاد كاملة بصفقات صفر،
    وواجهة كل الدوال مطابقة لـ StrategyEngine (full_data / _prepare_indicators
    / run / current_data_frame) لتبقى بقية المحرك بلا تغيير.
    """

    def __init__(self) -> None:
        self.config = None
        self.current_data_frame = None
        self.full_data = None

    async def _prepare_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        self.current_data_frame = data
        return data

    async def run(self, market_context: pd.DataFrame, current_index: int = None,
                  in_position: bool = False) -> Decision:
        from datetime import datetime as _dt
        return Decision(
            timestamp=_dt.utcnow(),
            action=DecisionAction.HOLD,
            confidence=0.0,
            reason="empty strategy_config → no-signal mode",
            metadata={},
        )

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
                        use_cache=True,
                        tz_offset_minutes=int(getattr(config, "tz_offset_minutes", 0) or 0),
                    )
                    
                    if data.empty:
                        logger.warning(f"No data returned for {symbol}")
                        continue

                    data = self._normalize_candle_index(data)
                    all_data[symbol] = data
                    logger.info(f"Loaded {len(data)} candles for {symbol} "
                                f"({data.index[0]} → {data.index[-1]})")

                except Exception as e:
                    # ✅ الجولة 13.3: أخطاء العقد الصريحة تُنقل كما هي — لا ابتلاع.
                    # (رفض الفريم غير المدعوم من المزود — «Unsupported timeframe …
                    # Supported: […]» — كان يُبتلع هنا ويتحول إلى «No data available
                    # for any symbol» الغامضة؛ الآن يفشل التشغيل برسالته الصريحة
                    # حتى يعرف الواجهة/المستخدم الفريمات المدعومة فوراً.)
                    if "Unsupported timeframe" in str(e):
                        raise
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
            # ✅ الجولة 12 (هوت-فكس): الحمولات الفارغة (indicators=[] وentry_rules=[]
            # وexit_rules=[]) — مثل اختبار قبول WINUSDT في بند 5-ب.2 — كانت تفشل
            # في StrategyConfig ("At least one entry rule is required") بعد تحويل
            # الصمت إلى خطأ صريح. الآن: استراتيجية فارغة = وضع "بدون إشارات"
            # (محرك محايد يُرجع HOLD دائماً) — الشموع تُعاد كاملة بدقة سنتها
            # وصفقات صفر، وهي الطريقة الصحيحة لاختبار دقة الأسعار والبيانات.
            _sc = dict(config.strategy_config or {})
            _is_empty_strategy = not (
                _sc.get("indicators") or _sc.get("entry_rules")
                or _sc.get("exit_rules") or _sc.get("filter_rules")
            )
            if _is_empty_strategy:
                strategy_engine = _NoopStrategyEngine()
                full_calculated_data = data
                strategy_engine.full_data = full_calculated_data
                logger.info(f"[{symbol}] empty strategy_config → no-signal mode (price-only run)")
            else:
                strategy_config_obj = StrategyConfigSchema(**config.strategy_config)
                strategy_engine = StrategyEngine(strategy_config_obj)
                full_calculated_data = await strategy_engine._prepare_indicators(data)
                strategy_engine.full_data = full_calculated_data

            render_data = {}
            volume_bars_dict = {}
            climax_points_dict = {}


        except Exception as e:
            # ✅ الجولة 12: لا صمت بعد اليوم — كان أي فشل تهيئة يعيد 0 صفقة بصمت
            # (مثل شكل composite غير المعروف). الآن الخطأ واضح ويظهر في /status.
            logger.exception(f"CRITICAL ERROR IN STRATEGY INIT: {e}")
            raise ValueError(
                f"فشل تهيئة الاستراتيجية في محرك الباك-تست: {e} — راجع شكل "
                '{"type": "and" | "or", "conditions": [...]} وأسماء المؤشرات '
                "(استخدم POST /api/v1/strategies1/validate للتحقق المسبق)"
            ) from e



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

        # ✅ R55 — سياسة المخاطر الفعلية (كونفيق نظيف):
        # الحقول غير المُرسلة = null = معطّلة. طلب المستخدم الحرفي:
        #   SL=0 أو SL=100 أو عدم الإرسال ⇒ تعطيل الستوب لوز كلياً
        #   TP=0 أو عدم الإرسال ⇒ تعطيل جني الربح
        #   التريلينق من الجذر ⇒ يعمل فعلياً هنا ويُلغي SL/TP (نفس دلالات
        #   محرك الخروج الموحد: القمة تبدأ من سعر الدخول، وكل قمة أعلى ترفع
        #   السقف، وهبوط الإغلاق بنسبة التريلينق من القمة يغلق عند الإغلاق)
        _sl_cfg = config.stop_loss_percent
        _tp_cfg = config.take_profit_percent
        _trail_cfg = config.trailing_stop_percent
        sl_active = _sl_cfg is not None and 0.0 < float(_sl_cfg) < 100.0
        tp_active = _tp_cfg is not None and float(_tp_cfg) > 0.0
        trail_active = _trail_cfg is not None and float(_trail_cfg) > 0.0
        if trail_active:
            sl_active = False
            tp_active = False
        sl_frac = (float(_sl_cfg) / 100.0) if sl_active else None
        tp_frac = (float(_tp_cfg) / 100.0) if tp_active else None
        trail_frac = (float(_trail_cfg) / 100.0) if trail_active else None
        trail_peak = 0.0  # قمة التريلينق للمركز الأساسي (تبدأ من سعر الدخول)

        # ✅ R55 — السقف الرقمي للمراكز المتزامنة (max_positions من الجذر):
        # None أو 1 = السلوك التاريخي بت-بت (مركز واحد)، 2..10 = إشارة جديدة
        # والمراكز المفتوحة < N ⇒ مركز إضافي مستقل بإدارة مخاطر كاملة.
        # ✅ R60 — وضع التراكم (compounding): مركز واحد فقط إجبارياً —
        # طلب المستخدم الحرفي: «اذا النضام في صفقه ما يقدر يفتح صفقه جديده
        # لين يقفلها». 100% من الرصيد في كل صفقة + مركز واحد = صفر رافعة
        # ضمنية (علة #10000042 القديمة مستحيلة الحدوث في هذا الوضع).
        _compounding_on = _compounding_enabled(config)
        _multi_n = _multi_position_compounding_enabled(config)  # ✅ R62
        if _multi_n is not None:
            # ✅ R62 — المراكز المتعددة التراكمية: N خانات فعلية — كل
            # إشارة دخول تفتح مركزاً بحجم الرصيد الجاري ÷ N لحظة الإشارة،
            # والرصيد يتجدد بعد كل إقفال (ربحاً أو خسارة) فتكبر الأحجام.
            max_concurrent = _multi_n
        elif _compounding_on:
            max_concurrent = 1
        else:
            max_concurrent = int(config.max_positions) if (config.max_positions or 0) > 1 else 1
        extra_positions: List[Dict[str, Any]] = []  # المراكز الإضافية 2..N
        max_open_observed = 0
        risk_echo = {
            "stop_loss_percent": float(_sl_cfg) if _sl_cfg is not None else None,
            "stop_loss_active": bool(sl_active),
            "take_profit_percent": float(_tp_cfg) if _tp_cfg is not None else None,
            "take_profit_active": bool(tp_active),
            "trailing_stop_percent": float(_trail_cfg) if _trail_cfg is not None else None,
            "trailing_active": bool(trail_active),
            "trailing_cancels_sl_tp": bool(trail_active),
            "max_positions_requested": int(config.max_positions) if config.max_positions is not None else None,
            "max_concurrent_applied": max_concurrent,
            # ✅ R62 — صدى وضع المراكز المتعددة التراكمية (شفافية كاملة)
            "multi_position_compounding": _multi_n is not None,
            "multi_position_slots": _multi_n,
            # ✅ R60 — صدى وضع التراكم (شفافية كاملة للفرونت والمكتبة)
            "compounding": _compounding_on,
            "compounding_semantics": (
                "R60: كل صفقة بـ100% من الرصيد الجاري + مركز واحد فقط"
                if _compounding_on else None
            ),
            "multi_position_semantics": (
                f"R62: كل مركز جديد = الرصيد الجاري ÷ {_multi_n} "
                f"(حتى {_multi_n} مراكز متزامنة، الحجم يتجدد بعد كل إقفال)"
                if _multi_n is not None else None
            ),
        }

        # ✅ الجولة 12: نموذج التنفيذ المطبق فعلياً (next_open افتراضياً)
        fill_model_str = str(getattr(config, "fill_model", "next_open") or "next_open")

        # ✅ R58 — توحيد دلالات الحجم + جدار النهاية + حاجز الإفلاس
        # (البلاغ #10000042: حجم 100% بدل 1% + تداول بعد نهاية النافذة +
        #  رصيد سالب استمر يتداول بأحجام سالبة وانعكست إشارة الربح)
        _risk_frac = _resolve_risk_fraction(config)
        _end_ts = None
        _end_dt = getattr(config, "end_date", None)
        if _end_dt is not None:
            try:
                _end_ts = int(pd.Timestamp(_end_dt).timestamp())
            except Exception:  # noqa: BLE001 — الجدار رفاهية دفاعية لا شرط بقاء
                _end_ts = None
        account_blown = False
        _liquidation_truncated = 0.0

        def _force_close_all(price: float, ts, reason: str) -> None:
            """✅ R58 — تصفية كاملة عند جدار النهاية أو إفلاس الحساب.

            تغلق المركز الأساسي وكل المراكز الإضافية عند «سعر» الشمعة الحالية
            (open أول شمعة بعد الجدار — نموذج تنفيذ واقعي)، تسجّل الصفقات
            ونقاط الخروج، ثم تثبّت الرصيد عند صفر إن سال (لا يمكن للحساب أن
            يخسر أكثر من رأس ماله — أرضية الواقع المالي).
            """
            nonlocal current_state, trade_id, entry_price, position_size
            nonlocal sl_price, tp_price, trail_peak, account_balance
            nonlocal cumulative_pnl, account_blown, _liquidation_truncated
            if current_state != 'NEUTRAL' and trade_id:
                _pnl_fc = ((price - entry_price) * position_size
                           if current_state == 'LONG'
                           else (entry_price - price) * position_size)
                _inv_fc = entry_price * position_size
                _pct_fc = (_pnl_fc / _inv_fc) * 100 if _inv_fc else 0.0
                _net_fc = self._close_trade_logic(
                    trades, trade_id, price, ts, reason, _pnl_fc, _pct_fc, config,
                )
                account_balance += _net_fc
                cumulative_pnl += _net_fc
                equity_curve.append(account_balance)
                trade_points.append({
                    "timestamp": ts,
                    "type": "exit",
                    "trade_id": trade_id,
                    "price": float(price),
                    "exit_price": float(price),
                    "exit_reason": reason,
                    "pnl": float(_net_fc),
                    "pnl_percentage": float(_pct_fc),
                    "entry_price": float(entry_price),
                    "position_size": float(position_size),
                    "position_type": current_state.lower(),
                    "commission": 0.0,
                    "fill_entry": fill_model_str,
                    "fill_exit": fill_model_str,
                    "direction": current_state.lower(),
                    "symbol": symbol,
                })
                current_state = 'NEUTRAL'
                trade_id = None
                entry_price = 0.0
                position_size = 0.0
                sl_price = 0.0
                tp_price = 0.0
                trail_peak = 0.0
            for _xp in list(extra_positions):
                _xs = _xp['position_size']
                if _xp['direction'] == 'LONG':
                    _xpnl = (price - _xp['entry_price']) * _xs
                else:
                    _xpnl = (_xp['entry_price'] - price) * _xs
                _xinv = _xp['entry_price'] * _xs
                _xpct = (_xpnl / _xinv) * 100 if _xinv else 0.0
                _xnet = self._close_trade_logic(
                    trades, _xp['trade_id'], price, ts, reason, _xpnl, _xpct, config,
                )
                account_balance += _xnet
                cumulative_pnl += _xnet
                equity_curve.append(account_balance)
                trade_points.append({
                    "timestamp": ts,
                    "type": "exit",
                    "trade_id": _xp['trade_id'],
                    "price": float(price),
                    "exit_price": float(price),
                    "exit_reason": reason,
                    "pnl": float(_xnet),
                    "pnl_percentage": float(_xpct),
                    "entry_price": float(_xp['entry_price']),
                    "position_size": float(_xs),
                    "position_type": _xp['direction'].lower(),
                    "stop_loss": float(_xp['sl_price']) if _xp['sl_price'] else None,
                    "take_profit": float(_xp['tp_price']) if _xp['tp_price'] else None,
                    "commission": 0.0,
                    "fill_entry": fill_model_str,
                    "fill_exit": fill_model_str,
                    "direction": _xp['direction'].lower(),
                    "symbol": symbol,
                    "position_kind": "additional",
                })
                extra_positions.remove(_xp)
            if account_balance < 0:
                # ✅ R58 — أرضية الواقع: التصفية لا تدع الرصيد سالباً أبداً
                _liquidation_truncated = -account_balance
                account_balance = 0.0
                equity_curve.append(0.0)
            if reason.startswith("Liquidation"):
                account_blown = True

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

            # ✅ R58 — حاجز الإفلاس (Liquidation): رصيد ≤ 0 يعني انتهاء الحساب.
            # بلاغ #10000042: المحرك استمر يتداول برصيد سالب ففتح مراكز بأحجام
            # سالبة (-354 و-1,247…) فانعكست إشارة الربح: تيك بروفت خاسر$ وستوب
            # رابح$. الآن: نصفي كل ما هو مفتوح عند open هذه الشمعة ونقف.
            if account_balance <= 0:
                if current_state != 'NEUTRAL' or extra_positions:
                    _force_close_all(open_price, current_time, "Liquidation (Account Blown)")
                account_blown = True
                break

            # ✅ R58 — جدار نهاية النافذة داخل المحرك (خط الدفاع الثاني):
            # بلاغ #10000042: نافذة 2023-10-14 → 2025-02-02 نُفّذت حتى «الآن»
            # (دخول 17 صفقة بعد النهاية وخروج End of Data عند نهاية البيانات).
            # حتى لو تسربت شموع أبعد من end_date عبر أي مسار بيانات، لا تُتاجر
            # بعد النهاية — الإغلاق عند إغلاق آخر شمعة داخل النافذة
            # (إغلاق الشمعة التي تسبق الجدار يقع عند النهاية نفسها بالضبط).
            if _end_ts is not None and current_time_sec > _end_ts:
                if i > 0:
                    _force_close_all(float(close_prices[i - 1]), data.index[i - 1], "End of Data")
                else:
                    _force_close_all(open_price, current_time, "End of Data")
                break

            # متغيرات مؤقتة لهذه الشمعة
            entering_trade = False
            exiting_trade = False
            exit_price = None
            exit_reason = None
            pnl = 0.0
            pnl_gross = 0.0
            pnl_percentage = 0.0
            balance_before_exit = account_balance 
            # ✅ R55 — أحداث المراكز الإضافية في هذه الشمعة (دخول/خروج)
            extra_entries_bar: List[Dict[str, Any]] = []
            extra_exits_bar: List[Dict[str, Any]] = []

            # ✅ الجولة 12: بيانات الصفقة المغلقة محفوظة قبل التصفير — كانت
            # entry_price/position_size تعود 0.0 في نقاط الخروج (bug قديم)
            closed_entry_price = 0.0
            closed_entry_time = None
            closed_sl = 0.0
            closed_tp = 0.0
            closed_size = 0.0

            
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
            # ✅ R55 — أرباح المراكز الإضافية غير المتحققة (مستقلة لكل مركز)
            for _xp in extra_positions:
                if _xp['entry_price'] > 0 and _xp['position_size'] > 0:
                    if _xp['direction'] == 'LONG':
                        unrealized_pnl += (close_price - _xp['entry_price']) * _xp['position_size']
                    else:
                        unrealized_pnl += (_xp['entry_price'] - close_price) * _xp['position_size']
            
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
                pnl_gross = pnl_close
                exit_price = execution_price
                exit_reason = (
                    f"Exit Signal: {executed_decision.reason}"
                    if exit_signal_triggered
                    else f"Signal Reversal: {target_state}"
                )
                
                # حفظ البيانات قبل المسح
                closed_trade_id = trade_id
                closed_position_type = current_state
                # ✅ الجولة 12: حفظ بيانات الصفقة قبل التصفير (لنقاط الخروج الشفافة)
                closed_entry_price = entry_price
                closed_entry_time = entry_time
                closed_sl = sl_price
                closed_tp = tp_price
                closed_size = position_size
                
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
                trail_peak = 0.0  # ✅ R55

                # ✅ R55 — إشارة خروج/انعكاس تغلق كل المراكز الإضافية أيضاً
                # (كل التعرض لاتجاه الاستراتيجية يُقفل عند خروجها)
                _x_reason_root = f"{exit_reason} (additional position)"
                for _xp in list(extra_positions):
                    _x_size = _xp['position_size']
                    if _xp['direction'] == 'LONG':
                        _x_pnl = (execution_price - _xp['entry_price']) * _x_size
                    else:
                        _x_pnl = (_xp['entry_price'] - execution_price) * _x_size
                    _x_inv = _xp['entry_price'] * _x_size
                    _x_pct = (_x_pnl / _x_inv) * 100 if _x_inv else 0
                    _net_x = self._close_trade_logic(
                        trades, _xp['trade_id'], execution_price, current_time,
                        _x_reason_root, _x_pnl, _x_pct, config,
                    )
                    account_balance += _net_x
                    cumulative_pnl += _net_x
                    equity_curve.append(account_balance)
                    extra_exits_bar.append({
                        "timestamp": current_time,
                        "type": "exit",
                        "trade_id": _xp['trade_id'],
                        "price": float(execution_price),
                        "exit_price": float(execution_price),
                        "exit_reason": _x_reason_root,
                        "pnl": float(_net_x),
                        "pnl_percentage": float(_x_pct),
                        "entry_price": float(_xp['entry_price']),
                        "position_size": float(_x_size),
                        "position_type": _xp['direction'].lower(),
                        "stop_loss": float(_xp['sl_price']) if _xp['sl_price'] else None,
                        "take_profit": float(_xp['tp_price']) if _xp['tp_price'] else None,
                        "commission": 0.0,
                        "fill_entry": fill_model_str,
                        "fill_exit": fill_model_str,
                        "direction": _xp['direction'].lower(),
                        "symbol": symbol,
                        "position_kind": "additional",
                    })
                    extra_positions.remove(_xp)

            # فتح مركز جديد (✅ R58: لا دخول برصيد ≤ 0 — الحساب المفلس لا يتداول)
            if target_state != 'NEUTRAL' and current_state == 'NEUTRAL' and account_balance > 0:
                entry_price = open_price
                entry_time = current_time
                
                # ✅ R58 — دلالة موحّدة: percentage=1 ⇒ 1% فعلاً (كانت تُفهم 100%)
                risk_amount = account_balance * _risk_frac
                position_size = risk_amount / entry_price 
                
                if sl_active and sl_frac is not None:
                    sl_offset = entry_price * sl_frac
                    if target_state == 'LONG':
                        sl_price = entry_price - sl_offset
                    else:
                        sl_price = entry_price + sl_offset
                
                if tp_active and tp_frac is not None:
                    tp_offset = entry_price * tp_frac
                    if target_state == 'LONG':
                        tp_price = entry_price + tp_offset
                    else:
                        tp_price = entry_price - tp_offset

                # ✅ R55 — قمة التريلينق تبدأ من سعر تنفيذ الدخول
                trail_peak = entry_price

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
                
                # ✅ الجولة 13 — إبادة العمولة: لا يوجد أي حساب عمولة/انزلاق في المحرك
                # (الكود المحذوف لا يعود) — commission/slippage حقلا استجابة ثابتان 0.0 للتوافق القرائي.
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
                    commission=0.0,
                    slippage=0.0,
                    stop_loss=sl_price if sl_active else None,
                    take_profit=tp_price if tp_active else None,
                    exit_reason=None,
                    # ✅ الجولة 12: الشفافية — نموذج التنفيذ الفعلي + الاتجاه
                    direction='long' if target_state == 'LONG' else 'short',
                    fill_entry=fill_model_str,
                    fill_exit=fill_model_str,
                    metadata={
                        'strategy': config.strategy_config.get('name', 'Unknown'),
                        'decision_reason': executed_decision.reason if executed_decision else None,
                        'confidence': executed_decision.confidence if executed_decision else None,
                        'risk_reward_ratio': risk_reward_ratio
                    }
                )
                trades.append(trade)

                # ✅ R55 — تتبع أقصى تزامن (المركز الأساسي)
                _open_now = 1 + len(extra_positions)
                if _open_now > max_open_observed:
                    max_open_observed = _open_now

            # ✅ R55 — مركز إضافي مستقل (max_positions من الجذر): إشارة جديدة
            # بنفس الاتجاه والمراكز المفتوحة < N ⇒ مركز مستقل بإدارة مخاطر
            # كاملة (SL/TP/تريلينق خاصة به). بلغ N ⇒ التجاهل (لا فتح).
            # الشرط `not entering_trade` يضمن أن إشارة واحدة لا تفتح مركزين
            # في نفس الشمعة — الأساس يُفتح أولاً والإضافي في إشارة لاحقة.
            if (
                max_concurrent > 1
                and not entering_trade
                and target_state != 'NEUTRAL'
                and current_state == target_state
                and (1 + len(extra_positions)) < max_concurrent
                and account_balance > 0  # ✅ R58 — لا مراكز إضافية بحساب مفلس
            ):
                _x_entry = open_price
                _x_time = current_time
                _x_risk = account_balance * _risk_frac  # ✅ R58 — دلالة موحّدة
                _x_size = _x_risk / _x_entry if _x_entry else 0.0
                _x_sl = 0.0
                _x_tp = 0.0
                if sl_active and sl_frac is not None:
                    _x_off = _x_entry * sl_frac
                    _x_sl = _x_entry - _x_off if target_state == 'LONG' else _x_entry + _x_off
                if tp_active and tp_frac is not None:
                    _x_off = _x_entry * tp_frac
                    _x_tp = _x_entry + _x_off if target_state == 'LONG' else _x_entry - _x_off
                _x_id = str(uuid.uuid4())
                _x_trade = Trade(
                    id=_x_id,
                    symbol=symbol,
                    entry_time=_x_time,
                    exit_time=None,
                    entry_price=_x_entry,
                    exit_price=None,
                    position_type='long' if target_state == 'LONG' else 'short',
                    position_size=_x_size,
                    pnl=None,
                    pnl_percentage=None,
                    commission=0.0,
                    slippage=0.0,
                    stop_loss=_x_sl if sl_active else None,
                    take_profit=_x_tp if tp_active else None,
                    exit_reason=None,
                    direction='long' if target_state == 'LONG' else 'short',
                    fill_entry=fill_model_str,
                    fill_exit=fill_model_str,
                    metadata={
                        'strategy': config.strategy_config.get('name', 'Unknown') if config.strategy_config else 'Unknown',
                        'decision_reason': executed_decision.reason if executed_decision else None,
                        'confidence': executed_decision.confidence if executed_decision else None,
                        'position_kind': 'additional',
                        'risk_reward_ratio': 0.0,
                    },
                )
                trades.append(_x_trade)
                extra_positions.append({
                    'trade_id': _x_id,
                    'trade': _x_trade,
                    'direction': target_state,
                    'entry_price': _x_entry,
                    'entry_time': _x_time,
                    'position_size': _x_size,
                    'sl_price': _x_sl,
                    'tp_price': _x_tp,
                    'trail_peak': _x_entry,  # قمة التريلينق تبدأ من سعر الدخول
                })
                _open_now = (1 if current_state != 'NEUTRAL' else 0) + len(extra_positions)
                if _open_now > max_open_observed:
                    max_open_observed = _open_now
                extra_entries_bar.append({
                    "timestamp": current_time,
                    "type": "entry",
                    "trade_id": _x_id,
                    "price": float(_x_entry),
                    "position_type": target_state.lower(),
                    "position_size": float(_x_size),
                    "entry_price": float(_x_entry),
                    "stop_loss": float(_x_sl) if (sl_active and _x_sl) else None,
                    "take_profit": float(_x_tp) if (tp_active and _x_tp) else None,
                    "decision_reason": executed_decision.reason if executed_decision else None,
                    "confidence": executed_decision.confidence if executed_decision else None,
                    "account_balance_before": account_balance,
                    "commission": 0.0,
                    "fill_entry": fill_model_str,
                    "direction": target_state.lower(),
                    "symbol": symbol,
                    "position_kind": "additional",
                })

            # ==========================================================
            # المرحلة 2: إدارة المخاطر (SL/TP) - داخل الشمعة
            # ==========================================================
            
            if current_state != 'NEUTRAL':
                stop_hit = False
                take_profit_hit = False
                trail_hit = False  # ✅ R55 — خروج التريلينق من الجذر
                
                # ✅ R55 — التريلينق من الجذر (يلغي SL/TP عند تفعيله — نفس
                # دلالات محرك الخروج الموحد): القمة تبدأ من سعر الدخول، كل
                # قمة شمعة أعلى ترفع السقف (لا ينخفض أبداً)، وهبوط إغلاق
                # الشمعة بنسبة التريلينق من أعلى قمة يغلق المركز كاملاً
                # عند سعر ذلك الإغلاق (reason = "Trailing Stop").
                if trail_active and trail_frac is not None:
                    if current_state == 'LONG':
                        if high_price > trail_peak:
                            trail_peak = high_price
                        if close_price <= trail_peak * (1.0 - trail_frac):
                            exit_price = close_price
                            exit_reason = "Trailing Stop"
                            trail_hit = True
                    elif current_state == 'SHORT':
                        if low_price < trail_peak:
                            trail_peak = low_price
                        if close_price >= trail_peak * (1.0 + trail_frac):
                            exit_price = close_price
                            exit_reason = "Trailing Stop"
                            trail_hit = True
                
                if not trail_hit and current_state == 'LONG':
                    if sl_active and low_price <= sl_price:
                        exit_price = sl_price
                        exit_reason = "Stop Loss Hit"
                        stop_hit = True
                    elif tp_active and high_price >= tp_price:
                        exit_price = tp_price
                        exit_reason = "Take Profit Hit"
                        take_profit_hit = True
                elif not trail_hit and current_state == 'SHORT':
                    if sl_active and high_price >= sl_price:
                        exit_price = sl_price
                        exit_reason = "Stop Loss Hit"
                        stop_hit = True
                    elif tp_active and low_price <= tp_price:
                        exit_price = tp_price
                        exit_reason = "Take Profit Hit"
                        take_profit_hit = True
                
                if stop_hit or take_profit_hit or trail_hit:
                    if current_state == 'LONG':
                        pnl = (exit_price - entry_price) * position_size
                    else:
                        pnl = (entry_price - exit_price) * position_size
                    
                    initial_investment = entry_price * position_size
                    pnl_percentage = (pnl / initial_investment) * 100 if initial_investment != 0 else 0
                    
                    exiting_trade = True
                    pnl_gross = pnl
                    balance_before_exit = account_balance
                    
                    # ✅ حفظ البيانات قبل إعادة التعيين (مهم جداً للمرحلة 4)
                    closed_trade_id = trade_id
                    closed_position_type = current_state
                    # ✅ الجولة 12: حفظ بيانات الصفقة قبل التصفير (لنقاط الخروج الشفافة)
                    closed_entry_price = entry_price
                    closed_entry_time = entry_time
                    closed_sl = sl_price
                    closed_tp = tp_price
                    closed_size = position_size
                    
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
                    trail_peak = 0.0  # ✅ R55
                    
                    # ✅ تمت إزالة 'continue' للسماح بتسجيل البيانات البصرية للشمعة الحالية
                    # إذا أردت منع فتح صفقة جديدة في نفس الشمعة بعد إغلاق، يمكن إضافة flag هنا.
                    pending_decision = None

            # ✅ R55 — إدارة مخاطر المراكز الإضافية (مستقلة لكل مركز):
            # كل مركز إضافي يُدار بسل/تيبي/تريلينق خاصة به — خروج أحدها لا
            # يمس الآخرين ولا المركز الأساسي (استقلال كامل كما طلب المستخدم).
            for _xp in list(extra_positions):
                _x_exit = None
                _x_reason = None
                if _xp['direction'] == 'LONG':
                    if trail_active and trail_frac is not None:
                        if high_price > _xp['trail_peak']:
                            _xp['trail_peak'] = high_price
                        if close_price <= _xp['trail_peak'] * (1.0 - trail_frac):
                            _x_exit = close_price
                            _x_reason = "Trailing Stop (additional position)"
                    if _x_exit is None and sl_active and low_price <= _xp['sl_price']:
                        _x_exit = _xp['sl_price']
                        _x_reason = "Stop Loss Hit (additional position)"
                    if _x_exit is None and tp_active and high_price >= _xp['tp_price']:
                        _x_exit = _xp['tp_price']
                        _x_reason = "Take Profit Hit (additional position)"
                else:  # SHORT
                    if trail_active and trail_frac is not None:
                        if low_price < _xp['trail_peak']:
                            _xp['trail_peak'] = low_price
                        if close_price >= _xp['trail_peak'] * (1.0 + trail_frac):
                            _x_exit = close_price
                            _x_reason = "Trailing Stop (additional position)"
                    if _x_exit is None and sl_active and high_price >= _xp['sl_price']:
                        _x_exit = _xp['sl_price']
                        _x_reason = "Stop Loss Hit (additional position)"
                    if _x_exit is None and tp_active and low_price <= _xp['tp_price']:
                        _x_exit = _xp['tp_price']
                        _x_reason = "Take Profit Hit (additional position)"

                if _x_exit is not None:
                    _x_size = _xp['position_size']
                    if _xp['direction'] == 'LONG':
                        _x_pnl = (_x_exit - _xp['entry_price']) * _x_size
                    else:
                        _x_pnl = (_xp['entry_price'] - _x_exit) * _x_size
                    _x_inv = _xp['entry_price'] * _x_size
                    _x_pct = (_x_pnl / _x_inv) * 100 if _x_inv else 0
                    _net_x = self._close_trade_logic(
                        trades, _xp['trade_id'], _x_exit, current_time,
                        _x_reason, _x_pnl, _x_pct, config,
                    )
                    account_balance += _net_x
                    cumulative_pnl += _net_x
                    equity_curve.append(account_balance)
                    extra_exits_bar.append({
                        "timestamp": current_time,
                        "type": "exit",
                        "trade_id": _xp['trade_id'],
                        "price": float(_x_exit),
                        "exit_price": float(_x_exit),
                        "exit_reason": _x_reason,
                        "pnl": float(_net_x),
                        "pnl_percentage": float(_x_pct),
                        "entry_price": float(_xp['entry_price']),
                        "position_size": float(_x_size),
                        "position_type": _xp['direction'].lower(),
                        "stop_loss": float(_xp['sl_price']) if _xp['sl_price'] else None,
                        "take_profit": float(_xp['tp_price']) if _xp['tp_price'] else None,
                        "commission": 0.0,
                        "fill_entry": fill_model_str,
                        "fill_exit": fill_model_str,
                        "direction": _xp['direction'].lower(),
                        "symbol": symbol,
                        "position_kind": "additional",
                    })
                    extra_positions.remove(_xp)

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
            # ✅ الجولة 12: نموذج التنفيذ signal_close — تنفيذ فوري عند إغلاق
            # شمعة الإشارة (لمطابقة محاكاة الواجهة المحلية). next_open يبقى
            # الافتراضي حرفياً بلا أي تغيير — هذه الكتلة لا تعمل إلا عند
            # fill_model="signal_close".
            # ==========================================================
            if config.fill_model == "signal_close" and pending_decision is not None:
                decision_sc = pending_decision
                act_sc = decision_sc.action
                target_state_sc = 'NEUTRAL'
                if act_sc == DecisionAction.BUY:
                    target_state_sc = 'LONG'
                elif act_sc == DecisionAction.SELL:
                    target_state_sc = 'SHORT' if config.enable_short_selling else 'NEUTRAL'

                exit_trig_sc = (
                    current_state != 'NEUTRAL'
                    and (
                        target_state_sc != current_state
                        or (
                            act_sc == DecisionAction.HOLD
                            and isinstance(getattr(decision_sc, "metadata", None), dict)
                            and decision_sc.metadata.get("trigger") == "exit_rule"
                        )
                    )
                )

                fill_price_sc = close_price

                if exit_trig_sc:
                    execution_price_sc = fill_price_sc
                    initial_investment_sc = entry_price * position_size
                    pnl_close_sc = (
                        (execution_price_sc - entry_price) * position_size
                        if current_state == 'LONG'
                        else (entry_price - execution_price_sc) * position_size
                    )
                    pnl_percentage_sc = (pnl_close_sc / initial_investment_sc) * 100 if initial_investment_sc != 0 else 0

                    exiting_trade = True
                    pnl = pnl_close_sc
                    pnl_gross = pnl_close_sc
                    exit_price = execution_price_sc
                    exit_reason = (
                        f"Exit Signal: {decision_sc.reason}"
                        if (act_sc == DecisionAction.HOLD or target_state_sc == 'NEUTRAL')
                        else f"Signal Reversal: {target_state_sc}"
                    )

                    closed_trade_id = trade_id
                    closed_position_type = current_state
                    closed_entry_price = entry_price
                    closed_entry_time = entry_time
                    closed_sl = sl_price
                    closed_tp = tp_price
                    closed_size = position_size
                    balance_before_exit = account_balance

                    net_pnl_closed_sc = self._close_trade_logic(
                        trades, trade_id, execution_price_sc, current_time, exit_reason,
                        pnl_close_sc, pnl_percentage_sc, config,
                    )
                    account_balance += net_pnl_closed_sc
                    cumulative_pnl += net_pnl_closed_sc
                    pnl = net_pnl_closed_sc
                    pnl_percentage = (net_pnl_closed_sc / initial_investment_sc) * 100 if initial_investment_sc != 0 else 0
                    equity_curve.append(account_balance)

                    current_state = 'NEUTRAL'
                    trade_id = None
                    entry_price = 0.0
                    position_size = 0.0
                    sl_price = 0.0
                    tp_price = 0.0
                    trail_peak = 0.0  # ✅ R55

                    # ✅ R55 — إشارة خروج/انعكاس تغلق كل المراكز الإضافية أيضاً (مسار signal_close)
                    _x_reason_root = f"{exit_reason} (additional position)"
                    for _xp in list(extra_positions):
                        _x_size = _xp['position_size']
                        if _xp['direction'] == 'LONG':
                            _x_pnl = (execution_price_sc - _xp['entry_price']) * _x_size
                        else:
                            _x_pnl = (_xp['entry_price'] - execution_price_sc) * _x_size
                        _x_inv = _xp['entry_price'] * _x_size
                        _x_pct = (_x_pnl / _x_inv) * 100 if _x_inv else 0
                        _net_x = self._close_trade_logic(
                            trades, _xp['trade_id'], execution_price_sc, current_time,
                            _x_reason_root, _x_pnl, _x_pct, config,
                        )
                        account_balance += _net_x
                        cumulative_pnl += _net_x
                        equity_curve.append(account_balance)
                        extra_exits_bar.append({
                            "timestamp": current_time,
                            "type": "exit",
                            "trade_id": _xp['trade_id'],
                            "price": float(execution_price_sc),
                            "exit_price": float(execution_price_sc),
                            "exit_reason": _x_reason_root,
                            "pnl": float(_net_x),
                            "pnl_percentage": float(_x_pct),
                            "entry_price": float(_xp['entry_price']),
                            "position_size": float(_x_size),
                            "position_type": _xp['direction'].lower(),
                            "stop_loss": float(_xp['sl_price']) if _xp['sl_price'] else None,
                            "take_profit": float(_xp['tp_price']) if _xp['tp_price'] else None,
                            "commission": 0.0,
                            "fill_entry": fill_model_str,
                            "fill_exit": fill_model_str,
                            "direction": _xp['direction'].lower(),
                            "symbol": symbol,
                            "position_kind": "additional",
                        })
                        extra_positions.remove(_xp)

                if target_state_sc != 'NEUTRAL' and current_state == 'NEUTRAL' and account_balance > 0:  # ✅ R58
                    entry_price = fill_price_sc
                    entry_time = current_time

                    risk_amount_sc = account_balance * _risk_frac  # ✅ R58 — دلالة موحّدة
                    position_size = risk_amount_sc / entry_price if entry_price else 0.0

                    if sl_active and sl_frac is not None:
                        sl_offset_sc = entry_price * sl_frac
                        sl_price = entry_price - sl_offset_sc if target_state_sc == 'LONG' else entry_price + sl_offset_sc

                    if tp_active and tp_frac is not None:
                        tp_offset_sc = entry_price * tp_frac
                        tp_price = entry_price + tp_offset_sc if target_state_sc == 'LONG' else entry_price - tp_offset_sc

                    # ✅ R55 — قمة التريلينق تبدأ من سعر تنفيذ الدخول
                    trail_peak = entry_price

                    current_state = target_state_sc
                    trade_id = str(uuid.uuid4())
                    entering_trade = True

                    risk_reward_ratio_sc = 0.0
                    if sl_price > 0 and tp_price > 0:
                        if target_state_sc == 'LONG':
                            risk_sc = entry_price - sl_price
                            reward_sc = tp_price - entry_price
                        else:
                            risk_sc = sl_price - entry_price
                            reward_sc = entry_price - tp_price
                        risk_reward_ratio_sc = reward_sc / risk_sc if risk_sc != 0 else 0

                    # ✅ الجولة 13 — إبادة العمولة: بلا أي حساب عمولة
                    trade_sc = Trade(
                        id=trade_id,
                        symbol=symbol,
                        entry_time=entry_time,
                        exit_time=None,
                        entry_price=entry_price,
                        exit_price=None,
                        position_type='long' if target_state_sc == 'LONG' else 'short',
                        position_size=position_size,
                        pnl=None,
                        pnl_percentage=None,
                        commission=0.0,
                        slippage=0.0,
                        stop_loss=sl_price if sl_active else None,
                        take_profit=tp_price if tp_active else None,
                        exit_reason=None,
                        direction='long' if target_state_sc == 'LONG' else 'short',
                        fill_entry=fill_model_str,
                        fill_exit=fill_model_str,
                        metadata={
                            'strategy': config.strategy_config.get('name', 'Unknown') if config.strategy_config else 'Unknown',
                            'decision_reason': decision_sc.reason,
                            'confidence': decision_sc.confidence,
                            'risk_reward_ratio': risk_reward_ratio_sc,
                        },
                    )
                    trades.append(trade_sc)

                    # ✅ R55 — تتبع أقصى تزامن (المركز الأساسي — مسار signal_close)
                    _open_now = 1 + len(extra_positions)
                    if _open_now > max_open_observed:
                        max_open_observed = _open_now

                # ✅ R55 — مركز إضافي مستقل (مسار signal_close): إشارة جديدة
                # بنفس الاتجاه والسعة متاحة ⇒ مركز مستقل بإدارة كاملة.
                if (
                    max_concurrent > 1
                    and not entering_trade
                    and target_state_sc != 'NEUTRAL'
                    and current_state == target_state_sc
                    and (1 + len(extra_positions)) < max_concurrent
                    and account_balance > 0  # ✅ R58 — لا مراكز إضافية بحساب مفلس
                ):
                    _x_entry = fill_price_sc
                    _x_time = current_time
                    _x_risk = account_balance * _risk_frac  # ✅ R58 — دلالة موحّدة
                    _x_size = _x_risk / _x_entry if _x_entry else 0.0
                    _x_sl = 0.0
                    _x_tp = 0.0
                    if sl_active and sl_frac is not None:
                        _x_off = _x_entry * sl_frac
                        _x_sl = _x_entry - _x_off if target_state_sc == 'LONG' else _x_entry + _x_off
                    if tp_active and tp_frac is not None:
                        _x_off = _x_entry * tp_frac
                        _x_tp = _x_entry + _x_off if target_state_sc == 'LONG' else _x_entry - _x_off
                    _x_id = str(uuid.uuid4())
                    _x_trade = Trade(
                        id=_x_id,
                        symbol=symbol,
                        entry_time=_x_time,
                        exit_time=None,
                        entry_price=_x_entry,
                        exit_price=None,
                        position_type='long' if target_state_sc == 'LONG' else 'short',
                        position_size=_x_size,
                        pnl=None,
                        pnl_percentage=None,
                        commission=0.0,
                        slippage=0.0,
                        stop_loss=_x_sl if sl_active else None,
                        take_profit=_x_tp if tp_active else None,
                        exit_reason=None,
                        direction='long' if target_state_sc == 'LONG' else 'short',
                        fill_entry=fill_model_str,
                        fill_exit=fill_model_str,
                        metadata={
                            'strategy': config.strategy_config.get('name', 'Unknown') if config.strategy_config else 'Unknown',
                            'decision_reason': decision_sc.reason,
                            'confidence': decision_sc.confidence,
                            'position_kind': 'additional',
                            'risk_reward_ratio': 0.0,
                        },
                    )
                    trades.append(_x_trade)
                    extra_positions.append({
                        'trade_id': _x_id,
                        'trade': _x_trade,
                        'direction': target_state_sc,
                        'entry_price': _x_entry,
                        'entry_time': _x_time,
                        'position_size': _x_size,
                        'sl_price': _x_sl,
                        'tp_price': _x_tp,
                        'trail_peak': _x_entry,
                    })
                    _open_now = (1 if current_state != 'NEUTRAL' else 0) + len(extra_positions)
                    if _open_now > max_open_observed:
                        max_open_observed = _open_now
                    extra_entries_bar.append({
                        "timestamp": current_time,
                        "type": "entry",
                        "trade_id": _x_id,
                        "price": float(_x_entry),
                        "position_type": target_state_sc.lower(),
                        "position_size": float(_x_size),
                        "entry_price": float(_x_entry),
                        "stop_loss": float(_x_sl) if (sl_active and _x_sl) else None,
                        "take_profit": float(_x_tp) if (tp_active and _x_tp) else None,
                        "decision_reason": decision_sc.reason,
                        "confidence": decision_sc.confidence,
                        "account_balance_before": account_balance,
                        "commission": 0.0,
                        "fill_entry": fill_model_str,
                        "direction": target_state_sc.lower(),
                        "symbol": symbol,
                        "position_kind": "additional",
                    })

                pending_decision = None



            # ==========================================================
            # المرحلة 4: البيانات البصرية (Visuals) — تُبنى لعينات فقط على البيانات الضخمة
            # ==========================================================
            create_visual = (
                visual_step == 1
                or (i % visual_step == 0)
                or entering_trade or exiting_trade
                or extra_entries_bar or extra_exits_bar  # ✅ R55 — شموع أحداث المراكز الإضافية دائماً مرئية
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

                                # ✅ الجولة 12.1 (إصلاح 0-أ الجذري): أعمدة العقد ind_* تُكتب دائماً —
                                # كانت pd.notna(val) تُسقط القيم NaN فتتفكك أعمدة العقد
                                # (ind_zz_*/ind_fib_*/ind_atl_*/ind_zzf_*) من شموع فترة التمهيد
                                # ويصبح مفتاح كل شمعة مختلفاً عن الأخرى (أعمدة تتلوى وتختفي).
                                # الآن: قيمة NaN/None في أعمدة العقد → null في JSON (ليست مفقودة)
                                # فتبقى مجموعة مفاتيح كل شمعة ثابتة وكاملة — العقد المُلزم.
                                _is_contract_col = str(col).startswith("ind_")
                                if val is None or (isinstance(val, float) and pd.isna(val)):
                                    if _is_contract_col:
                                        indicators[col] = None
                                    continue
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
                                elif _is_contract_col:
                                    # قيمة غير عددية NaN لأي نوع آخر في عمود عقد → null
                                    indicators[col] = None


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
                # ✅ R55 — هامش المراكز الإضافية
                for _xp in extra_positions:
                    margin_used += (_xp['position_size'] * close_price) / leverage_used
            
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
                    # ✅ الجولة 12 (بند 5-ب.3): وسم كل شمعة برمزها
                    symbol=symbol,
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
                        # ✅ الجولة 13 (Zero-Fee): DEPRECATED — ثابت 0.0 دائماً
                        "commission": 0.0,
                        # ✅ الجولة 12: الشفافية
                        "fill_entry": fill_model_str,
                        "direction": current_state.lower(),
                        # ✅ الجولة 12 (بند 5-ب.3): رمز النقطة
                        "symbol": symbol,
                    })
            
                # تسجيل صفقات الإغلاق (مع استخدام المتغيرات المحفوظة)
                if exiting_trade:
                    # استخدام المتغيرات المحفوظة إذا كنا أغلقنا الصفقة في هذه الدورة
                    # وإلا استخدام القيم الحالية (لإغلاق نهاية البيانات)
                    record_trade_id = closed_trade_id if closed_trade_id else trade_id
                    record_position_type = closed_position_type if closed_position_type else current_state
                    # ✅ الجولة 12: بيانات الصفقة المغلقة (كانت تعود 0.0 بعد التصفير)
                    rec_entry_price = closed_entry_price if closed_trade_id else entry_price
                    rec_entry_time = closed_entry_time if closed_trade_id else entry_time
                    rec_sl = closed_sl if closed_trade_id else sl_price
                    rec_tp = closed_tp if closed_trade_id else tp_price
                    rec_size = closed_size if closed_trade_id else position_size
                    rec_direction = str(record_position_type).lower()

                    _delta = float(exit_price) - float(rec_entry_price) if rec_entry_price else 0.0
                    _delta_pct = (_delta / float(rec_entry_price) * 100.0) if rec_entry_price else 0.0
                    _sign_dir = 1.0 if rec_direction == 'long' else -1.0
                    # ✅ الجولة 13 (عقد الدقة — الصيغة الموحدة):
                    #   price_delta_pct = (exit − entry) / entry × 100 × direction
                    #   result_pct      = price_delta_pct (نفس القيمة بلا اختلاف)
                    _delta_pct_signed = _delta_pct * _sign_dir

                    visual_candle.trade_action = f"EXIT_{record_position_type.upper()}"
                    visual_candle.trade_id = record_trade_id
                    visual_candle.trade_price = float(exit_price)
                    visual_candle.pnl = float(pnl)
                    visual_candle.pnl_percentage = float(pnl_percentage)
                
                    trade_points.append({
                        "timestamp": current_time,
                        "type": "exit",
                        "trade_id": record_trade_id,
                        "price": float(exit_price),
                        "exit_price": float(exit_price),
                        "exit_reason": exit_reason,
                        "pnl": float(pnl),
                        "pnl_percentage": float(pnl_percentage),
                        "entry_price": float(rec_entry_price),
                        "position_size": float(rec_size),
                        "position_type": rec_direction,
                        "holding_period": (current_time - rec_entry_time).total_seconds() / 3600 if rec_entry_time else 0,
                        "account_balance_before": float(balance_before_exit),
                        "account_balance_after": account_balance,
                        "cumulative_pnl": cumulative_pnl,
                        # ✅ الجولة 13 (Zero-Fee): DEPRECATED — ثابت 0.0 دائماً
                        "commission": 0.0,
                        "stop_loss": float(rec_sl),
                        "take_profit": float(rec_tp),
                        # ✅ الجولة 12: الشفافية الحسابية الكاملة
                        # ✅ الجولة 13 (عقد الدقة): price_delta_pct موقّعة بالاتجاه وresult_pct = نفسها
                        "price_delta": _delta,
                        "price_delta_pct": _delta_pct_signed,
                        "direction": rec_direction,
                        "result_pct": _delta_pct_signed,
                        "pnl_gross": float(pnl_gross),
                        "fill_entry": fill_model_str,
                        "fill_exit": fill_model_str,
                        # ✅ الجولة 12 (بند 5-ب.3): رمز النقطة
                        "symbol": symbol,
                    })
            
                # ✅ R55 — نقاط دخول/خروج المراكز الإضافية لهذه الشمعة
                # (نفس عقد النقاط + مفتا sl/tp + وسم position_kind)
                for _xe in extra_entries_bar:
                    trade_points.append(_xe)
                for _xx in extra_exits_bar:
                    trade_points.append(_xx)
                
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
            pnl_gross = pnl
            
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
                _delta_eod = float(exit_price) - float(entry_price) if entry_price else 0.0
                _delta_pct_eod = (_delta_eod / float(entry_price) * 100.0) if entry_price else 0.0
                _sign_eod = 1.0 if current_state.lower() == 'long' else -1.0
                # ✅ الجولة 13 (عقد الدقة): price_delta_pct موقّعة بالاتجاه وresult_pct = نفسها
                _delta_pct_eod_signed = _delta_pct_eod * _sign_eod
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
                    # ✅ الجولة 13 (Zero-Fee): DEPRECATED — ثابت 0.0 دائماً
                    "commission": 0.0,
                    "stop_loss": float(sl_price),
                    "take_profit": float(tp_price),
                    # ✅ الجولة 12: الشفافية الحسابية الكاملة
                    # ✅ الجولة 13 (عقد الدقة): price_delta_pct موقّعة بالاتجاه وresult_pct = نفسها
                    "price_delta": _delta_eod,
                    "price_delta_pct": _delta_pct_eod_signed,
                    "direction": current_state.lower(),
                    "result_pct": _delta_pct_eod_signed,
                    "pnl_gross": float(pnl_gross),
                    "fill_entry": fill_model_str,
                    "fill_exit": fill_model_str,
                    # ✅ الجولة 12 (بند 5-ب.3): رمز النقطة
                    "symbol": symbol,
                })

        # ✅ R55 — إغلاق المراكز الإضافية في نهاية البيانات (نفس سعر آخر إغلاق)
        if extra_positions:
            _eod_price = data['close'].iloc[-1]
            _eod_time = data.index[-1]
            for _xp in list(extra_positions):
                _x_size = _xp['position_size']
                if _xp['direction'] == 'LONG':
                    _x_pnl = (_eod_price - _xp['entry_price']) * _x_size
                else:
                    _x_pnl = (_xp['entry_price'] - _eod_price) * _x_size
                _x_inv = _xp['entry_price'] * _x_size
                _x_pct = (_x_pnl / _x_inv) * 100 if _x_inv else 0
                _net_x = self._close_trade_logic(
                    trades, _xp['trade_id'], _eod_price, _eod_time,
                    "End of Data", _x_pnl, _x_pct, config,
                )
                account_balance += _net_x
                cumulative_pnl += _net_x
                equity_curve.append(account_balance)
                trade_points.append({
                    "timestamp": _eod_time,
                    "type": "exit",
                    "trade_id": _xp['trade_id'],
                    "price": float(_eod_price),
                    "exit_price": float(_eod_price),
                    "exit_reason": "End of Data",
                    "pnl": float(_net_x),
                    "pnl_percentage": float(_x_pct),
                    "entry_price": float(_xp['entry_price']),
                    "position_size": float(_x_size),
                    "position_type": _xp['direction'].lower(),
                    "stop_loss": float(_xp['sl_price']) if _xp['sl_price'] else None,
                    "take_profit": float(_xp['tp_price']) if _xp['tp_price'] else None,
                    "commission": 0.0,
                    "fill_entry": fill_model_str,
                    "fill_exit": fill_model_str,
                    "direction": _xp['direction'].lower(),
                    "symbol": symbol,
                    "position_kind": "additional",
                })
                extra_positions.remove(_xp)

        # ✅ R58 — أرضية الواقع المالي (ختامية): إغلاق نهاية البيانات قد يترك
        # الرصيد سالباً حسابياً بعد خسائر متزامنة — لا يمكن للحساب أن يخسر أكثر
        # من رأس ماله: نثبّته عند صفر ونقطع منحنى الرصيد عند الصفر
        # (الخسارة القصوى الممكنة = -100% مهما كانت الأحجام أو التزامن).
        if account_balance < 0:
            account_blown = True
            _liquidation_truncated = -account_balance
            account_balance = 0.0
        if account_blown:
            equity_curve[:] = [max(0.0, float(v)) for v in equity_curve]

        return trades, equity_curve, visual_candles, trade_points


    def _build_risk_echo(self, config: BacktestConfig, trades: List[Trade]) -> Dict[str, Any]:
        """✅ R55 — صدى سياسة المخاطر المطبّقة فعلاً (نفس منطق المحاكاة حرفياً).

        يُبنى من الكونفيق النظيف: الحقول غير المُرسلة = null = معطّلة،
        SL=0/100 = تعطيل، التريلينق يُلغي SL/TP عند تفعيله، والسقف الرقمي
        max_positions يُطبَّق في المحركين. يُحقن في math_audit ليصل للفرونت
        والمكتبة — انتهى عصر الافتراضات المخفية (5/10/2 غصباً).
        """
        _sl = config.stop_loss_percent
        _tp = config.take_profit_percent
        _tr = config.trailing_stop_percent
        sl_active = _sl is not None and 0.0 < float(_sl) < 100.0
        tp_active = _tp is not None and float(_tp) > 0.0
        trail_active = _tr is not None and float(_tr) > 0.0
        if trail_active:
            sl_active = False
            tp_active = False
        # أقصى تزامن ملحوظ من فترات الصفقات المتداخلة (إن وُجدت)
        _max_open = 0
        try:
            _events = []
            for tr in trades:
                _events.append((tr.entry_time, 1))
                if tr.exit_time is not None:
                    _events.append((tr.exit_time, -1))
            _events.sort(key=lambda e: (e[0] is None, e[0]))
            _cur = 0
            for _, d in _events:
                _cur += d
                if _cur > _max_open:
                    _max_open = _cur
        except Exception:  # noqa: BLE001 — الإحصاء غير حرج
            _max_open = 0
        return {
            "stop_loss_percent": float(_sl) if _sl is not None else None,
            "stop_loss_active": bool(sl_active),
            "take_profit_percent": float(_tp) if _tp is not None else None,
            "take_profit_active": bool(tp_active),
            "trailing_stop_percent": float(_tr) if _tr is not None else None,
            "trailing_active": bool(trail_active),
            "trailing_cancels_sl_tp": bool(trail_active),
            "max_positions_requested": int(config.max_positions) if config.max_positions is not None else None,
            "max_concurrent_applied": (
                _multi_position_compounding_enabled(config)
                if _multi_position_compounding_enabled(config) is not None
                else (
                    1 if _compounding_enabled(config)
                    else (int(config.max_positions) if (config.max_positions or 0) > 1 else 1)
                )
            ),
            "max_open_positions_observed": int(_max_open),
            "additional_positions_trades": sum(
                1 for tr in trades
                if isinstance(getattr(tr, "metadata", None), dict)
                and tr.metadata.get("position_kind") == "additional"
            ),
            # ✅ R58 — شفافية الحجم والتصفية (نهاية عصر الالتباس 1% ↔ 100%):
            # ما استلمه المحرك، وما طبّقه فعلاً ككسر من الرصيد، وهل صُفّي الحساب.
            "position_sizing_mode": str(getattr(config, "position_sizing", "") or ""),
            "position_size_percent_input": (
                float(config.position_size_percent)
                if config.position_size_percent is not None else None
            ),
            "position_fraction_applied": _resolve_risk_fraction(config),
            "position_size_semantics": (
                (
                    f"R62: كل مركز جديد = الرصيد الجاري ÷ {_multi_position_compounding_enabled(config)} "
                    "+ حتى N مراكز متزامنة (الحجم يتجدد بعد كل إقفال)"
                    if _multi_position_compounding_enabled(config) is not None
                    else None
                )
                or (
                    "R60: compounding ⇒ 100% من الرصيد الجاري في كل صفقة + مركز واحد فقط"
                    if _compounding_enabled(config)
                    else "R58: percentage ⇒ نسبة مئوية (1 = 1%)؛ غير ذلك كسر تاريخي (1.0 = 100%)"
                )
            ),
            # ✅ R60 — صدى وضع التراكم في effective_config (يصل للفرونت والمكتبة)
            "compounding": _compounding_enabled(config),
            # ✅ R62 — صدى وضع المراكز المتعددة التراكمية (يصل للفرونت والمكتبة)
            "multi_position_compounding": _multi_position_compounding_enabled(config) is not None,
            "multi_position_slots": _multi_position_compounding_enabled(config),
            "account_liquidated": any(
                (tr.exit_reason or "").startswith("Liquidation") for tr in trades
            ),
        }

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

        ✅ الجولة 13 — إبادة العمولة (حرفياً):
        كود تطبيق commission/slippage مُمسوح بالكامل — لا فرع شرطي، لا fallback
        في التواقيع، لا افتراض مخفي. الحساب صافٍ بالبنية نفسها:
            pnl == (exit_price − entry_price) × units × (long? +1 : −1)
        تُعيد دائماً الـ pnl الخام كما هو (لا خصم إطلاقاً).
        """
        net_pnl = pnl
        for trade in trades:
            if trade.id == trade_id and trade.exit_time is None:
                trade.exit_time = exit_time
                trade.exit_price = exit_price
                trade.exit_reason = reason
                # ✅ الجولة 13: الربح صافٍ بالبنية — لا خصم أي رسوم إطلاقاً
                trade.pnl = pnl
                trade.pnl_percentage = pnl_percentage

                # ✅ الجولة 13: أعمدة الشفافية الحسابية الكاملة
                # (الصيغة الموحدة الموثقة — بلا أي تقريب، float64 كاملة)
                fill_m = str(getattr(config, "fill_model", "next_open") or "next_open") if config else "next_open"
                _sign_tr = 1.0 if trade.position_type == 'long' else -1.0
                _delta_tr = float(exit_price) - float(trade.entry_price)
                trade.price_delta = _delta_tr
                # ✅ الجولة 13 (الصيغة الموحدة): price_delta_pct موقّعة بالاتجاه
                trade.price_delta_pct = (_delta_tr / float(trade.entry_price) * 100.0 * _sign_tr) if trade.entry_price else 0.0
                trade.direction = 'long' if _sign_tr > 0 else 'short'
                # ✅ الجولة 13: result_pct = price_delta_pct (نفس القيمة بلا اختلاف)
                trade.result_pct = trade.price_delta_pct
                trade.pnl_gross = _delta_tr * float(trade.position_size) * _sign_tr
                trade.fill_entry = fill_m
                trade.fill_exit = fill_m
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

        # ✅ الجولة 13 — التدقيق الحسابي الذاتي (math_audit) بعقد الدقة المتناهية:
        # الصيغة الصافية (بلا أي إشارة إلى commission/slippage — محذوفة من النظام نهائياً):
        #     pnl == (exit_price - entry_price) * units * (long? +1 : -1)
        # التسامح المشدّد: 1e-9 (كان 0.01 فضفاضاً لنظام بلا عمولة)
        _FORMULA_TOLERANCE = 1e-9
        fees_applied = 0.0
        sum_pnl = 0.0
        max_abs_error = 0.0
        checked = 0
        audit_violations: List[Dict[str, Any]] = []
        for tr in trades:
            try:
                if tr.exit_time is None or tr.exit_price is None or tr.pnl is None:
                    continue
                checked += 1
                _sign_a = 1.0 if tr.position_type == 'long' else -1.0
                expected_a = (
                    (float(tr.exit_price) - float(tr.entry_price)) * float(tr.position_size) * _sign_a
                )
                err_a = abs(float(tr.pnl) - expected_a)
                if err_a > max_abs_error:
                    max_abs_error = err_a
                if err_a > _FORMULA_TOLERANCE and len(audit_violations) < 10:
                    audit_violations.append({
                        "trade_id": tr.id,
                        "pnl": float(tr.pnl),
                        "expected": float(expected_a),
                        "abs_error": float(err_a),
                    })
                # ✅ الجولة 13 (Zero-Fee): يبقى إثبات الشفافية — ثابت 0.0 دائماً
                fees_applied += float(tr.commission or 0.0)
                sum_pnl += float(tr.pnl)
            except Exception:
                logger.exception("math_audit: فحص صفقة فشل — تجاهل")
        total_pnl_matches = bool(abs(total_pnl - sum_pnl) <= 0.01)
        # ✅ R58 — التصفية القسرية تقطع خسائر الصفقات عند رأس المال المتاح:
        # الفرق بين مجموع pnl الخام و total_pnl المحدود هو «المقطوع» — متوقع
        # وموثق، ليس خطأ حسابياً.
        _r58_liquidated = bool(
            equity_curve and float(equity_curve[-1]) <= 0.0
        ) or any(
            (tr.exit_reason or "").startswith("Liquidation") for tr in trades
        )
        if not total_pnl_matches and not _r58_liquidated:
            logger.warning(
                "math_audit: total_pnl (%.6f) != مجموع pnl الصفقات (%.6f)",
                total_pnl, sum_pnl,
            )
        elif not total_pnl_matches and _r58_liquidated:
            logger.info(
                "math_audit: تباقط تصفية متوقع (R58) — الرصيد ثُبّت عند صفر "
                "والمقطوع %.6f موثق في liquidation_truncated",
                sum_pnl - total_pnl,
            )
        math_audit = {
            "checked_trades": checked,
            # ✅ الجولة 13: قيمة خام بلا تقريب (عقد الدقة المتناهية)
            "max_abs_error": float(max_abs_error),
            "formula_tolerance": _FORMULA_TOLERANCE,
            "formula": "pnl == (exit_price - entry_price) * units * (long? +1 : -1)",
            "consistent": bool(max_abs_error <= _FORMULA_TOLERANCE and total_pnl_matches and not audit_violations),
            "total_pnl": float(total_pnl),
            "trades_pnl_sum": float(sum_pnl),
            "total_pnl_matches": total_pnl_matches,
            "fees_applied": float(fees_applied),
            "violations": audit_violations,
            # ✅ الجولة 13 — تقرير الدقة: كل الحسابات float64 كاملة بلا أي تقريب
            "precision_report": {
                "formula_tolerance": _FORMULA_TOLERANCE,
                "float64": True,
                "rounded_fields": [],
            },
            # ✅ R55 — صدى سياسة المخاطر المطبّقة فعلاً + إحصاء التزامن:
            # شفافية كاملة (ما طُبّق من SL/TP/تريلينق/سقف مراكز ومن القيم)
            "risk_echo": self._build_risk_echo(config, trades),
            # ✅ R58 — أرضية الواقع المالي: هل صُفّي الحساب (رصيد ≤ 0)؟
            "account_liquidated": _r58_liquidated,
            # ✅ R58 — مقدار الخسارة المقطوعة عند التصفية (صفر إن لم تُصفَّ)
            "liquidation_truncated": (
                max(0.0, sum_pnl - total_pnl) if _r58_liquidated else 0.0
            ),
        }
        
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
            raw_data=None,

            # ✅ الجولة 12: الشفافية الحسابية الكاملة
            # (trades=trades كان يُمرَّر أعلاه وصار الآن حقلاً حقيقياً في BacktestResult)
            # ✅ الجولة 13: قيمة خام بلا تقريب — إثبات Zero-Fee (ثابت 0.0 دائماً)
            fees_applied=float(fees_applied),
            fill_model=str(getattr(config, "fill_model", "next_open") or "next_open"),
            math_audit=math_audit,
            # ✅ R55 — صدى إعدادات المخاطر المطبّقة فعلاً (نفس risk_echo)
            effective_config=dict(math_audit.get("risk_echo") or {}),
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
            # ✅ الجولة 13 — إبادة العمولة: لا خصم عند الدخول (كود commission ممسوح)
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



