from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum

class FilterType(str, Enum):
    """أنواع الفلترة"""
    MARKET = "market"           # فلترة السوق
    SYMBOL = "symbol"           # فلترة الرموز
    INDICATOR = "indicator"     # فلترة المؤشرات
    USER = "user"               # فلترة معلمات المستخدم
    COMPOSITE = "composite"     # فلترة مركبة

class FilterOperator(str, Enum):
    """معاملات الفلترة"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_THAN_EQUAL = "greater_than_equal"
    LESS_THAN = "less_than"
    LESS_THAN_EQUAL = "less_than_equal"
    BETWEEN = "between"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES_PATTERN = "matches_pattern"

class FilterCondition(BaseModel):
    """شرط فلترة فردي"""
    field: str
    operator: FilterOperator
    value: Any
    value_type: str = "auto"  # auto, string, number, boolean
    
    @validator('value')
    def validate_value(cls, v, values):
        operator = values.get('operator')
        
        # التحقق من صحة القيمة حسب المعامل
        if operator in [FilterOperator.BETWEEN] and not isinstance(v, list):
            raise ValueError(f"Value for operator '{operator}' must be a list")
        
        if operator in [FilterOperator.IN, FilterOperator.NOT_IN] and not isinstance(v, list):
            raise ValueError(f"Value for operator '{operator}' must be a list")
        
        return v

class FilterRule(BaseModel):
    """قاعدة فلترة"""
    name: str
    type: FilterType
    conditions: List[FilterCondition]
    enabled: bool = True
    weight: float = Field(1.0, ge=0.0, le=1.0)  # وزن القاعدة
    description: Optional[str] = None

class CompositeFilter(BaseModel):
    """فلتر مركب (AND/OR)"""
    type: str  # "and", "or"
    filters: List[Union['CompositeFilter', FilterRule]]
    description: Optional[str] = None
    
    @validator('filters')
    def validate_filters(cls, v):
        if len(v) < 2:
            raise ValueError("Composite filter must have at least 2 filters")
        return v

class FilterCriteria(BaseModel):
    """معايير الفلترة"""
    market: str = "crypto"
    symbol_pattern: Optional[str] = None  # نمط الرموز (مثل *USDT)
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_volume: Optional[float] = None
    min_volume_24h: Optional[float] = None
    max_volatility: Optional[float] = None  # تقلبات عالية
    required_indicators: Optional[List[str]] = None  # مؤشرات مطلوبة
    
    # فلاتر المؤشرات
    indicator_filters: Optional[Dict[str, Dict[str, Any]]] = None
    
    # فلاتر المستخدم
    user_preferences: Optional[Dict[str, Any]] = None
    
    # فلاتر مخصصة
    custom_filters: Optional[List[FilterRule]] = None
    composite_filter: Optional[CompositeFilter] = None
    
    # حدود النتائج
    limit: int = Field(50, ge=1, le=1000)
    offset: int = 0
    sort_by: Optional[str] = None
    sort_order: str = "desc"  # asc, desc
    
    class Config:
        json_schema_extra = {
            "example": {
                "market": "crypto",
                "symbol_pattern": "*USDT",
                "min_volume_24h": 1000000,
                "max_price": 50000,
                "required_indicators": ["rsi", "macd"],
                "indicator_filters": {
                    "rsi": {"min": 30, "max": 70},
                    "macd": {"signal": "bullish"}
                },
                "limit": 20
            }
        }

class FilterResult(BaseModel):
    """نتيجة الفلترة"""
    symbols: List[str]
    total_count: int
    filtered_count: int
    filtered_symbols: List[Dict[str, Any]]  # الرموز مع بيانات إضافية
    criteria: FilterCriteria
    execution_time_ms: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)