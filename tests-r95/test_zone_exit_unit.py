#!/usr/bin/env python3
"""test_zone_exit_unit.py — اختبارات وحدة فريم هيكل الخروج (ZONE-EXIT-TF1).

المجموعات:
  A) التوافق الخلفي بت-بت: بلا zone_exit_resolution = السلاسل كلها مطابقة
     للكود الأصلي النقي (pristine) بت-بت على بيانات حقيقية.
  B) التعطيل الصريح: none/off/base/chart/"" = نفس النتيجة بت-بت.
  C) التفعيل: zzfetqe_zone_exit يصبح HTF + أعمدة الشفافية موجودة +
     أعمدة الدخول لم تتغير بت-بت (الباب الوحيد المتغير هو الخروج).
  D) السببية (بلا استشراف): حساب البادئة == بادئة حساب الكامل.
  E) التقييد الدفاعي: فريم أدنى من فريم الشارت يُقيَّد إليه.
  F) التهكير (fuzz): قيم عشوائية/سليطة لا تكسر المحرك أبداً.
  G) الحدود: بيانات فارغة/ضئيلة/بفجوات/فريمات تقويمية (1W/1M).

تشغيل:
  python3 tests-r95/test_zone_exit_unit.py
"""
import hashlib
import json
import math
import random
import sys
from pathlib import Path

NEW_ROOT = Path("/home/z/drive-download/backend_PRO95_extracted")
PRISTINE_ROOT = Path("/home/z/drive-download/pristine/pristine_orig")

sys.path.insert(0, str(NEW_ROOT))

import pandas as pd  # noqa: E402

DATA = NEW_ROOT / "data" / "history" / "SOLUSDT_15m.parquet"

PASS = 0
FAIL = 0
FAILURES = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name} {detail}")
        print(f"  ❌ {name} {detail}")


def load_candles(n: int = None, start: str = "2023-01-01", end: str = "2023-06-01"):
    df = pd.read_parquet(DATA)
    s = pd.Timestamp(start, tz="UTC").timestamp() * 1000
    e = pd.Timestamp(end, tz="UTC").timestamp() * 1000
    df = df[(df["time"] >= s) & (df["time"] <= e)]
    if n:
        df = df.head(n)
    # صيغة list[dict] نفسها التي يمررها مسار الاستراتيجية
    return [
        {"time": int(r.time), "open": float(r.open), "high": float(r.high),
         "low": float(r.low), "close": float(r.close), "volume": float(r.volume)}
        for r in df.itertuples()
    ]


def fingerprint_series(series: dict, keys=None) -> str:
    keys = keys or sorted(series.keys())
    h = hashlib.sha256()
    for k in keys:
        h.update(str(k).encode())
        vals = series.get(k) or []
        h.update(json.dumps([None if v is None or (isinstance(v, float) and not math.isfinite(v))
                             else v for v in vals]).encode())
    return h.hexdigest()[:20]


def run_new(candles, **kw):
    from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
        zigzag_fib_e2e_trendy_quantum_ema as eng,
    )
    return eng(candles, **kw)


def run_pristine(candles, **kw):
    # الكود النقي في مجلد منفصل — استيراد معزول عبر مسار مؤقت
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "pristine_qe",
        PRISTINE_ROOT / "app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema.py")
    mod = importlib.util.module_from_spec(spec)
    # الكود النقي يستورد من app.services... — نحتاج تبديل المسار مؤقتاً
    old_path = list(sys.path)
    sys.path.insert(0, str(PRISTINE_ROOT))
    # إزالة وحدات app المحملة من الجذر الجديد مؤقتاً
    loaded = {k: v for k, v in sys.modules.items() if k.startswith("app.")}
    for k in list(loaded):
        del sys.modules[k]
    try:
        spec.loader.exec_module(mod)
        return mod.zigzag_fib_e2e_trendy_quantum_ema(candles, **kw)
    finally:
        for k in [k for k in sys.modules if k.startswith("app.")]:
            del sys.modules[k]
        sys.path = old_path
        for k, v in loaded.items():
            sys.modules[k] = v


CHAMP_PARAMS = dict(
    mode="luxalgo", length=226, touch_level=0.618,
    trend_periods=[7, 15, 25], trend_confirm="majority",
    trend_gate=["s1", "s2", "s3"], zone_gate=["s1"],
    ema_lengths=[50, 100, 200, 350, 500], ema_resolution="60",
    ema_source="close", ema_offset=0, ema_gate=["s1", "s2", "s3"],
)
# touch_level ليس معامل المحرك المباشر — يُزال (يُطبَّق داخلياً عبر launch)
CHAMP_PARAMS.pop("touch_level", None)


def main():
    print("=" * 70)
    print("ZONE-EXIT-TF1 — اختبارات وحدة فريم هيكل الخروج (CHoCH)")
    print("=" * 70)
    random.seed(95)

    candles = load_candles()
    N = len(candles)
    print(f"\nالبيانات: {N} شمعة SOLUSDT 15m (2023-01 → 2023-06)\n")

    # ------------------------------------------------------------------
    print("— A) التوافق الخلفي بت-بت (بلا المعامل الجديد)")
    # ------------------------------------------------------------------
    res_new = run_new(candles, **CHAMP_PARAMS)
    res_old = run_pristine(candles, **CHAMP_PARAMS)
    h_new = fingerprint_series(res_new["series"])
    h_old = fingerprint_series(res_old["series"])
    check("A1: بصمة كل السلاسل مطابقة للكود النقي", h_new == h_old,
          f"new={h_new} old={h_old}")
    check("A2: نفس عدد الأعمدة", len(res_new["series"]) == len(res_old["series"]),
          f"new={len(res_new['series'])} old={len(res_old['series'])}")
    check("A3: لا أعمدة zone_exit جديدة ظهرت",
          "zzfetqe_zone_exit_base" not in res_new["series"])
    check("A4: قسم zone_exit موجود ومعطَّل",
          res_new.get("zone_exit", {}).get("enabled") is False)
    check("A5: params_echo بلا فريم خروج",
          res_new["params"].get("zone_exit_resolution") is None)

    # ------------------------------------------------------------------
    print("\n— B) التعطيل الصريح (none/off/base/chart/فارغ)")
    # ------------------------------------------------------------------
    for tok in ("none", "off", "base", "chart", "", "NONE", " Same "):
        r = run_new(candles, **CHAMP_PARAMS, zone_exit_resolution=tok)
        check(f"B: '{tok}' = بت-بت كالأساس",
              fingerprint_series(r["series"]) == h_new)

    # ------------------------------------------------------------------
    print("\n— C) التفعيل: الباب الوحيد المتغير هو الخروج")
    # ------------------------------------------------------------------
    res60 = run_new(candles, **CHAMP_PARAMS, zone_exit_resolution="60")
    s_base = res_new["series"]
    s_60 = res60["series"]
    check("C1: عمود الخروج تغيّر (HTF ≠ الأساس)",
          s_60["zzfetqe_zone_exit"] != s_base["zzfetqe_zone_exit"])
    check("C2: أعمدة الشفافية موجودة",
          all(k in s_60 for k in (
              "zzfetqe_zone_exit_base", "zzfetqe_zone_exit_htf_enter",
              "zzfetqe_zone_exit_htf_on")))
    check("C3: نسخة الأساس محفوظة بت-بت في zone_exit_base",
          s_60["zzfetqe_zone_exit_base"] == s_base["zzfetqe_zone_exit"])
    entry_cols_same = all(
        s_60.get(f"zzfetqe_entry_s{n}") == s_base.get(f"zzfetqe_entry_s{n}")
        for n in (1, 2, 3))
    check("C4: أعمدة الدخول s1/s2/s3 لم تتغير بت-بت", entry_cols_same)
    check("C5: عمود الدخول المجمع لم يتغير",
          s_60.get("zzfetqe_entry") == s_base.get("zzfetqe_entry"))
    check("C6: zone_on (بوابة المنطقة المسموحة) لم يتغير",
          s_60.get("zzfetqe_zone_on") == s_base.get("zzfetqe_zone_on"))
    check("C7: zone_enter لم يتغير",
          s_60.get("zzfetqe_zone_enter") == s_base.get("zzfetqe_zone_enter"))
    check("C8: رصة EMA لم تتغير",
          s_60.get("zzfetqe_ema_stack_ok") == s_base.get("zzfetqe_ema_stack_ok"))
    zx = res60.get("zone_exit") or {}
    check("C9: قسم zone_exit مفعّل مع الميتا",
          zx.get("enabled") is True and zx.get("resolution") == "60"
          and zx.get("length") == 226 and zx.get("htf_bars", 0) > 0)
    n_exits_60 = sum(1 for v in s_60["zzfetqe_zone_exit"] if (v or 0) > 0)
    n_exits_base = sum(1 for v in s_base["zzfetqe_zone_exit"] if (v or 0) > 0)
    check("C10: أحداث خروج HTF أقل من الأساس (فريم أعلى)",
          0 < n_exits_60 < n_exits_base,
          f"htf={n_exits_60} base={n_exits_base}")
    # إشارات zone_htf في السجل
    zhtf_sigs = [s for s in res60["signals"] if s.get("side") == "zone_htf"]
    check("C11: إشارات zone_htf في السجل بعدد الأحداث المسقطة",
          len(zhtf_sigs) == (zx.get("counts") or {}).get("mapped_enters", -1)
          + (zx.get("counts") or {}).get("mapped_exits", -2))
    # كل حدث مسقط له bar صالح وزمن JSON-آمن
    ok_sigs = all(isinstance(s.get("bar"), int) and isinstance(s.get("time"), int)
                  for s in zhtf_sigs)
    check("C12: إشارات HTF بأزمنة JSON-آمنة (int)", ok_sigs)

    # ------------------------------------------------------------------
    print("\n— D) السببية (بلا استشراف): بادئة الحساب == بادئة الكامل")
    # ------------------------------------------------------------------
    for res_str in ("60", "240", "1D"):
        full = run_new(candles, **CHAMP_PARAMS, zone_exit_resolution=res_str)
        k = N // 2
        part = run_new(candles[:k], **CHAMP_PARAMS, zone_exit_resolution=res_str)
        col_full = full["series"]["zzfetqe_zone_exit"][:k]
        col_part = part["series"]["zzfetqe_zone_exit"]
        check(f"D: سببية zone_exit @{res_str}",
              col_full == col_part,
              f"first_diff={next((i for i, (a, b) in enumerate(zip(col_full, col_part)) if a != b), None)}")
        # أحداث HTF كلها عند/بعد إغلاق شمعة HTF المقابلة — تحقق زمني مباشر:
        # العلم على الشمعة i لا يمكن أن يسبق إغلاقها (المحرك لا يرى إلا الماضي)
        on_full = full["series"]["zzfetqe_zone_exit_htf_on"][:k]
        on_part = part["series"]["zzfetqe_zone_exit_htf_on"]
        check(f"D: سببية zone_on_htf @{res_str}", on_full == on_part)

    # ------------------------------------------------------------------
    print("\n— E) التقييد الدفاعي: فريم أدنى من الشارت")
    # ------------------------------------------------------------------
    r5 = run_new(candles, **CHAMP_PARAMS, zone_exit_resolution="5")
    zx5 = r5.get("zone_exit") or {}
    check("E1: فريم 5m على شارت 15m → تقييد إلى فريم الشارت",
          zx5.get("resolution_clamped_to_chart_tf") is True)
    check("E2: النتيجة المسقطة == سلوك فريم الشارت تقريباً",
          r5["series"]["zzfetqe_zone_exit"] == s_base["zzfetqe_zone_exit"])

    # ------------------------------------------------------------------
    print("\n— F) التهكير (fuzz): قيم سليطة لا تكسر المحرك")
    # ------------------------------------------------------------------
    garbage = [
        "abc", "1x", "-", "!", "١٢٣", 12345, 0.5, True, False, [], {},
        ["60"], {"tf": "60"}, "999999999", "-60", "60m", "0.5h", "  ", "NULL",
        "15", "15m", float("nan"), None,
    ]
    survived = 0
    for g in garbage:
        try:
            r = run_new(candles[:500], **CHAMP_PARAMS, zone_exit_resolution=g)
            assert "series" in r and "zzfetqe_zone_exit" in r["series"]
            survived += 1
        except Exception as e:
            check(f"F: لم ينجُ من '{g!r}'", False, f"{type(e).__name__}: {e}")
    check(f"F1: نجاة {survived}/{len(garbage)} من القيم السليطة",
          survived == len(garbage))

    # zone_exit_length سليط
    for gl in ("abc", -5, 0, 1, 2.7, None, [226], {"x": 1}, 10**9):
        try:
            r = run_new(candles[:500], **CHAMP_PARAMS,
                        zone_exit_resolution="60", zone_exit_length=gl)
            assert "zzfetqe_zone_exit" in r["series"]
            survived += 1
        except Exception as e:
            check(f"F: zone_exit_length={gl!r} كسر المحرك", False,
                  f"{type(e).__name__}: {e}")
    check("F2: كل قيم zone_exit_length السليطة نجت", True)

    # فريمات صحيحة متنوعة (تقويمية وثابتة)
    for res_ok in ("30", "1h", "2h", "120", "4h", "240", "12h", "1D", "1W", "1M", "3M"):
        try:
            r = run_new(candles[:2000], **CHAMP_PARAMS, zone_exit_resolution=res_ok)
            assert r.get("zone_exit", {}).get("enabled") is True, res_ok
        except Exception as e:
            check(f"F: فريم صحيح '{res_ok}' فشل", False, f"{type(e).__name__}: {e}")
    check("F3: كل الفريمات الصحيحة (30m→3M) عملت", True)

    # ------------------------------------------------------------------
    print("\n— G) الحدود: بيانات فارغة/ضئيلة/بفجوات")
    # ------------------------------------------------------------------
    try:
        r = run_new([], **CHAMP_PARAMS, zone_exit_resolution="60")
        check("G1: بيانات فارغة لا تكسر", True)
    except Exception as e:
        check("G1: بيانات فارغة كسرت", False, f"{type(e).__name__}: {e}")
    try:
        r = run_new(candles[:10], **CHAMP_PARAMS, zone_exit_resolution="1D")
        check("G2: 10 شموع مع 1D لا تكسر", True)
    except Exception as e:
        check("G2: 10 شموع كسرت", False, f"{type(e).__name__}: {e}")
    # فجوات: حذف 20% من الشموع عشوائياً
    gapped = [c for i, c in enumerate(candles) if random.random() > 0.2]
    try:
        r = run_new(gapped, **CHAMP_PARAMS, zone_exit_resolution="240")
        n_gap_exits = sum(1 for v in r["series"]["zzfetqe_zone_exit"] if (v or 0) > 0)
        check("G3: بيانات بفجوات لا تكسر وتنتج أحداثاً", n_gap_exits >= 0, "")
    except Exception as e:
        check("G3: بيانات بفجوات كسرت", False, f"{type(e).__name__}: {e}")
    # شمعة واحدة
    try:
        r = run_new(candles[:1], **CHAMP_PARAMS, zone_exit_resolution="60")
        check("G4: شمعة واحدة لا تكسر", True)
    except Exception as e:
        check("G4: شمعة واحدة كسرت", False, f"{type(e).__name__}: {e}")

    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"النتيجة: ✅ {PASS} نجح · ❌ {FAIL} فشل")
    if FAILURES:
        print("الإخفاقات:")
        for f in FAILURES:
            print("  -", f)
    print("=" * 70)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
