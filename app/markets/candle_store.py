# app/market/candle_store.py
import pandas as pd
from collections import defaultdict
from typing import Dict, List
from app.markets.models import Candle

class CandleStore:
    def __init__(self, max_candles: int = 1000):
        self.max_candles = max_candles
        self._store: Dict[str, List[Candle]] = defaultdict(list)

    def add(self, candle: Candle):
        key = f"{candle.symbol}:{candle.timeframe}"
        self._store[key].append(candle)

        if len(self._store[key]) > self.max_candles:
            self._store[key] = self._store[key][-self.max_candles:]

    def to_dataframe(self, symbol: str, timeframe: str) -> pd.DataFrame:
        key = f"{symbol}:{timeframe}"
        candles = self._store.get(key, [])

        if not candles:
            return pd.DataFrame()

        data = [{
            "timestamp": c.open_time,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume
        } for c in candles]

        df = pd.DataFrame(data).set_index("timestamp")
        return df
