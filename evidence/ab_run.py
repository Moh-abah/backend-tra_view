#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B على نفس الشموع حرفياً — القديم (merge_extract) مقابل الجديد (round34)."""
import json
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
BT = json.load(open(os.path.join(ROOT, "tmp_drive", "bt_chart.json")))
ov_old_data = BT["overlays"]["overlays"]
candles = [
    {"time": c.get("timestamp"), "open": c.get("open"), "high": c.get("high"),
     "low": c.get("low"), "close": c.get("close"), "volume": c.get("volume")}
    for c in BT["visual_candles"] if isinstance(c, dict)
]
print("candles:", len(candles))

WHICH = sys.argv[1]  # old | new
OUT = os.path.join(ROOT, f"ab_{WHICH}.json")

if WHICH == "old":
    sys.path.insert(0, os.path.join(ROOT, "tmp_drive", "merge_extract"))
else:
    sys.path.insert(0, os.path.join(ROOT, "round34"))

from app.services.indicators.overlays import zigzag_fib, auto_fib_retracement  # noqa: E402
from app.services.indicators.overlays_zlf_e2e import zigzag_fib_e2e  # noqa: E402
from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy  # noqa: E402
from app.services.indicators.trend_fractals import auto_trendlines_fractal  # noqa: E402

out = {}
out["zzfib_tv"] = zigzag_fib(candles, mode="tradingview", depth=12, deviation=20, backstep=3)
out["zzfib_e2e"] = zigzag_fib_e2e(candles, mode="luxalgo", length=100)
out["zzfib_e2e_trendy"] = zigzag_fib_e2e_trendy(
    candles, mode="luxalgo", length=100, trend_periods=[7, 15, 25],
    trend_confirm="majority", trend_gate=["s1", "s2", "s3"])
out["trend_fractal"] = auto_trendlines_fractal(candles, periods=[7, 15, 25])
out["fib"] = auto_fib_retracement(candles)

json.dump(out, open(OUT, "w"), ensure_ascii=False)
print(f"saved {OUT}")
for k, v in out.items():
    keys = list(v.keys())[:8]
    print(f"  {k}: {keys}")
