#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EBREAK1 خط الأساس: إعادة إنتاج أعمدة البطل 10001493 على نسخة درايف الجديدة.

يقارن 26 عمود ind_* بت-بت مقابل gold-mc1-structstrict/audit/local_series.pkl
(المتجمّد من الجلسة السابقة والمطابق حيًا للبطل #10001493).
"""
import json, pickle, sys, os
import pandas as pd

APP = "/home/z/my-project/trading-system/ebreak-reclaim/download/extracted"
sys.path.insert(0, APP)

from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
    zigzag_fib_e2e_trendy_quantum_ema,
)

THETA = "/home/z/my-project/trading-system/gold-mc1-structstrict/audit/theta_15m.json"
PKL = "/home/z/my-project/trading-system/gold-mc1-structstrict/audit/local_series.pkl"

CHAMPION_PARAMS = dict(
    mode="luxalgo", length=226,
    trend_periods=[7, 15, 25], trend_confirm="majority",
    trend_gate=["s1", "s2", "s3"], zone_gate=["s1", "s2", "s3"],
    ema_lengths=[50, 100, 200, 350, 500], ema_resolution="60",
    ema_source="close", ema_offset=0, ema_gate=["s1", "s2", "s3"],
    zone_exit_resolution="5m", zone_exit_length=113,
    struct_reversal_pct=22,
)

def main():
    raw = json.load(open(THETA))
    df = pd.DataFrame(raw, columns=[
        "time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_volume",
        "ignore", "confirm"])
    print(f"candles: {len(df)}")
    res = zigzag_fib_e2e_trendy_quantum_ema(df, **CHAMPION_PARAMS)
    ser = res["series"]
    print(f"series columns: {len(ser)}")

    frozen = pickle.load(open(PKL, "rb"))
    fser = frozen["series"]
    print(f"frozen columns: {len(fser)}")

    bad = []
    for col, arr in fser.items():
        key = col[len("ind_"):] if col.startswith("ind_") else col
        mine = ser.get(key)
        if mine is None:
            bad.append((col, "MISSING")); continue
        if len(mine) != len(arr):
            bad.append((col, f"LEN {len(mine)} != {len(arr)}")); continue
        diffs = 0
        for i, (a, b) in enumerate(zip(arr, mine)):
            av = None if (a is None or (isinstance(a, float) and a != a)) else float(a)
            bv = None if (b is None or (isinstance(b, float) and b != b)) else float(b)
            if av is None and bv is None:
                continue
            if av is None or bv is None or (av != bv and abs(av - bv) > 0):
                diffs += 1
                if diffs <= 2:
                    bad.append((col, f"i={i} frozen={av} mine={bv}"))
        if diffs:
            bad.append((col, f"total diffs={diffs}"))
    if bad:
        print("BIT-BIT MISMATCHES:")
        for x in bad[:30]:
            print("  ", x)
        print("VERDICT: BASELINE BROKEN")
        return 1
    print(f"VERDICT: BASELINE BIT-BIT IDENTICAL ({len(fser)} columns × {len(df)} candles)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
