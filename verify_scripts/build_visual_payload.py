#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""توليد الحمولة البصرية الشاملة للاختبار HTML — كل الاستراتيجيات الثلاث."""
import json
import os
import sys
from datetime import datetime, timezone

# ✅ مسارات نسبية — تعمل من أي مكان
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.environ.get("NEW_SRC") or os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT)
_EVIDENCE = os.path.join(_PROJECT, "evidence")
_OUT = os.path.join(_HERE, "visual_full_payload.json")

from app.services.indicators.overlays import compute_overlays


def build(symbol, timeframe, candles):
    params = {
        "zzfib": {"mode": "tradingview", "depth": 12, "deviation": 20, "backstep": 3},
        "zzfib_e2e": {"mode": "luxalgo", "length": 100},
        "zzfib_e2e_trendy": {"mode": "luxalgo", "length": 100,
                             "trend_periods": [7, 15, 25], "trend_confirm": "majority",
                             "trend_gate": ["s1", "s2", "s3"]},
        "trend_fractal": {"periods": [7, 15, 25]},
    }
    res = compute_overlays(candles, types=["zzfib_e2e", "zzfib_e2e_trendy", "trend_fractal"],
                           params=params)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "candles": candles,
        "overlays": res["overlays"],
        "time_from": res["time_from"],
        "time_to": res["time_to"],
    }


def main():
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "core_spec": "ROUND34-unified-zigzag-fib", "cases": []}

    # Case 1: APPBUSDT 5m (بلاغ المستخدم — الإشارة 31/10 07:40 الرياض)
    candles = json.load(open(os.path.join(_EVIDENCE, "APPBUSDT_5m_week.json")))
    candles = [{"time": c["timestamp"], "open": c["open"], "high": c["high"],
                "low": c["low"], "close": c["close"], "volume": c["volume"]} for c in candles]
    out["cases"].append(build("APPBUSDT", "5m", candles))

    # Case 2: BTC 1m golden
    btc = json.load(open(os.path.join(_EVIDENCE, "golden_btc_1m.json")))
    out["cases"].append(build("BTCUSDT", "1m", btc))

    json.dump(out, open(_OUT, "w"), ensure_ascii=False)
    print(f"saved → {_OUT}")
    for c in out["cases"]:
        o = c["overlays"]
        e2e = o.get("zzfib_e2e") or {}
        tr = o.get("zzfib_e2e_trendy") or {}
        print(f"  {c['symbol']} {c['timeframe']}: candles={len(c['candles'])} "
              f"e2e_legs={len(e2e.get('legs') or [])} e2e_ranges={len(e2e.get('ranges') or [])} "
              f"trendy_signals={len(tr.get('signals') or [])}")


if __name__ == "__main__":
    main()
