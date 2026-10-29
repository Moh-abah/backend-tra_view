from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal
from enum import Enum
import datetime as _dt
import json


def _json_default(obj: Any) -> Any:
    """محول آمن شامل لأي كائن غير قابل للتسلسل — يمنع انهيار البث الحي.

    كان البث الحي ينهار بالكامل على: TypeError: Object of type datetime is
    not JSON serializable — لأن كائنات datetime تتسرب داخل data/metadata.
    هذا المحول يعالج كل الحالات المعروفة بدلاً من تكرار الكارثة.
    """
    if isinstance(obj, (_dt.datetime, _dt.date, _dt.time)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, _dt.timedelta):
        return obj.total_seconds()
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, Enum):
        return obj.value
    try:  # numpy scalars (np.float64/int64/bool_...) — شائعة في بيانات المؤشرات
        import numpy as np

        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
    except ImportError:  # pragma: no cover
        pass
    return str(obj)


class StreamDataType(str, Enum):
    """أنواع البيانات في البث اللحظي"""
    PRICE = "price"              # بيانات السعر
    INDICATOR = "indicator"      # بيانات المؤشر
    CONDITION = "condition"      # حالة الشرط
    SIGNAL = "signal"            # إشارة تداول
    ENTRY_POINT = "entry_point"  # نقطة دخول
    STATUS = "status"           # حالة النظام
    FILTER = "filter"           # نتيجة فلترة

class StreamMessage(BaseModel):
    """رسالة البث اللحظي"""
    type: StreamDataType
    symbol: str
    timeframe: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None

    def to_json(self) -> str:
        """تحويل الرسالة إلى JSON — آمنة ضد datetime/numpy/Decimal وأي كائن غير متوقع"""
        return json.dumps(
            {
                "type": self.type,
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "timestamp": self.timestamp.isoformat(),
                "data": self.data,
                "metadata": self.metadata,
            },
            default=_json_default,
            ensure_ascii=False,
        )

class PriceStreamData(BaseModel):
    """بيانات السعر للبث"""
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: Optional[float] = None  # متوسط السعر المرجح بالحجم
    timestamp: datetime

class IndicatorStreamData(BaseModel):
    """بيانات المؤشر للبث"""
    name: str
    value: float
    previous_value: Optional[float] = None
    values: Optional[List[float]] = None  # آخر 20 قيمة للرسم
    metadata: Optional[Dict[str, Any]] = None
    signal: Optional[int] = None  # -1, 0, 1

class ConditionStreamData(BaseModel):
    """حالة شرط للبث"""
    name: str
    is_met: bool
    description: str
    current_value: float
    threshold: float
    conditions: List[Dict[str, Any]]  # الشروط الفرعية
    confidence: float = 1.0

class SignalStreamData(BaseModel):
    """إشارة تداول للبث"""
    type: str  # entry, exit
    action: str  # buy, sell, close
    strength: float
    price: float
    timestamp: datetime
    conditions: List[ConditionStreamData]
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

class EntryPointStreamData(BaseModel):
    """نقطة دخول للبث"""
    price: float
    stop_loss: float
    take_profit: float
    confidence: float
    risk_reward_ratio: float
    position_size: float  # نسبة من رأس المال
    timestamp: datetime