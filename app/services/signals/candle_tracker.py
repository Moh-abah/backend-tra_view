from datetime import datetime

class CandleStateTracker:
    def __init__(self):
        self._last_candle_time = {}

    def is_new_candle(self, symbol: str, timeframe: str, candle_time: datetime) -> bool:
        key = (symbol, timeframe)
        last_time = self._last_candle_time.get(key)

        if last_time is None or candle_time > last_time:
            self._last_candle_time[key] = candle_time
            return True

        return False
