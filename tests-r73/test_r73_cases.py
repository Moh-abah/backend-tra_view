#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بطارية اختبار PRO73-R3 — الحالات الخاصة المسمّاة + نسخ المستند الكاملة.

الأقسام:
  G) نسخ المستند الكاملة (osc_cases): الأعداد (28/16/23=67) · تطبيع نظيف بلا
     تحذيرات · تغطية الفريمات الـ14 · مطابقة معاملات المستند حرفياً (نقاط
     تحديد) · حقول RSI الأربعة (value/ma/bb_upper/bb_lower).
  H) دلالة كل حالة من الحالات الثلاث عشرة بت-بت: لكل حالة شجرة تُقيَّم على
     سلاسل مُحكمة يدوياً — سيناريو مُحقق وسيناريوهات نفي دقيقة (التراصب،
     العتبات، الاتجاه، الاختراق).
  I) skip_unavailable + البولينجر: تجاوز النسخ غير المتاحة (فريم أدنى من
     القاعدة) مع بقاء الفشل المغلق للمرجع المجهول · رياضيات BB حول RSI ·
     حالة «جميع الفريمات ايجابية» على قاعدة 1h مع فريمات أدنى مفقودة.
  J) التكامل على نافذة SOL الحقيقية (نافذة R69.2): تقييم الحالات الـ13 عبر
     النواة نفسها + الوحدات الست (أي حالة / انطباق العائلات / إنذار مبكر).
  K) القالبان الرسميان: البوابة الافتراضية = «أي حالة لحظية» (OR بثلاث
     عائلات) والنسخ = المستند الكامل 67.
"""
import json
import os
import sys
import time
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [os.path.join(HERE, ".."), os.path.join(HERE, "..", "src"), HERE]
SRC = next((p for p in CANDIDATES
            if os.path.isfile(os.path.join(p, "app", "services", "indicators", "mtf_oscillator_core.py"))),
           CANDIDATES[0])
sys.path.insert(0, os.path.abspath(SRC))

os.environ.setdefault("SECRET_KEY", "battery-only-secret-key-0123456789abcdef")
os.environ.setdefault("DEBUG", "true")

import numpy as np  # noqa: E402

from app.services.indicators.mtf_oscillator_core import (  # noqa: E402
    TF_ORDER, TF_REGISTRY, OSC_KIND_FIELDS,
    compute_oscillator_matrix, evaluate_osc_conditions,
    normalize_osc_conditions, normalize_osc_instances,
)
from app.services.indicators.osc_cases import (  # noqa: E402
    OSC_DOC_INSTANCES, OSC_DOC_INSTANCE_IDS, OSC_CASE_LIBRARY, OSC_CASE_CATALOG,
    collect_case_refs, get_case_tree,
    MASTER_ANY_CASE, MASTER_STRICT, EARLY_WATCH,
)

PASS = 0
FAIL = 0
FAILURES = []
EVID = {"sections": {}}


def check(name: str, cond: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
    return cond


def section(title: str):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


T0_ALL = time.perf_counter()


def _p():
    return PASS


def _f():
    return FAIL


# ===========================================================================
section("G) نسخ المستند الكاملة — العدد والتطبيع والمطابقة الحرفية")

from collections import Counter  # noqa: E402
kind_counts = Counter(x["kind"] for x in OSC_DOC_INSTANCES)
check("G1 الأعداد: MACD×28 + RSI×16 + Mom×23 = 67",
      kind_counts.get("macd") == 28 and kind_counts.get("rsi") == 16 and kind_counts.get("mom") == 23,
      f"{dict(kind_counts)}")
insts_norm, w_norm = normalize_osc_instances(OSC_DOC_INSTANCES)
check("G2 التطبيع نظيف تماماً (صفر تحذيرات)", not w_norm, str(w_norm[:3]))
ids_norm = {i["id"] for i in insts_norm}
check("G3 المعرفات فريدة ومحفوظة بعد التطبيع", ids_norm == OSC_DOC_INSTANCE_IDS,
      f"{len(ids_norm)} معرف")
tfs_covered = {x["timeframe"] for x in OSC_DOC_INSTANCES}
check("G4 الفريمات الـ14 كلها مغطاة", tfs_covered == set(TF_ORDER),
      f"مفقود: {set(TF_ORDER) - tfs_covered}")


def _inst(iid):
    return next(x for x in OSC_DOC_INSTANCES if x["id"] == iid)


spot = {
    "macd_1d_12_26_4": {"fast": 12, "slow": 26, "signal": 4},
    "macd_1d_6_13_4": {"fast": 6, "slow": 13, "signal": 4},
    "macd_3d_5_11_4": {"fast": 5, "slow": 11, "signal": 4},
    "macd_3d_6_13_4": {"fast": 6, "slow": 13, "signal": 4},
    "macd_3d_12_26_4": {"fast": 12, "slow": 26, "signal": 4},
    "macd_1w_18_39_4": {"fast": 18, "slow": 39, "signal": 4},
    "macd_2w_12_26_2": {"fast": 12, "slow": 26, "signal": 2},
    "macd_1mo_12_26_2": {"fast": 12, "slow": 26, "signal": 2},
}
ok_spot = all(all(_inst(k).get(p) == v for p, v in want.items()) for k, want in spot.items())
check("G5 مطابقة معاملات MACD حرفياً من المستند (8 نقاط تحديد)", ok_spot,
      "؛ ".join(f"{k}={_inst(k).get('fast')}/{_inst(k).get('slow')}/{_inst(k).get('signal')}" for k in spot))
spot_rsi = {
    "rsi_1d_10_14": (10, 14), "rsi_1d_14_14": (14, 14),
    "rsi_2d_14_6": (14, 6), "rsi_2d_14_14": (14, 14),
    "rsi_3d_14_6": (14, 6), "rsi_1w_14_14": (14, 14), "rsi_1mo_14_14": (14, 14),
}
ok_rsi = all((_inst(k).get("period"), _inst(k).get("ma_length")) == v for k, v in spot_rsi.items())
ok_rsi = ok_rsi and all(x.get("bb_std") == 2 for x in OSC_DOC_INSTANCES if x["kind"] == "rsi")
check("G6 مطابقة RSI من المستند (Length/MA لكل النقاط + BB StdDev=2 للجميع)", ok_rsi)
spot_mom = {"mom_1w_5": 5, "mom_1w_10": 10, "mom_3d_10": 10, "mom_3d_5": 5,
            "mom_1m_5": 5, "mom_1s_10": 10}
ok_mom = all(_inst(k).get("length") == v for k, v in spot_mom.items())
check("G7 مطابقة Momentum من المستند (Length — نقاط تحديد)", ok_mom)
check("G8 حقول RSI الأربعة (value/ma/bb_upper/bb_lower — PRO73-R3)",
      OSC_KIND_FIELDS["rsi"] == ("value", "ma", "bb_upper", "bb_lower"))
check("G9 فهرس الحالات: 13 حالة + 6 وحدات ماكرو = 19",
      len(OSC_CASE_LIBRARY) == 13 and len(OSC_CASE_CATALOG) == 19)
bad_refs = []
for case in OSC_CASE_LIBRARY:
    for r in collect_case_refs(case["tree"]):
        iid = r.split(":", 1)[1].split(".", 1)[0]
        if iid not in OSC_DOC_INSTANCE_IDS:
            bad_refs.append((case["id"], iid))
check("G10 كل مراجع الحالات الـ13 تحلّ ضد نسخ المستند (لا مرجع مكسور)",
      not bad_refs, str(bad_refs[:3]))

EVID["sections"]["G_doc_defaults"] = {
    "pass": PASS - _p(), "fail": FAIL - _f(),
    "counts": dict(kind_counts), "total": len(OSC_DOC_INSTANCES),
}
_pG = lambda: _p()  # noqa: E731
_fG = lambda: _f()  # noqa: E731


# ===========================================================================
section("H) دلالة الحالات الثلاث عشرة بت-بت (سلاسل مُحكمة يدوياً)")

NBARS = 4
ONES = np.ones(NBARS)
PRICE = {"open": ONES, "high": ONES, "low": ONES, "close": ONES}


def _series_for(case_id: str, values: dict):
    """سلاسل مُحكمة لكل مراجع الحالة — القيم ثابتة على كل الشموع."""
    tree = get_case_tree(case_id)
    refs = collect_case_refs(tree)
    osc = {}
    for r in refs:
        iid, field = r.split(":", 1)[1].split(".", 1)
        val = values.get(iid, 0.0)
        osc.setdefault(iid, {})[field] = np.full(NBARS, float(val))
    return tree, osc


def _eval(case_id: str, values: dict, avail=None):
    tree, osc = _series_for(case_id, values)
    t, w = normalize_osc_conditions(tree)
    assert not w, f"تحذيرات غير متوقعة في {case_id}: {w[:2]}"
    g, _ = evaluate_osc_conditions(t, osc, PRICE["open"], PRICE["high"],
                                   PRICE["low"], PRICE["close"], NBARS,
                                   osc_available=avail)
    return bool(g.all())


def _macd_values(**over):
    vals = {iid: 5.0 for iid in OSC_DOC_INSTANCE_IDS if iid.startswith("macd_")}
    vals.update(over)
    return vals


def _mom_values(**over):
    vals = {iid: 1.0 for iid in OSC_DOC_INSTANCE_IDS if iid.startswith("mom_")}
    vals.update(over)
    return vals


# — ماكد 1: جميع الفريمات ايجابية —
v = _macd_values()
check("H1 ماكد1: كل الخطوط موجبة → الحالة تحققت", _eval("macd_case1_all_tfs_positive", v))
check("H1b ماكد1: فريم واحد سالب → لم تتحقق",
      not _eval("macd_case1_all_tfs_positive", _macd_values(**{"macd_4h_12_26_4": -1.0})))

# — ماكد 2: اختراق 4h للصفر صعوداً (حدث وليس حالة) —
cross_vals = {"macd_4h_6_13_4": 1.0}
tree, osc = _series_for("macd_case2_4h_zero_cross_up", cross_vals)
osc["macd_4h_6_13_4"]["line"] = np.array([-1.0, -1.0, 1.0, 1.0])   # اختراق عند الشمعة 2
osc["macd_4h_12_26_4"]["line"] = np.full(NBARS, -5.0)
t2, w2 = normalize_osc_conditions(tree)
g2, _ = evaluate_osc_conditions(t2, osc, ONES, ONES, ONES, ONES, NBARS)
check("H2 ماكد2: خط 4h اخترق الصفر لأعلى → حدث الاختراق بالضبط عند شمعته",
      list(g2) == [False, False, True, False], str(list(g2)))
g2b, _ = evaluate_osc_conditions(
    normalize_osc_conditions(get_case_tree("macd_case2_4h_zero_cross_up"))[0],
    {"macd_4h_6_13_4": {"line": np.full(NBARS, 5.0)},
     "macd_4h_12_26_4": {"line": np.full(NBARS, -5.0)}}, ONES, ONES, ONES, ONES, NBARS)
check("H2b ماكد2: خط فوق الصفر من البداية (لا اختراق) → لا إشارة", not g2b.any())

# — ماكد 3: خطا 3 أيام فوق خط 1 يوم —
check("H3 ماكد3: 3d(6/13/4) فوق 1d(12/26/4) → تحققت",
      _eval("macd_case3_3d_above_1d", {"macd_3d_6_13_4": 5.0, "macd_3d_5_11_4": -5.0,
                                       "macd_1d_12_26_4": 1.0}))
check("H3b ماكد3: 3d(5/11/4) وحده فوق 1d → تحققت (أحدهما يكفي)",
      _eval("macd_case3_3d_above_1d", {"macd_3d_6_13_4": -5.0, "macd_3d_5_11_4": 2.0,
                                       "macd_1d_12_26_4": 1.0}))
check("H3c ماكد3: كلاهما تحت 1d → لم تتحقق",
      not _eval("macd_case3_3d_above_1d", {"macd_3d_6_13_4": 0.5, "macd_3d_5_11_4": 0.5,
                                           "macd_1d_12_26_4": 1.0}))

# — ماكد 4: تراصب الأكبر فوق الأصغر مع الأمثلة أ/ب —
stack_ok = {
    "macd_1w_6_13_4": 9.0, "macd_3d_6_13_4": 7.0, "macd_3d_5_11_4": 6.0,
    "macd_1d_6_13_4": 4.0, "macd_4h_6_13_4": 3.0, "macd_1h_6_13_4": 2.0, "macd_15m_6_13_4": 1.0,
}
check("H4 ماكد4: التراصب الكامل (أسبوع ← 3d ← 1d ← 4h ← 1h ← 15m) موجب → تحققت",
      _eval("macd_case4_htf_dominance", stack_ok))
check("H4b ماكد4: كسر حلقة واحدة (4h فوق 1d) → لم تتحقق",
      not _eval("macd_case4_htf_dominance", dict(stack_ok, macd_4h_6_13_4=4.5)))
check("H4c ماكد4: سلبية 3d(5/11/4) (مثال ب) → لم تتحقق",
      not _eval("macd_case4_htf_dominance", dict(stack_ok, macd_3d_5_11_4=-1.0)))

# — ماكد 5: الترص العكسي تحت الصفر (إنذار مبكر) —
deep_ok = {"macd_3d_6_13_4": -1.0, "macd_1d_12_26_4": -2.0, "macd_4h_12_26_4": -3.0}
check("H5 ماكد5: 3d > 1d > 4h وكلهم تحت الصفر → إنذار مبكر تحقق",
      _eval("macd_case5_deep_negative_stack", deep_ok))
check("H5b ماكد5: 4h موجب → لا إنذار",
      not _eval("macd_case5_deep_negative_stack", dict(deep_ok, macd_4h_12_26_4=1.0)))
check("H5c ماكد5: ترتيب مقلوب → لا إنذار",
      not _eval("macd_case5_deep_negative_stack",
                {"macd_3d_6_13_4": -3.0, "macd_1d_12_26_4": -2.0, "macd_4h_12_26_4": -1.0}))

# — آر إس آي 1 —
check("H6 RSI1: أحد خطي 1d فوق 50 → تحققت",
      _eval("rsi_case1_1d_over_50", {"rsi_1d_10_14": 55.0, "rsi_1d_14_14": 45.0}))
check("H6b RSI1: كلاهما تحت 50 → لم تتحقق",
      not _eval("rsi_case1_1d_over_50", {"rsi_1d_10_14": 49.9, "rsi_1d_14_14": 45.0}))
check("H6c RSI1: الحد 50 نفسه ليس «تجاوزاً» (>)",
      not _eval("rsi_case1_1d_over_50", {"rsi_1d_10_14": 50.0, "rsi_1d_14_14": 50.0}))

# — آر إس آي 2 —
check("H7 RSI2: 3d=45 فوق 40 وليس فوق خط 1d (الأصغر أعلى) → تحققت",
      _eval("rsi_case2_3d_over_40_not_on_top", {"rsi_3d_14_6": 45.0, "rsi_1d_10_14": 50.0}))
check("H7b RSI2: 3d فوق خط أصغر منه (ترتيب خاطئ) → لم تتحقق",
      not _eval("rsi_case2_3d_over_40_not_on_top", {"rsi_3d_14_6": 55.0, "rsi_1d_10_14": 50.0}))
check("H7c RSI2: 3d تحت 40 → لم تتحقق",
      not _eval("rsi_case2_3d_over_40_not_on_top", {"rsi_3d_14_6": 39.9, "rsi_1d_10_14": 50.0}))

# — آر إس آي 3: الترص بين 50 و 60 —
zone_ok = {"rsi_1h_14_14": 55.0, "rsi_4h_14_14": 53.0, "rsi_1d_14_14": 51.0}
check("H8 RSI3: 1h > 4h > 1d كلهم بين 50-60 → تحققت",
      _eval("rsi_case3_stack_50_60", zone_ok))
check("H8b RSI3: 4h خارج النطاق (48) → لم تتحقق",
      not _eval("rsi_case3_stack_50_60", dict(zone_ok, rsi_4h_14_14=48.0)))
check("H8c RSI3: ترتيب مقلوب (1h تحت 4h) → لم تتحقق",
      not _eval("rsi_case3_stack_50_60", dict(zone_ok, rsi_1h_14_14=52.0)))
check("H8d RSI3: فوق 60 → لم تتحقق",
      not _eval("rsi_case3_stack_50_60", dict(zone_ok, rsi_1h_14_14=61.0, rsi_4h_14_14=59.0)))

# — آر إس آي 4: الأصغر فوق الأكبر (الترتيب الصحي) —
small_top = {"rsi_1h_14_14": 60.0, "rsi_4h_14_14": 55.0, "rsi_1d_14_14": 52.0,
             "rsi_2d_14_14": 50.0, "rsi_3d_14_6": 48.0, "rsi_1w_14_14": 45.0}
check("H9 RSI4: سلسلة الأصغر فوق الأكبر (1h→…→1w) → تحققت",
      _eval("rsi_case4_small_on_top_stack", small_top))
check("H9b RSI4: كسر حلقة (2d تحت 3d) → لم تتحقق",
      not _eval("rsi_case4_small_on_top_stack", dict(small_top, rsi_2d_14_14=47.0)))

# — آر إس آي 5: الترص العكسي تحت 50 (إنذار مبكر) —
rev_ok = {"rsi_1w_14_14": 45.0, "rsi_3d_14_6": 42.0, "rsi_2d_14_14": 40.0, "rsi_1d_14_14": 38.0}
check("H10 RSI5: الأكبر فوق الأصغر وكلهم تحت 50 → إنذار تحقق",
      _eval("rsi_case5_reverse_below_50", rev_ok))
check("H10b RSI5: الأسبوعي فوق 50 → لا إنذار",
      not _eval("rsi_case5_reverse_below_50", dict(rev_ok, rsi_1w_14_14=55.0)))
check("H10c RSI5: ترتيب صحيح (الأصغر أعلى) → لا إنذار",
      not _eval("rsi_case5_reverse_below_50",
                {"rsi_1w_14_14": 38.0, "rsi_3d_14_6": 40.0, "rsi_2d_14_14": 42.0, "rsi_1d_14_14": 45.0}))

# — مومنتم 1 —
check("H11 Mom1: 1w(طول5) فوق 3d(طول10) → تحققت",
      _eval("mom_case1_1w_over_3d", {"mom_1w_5": 10.0, "mom_3d_10": 5.0}))
check("H11b Mom1: 1w تحت 3d → لم تتحقق",
      not _eval("mom_case1_1w_over_3d", {"mom_1w_5": 4.9, "mom_3d_10": 5.0}))

# — مومنتم 2 —
check("H12 Mom2: كل الفريمات فوق الصفر → تحققت", _eval("mom_case2_all_above_zero", _mom_values()))
check("H12b Mom2: فريم واحد تحت الصفر → لم تتحقق",
      not _eval("mom_case2_all_above_zero", _mom_values(**{"mom_1d_5": -0.1})))

# — مومنتم 3 —
mom_stack = {"mom_1w_5": 9.0, "mom_3d_10": 7.0, "mom_2d_10": 5.0,
             "mom_1d_10": 3.0, "mom_4h_10": 2.0, "mom_1h_10": 1.0}
check("H13 Mom3: تراصب الأكبر فوق الأصغر → تحققت",
      _eval("mom_case3_large_on_top_stack", mom_stack))
check("H13b Mom3: كسر حلقة (1d فوق 2d) → لم تتحقق",
      not _eval("mom_case3_large_on_top_stack", dict(mom_stack, mom_1d_10=6.0)))

EVID["sections"]["H_case_semantics"] = {"pass": PASS - _pG(), "fail": FAIL - _fG()}
_pH = lambda: _p()  # noqa: E731
_fH = lambda: _f()  # noqa: E731


# ===========================================================================
section("I) skip_unavailable + البولينجر (BB) — آلية «جميع الفريمات» على أي عمق بيانات")

# I1/I2: ورقة بفريم أدنى من القاعدة → تجاوز عند العلم، فشل مغلق بدونه
leaf_skip = normalize_osc_conditions(
    {"left": "osc:macd_1s_6_13_4.line", "op": ">", "right": 0, "skip_unavailable": True})[0]
leaf_noskip = normalize_osc_conditions(
    {"left": "osc:macd_1s_6_13_4.line", "op": ">", "right": 0})[0]
osc_tiny = {"macd_1s_6_13_4": {"line": np.full(NBARS, np.nan)}}   # غير متاحة → كل NaN
g_skip, _ = evaluate_osc_conditions(leaf_skip, osc_tiny, ONES, ONES, ONES, ONES, NBARS,
                                    osc_available={"macd_1s_6_13_4": False})
g_noskip, _ = evaluate_osc_conditions(leaf_noskip, osc_tiny, ONES, ONES, ONES, ONES, NBARS,
                                      osc_available={"macd_1s_6_13_4": False})
check("I1 skip_unavailable=true + نسخة غير متاحة → الورقة مُحققة (تجاوز)", bool(g_skip.all()))
check("I2 بلا علم → فشل مغلق (NaN → False)", not g_noskip.any())
g_typo, _ = evaluate_osc_conditions(leaf_skip, osc_tiny, ONES, ONES, ONES, ONES, NBARS,
                                    osc_available={"macd_1s_typo": False})
check("I3 مرجع مجهول (خطأ إملائي) يبقى فشلاً مغلقاً حتى مع العلم", not g_typo.any())
g_avail, _ = evaluate_osc_conditions(leaf_skip, {"macd_1s_6_13_4": {"line": np.array([np.nan, 1.0, 1.0, 1.0])}},
                                     ONES, ONES, ONES, ONES, NBARS,
                                     osc_available={"macd_1s_6_13_4": True})
check("I4 نسخة متاحة مع إحماء NaN: العلم لا يتجاوز الإحماء (الشمعة 0 False)",
      list(g_avail) == [False, True, True, True], str(list(g_avail)))

# I5: رياضيات BB حول RSI على سلسلة مركّبة
rs_bb = compute_oscillator_matrix(
    [{"time": 1690000000000 + i * 3_600_000, "open": 100.0 + i, "high": 101.0 + i,
      "low": 99.0 + i, "close": 100.0 + i, "volume": 1.0} for i in range(80)],
    [{"kind": "rsi", "id": "r", "timeframe": "1h", "period": 14, "ma_length": 5, "bb_std": 2.0}],
)
s_r = rs_bb["series"]["r"]
check("I5 حقول RSI الأربعة موجودة في مصفوفة النواة",
      set(s_r.keys()) == {"value", "ma", "bb_upper", "bb_lower"})
nn_upper = [x for x in s_r["bb_upper"] if x is not None]
check("I6 البولينجر محسوب بعد الإحماء (value من 14 · ma/bb من 14+5-1)",
      len(nn_upper) == 80 - 18, f"غير فارغة: {len(nn_upper)}")
i0 = next(i for i, x in enumerate(s_r["ma"]) if x is not None)
ok_band = all(s_r["bb_lower"][i] <= s_r["ma"][i] <= s_r["bb_upper"][i] for i in range(i0, 80))
check("I7 الـma بين الحدين دائماً (bb = ma ± k·stdev)", ok_band)
bb_width_ok = all(abs((s_r["bb_upper"][i] - s_r["ma"][i]) - (s_r["ma"][i] - s_r["bb_lower"][i])) < 1e-9
                  for i in range(i0, 80))
check("I8 النطاق متناظر حول الـma", bb_width_ok)

# I9: حالة «جميع الفريمات ايجابية» على قاعدة 1h — الفريمات الأدنى تُتجاوز والعليا موجبة
rng = np.random.default_rng(11)
syn_1h = []
p = 50.0
for i in range(9600):   # 400 يوم على قاعدة 1h
    p *= (1.0 + rng.normal(0.0012, 0.01))
    syn_1h.append({"time": 1672531200000 + i * 3_600_000, "open": p, "high": p * 1.01,
                   "low": p * 0.99, "close": p, "volume": 1.0})
case1_tree = get_case_tree("macd_case1_all_tfs_positive")
m_syn = compute_oscillator_matrix(syn_1h, OSC_DOC_INSTANCES)
avail_syn = {str(rep["id"]): bool(rep.get("available", True)) for rep in m_syn["instances"]}
n_unavail = sum(1 for v in avail_syn.values() if not v)
osc_syn = {iid: {f: np.asarray([np.nan if x is None else float(x) for x in vals])
                 for f, vals in fields.items()}
           for iid, fields in (m_syn["series"] or {}).items()}
o_syn = np.asarray([x["open"] for x in syn_1h])
h_syn = np.asarray([x["high"] for x in syn_1h])
l_syn = np.asarray([x["low"] for x in syn_1h])
c_syn = np.asarray([x["close"] for x in syn_1h])
g_case1, w_case1 = evaluate_osc_conditions(case1_tree, osc_syn, o_syn, h_syn, l_syn, c_syn,
                                           len(syn_1h), osc_available=avail_syn)
case1_noskip_tree, _ = normalize_osc_conditions(
    {"logic": "and", "conditions": [
        {"left": f"osc:{iid}.line", "op": ">", "right": 0}
        for iid in (x["id"] for x in OSC_DOC_INSTANCES if x["kind"] == "macd")]})
g_case1_ns, _ = evaluate_osc_conditions(case1_noskip_tree, osc_syn, o_syn, h_syn, l_syn, c_syn,
                                        len(syn_1h), osc_available=avail_syn)
check("I9 على قاعدة 1h: الفريمات الأدنى (1s/5s/30s/1m/5m/15m/…) غير متاحة وتُتجاوز بالعلم",
      n_unavail > 0 and int(g_case1.sum()) > 0,
      f"غير متاحة: {n_unavail} نسخة · إصابات الحالة: {int(g_case1.sum())}")
check("I10 نفس الحالة بلا علم → مستحيلة رياضياً على هذه القاعدة (فشل مغلق)",
      int(g_case1_ns.sum()) == 0)

EVID["sections"]["I_skip_bb"] = {
    "pass": PASS - _pH(), "fail": FAIL - _fH(),
    "synthetic_base": "1h", "synthetic_bars": len(syn_1h),
    "unavailable_instances": n_unavail,
    "case1_hits_with_skip": int(g_case1.sum()),
    "case1_hits_without_skip": int(g_case1_ns.sum()),
}
_pI = lambda: _p()  # noqa: E731
_fI = lambda: _f()  # noqa: E731


# ===========================================================================
section("J) التكامل على نافذة SOL الحقيقية (R69.2) — الحالات عبر النواة نفسها")

DATA_CANDIDATES = [
    "/home/z/my-project/r70-workspace/data/SOLUSDT_1m.npz",
    os.path.join(HERE, "..", "..", "..", "r70-workspace", "data", "SOLUSDT_1m.npz"),
]
DATA_PATH = next((p for p in DATA_CANDIDATES if os.path.isfile(p)), None)
if DATA_PATH is None:
    print("⚠️ بيانات SOL غير موجودة — القسم J يُتخطى")
else:
    W_FROM = int(_dt.datetime(2023, 9, 1, tzinfo=_dt.timezone.utc).timestamp() * 1000)
    W_TO = int(_dt.datetime(2023, 11, 8, tzinfo=_dt.timezone.utc).timestamp() * 1000)
    z = np.load(DATA_PATH)
    t = z["time_ms"].astype(np.int64)
    m = (t >= W_FROM) & (t < W_TO)
    T = t[m]
    O = z["open"][m].astype(np.float64)
    H = z["high"][m].astype(np.float64)
    L = z["low"][m].astype(np.float64)
    C = z["close"][m].astype(np.float64)
    V = z["volume"][m].astype(np.float64)
    candles = [{"time": int(T[i]), "open": float(O[i]), "high": float(H[i]),
                "low": float(L[i]), "close": float(C[i]), "volume": float(V[i])}
               for i in range(len(T))]
    tJ = time.perf_counter()
    matrix = compute_oscillator_matrix(candles, OSC_DOC_INSTANCES)
    nJ = len(T)
    osc_np = {iid: {f: np.asarray([np.nan if x is None else float(x) for x in vals])
                    for f, vals in fields.items()}
              for iid, fields in (matrix["series"] or {}).items()}
    avail = {str(rep["id"]): bool(rep.get("available", True)) for rep in matrix["instances"]}
    case_hits = {}
    for case in OSC_CASE_LIBRARY:
        tree, _ = normalize_osc_conditions(case["tree"])
        g, _ = evaluate_osc_conditions(tree, osc_np, O, H, L, C, nJ, osc_available=avail)
        case_hits[case["id"]] = int(g.sum())
    elJ = time.perf_counter() - tJ
    hits_any = sum(1 for v in case_hits.values() if v > 0)
    check("J1 الحالات تُقيَّم عبر النواة على النافذة الحقيقية (≥ 5 حالات بإصابات)",
          hits_any >= 5, f"حالات بإصابات: {hits_any}/13 · زمن {elJ:.1f}s")
    check("J2 نافذة صاعدة: rsi_case1 (خطا 1d فوق 50) واسعة الانتشار",
          case_hits.get("rsi_case1_1d_over_50", 0) > nJ * 0.5,
          f"{case_hits.get('rsi_case1_1d_over_50', 0):,} شمعة")
    check("J3 macd_case3 (3d فوق 1d) إصابات معتبرة",
          case_hits.get("macd_case3_3d_above_1d", 0) > nJ * 0.1,
          f"{case_hits.get('macd_case3_3d_above_1d', 0):,}")
    check("J4 macd_case2 (اختراق 4h للصفر) أحداث قليلة منطقية (عبور وليس حالة)",
          0 < case_hits.get("macd_case2_4h_zero_cross_up", 0) < 200,
          f"{case_hits.get('macd_case2_4h_zero_cross_up', 0)} حدثاً")
    check("J5 الفريمات الأدنى من 1m غير متاحة على القاعدة (تُتجاوز في حالة «الكل»)",
          sum(1 for v in avail.values() if not v) == 12,
          f"غير متاحة: {sum(1 for v in avail.values() if not v)} (المتوقع 12: 1s/5s/30s × 4)")
    # الوحدات الست تُقيَّم أيضاً بلا تحذيرات
    macros_ok = True
    macro_hits = {}
    for entry in OSC_CASE_CATALOG:
        if entry["kind"] != "macro":
            continue
        tree, w = normalize_osc_conditions(entry["tree"])
        if w:
            macros_ok = False
        g, _ = evaluate_osc_conditions(tree, osc_np, O, H, L, C, nJ, osc_available=avail)
        macro_hits[entry["id"]] = int(g.sum())
    check("J6 الوحدات الست (أي حالة/انطباق العائلات/إنذار مبكر…) تتقيّم بلا تحذيرات",
          macros_ok, str(macro_hits))
    check("J7 master_strict ⊆ master_any (انطباق العائلات أضيق من أي حالة)",
          macro_hits.get("master_strict", 0) <= macro_hits.get("master_any_case", 0),
          f"strict={macro_hits.get('master_strict', 0):,} · any={macro_hits.get('master_any_case', 0):,}")
    EVID["sections"]["J_real_window"] = {
        "pass": PASS - _pI(), "fail": FAIL - _fI(),
        "window": {"from": W_FROM, "to": W_TO, "bars": nJ},
        "matrix_elapsed_s": round(elJ, 2),
        "case_hits": case_hits, "macro_hits": macro_hits,
    }

_pJ = lambda: _p()  # noqa: E731
_fJ = lambda: _f()  # noqa: E731


# ===========================================================================
section("K) القالبان الرسميان — بوابة «أي حالة لحظية» + نسخ المستند")

from app.services.strategy.presets import TRENDY_MACDIZED, BLAZING_MACDIZED  # noqa: E402

p_tm = TRENDY_MACDIZED["strategy_config"]["indicators"][0]["params"]
p_bm = BLAZING_MACDIZED["strategy_config"]["indicators"][0]["params"]
check("K1 القالبان يحملان نسخ المستند الكاملة (67/67)",
      len(p_tm["osc_instances"]) == 67 and len(p_bm["osc_instances"]) == 67)
gate_tm = p_tm["osc_conditions"]
check("K2 البوابة الافتراضية = «أي حالة لحظية» (OR بثلاث عائلات)",
      gate_tm["logic"] == "or" and len(gate_tm["conditions"]) == 3
      and all(c["logic"] == "or" for c in gate_tm["conditions"]))
check("K3 عائلات البوابة: ماكد (4 حالات) · آر إس آي (4) · مومنتم (3)",
      [len(c["conditions"]) for c in gate_tm["conditions"]] == [4, 4, 3])
import json as _json_lib  # noqa: E402
lib_sigs = {_json_lib.dumps(c["tree"], sort_keys=True, default=str): c["id"]
             for c in OSC_CASE_LIBRARY}
ids_in_gate = set()
for fam in gate_tm["conditions"]:
    for sub in fam["conditions"]:
        ids_in_gate.add(lib_sigs.get(_json_lib.dumps(sub, sort_keys=True, default=str), "?"))
check("K4 الحالتان 5 (الإنذار المبكر) خارجا البوابة الافتراضية",
      "macd_case5_deep_negative_stack" not in ids_in_gate
      and "rsi_case5_reverse_below_50" not in ids_in_gate and "?" not in ids_in_gate,
      f"الحالات في البوابة: {len(ids_in_gate)}")

EVID["sections"]["K_presets"] = {"pass": PASS - _pJ(), "fail": FAIL - _fJ()}

# ===========================================================================
ELAPSED = time.perf_counter() - T0_ALL
print(f"\n{'=' * 78}")
print(f"PRO73-R3 CASES BATTERY: PASS={PASS} FAIL={FAIL} | زمن={ELAPSED:.1f}s")
if FAILURES:
    print("الفشل:")
    for n, d in FAILURES:
        print(f"  ❌ {n} — {d}")
EVID["summary"] = {"pass": PASS, "fail": FAIL, "elapsed_s": round(ELAPSED, 1),
                   "failures": [{"name": n, "detail": d} for n, d in FAILURES]}
os.makedirs(os.path.join(HERE, "r73-evidence"), exist_ok=True)
with open(os.path.join(HERE, "r73-evidence", "battery-r73-cases.json"), "w", encoding="utf-8") as fh:
    json.dump(EVID, fh, ensure_ascii=False, indent=2, default=str)
print(f"الأدلة: {os.path.join(HERE, 'r73-evidence', 'battery-r73-cases.json')}")
sys.exit(0 if FAIL == 0 else 1)
