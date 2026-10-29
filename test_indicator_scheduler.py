# test_indicator_scheduler.py
from datetime import datetime, timedelta

from app.markets import indicator_scheduler , candle_builder



indicator_scheduler.register_indicators(
    symbol="BTCUSDT",
    timeframe="1m",
    indicators=[
        {"name": "ema", "params": {"period": 14}, "enabled": True},
        {"name": "rsi", "params": {"period": 14}, "enabled": True},
    ]
)

now = datetime.utcnow()

# ticks
candle_builder.process_tick(
    symbol="BTCUSDT", timeframe="1m",
    price=100, volume=1, timestamp=now
)

candle_builder.process_tick(
    symbol="BTCUSDT", timeframe="1m",
    price=105, volume=2, timestamp=now + timedelta(seconds=20)
)

# إغلاق الشمعة
candle_builder.process_tick(
    symbol="BTCUSDT", timeframe="1m",
    price=110, volume=1, timestamp=now + timedelta(seconds=61)
)

key = "BTCUSDT:1m"
print("RESULT CACHE:", indicator_scheduler.results_cache[key])
