# app/api/chart_snapshot.py
from fastapi import APIRouter, Depends
from app.markets.indicator_scheduler import indicator_scheduler

router = APIRouter()

@router.get("/chart/snapshot/{symbol}")
async def chart_snapshot(
    symbol: str,
    timeframe: str = "1m"
):
    key = f"{symbol}:{timeframe}"

    if key not in indicator_scheduler.results_cache:
        return {
            "type": "snapshot",
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": [],
            "indicators": {}
        }

    data = indicator_scheduler.results_cache[key]

    return {
        "type": "snapshot",
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": data["candles"],      # آخر N شموع مغلقة فقط
        "indicators": data["indicators"] # مؤشرات محسوبة مسبقاً
    }
