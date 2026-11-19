# =============================================================================
# ✅ EMAGATE-UNIFIED — نواة بوابة رصة EMA الموحدة المركزية
# (شرح أكثر وضبط أكبر — أمر صاحب القرار 2026-11-19)
# =============================================================================
# «ونريد منك تطبيق التعديل على اي مكان فيه البوابه واي استراتيجه فيها
#   البوابه عشان يكون العمل موحد ومركزي ومنظم»
#
# عقد الرصة الهرمي (الشروط السبعة حرفياً — المصدر الوحيد للحقيقة):
#
#   1- السعر يأتي أولاً فوق متوسطات EMA كلها (كل المكونة).
#   2- تحت السعر يأتي EMA 21 فوق EMA 50، ولا يوجد أي متوسط أكبر منهما
#      فوقهما — إلا متوسط أصغر من EMA 21 فيجوز أن يعلو فوق EMA 21.
#   3- EMA 50 (إن وجد) فوق EMA 100 (إن وجد) — ولا أكبر منهما فوقهما.
#   4- EMA 100 (إن وجد) فوق EMA 200 (إن وجد) — ولا أكبر منهما فوقهما.
#   5- EMA 200 (إن وجد) فوق EMA 350 (إن وجد) — ولا أكبر منهما فوقهما.
#   6- EMA 350 (إن وجد) فوق EMA 500 (إن وجد) — ولا أكبر منهما فوقهما.
#   7- EMA 500 (إن وجد) فوق أي متوسط أكبر منه (إن وُجد — يعمَّم للكل).
#
# الصياغة التنفيذية الموحدة (تُغطي الشروط السبعة كلها لأي مجموعة أطوال):
#
#   السلّم (ladder) = الأطوال ≥ ema_stack_base (الافتراضي 21 — قرار نص
#   الشرط 2: «أصغر من ema 21» هو حدّ الإعفاء).
#   السريعة (fast)  = الأطوال < ema_stack_base (مثل 8/13) — معفية من
#   الترتيب (يجوز أن تعلو فوق EMA 21 كما نص الشرط 2 حرفياً) ويشترط لها
#   فقط الشرط 1: السعر فوقها.
#
#   ok[i] = جاهزية كل القيم ∧ (السعر > كل متوسط) ∧ (ترتيب السلّم كاملاً:
#   لكل زوج أطوال a < b في السلّم: EMA_a > EMA_b).
#
#   برهان التكافؤ مع فقرات «لا يوجد أي متوسط أكبر منهم فوقهم»: ترتيب
#   السلّم الكامل بالتسلسل (EMA_a > EMA_b لكل a < b) يجعل كل متوسط أكبر
#   تحت أصغر زوجٍ يُذكره الشرط — فالجملة الوصفية محقَّقة بالبناء، ولا
#   يبقى قيدٌ إجرائي زائد. الإعفاء الوحيد غير الزائد عن الترتيب هو
#   إعفاء الأصغر من القاعدة (fast) — منصوص الشرط 2.
#
# الوضعان (مفتاح A/B — عزل نظيف):
#   · "hierarchical" (الافتراضي الجديد): العقد أعلاه بالضبط — مستقل عن
#     ترتيب تمرير الأطوال (يفرزها داخلياً)، يتكيف مع أي مجموعة جزئية
#     («إن وجد»)، ويعفي الأسرع من القاعدة.
#   · "strict" (الوضع التاريخي حرفياً — للتراجع/المقارنة): الرصة سلسلة
#     واحدة بترتيب التمرير كما هو: close > ema[0] > ema[1] > ... (لا
#     فرز ولا إعفاء — أثر التكوينات القياسية المطابقة بت-بت).
#
# توافق خلفي (بيت-بت): لأي تكوين قائم بأطوال ≥ 21 مرتَّبة تصاعدياً
# (الافتراضي [21,50,100,200,350,500] وتكوين الجبارة [50,100,200,350,500])
# يُنتج الوضعان النتيجة نفسها بت-بت — النواة تُبرهن ذلك في بطارية
# التحقق (verify_emagate_unified.py).
#
# التشخيص المرجع (أعمدة تُرجع للمحرك لكل شمعة):
#   ready      : كل القيم صالحة (والسعر صالح) — نفس عقد الجاهزية التاريخي.
#   price_ok   : الشرط 1 وحده (السعر فوق الكل).
#   ladder_ok  : الشروط 2-7 وحدها (ترتيب السلّم).
#   ok         : البوابة كاملة (ready ∧ price_ok ∧ ladder_ok).
#   pair_ok_{a}_{b} : كل زوج متجاور في السلّم على حدة — عمود لكل شرط
#   من الشروط 2-7 (مؤشرات إنذار للواجهة: أي زوج انكسر).
#
# عقد الاستخدام: دالة واحدة compute_ema_stack_gate() نقية بلا حالة —
# يستدعيها محرك الكمومية-EMA (ومنه بالتفويض محرك كموميه الزخم الاولى
# QMOM1) — مركز واحد لكل مكان فيه البوابة (عقد «موحد ومركزي ومنظم»).
# =============================================================================

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "compute_ema_stack_gate",
    "norm_ema_stack_mode",
    "norm_ema_stack_base",
    "EMA_STACK_MODE_HIERARCHICAL",
    "EMA_STACK_MODE_STRICT",
    "EMA_STACK_MODES",
    "DEFAULT_EMA_STACK_BASE",
    "DEFAULT_EMA_STACK_MODE",
]

EMA_STACK_MODE_HIERARCHICAL = "hierarchical"
EMA_STACK_MODE_STRICT = "strict"
EMA_STACK_MODES = (EMA_STACK_MODE_HIERARCHICAL, EMA_STACK_MODE_STRICT)

# حدّ الإعفاء الافتراضي — نص الشرط 2: «أصغر من ema 21» (قالبي قابل
# للتخصيص من الواجهة عبر ema_stack_base — لا أرقام حاكمة داخل المنطق).
DEFAULT_EMA_STACK_BASE = 21
DEFAULT_EMA_STACK_MODE = EMA_STACK_MODE_HIERARCHICAL


def norm_ema_stack_mode(raw: Any) -> str:
    """تطبيع وضع الرصة — «hierarchical» (الافتراضي) أو «strict».

    أي قيمة غير معروفة/فارغة/None ⇒ الافتراضي (hierarchical) بصمت —
    عقد التراجع الآمن: البوابة لا تفشل أبداً بسبب قيمة وضع مشوهة.
    """
    if raw is None:
        return DEFAULT_EMA_STACK_MODE
    s = str(raw).strip().lower()
    if s in ("", "default", "hier", "hierarchy", "ema", "new"):
        return EMA_STACK_MODE_HIERARCHICAL
    if s in ("strict", "legacy", "old", "chain"):
        return EMA_STACK_MODE_STRICT
    return DEFAULT_EMA_STACK_MODE


def norm_ema_stack_base(raw: Any) -> int:
    """تطبيع حدّ الإعفاء (قاعدة السلّم) — عدد صحيح ≥ 1.

    الافتراضي 21 (نص الشرط 2). الأصغر من القاعدة = سريعة معفاة من
    الترتيب. القاعدة = 1 ⇒ كل الأطوال في السلّم (إعفاء لا أحد).
    """
    if raw is None:
        return DEFAULT_EMA_STACK_BASE
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_EMA_STACK_BASE
    return n if n >= 1 else DEFAULT_EMA_STACK_BASE


def _finite(v: Any) -> Optional[float]:
    """قيمة عددية محدودة أو None — تحصين القيم JSON-آمنة."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def compute_ema_stack_gate(
    closes: Sequence[Any],
    ema_values: Dict[Any, Sequence[Any]],
    mode: Any = None,
    base: Any = None,
) -> Dict[str, Any]:
    """بوابة رصة EMA الموحدة — الشروط السبعة (شرح صاحب القرار).

    المعاملات:
      closes      : أسعار الإغلاق لكل شمعة قاعدة (قائمة/مسلسل).
      ema_values  : {طول: قيم EMA لكل شمعة} — بأي ترتيب مفاتيح؛ الأطوال
                    تُفرَز داخلياً (وضع hierarchical) فلا يعتمد شيء على
                    ترتيب التمرير.
      mode        : «hierarchical» (افتراضي) | «strict» (الوضع التاريخي).
      base        : حدّ الإعفاء/قاعدة السلّم (افتراضي 21).

    المخرجات (كلها طول N — قيم 0/1 ما عدا meta):
      ready / price_ok / ladder_ok / ok : أعمدة الحالة (0/1).
      pairs : [{a, b, label, ok[]}] لكل زوج متجاور في السلّم (أو في
              ترتيب التمرير للوضع strict) — عمود لكل شرط من 2-7.
      meta  : {mode, base, ladder_lengths, fast_lengths, pair_labels,
               rule_ar, rule_ar_strict} — عقد الشفافية للواجهة.
    """
    mode_n = norm_ema_stack_mode(mode)
    base_n = norm_ema_stack_base(base)

    # أطوال موحدة (int) مع الحفاظ على أول قيم لكل طول — الأطوال المكررة
    # مستحيلة من المحرك (يفردها _norm_ema_lengths) وهنا نحتاط.
    lengths: List[int] = []
    vals: Dict[int, List[Optional[float]]] = {}
    for raw_len, raw_seq in (ema_values or {}).items():
        try:
            n_len = int(raw_len)
        except (TypeError, ValueError):
            continue
        if n_len < 1 or n_len in vals:
            continue
        lengths.append(n_len)
        vals[n_len] = [_finite(v) for v in (raw_seq or [])]

    N = len(closes) if closes is not None else 0
    closes_f: List[Optional[float]] = [_finite(x) for x in (closes or [])][:N] \
        if closes is not None else []
    if N and len(closes_f) < N:
        closes_f = closes_f + [None] * (N - len(closes_f))

    # ── تقسيم السلّم/السريعة + الفرز (وضع hierarchical) ──
    if mode_n == EMA_STACK_MODE_HIERARCHICAL:
        ladder = sorted(n for n in lengths if n >= base_n)
        fast = sorted(n for n in lengths if n < base_n)
    else:
        # الوضع التاريخي: «سلّم» بترتيب التمرير كما هو (لا فرز) — والكل
        # في السلّم (لا إعفاء) — حرفية السلوك القديم للتراجع/A-B.
        ladder = list(lengths)
        fast = []

    ladder_lines: List[List[Optional[float]]] = [
        vals.get(n) or [None] * N for n in ladder
    ]

    # ── الأعمدة (0/1) ──
    ready: List[float] = [0.0] * N
    price_ok: List[float] = [0.0] * N
    ladder_ok: List[float] = [0.0] * N
    ok: List[float] = [0.0] * N

    K = len(ladder)
    pair_defs: List[Tuple[int, int]] = [
        (ladder[k], ladder[k + 1]) for k in range(K - 1)
    ] if K > 1 else []
    pair_ok: Dict[str, List[float]] = {
        f"pair_{a}_{b}": [0.0] * N for a, b in pair_defs
    }

    # كل القيم (السلّم + السريعة) يشترط لها الشرط 1 أن يكون السعر فوقها —
    # والسريعة معفاة من الترتيب فقط لا من الشرط 1.
    all_lines: List[List[Optional[float]]] = [
        vals.get(n) or [None] * N for n in sorted(lengths)
    ]

    for i in range(N):
        c_i = closes_f[i]
        valid_all = (c_i is not None) and all(
            (ln[i] is not None) if i < len(ln) else False
            for ln in all_lines
        )
        if not valid_all:
            continue
        ready[i] = 1.0
        f_close = float(c_i)
        f_all = [float(ln[i]) for ln in all_lines if i < len(ln)]
        # الشرط 1: السعر أولاً فوق الجميع (سريعة وسلّم).
        p_ok = all(f_close > v for v in f_all)
        if p_ok:
            price_ok[i] = 1.0
        # الشروط 2-7: ترتيب السلّم (أزواج متجاورة تكفي بالتسلسل).
        l_ok = True
        f_ladder = [float(ladder_lines[k][i]) for k in range(K)]
        for k in range(K - 1):
            pair_state = f_ladder[k] > f_ladder[k + 1]
            if pair_state:
                pair_ok[f"pair_{ladder[k]}_{ladder[k + 1]}"][i] = 1.0
            else:
                l_ok = False
        if l_ok:
            ladder_ok[i] = 1.0
        if p_ok and l_ok:
            ok[i] = 1.0

    # الوضع strict: البوابة = الصيغة التاريخية حرفياً (سلسلة بترتيب
    # التمرير) — مستقلة عن أعمدة التشخيص أعلاه (تبقى معلوماتية).
    if mode_n == EMA_STACK_MODE_STRICT and lengths:
        ok = [0.0] * N
        given_lines: List[List[Optional[float]]] = [
            vals.get(n) or [None] * N for n in lengths
        ]
        for i in range(N):
            if ready[i] < 0.5:
                continue
            chain = True
            v0 = given_lines[0][i]
            if v0 is None or not (float(closes_f[i]) > float(v0)):
                chain = False
            else:
                f_given = [float(given_lines[k][i]) for k in range(len(lengths))]
                for k in range(len(lengths) - 1):
                    if not (f_given[k] > f_given[k + 1]):
                        chain = False
                        break
            if chain:
                ok[i] = 1.0

    ladder_txt = " > ".join(f"EMA{n}" for n in ladder) if ladder else "(بلا سلّم)"
    pairs_out: List[Dict[str, Any]] = []
    for a, b in pair_defs:
        pairs_out.append({
            "a": int(a), "b": int(b),
            "label": f"ema_{a} > ema_{b}",
            "ok": pair_ok[f"pair_{a}_{b}"],
        })

    return {
        "ok": ok,
        "ready": ready,
        "price_ok": price_ok,
        "ladder_ok": ladder_ok,
        "pairs": pairs_out,
        "meta": {
            "mode": mode_n,
            "base": int(base_n) if mode_n == EMA_STACK_MODE_HIERARCHICAL else None,
            "ladder_lengths": [int(n) for n in ladder],
            "fast_lengths": [int(n) for n in fast],
            "pair_labels": [p["label"] for p in pairs_out],
            "lengths_all": sorted(int(n) for n in lengths),
            "rule_ar": (
                "الشروط السبعة: (1) السعر فوق كل المتوسطات · (2-7) السلّم "
                f"مرتب تماماً {ladder_txt} — لا متوسط أكبر فوق أي زوج "
                f"(محقَّق بالبناء)، والأطوال الأصغر من {base_n} "
                "(سريعة مثل 8/13) معفاة من الترتيب يجوز أن تعلو فوق أعلى "
                "السلّم لكن تحت السعر"
            ) if mode_n == EMA_STACK_MODE_HIERARCHICAL else (
                "الوضع التاريخي strict: سلسلة واحدة بترتيب تمرير الأطوال "
                "كما هو: close > ema[0] > ema[1] > ... — بلا فرز ولا إعفاء "
                "(مفتاح تراجع/A-B)"
            ),
        },
    }
