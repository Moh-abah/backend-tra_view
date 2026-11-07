# -*- coding: utf-8 -*-
"""
ROUND26 — اختبار الإصلاح (قبل/بعد) على نفس شموع RUNEUSDT 1m الخام
1) المحرك القديم (ROUND22) مقابل المحرك المصلح (ROUND26) على نفس المدخلات
2) حالة المستخدم 17:34: S2 (خاطئة) → S1 (صحيحة)؟
3) لا إشارة أبداً بمرجع خارج عمر نطاقها بعد الإصلاح
4) جدول تغيّر كل الإشارات + سلامة البنية (نطاقات/أعمدة/أسماء)
"""
import json
import os
import importlib.util
from datetime import datetime, timezone, timedelta

OUT = "/home/z/my-project/download/ROUND26-RANGE-LIFE-REF/evidence"
K3 = timezone(timedelta(hours=3))


def t3(ms):
    if ms is None:
        return "—"
    return datetime.fromtimestamp(int(ms) / 1000, tz=K3).strftime("%m-%d %H:%M")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


OLD = load("/home/z/my-project/download/ROUND22-ZLF-E2E/app/services/indicators/overlays_zlf_e2e.py", "eng_old")
NEW = load("/home/z/my-project/download/ROUND26-RANGE-LIFE-REF/app/services/indicators/overlays_zlf_e2e.py", "eng_new")


def sig_map(eng):
    return {s["bar"]: s for s in eng["signals"] if s.get("side") == "liquidity"}


def main():
    candles = json.load(open(f"{OUT}/raw_candles_1m.json"))
    print(f"الشموع: {len(candles)} ({t3(candles[0]['time'])} → {t3(candles[-1]['time'])})")

    old = OLD.zigzag_fib_e2e(candles)
    new = NEW.zigzag_fib_e2e(candles)

    om, nm = sig_map(old), sig_map(new)
    print(f"إشارات: قبل={len(om)} · بعد={len(nm)} · نطاقات: قبل={len(old['ranges'])} بعد={len(new['ranges'])}")

    # --- 1) حالة المستخدم 17:34 ---
    print()
    print("=== حالة المستخدم: نطاق ولده 11-03 17:08 ===")
    # نجد نطاق الولادة 17:08 في المحرك الجديد
    tgt = None
    for s in nm.values():
        if t3(s["range_anchor"]["time"]) == "11-03 17:08":
            if t3(s["time"]) == "11-03 17:34":
                tgt = s
    # قبل
    before = None
    for s in om.values():
        if t3(s["time"]) == "11-03 17:34" and s.get("ref_vol") and abs(s["ref_vol"] - 72790.3) < 1:
            before = s
    if before:
        print(f"  قبل (ROUND22): {t3(before['time'])} → {before['signal'].split()[-1]} · "
              f"V={before['volume']} · المرجع@{t3(before['ref_time'])} V={before['ref_vol']} H={before['ref_high']} (خارج النطاق!)")
    if tgt:
        G = candles[tgt["bar"]]
        print(f"  بعد (ROUND26): {t3(tgt['time'])} → {tgt['signal'].split()[-1]} · "
              f"V={tgt['volume']} · المرجع@{t3(tgt['ref_time'])} V={tgt['ref_vol']} H={tgt['ref_high']} (داخل عمر النطاق)")
        ok = tgt["signal"].endswith("S1")
        print(f"  ⇒ التحول: S2 → {tgt['signal'].split()[-1]}  {'✅ كما توقع صاحب القرار' if ok else '❌'}")

    # --- 2) صفر مراجع خارج عمر النطاق ---
    print()
    bad_new = 0
    for s in nm.values():
        rb = s.get("ref_bar")
        ab = new["ranges"][s["range_index"]]["anchor"]["bar"]
        if rb is not None and rb < ab:
            bad_new += 1
    bad_old = 0
    for s in om.values():
        rb = s.get("ref_bar")
        ab = old["ranges"][s["range_index"]]["anchor"]["bar"]
        if rb is not None and rb < ab:
            bad_old += 1
    print(f"=== إشارات بمرجع خارج عمر النطاق: قبل={bad_old}/{len(om)} · بعد={bad_new}/{len(nm)} "
          f"{'✅' if bad_new == 0 else '❌'}")

    # --- 3) جدول تغيّر التصنيفات ---
    print()
    changes = []
    for bar, ns in nm.items():
        os_ = om.get(bar)
        ocell = os_["signal"].split("S")[-1] if os_ else "—"
        ncell = ns["signal"].split("S")[-1]
        if ocell != ncell:
            changes.append((bar, os_, ns))
    disappeared = [om[b] for b in om if b not in nm]
    appeared = [nm[b] for b in nm if b not in om]
    print(f"=== تغيّر التصنيف: {len(changes)} · اختفت: {len(disappeared)} · ظهرت جديدة: {len(appeared)}")
    rows = []
    for bar, os_, ns in changes:
        row = {
            "time": t3(ns["time"]),
            "before": os_["signal"].split()[-1] if os_ else "—",
            "after": ns["signal"].split()[-1],
            "volume": ns["volume"],
            "ref_before": ({"t3": t3(os_["ref_time"]), "vol": os_["ref_vol"], "high": os_["ref_high"]} if os_ else None),
            "ref_after": {"t3": t3(ns["ref_time"]), "vol": ns["ref_vol"], "high": ns["ref_high"]},
        }
        rows.append(row)
        print(f"  {row['time']}: {row['before']} → {row['after']} | V={row['volume']:.0f} | "
              f"مرجع: {(row['ref_before']['t3'] + '(' + format(row['ref_before']['vol'], '.0f') + ')') if row['ref_before'] else '—'} → "
              f"{row['ref_after']['t3']}({row['ref_after']['vol']:.0f})")
    for s in disappeared:
        print(f"  اختفت: {t3(s['time'])} {s['signal'].split()[-1]} (V={s['volume']:.0f})")
    for s in appeared:
        print(f"  ظهرت: {t3(s['time'])} {s['signal'].split()[-1]} (V={s['volume']:.0f})")

    # --- 4) تطابق آخر إشارتين بعد الإصلاح (سؤال المستخدم) ---
    print()
    last2 = sorted(nm.values(), key=lambda s: s["bar"])[-2:]
    print("=== آخر إشارتين بعد الإصلاح (RUNEUSDT 1m) ===")
    for s in last2:
        G = candles[s["bar"]]
        print(f"  {t3(s['time'])} → {s['signal'].split()[-1]} | V={s['volume']:.0f} | "
              f"المرجع@{t3(s['ref_time'])} H={s['ref_high']} V={s['ref_vol']:.0f} | "
              f"ولادة النطاق@{t3(s['range_anchor']['time'])}")

    # --- 5) سلامة البنية ---
    print()
    ok_series = set(new["series"].keys()) >= set(old["series"].keys())
    added = sorted(set(new["series"].keys()) - set(old["series"].keys()))
    ok_added = added == ["zzfe_anchor", "zzfe_range_index"]
    ok_len = all(len(new["series"][k]) == len(candles) for k in new["series"])
    print(f"=== سلامة البنية: الأعمدة القديمة كلها محفوظة: {ok_series} · المضاف حرفياً: {added} "
          f"({ok_added}) · أطوال صحيحة: {ok_len} · "
          f"spec: {new['spec']} · engine: {new['engine']}")

    # حفظ الأدلة
    json.dump({
        "counts": {"before": len(om), "after": len(nm), "ranges_before": len(old["ranges"]),
                   "ranges_after": len(new["ranges"])},
        "out_of_range_ref": {"before": bad_old, "after": bad_new},
        "target_case": {
            "before": ({"t3": t3(before["time"]), "cell": before["signal"].split()[-1],
                        "ref_t3": t3(before["ref_time"]), "ref_vol": before["ref_vol"],
                        "ref_high": before["ref_high"]} if before else None),
            "after": ({"t3": t3(tgt["time"]), "cell": tgt["signal"].split()[-1],
                       "ref_t3": t3(tgt["ref_time"]), "ref_vol": tgt["ref_vol"],
                       "ref_high": tgt["ref_high"]} if tgt else None),
        },
        "classification_changes": rows,
        "disappeared": [{"t3": t3(s["time"]), "cell": s["signal"].split()[-1], "volume": s["volume"]} for s in disappeared],
        "appeared": [{"t3": t3(s["time"]), "cell": s["signal"].split()[-1], "volume": s["volume"]} for s in appeared],
        "last2_after": [{"t3": t3(s["time"]), "cell": s["signal"].split()[-1], "volume": s["volume"],
                         "ref_t3": t3(s["ref_time"]), "ref_vol": s["ref_vol"], "ref_high": s["ref_high"],
                         "anchor_t3": t3(s["range_anchor"]["time"])} for s in last2],
        "structure": {"old_columns_preserved": ok_series, "added_columns": added,
                      "added_columns_exact": ok_added, "series_lengths_ok": ok_len,
                      "spec": NEW.ZLF_E2E_SPEC, "engine": NEW.ZLF_E2E_ENGINE_NAME},
    }, open(f"{OUT}/before_after.json", "w"), ensure_ascii=False, indent=1)
    print("\nحُفظ الدليل: evidence/before_after.json")


if __name__ == "__main__":
    main()
