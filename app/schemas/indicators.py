"""
مخططات البيانات للشارت والمؤشرات
"""
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, validator

class Timeframe(str, Enum):
    SEC30 = "30s"
    MIN1 = "1m"
    MIN2 = "2m"
    MIN3 = "3m"
    MIN5 = "5m"
    MIN10 = "10m"
    MIN15 = "15m"
    MIN30 = "30m"
    HOUR1 = "1h"
    HOUR2 = "2h"
    HOUR3 = "3h"
    HOUR4 = "4h"
    HOUR6 = "6h"
    HOUR8 = "8h"
    HOUR12 = "12h"
    DAY1 = "1d"
    DAY2 = "2d"
    DAY3 = "3d"
    WEEK1 = "1w"
    WEEK2 = "2w"
    MONTH1 = "1M"



    
class MarketType(str, Enum):
    CRYPTO = "crypto"
    STOCKS = "stocks"
    FOREX = "forex"

class IndicatorType(str, Enum):
    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    SUPPORT = "support"
    SUPPORT_RESISTANCE = "support_resistance"

class IndicatorConfig(BaseModel):
    """تكوين المؤشر"""
    name: str = Field(..., description="اسم المؤشر")
    type: IndicatorType = Field(..., description="نوع المؤشر")
    params: Dict[str, Any] = Field(default_factory=dict, description="معاملات المؤشر")
    enabled: bool = Field(default=True, description="تفعيل المؤشر")
    display_name: Optional[str] = Field(None, description="اسم العرض")
    
    @validator('params')
    def validate_params(cls, v, values):
        """التحقق من صحة المعاملات"""
        name = values.get('name', '').lower()
        
        # قيود لكل مؤشر
        constraints = {
            'rsi': {'period': (5, 100), 'overbought': (50, 100), 'oversold': (0, 50)},
            'ema': {'period': (1, 500)},
            'macd': {'fast': (5, 50), 'slow': (10, 100), 'signal': (5, 50)},
            'bb': {'period': (5, 100), 'std': (1, 5)},
            'atr': {'period': (5, 100)},
        }
        
        if name in constraints:
            for param, (min_val, max_val) in constraints[name].items():
                if param in v and v[param] is not None:
                    if not min_val <= v[param] <= max_val:
                        raise ValueError(
                            f"Parameter {param} for {name} must be between {min_val} and {max_val}"
                        )
        return v

class ChartSubscription(BaseModel):
    """اشتراك الشارت"""
    symbol: str = Field(..., description="رمز التداول")
    timeframe: Timeframe = Field(default=Timeframe.MIN15, description="الإطار الزمني")
    market: MarketType = Field(default=MarketType.CRYPTO, description="نوع السوق")
    indicators: List[IndicatorConfig] = Field(default_factory=list, description="قائمة المؤشرات")

class CandleData(BaseModel):
    """بيانات الشمعة"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class IndicatorResult(BaseModel):
    """نتيجة المؤشر"""
    name: str
    values: List[Optional[float]]
    signals: Optional[List[int]] = None
    metadata: Dict[str, Any] = {}

class ChartData(BaseModel):
    """بيانات الشارت الكاملة"""
    symbol: str
    timeframe: Timeframe
    market: MarketType
    candles: List[CandleData]
    indicators: List[IndicatorResult]
    metadata: Dict[str, Any]

class PriceUpdate(BaseModel):
    """تحديث السعر الحي"""
    symbol: str
    price: float
    volume: float
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    change: Optional[float] = None