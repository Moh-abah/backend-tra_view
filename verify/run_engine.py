#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تشغيل المؤشر (قبل أو بعد التعديل) على بيانات البطل + تفريغ السلاسل."""
import json, pickle, sys

APP = sys.argv[1]
OUT = sys.argv[2]
sys.path.insert(0, APP)
import pandas as pd
from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
    zigzag_fib_e2e_trendy_quantum_ema,
)

PARAMS = dict(
    mode="luxalgo", length=226,
    trend_periods=[7, 15, 25], trend_confirm="majority",
    trend_gate=["s1", "s2", "s3"], zone_gate=["s1", "s2", "s3"],
    ema_lengths=[50, 100, 200, 350, 500], ema_resolution="60",
    ema_source="close", ema_offset=0, ema_gate=["s1", "s2", "s3"],
    zone_exit_resolution="5m", zone_exit_length=113,
    struct_reversal_pct=22,
)

raw = json.load(open("/home/z/my-project/trading-system/gold-mc1-structstrict/audit/theta_15m.json"))
df = pd.DataFrame(raw, columns=[
    "time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades", "taker_volume",
    "ignore", "confirm"])
res = zigzag_fib_e2e_trendy_quantum_ema(df, **PARAMS)
ser = {k: v for k, v in (res.get("series") or {}).items()}
print(f"[{OUT}] columns={len(ser)} candles={len(df)}")
pickle.dump({"series": ser, "ema_break": res.get("ema_break")}, open(OUT, "wb"))
