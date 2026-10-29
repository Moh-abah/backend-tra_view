# app/market/timeframe.py
from datetime import datetime, timedelta

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

def floor_time(ts: datetime, timeframe: str) -> datetime:
    seconds = TIMEFRAME_SECONDS[timeframe]
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.fromtimestamp(floored)

def next_close_time(open_time: datetime, timeframe: str) -> datetime:
    return open_time + timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
