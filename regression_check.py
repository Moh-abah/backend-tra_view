# -*- coding: utf-8 -*-
"""ROUND26 — فحص انحدار شامل: 5m + عملات متعددة — صفر مراجع خارج عمر النطاق + لا أعطال."""
import json
import os
import sys
import time
import importlib.util
from datetime import datetime, timezone, timedelta

OUT = "/home/z/my-project/download/ROUND26-RANGE-LIFE-REF/evidence"
K3 = timezone(timedelta(hours=3))


def t3(ms):
    return datetime.fromtimestamp(int(ms) / 1000, tz=K3).strftime("%m-%d %H:%M")


spec = importlib.util.spec_from_file_location(
    "eng_new", "/home/z/my-project/download/ROUND26-RANGE-LIFE-REF/app/services/indicators/overlays_zlf_e2e.py")
NEW = importlib.util.module_from_spec(spec)
spec.loader.exec_module(NEW)

sys.path.insert(0, "/home/z/my-project/download/ROUND23-REAL-TEST")
from zlf_fetch import fetch_klines, klines_to_df, TF_MS  # noqa: E402

CASES = [
    ("RUNEUSDT", "5m", 2500),
    ("RUNEUSDT", "1m", 4500),
    ("BTCUSDT", "1m", 4500),
    ("ETHUSDT", "1m", 4500),
    ("SOLUSDT", "1m", 4500),
    ("BTCUSDT", "5m", 2500),
    ("LINKUSDT", "5m", 2500),
]

results = []
for sym, tf, need in CASES:
    now_ms = int(time.time() * 1000)
    kls = fetch_klines(sym, tf, need)
    df, _ = klines_to_df(kls, TF_MS[tf], now_ms)
    candles = [{"time": int(ts.timestamp() * 1000), "open": r["open"], "high": r["high"],
                "low": r["low"], "close": r["close"], "volume": r["volume"]}
               for ts, r in df.iterrows()]
    eng = NEW.zigzag_fib_e2e(candles)
    sigs = [s for s in eng["signals"] if s.get("side") == "liquidity"]
    bad = 0
    for s in sigs:
        rb = s.get("ref_bar")
        ab = eng["ranges"][s["range_index"]]["anchor"]["bar"]
        if rb is not None and rb < ab:
            bad += 1
    # سلامة سلاسل المرجع: عند وجود إشارة عند شمعة، يجب ref غير فارغ
    missing_ref = 0
    for s in sigs:
        if s.get("ref_vol") is None:
            missing_ref += 1
    ok = bad == 0 and missing_ref == 0
    results.append({"symbol": sym, "tf": tf, "candles": len(candles), "ranges": len(eng["ranges"]),
                    "signals": len(sigs), "out_of_range_ref": bad, "signals_missing_ref": missing_ref, "ok": ok})
    print(f"  {sym} {tf}: شموع={len(candles)} نطاقات={len(eng['ranges'])} إشارات={len(sigs)} · "
          f"مرجع-خارج-العمر={bad} · إشارة-بلا-مرجع={missing_ref} {'✅' if ok else '❌'}")

json.dump(results, open(f"{OUT}/regression.json", "w"), ensure_ascii=False, indent=1)
all_ok = all(r["ok"] for r in results)
print(f"\n⇒ نتيجة الانحدار الشامل: {'✅ كل الحالات سليمة' if all_ok else '❌ يوجد خلل'}")
