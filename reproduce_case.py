# -*- coding: utf-8 -*-
"""
ROUND26 — إعادة إنتاج حالة المستخدم بالضبط (قبل الإصلاح):
"الحمراء العملاقة 72,790 @ 15:23 خارج النطاق (الزقزاق ظهر ~17:09) — ومع ذلك صارت مرجعاً → S2 @ 17:33 بدل S1"
نجلب شموع RUNEUSDT 1m الخام من Binance ونشغّل المحرك الحالي (غير المصلح)
ونستخرج: الإشارة المستهدفة + نطاقها + anchor + مرجعها → إثبات أن المرجع قبل الولادة.
"""
import json
import os
import sys
import time
import importlib.util
from datetime import datetime, timezone, timedelta

OUT = "/home/z/my-project/download/ROUND26-RANGE-LIFE-REF/evidence"
K3 = timezone(timedelta(hours=3))


def t3(ms):
    if ms is None:
        return "—"
    return datetime.fromtimestamp(int(ms) / 1000, tz=K3).strftime("%m-%d %H:%M")


ENG = "/home/z/my-project/download/ROUND22-ZLF-E2E/app/services/indicators/overlays_zlf_e2e.py"
spec = importlib.util.spec_from_file_location("e2e_engine_current", ENG)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
zigzag_fib_e2e = mod.zigzag_fib_e2e

sys.path.insert(0, "/home/z/my-project/download/ROUND23-REAL-TEST")
from zlf_fetch import fetch_klines, klines_to_df, TF_MS  # noqa: E402


def main():
    os.makedirs(OUT, exist_ok=True)
    print("جلب شموع RUNEUSDT 1m (تغطية 10-30 → الآن) ...")
    now_ms = int(time.time() * 1000)
    kls = fetch_klines("RUNEUSDT", "1m", 9000)
    df, forming_open = klines_to_df(kls, TF_MS["1m"], now_ms)
    candles = [{"time": int(ts.timestamp() * 1000), "open": r["open"], "high": r["high"],
                "low": r["low"], "close": r["close"], "volume": r["volume"]}
               for ts, r in df.iterrows()]
    print(f"شموع: {len(candles)} · من {t3(candles[0]['time'])} إلى {t3(candles[-1]['time'])} · forming_open={forming_open}")
    json.dump(candles, open(f"{OUT}/raw_candles_1m.json", "w"), ensure_ascii=False)

    eng = zigzag_fib_e2e(candles)
    sigs = [s for s in eng["signals"] if s.get("side") == "liquidity"]
    print(f"إشارات المحرك الحالي: {len(sigs)}")

    # نطاق البحث عن حالة المستخدم: ref_vol قريب من 72790 وإشارة S2 حول 17:33
    print()
    print("=== كل الإشارات S2 التي مرجعها قبل ولادة نطاقها (إثبات المشكلة) ===")
    bad = 0
    target = None
    for s in sigs:
        rng = eng["ranges"][s["range_index"]]
        anchor_bar = rng["anchor"]["bar"]
        ref_bar = s.get("ref_bar")
        if ref_bar is not None and ref_bar < anchor_bar:
            bad += 1
            is_target = (abs(float(s.get("ref_vol") or 0) - 72790.0) < 1.0)
            mark = "  ←←← حالة المستخدم (مرجعها 72,790)" if is_target else ""
            print(f"  {t3(s['time'])} {s['signal']}: vol={s['volume']} · ref_vol={s['ref_vol']} · "
                  f"ref_high={s['ref_high']} · المرجع@{t3(s['ref_time'])} · ولادة النطاق@{t3(s['range_anchor']['time'])}{mark}")
            if is_target:
                target = s
    print(f"\nإجمالي الإشارات التي مرجعها خارج (قبل) نطاقها: {bad}/{len(sigs)}")

    if target:
        rng = eng["ranges"][target["range_index"]]
        print()
        print("=== تفصيل حالة المستخدم (قبل الإصلاح) ===")
        G = candles[target["bar"]]
        print(f"  النطاق #{target['range_index']}: {rng['p1']['kind']} {t3(rng['p1']['time'])}@{rng['p1']['price']}"
              f" → {rng['p2']['kind']} {t3(rng['p2']['time'])}@{rng['p2']['price']}")
        print(f"  ولادة النطاق (ظهور الزقزاق) = {t3(target['range_anchor']['time'])}  (توقع المستخدم: ~17:09 ±1)")
        print(f"  المرجع R المستخدم حالياً: حمراء @ {t3(target['ref_time'])} (توقع المستخدم: 15:23) "
              f"· قمة={target['ref_high']} · حجم={target['ref_vol']}")
        print(f"  شمعة الإشارة G @ {t3(target['time'])}: O={G['open']} H={G['high']} L={G['low']} "
              f"C={G['close']} V={G['volume']}  (التصنيف الحالي: {target['signal']})")
        print(f"  ⇒ المرجع {t3(target['ref_time'])} سابق لولادة النطاق {t3(target['range_anchor']['time'])}"
              f" → خارج النطاق حسب اتفاقك — وهذا سبب ظهور S2 بدل S1.")
        json.dump({
            "signal_time": target["time"], "t3": t3(target["time"]), "engine_signal": target["signal"],
            "G": G, "ref_high": target["ref_high"], "ref_vol": target["ref_vol"],
            "ref_time": target["ref_time"], "ref_t3": t3(target["ref_time"]),
            "anchor_time": target["range_anchor"]["time"], "anchor_t3": t3(target["range_anchor"]["time"]),
            "range_index": target["range_index"],
            "range_p1": {"kind": rng["p1"]["kind"], "time": rng["p1"]["time"], "price": rng["p1"]["price"]},
            "range_p2": {"kind": rng["p2"]["kind"], "time": rng["p2"]["time"], "price": rng["p2"]["price"]},
            "launch_line": target["launch_line"],
        }, open(f"{OUT}/target_case_BEFORE.json", "w"), ensure_ascii=False, indent=1)

    # شموع النطاق نفسها: كم حمراء داخل عمر النطاق قبل الإشارة؟
    if target:
        rng = eng["ranges"][target["range_index"]]
        a, b = rng["anchor"]["bar"], target["bar"]
        reds = [(t3(candles[j]["time"]), candles[j]["high"], candles[j]["volume"])
                for j in range(a, b) if candles[j]["close"] < candles[j]["open"]]
        print(f"\n  الحمراء داخل عمر النطاق [الولادة {t3(candles[a]['time'])} → الإشارة {t3(candles[b]['time'])}): {len(reds)}")
        for rt, rh, rv in reds:
            print(f"    {rt} · H={rh} · V={rv}")
        if reds:
            best = max(reds, key=lambda x: x[2])
            print(f"  ⇒ أكبر حمراء داخل عمر النطاق = {best[0]} · H={best[1]} · V={best[2]}")
            print(f"     شمعة 17:33 حجمها {target['volume']} مقابلها → "
                  f"{'أكبر ⇒ S1' if target['volume'] > best[2] else 'أصغر/يساوي ⇒ S2'} "
                  f"واختراق القمة: {G['high']} > {best[1]}؟ {G['high'] > best[1]}")


if __name__ == "__main__":
    main()
