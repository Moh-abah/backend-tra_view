#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""✅ EMAGATE-UNIFIED — بطارية التحقق الكاملة (بوابة رصة EMA الموحدة).

الفحوص:
L1  الهوية بت-بت للشيفرة الأصلية (المرجع الملتقط قبل التعديل):
    L1a التكوين القياسي الستة [21,50,100,200,350,500] — بت-بت.
    L1b تكوين الجبّارة الخمسة [50,100,200,350,500] (A226) — بت-بت.
    L1c كموميه الزخم الاولى كاملة (بوابة الزخم 46/11/35) — بت-بت.
    L1d الوضع strict (التراجع التاريخي) على التكوين القياسي = المرجع.
L2  دلالات الشروط السبعة (8 سيناريوهات اصطناعية محكمة):
    S1 السريعة (<21) فوق أعلى السلّم لا تكسر البوابة (نص الشرط 2).
    S2 strict على الترتيب المثالي يمر.
    S3 السعر تحت سريعة واحدة = كسر الشرط 1 (السعر فوق الكل).
    S4 كسر زوج واحد (EMA50 فوق EMA21) = عمود الزوج 0 وحده.
    S5 استقلال كامل عن ترتيب تمرير الأطوال (hierarchical يفرز).
    S6 مجموعة جزئية [21,50] («إن وجد») — زوج واحد فقط.
    S7 القاعدة=1 (الكل سلّم — إعفاء لا أحد).
    S8 القاعدة=100 (السلّم 100/200/350/500 والباقي سريعة).
L3  تدفق المعاملات من تكوين الاستراتيجية إلى المحرك:
    config_to_overlay_params + _normalize_overlay_params يمرران
    ema_stack_mode/ema_stack_base حرفياً (فرعا الكمومية-EMA وQMOM1).
L4  القوالب الرسمية: 13 قالباً — كموميه الزخم الاولى (QMOM1) موجودة
    بحمولتها الكاملة (المحرك + الرصة الهرمية الصريحة + شجرة الشروط
    الأربعة) وتتحول نظيفاً عبر config_to_overlay_params — وملاحظتا
    صاحب القرار (2026-11-19): ديفولت length=100 (لا 226) + الرصة
    الكاملة الستة [21,50,100,200,350,500] مع EMA21 الجديدة.
L5  عرض الأعمدة ind_*: التشخيص السبعمعة (price_ok/ladder_ok/
    pair_ok_{a}_{b}) يصل الشارت عبر zzfetqe_* وzzfetqem_* (QMOM1).
L6  لوحة الإعدادات: get_default_params للمؤشرين المسجّلين يكشف
    ema_stack_mode/ema_stack_base (endpoint /{indicator_name}/params)
    وديفولتاتهما length=100 + الستة الكاملة.
"""
import io
import json
import os
import sys

RUNTIME = os.environ.get(
    "EMAGATE_RUNTIME",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))) if os.path.basename(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ) == "tools" else None)
if RUNTIME is None or not os.path.isdir(os.path.join(RUNTIME, "app")):
    RUNTIME = os.environ.get("EMAGATE_RUNTIME", os.getcwd())
DATA = os.environ.get(
    "EMAGATE_DATA",
    "/home/z/my-project/trading-system/zone-exit-ltf/data/MMTUSDT_15m.json")
REFERENCE = os.environ.get(
    "EMAGATE_REFERENCE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 "..", "tools", "reference_basis_outputs.json"))
if not os.path.isfile(REFERENCE):
    REFERENCE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "reference_basis_outputs.json")

sys.path.insert(0, RUNTIME)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), "|", name,
          ("| " + str(detail)) if detail else "")


def close(a, b):
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) <= 1e-12 * max(1.0, abs(fa), abs(fb))
    except (TypeError, ValueError):
        return a == b


def series_equal(new, ref):
    if new is None:
        return False
    if len(new) != len(ref):
        return False
    for a, b in zip(new, ref):
        if (a is None) != (b is None):
            return False
        if a is not None and not close(a, b):
            return False
    return True


# ---------------------------------------------------------------------------
print("=" * 72)
print("✅ EMAGATE-UNIFIED VERIFY — RUNTIME:", RUNTIME)
print("=" * 72)

import pandas as pd  # noqa: E402

# ---------------------------------------------------------------------------
# L2 — دلالات الشروط السبعة (اصطناعية — قبل الحمل الثقيل)
# ---------------------------------------------------------------------------
from app.services.indicators.ema_stack_gate import (  # noqa: E402
    compute_ema_stack_gate)

closes = [110.0, 112.0, 111.0]
EMA = {
    8: [105.0, 106.0, 107.0], 13: [101.0, 101.5, 102.0],
    21: [100.0, 100.5, 101.0], 50: [90.0, 90.5, 91.0],
    100: [80.0, 80.5, 81.0], 200: [70.0, 70.5, 71.0],
    350: [60.0, 60.5, 61.0], 500: [50.0, 50.5, 51.0],
}


def _n(col):
    return sum(1 for v in col if v)


r1 = compute_ema_stack_gate(closes, EMA)
check("S1 السريعة فوق 21 لا تكسر (شرط 2 حرفياً)", _n(r1["ok"]) == 3,
      r1["meta"]["fast_lengths"])
r2 = compute_ema_stack_gate(closes, EMA, mode="strict")
check("S2 strict على الترتيب المثالي يمر", _n(r2["ok"]) == 3)
r3 = compute_ema_stack_gate([104.0, 104.5, 105.0], EMA)
check("S3 السعر تحت سريعة = كسر الشرط 1",
      _n(r3["price_ok"]) == 0 and _n(r3["ladder_ok"]) == 3
      and _n(r3["ok"]) == 0)
ema4 = dict(EMA)
ema4[50] = [102.0, 102.5, 103.0]
r4 = compute_ema_stack_gate(closes, ema4)
check("S4 كسر زوج 21>50: عموده 0 وحده",
      _n(r4["pairs"][0]["ok"]) == 0 and _n(r4["pairs"][1]["ok"]) == 3
      and _n(r4["ok"]) == 0)
ema5 = {k: EMA[k] for k in [500, 8, 350, 13, 200, 50, 100, 21]}
r5 = compute_ema_stack_gate(closes, ema5)
check("S5 استقلال ترتيب التمرير (فرز داخلي)", _n(r5["ok"]) == 3)
r6 = compute_ema_stack_gate(closes, {21: EMA[21], 50: EMA[50]})
check("S6 جزئية 21/50 («إن وجد»)",
      r6["meta"]["pair_labels"] == ["ema_21 > ema_50"] and _n(r6["ok"]) == 3)
r7 = compute_ema_stack_gate(closes, EMA, base=1)
check("S7 القاعدة=1 (الكل سلّم)",
      r7["meta"]["fast_lengths"] == [] and len(r7["meta"]["ladder_lengths"]) == 8)
r8 = compute_ema_stack_gate(closes, EMA, base=100)
check("S8 القاعدة=100 (سلّم 100/200/350/500)",
      r8["meta"]["ladder_lengths"] == [100, 200, 350, 500]
      and _n(r8["ok"]) == 3)

# ---------------------------------------------------------------------------
# البيانات الحقيقية + المرجع
# ---------------------------------------------------------------------------
candles = json.load(io.open(DATA, encoding="utf-8"))
df = pd.DataFrame([{
    "open": float(c["open"]), "high": float(c["high"]),
    "low": float(c["low"]), "close": float(c["close"]),
    "volume": float(c["volume"]),
} for c in candles])
df.index = pd.DatetimeIndex(
    pd.to_datetime([c["time"] for c in candles], unit="ms", utc=True),
    name="time")

from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (  # noqa: E402
    zigzag_fib_e2e_trendy_quantum_ema as qe_engine)
from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema_mom import (  # noqa: E402
    zigzag_fib_e2e_trendy_quantum_ema_mom as qmom_engine)

ref = json.load(io.open(REFERENCE, encoding="utf-8")) if os.path.isfile(
    REFERENCE) else None
if ref is None:
    print("! لا يوجد مرجع — فحوص الهوية L1 تُتخطى (شغّل capture_basis_reference.py)")
else:
    BASE_PARAMS = {
        "mode": "luxalgo", "length": 100,
        "trend_periods": [7, 15, 25], "trend_confirm": "majority",
        "trend_gate": ["s1", "s2", "s3"], "zone_gate": ["s1", "s2", "s3"],
        "ema_resolution": "60", "ema_source": "close", "ema_offset": 0,
    }

    def run_and_compare(tag, params, keys_prefixes=("zzfetqe_",)):
        res = qe_engine(df, **params)
        s = res["series"]
        r = ref[tag]
        bad = []
        for k, rvals in r["series"].items():
            if not series_equal(s.get(k), rvals):
                bad.append(k)
        check(f"L1 {tag} بت-بت", not bad, bad[:3] if bad else "كل الأعمدة")
        return res, s

    res_c, s_c = run_and_compare(
        "canonical_6",
        dict(BASE_PARAMS, ema_lengths=[21, 50, 100, 200, 350, 500],
             ema_gate=["s1", "s2", "s3"]))
    check("L1a-2 التكوين القياسي: 46 دخولاً نهائياً كالمرجع",
          sum(1 for v in s_c.get("zzfetqe_entry") or [] if v) == 46)

    res_a, s_a = run_and_compare(
        "almighty_5",
        dict(BASE_PARAMS, length=226, zone_gate=["s1"],
             ema_lengths=[50, 100, 200, 350, 500],
             ema_gate=["s1", "s2", "s3"]))

    # L1c — QMOM1 كاملة
    qmom_payload = json.load(io.open(os.path.join(
        RUNTIME, "payloads", "payload_qmom1_mmt_10000604.json"),
        encoding="utf-8"))
    qmom_params = qmom_payload["strategy_config"]["indicators"][0]["params"]
    res_q = qmom_engine(df, **qmom_params)
    s_q = res_q["series"]
    r_q = ref["qmom1_full"]
    bad_q = [k for k, rvals in r_q["series"].items()
             if not series_equal(s_q.get(k), rvals)]
    check("L1c كموميه الزخم الاولى كاملة بت-بت", not bad_q,
          bad_q[:3] if bad_q else "46/11/35 محفوظة")
    check("L1c-2 بوابة الزخم 46/11/35",
          (res_q.get("osc") or {}).get("counts") == {
              "quantum_ema_entries": 46, "final_entries": 11,
              "osc_blocked_entries": 35})

    # L1d — strict = التاريخي حرفياً (مفتاح التراجع)
    res_s = qe_engine(df, **dict(
        BASE_PARAMS, ema_lengths=[21, 50, 100, 200, 350, 500],
        ema_gate=["s1", "s2", "s3"], ema_stack_mode="strict"))
    bad_s = [k for k, rvals in ref["canonical_6"]["series"].items()
             if not series_equal(res_s["series"].get(k), rvals)]
    check("L1d strict = الوضع التاريخي بت-بت (تراجع آمن)", not bad_s,
          bad_s[:3] if bad_s else "كل الأعمدة")

# ---------------------------------------------------------------------------
# L3 — تدفق المعاملات (تكوين الاستراتيجية → المحرك)
# ---------------------------------------------------------------------------
from app.services.indicators.overlay_columns import (  # noqa: E402
    config_to_overlay_params)
from app.services.indicators.overlays import _normalize_overlay_params  # noqa: E402

for engine_name, overlay_name in (
        ("zigzag_fib_e2e_trendy_quantum_ema", "zzfib_e2e_trendy_quantum_ema"),
        ("zigzag_fib_e2e_trendy_quantum_ema_mom",
         "zzfib_e2e_trendy_quantum_ema_mom")):
    cfg = {
        "name": engine_name,
        "params": {
            "length": 100, "mode": "luxalgo",
            "trend_periods": [7, 15, 25], "trend_confirm": "majority",
            "trend_gate": ["s1", "s2", "s3"], "zone_gate": ["s1", "s2", "s3"],
            "ema_lengths": [21, 50, 100, 200, 350, 500],
            "ema_resolution": "60", "ema_source": "close",
            "ema_offset": 0, "ema_gate": ["s1", "s2", "s3"],
            "ema_stack_mode": "hierarchical", "ema_stack_base": 21,
        },
    }
    conv = config_to_overlay_params(cfg) or {}
    p = conv.get(overlay_name) or {}
    norm = _normalize_overlay_params(overlay_name, p)
    check(f"L3 تدفق المعاملات ({engine_name.split('_')[-1]})",
          p.get("ema_stack_mode") == "hierarchical"
          and p.get("ema_stack_base") == 21
          and norm.get("ema_stack_mode") == "hierarchical"
          and norm.get("ema_stack_base") == 21)

# ---------------------------------------------------------------------------
# L4 — القوالب الرسمية (get_presets)
# ---------------------------------------------------------------------------
from app.services.strategy.presets import get_presets, QMOM1_TRIPLE_SIGNAL  # noqa: E402

presets = get_presets()
ids = [p.get("id") for p in presets]
check("L4a عدد القوالب = 13", len(presets) == 13, len(presets))
check("L4b قالب كموميه الزخم الاولى موجود",
      "qmom1_quantum_momentum_zero_fee" in ids)
qp = QMOM1_TRIPLE_SIGNAL
qparams = qp["strategy_config"]["indicators"][0]["params"]
check("L4c حمولة QMOM1: المحرك الصحيح",
      qp["strategy_config"]["indicators"][0]["name"]
      == "zigzag_fib_e2e_trendy_quantum_ema_mom")
check("L4d حمولة QMOM1: الرصة الهرمية صريحة",
      qparams.get("ema_stack_mode") == "hierarchical"
      and qparams.get("ema_stack_base") == 21)
check("L4e حمولة QMOM1: 7 نسخ موشرات + شجرة الشروط الأربعة",
      len(qparams.get("osc_instances") or []) == 7
      and len((qparams.get("osc_conditions") or {}).get("conditions") or []) == 4)
conv_q = config_to_overlay_params(
    qp["strategy_config"]["indicators"][0]) or {}
pq = conv_q.get("zzfib_e2e_trendy_quantum_ema_mom") or {}
check("L4f حمولة QMOM1 تتحول نظيفاً (config_to_overlay_params)",
      "osc_instances" in pq and "osc_conditions" in pq
      and pq.get("ema_stack_mode") == "hierarchical")
# ✅ ملاحظة صاحب القرار (2026-11-19): «اجعله ع الديفولت 100» +
# «اذكر ema_lengths كاملة مع الجديدة» — القالب يقف على الديفولت.
check("L4g حمولة QMOM1: ديفولت length=100 (لا 226)",
      qparams.get("length") == 100, qparams.get("length"))
check("L4h حمولة QMOM1: الرصة الكاملة الستة مع EMA21 الجديدة",
      qparams.get("ema_lengths") == [21, 50, 100, 200, 350, 500],
      qparams.get("ema_lengths"))

# ---------------------------------------------------------------------------
# L5 — عرض الأعمدة ind_* (المسار الحي)
# ---------------------------------------------------------------------------
new_cols = ["zzfetqe_ema_stack_price_ok", "zzfetqe_ema_stack_ladder_ok",
            "zzfetqe_ema_stack_pair_ok_21_50",
            "zzfetqe_ema_stack_pair_ok_50_100",
            "zzfetqe_ema_stack_pair_ok_100_200",
            "zzfetqe_ema_stack_pair_ok_200_350",
            "zzfetqe_ema_stack_pair_ok_350_500"]
have = [c for c in new_cols if c in s_c]
check("L5a التشخيص السبعمعة في سلاسل المحرك (7 أعمدة)", len(have) == 7,
      len(have))

from app.services.indicators.overlay_columns import (  # noqa: E402
    _zzfetqe_columns, _zzfetqem_columns)
ind_qe = _zzfetqe_columns({"series": {c: s_c.get(c) for c in new_cols}})
check("L5b ind_zzfetqe_ema_stack_{price_ok,ladder_ok,pair_ok_*} تصل الشارت",
      all(("ind_" + c) in ind_qe for c in new_cols))
ind_qem = _zzfetqem_columns({"series": {
    c.replace("zzfetqe_", "zzfetqem_"): s_c.get(c) for c in new_cols}})
check("L5c مرآة QMOM1 ind_zzfetqem_ema_stack_* تصل الشارت",
      all(("ind_" + c.replace("zzfetqe_", "zzfetqem_")) in ind_qem
          for c in new_cols))

# ---------------------------------------------------------------------------
# L6 — لوحة الإعدادات (endpoint /{indicator_name}/params)
# ---------------------------------------------------------------------------
try:
    from app.services.indicators.registry import IndicatorRegistry  # noqa: E402
    import app.services.indicators  # noqa: F401,E402  (استيراد التسجيل الذاتي)

    for name in ("zigzag_fib_e2e_trendy_quantum_ema",
                 "zigzag_fib_e2e_trendy_quantum_ema_mom"):
        info = IndicatorRegistry.get_indicator_info(name)
        dp = (info.default_params if info else None) or {}
        check(f"L6 لوحة إعدادات {name.split('_')[-1]} يكشف المفتاحين الجديدين",
              dp.get("ema_stack_mode") == "hierarchical"
              and dp.get("ema_stack_base") == 21)
        # ✅ الديفولت 100 + الرصة الكاملة الستة (كموميه الزخم الاولى أيضاً)
        check(f"L6b ديفولتات {name.split('_')[-1]}: length=100 + الستة الكاملة",
              dp.get("length") == 100
              and dp.get("ema_lengths") == [21, 50, 100, 200, 350, 500],
              (dp.get("length"), dp.get("ema_lengths")))
except Exception as e:  # noqa: BLE001
    check("L6 لوحة الإعدادات (تسجيل)", False, str(e)[:80])

# ---------------------------------------------------------------------------
print("=" * 72)
print(f"النتيجة: {len(PASS)} PASS · {len(FAIL)} FAIL")
if FAIL:
    print("FAILED:", FAIL)
sys.exit(1 if FAIL else 0)
