# =============================================================================
# ✅ PRO73-R3 — مكتبة نسخ الموشرات الكاملة + الحالات الخاصة المسمّاة
# =============================================================================
# مصدر الحقيقة (2026-11-13 — أمر صاحب القرار):
#   «ويعمل وبكامل الاعدادات والموشرات كامله هذي الي في المستند»
#   المستند: https://docs.google.com/document/d/1NAQOuiniJ6yFBApLmiYruxeJFp3JnMra2Aqs_TwPcvo
#
# المحتوى:
#   1) OSC_DOC_INSTANCES — النسخ الكاملة حرفياً من المستند (28 MACD + 16 RSI
#      + 23 Momentum = 67 نسخة على الفريمات الـ14)، لكل نسخة معرف وصفّي
#      ذاتي: macd_{tf}_{fast}_{slow}_{signal} · rsi_{tf}_{len}_{ma} ·
#      mom_{tf}_{len} — كل شيء قابل للتعديل من التكوين بلا أي كود.
#   2) OSC_CASE_LIBRARY — الحالات الخاصة الثلاث عشرة المسمّاة بنص المالك
#      حرفياً (MACD 1-5 · RSI 1-5 · Momentum 1-3)، كل حالة شجرة شروط
#      قابلة للتركيب (and/or/not) جاهزة للدمج في أي بوابة، مع كل مراجعها.
#   3) وحدات الماكرو: macd_any / rsi_any / mom_any / MASTER_ANY_CASE /
#      MASTER_STRICT / EARLY_WATCH — جاهزة للتبديل بنقرة من الفرونت إند.
#
# جدول مطابقة المستند (الإطار → الإعدادات):
#   MACD  — Fast/Slow/Signal:
#     1s·5s·1m·5m·15m·1h·4h·1d·2d: (6/13/4) و (12/26/4)
#     3 أيام: (5/11/4) و (6/13/4) و (12/26/4)
#     أسبوع: (6/13/4) و (12/26/4) و (18/39/4)
#     أسبوعان: (12/26/2) · شهر: (12/26/2)
#     (30 ثانية غير موجودة في جدول الماكد بالمستند → نفس عائلتها 6/13/4 + 12/26/4)
#   RSI — Source: Close · MA Type: EMA · BB StdDev: 2:
#     1s·5s·30s·1m·5m·15m·1h·4h·1w·2w: (14/14)
#     1 يوم: (10/14) و (14/14) · يومان: (14/6) و (14/14) · 3 أيام: (14/6)
#     (شهر غير موجودة في جدول RSI بالمستند → افتراضي العائلة 14/14)
#   Momentum — Source: Close:
#     1s·5s: (10) · البقية: (5) و (10) لكل فريم
#     (30 ثانية غير موجودة → 10 مثل جيرانها)
#
# ملاحظة مطابقة أرقام المالك في نصوصه: «4/13/6» = الإعداد (6/13/4) نفسه
# بترتيب قراءة RTL (Signal/Slow/Fast)، و«4/11/5» = (5/11/4)، و«4/26/12» =
# (12/26/4)، و«2/14/10» = RSI Length 10 · MA 14 · BB 2، و«2/6/14» =
# RSI Length 14 · MA 6 · BB 2 — كلها مطابقة حرفياً لجدول المستند.
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "OSC_DOC_SOURCE",
    "OSC_DOC_URL",
    "OSC_DOC_INSTANCES",
    "OSC_CASE_LIBRARY",
    "OSC_CASE_CATALOG",
    "MASTER_ANY_CASE",
    "MASTER_STRICT",
    "EARLY_WATCH",
    "get_case_tree",
    "collect_case_refs",
]

OSC_DOC_SOURCE = "google-doc"
OSC_DOC_URL = "https://docs.google.com/document/d/1NAQOuiniJ6yFBApLmiYruxeJFp3JnMra2Aqs_TwPcvo/edit?usp=sharing"

OSC_CASE_LIBRARY_SPEC = "PRO73-osc-cases"
OSC_CASE_LIBRARY_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# مساعدات بناء الشجرة (نفس عقد mtf_oscillator_core حرفياً)
# ---------------------------------------------------------------------------
def _leaf(left: str, op: str, right: Any, skip: bool = False) -> Dict[str, Any]:
    return {"left": left, "op": op, "right": right, "skip_unavailable": bool(skip)}


def _and(*subs: Dict[str, Any]) -> Dict[str, Any]:
    return {"logic": "and", "conditions": list(subs)}


def _or(*subs: Dict[str, Any]) -> Dict[str, Any]:
    return {"logic": "or", "conditions": list(subs)}


def _not(sub: Dict[str, Any]) -> Dict[str, Any]:
    return {"logic": "not", "conditions": [sub]}


def _ref(iid: str, field: str) -> str:
    return f"osc:{iid}.{field}"


def _tf_key(tf: str) -> str:
    return "1mo" if tf == "1M" else tf


# ---------------------------------------------------------------------------
# 1) نسخ المستند الكاملة (67 نسخة)
# ---------------------------------------------------------------------------
_MACD_STD_TFS = ["1s", "5s", "30s", "1m", "5m", "15m", "1h", "4h", "1d", "2d"]


def _build_doc_macd_instances() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for tf in _MACD_STD_TFS:
        out.append({"kind": "macd", "id": f"macd_{tf}_6_13_4", "timeframe": tf,
                    "fast": 6, "slow": 13, "signal": 4, "doc": f"الإعداد الأول للمستند ({tf})"})
        out.append({"kind": "macd", "id": f"macd_{tf}_12_26_4", "timeframe": tf,
                    "fast": 12, "slow": 26, "signal": 4, "doc": f"الإعداد الثاني للمستند ({tf})"})
    # 3 أيام — ثلاثة إعدادات
    out += [
        {"kind": "macd", "id": "macd_3d_5_11_4", "timeframe": "3d",
         "fast": 5, "slow": 11, "signal": 4, "doc": "الإعداد الأول للمستند (3d)"},
        {"kind": "macd", "id": "macd_3d_6_13_4", "timeframe": "3d",
         "fast": 6, "slow": 13, "signal": 4, "doc": "الإعداد الثاني للمستند (3d)"},
        {"kind": "macd", "id": "macd_3d_12_26_4", "timeframe": "3d",
         "fast": 12, "slow": 26, "signal": 4, "doc": "الإعداد الثالث للمستند (3d)"},
    ]
    # أسبوع — ثلاثة إعدادات
    out += [
        {"kind": "macd", "id": "macd_1w_6_13_4", "timeframe": "1w",
         "fast": 6, "slow": 13, "signal": 4, "doc": "الإعداد الأول للمستند (1w)"},
        {"kind": "macd", "id": "macd_1w_12_26_4", "timeframe": "1w",
         "fast": 12, "slow": 26, "signal": 4, "doc": "الإعداد الثاني للمستند (1w)"},
        {"kind": "macd", "id": "macd_1w_18_39_4", "timeframe": "1w",
         "fast": 18, "slow": 39, "signal": 4, "doc": "الإعداد الثالث للمستند (1w)"},
    ]
    # أسبوعان وشهر
    out += [
        {"kind": "macd", "id": "macd_2w_12_26_2", "timeframe": "2w",
         "fast": 12, "slow": 26, "signal": 2, "doc": "الإعداد الأول للمستند (2w)"},
        {"kind": "macd", "id": "macd_1mo_12_26_2", "timeframe": "1M",
         "fast": 12, "slow": 26, "signal": 2, "doc": "الإعداد الأول للمستند (1M)"},
    ]
    return out


def _build_doc_rsi_instances() -> List[Dict[str, Any]]:
    rows = [
        ("1s", 14, 14), ("5s", 14, 14), ("30s", 14, 14), ("1m", 14, 14),
        ("5m", 14, 14), ("15m", 14, 14), ("1h", 14, 14), ("4h", 14, 14),
        ("1d", 10, 14), ("1d", 14, 14),
        ("2d", 14, 6), ("2d", 14, 14),
        ("3d", 14, 6),
        ("1w", 14, 14), ("2w", 14, 14), ("1M", 14, 14),
    ]
    out: List[Dict[str, Any]] = []
    for tf, rlen, ma in rows:
        out.append({
            "kind": "rsi", "id": f"rsi_{_tf_key(tf)}_{rlen}_{ma}", "timeframe": tf,
            "period": rlen, "ma_length": ma, "bb_std": 2,
            "doc": f"RSI {rlen} · EMA {ma} · BB StdDev 2 ({tf}) — Source: Close",
        })
    return out


def _build_doc_mom_instances() -> List[Dict[str, Any]]:
    rows = [("1s", 10), ("5s", 10), ("30s", 10)]
    for tf in ["1m", "5m", "15m", "1h", "4h", "1d", "2d", "3d", "1w", "1M"]:
        rows += [(tf, 5), (tf, 10)]
    out: List[Dict[str, Any]] = []
    for tf, ln in rows:
        out.append({"kind": "mom", "id": f"mom_{_tf_key(tf)}_{ln}", "timeframe": tf,
                    "length": ln, "doc": f"Length {ln} ({tf}) — Source: Close"})
    return out


OSC_DOC_INSTANCES: List[Dict[str, Any]] = (
    _build_doc_macd_instances() + _build_doc_rsi_instances() + _build_doc_mom_instances()
)
OSC_DOC_INSTANCE_IDS = {str(x["id"]) for x in OSC_DOC_INSTANCES}


# ---------------------------------------------------------------------------
# 2) الحالات الخاصة المسمّاة — نص المالك حرفياً → شجرة شروط قابلة للتركيب
# ---------------------------------------------------------------------------
def _all_macd_positive_tree() -> Dict[str, Any]:
    """ماكد 1: جميع الفريمات ايجابية (السريع متجاوز البطيء = خط الماكد > 0)."""
    leaves = [
        _leaf(_ref(iid, "line"), ">", 0, skip=True)
        for iid in (x["id"] for x in _build_doc_macd_instances())
    ]
    return _and(*leaves)


def _all_mom_positive_tree() -> Dict[str, Any]:
    """مومنتم 2: اختراق جميع الأطر الزمنية مستوى صفر لأعلى (الخط > 0)."""
    leaves = [
        _leaf(_ref(iid, "line"), ">", 0, skip=True)
        for iid in (x["id"] for x in _build_doc_mom_instances())
    ]
    return _and(*leaves)


_M1 = "macd_1w_6_13_4"
_M3D_A = "macd_3d_6_13_4"     # «4/13/6» بالمستند
_M3D_B = "macd_3d_5_11_4"     # «4/11/5» بالمستند
_M1D_C = "macd_1d_12_26_4"    # «4/26/12» بالمستند
_M4H_C = "macd_4h_12_26_4"

OSC_CASE_LIBRARY: List[Dict[str, Any]] = [
    # ---------------- MACD — الحالات الخمس ----------------
    {
        "id": "macd_case1_all_tfs_positive",
        "family": "macd",
        "kind": "instant",
        "title": "ماكد 1 — جميع الفريمات ايجابية (السريع متجاوز البطيء)",
        "text": "ان تكون جميع الفر يات ايجابية ( السريع متجاوز البطيء )",
        "tree": _all_macd_positive_tree(),
    },
    {
        "id": "macd_case2_4h_zero_cross_up",
        "family": "macd",
        "kind": "instant",
        "title": "ماكد 2 — خط ماكد 4 ساعات اخترق خط الصفر لاعلى",
        "text": "خط ماكد للاطار الزمني 4 ساعات اخترق خط الصفر لاعلى.",
        "tree": _or(
            _leaf(_ref("macd_4h_6_13_4", "line"), "cross_above", 0),
            _leaf(_ref(_M4H_C, "line"), "cross_above", 0),
        ),
    },
    {
        "id": "macd_case3_3d_above_1d",
        "family": "macd",
        "kind": "instant",
        "title": "ماكد 3 — خطا 3 أيام (4/13/6 و 4/11/5) فوق خط 1 يوم (4/26/12)",
        "text": "خطي ماكد للاطار الزمني (3 يوم) بالمعلمات 4/13/6 و 4/11/5 كليهما او "
                "احدهما على الاقل فوق خط ماكد للاطار الزمني (1 يوم) ذو المعلمات 4/26/12.",
        "tree": _or(
            _leaf(_ref(_M3D_A, "line"), ">", _ref(_M1D_C, "line")),
            _leaf(_ref(_M3D_B, "line"), ">", _ref(_M1D_C, "line")),
        ),
    },
    {
        "id": "macd_case4_htf_dominance",
        "family": "macd",
        "kind": "instant",
        "title": "ماكد 4 — اعتلاء الأكبر فوق الأصغر (زخم متزايد) — تراصب كامل",
        "text": "بشكل عام اعتلاء خط الاطار الزمني الاكبر فوق الاطار الزمني الاصغر فهو "
                "افضل وفرصة دخول شراء. أمثلة: أ- 1 اسبوع ايجابي وفوق 3 أيام (زخم متزايد) "
                "ب- 3 أيام بالمعلمات 4/13/6 ايجابي وفوق 3 أيام بمعلمات 4/11/5 وايجابي.",
        "tree": _and(
            # أ — الأسبوعي (6/13/4) موجب وفوق 3 أيام (6/13/4)
            _leaf(_ref(_M1, "line"), ">", 0),
            _leaf(_ref(_M1, "line"), ">", _ref(_M3D_A, "line")),
            # ب — 3 أيام (6/13/4) موجب وفوق 3 أيام (5/11/4) وهو موجب أيضاً
            _leaf(_ref(_M3D_A, "line"), ">", 0),
            _leaf(_ref(_M3D_A, "line"), ">", _ref(_M3D_B, "line")),
            _leaf(_ref(_M3D_B, "line"), ">", 0),
            # التراصب العام — الأكبر فوق الأصغر (عائلة 6/13/4)
            _leaf(_ref(_M3D_A, "line"), ">", _ref("macd_1d_6_13_4", "line")),
            _leaf(_ref("macd_1d_6_13_4", "line"), ">", _ref("macd_4h_6_13_4", "line")),
            _leaf(_ref("macd_4h_6_13_4", "line"), ">", _ref("macd_1h_6_13_4", "line")),
            _leaf(_ref("macd_1h_6_13_4", "line"), ">", _ref("macd_15m_6_13_4", "line")),
        ),
    },
    {
        "id": "macd_case5_deep_negative_stack",
        "family": "macd",
        "kind": "early",
        "title": "ماكد 5 — ترص عكسي تحت الصفر (3يوم ← 1يوم ← 4ساعات) — موجة صعودية قادمة",
        "text": "من ناحية اخرى فإن ترتب الاطارات الزمنية (3 يوم 4/6/13) ثم (1 يوم 4/26/12) "
                "تحته، ثم (4 ساعات 4/26/12) تحته، وكلهم تحت مستوى الصفر فان ذلك قد ينذر "
                "بموجه صعوديه قادمة.",
        "note": "«4/6/13» في نص المالك = نفس إعداد (6/13/4) بترتيب RTL — وكل الأوراق "
                "قابلة للتعديل إن أراد المالك تفسيراً آخر.",
        "tree": _and(
            _leaf(_ref(_M3D_A, "line"), ">", _ref(_M1D_C, "line")),
            _leaf(_ref(_M1D_C, "line"), ">", _ref(_M4H_C, "line")),
            _leaf(_ref(_M3D_A, "line"), "<", 0),
            _leaf(_ref(_M1D_C, "line"), "<", 0),
            _leaf(_ref(_M4H_C, "line"), "<", 0),
        ),
    },
    # ---------------- RSI — الحالات الخمس ----------------
    {
        "id": "rsi_case1_1d_over_50",
        "family": "rsi",
        "kind": "instant",
        "title": "آر إس آي 1 — أحد خطي 1 يوم (2/14/10 و 2/14/14) فوق 50",
        "text": "تجاوز أحد خطي rsi الاطار الزمني (1 يوم) بالمعلمات 2/14/10 و 2/14/14 "
                "او كليهما مستوى 50 ومافوق.",
        "tree": _or(
            _leaf(_ref("rsi_1d_10_14", "value"), ">", 50),
            _leaf(_ref("rsi_1d_14_14", "value"), ">", 50),
        ),
    },
    {
        "id": "rsi_case2_3d_over_40_not_on_top",
        "family": "rsi",
        "kind": "instant",
        "title": "آر إس آي 2 — خط 3 أيام (2/6/14) فوق 40 ولا يكون فوق فريم أصغر منه",
        "text": "تجاوز خط rsi الاطار الزمني (3 يوم) بالمعلمات 2/6/14 مستوى 40 ومافوق. "
                "والا يكون فوق خط فريم زمني اصغر منه.",
        "note": "«فريم أصغر» افتراضياً = خط 1 يوم الأول (2/14/10) — قابل للتعديل لأي "
                "نسخة، ويوافق مبدأ الحالة 4 (الأصغر فوق الأكبر هو الترتيب الصحي).",
        "tree": _and(
            _leaf(_ref("rsi_3d_14_6", "value"), ">=", 40),
            _not(_leaf(_ref("rsi_3d_14_6", "value"), ">", _ref("rsi_1d_10_14", "value"))),
        ),
    },
    {
        "id": "rsi_case3_stack_50_60",
        "family": "rsi",
        "kind": "instant",
        "title": "آر إس آي 3 — ترص (1 ساعة ← 4 ساعات ← 1 يوم) بين 50 و 60 — مرحلة قبل الصعود",
        "text": "وجود الاطار الزمني (1 ساعه) ثم (4 ساعات تحته) ثم (1يوم تحته) بين "
                "مستوى 50 ومستوى 60 قد يعبر عن مرحله مهمه قبل صعود السعر.",
        "tree": _and(
            _leaf(_ref("rsi_1h_14_14", "value"), ">=", 50),
            _leaf(_ref("rsi_1h_14_14", "value"), "<=", 60),
            _leaf(_ref("rsi_4h_14_14", "value"), ">=", 50),
            _leaf(_ref("rsi_4h_14_14", "value"), "<=", 60),
            _leaf(_ref("rsi_1d_14_14", "value"), ">=", 50),
            _leaf(_ref("rsi_1d_14_14", "value"), "<=", 60),
            # الترتيب الصحي: الأصغر أعلى (مبدأ الحالة 4)
            _leaf(_ref("rsi_1h_14_14", "value"), ">", _ref("rsi_4h_14_14", "value")),
            _leaf(_ref("rsi_4h_14_14", "value"), ">", _ref("rsi_1d_14_14", "value")),
        ),
    },
    {
        "id": "rsi_case4_small_on_top_stack",
        "family": "rsi",
        "kind": "instant",
        "title": "آر إس آي 4 — ترص الأصغر فوق الأكبر (الترتيب الصحي) — فرصة شراء",
        "text": "بشكل عام اعتلاء خط الاطار الزمني الاصغر فوق الاكبر فهو اصح وفرصة دخول "
                "شراء (بشرط ترتبهم بالشكل الاتي: الاصغر اعلاهم ثم الاكبر منه...).",
        "tree": _and(
            _leaf(_ref("rsi_1h_14_14", "value"), ">", _ref("rsi_4h_14_14", "value")),
            _leaf(_ref("rsi_4h_14_14", "value"), ">", _ref("rsi_1d_14_14", "value")),
            _leaf(_ref("rsi_1d_14_14", "value"), ">", _ref("rsi_2d_14_14", "value")),
            _leaf(_ref("rsi_2d_14_14", "value"), ">", _ref("rsi_3d_14_6", "value")),
            _leaf(_ref("rsi_3d_14_6", "value"), ">", _ref("rsi_1w_14_14", "value")),
        ),
    },
    {
        "id": "rsi_case5_reverse_below_50",
        "family": "rsi",
        "kind": "early",
        "title": "آر إس آي 5 — ترص عكسي (الأكبر فالأصغر تحته) تحت 50 — موجة صعودية قادمة",
        "text": "من ناحية اخرى فإن ترتب الاطارات الزمنية بشكل عكسي (الاكبر فالاصغر "
                "تحته) تحت مستوى 50 فقد يعبر عن موجه صعوديه قادمة.",
        "tree": _and(
            _leaf(_ref("rsi_1w_14_14", "value"), ">", _ref("rsi_3d_14_6", "value")),
            _leaf(_ref("rsi_3d_14_6", "value"), ">", _ref("rsi_2d_14_14", "value")),
            _leaf(_ref("rsi_2d_14_14", "value"), ">", _ref("rsi_1d_14_14", "value")),
            _leaf(_ref("rsi_1w_14_14", "value"), "<", 50),
            _leaf(_ref("rsi_3d_14_6", "value"), "<", 50),
            _leaf(_ref("rsi_2d_14_14", "value"), "<", 50),
            _leaf(_ref("rsi_1d_14_14", "value"), "<", 50),
        ),
    },
    # ---------------- Momentum — الحالات الثلاث ----------------
    {
        "id": "mom_case1_1w_over_3d",
        "family": "mom",
        "kind": "instant",
        "title": "مومنتم 1 — اعتلاء 1 أسبوع (طول 5) على 3 أيام (طول 10) — فرصة شراء",
        "text": "اعتلاء الاطار الزمني (1 اسبوع بطول 5) على الاطار الزمني ل (3 يوم طول 10) "
                "يمثل فرصة شراء.",
        "tree": _leaf(_ref("mom_1w_5", "line"), ">", _ref("mom_3d_10", "line")),
    },
    {
        "id": "mom_case2_all_above_zero",
        "family": "mom",
        "kind": "instant",
        "title": "مومنتم 2 — اختراق جميع الأطر الزمنية مستوى صفر لأعلى",
        "text": "اختراق جميع الاطر الزمنية مستوى صفر لأعلى.",
        "tree": _all_mom_positive_tree(),
    },
    {
        "id": "mom_case3_large_on_top_stack",
        "family": "mom",
        "kind": "instant",
        "title": "مومنتم 3 — اعتلاء الأكبر فوق الأصغر (زخم متزايد) — تراصب كامل",
        "text": "بشكل عام اعتلاء خط الاطار الزمني الاكبر فوق الاطار الزمني الاصغر فهو "
                "افضل وفرصة دخول شراء. أمثلة: أ- عندما يكون خط الاسبوعي فوق خط (3 يوم) "
                "فهذا يعبر عن زخم متزايد.",
        "tree": _and(
            _leaf(_ref("mom_1w_5", "line"), ">", _ref("mom_3d_10", "line")),
            _leaf(_ref("mom_3d_10", "line"), ">", _ref("mom_2d_10", "line")),
            _leaf(_ref("mom_2d_10", "line"), ">", _ref("mom_1d_10", "line")),
            _leaf(_ref("mom_1d_10", "line"), ">", _ref("mom_4h_10", "line")),
            _leaf(_ref("mom_4h_10", "line"), ">", _ref("mom_1h_10", "line")),
        ),
    },
]


def collect_case_refs(node: Any) -> List[str]:
    """جمع كل مراجع osc: من شجرة (للتحقق من قابلية الحل ضد نسخ المستند)."""
    refs: List[str] = []
    if not isinstance(node, dict):
        return refs
    if "logic" in node:
        for sub in node.get("conditions") or []:
            refs.extend(collect_case_refs(sub))
        return refs
    for side in ("left", "right"):
        v = node.get(side)
        if isinstance(v, str) and v.lower().startswith("osc:"):
            refs.append(v.lower())
    return refs


def get_case_tree(case_id: str) -> Optional[Dict[str, Any]]:
    for case in OSC_CASE_LIBRARY:
        if case["id"] == case_id:
            return case["tree"]
    return None


# ---------------------------------------------------------------------------
# 3) وحدات الماكرو — بوابات جاهزة للتبديل بنقرة من الفرونت إند
# ---------------------------------------------------------------------------
def _cases_of(family: str, kind: str = "instant") -> List[Dict[str, Any]]:
    return [c for c in OSC_CASE_LIBRARY if c["family"] == family and c["kind"] == kind]


def _or_of_cases(cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _or(*[dict(c["tree"]) for c in cases])


MACD_ANY = _or_of_cases(_cases_of("macd"))
RSI_ANY = _or_of_cases(_cases_of("rsi"))
MOM_ANY = _or_of_cases(_cases_of("mom"))

# «أي حالة لحظية» — كل حالة من الحالات الـ11 كافية بذاتها (نص المالك:
# «والتي ان تحققت فهي تعطي اشارة ايجابية وفرصة شراء بشكل لحظي»)
MASTER_ANY_CASE: Dict[str, Any] = _or(MACD_ANY, RSI_ANY, MOM_ANY)

# «انطباق كل شروط الماكد والمومنتم والآر إس آي» — كل عائلة تُطالب بحالة
# واحدة على الأقل (نموذج S1 AND كل الموشرات)
MASTER_STRICT: Dict[str, Any] = _and(MACD_ANY, RSI_ANY, MOM_ANY)

# الإنذارات المبكرة (الحالتان 5 لماكد/آر إس آي) — موجة صعودية قادمة
EARLY_WATCH: Dict[str, Any] = _or(
    dict(get_case_tree("macd_case5_deep_negative_stack") or {}),
    dict(get_case_tree("rsi_case5_reverse_below_50") or {}),
)

_OSC_MACROS: List[Dict[str, Any]] = [
    {"id": "macd_any", "family": "macro", "kind": "macro",
     "title": "أي حالة ماكد لحظية (1-4)", "tree": MACD_ANY},
    {"id": "rsi_any", "family": "macro", "kind": "macro",
     "title": "أي حالة آر إس آي لحظية (1-4)", "tree": RSI_ANY},
    {"id": "mom_any", "family": "macro", "kind": "macro",
     "title": "أي حالة مومنتم لحظية (1-3)", "tree": MOM_ANY},
    {"id": "master_any_case", "family": "macro", "kind": "macro",
     "title": "أي حالة لحظية (البوابة الافتراضية للقالبين)", "tree": MASTER_ANY_CASE},
    {"id": "master_strict", "family": "macro", "kind": "macro",
     "title": "انطباق العائلات الثلاث (ماكد ∧ آر إس آي ∧ مومنتم)", "tree": MASTER_STRICT},
    {"id": "early_watch", "family": "macro", "kind": "macro",
     "title": "إنذار مبكر — موجة صعودية قادمة (ماكد5/آر إس آي5)", "tree": EARLY_WATCH},
]


# ---------------------------------------------------------------------------
# 4) الفهرس — للفرونت إند (كل شيء قابل للعرض والتعديل)
# ---------------------------------------------------------------------------
def _catalog_entry(case: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": case["id"],
        "family": case["family"],
        "kind": case["kind"],
        "title": case["title"],
        "text": case["text"],
        "note": case.get("note"),
        "refs": collect_case_refs(case["tree"]),
        "tree": case["tree"],
    }


OSC_CASE_CATALOG: List[Dict[str, Any]] = (
    [_catalog_entry(c) for c in OSC_CASE_LIBRARY] + _OSC_MACROS
)
