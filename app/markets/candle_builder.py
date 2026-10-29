# app/market/candle_builder.py
from datetime import datetime
from typing import Callable, Dict, Optional
from .models import Candle
from .timeframe import floor_time, next_close_time

class CandleBuilder:
    def __init__(self):
        self._candles: Dict[str, Candle] = {}
        self._on_close: Optional[Callable[[Candle], None]] = None

    def on_candle_close(self, callback: Callable[[Candle], None]):
        self._on_close = callback

    def process_tick(
        self,
        *,
        symbol: str,
        timeframe: str,
        price: float,
        volume: float,
        timestamp: datetime
    ):
        key = f"{symbol}:{timeframe}"
        open_time = floor_time(timestamp, timeframe)

        candle = self._candles.get(key)

        # 🟢 إنشاء شمعة جديدة
        if candle is None or candle.open_time != open_time:
            if candle:
                self._close_candle(key)

            self._candles[key] = Candle(
                symbol=symbol,
                timeframe=timeframe,
                open_time=open_time,
                close_time=next_close_time(open_time, timeframe),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
            )
            return

        # 🔄 تحديث الشمعة الحالية
        candle.high = max(candle.high, price)
        candle.low = min(candle.low, price)
        candle.close = price
        candle.volume += volume

    def _close_candle(self, key: str):
        candle = self._candles.pop(key, None)
        if candle and self._on_close:
            self._on_close(candle)
