# services/market/candle_tracker.py
class CandleTracker:
    def __init__(self):
        self.last_candle_time = {}

    def is_new_candle(self, symbol, timeframe, candle_time):
        key = f"{symbol}:{timeframe}"
        if key not in self.last_candle_time:
            self.last_candle_time[key] = candle_time
            return False

        if candle_time > self.last_candle_time[key]:
            self.last_candle_time[key] = candle_time
            return True

        return False
