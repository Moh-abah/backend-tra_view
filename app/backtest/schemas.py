# trading_backend\app\backtest\schemas.py
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime, date, timedelta, timezone
from enum import Enum
import pandas as pd
import numpy as np

class BacktestMode(str, Enum):
    """أنواع الباك-تيست"""
    STANDARD = "standard"           # باك-تيست قياسي
    WALK_FORWARD = "walk_forward"   # اختبار مشي للأمام
    MONTE_CARLO = "monte_carlo"     # محاكاة مونت كارلو
    STRESS_TEST = "stress_test"     # اختبار الإجهاد

class PositionType(str, Enum):
    """أنواع المراكز"""
    LONG = "long"
    SHORT = "short"

class Trade(BaseModel):
    """صفقة تداول"""
    id: str
    symbol: str
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    position_type: PositionType
    position_size: float  # كمية أو حجم المركز
    pnl: Optional[float] = None  # الربح/الخسارة
    pnl_percentage: Optional[float] = None
    commission: float = 0.0
    slippage: float = 0.0
    stop_loss: Optional[float]
    take_profit: Optional[float]
    exit_reason: Optional[str]  # سبب الخروج
    metadata: Dict[str, Any] = Field(default_factory=dict)

    pnl_percent: Optional[float] = Field(None, alias="pnl_percent")
    class Config:
        arbitrary_types_allowed = True
        
class BacktestConfig(BaseModel):
    """تكوين الباك-تيست"""
    # معلومات أساسية (name اختياري — يُولَّد تلقائياً إن لم يُرسل)
    name: Optional[str] = None
    description: Optional[str] = None
    mode: BacktestMode = BacktestMode.STANDARD

    # الإعدادات الزمنية (start_date اختياري — يُشتق من days إن لم يُحدد)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    days: Optional[int] = Field(None, ge=1, le=3650, description="بديل مريح لتحديد start_date: عدد الأيام للخلف من end_date")
    timeframe: str = "1d"

    # السوق والرموز
    market: str = "crypto"
    symbols: List[str] = Field(..., min_length=1)

    # الإستراتيجية

    strategy_config: Optional[Dict[str, Any]] = None
    # إدارة رأس المال
    initial_capital: float = Field(10000.0, gt=0)
    position_sizing: str = "fixed"  # fixed, percentage, kelly
    position_size_percent: float = Field(0.1, ge=0.01, le=1.0)
    max_positions: int = Field(3, ge=1, le=10)

    # التكاليف
    commission_rate: float = Field(0.001, ge=0.0, le=0.05)  # 0.1%
    slippage_percent: float = Field(0.001, ge=0.0, le=0.01)  # 0.1%

    # إدارة المخاطر
    stop_loss_percent: Optional[float] = Field(5.0, ge=0.1, le=50.0)
    take_profit_percent: Optional[float] = Field(10.0, ge=0.1, le=100.0)
    trailing_stop_percent: Optional[float] = Field(2.0, ge=0.1, le=10.0)
    max_daily_loss_percent: float = Field(5.0, ge=0.1, le=50.0)

    # إعدادات متقدمة
    enable_short_selling: bool = False
    enable_margin: bool = False
    leverage: float = Field(1.0, ge=1.0, le=10.0)
    require_confirmation: bool = False

    @model_validator(mode="before")
    @classmethod
    def accept_frontend_field_aliases(cls, data: Any) -> Any:
        """توافق العقود مع الفرونت (قبول الحقول البديلة بدل رفض الطلب 422):

        - symbol (str)            → symbols  ([symbol])
        - interval                → timeframe
        - strategy (str|dict)     → strategy_config  (str → {"name": str})
        - commission              → commission_rate
        - capital / balance       → initial_capital
        - name مفقود              → يُولَّد لاحقاً في derive_and_validate_dates
        """
        if not isinstance(data, dict):
            return data
        d = dict(data)

        if "symbols" not in d and d.get("symbol"):
            d["symbols"] = [d["symbol"]] if isinstance(d["symbol"], str) else list(d["symbol"])
        if "timeframe" not in d and d.get("interval"):
            d["timeframe"] = d["interval"]
        if "strategy_config" not in d and d.get("strategy") is not None:
            strategy = d["strategy"]
            if isinstance(strategy, str):
                d["strategy_config"] = {"name": strategy}
            elif isinstance(strategy, dict):
                d["strategy_config"] = strategy
        if "commission_rate" not in d and d.get("commission") is not None:
            commission = d["commission"]
            # يقبل قيمة نسبة (0.001) أو نسبة مئوية (0.1 = 10%؟ لا — نفترض أنها نفس المعنى)
            try:
                commission = float(commission)
                # إن أُرسلت كنسبة مئوية كبيرة (مثل 0.1 تعني 10%؟) — 0.1 كنسبة = 0.1% وهي ضمن الحد
                d["commission_rate"] = commission / 100.0 if commission > 0.05 else commission
            except (TypeError, ValueError):
                pass
        if "initial_capital" not in d and d.get("capital") is not None:
            try:
                d["initial_capital"] = float(d["capital"])
            except (TypeError, ValueError):
                pass
        return d

    @model_validator(mode="after")
    def derive_and_validate_dates(self):
        """اشتقاق التواريخ من days عند غيابها والتحقق من صحتها"""
        now = datetime.now(timezone.utc)
        if not self.name:
            # اسم تلقائي ودود عند غيابه (الفرونت القديم لا يرسله)
            self.name = f"Backtest {self.symbols[0] if self.symbols else 'Unknown'} {self.timeframe} {now.strftime('%Y-%m-%d %H:%M')}"
        if self.end_date is None:
            self.end_date = now
        elif self.end_date.tzinfo is None:
            self.end_date = self.end_date.replace(tzinfo=timezone.utc)
        if self.start_date is None:
            days = self.days if self.days else 30
            self.start_date = self.end_date - timedelta(days=days)
        elif self.start_date.tzinfo is None:
            self.start_date = self.start_date.replace(tzinfo=timezone.utc)
        if self.end_date <= self.start_date:
            raise ValueError("End date must be after start date")
        return self





class MonthlyReturnsStats(BaseModel):
    """إحصائيات العوائد الشهرية"""
    avg_monthly_return: float
    std_monthly_return: float
    best_month: Optional[str] = None
    worst_month: Optional[str] = None
    positive_months: int
    negative_months: int
    consistency_rate: float

class YearlyReturnsStats(BaseModel):
    """إحصائيات العوائد السنوية"""
    avg_yearly_return: float
    std_yearly_return: float
    best_year: Optional[str] = None
    worst_year: Optional[str] = None
    positive_years: int
    max_consecutive_positive: int
    max_consecutive_negative: int

class PnlDistribution(BaseModel):
    """توزيع الربح/الخسارة"""
    mean: float
    median: float
    std: float
    skewness: Optional[float] = None
    kurtosis: Optional[float] = None
    q1: float
    q3: float
    iqr: float
    outliers: Optional[List[float]] = None

class SymbolPerformance(BaseModel):
    """أداء رمز معين"""
    # الأساسية
    total_trades: int
    completed_trades: int
    open_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    
    # الأداء المالي
    gross_profit: float
    gross_loss: float
    net_profit: float
    total_invested: float
    avg_position_size: float
    
    # النسب
    win_rate: float
    profit_factor: Optional[float] = None
    avg_win: float
    avg_loss: float
    avg_rr_ratio: float
    
    # الإحصائيات
    best_trade: float
    worst_trade: float
    avg_pnl: float
    std_pnl: float
    sharpe_ratio: float
    
    # التوقيت
    avg_trade_duration_hours: float
    min_duration: float
    max_duration: float
    
    # المخاطرة
    max_drawdown_percent: float
    volatility_percent: float
    var_95: float
    cvar_95: float
    
    # تحليل متقدم
    expectancy: float
    kelly_criterion: Optional[float] = None
    system_quality_number: float
    
    # تحليل التوزيع (اختياري)
    monthly_distribution: Optional[Dict[str, int]] = None
    hourly_distribution: Optional[Dict[int, int]] = None
    pnl_distribution: Optional[PnlDistribution] = None
    
    # بيانات إضافية للرسم البياني (اختياري)
    _equity_curve: Optional[List[float]] = None
    _drawdown_curve: Optional[List[float]] = None







# class VisualCandle(BaseModel):
#     """شمعة مع جميع بيانات الرسم"""
#     timestamp: datetime
#     open: float
#     high: float
#     low: float
#     close: float
#     volume: float
    
#     # بيانات المؤشرات لهذه الشمعة
#     indicators: Dict[str, Optional[float]] = Field(default_factory=dict)
    
#     # حالة الاستراتيجية عند هذه الشمعة
#     strategy_decision: Optional[str] = None  # "BUY", "SELL", "HOLD"
#     triggered_rules: List[str] = Field(default_factory=list)  # القواعد المنشطة
#     confidence: Optional[float] = None
#     position_state: str = "NEUTRAL"  # "LONG", "SHORT", "NEUTRAL"
    
#     # بيانات الصفقة إذا كانت هذه شمعة دخول/خروج
#     trade_action: Optional[str] = None  # "ENTRY_LONG", "EXIT_LONG", etc.
#     trade_id: Optional[str] = None
#     trade_price: Optional[float] = None
#     trade_size: Optional[float] = None



class VisualCandle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    indicators: Dict[str, Optional[ Any]] = {}
    strategy_decision: Optional[str] = None
    triggered_rules: List[str] = []
    confidence: Optional[float] = None
    position_state: str = "NEUTRAL"
    
    # بيانات الصفقات
    trade_action: Optional[str] = None
    trade_id: Optional[str] = None
    trade_price: Optional[float] = None
    trade_size: Optional[float] = None
    
    # البيانات المالية
    account_balance: Optional[float] = None
    cumulative_pnl: Optional[float] = None
    position_size: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    current_pnl: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percentage: Optional[float] = None





    volume_bar: Optional[Dict[str, Any]] = None
    climax_point: Optional[Dict[str, Any]] = None
    

class BacktestResult(BaseModel):
    """نتيجة الباك-تيست"""
    # معلومات أساسية
    id: str
    config: BacktestConfig
    execution_time_seconds: float

    visual_candles: List[VisualCandle]  # كل الشموع مع بياناتها
    trade_points: List[Dict[str, Any]]  # نقاط الدخول والخروج المفصلة
    indicator_data: Dict[str, Dict[str, List[float]]]  # بيانات جميع المؤشرات
    

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # الأداء العام
    initial_capital: float
    final_capital: float
    total_pnl: float
    total_pnl_percent: float
    annual_return_percent: float
    
    # المقاييس الأساسية
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    profit_factor: Optional[float] = None
    expectancy: float
    
    # المخاطرة
    max_drawdown_percent: float
    max_drawdown_duration_days: int
    volatility_annual: float
    var_95: float
    cvar_95: float
    
    # العائد المعدل بالمخاطرة
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    
    # البيانات الخام
    equity_curve: List[float]
    drawdown_curve: List[float]
    monthly_returns: Dict[str, Any]  # يمكن أن تحتوي على إحصائيات
    yearly_returns: Dict[str, Any]   # يمكن أن تحتوي على إحصائيات
    
    # تحليل الصفقات
    avg_winning_trade: float
    avg_losing_trade: float
    largest_winning_trade: float
    largest_losing_trade: float
    avg_trade_duration_hours: float
    
    # ربحية الرموز
    symbols_performance: Dict[str, Dict[str, Any]]  # دعم أنواع متعددة
    
    # الكفاءة
    system_quality_number: float
    kelly_criterion: float
    
    # الحقول الاختيارية
    recovery_factor: Optional[float] = None
    ulcer_index: Optional[float] = None
    raw_data: Optional[Dict[str, Any]] = None
    
    # دالة تحويل للأنواع NumPy
    @field_validator('equity_curve', 'drawdown_curve', mode='before')
    @classmethod
    def convert_numpy_floats(cls, v):
        """تحويل numpy floats إلى Python floats"""
        if isinstance(v, list):
            return [float(x) if isinstance(x, (np.float32, np.float64, np.int32, np.int64)) else x for x in v]
        return v
    
    @field_validator('monthly_returns', 'yearly_returns', 'symbols_performance', mode='before')
    @classmethod
    def convert_numpy_in_dicts(cls, v):
        """تحويل numpy types في القواميس"""
        if isinstance(v, dict):
            return cls._recursive_convert(v)
        return v
    
    @classmethod
    def _recursive_convert(cls, obj):
        """تحويل متكرر للأنواع numpy"""
        if isinstance(obj, dict):
            return {k: cls._recursive_convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [cls._recursive_convert(item) for item in obj]
        elif isinstance(obj, (np.float32, np.float64)):
            return float(obj)
        elif isinstance(obj, (np.int32, np.int64)):
            return int(obj)
        else:
            return obj

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            np.float64: lambda v: float(v) if not np.isnan(v) else None,
            np.float32: lambda v: float(v) if not np.isnan(v) else None,
            np.int64: lambda v: int(v),
            np.int32: lambda v: int(v),
        }


# class BacktestResult(BaseModel):
#     """نتيجة الباك-تيست"""
#     # معلومات أساسية
#     id: str
#     config: BacktestConfig
#     execution_time_seconds: float
#     timestamp: datetime = Field(default_factory=datetime.utcnow)
    
#     # الأداء العام
#     initial_capital: float
#     final_capital: float
#     total_pnl: float
#     total_pnl_percent: float
#     annual_return_percent: float
#     sharpe_ratio: float
#     sortino_ratio: float
#     calmar_ratio: float
#     recovery_factor: float | None = None
#     ulcer_index: float | None = None
#     # المقاييس الأساسية
#     total_trades: int
#     winning_trades: int
#     losing_trades: int
#     win_rate: float
#     profit_factor: float
#     expectancy: float
    
#     # المخاطرة
#     max_drawdown_percent: float
#     max_drawdown_duration_days: int
#     volatility_annual: float
#     var_95: float  # Value at Risk 95%
#     cvar_95: float  # Conditional VaR 95%
    
#     # التفاصيل
#     trades: List[Trade]
#     equity_curve: List[float]
#     drawdown_curve: List[float]
#     monthly_returns: Dict[str, float]
#     yearly_returns: Dict[str, float]
    
#     # تحليل الصفقات
#     avg_winning_trade: float
#     avg_losing_trade: float
#     largest_winning_trade: float
#     largest_losing_trade: float
#     avg_trade_duration_hours: float
    
#     # ربحية الرموز
#     symbols_performance: Dict[str, Dict[str, float]]
    
#     # الكفاءة
#     system_quality_number: float  # SQN
#     kelly_criterion: float
    
#     # البيانات الخام
#     raw_data: Optional[Dict[str, Any]] = None
    
#     class Config:
#         arbitrary_types_allowed = True

class OptimizationResult(BaseModel):
    """نتيجة تحسين المعاملات"""
    parameter_sets: List[Dict[str, Any]]
    results: List[BacktestResult]
    best_parameters: Dict[str, Any]
    best_result: BacktestResult
    optimization_metrics: Dict[str, Any]