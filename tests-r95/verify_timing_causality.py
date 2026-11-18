#!/usr/bin/env python3
"""verify_timing_causality.py — تحقق زمني عميق من إسقاط أحداث HTF.

يثبت لكل حدث خروج/دخول HTF:
  1) الشمعة القاعدة الحاملة للعلم إغلاقها >= إغلاق شمعة HTF التي أكدت الحدث
     (t[base_bar] + base_step >= htf_close_time) — لا استشراف إطلاقاً.
  2) الشمعة القاعدة الحالية هي «أول» شمعة ترى الحدث (السابقة لها لا تراه).
  3) لا حدثين على نفس الشمعة القاعدة (تداخل مستحيل).
  4) توزيع التأخير (بالشموع) بين إغلاق HTF وأول شمعة قاعدة رائية.
"""
import sys
from pathlib import Path

NEW_ROOT = Path("/home/z/drive-download/backend_PRO95_extracted")
sys.path.insert(0, str(NEW_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.indicators.overlays_zone_exit_mtf import compute_zone_exit_mtf  # noqa: E402


def main():
    df = pd.read_parquet(NEW_ROOT / "data/history/SOLUSDT_15m.parquet")
    # نافذة 2023 كاملة
    s = pd.Timestamp("2023-01-01", tz="UTC").timestamp() * 1000
    e = pd.Timestamp("2024-01-01", tz="UTC").timestamp() * 1000
    df = df[(df["time"] >= s) & (df["time"] <= e)]
    candles = [
        {"time": int(r.time), "open": float(r.open), "high": float(r.high),
         "low": float(r.low), "close": float(r.close)}
        for r in df.itertuples()
    ]
    t = np.array([c["time"] for c in candles], dtype=np.int64)
    base_step = 900_000

    all_ok = True
    for res in ("60", "240", "1D"):
        zx = compute_zone_exit_mtf(candles, resolution=res, length=100)
        if zx is None:
            print(f"[{res}] تعذّر الحساب!")
            all_ok = False
            continue
        meta = zx["meta"]
        events = zx["events"]
        delays = []
        bad = 0
        seen_base_bars = set()
        for ev in events:
            i0, hc = ev["base_bar"], ev["htf_close_time"]
            # 1) السببية: إغلاق الشمعة القاعدة >= إغلاق HTF
            if not (t[i0] + base_step >= hc):
                bad += 1
            # 2) «أول» شمعة رائية: الشمعة السابقة لا ترى الحدث
            if i0 > 0 and t[i0 - 1] + base_step >= hc:
                bad += 1
            # 3) لا تداخل
            if i0 in seen_base_bars:
                bad += 1
            seen_base_bars.add(i0)
            delays.append(int((t[i0] + base_step - hc) // base_step))
        counts = meta["counts"]
        n_ev = len(events)
        print(f"[{res:>3}] htf_bars={meta['htf_bars']:,} · أحداث enter={counts['htf_zone_enters']} "
              f"exit={counts['htf_zone_exits']} · مسقطة enter={counts['mapped_enters']} "
              f"exit={counts['mapped_exits']} · مخالفات={bad}")
        if delays:
            print(f"       التأخير بالشموع (إغلاق HTF → أول شمعة رائية): "
                  f"min={min(delays)} max={max(delays)} avg={sum(delays)/len(delays):.2f}")
        if bad or n_ev != counts["mapped_enters"] + counts["mapped_exits"]:
            all_ok = False
        # العلم مسقط على شموع موجودة فعلاً في الأعمدة
        n_flag_exit = sum(1 for v in zx["zone_exit"] if v > 0)
        n_flag_enter = sum(1 for v in zx["zone_enter"] if v > 0)
        if n_flag_exit != counts["mapped_exits"] or n_flag_enter != counts["mapped_enters"]:
            print(f"       ❌ عدد الأعلام لا يطابق الأحداث: {n_flag_exit}/{counts['mapped_exits']}")
            all_ok = False

    print("\nTIMING_CAUSALITY:", "ALL_OK" if all_ok else "FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
