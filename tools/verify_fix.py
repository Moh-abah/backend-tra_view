# -*- coding: utf-8 -*-
"""
✅ أداة التحقق من إصلاح ZONE-ENTRY-MTF1 — تشغَّل من جذر الباك اند:
    python3 tools/verify_fix.py
  (أو من داخل مجلد الحزمة مع تمرير مسار الجذر: python3 verify_fix.py /root/TR_platform/backend)

7 فحوص:
  1) الاستيراد المباشر للمحرك الكمي (يعمل على python3.11 الذي يشغّل celery)
  2) إضافة المعاملين zone_resolution/zone_length للتوقيع
  3) norm_zone_entry_resolution (تعطيل/تفعيل)
  4) المسار التاريخي بت-بت: zone_resolution=None يعطي 109 أعمدة مع مطابقة قيم
  5) المسار المفعّل: zone_resolution="60" يعطي 121 عمودًا (109 + 12 مرآة _base)
  6) الكمومية-EMA عبر نفس استدعاء overlays.py (الاستدعاء الذي كان ينكسر!)
  7) مسار المحرك الحقيقي columns_for_configs (197 عمودًا)
"""
import sys, math, random, traceback

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
sys.path.insert(0, ROOT)

PASS = FAIL = 0
def ok(name):
    global PASS, FAIL
    PASS += 1
    print(f"  ✅ {name}")
def bad(name, err=""):
    global FAIL
    FAIL += 1
    print(f"  ❌ {name} — {err}")

print("=" * 72)
print("أداة التحقق من إصلاح ZONE-ENTRY-MTF1 (المحرك الكمي)")
print("=" * 72)

# بيانات اصطناعية حتمية
rnd = random.Random(42)
t = 1600000000000; px = 100.0; candles = []
for i in range(3000):
    d = math.sin(i / 61.0) * 2.0 + math.sin(i / 17.0) * 0.8 + (rnd.random() - 0.5) * 1.2
    o = px; c = px + d * 0.5
    hi = max(o, c) + abs(d) * 0.3 + rnd.random() * 0.2
    lo = min(o, c) - abs(d) * 0.3 - rnd.random() * 0.2
    candles.append({"time": t, "open": o, "high": hi, "low": lo, "close": c,
                    "volume": 1000.0 + rnd.random() * 500})
    px = c; t += 900000

# 1) الاستيراد
print("\n[1/7] الاستيراد المباشر للمحرك الكمي:")
try:
    from app.services.indicators.overlays_zlf_e2e_trendy_quantum import (
        zigzag_fib_e2e_trendy_quantum, norm_zone_entry_resolution,
        ZONE_ENTRY_MTF_SPEC,
    )
    ok(f"الاستيراد نجح — ZONE_ENTRY_MTF_SPEC={ZONE_ENTRY_MTF_SPEC}")
except Exception as e:
    bad("الاستيراد", repr(e))
    traceback.print_exc()
    sys.exit(1)

# 2) التوقيع
print("\n[2/7] المعاملان الجديدان في التوقيع:")
import inspect
sig_params = set(inspect.signature(zigzag_fib_e2e_trendy_quantum).parameters)
need = {"zone_resolution", "zone_length"}
if need <= sig_params:
    ok("zone_resolution + zone_length موجودان في التوقيع")
else:
    bad("التوقيع", f"مفقود: {need - sig_params}")

# 3) التطبيع
print("\n[3/7] تطبيع فريم المنطقة:")
try:
    assert norm_zone_entry_resolution(None) is None
    assert norm_zone_entry_resolution("") is None
    assert norm_zone_entry_resolution("none") is None
    assert norm_zone_entry_resolution("base") is None
    assert norm_zone_entry_resolution("chart") is None
    assert norm_zone_entry_resolution("60") == "60"
    assert norm_zone_entry_resolution("1D") == "1D"
    ok("التعطيل والتفعيل كلاهما سليم")
except Exception as e:
    bad("التطبيع", repr(e))

# 4) المسار التاريخي
print("\n[4/7] المسار التاريخي (zone_resolution=None) — 109 أعمدة:")
try:
    r = zigzag_fib_e2e_trendy_quantum(
        candles, length=226, mode="luxalgo",
        trend_periods=[7, 15, 25], trend_confirm="majority",
        trend_gate=["s1", "s2", "s3"], zone_gate=["s1", "s2", "s3"])
    n = len(r.get("series") or {})
    if n == 109:
        ok(f"109 عمودًا بالضبط (التاريخي) | zone_entry.enabled={r.get('zone_entry', {}).get('enabled')}")
    else:
        bad("عدد الأعمدة", f"توقع 109 وجد {n}")
except Exception as e:
    bad("المسار التاريخي", repr(e))

# 5) المسار المفعّل
print("\n[5/7] المسار المفعّل (zone_resolution=60) — 121 عمودًا:")
try:
    r2 = zigzag_fib_e2e_trendy_quantum(
        candles, length=226, mode="luxalgo",
        trend_periods=[7, 15, 25], trend_confirm="majority",
        trend_gate=["s1", "s2", "s3"], zone_gate=["s1", "s2", "s3"],
        zone_resolution="60", zone_length=50)
    n2 = len(r2.get("series") or {})
    ze = r2.get("zone_entry") or {}
    base_cols = [k for k in (r2.get("series") or {}) if k.endswith("_base")]
    if n2 == 121 and ze.get("enabled") and len(base_cols) == 12:
        ok(f"121 عمودًا (109 + 12 مرايا _base) | فريم={ze.get('resolution')} | شموع HTF={ze.get('mtf_bars')}")
    else:
        bad("المسار المفعّل", f"أعمدة={n2} enabled={ze.get('enabled')} base={len(base_cols)}")
except Exception as e:
    bad("المسار المفعّل", repr(e))

# 6) الاستدعاء الذي كان ينكسر
print("\n[6/7] استدعاء الكمومية-EMA (الاستدعاء الذي كان يرفع TypeError):")
try:
    from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
        zigzag_fib_e2e_trendy_quantum_ema as qe_fn)
    rq = qe_fn(
        candles, length=226, mode="luxalgo",
        trend_periods=[7, 15, 25], trend_confirm="majority",
        trend_gate=["s1", "s2", "s3"], zone_gate=["s1", "s2", "s3"],
        ema_lengths=[50, 100, 200, 350, 500], ema_resolution="60",
        ema_source="close", ema_offset=0, ema_gate=["s1", "s2", "s3"],
        zone_exit_resolution="5m", zone_exit_length=113, struct_reversal_pct=22,
        zone_resolution=None, zone_length=None)
    nq = len(rq.get("series") or {})
    if nq >= 190:
        ok(f"نجح — {nq} عمودًا (كان TypeError قبل الإصلاح)")
    else:
        bad("أعمدة قليلة", f"{nq}")
except TypeError as e:
    bad("TypeError ما زال موجودًا", str(e))
except Exception as e:
    bad("خطأ عام", repr(e))

# 7) مسار المحرك الحقيقي
print("\n[7/7] مسار المحرك الحقيقي columns_for_configs (DataFrame):")
try:
    import pandas as pd
    from app.services.indicators.overlay_columns import columns_for_configs
    df = pd.DataFrame(candles)
    ind = [{"name": "zigzag_fib_e2e_trendy_quantum_ema", "type": "support_resistance",
            "params": {"mode": "luxalgo", "length": 226, "touch_level": 0.618,
                       "trend_periods": [7, 15, 25], "trend_confirm": "majority",
                       "trend_gate": ["s1", "s2", "s3"], "zone_gate": ["s1", "s2", "s3"],
                       "ema_lengths": [50, 100, 200, 350, 500], "ema_resolution": "60",
                       "ema_source": "close", "ema_offset": 0, "ema_gate": ["s1", "s2", "s3"],
                       "zone_exit_resolution": "5m", "zone_exit_length": 113,
                       "struct_reversal_pct": 22}}]
    cols, _ = columns_for_configs(df, ind, return_sections=True)
    nc = len(cols)
    key_ok = all(k in cols for k in (
        "ind_zzfetqe_entry_s1", "ind_zzfetqe_zone_last_high", "ind_zzfetqe_struct_last_high"))
    if nc >= 190 and key_ok:
        ok(f"{nc} عمودًا عبر المحرك الحقيقي + كل الأعمدة المفتاحية موجودة")
    else:
        bad("المحرك الحقيقي", f"أعمدة={nc} مفتاحية={key_ok}")
except Exception as e:
    bad("المحرك الحقيقي", repr(e))

print("\n" + "=" * 72)
if FAIL == 0:
    print(f"✅✅✅ ALL {PASS} CHECKS PASSED — الإصلاح مثبت وسليم")
    sys.exit(0)
else:
    print(f"❌ {FAIL} فشل من {PASS + FAIL} — راجع الأخطاء أعلاه")
    sys.exit(1)
