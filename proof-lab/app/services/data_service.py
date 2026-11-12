# app/services/data_service.py — ساندبوكس إثبات R45
"""مزوّد بيانات اصطناعي حتمي (بلا شبكة) بعقد DataService الحقيقي:
get_historical(symbol=, timeframe=, market=, days=) → DataFrame.

* شموع حتمية (seed من الرمز) — نفس الرمز/الفريم يعطي نفس السلسلة دائماً.
* ساعة قابلة للتجميد عبر R45_TEST_CLOCK_EPOCH (نفس خطاف الكاش) — يسمح
  بإثبات «تحديث الرأس فقط» بدقة متناهية.
* كل استدعاء جلب يُسجَّل في FETCH_LOG (لإثبات عدد الجلبات الفعلي).
"""
from __future__ import annotations

import hashlib
import math
import os
import time
from typing import List

import pandas as pd

FETCH_LOG: List[dict] = []

_INTERVALS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400,
}


def _now() -> float:
    epoch = os.environ.get("R45_TEST_CLOCK_EPOCH")
    if epoch:
        try:
            return float(epoch)
        except ValueError:
            pass
    return time.time()


class DataService:
    def __init__(self, db=None):
        self.db = db

    async def get_historical(
        self, symbol=None, timeframe=None, market=None, days=None, **kwargs
    ) -> pd.DataFrame:
        symbol = str(symbol or "BTCUSDT").upper()
        timeframe = str(timeframe or "1h")
        days = max(1, int(days or 30))
        interval = _INTERVALS.get(timeframe, 3600)

        now = int(_now())
        start = now - days * 86400
        # محاذاة البداية للفاصل (مثل مزوّدي الأسواق الحقيقيين)
        start = (start // interval) * interval
        times = list(range(start, now, interval))

        seed = int(hashlib.md5(f"{market}:{symbol}:{timeframe}".encode()).hexdigest()[:8], 16)
        base = 40000.0 + (seed % 5000)

        rows = []
        price = base
        for i, t in enumerate(times):
            wave = math.sin((seed + i) * 0.017) * 0.012
            drift = math.sin((seed + i) * 0.0031) * 0.004
            ret = wave + drift
            open_ = price
            close_ = max(1.0, price * (1.0 + ret))
            high = max(open_, close_) * (1.0 + abs(wave) * 0.35 + 0.001)
            low = min(open_, close_) * (1.0 - abs(wave) * 0.35 - 0.001)
            vol = 100.0 + (i % 37) * 3.0
            rows.append(
                {
                    "time": int(t * 1000),  # ميلي ثانية مثل بينانس
                    "open": round(open_, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close_, 2),
                    "volume": round(vol, 3),
                }
            )
            price = close_

        FETCH_LOG.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "days": days,
                "candles": len(rows),
                "wall": time.time(),
            }
        )
        df = pd.DataFrame(rows)
        return df
