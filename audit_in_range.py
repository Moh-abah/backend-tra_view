# -*- coding: utf-8 -*-
"""
ROUND26 — تدقيق «كل المقارنات من داخل النطاق» + سلامة عمود ولادة النطاق
1) إعادة اشتقاق مستقلة لكل إشارة بشكل صارم من داخل عمر النطاق فقط:
   [المرجع الحي، هيمنة الخضراء، الانطلاقة، الاختراق، الحجم] من شموع [anchor..G)
   ومطابقة نتيجة المحرك 100% — إثبات أن لا مقارنة تستخدم ما خارج النطاق.
2) فحص عمود zzfe_anchor (عدد الولادات = عدد النطاقات · التوقيتات مطابقة)
   و zzfe_range_index (الانتقالات عند أشرطة الولادة بالضبط).
3) إثبات أن خط الانطلاقة مستمد من رسم الفيبو (p1/p2) وليس من شموع خارجية.
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


spec = importlib.util.spec_from_file_location(
    "eng_new_audit", "/home/z/my-project/download/ROUND26-RANGE-LIFE-REF/app/services/indicators/overlays_zlf_e2e.py")
ENG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ENG)


def audit(symbol_candles_file, label):
    candles = json.load(open(symbol_candles_file))
    eng = ENG.zigzag_fib_e2e(candles)
    N = len(candles)
    tick = (eng.get("params") or {}).get("inferred_tick") or 0.0
    sigs = [s for s in eng["signals"] if s.get("side") == "liquidity"]

    # ============ 1) إعادة الاشتقاق المستقلة الصارمة من داخل النطاق ============
    mismatches = 0
    details = []
    for s in sigs:
        G_bar = s["bar"]
        a_bar = eng["ranges"][s["range_index"]]["anchor"]["bar"]
        # كل مدخلات القرار تُبنى حصراً من [anchor..G_bar] — لا شيء قبله
        live_ref = None
        green_max = None
        for j in range(a_bar, G_bar):
            c = candles[j]
            if c["close"] < c["open"] and c["volume"] is not None:
                if live_ref is None or c["volume"] >= live_ref["vol"]:
                    live_ref = {"bar": j, "high": c["high"], "vol": c["volume"]}
            if c["close"] > c["open"]:
                green_max = c["volume"] if green_max is None else max(green_max, c["volume"])
        G = candles[G_bar]
        green = G["close"] > G["open"]
        launch_ok = G["low"] >= (s["launch_line"] - 1.0 * tick)
        dominance = (green_max is None) or (G["volume"] > green_max)
        breakout = (live_ref is not None) and (G["high"] > live_ref["high"])
        vol_dom = (live_ref is not None) and (G["volume"] > live_ref["vol"])
        cell = 1 if (breakout and vol_dom) else 2 if breakout else 3 if vol_dom else 0
        ok = bool(green and launch_ok and dominance and cell)
        eng_cell = int(s["signal"].rsplit("S", 1)[-1])
        ref_match = (live_ref is not None and live_ref["bar"] == s.get("ref_bar")
                     and abs(live_ref["vol"] - s["ref_vol"]) < 1e-9)
        match = ok and eng_cell == cell and ref_match
        if not match:
            mismatches += 1
            details.append({"t3": t3(s["time"]), "engine": eng_cell, "audit": cell,
                            "ref_match": ref_match, "complete": ok})
    print(f"  [{label}] إشارات: {len(sigs)} · إعادة اشتقاق صارمة من داخل النطاق فقط → "
          f"عدم تطابق: {mismatches} {'✅ كل المقارنات داخلية 100%' if mismatches == 0 else '❌'}")

    # ============ 2) سلامة عمود ولادة النطاق ============
    ser = eng["series"]
    anch = ser["zzfe_anchor"]
    ridx = ser["zzfe_range_index"]
    anchor_bars_engine = sorted(set(int(r["anchor"]["bar"]) for r in eng["ranges"] if r["anchor"]["bar"] < N))
    anchor_bars_column = [i for i, v in enumerate(anch) if v and float(v) == 1.0]
    ok_anchor = anchor_bars_engine == anchor_bars_column
    print(f"  [{label}] عمود zzfe_anchor: ولادات المحرك={len(anchor_bars_engine)} · "
          f"ولادات العمود={len(anchor_bars_column)} · تطابق المواضع والتوقيتات: {ok_anchor} "
          f"{'✅' if ok_anchor else '❌'}")
    # توقيتات
    tmatch = all(candles[i]["time"] == next(r["anchor"]["time"] for r in eng["ranges"]
                                            if int(r["anchor"]["bar"]) == i)
                 for i in anchor_bars_column)
    print(f"  [{label}] توقيت كل نقطة ولادة في العمود = anchor.time في النطاقات: {tmatch} {'✅' if tmatch else '❌'}")
    # range_index: الانتقالات
    bad_trans = 0
    prev = -1.0
    for i in range(N):
        cur = ridx[i]
        if cur != prev:
            # انتقال مشروع فقط عند شمعة ولادة
            if not (anch[i] == 1.0 or (prev == -1.0 and cur >= 0) or i == 0):
                if not (anch[i] == 1.0):
                    bad_trans += 1
            prev = cur
    # قبل أول ولادة يجب -1
    first_a = anchor_bars_column[0] if anchor_bars_column else N
    ok_pre = all(float(v) == -1.0 for v in ridx[:first_a])
    print(f"  [{label}] zzfe_range_index: انتقالات غير مشروعة={bad_trans} · "
          f"قيم ما قبل أول ولادة = -1: {ok_pre} {'✅' if bad_trans == 0 and ok_pre else '❌'}")

    # ============ 3) الانطلاقة من رسم الفيبو (p1/p2) ============
    ok_launch = True
    for r in eng["ranges"]:
        p1, p2 = r["p1"]["price"], r["p2"]["price"]
        if r["launch_line"] is None:
            if abs(p1 - p2) < 1e-12:
                continue
            ok_launch = False
            break
        # 0.618 للمستخدم = price(0.382) بمقياس المحرك من الأول إلى الثاني
        expected = p1 + (p2 - p1 if False else (r["launch_line"] - p1))  # placeholder
    # تحقق مباشر بالمعادلة المصادقة: launch = q1 + diff*0.382
    for r in eng["ranges"]:
        q1, q2 = r["p1"]["price"], r["p2"]["price"]
        diff = (1.0 if q1 < q2 else -1.0) * abs(q1 - q2)
        exp = q1 + diff * 0.382
        if r["launch_line"] is not None and abs(exp - r["launch_line"]) > 1e-9:
            ok_launch = False
            break
    print(f"  [{label}] خط الانطلاقة = price(0.382) من رسم الفيبو المعتمد (وليس من شموع خارجية): {ok_launch} {'✅' if ok_launch else '❌'}")

    return {"label": label, "signals": len(sigs), "audit_mismatches": mismatches,
            "anchor_bars": len(anchor_bars_engine), "anchor_column_match": ok_anchor,
            "anchor_times_match": tmatch, "range_index_ok": bad_trans == 0 and ok_pre,
            "launch_ok": ok_launch}


def main():
    os.makedirs(OUT, exist_ok=True)
    print("=== تدقيق ROUND26: كل مقارنات القرار من داخل النطاق + عمود الولادة ===")
    results = []
    results.append(audit(f"{OUT}/raw_candles_1m.json", "RUNE 1m"))

    # عينات إضافية: نستخدم شموع الانحدار إن وُجدت وإلا نجلب سريعاً
    import sys, time
    sys.path.insert(0, "/home/z/my-project/download/ROUND23-REAL-TEST")
    from zlf_fetch import fetch_klines, klines_to_df, TF_MS
    for sym, tf, need in (("RUNEUSDT", "5m", 2500), ("BTCUSDT", "1m", 3000)):
        f = f"{OUT}/raw_{sym}_{tf}.json"
        if not os.path.exists(f):
            now_ms = int(time.time() * 1000)
            kls = fetch_klines(sym, tf, need)
            df, _ = klines_to_df(kls, TF_MS[tf], now_ms)
            cs = [{"time": int(ts.timestamp() * 1000), "open": r["open"], "high": r["high"],
                   "low": r["low"], "close": r["close"], "volume": r["volume"]}
                  for ts, r in df.iterrows()]
            json.dump(cs, open(f, "w"))
        results.append(audit(f, f"{sym} {tf}"))

    all_ok = all(r["audit_mismatches"] == 0 and r["anchor_column_match"] and r["anchor_times_match"]
                 and r["range_index_ok"] and r["launch_ok"] for r in results)
    print(f"\n⇒ الحكم النهائي: {'✅✅ كل المقارنات من داخل النطاق + عمود الولادة سليم' if all_ok else '❌ يوجد خلل'}")
    json.dump({"results": results, "verdict": "ALL_IN_RANGE_OK" if all_ok else "FAILED"},
              open(f"{OUT}/in_range_audit.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
