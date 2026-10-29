# app/backtest/engine.py
import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import uuid
from collections import defaultdict
import warnings
import traceback
from app.services.strategy.schemas import StrategyConfig as StrategyConfigSchema
from app.services.strategy.core import StrategyEngine
from .schemas import BacktestConfig, BacktestResult, Trade, PositionType
from .metrics import PerformanceMetrics
from app.services.data_service import DataService
from app.services.indicators import IndicatorCalculator

warnings.filterwarnings('ignore')

class BacktestEngine:
    """محرك الباك-تيست التاريخي الكامل"""
    
    def __init__(self, data_service: DataService):
        self.data_service = data_service
        self.metrics_calculator = PerformanceMetrics()
        self.indicator_calculator = IndicatorCalculator()
        
    async def run_backtest(self, config: BacktestConfig) -> BacktestResult:
        """
        تشغيل باك-تيست كامل
        
        Args:
            config: تكوين الباك-تيست
            
        Returns:
            BacktestResult: نتيجة الباك-تيست
        """
        start_time = datetime.utcnow()
        
        print(f"🚀 Starting backtest: {config.name}")
        print(f"📅 Period: {config.start_date} to {config.end_date}")
        print(f"💰 Initial capital: ${config.initial_capital:,.2f}")
        print(f"📊 Symbols: {config.symbols}")
        print(f"⏰ Timeframe: {config.timeframe}")
        
        try:
            # 1. جلب البيانات التاريخية لجميع الرموز
            all_data = {}
            for symbol in config.symbols:
                try:
                    print(f"📥 Fetching data for {symbol}...")
                    
                    # حساب عدد الأيام المطلوبة
                    days_required = (config.end_date - config.start_date).days + 30
                    
                    data = await self.data_service.get_historical(
                        symbol=symbol,
                        timeframe=config.timeframe,
                        market=config.market,
                        days=days_required,
                        use_cache=True
                    )
                    
                    if not data.empty:

                        # توحيد الـ index ليكون UTC tz-aware
                        data.index = pd.to_datetime(data.index, utc=True)

                        # توحيد تواريخ الكونفيق
                        start = config.start_date.astimezone(timezone.utc)
                        end = config.end_date.astimezone(timezone.utc)

                        mask = (data.index >= start) & (data.index <= end)
                        filtered_data = data.loc[mask]

                        # فلترة البيانات حسب النطاق الزمني المطلوب
                        # if isinstance(data.index[0], pd.Timestamp):
                        #     mask = (data.index >= config.start_date) & (data.index <= config.end_date)
                        #     filtered_data = data.loc[mask]
                        # else:
                        #     data.index = pd.to_datetime(data.index, utc=True)

                        #     data.index = pd.to_datetime(data.index)
                        #     mask = (data.index >= config.start_date) & (data.index <= config.end_date)
                        #     filtered_data = data.loc[mask]
                        
                        if not filtered_data.empty:
                            all_data[symbol] = filtered_data
                            print(f"✅ Got {len(filtered_data)} bars for {symbol}")
                        else:
                            print(f"⚠️ No data in date range for {symbol}")
                    else:
                        print(f"⚠️ No data available for {symbol}")
                        
                except Exception as e:
                    print(f"❌ Error fetching data for {symbol}: {str(e)}")
                    traceback.print_exc()
            
            if not all_data:
                raise ValueError("No data available for any symbol")
            
            # 2. محاكاة التداول
            trades = []
            equity_curve = [config.initial_capital]
            current_capital = config.initial_capital
            
            # محاكاة لكل رمز
            for symbol, data in all_data.items():
                symbol_trades = await self._simulate_trades_for_symbol(
                    symbol, data, config, current_capital
                )
                trades.extend(symbol_trades)
                
                # تحديث رأس المال بناءً على الصفقات
                for trade in symbol_trades:
                    if trade.pnl:
                        current_capital += trade.pnl
                        equity_curve.append(current_capital)
            
            # 3. حساب المقاييس
            result = await self._create_backtest_result(
                config=config,
                trades=trades,
                equity_curve=equity_curve,
                execution_start=start_time
            )
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            result.execution_time_seconds = execution_time
            
            print(f"✅ Backtest completed in {execution_time:.2f} seconds")
            print(f"📈 Final capital: ${result.final_capital:,.2f}")
            print(f"💰 Total P&L: {result.total_pnl_percent:.2f}%")
            print(f"🎯 Win rate: {result.win_rate:.2f}%")
            print(f"📊 Total trades: {result.total_trades}")
            print(f"📉 Max drawdown: {result.max_drawdown_percent:.2f}%")
            
            return result
            
        except Exception as e:
            print(f"❌ Backtest failed: {str(e)}")
            traceback.print_exc()
            raise
    


    async def _simulate_trades_for_symbol(
        self,
        symbol: str,
        data: pd.DataFrame,
        config: BacktestConfig,
        initial_capital: float
    ) -> List[Trade]:
        """محاكاة الصفقات لرمز معين"""
        
        # ⭐⭐ إضافة هذا الشرط فقط ⭐⭐
        if config.strategy_config:
            # استخدام الإستراتيجية الجديدة
            return await self._simulate_with_strategy(
                symbol, data, config, initial_capital
            )
        else:
            # استخدام المنطق الحالي (الافتراضي)
            return await self._simulate_with_default_logic(
                symbol, data, config, initial_capital
            )




    async def _simulate_with_default_logic(
        self,
        symbol: str,
        data: pd.DataFrame,
        config: BacktestConfig,
        initial_capital: float
    ) -> List[Trade]:
        """محاكاة الصفقات لرمز معين"""
        trades = []
        
    


        if len(data) < 50:  # نحتاج بيانات كافية
            print(f"⚠️ Not enough data for {symbol} ({len(data)} bars)")
            return trades
        
        # فرز البيانات حسب التاريخ
        data = data.sort_index()
        
        print(f"📊 Simulating trades for {symbol} with {len(data)} bars")
   
        data = data.copy()
        
        # حساب المؤشرات
        data = self._calculate_indicators(data)
        
        position = None
        entry_price = 0
        entry_time = None
        position_size = 0
        trade_id = None
        
        for i in range(20, len(data)):  # بدء من 20 لضمان وجود بيانات للمؤشرات
            current_time = data.index[i]
            current_price = data['close'].iloc[i]
            current_rsi = data['rsi'].iloc[i] if 'rsi' in data.columns else 50
            current_sma_20 = data['sma_20'].iloc[i] if 'sma_20' in data.columns else current_price
            prev_rsi = data['rsi'].iloc[i-1] if i > 0 and 'rsi' in data.columns else 50
            
            # منطق الدخول والخروج
            if position is None:
                # شروط الدخول لمركز شراء
                entry_condition = (
                    current_rsi < 30 and  # RSI فوق البيع
                    prev_rsi < current_rsi and  # RSI يتجه للأعلى
                    current_price > current_sma_20  # السعر فوق المتوسط المتحرك
                )
                
                if entry_condition and config.enable_short_selling == False:
                    # دخول مركز شراء
                    position = 'long'
                    entry_price = current_price
                    entry_time = current_time
                    position_size = (initial_capital * config.position_size_percent) / entry_price
                    
                    # حساب العمولة والانزلاق
                    commission = entry_price * position_size * config.commission_rate
                    slippage = entry_price * position_size * config.slippage_percent
                    
                    trade_id = str(uuid.uuid4())
                    
                    trade = Trade(
                        id=trade_id,
                        symbol=symbol,
                        entry_time=entry_time,
                        exit_time=None,
                        entry_price=entry_price,
                        exit_price=None,
                        position_type='long',
                        position_size=position_size,
                        pnl=None,
                        pnl_percentage=None,
                        commission=commission,
                        slippage=slippage,
                        stop_loss=entry_price * (1 - config.stop_loss_percent/100) if config.stop_loss_percent else None,
                        take_profit=entry_price * (1 + config.take_profit_percent/100) if config.take_profit_percent else None,
                        exit_reason=None,
                        metadata={
                            'entry_condition': 'rsi_oversold',
                            'rsi_value': float(current_rsi),
                            'sma_20': float(current_sma_20)
                        }
                    )
                    
                    trades.append(trade)
                    print(f"  📈 Entry long at {entry_price:.2f} for {symbol}")
            
            elif position == 'long':
                current_pnl = (current_price - entry_price) * position_size
                current_pnl_percent = ((current_price - entry_price) / entry_price) * 100
                
                # شروط الخروج
                exit_condition = False
                exit_reason = ""
                
                # 1. RSI فوق الشراء
                if current_rsi > 70:
                    exit_condition = True
                    exit_reason = "rsi_overbought"
                
                # 2. وقف الخسارة
                elif config.stop_loss_percent and current_pnl_percent < -config.stop_loss_percent:
                    exit_condition = True
                    exit_reason = "stop_loss"
                
                # 3. جني الأرباح
                elif config.take_profit_percent and current_pnl_percent > config.take_profit_percent:
                    exit_condition = True
                    exit_reason = "take_profit"
                
                # 4. السعر تحت المتوسط المتحرك
                elif current_price < current_sma_20:
                    exit_condition = True
                    exit_reason = "below_sma"
                
                if exit_condition:
                    # حساب العمولة والانزلاق للخروج
                    exit_commission = current_price * position_size * config.commission_rate
                    exit_slippage = current_price * position_size * config.slippage_percent
                    
                    # تحديث الصفقة
                    for trade in trades:
                        if trade.id == trade_id and trade.exit_time is None:
                            trade.exit_time = current_time
                            trade.exit_price = current_price
                            trade.pnl = current_pnl - exit_commission - exit_slippage
                            trade.pnl_percentage = current_pnl_percent
                            trade.exit_reason = exit_reason
                            trade.commission += exit_commission
                            trade.slippage += exit_slippage
                            break
                    
                    print(f"  📉 Exit long at {current_price:.2f} for {symbol}, P&L: {current_pnl_percent:.2f}% ({exit_reason})")
                    position = None
                    trade_id = None
        
        # إغلاق أي مركز مفتوح في نهاية الفترة
        if position is not None:
            last_price = data['close'].iloc[-1]
            last_time = data.index[-1]
            final_pnl = (last_price - entry_price) * position_size
            final_pnl_percent = ((last_price - entry_price) / entry_price) * 100
            
            for trade in trades:
                if trade.id == trade_id and trade.exit_time is None:
                    trade.exit_time = last_time
                    trade.exit_price = last_price
                    trade.pnl = final_pnl
                    trade.pnl_percentage = final_pnl_percent
                    trade.exit_reason = 'end_of_period'
                    break
            
            print(f"  🔚 Closed open position at {last_price:.2f} for {symbol}, Final P&L: {final_pnl_percent:.2f}%")
        
        return trades


    async def _simulate_with_strategy(
        self,
        symbol: str,
        data: pd.DataFrame,
        config: BacktestConfig,
        initial_capital: float
    ) -> List[Trade]:
        """محاكاة الصفقات باستخدام إستراتيجية مخصصة"""
        
        trades = []
        
        if len(data) < 20:
            return trades
        
        # 1. إنشاء محرك الإستراتيجية من التكوين
        try:

            # تحويل التكوين إلى كائن StrategyConfig
            strategy_config_obj = StrategyConfigSchema(**config.strategy_config)
            strategy_engine = StrategyEngine(strategy_config_obj)
            
        except Exception as e:
            print(f"❌ خطأ في إنشاء الإستراتيجية: {e}")
            # استرجاع المنطق الافتراضي
            return await self._simulate_with_default_logic(symbol, data, config, initial_capital)
        
        # 2. تشغيل الإستراتيجية على البيانات
        try:
            strategy_result = await strategy_engine.run_strategy(
                data=data,
                live_mode=False,
                use_cache=True
            )
            
            signals = strategy_result.filtered_signals
            print(f"   📊 الإستراتيجية أنتجت {len(signals)} إشارة لـ {symbol}")
            
        except Exception as e:
            print(f"❌ خطأ في تشغيل الإستراتيجية: {e}")
            return trades
        
        # 3. تحويل الإشارات إلى صفقات (باستخدام نفس منطقك الحالي)
        position = None
        entry_price = 0
        entry_time = None
        position_size = 0
        trade_id = None
        
        for signal in signals:
            try:
                # العثور على السعر المناسب للإشارة
                signal_time = signal.timestamp
                
                # البحث عن السعر في وقت الإشارة
                price_data = data[data.index == signal_time]
                if price_data.empty:
                    # إذا لم نجد الوقت بالضبط، نأخذ السعر الأقرب
                    idx = (data.index - signal_time).abs().argmin()
                    current_price = data['close'].iloc[idx]
                else:
                    current_price = price_data['close'].iloc[0]
                
                # منطق الدخول والخروج
                if signal.action == 'buy' and position is None:
                    # دخول مركز شراء
                    position = 'long'
                    entry_price = current_price
                    entry_time = signal_time
                    position_size = (initial_capital * config.position_size_percent) / entry_price
                    
                    # حساب العمولة والانزلاق
                    commission = entry_price * position_size * config.commission_rate
                    slippage = entry_price * position_size * config.slippage_percent
                    
                    trade_id = str(uuid.uuid4())
                    
                    trade = Trade(
                        id=trade_id,
                        symbol=symbol,
                        entry_time=entry_time,
                        exit_time=None,
                        entry_price=entry_price,
                        exit_price=None,
                        position_type='long',
                        position_size=position_size,
                        pnl=None,
                        pnl_percentage=None,
                        commission=commission,
                        slippage=slippage,
                        stop_loss=entry_price * (1 - config.stop_loss_percent/100) if config.stop_loss_percent else None,
                        take_profit=entry_price * (1 + config.take_profit_percent/100) if config.take_profit_percent else None,
                        exit_reason=None,
                        metadata={
                            'strategy': config.strategy_config.get('name', 'Unknown'),
                            'signal_reason': signal.reason,
                            'rule_name': signal.rule_name
                        }
                    )
                    
                    trades.append(trade)
                    print(f"  📈 دخول بيعت على {entry_price:.2f} لـ {symbol} - {signal.reason}")
                
                elif signal.action in ['sell', 'close'] and position == 'long':
                    # خروج من المركز
                    current_pnl = (current_price - entry_price) * position_size
                    current_pnl_percent = ((current_price - entry_price) / entry_price) * 100
                    
                    # حساب العمولة والانزلاق للخروج
                    exit_commission = current_price * position_size * config.commission_rate
                    exit_slippage = current_price * position_size * config.slippage_percent
                    
                    # تحديث الصفقة
                    for trade in trades:
                        if trade.id == trade_id and trade.exit_time is None:
                            trade.exit_time = signal_time
                            trade.exit_price = current_price
                            trade.pnl = current_pnl - exit_commission - exit_slippage
                            trade.pnl_percentage = current_pnl_percent
                            trade.exit_reason = f"إشارة إستراتيجية: {signal.reason}"
                            trade.commission += exit_commission
                            trade.slippage += exit_slippage
                            break
                    
                    print(f"  📉 خروج بيعت على {current_price:.2f} لـ {symbol}, ربح/خسارة: {current_pnl_percent:.2f}%")
                    position = None
                    trade_id = None
                    
            except Exception as e:
                print(f"⚠️ خطأ في معالجة الإشارة: {e}")
                continue
        
        # إغلاق أي مركز مفتوح في نهاية الفترة
        if position is not None:
            last_price = data['close'].iloc[-1]
            last_time = data.index[-1]
            final_pnl = (last_price - entry_price) * position_size
            final_pnl_percent = ((last_price - entry_price) / entry_price) * 100
            
            for trade in trades:
                if trade.id == trade_id and trade.exit_time is None:
                    trade.exit_time = last_time
                    trade.exit_price = last_price
                    trade.pnl = final_pnl
                    trade.pnl_percentage = final_pnl_percent
                    trade.exit_reason = 'نهاية الفترة'
                    break
            
            print(f"  🔚 إغلاق مركز مفتوح على {last_price:.2f} لـ {symbol}, ربح/خسارة نهائية: {final_pnl_percent:.2f}%")
        
        return trades 

    def _calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """حساب المؤشرات الفنية"""
        data = data.copy()
        
        # RSI
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['rsi'] = 100 - (100 / (1 + rs))
        
        # المتوسطات المتحركة
        data['sma_20'] = data['close'].rolling(window=20).mean()
        data['sma_50'] = data['close'].rolling(window=50).mean()
        
        # MACD
        ema_12 = data['close'].ewm(span=12, adjust=False).mean()
        ema_26 = data['close'].ewm(span=26, adjust=False).mean()
        data['macd'] = ema_12 - ema_26
        data['macd_signal'] = data['macd'].ewm(span=9, adjust=False).mean()
        data['macd_histogram'] = data['macd'] - data['macd_signal']
        
        # بولينجر باندز
        data['bb_middle'] = data['close'].rolling(window=20).mean()
        bb_std = data['close'].rolling(window=20).std()
        data['bb_upper'] = data['bb_middle'] + (bb_std * 2)
        data['bb_lower'] = data['bb_middle'] - (bb_std * 2)
        
        return data
    
    async def _create_backtest_result(
        self,
        config: BacktestConfig,
        trades: List[Trade],
        equity_curve: List[float],
        execution_start: datetime
    ) -> BacktestResult:
        """إنشاء نتيجة الباك-تيست"""
        
        if not trades:
         
            return BacktestResult(
                id=str(uuid.uuid4()),
                config=config,
                execution_time_seconds=(datetime.utcnow() - execution_start).total_seconds(),
                initial_capital=config.initial_capital,
                final_capital=config.initial_capital,
                total_pnl=0,
                total_pnl_percent=0,
                annual_return_percent=0,
                sharpe_ratio=0,
                sortino_ratio=0,
                calmar_ratio=0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0,
                profit_factor=0,
                expectancy=0,
                max_drawdown_percent=0,
                max_drawdown_duration_days=0,
                volatility_annual=0,
                var_95=0,
                cvar_95=0,
                trades=trades,
                equity_curve=equity_curve,
                drawdown_curve=self._calculate_drawdown_curve(equity_curve),
                monthly_returns={},
                yearly_returns={},
                avg_winning_trade=0,
                avg_losing_trade=0,
                largest_winning_trade=0,
                largest_losing_trade=0,
                avg_trade_duration_hours=0,
                symbols_performance=self._calculate_symbols_performance(trades),
                system_quality_number=0,
                kelly_criterion=0
            )
        
        # حساب المقاييس الأساسية
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl <= 0]
        
        win_rate = len(winning_trades) / len(trades) * 100 if trades else 0
        
        total_pnl = sum(t.pnl or 0 for t in trades)
        total_pnl_percent = (total_pnl / config.initial_capital) * 100
        
        final_capital = config.initial_capital + total_pnl
        
        # حساب العائد السنوي
        days_duration = (config.end_date - config.start_date).days
        annual_return_percent = 0
        if days_duration > 0 and config.initial_capital > 0:
            annual_return_percent = ((final_capital / config.initial_capital) ** (365 / days_duration) - 1) * 100
        
        # حساب منحنى الانخفاض
        drawdown_curve = self._calculate_drawdown_curve(equity_curve)
        max_drawdown_percent = max(drawdown_curve) if drawdown_curve else 0
        
        # حساب العوائد الشهرية والسنوية
        monthly_returns, yearly_returns = self._calculate_periodic_returns(equity_curve, config)
        
        # حساب المقاييس الأخرى
        sharpe_ratio = self._calculate_sharpe_ratio(equity_curve)
        sortino_ratio = self._calculate_sortino_ratio(equity_curve)
        calmar_ratio = self._calculate_calmar_ratio(annual_return_percent, max_drawdown_percent)
        profit_factor = self._calculate_profit_factor(winning_trades, losing_trades)
        expectancy = self._calculate_expectancy(trades)
        
        # حساب متوسط مدة الصفقة
        avg_trade_duration = self._calculate_avg_trade_duration(trades)
        recovery_factor = (
            total_pnl / max_drawdown_percent
            if max_drawdown_percent > 0 else 0
        )

        # إنشاء نتيجة الباك-تيست
        result = BacktestResult(
            id=str(uuid.uuid4()),
            config=config,
            execution_time_seconds=(datetime.utcnow() - execution_start).total_seconds(),
            initial_capital=config.initial_capital,
            final_capital=final_capital,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,
            annual_return_percent=annual_return_percent,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            total_trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            max_drawdown_percent=max_drawdown_percent,
            max_drawdown_duration_days=self._calculate_max_drawdown_duration(drawdown_curve),
            volatility_annual=self._calculate_volatility(equity_curve),
            var_95=self._calculate_var(equity_curve, 95),
            cvar_95=self._calculate_cvar(equity_curve, 95),
            trades=trades,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            monthly_returns=monthly_returns,
            yearly_returns=yearly_returns,
            avg_winning_trade=np.mean([t.pnl for t in winning_trades]) if winning_trades else 0,
            avg_losing_trade=np.mean([t.pnl for t in losing_trades]) if losing_trades else 0,
            largest_winning_trade=max([t.pnl for t in winning_trades]) if winning_trades else 0,
            largest_losing_trade=min([t.pnl for t in losing_trades]) if losing_trades else 0,
            avg_trade_duration_hours=avg_trade_duration,
            symbols_performance=self._calculate_symbols_performance(trades),
            system_quality_number=self._calculate_system_quality_number(trades),
            kelly_criterion=self._calculate_kelly_criterion(trades)
        )
        
        return result
    
    def _calculate_drawdown_curve(self, equity_curve: List[float]) -> List[float]:
        """حساب منحنى الانخفاض"""
        if not equity_curve:
            return []
        
        peak = equity_curve[0]
        drawdowns = []
        
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100 if peak > 0 else 0
            drawdowns.append(drawdown)
        
        return drawdowns
    
    def _calculate_symbols_performance(self, trades: List[Trade]) -> Dict[str, Dict[str, float]]:
        """حساب أداء كل رمز"""
        symbols = {}
        
        for trade in trades:
            if trade.symbol not in symbols:
                symbols[trade.symbol] = {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'total_pnl': 0,
                    'avg_pnl': 0
                }
            
            symbols[trade.symbol]['total_trades'] += 1
            if trade.pnl and trade.pnl > 0:
                symbols[trade.symbol]['winning_trades'] += 1
            if trade.pnl:
                symbols[trade.symbol]['total_pnl'] += trade.pnl
        
        for symbol, data in symbols.items():
            if data['total_trades'] > 0:
                data['win_rate'] = (data['winning_trades'] / data['total_trades']) * 100
                data['avg_pnl'] = data['total_pnl'] / data['total_trades']
        
        return symbols
    
    def _calculate_periodic_returns(self, equity_curve: List[float], config: BacktestConfig) -> Tuple[Dict[str, float], Dict[str, float]]:
        """حساب العوائد الشهرية والسنوية"""
        # هذا مثال مبسط
        # في التطبيق الحقيقي، نحتاج إلى تتبع التواريخ
        
        monthly_returns = {}
        yearly_returns = {}
        
        if len(equity_curve) > 30:
            # عوائد شهرية افتراضية
            for i in range(min(12, len(equity_curve) // 30)):
                start_idx = i * 30
                end_idx = min((i + 1) * 30, len(equity_curve) - 1)
                
                if end_idx > start_idx:
                    monthly_return = ((equity_curve[end_idx] - equity_curve[start_idx]) / 
                                    equity_curve[start_idx]) * 100
                    monthly_returns[f"Month_{i+1}"] = monthly_return
        
        # العائد السنوي الإجمالي
        if len(equity_curve) > 1:
            yearly_return = ((equity_curve[-1] - equity_curve[0]) / 
                           equity_curve[0]) * 100
            yearly_returns["Total_Period"] = yearly_return
        
        return monthly_returns, yearly_returns
    
    def _calculate_sharpe_ratio(self, equity_curve: List[float]) -> float:
        """حساب نسبة شارب"""
        if len(equity_curve) < 2:
            return 0.0
        
        returns = np.diff(equity_curve) / equity_curve[:-1]
        if returns.std() == 0:
            return 0.0
        
        # افتراض معدل خالي من المخاطر 2%
        risk_free_rate = 0.02 / 252  # معدل يومي
        
        sharpe = (returns.mean() - risk_free_rate) / returns.std() * np.sqrt(252)
        return float(sharpe)
    
    def _calculate_sortino_ratio(self, equity_curve: List[float]) -> float:
        """حساب نسبة سورتينو"""
        if len(equity_curve) < 2:
            return 0.0
        
        returns = np.diff(equity_curve) / equity_curve[:-1]
        negative_returns = returns[returns < 0]
        
        if len(negative_returns) == 0 or negative_returns.std() == 0:
            return 0.0
        
        # افتراض معدل خالي من المخاطر 2%
        risk_free_rate = 0.02 / 252
        
        sortino = (returns.mean() - risk_free_rate) / negative_returns.std() * np.sqrt(252)
        return float(sortino)
    
    def _calculate_calmar_ratio(self, annual_return: float, max_drawdown: float) -> float:
        """حساب نسبة كالمار"""
        if max_drawdown == 0:
            return 0.0
        return annual_return / abs(max_drawdown)
    
    def _calculate_profit_factor(self, winning_trades: List[Trade], losing_trades: List[Trade]) -> float:
        """حساب عامل الربح"""
        gross_profit = sum(t.pnl for t in winning_trades if t.pnl)
        gross_loss = abs(sum(t.pnl for t in losing_trades if t.pnl))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        
        return gross_profit / gross_loss
    
    def _calculate_expectancy(self, trades: List[Trade]) -> float:
        """حساب التوقع"""
        if not trades:
            return 0.0
        
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl <= 0]
        
        win_rate = len(winning_trades) / len(trades)
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = abs(np.mean([t.pnl for t in losing_trades])) if losing_trades else 0
        
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        return float(expectancy)
    
    def _calculate_max_drawdown_duration(self, drawdown_curve: List[float]) -> int:
        """حساب مدة أقصى انخفاض"""
        if not drawdown_curve:
            return 0
        
        max_duration = 0
        current_duration = 0
        
        for dd in drawdown_curve:
            if dd > 0:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0
        
        return max_duration
    
    def _calculate_volatility(self, equity_curve: List[float]) -> float:
        """حساب التقلب السنوي"""
        if len(equity_curve) < 2:
            return 0.0
        
        returns = np.diff(equity_curve) / equity_curve[:-1]
        volatility = returns.std() * np.sqrt(252) * 100  # كنسبة مئوية سنوية
        return float(volatility)
    
    def _calculate_var(self, equity_curve: List[float], confidence: float) -> float:
        """حساب القيمة المعرضة للخطر"""
        if len(equity_curve) < 2:
            return 0.0
        
        returns = np.diff(equity_curve) / equity_curve[:-1]
        var = np.percentile(returns, 100 - confidence) * 100  # كنسبة مئوية
        return float(var)
    
    def _calculate_cvar(self, equity_curve: List[float], confidence: float) -> float:
        """حساب القيمة المعرضة للخطر الشرطية"""
        if len(equity_curve) < 2:
            return 0.0
        
        returns = np.diff(equity_curve) / equity_curve[:-1]
        var = np.percentile(returns, 100 - confidence)
        cvar = returns[returns <= var].mean() * 100  # كنسبة مئوية
        return float(cvar)
    
    def _calculate_avg_trade_duration(self, trades: List[Trade]) -> float:
        """حساب متوسط مدة الصفقة بالساعات"""
        if not trades:
            return 0.0
        
        durations = []
        for trade in trades:
            if trade.entry_time and trade.exit_time:
                duration = (trade.exit_time - trade.entry_time).total_seconds() / 3600
                durations.append(duration)
        
        return float(np.mean(durations)) if durations else 0.0
    
    def _calculate_system_quality_number(self, trades: List[Trade]) -> float:
        """حساب رقم جودة النظام"""
        if not trades:
            return 0.0
        
        pnls = [t.pnl for t in trades if t.pnl is not None]
        if not pnls:
            return 0.0
        
        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls)
        
        if std_pnl == 0:
            return 0.0
        
        sqn = (mean_pnl / std_pnl) * np.sqrt(len(trades))
        return float(sqn)
    
    def _calculate_kelly_criterion(self, trades: List[Trade]) -> float:
        """حساب معيار كيلي"""
        if not trades:
            return 0.0
        
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl < 0]
        
        win_rate = len(winning_trades) / len(trades)
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = abs(np.mean([t.pnl for t in losing_trades])) if losing_trades else 0
        
        if avg_loss == 0:
            return 0.0
        
        kelly = win_rate - ((1 - win_rate) / (avg_win / avg_loss))
        return float(kelly)
    
    async def run_walk_forward_analysis(
        self,
        config: BacktestConfig,
        periods: int = 5
    ) -> List[BacktestResult]:
        """تشغيل تحليل مشي للأمام"""
        results = []
        
        # تقسيم الفترة الزمنية إلى فترات فرعية
        total_days = (config.end_date - config.start_date).days
        period_days = total_days // periods
        
        for i in range(periods):
            period_start = config.start_date + timedelta(days=i * period_days)
            period_end = period_start + timedelta(days=period_days)
            
            if i == periods - 1:
                period_end = config.end_date
            
            print(f"\n🔍 Walk-forward period {i+1}: {period_start.date()} to {period_end.date()}")
            
            # تحديث التكوين للفترة الحالية
            period_config = config.copy()
            period_config.start_date = period_start
            period_config.end_date = period_end
            
            # تشغيل الباك-تيست للفترة الحالية
            try:
                result = await self.run_backtest(period_config)
                results.append(result)
                print(f"✅ Period {i+1} completed: P&L {result.total_pnl_percent:.2f}%, Trades: {result.total_trades}")
            except Exception as e:
                print(f"❌ Error in period {i+1}: {str(e)}")
        
        return results
    
    async def run_monte_carlo_simulation(
        self,
        config: BacktestConfig,
        simulations: int = 1000
    ) -> Dict[str, Any]:
        """تشغيل محاكاة مونت كارلو"""
        print(f"\n🎲 Running Monte Carlo simulation ({simulations} iterations)")
        
        # تشغيل باك-تيست أساسي للحصول على الصفقات
        print("Running base backtest for simulation data...")
        base_result = await self.run_backtest(config)
        base_trades = base_result.trades
        
        if not base_trades or len(base_trades) < 10:
            print("⚠️ Not enough trades for Monte Carlo simulation")
            return {
                'simulations': 0,
                'mean_return': 0.0,
                'std_return': 0.0,
                'min_return': 0.0,
                'max_return': 0.0,
                'percentile_5': 0.0,
                'percentile_25': 0.0,
                'percentile_50': 0.0,
                'percentile_75': 0.0,
                'percentile_95': 0.0,
                'probability_profit': 0.0,
                'probability_loss': 0.0
            }
        
        # محاكاة إعادة ترتيب الصفقات
        simulated_returns = []
        base_pnls = [t.pnl for t in base_trades if t.pnl is not None]
        
        print(f"Using {len(base_pnls)} trades for simulation")
        
        for i in range(simulations):
            # إعادة ترتيب عشوائي للصفقات
            shuffled_pnls = np.random.permutation(base_pnls)
            
            # محاكاة العوائد
            total_pnl = np.sum(shuffled_pnls)
            total_return = (total_pnl / config.initial_capital) * 100
            simulated_returns.append(total_return)
            
            if (i + 1) % 100 == 0:
                print(f"  Completed {i+1}/{simulations} iterations")
        
        returns_array = np.array(simulated_returns)
        
        stats = {
            'simulations': simulations,
            'mean_return': float(np.mean(returns_array)),
            'std_return': float(np.std(returns_array)),
            'min_return': float(np.min(returns_array)),
            'max_return': float(np.max(returns_array)),
            'percentile_5': float(np.percentile(returns_array, 5)),
            'percentile_25': float(np.percentile(returns_array, 25)),
            'percentile_50': float(np.percentile(returns_array, 50)),
            'percentile_75': float(np.percentile(returns_array, 75)),
            'percentile_95': float(np.percentile(returns_array, 95)),
            'probability_profit': float(np.sum(returns_array > 0) / len(returns_array)),
            'probability_loss': float(np.sum(returns_array < 0) / len(returns_array))
        }
        
        print(f"✅ Monte Carlo simulation completed")
        print(f"   Mean return: {stats['mean_return']:.2f}%")
        print(f"   Probability of profit: {stats['probability_profit']*100:.1f}%")
        
        return stats