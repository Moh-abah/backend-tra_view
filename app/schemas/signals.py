# trading_backend/app/schemas/signals.py
from pydantic import BaseModel
from typing import List, Dict, Any

class SignalRequest(BaseModel):
    symbol: str
    timeframe: str
    market: str = "crypto"
    days: int = 30
    indicators: List[Dict[str, Any]]
