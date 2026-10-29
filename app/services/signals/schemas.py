from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime

class SignalResult(BaseModel):
    symbol: str
    timeframe: str
    market: str
    signal: Optional[str]  # buy | sell | None
    candle_time: datetime
    indicators: Dict[str, float]
    conditions_met: List[str]
