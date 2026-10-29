# trading_backend/app/services/candle_aggregator.py
from datetime import datetime, timedelta
from collections import defaultdict

class CandleAggregator:
    def __init__(self):
        # تخزين الشمعة الحالية لكل رمز وفريم
        self.current_candles = defaultdict(dict)

    def add_tick(self, symbol: str, price: float, volume: float, timestamp: datetime, timeframe: str):
        """
        timeframe: '1m', '5m', '1h', '1d', ...
        """
        # تحويل timestamp إلى بداية الشمعة
        start_time = self.get_candle_start_time(timestamp, timeframe)

        candle = self.current_candles[symbol].get(timeframe)

        if candle is None or candle["start_time"] != start_time:
            # الشمعة السابقة انتهت
            completed_candle = candle
            # إنشاء شمعة جديدة
            candle = {
                "start_time": start_time,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume
            }
            self.current_candles[symbol][timeframe] = candle
            return completed_candle  # إذا كانت موجودة، نرسلها للخارج
        else:
            # تحديث الشمعة الحالية
            candle["high"] = max(candle["high"], price)
            candle["low"] = min(candle["low"], price)
            candle["close"] = price
            candle["volume"] += volume
            return None

    def get_candle_start_time(self, timestamp: datetime, timeframe: str) -> datetime:
        if timeframe.endswith('m'):
            minutes = int(timeframe[:-1])
            return timestamp.replace(second=0, microsecond=0) - timedelta(
                minutes=timestamp.minute % minutes)
        elif timeframe.endswith('h'):
            hours = int(timeframe[:-1])
            return timestamp.replace(minute=0, second=0, microsecond=0) - timedelta(
                hours=timestamp.hour % hours)
        elif timeframe.endswith('d'):
            return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # الافتراضي دقيقة
            return timestamp.replace(second=0, microsecond=0)
