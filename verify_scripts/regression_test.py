#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# ✅ ROUND34 — اختبار الانحدار الذهبي: القديم مقابل الموحد (بايت-ببايت)
# =============================================================================
# يقارن مخرجات المحركات القديمة (المستنسخة في /tmp/project_src) مع المحركات
# الموحدة (/home/z/backend-src) على نفس البيانات حرفياً:
#   1) zigzag_fib        (البطل ZLF)        — وضعا tradingview/luxalgo
#   2) zigzag_fib_e2e    (البطل e2e)        — وضعا luxalgo/tradingview
#   3) zigzag_fib_e2e_trendy (الترندية)     — luxalgo + بوابة الترند
#   4) zigzag_channels   (البطل الأصلي HL)  — luxalgo
# المقارنة تشمل: series (كل الأعمدة) + signals + legs + current +
# ranges (مع تجاهل حقل levels الجديد الإضافي فقط).
# =============================================================================
import importlib
import json
import sys

RESULTS = []


def jhash(obj) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str,
                                     ensure_ascii=False).encode()).hexdigest()


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(("PASS ✅ " if ok else "FAIL ❌ ") + name + (f"  [{detail}]" if detail and not ok else ""))


def strip_new_fields(res, kind):
    """يزيل الحقول التوثيقية/الإضافية قبل مقارنة القيم.

    يضمن مقارنة عادلة ضد أي نسخة احتياط:
    - ما قبل ج34 (الأساس الأصلي)، أو
    - أي ج34 أخرى (تصلح نفس العلل — مثل هذه الحزمة)
    الفروق المسموحة: وسوم التوثيق (notes/spec/engine/name/core — نصوص
    إصدارات فقط) + إضافات ج34 الموثقة (ranges[].levels).
    القيم المحسوبة (أرجل/نطاقات/إشارات/سلاسل) يجب أن تتطابق حرفياً.
    """
    import copy
    r = copy.deepcopy(res)
    r.pop("notes", None)             # نص توثيقي فقط (حُدّثت صياغته)
    for k in ("spec", "engine", "name"):  # وسوم توثيقية تختلف بين الإصدارات
        r.pop(k, None)
    if kind in ("e2e", "trendy"):
        r.pop("core", None)          # حقل هوية النواة الجديد
        for rng in r.get("ranges") or []:
            rng.pop("levels", None)  # مستويات بحدود الرسم (إضافة جديدة)
    liq = r.get("liquidity")
    if isinstance(liq, dict):
        for k in ("spec", "engine"):
            liq.pop(k, None)
    return r


def main():
    # ✅ مسارات قابلة للتهيئة — الافتراضي: نسبي للسكربت
    #   OLD_SRC = مسار نسخة ما قبل ج34 (احتياطك قبل الدمج) — إلزامي لهذا الفحص
    #   NEW_SRC = مسار المشروع المدموج (الافتراضي: والد والد السكربت)
    import os
    _here = os.path.dirname(os.path.abspath(__file__))
    old_root = os.environ.get("OLD_SRC", "")
    new_root = os.environ.get("NEW_SRC") or os.path.dirname(_here)

    if not old_root or not os.path.isdir(old_root):
        print("=" * 64)
        print("هذا فحص A/B الإضافي (بايت-ببايت) بين كود ما قبل ج34 والكود الموحد.")
        print("يحتاج نسخة الكود القديم في مسار منفصل. الاستخدام:")
        print("  OLD_SRC=/path/to/backup_before_round34 NEW_SRC=/path/to/merged \\")
        print("      python verify_scripts/regression_test.py")
        print("")
        print("⚠️ لا يوجد OLD_SRC — تخطّي هذا الفحص الإضافي.")
        print("   الانحدار الرسمي الحتمي (بلقطات الهاش الذهبية) موجود داخل")
        print("   verify_round32.py — الفحص 17 — ويعمل بلا كود قديم وبلا شبكة.")
        print("=" * 64)
        return 0

    # --- تحميل النسخة القديمة ---
    sys.path.insert(0, old_root)
    import app.services.indicators.overlays as old_overlays_mod
    import app.services.indicators.overlays_zlf_e2e as old_e2e_mod
    import app.services.indicators.overlays_zlf_e2e_trendy as old_trendy_mod

    # --- تبديل المسار إلى النسخة الجديدة ---
    for mod_name in list(sys.modules):
        if mod_name.startswith("app."):
            del sys.modules[mod_name]
    sys.path.remove(old_root)
    sys.path.insert(0, new_root)
    import app.services.indicators.overlays as new_overlays_mod
    import app.services.indicators.overlays_zlf_e2e as new_e2e_mod
    import app.services.indicators.overlays_zlf_e2e_trendy as new_trendy_mod
    import app.services.indicators.zigzag_fib_core as core_mod
    print(f"core = {core_mod.ZIGZAG_FIB_CORE_SPEC} v{core_mod.ZIGZAG_FIB_CORE_VERSION}\n")

    import pandas as pd

    datasets = {}
    _evidence = os.path.join(new_root, "evidence")
    for tag, path in [
        ("APPBUSDT_5m_week", os.path.join(_evidence, "APPBUSDT_5m_week.json")),
        ("BTC_golden_1m", os.path.join(_evidence, "golden_btc_1m.json")),
    ]:
        try:
            raw = json.load(open(path))
            if isinstance(raw, dict) and "time" in raw:
                raw = [raw]
            elif isinstance(raw, list) and raw and isinstance(raw[0], list):
                raw = [{"time": k[0], "open": float(k[1]), "high": float(k[2]),
                        "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])} for k in raw]
            datasets[tag] = raw
            print(f"dataset {tag}: {len(raw)} candles")
        except Exception as e:
            print(f"dataset {tag}: SKIP ({e})")

    def as_df(candles):
        df = pd.DataFrame(candles)
        df["timestamp"] = pd.to_datetime(df["time"] if "time" in df else df["timestamp"], unit="ms", utc=True)
        return df.set_index("timestamp")

    def as_iso(candles):
        """نفس الشموع لكن timestamp كسلسلة ISO (مسار chart-data في الباك تست)."""
        from datetime import datetime, timezone
        return [{"timestamp": datetime.fromtimestamp((c.get("time") or c.get("timestamp")) / 1000, tz=timezone.utc).isoformat(),
                 "open": c["open"], "high": c["high"], "low": c["low"],
                 "close": c["close"], "volume": c["volume"]} for c in candles]

    for tag, candles in datasets.items():
        df = as_df(candles)
        iso = as_iso(candles)

        # ---------- 1) البطل ZLF (zigzag_fib) ----------
        for mode_kw in ({"mode": "tradingview"}, {"mode": "luxalgo", "length": 100}):
            md = mode_kw.get("mode")
            old = old_overlays_mod.zigzag_fib(df, liq_lookback=240, **mode_kw)
            new = new_overlays_mod.zigzag_fib(df, liq_lookback=240, **mode_kw)
            ok = jhash(old) == jhash(new)
            check(f"[{tag}] zzfib mode={md} — تطابق كامل (بايت-ببايت)", ok,
                  f"old={jhash(old)[:12]} new={jhash(new)[:12]}")

        # ---------- 2) البطل e2e (zigzag_fib_e2e) — luxalgo ----------
        old = old_e2e_mod.zigzag_fib_e2e(df, mode="luxalgo", length=100)
        new = new_e2e_mod.zigzag_fib_e2e(df, mode="luxalgo", length=100)
        ok = jhash(strip_new_fields(old, "e2e")) == jhash(strip_new_fields(new, "e2e"))
        check(f"[{tag}] zzfib_e2e luxalgo — تطابق كامل (بدون الإضافات الجديدة)", ok,
              f"old={jhash(strip_new_fields(old, 'e2e'))[:12]} new={jhash(strip_new_fields(new, 'e2e'))[:12]}")

        # e2e بوضع tradingview
        old = old_e2e_mod.zigzag_fib_e2e(df, mode="tradingview")
        new = new_e2e_mod.zigzag_fib_e2e(df, mode="tradingview")
        ok = jhash(strip_new_fields(old, "e2e")) == jhash(strip_new_fields(new, "e2e"))
        check(f"[{tag}] zzfib_e2e tradingview — تطابق كامل", ok)

        # ---------- 3) الترندية ----------
        old = old_trendy_mod.zigzag_fib_e2e_trendy(df, mode="luxalgo", length=100)
        new = new_trendy_mod.zigzag_fib_e2e_trendy(df, mode="luxalgo", length=100)
        ok = jhash(strip_new_fields(old, "trendy")) == jhash(strip_new_fields(new, "trendy"))
        check(f"[{tag}] zzfib_e2e_trendy luxalgo — تطابق كامل", ok)

        # ---------- 4) البطل الأصلي (zigzag_channels) ----------
        old = old_overlays_mod.zigzag_channels(df, length=100)
        new = new_overlays_mod.zigzag_channels(df, length=100)
        ok = jhash(old) == jhash(new)
        check(f"[{tag}] zigzag_channels — تطابق كامل", ok)

        # ---------- 5) ✅ إصلاح ISO: نفس الشموع كسلاسل ISO ----------
        new_iso = new_e2e_mod.zigzag_fib_e2e(iso, mode="luxalgo", length=100)
        new_df = new_e2e_mod.zigzag_fib_e2e(df, mode="luxalgo", length=100)
        old_iso = old_e2e_mod.zigzag_fib_e2e(iso, mode="luxalgo", length=100)
        # القديم مع ISO: إن كان الاحتياط ما قبل ج34 → كل الأزمنة صفر (العلة
        # المصلحة). وإن كان الاحتياط ج34 أخرى (مصلِحة أيضاً) → أزمنته سليمة
        # كذلك — يُوثَّق ذلك بدل احتسابه فشلاً (كلا الحالتين تثبتان صحة مسارنا).
        _old_legs = old_iso.get("legs") or []
        old_zero_times = (not _old_legs) or all(
            (lg.get("t1") == 0 and lg.get("t2") == 0) for lg in _old_legs
        )
        iso_matches_df = jhash(strip_new_fields(new_iso, "e2e")) == jhash(strip_new_fields(new_df, "e2e"))
        check(f"[{tag}] إصلاح ISO — e2e على شموع ISO == e2e على DataFrame", iso_matches_df)
        if old_zero_times:
            check(f"[{tag}] إثبات العلة القديمة — القديم مع ISO كان يرجع أزمنة=0", True)
        else:
            print(f"PASS ✅ [{tag}] الاحتياط يصلح ISO أيضاً (ج34 أخرى) — لا علة قديمة فيه أصلاً")

        # نفس الفحص للترندية
        new_iso_t = new_trendy_mod.zigzag_fib_e2e_trendy(iso, mode="luxalgo", length=100)
        new_df_t = new_trendy_mod.zigzag_fib_e2e_trendy(df, mode="luxalgo", length=100)
        ok = jhash(strip_new_fields(new_iso_t, "trendy")) == jhash(strip_new_fields(new_df_t, "trendy"))
        check(f"[{tag}] إصلاح ISO — الترندية على ISO == DataFrame", ok)

        # ---------- 6) الحقول الجديدة موجودة وصحيحة ----------
        rngs = new_df.get("ranges") or []
        has_levels = bool(rngs) and all(
            isinstance(r.get("levels"), list) and len(r["levels"]) > 0 for r in rngs
        )
        # حدود الرسم: تبدأ من الولادة وتنتهي قبل ولادة التالي
        bounds_ok = True
        for i, r in enumerate(rngs):
            for lv in r.get("levels") or []:
                if lv["x_from"] != r["anchor"]["bar"]:
                    bounds_ok = False
                death_bar = r["death"]["bar"]
                if death_bar is not None and death_bar < len(candles) and lv["x_to"] != death_bar - 1:
                    bounds_ok = False
        check(f"[{tag}] إضافة ROUND34 — كل نطاق يحمل levels بحدود ولادة/نهاية صحيحة",
              has_levels and bounds_ok)

    print()
    total = len(RESULTS)
    n_ok = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"===== النتيجة: {n_ok}/{total} PASS =====")
    json.dump([{"name": n, "pass": ok, "detail": d} for n, ok, d in RESULTS],
              open(os.path.join(_here, "regression_results.json"), "w"), ensure_ascii=False, indent=1)
    return 0 if n_ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
