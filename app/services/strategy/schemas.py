# app\services\strategy\schemas.py
from typing import Dict, List, Any, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator, validator
from enum import Enum
from datetime import datetime
from app.services.indicators.base import IndicatorConfig, IndicatorType

class ConditionType(str, Enum):
    """أنواع شروط الدخول والخروج"""
    INDICATOR_VALUE = "indicator_value"          # قيمة مؤشر
    INDICATOR_CROSSOVER = "indicator_crossover"  # تقاطع مؤشرين
    PRICE_CROSSOVER = "price_crossover"          # تقاطع سعر مع مؤشر
    VOLUME_CONDITION = "volume_condition"        # شرط حجم
    TIME_CONDITION = "time_condition"            # شرط زمني
    LOGICAL_AND = "logical_and"                  # AND منطقي
    LOGICAL_OR = "logical_or"                    # OR منطقي
    LOGICAL_NOT = "logical_not"                  # NOT منطقي

class Operator(str, Enum):
    """المعاملات الرياضية للشروط"""
    GREATER_THAN = ">"
    GREATER_THAN_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_EQUAL = "<="
    EQUAL = "=="
    NOT_EQUAL = "!="
    CROSSOVER_ABOVE = "cross_above"
    CROSSOVER_BELOW = "cross_below"
    TOUCHES = "touches"               
class PositionSide(str, Enum):
    """جهة المركز"""
    LONG = "long"
    SHORT = "short"
    BOTH = "both"

class Condition(BaseModel):
    """شرط فردي"""
    type: ConditionType
    operator: Operator
    left_value: Union[str, float]  # يمكن أن يكون اسم مؤشر أو قيمة رقمية
    right_value: Union[str, float]
    timeframe: Optional[str] = None  # إطار زمني محدد للشرط
    
    @field_validator('left_value', 'right_value')
    def validate_values(cls, v, info):
        if isinstance(v, str) and v.startswith('indicator:'):
            # التحقق من صيغة المؤشر: indicator:rsi أو indicator:macd.signal
            indicator_name = v.split(':')[1]
            if '.' in indicator_name:
                main, sub = indicator_name.split('.')
                # يمكن إضافة تحقق إضافي هنا
        return v

class CompositeCondition(BaseModel):
    """شرط مركب (AND/OR)

    ✅ إصلاح: كان النوع Literal["and","or"] فقط بينما كل الاستراتيجيات المدمجة
    والمقيّم (conditions.py) يستخدمون "logical_and"/"logical_or" — فتفشل
    كل استراتيجيات النظام المدمجة في التحقق! نقبل الصيغتين ونوحّدها داخلياً.
    """
    type: Literal["and", "or", "logical_and", "logical_or"]
    conditions: List[Union['CompositeCondition', Condition]]

    @validator('conditions')
    def validate_conditions(cls, v):
        if len(v) < 2:
            raise ValueError("Composite conditions must have at least 2 sub-conditions")
        return v

    @field_validator('type', mode='before')
    @classmethod
    def normalize_logical_type(cls, v):
        """توحيد logical_and→and و logical_or→or (نفس دلالات المقيّم)"""
        if v == "logical_and":
            return "and"
        if v == "logical_or":
            return "or"
        return v

class EntryRule(BaseModel):
    """قاعدة دخول"""
    name: str
    condition: Union[Condition, CompositeCondition]
    position_side: PositionSide = PositionSide.LONG
    weight: float = Field(1.0, ge=0.0, le=1.0)  # وزن القاعدة في اتخاذ القرار
    enabled: bool = True

class ExitRule(BaseModel):
    """قاعدة خروج"""
    name: str
    condition: Union[Condition, CompositeCondition]
    exit_type: Literal["stop_loss", "take_profit", "trailing_stop", "signal_exit"]
    value: Optional[float] = None  # قيمة للوقف أو جني الأرباح
    enabled: bool = True

class FilterRule(BaseModel):
    """قاعدة فلترة"""
    name: str
    condition: Union[Condition, CompositeCondition]
    action: Literal["allow", "block", "delay"]
    enabled: bool = True
    metadata: Optional[Dict[str, Any]] = None

    @field_validator('metadata', mode='before')
    @classmethod
    def ensure_metadata(cls, v):
        """تأكد أن metadata تكون dict إذا كانت None"""
        return v or {}

class RiskManagement(BaseModel):
    """إدارة المخاطر"""
    stop_loss_percentage: float = Field(2.0, ge=0.1, le=50.0)
    take_profit_percentage: float = Field(4.0, ge=0.1, le=100.0)
    trailing_stop_percentage: float = Field(1.0, ge=0.1, le=10.0)
    max_position_size: float = Field(0.1, ge=0.01, le=1.0)  # نسبة من رأس المال
    max_daily_loss: float = Field(5.0, ge=0.1, le=50.0)    # نسبة مئوية
    max_concurrent_positions: int = Field(3, ge=1, le=10)

class StrategyConfig(BaseModel):
    """تكوين الإستراتيجية الكامل"""
    # معلومات أساسية
    name: str
    version: str = "1.0.0"
    description: Optional[str] = None
    author: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # إعدادات التداول
    base_timeframe: str = "1h"  # الإطار الزمني الأساسي
    allowed_timeframes: List[str] = ["1h", "4h", "1d"]
    position_side: PositionSide = PositionSide.LONG
    initial_capital: float = 10000.0
    commission_rate: float = Field(0.001, ge=0.0, le=0.05)  # 0.1%
    
    # المؤشرات المستخدمة
    indicators: List[IndicatorConfig] = Field(default_factory=list)
    
    # قواعد التداول
    entry_rules: List[EntryRule] = Field(default_factory=list)
    exit_rules: List[ExitRule] = Field(default_factory=list)
    filter_rules: List[FilterRule] = Field(default_factory=list)
    
    # إدارة المخاطر
    risk_management: RiskManagement = Field(default_factory=RiskManagement)
    
    # إعدادات متقدمة
    require_confirmation: bool = False  # هل تحتاج تأكيد من إطار زمني أعلى؟
    confirmation_timeframe: Optional[str] = None
    max_signals_per_day: Optional[int] = None
    
    # @validator('indicators')
    # def validate_indicators(cls, v):
    #     """التحقق من عدم وجود تعارض في أسماء المؤشرات"""
    #     names = [ind.name for ind in v]
    #     if len(names) != len(set(names)):
    #         raise ValueError("Duplicate indicator names found")
    #     return v
    
    @validator('indicators')
    def validate_indicators(cls, v):
        """التحقق من عدم وجود تعارض (IDs must be unique, Names only need uniqueness if ID is missing)."""
        # 1. Check ID uniqueness
        ids = [ind.id for ind in v if ind.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate indicator IDs found. IDs must be unique.")
        
        # 2. Check Name uniqueness for items WITHOUT IDs (Legacy/Standard support)
        names_without_ids = [ind.name for ind in v if ind.id is None]
        if len(names_without_ids) != len(set(names_without_ids)):
            raise ValueError(
                "Duplicate indicator names found for indicators without IDs. "
                "Please use 'id' field if you want multiple instances of the same indicator."
            )
        return v
    @validator('entry_rules')
    def validate_entry_rules(cls, v, values):
        """التحقق من وجود قواعد دخول"""
        if not v:
            raise ValueError("At least one entry rule is required")
        
        # التحقق من أن مجموع الأوزان لا يتجاوز 1.0
        total_weight = sum(rule.weight for rule in v if rule.enabled)
        if total_weight > 1.0:
            raise ValueError(f"Total weight of entry rules ({total_weight}) exceeds 1.0")
        
        return v

class StrategyMetadata(BaseModel):
    """بيانات وصفية للإستراتيجية"""
    id: str  # معرف فريد
    name: str
    version: str
    description: Optional[str]
    performance_score: float = 0.0
    last_backtest_date: Optional[datetime] = None
    is_active: bool = True
    tags: List[str] = Field(default_factory=list)