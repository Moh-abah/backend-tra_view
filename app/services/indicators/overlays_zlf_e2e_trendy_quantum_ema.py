# =============================================================================
# ✅ QUANTUMEMA1 — ZLF-End-To-End-Trendy-Quantum-EMA
# «الاستراتيجية الترندية الكمومية المتوسطة المتحركة الأسية»
# =============================================================================
# مواصفة صاحب القرار: استنساخ كامل من «الاستراتيجية الترندية الكمومية»
# (ZLF-End-To-End-Trendy-Quantum) + **بوابة ثانية جوار بوابة المنطقة**
# (قمّة أعلى من قمّة + قاع أعلى من قاع HH+HL):
#
#   الشرط الثاني للمنطقة المسموحة: أن يتخطى السعر المتوسطات الستة لأعلى،
#   على أن تترتب متوسطات EMA تنازلياً على الشارت تحت السعر:
#       EMA 21 أولاً (الأعلى) ← EMA 50 ← EMA 100 ← EMA 200 ← EMA 350
#       ← ثم أسفلهم جميعاً EMA 500
#   إذا تحقق هذا الترتيب بالتزامن مع تحقق (HH + HL) هنا يُسمح بالتقاط
#   إشارات الشراء حسب الشروط.
#
# المتوسطات الستة تُحسب على **فريم الساعة** (resolution="60" — دائماً في
# الافتراضي، قابل للتخصيص من الواجهة) عبر نواة MTF EMA (MTFEMA1 — نفس
# سكربت Pine الذي سلّمه صاحب القرار: ta.ema على شموع HTF ثم
# request.security بلا استشراف — الشريط النامي لا يُرى) وتُرسم خطوطها
# على شموع فريم الشارت الحالي (15m) — لكل شمعة قيمة = EMA لآخر شمعة
# ساعة مغلقة عند لحظة ≤ إغلاقها.
#
# البنية (طبقة سياسات رقيقة فوق المحرك الكمي — لا استنساخ):
#   1) يُحسب المحرك الكمي zigzag_fib_e2e_trendy_quantum حرفياً (نفس
#      المعاملات) → كل أعمدته تُمرَّر كما هي (عقدَي zzfetq_* الكمية + zzfet_*
#      الترندية — بيانات الرسم الكاملة بت-بت).
#   2) تُبنى شموع الساعة مرة واحدة (بَكرات HTF من شموع القاعدة) وتُحسب
#      عليها EMA(21/50/100/200/350/500) ببذرة SMA بنمط TradingView، ثم
#      تُسقط على شموع القاعدة بلا أي نظر مستقبلية.
#   3) بوابة الرصة (stack): close > ema21 > ema50 > ema100 > ema200 >
#      ema350 > ema500 (الستة كلها صالحة) — حالة لحظية لكل شمعة قاعدة.
#   4) البوابة النهائية على الدخول (شفافية كاملة — فوق الكمومية):
#        zzfetqe_entry_s{n}        = نهائي الكمومية ∧ رصة EMA موافقة
#        zzfetqe_entry_eblocked_s{n} = نهائي الكمومية ∧ الرصة غير موافقة
#      ema_gate: [s1,s2,s3] افتراضياً · "none" = تعطيل بوابة EMA
#      (بيانات الرصة تظل تُحتسب وتُرجع — شفافية بنائية مثل zone_gate).
#
# عقد الرسم: كل ما ترجعه الكمومية بحذافيره (zzfetq_* + zzfet_*) + الأعمدة
# الجديدة zzfetqe_ema_{len} الستة (خطوط الرسم على فريم الشارت) + حالة
# البوابة وأحداثها — بالإضافة إلى قسم الألوان الستة (من مواصفة صاحب
# القرار بالصورة: أخضر/بنفسجي/أصفر/أحمر/أزرق/رمادي) في ema.colors
# ليستخدمه الفرونت إند مباشرة.
#
# ✅ STRUCT1 — بوابة الهيكل الكبير (STRUCT-STRICT · صرامة حرفية):
#      «قمة أعلى من القمة السابقة ∧ قاع أعلى من القاع السابق» مقروءة على
#      الهيكل الكبير المرئي (المحاور الكبرى المتبادلة قمة/قاع — لا المحاور
#      الصغيرة اليومية التي يرسمها زقزاق length=226 داخل الصعود الواحد).
#      كل محور كبير يُقرأ عند شمعة تأكيده فقط (سببية كاملة بلا استشراف
#      ولا إعادة رسم): القمة الكبرى تؤكد عند أول إغلاق ≤ قمته×(1−R%)
#      والقاع الكبير عند أول إغلاق ≥ قاعه×(1+R%) — R = struct_reversal_pct
#      (افتراضي 22% — قابل للتخصيص من الحمولة/الواجهة).
#      الأعمدة الجديدة (إضافة صرفة — لا يمس أي عمود قائم بت-بت):
#        zzfetqe_struct_last_high / zzfetqe_struct_prev_high
#        zzfetqe_struct_last_low  / zzfetqe_struct_prev_low
#        zzfetqe_struct_hh_hl  (1.0 فقط عندما القمة>القمة ∧ القاع>القاع)
#
# العقد: كل الأسماء الجديدة zzfetqe_* → ind_zzfetqe_* لا تتداخل مع zzfet_*
# (الترندية) ولا zzfetq_* (الكمومية) ولا zzfe_*/zzf_*/trf_*/zzfb_*/zzfetm_*.
# =============================================================================

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# المحرك الكمي (المصدر الموحد لكل بيانات الترندية + المنطقة الكمومية)
from app.services.indicators.overlays_zlf_e2e_trendy_quantum import (
    ZLF_E2E_TRENDY_QUANTUM_ENGINE_NAME,
    zigzag_fib_e2e_trendy_quantum,
)
# نواة MTF EMA (MTFEMA1 — سكربت Pine بحذافيره: بناء شموع HTF + EMA ببذرة
# SMA بنمط TradingView + إسقاط بلا استشراف) — نعيد استخدام دوالها مباشرة
# (بناء البَكرات مرة واحدة لكل الأطوال الستة).
from app.services.indicators.overlays_mtf_ema import (
    _build_htf_bars,
    _ema_tv,
    _norm_candles_arrays,
    _parse_resolution,
    _source_from_ohlc,
)
# ✅ ZONE-EXIT-TF1 — فريم هيكل الخروج (CHoCH على أي فريم): آلة المنطقة
# على شموع HTF + الإسقاط السببي على شموع القاعدة (الدخول والمنطقة
# المسموحة يبقيان على فريم الشارت كما هما بلا أي كسر).
from app.services.indicators.overlays_zone_exit_mtf import (
    ZONE_EXIT_TF_SPEC,
    compute_zone_exit_mtf,
    norm_zone_exit_resolution,
)
# ✅ EMAGATE-UNIFIED — نواة بوابة رصة EMA الموحدة المركزية (الشروط
# السبعة — شرح صاحب القرار 2026-11-19): «موحد ومركزي ومنظم» — المحرك
# الوحيد الذي يحسب الرصة هو هذه النواة، وكل استراتيجية فيها البوابة
# (الكمومية المتوسطة نفسها + كموميه الزخم الاولى QMOM1 بالتفويض)
# تمر من هنا حصراً.
from app.services.indicators.ema_stack_gate import (
    DEFAULT_EMA_STACK_BASE as _EMAGATE_DEFAULT_BASE,
    DEFAULT_EMA_STACK_MODE as _EMAGATE_DEFAULT_MODE,
    compute_ema_stack_gate,
    norm_ema_stack_base as _norm_ema_stack_base,
    norm_ema_stack_mode as _norm_ema_stack_mode,
)

logger = logging.getLogger(__name__)

__all__ = [
    "zigzag_fib_e2e_trendy_quantum_ema",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_SPEC",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_GATE",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_LENGTHS",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_RESOLUTION",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_COLORS",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_STACK_MODE",
    "ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_STACK_BASE",
]

# ---------------------------------------------------------------------------
# هوية المحرك المنفصل (عقد التمايز الكامل)
# ---------------------------------------------------------------------------
ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME = "ZLF-End-To-End-Trendy-Quantum-EMA"
ZLF_E2E_TRENDY_QUANTUM_EMA_SPEC = "QUANTUMEMA1-e2e-trendy-quantum-ema"

# القوالب الافتراضية (كلها قابلة للتخصيص من الواجهة — لا أرقام داخل الكود):
#   - أطوال EMA الستة بالترتيب التنازلي للرصة (EMA21 أعلى ← EMA500 أسفل)
#   - فريم الحساب: الساعة دائماً («60» — قرار صاحب القرار)
#   - الأنواع المبوّبة ببوابة الرصة: الثلاثة كلها (وقوعة احتياطية عند
#     الاستدعاء بلا معاملات — المرجع المعتمد يعيش في بريسِت الاستراتيجية)
ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_LENGTHS: Tuple[int, ...] = (21, 50, 100, 200, 350, 500)
ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_RESOLUTION: str = "60"
ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_GATE: Tuple[str, ...] = ("s1", "s2", "s3")
# ✅ EMAGATE-UNIFIED — قوالب وضع الرصة الهرمي (الشروط السبعة):
#   · الوضع الافتراضي hierarchical: السعر فوق الكل + السلّم (≥ القاعدة)
#     مرتب تماماً + الأسرع من القاعدة (مثل 8/13) معفاة من الترتيب —
#     مستقل عن ترتيب تمرير الأطوال ويتكيف مع أي مجموعة جزئية («إن وجد»).
#   · الوضع strict: الصيغة التاريخية حرفياً (سلسلة بترتيب التمرير) —
#     مفتاح تراجع/A-B. للتكوينات القياسية الاثنان بت-بت.
ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_STACK_MODE: str = _EMAGATE_DEFAULT_MODE
ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_STACK_BASE: int = _EMAGATE_DEFAULT_BASE

# ألوان الخطوط الستة (مواصفة صاحب القرار بالصورة — يستخدمها الفرونت إند
# مباشرة من ema.colors في استجابة المحرك عند رسم الشارت):
#   EMA 21  أخضر     · EMA 50 بنفسجي    · EMA 100 أصفر/برتقالي
#   EMA 200 أحمر      · EMA 350 أزرق    · EMA 500 رمادي
# ✅ SPLIT-TP1 (جلسة الترندات الجديدة 8/13): أُضيف لونان للترندات الجديدة
#   EMA 8  سماوي (كلاسيك) · EMA 13 كهرماني/ذهبي — أي طول مخصص آخر
#   يُلوَّن تلقائياً من لوحة الاحتياط الدائرية أدناه (لا خط بلا لون أبداً).
ZLF_E2E_TRENDY_QUANTUM_EMA_COLORS: Dict[int, str] = {
    8: "#00BCD4",    # سماوي (الترند الجديد الأول — EMA 8)
    13: "#FFC107",   # كهرماني/ذهبي (الترند الجديد الثاني — EMA 13)
    21: "#4CAF50",   # أخضر
    50: "#9C27B0",   # بنفسجي
    100: "#FF9800",  # أصفر/برتقالي
    200: "#F44336",  # أحمر
    350: "#2196F3",  # أزرق
    500: "#9E9E9E",  # رمادي
}

# ✅ SPLIT-TP1 — لوحة احتياط دائرية لأي طول مخصص غير موجود في القاموس
# الرئيسي (مثل 30 · 233 · أي طول يضيفه صاحب القرار مستقبلاً من الفرونت):
# كل طول بلا لون رسمي يأخذ اللون التالي بالترتيب — لا يبقى أي خط بلا لون
# يمنع رسمه (علة «الترندات الجديدة 8/13 لم تُرسم» عولجت من جذرها).
ZLF_E2E_TRENDY_QUANTUM_EMA_COLOR_FALLBACKS: Tuple[str, ...] = (
    "#00BCD4",  # سماوي
    "#FFC107",  # كهرماني
    "#E91E63",  # وردي
    "#8BC34A",  # أخضر فاتح
    "#795548",  # بني
    "#673AB7",  # بنفسجي غامق
    "#009688",  # تركوازي
    "#FF5722",  # برتقالي غامق
    "#3F51B5",  # نيلي
    "#CDDC39",  # لايم
    "#7C4DFF",  # بنفسجي فاتح
    "#FF9800",  # برتقالي
)


def _ema_line_color(length: Any) -> str:
    """✅ لون خط EMA لطول أي — القاموس الرسمي ثم لوحة الاحتياط الدائرية.

    يعيد دائماً لوناً صالحاً (لا None أبداً) — أي طول مخصص (8/13/30/233...)
    يُرسم بلون. القاموس الرئيسي للأطوال المعروفة والاحتياط لكل جديد.
    """
    try:
        n = int(length)
    except (TypeError, ValueError):
        return ZLF_E2E_TRENDY_QUANTUM_EMA_COLOR_FALLBACKS[0]
    col = ZLF_E2E_TRENDY_QUANTUM_EMA_COLORS.get(n)
    if col:
        return col
    return ZLF_E2E_TRENDY_QUANTUM_EMA_COLOR_FALLBACKS[
        (n * 7 + 3) % len(ZLF_E2E_TRENDY_QUANTUM_EMA_COLOR_FALLBACKS)]

_EMA_GATE_KIND = {"s1": 1, "1": 1, "s2": 2, "2": 2, "s3": 3, "3": 3}


# ✅ STRUCT1 — افتراضي نسبة انعكاس تأكيد محاور الهيكل الكبير (22%).
#      معايرة على GOLD-MC1 · THETAUSDT · 15m (2020→2026): أعلى نسبة حجب
#      للخاسرات مع أقل تضحية بالرابحات وفق قراءة صاحب القرار للهيكل.
ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_STRUCT_REVERSAL_PCT: float = 22.0

# ✅ EBREAK1 — افتراضيات آلة «كسر EMA-N → نزول X% → استرداد قمة الشمعة
#      الكاسرة» (الدخول الثاني): خط الكسر = EMA-100 من رصة الساعة (طلب
#      صاحب القرار: «خروج كسر ال100»)، ونزوع التسليح = 3% من سعر الكسر
#      («ونزول السعر 3% من هذا الكسر»).
ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_LENGTH: int = 100
ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_DROP_PCT: float = 3.0


def _compute_ema_break_reclaim(
    high: List[float],
    low: List[float],
    close: List[float],
    ema_line: Sequence[Optional[float]],
    drop_pct: float,
) -> Tuple[List[float], List[Optional[float]], List[Optional[float]],
            List[float], List[float], List[Dict[str, Any]]]:
    """✅ EBREAK1 — آلة حالة «الكسر → النزول → الاسترداد» (الدخول الثاني).

    سببية كاملة بلا استشراف وبلا إعادة رسم: كل عمود عند الشمعة i لا يعتمد
    إلا على الشموع ≤ i. الحلقة (episode) تُدار بقيم شمعة الكسر نفسها:

    1. **شمعة الكسر** (break): أول شمعة يغلق فيها السعر تحت خط EMA-N بعد
       شمعة أغلقت ≥ الخط (عبور هابط — وأول شمعة صالحة تحت الخط تُحسب
       كسراً تحفظياً عند بداية البيانات). عند الكسر نثبّت مرجعي الحلقة:
       قمة الشمعة الكاسرة (ref_high) وسعر كسرها = إغلاقها (ref_close).
    2. **التسليح** (drop_ok): أول قاع low ≤ ref_close×(1−X%) من شمعة
       الكسر نفسها فصاعداً (ذيل شمعة الكسر جزء من النزول) — «نزول
       السعر X% من هذا الكسر».
    3. **الاسترداد** (reclaim): بعد التسليح، أول شمعة يغلق فيها >
       قمة الشمعة الكاسرة → إشارة الدخول الثاني (قيمة واحدة في الحلقة)
       — «اذا اغلقت الشمعة فوق قمة الشمعة الكاسرة اشتري دخول ثاني».
       يجوز أن يكتمل التسليح والإطلاق في نفس الشمعة (مطرقة استرداد:
       ذيل ينزل 3% ثم إغلاق فوق قمة شمعة الكسر).

    انتهاء الحلقة: إما بإطلاق الاسترداد (إشارة واحدة لكل حلقة — «دخول
    ثاني» مفرد) أو بكسر جديد (عبور هابط جديد يفتح حلقة بقيم الشمعة
    الكاسرة الجديدة). الشمعة التي تغلق ≥ الخط لا تلغي حلقة قائمة ولا
    تطلق شيئاً — قيم الحلقة تظل من شمعة الكسر الأصلية حرفياً.

    يرجع (break_ev[], ref_high[], ref_close[], drop_ok[], reclaim[], events).
    """
    N = len(close)
    break_ev: List[float] = [0.0] * N
    ref_high: List[Optional[float]] = [None] * N
    ref_close: List[Optional[float]] = [None] * N
    drop_ok: List[float] = [0.0] * N
    reclaim: List[float] = [0.0] * N
    events: List[Dict[str, Any]] = []
    p = float(drop_pct) / 100.0
    below_prev: Optional[bool] = None   # حالة آخر شمعة صالحة (None = بداية)
    active = False
    r_high: Optional[float] = None
    r_close: Optional[float] = None
    armed = False
    for i in range(N):
        e = ema_line[i] if i < len(ema_line) else None
        if e is None:
            continue                        # إحماء EMA — لا حالة بعد
        ci = float(close[i])
        below = ci < float(e)
        if below and below_prev is not True:
            # حدث كسر: عبور هابط جديد (أول شمعة صالحة تحت الخط تُحسب كسراً
            # تحفظياً عند بداية البيانات — below_prev=None)
            active = True
            r_high = float(high[i])
            r_close = ci
            armed = float(low[i]) <= r_close * (1.0 - p)
            break_ev[i] = 1.0
            events.append({
                "bar": i, "kind": "break", "ref_high": r_high,
                "ref_close": r_close, "armed": bool(armed),
            })
        elif active and not armed:
            # داخل حلقة قائمة — حدّث التسليح بقاع هذه الشمعة أياً كانت
            # ناحيتها من الخط (ذيل مطرقة فوق الخط جزء من النزول أيضاً)
            if float(low[i]) <= r_close * (1.0 - p):
                armed = True
        if active:
            ref_high[i] = r_high
            ref_close[i] = r_close
            drop_ok[i] = 1.0 if armed else 0.0
            if armed and ci > r_high:
                reclaim[i] = 1.0
                events.append({
                    "bar": i, "kind": "reclaim", "ref_high": r_high,
                    "ref_close": r_close, "close": ci,
                })
                # إشارة واحدة لكل حلقة — تُغلق وينتظر كسر جديد
                active = False
                r_high = None
                r_close = None
                armed = False
        below_prev = below
    return break_ev, ref_high, ref_close, drop_ok, reclaim, events


def _compute_macro_structure(
    high: List[float],
    low: List[float],
    close: List[float],
    reversal_pct: float,
) -> Tuple[List[Optional[float]], List[Optional[float]],
           List[Optional[float]], List[Optional[float]], List[Dict[str, Any]]]:
    """✅ STRUCT1 — حالة الهيكل الكبير (زقزاق الانحراف السببي المتبادل).

    المحاور الكبرى متبادلة قمة/قاع: القمة الكبرى المرشحة = أعلى قيمة high
    منذ آخر قاع كبرى مؤكد، وتؤكد عند أول شمعة يغلق فيها ≤ قمته×(1−R%).
    والقاع الكبرى المرشح = أدنى قيمة low منذ آخر قمة كبرى مؤكدة، ويؤكد
    عند أول شمعة يغلق فيها ≥ قاعه×(1+R%). بعد تأكيد القمة نبحث عن القاع
    (والعكس) — تبادل كامل بلا استشراف وبلا إعادة رسم (كل حالة نهائية
    عند شمعة تأكيدها ولا تتغير بعدها أبداً).

    يرجع (last_high[], prev_high[], last_low[], prev_low[], events):
    قيم الأعمدة عند كل شمعة = حالة آخر قمة/قاع كبريين مؤكدين حتىها
    (None قبل اكتمال أول زوج قمم/قيعان مؤكد).
    """
    N = len(close)
    lh: List[Optional[float]] = [None] * N
    ph: List[Optional[float]] = [None] * N
    ll: List[Optional[float]] = [None] * N
    pl: List[Optional[float]] = [None] * N
    events: List[Dict[str, Any]] = []
    if N == 0:
        return lh, ph, ll, pl, events
    last_h: Optional[float] = None
    prev_h: Optional[float] = None
    last_l: Optional[float] = None
    prev_l: Optional[float] = None
    cand_h_price: float = high[0]
    cand_h_bar: int = 0
    cand_l_price: float = low[0]
    cand_l_bar: int = 0
    mode: Optional[str] = None  # None=غير محدد · 'up'=بحث عن قمة · 'down'=بحث عن قاع
    down_thr = 1.0 - reversal_pct / 100.0
    up_thr = 1.0 + reversal_pct / 100.0
    for i in range(N):
        if mode in (None, "up") and high[i] > cand_h_price:
            cand_h_price = high[i]
            cand_h_bar = i
        if mode in (None, "down") and low[i] < cand_l_price:
            cand_l_price = low[i]
            cand_l_bar = i
        confirmed: Optional[Tuple[str, float, int]] = None
        if mode in (None, "up") and close[i] <= cand_h_price * down_thr:
            confirmed = ("top", cand_h_price, cand_h_bar)
        elif mode in (None, "down") and close[i] >= cand_l_price * up_thr:
            confirmed = ("bottom", cand_l_price, cand_l_bar)
        if confirmed is not None:
            kind, price, pbar = confirmed
            if kind == "top":
                prev_h = last_h
                last_h = price
                mode = "down"
                seg = low[pbar:i + 1]
                cand_l_price = min(seg)
                cand_l_bar = pbar + seg.index(cand_l_price)
            else:
                prev_l = last_l
                last_l = price
                mode = "up"
                seg = high[pbar:i + 1]
                cand_h_price = max(seg)
                cand_h_bar = pbar + seg.index(cand_h_price)
            events.append({
                "bar": int(i),
                "pivot_bar": int(pbar),
                "kind": kind,
                "price": float(price),
                "prev_price": (
                    float(prev_h) if kind == "top" and prev_h is not None
                    else (float(prev_l) if kind == "bottom" and prev_l is not None
                          else None)),
            })
        lh[i] = last_h
        ph[i] = prev_h
        ll[i] = last_l
        pl[i] = prev_l
    return lh, ph, ll, pl, events


def _norm_ema_gate(raw: Any) -> List[int]:
    """تطبيع أنواع الإشارات المبوّبة برصة EMA — يقبل s1/s2/s3 أو 1/2/3.

    None            = البوابة على الثلاثة كلها (الافتراضي).
    «none»/«off»    = بوابة EMA معطلة كلياً (مفتاح عزل A/B — بيانات الرصة
                     والخطوط الستة تظل تُحتسب وتُرجع كما تظل المنطقة محسوبة
                     مع zone_gate=none).
    قائمة فارغة/قيم غير معروفة = معطلة كلياً أيضاً.
    """
    if raw is None:
        return [1, 2, 3]
    if isinstance(raw, str):
        s_all = str(raw).strip().lower()
        if s_all in ("none", "off", "false", "0", ""):
            return []
        raw = [x for x in raw.replace(";", ",").split(",") if str(x).strip()]
    out = set()
    for x in raw:
        s = str(x).strip().lower()
        if s in _EMA_GATE_KIND:
            out.add(_EMA_GATE_KIND[s])
    return sorted(out)


def _norm_ema_lengths(raw: Any) -> List[int]:
    """تطبيع أطوال EMA — قائمة أعداد صحيحة ≥ 1 بالترتيب التنازلي للرصة.

    None = الافتراضي الحرفي (21/50/100/200/350/500). أي عدد أطوال مقبول
    (الرصة تُبنى ديناميكياً من القائمة — عمود لكل طول zzfetqe_ema_{len}).
    """
    if raw is None:
        return list(ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_LENGTHS)
    if isinstance(raw, (int, float)):
        raw = [raw]
    try:
        items = list(raw)
    except TypeError:
        return list(ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_LENGTHS)
    lengths: List[int] = []
    for x in items:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n >= 1 and n not in lengths:
            lengths.append(n)
    if not lengths:
        return list(ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_LENGTHS)
    return lengths


def _compute_mtf_ema_family(
    candles: Any,
    lengths: Sequence[int],
    source: str,
    offset: int,
    resolution: str,
) -> Tuple[Dict[str, List[Optional[float]]], Dict[str, Any]]:
    """عائلة MTF EMA على شموع القاعدة — بناء HTF واحد لكل الأطوال.

    نفس عقد MTFEMA1 الحرفي (سكربت Pine): EMA(length) على شموع HTF ببذرة
    SMA بنمط TradingView، وقيمة كل شمعة قاعدة = EMA لآخر شمعة HTF مغلقة
    عند لحظة ≤ إغلاقها (بلا نظر مستقبلية — الشريط النامي لا يُرى)، ثم
    إزاحة plot(offset) (موجب = يميناً كما في Pine).

    يرجع ({zzfetqe_ema_{len}: قيم JSON-آمنة}, meta) — meta تحمل تفاصيل
    الفريم/البَكرات/التقييد الدفاعي (مطابقة عقد mtf_ema الأصلي).
    """
    t, o, h, l, c = _norm_candles_arrays(candles)
    N = int(t.size)
    res_info = _parse_resolution(resolution)

    empty: Dict[str, List[Optional[float]]] = {f"ema_{int(n)}": [None] * N for n in lengths}
    meta: Dict[str, Any] = {
        "resolution": res_info["label"],
        "htf_kind": res_info["kind"],
        "htf_bars": 0,
        "lengths": [int(x) for x in lengths],
        "source": str(source),
        "offset": int(offset),
    }
    if N == 0:
        return empty, meta

    # خطوة شمعة القاعدة (أصغر فرق زمني موجب — متين أمام فجوات البيانات)
    if N > 1:
        import numpy as np

        diffs = np.diff(t)
        pos = diffs[diffs > 0]
        base_step = int(pos.min()) if pos.size else 60_000
    else:
        base_step = 60_000

    # HTF لا يمكن أن يكون أدنى من فريم الشارت نفسه — تقييد دفاعي (متسق
    # رياضياً: يصبح EMA على الفريم الحالي) مع تحذير في meta.
    htf_step = res_info.get("step_ms")
    clamped = False
    if res_info["kind"] == "fixed" and htf_step is not None and htf_step < base_step:
        logger.warning(
            "QUANTUM-EMA: resolution '%s' (%d ms) أدنى من فريم الشارت (%d ms) — "
            "استُخدم فريم الشارت نفسه", res_info["label"], htf_step, base_step)
        htf_step = base_step
        res_info = dict(res_info, step_ms=base_step)
        clamped = True

    starts, closes, b_o, b_h, b_l, b_c = _build_htf_bars(t, o, h, l, c, res_info)
    M = int(starts.size)
    meta["htf_bars"] = M
    meta["htf_step_ms"] = int(htf_step) if htf_step is not None else None
    meta["base_step_ms"] = base_step
    meta["resolution_clamped_to_chart_tf"] = clamped

    src_htf = _source_from_ohlc(b_o, b_h, b_l, b_c, source)

    # ── التطابق بلا نظر مستقبلية: شمعة القاعدة ترى آخر شمعة HTF مع
    # close_time ≤ لحظة إغلاقها (t_i + base_step)
    import numpy as np

    cutoff = t + base_step
    j = np.searchsorted(closes, cutoff, side="right") - 1 if M else np.full(N, -1, dtype=np.int64)
    valid = j >= 0
    j_safe = np.clip(j, 0, max(M - 1, 0))

    def _jsonable(v) -> Optional[float]:
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if math.isfinite(f) else None

    out: Dict[str, List[Optional[float]]] = {}
    first_valid: Dict[str, Optional[int]] = {}
    for n in lengths:
        ema_htf = _ema_tv(src_htf, int(n)) if M else None
        if M:
            vals = np.where(valid, ema_htf[j_safe], np.nan)
        else:
            vals = np.full(N, np.nan, dtype=float)

        # ── إزاحة plot(offset): shifted[i] = value[i - offset] (Pine حرفياً)
        off = int(offset)
        if off != 0:
            idx = np.arange(N, dtype=np.int64)
            src_idx = idx - off
            ok = (src_idx >= 0) & (src_idx < N)
            shifted = np.full(N, np.nan, dtype=float)
            shifted[ok] = vals[src_idx[ok]]
            vals = shifted

        col = [ _jsonable(v) for v in vals.tolist() ]
        out[f"ema_{int(n)}"] = col
        fv = next((i for i, v in enumerate(col) if v is not None), None)
        first_valid[f"ema_{int(n)}"] = fv

    meta["first_valid_index"] = first_valid
    return out, meta


# ---------------------------------------------------------------------------
# المحرك الرئيسي — ZLF-End-To-End-Trendy-Quantum-EMA (بوابة الرصة فوق الكمي)
# ---------------------------------------------------------------------------
def zigzag_fib_e2e_trendy_quantum_ema(
    candles: Any,
    length: int = 100,
    reverse: bool = False,
    levels: Optional[Sequence[float]] = None,
    extend_right: bool = True,
    extend_leg_to_live: bool = True,
    mode: str = "luxalgo",
    depth: int = 12,
    deviation: float = 20.0,
    backstep: int = 3,
    launch_touch_ticks: float = 1.0,
    trend_periods: Any = None,
    trend_confirm: Any = "majority",
    trend_gate: Any = None,
    zone_gate: Any = None,
    ema_lengths: Any = None,
    ema_resolution: Any = None,
    ema_source: str = "close",
    ema_offset: int = 0,
    ema_gate: Any = None,
    zone_exit_resolution: Any = None,
    zone_exit_length: Any = None,
    # ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة للدخول (HH+HL على أي فريم)
    zone_resolution: Any = None,
    zone_length: Any = None,
    ema_stack_mode: Any = None,
    ema_stack_base: Any = None,
    # ✅ STRUCT1 — نسبة انعكاس تأكيد محاور الهيكل الكبير (قمة/قاع كبرى).
    #      None = الافتراضي 22.0 (معايرة GOLD-MC1 على THETAUSDT 15m).
    struct_reversal_pct: Any = None,
    # ✅ EBREAK1 — آلة «كسر EMA-N → نزول X% → استرداد قمة الشمعة الكاسرة»
    #      (الدخول الثاني بعد الخروج على كسر الـEMA). افتراضياً: خط 100
    #      من رصة الساعة ونزول 3% — حرفي طلب صاحب القرار.
    ema_break_length: Any = None,
    ema_break_drop_pct: Any = None,
) -> Dict[str, Any]:
    """ZLF-End-To-End-Trendy-Quantum-EMA — الكمومية بحذافيرها + بوابة رصة EMA.

    المعاملات: نفس معاملات الكمومية حرفياً (mode/length/depth/deviation/
    backstep/reverse/levels/extend_right/extend_leg_to_live/launch_touch_ticks/
    trend_periods/trend_confirm/trend_gate/zone_gate) + قالب EMA:
      ema_lengths  : أطوال المتوسطات الستة بالترتيب التنازلي للرصة
                     (افتراضياً [21, 50, 100, 200, 350, 500]).
      ema_resolution: فريم حساب المتوسطات — «60» = الساعة (الافتراضي
                     الحرفي لقرار صاحب القرار؛ قابل للتخصيص من الواجهة).
      ema_source   : مصدر السعر على شموع HTF (close/open/high/low/hl2/
                     hlc3/ohlc4 — افتراضي close).
      ema_offset   : إزاحة الرسم بالشموع (افتراضي 0 — موجب يميناً).
      ema_gate     : الأنواع المبوّبة برصة EMA — s1/s2/s3 (افتراضياً الثلاثة)
                     أو "none" لتعطيل البوابة (بيانات الرصة تبقى محسوبة).
      ema_stack_mode : ✅ EMAGATE-UNIFIED — وضع الرصة: "hierarchical"
                     (الافتراضي — الشروط السبعة: السعر فوق الكل + السلّم
                     مرتب + الأسرع من القاعدة معفاة) أو "strict" (الوضع
                     التاريخي حرفياً — سلسلة بترتيب التمرير — للتراجع/A-B).
      ema_stack_base : حدّ الإعفاء/قاعدة السلّم (افتراضي 21 — نص الشرط 2:
                     «أصغر من ema 21» معفى من الترتيب). قابلة للتعديل
                     من الواجهة مع الأطوال نفسها (تركيب/إضافة/حذف بلا كود).
      zone_exit_resolution : ✅ ZONE-EXIT-TF1 — فريم حساب هيكل الخروج
                     (CHoCH: LL+LH يغلق المنطقة ويُخرج أي صفقة مفتوحة).
                     فارغ/"none"/"base"/"chart" = فريم الشارت (السلوك
                     التاريخي بت-بت). يقبل كل الصيغ: "60"/"1h"/"240"/"4h"
                     /"1D"/"1W"/"1M"... الدخول والمنطقة المسموحة يبقيان
                     على فريم الشارت دائماً بلا أي كسر.
      zone_exit_length      : طول زقزاق هيكل الخروج على HTF (اختياري —
                     افتراضياً نفس length). يتيح ضبط حساسية بنية الخروج
                     مستقلة عن حساسية الدخول.
      ema_break_length      : ✅ EBREAK1 — طول خط EMA الذي تُدار عليه آلة
                     الدخول الثاني (كسره → نزول → استرداد) — افتراضياً 100
                     (من رصة الساعة نفسها؛ وإن لم يكن ضمن الأطوال حُسب خط
                     إضافي بنفس البناء).
      ema_break_drop_pct    : ✅ EBREAK1 — نسبة النزول من سعر الكسر لتسليح
                     الدخول الثاني (افتراضياً 3%) — من إغلاق شمعة الكسر،
                     عدّاً ذيلها فصاعداً.

    المخرجات: سلاسل تحتوي عقد التمايز معاً — zzfetqe_* الجديدة + zzfetq_*
    الكمية (62) + zzfet_* الترندية (47) ممرَّرة بت-بت (بيانات الرسم الكاملة
    كما كانت الكمومية ترجعها بحذافيرها + الخطوط الستة وحالة البوابة).
    """
    # ------------------------------------------------------------------
    # 1) المحرك الكمي الأصلي — حرفياً بنفس المعاملات (المصدر الموحد لكل
    #    بيانات الترندية zzfet_* + الكمومية zzfetq_* + المنطقة zone)
    # ------------------------------------------------------------------
    base = zigzag_fib_e2e_trendy_quantum(
        candles,
        length=length,
        reverse=reverse,
        levels=levels,
        extend_right=extend_right,
        extend_leg_to_live=extend_leg_to_live,
        mode=mode,
        depth=depth,
        deviation=deviation,
        backstep=backstep,
        launch_touch_ticks=launch_touch_ticks,
        trend_periods=trend_periods,
        trend_confirm=trend_confirm,
        trend_gate=trend_gate,
        zone_gate=zone_gate,
        # ✅ ZONE-ENTRY-MTF1 — تمرير حرفي لفريم المنطقة المسموحة للدخول
        zone_resolution=zone_resolution,
        zone_length=zone_length,
    )
    base_series: Dict[str, List[Optional[float]]] = base.get("series") or {}

    # شموع القاعدة (t/o/h/l/c) — للحكم على السعر فوق الرصة
    t, o, h, l, c = _norm_candles_arrays(candles)
    N = int(t.size)
    ema_cells = _norm_ema_gate(ema_gate)
    ema_lengths_norm = _norm_ema_lengths(ema_lengths)
    ema_stack_mode_norm = _norm_ema_stack_mode(ema_stack_mode)
    ema_stack_base_norm = _norm_ema_stack_base(ema_stack_base)
    res_raw = ema_resolution if ema_resolution is not None else ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_RESOLUTION
    src_norm = str(ema_source or "close").strip().lower()
    if src_norm not in ("open", "high", "low", "close", "hl2", "hlc3", "ohlc4"):
        src_norm = "close"

    # ------------------------------------------------------------------
    # 2) عائلة MTF EMA — بناء HTF واحد (فريم الساعة افتراضياً) وستة EMA
    #    عليه، مسقطة على شموع القاعدة بلا نظر مستقبلية (عقد MTFEMA1).
    # ------------------------------------------------------------------
    ema_cols, ema_meta = _compute_mtf_ema_family(
        candles, ema_lengths_norm, src_norm, int(ema_offset or 0), str(res_raw))

    # ------------------------------------------------------------------
    # 3) ✅ EMAGATE-UNIFIED — بوابة الرصة الموحدة (الشروط السبعة):
    #    النواة المركزية compute_ema_stack_gate هي المحرك الوحيد للرصة
    #    (كل استراتيجية فيها البوابة تمر من هنا حصراً — عقد «موحد
    #    ومركزي ومنظم»). الوضع الافتراضي hierarchical: (1) السعر فوق
    #    كل المتوسطات + (2-7) السلّم مرتب تماماً بالأطوال (EMA الأصغر فوق
    #    الأكبر — عمود تشخيص لكل زوج متجاور) + الأسرع من القاعدة (مثل
    #    8/13) معفاة من الترتيب يجوز أن تعلو فوق أعلى السلّم تحت السعر.
    #    الوضع strict = الصيغة التاريخية حرفياً (سلسلة بترتيب التمرير).
    #    للتكوينات القياسية المرتبة الاثنان بت-بت (بطارية التحقق).
    # ------------------------------------------------------------------
    e_lines: List[List[Optional[float]]] = [
        ema_cols.get(f"ema_{int(n)}") or [None] * N for n in ema_lengths_norm
    ]
    stack = compute_ema_stack_gate(
        [float(x) for x in c],
        {int(n): (ema_cols.get(f"ema_{int(n)}") or [None] * N)
         for n in ema_lengths_norm},
        mode=ema_stack_mode_norm,
        base=ema_stack_base_norm,
    )
    stack_meta: Dict[str, Any] = stack["meta"]
    e_ok: List[float] = [1.0 if v else 0.0 for v in stack["ok"]]
    e_ready: List[float] = [1.0 if v else 0.0 for v in stack["ready"]]
    e_price_ok: List[float] = [1.0 if v else 0.0 for v in stack["price_ok"]]
    e_ladder_ok: List[float] = [1.0 if v else 0.0 for v in stack["ladder_ok"]]
    stack_pairs: List[Dict[str, Any]] = stack["pairs"]
    e_enter: List[float] = [0.0] * N
    e_exit: List[float] = [0.0] * N
    ema_signals: List[Dict[str, Any]] = []
    stack_on = False

    for i in range(N):
        vals = [ln[i] if i < len(ln) else None for ln in e_lines]
        close_i = c[i] if i < len(c) else None
        # أحداث دخول/خروج حالة الرصة (عند الشمعة نفسها)
        now_on = e_ok[i] > 0.5
        if now_on and not stack_on:
            stack_on = True
            e_enter[i] = 1.0
            ema_signals.append({
                # int() صريح — t من _norm_candles_arrays (numpy): القيمة الخام
                # int64 غير قابلة للتسلسل JSON في مسار overlays/compute الحي.
                "bar": int(i), "time": int(t[i]) if i < len(t) else None,
                "side": "ema", "signal": (
                    "ZLF-E2E-Trendy-Quantum-EMA Stack ENTER ("
                    + str(stack_meta.get("rule_ar", "")) + ")"),
                "engine": ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME,
                "close": float(close_i) if close_i is not None else None,
                "ema_values": [float(v) if v is not None else None for v in vals],
                "resolution": ema_meta.get("resolution"),
                "stack_mode": stack_meta.get("mode"),
            })
        elif not now_on and stack_on:
            stack_on = False
            e_exit[i] = 1.0
            ema_signals.append({
                "bar": int(i), "time": int(t[i]) if i < len(t) else None,
                "side": "ema", "signal": (
                    "ZLF-E2E-Trendy-Quantum-EMA Stack EXIT (order broken — "
                    f"mode={stack_meta.get('mode')})"),
                "engine": ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME,
                "close": float(close_i) if close_i is not None else None,
                "resolution": ema_meta.get("resolution"),
                "stack_mode": stack_meta.get("mode"),
            })

    # ------------------------------------------------------------------
    # 4) البوابة النهائية على الدخول — فوق نهائي الكمومية مباشرة
    # ------------------------------------------------------------------
    def _base_col(name: str) -> List[Optional[float]]:
        return list(base_series.get(name) or [0.0] * N)

    cols_q_final = {n: _base_col(f"zzfetq_entry_s{n}") for n in (1, 2, 3)}

    qe_entry = [0.0] * N
    qe_entry_s = {n: [0.0] * N for n in (1, 2, 3)}
    qe_eblocked = {n: [0.0] * N for n in (1, 2, 3)}
    n_final = 0
    n_eblocked = 0
    for i in range(N):
        for n in (1, 2, 3):
            gated = n in ema_cells
            quantum_final = float(cols_q_final[n][i] or 0.0)
            if gated:
                ema_allows_i = e_ok[i] > 0.5
                if quantum_final and ema_allows_i:
                    qe_entry_s[n][i] = 1.0
                    qe_entry[i] = 1.0
                    n_final += 1
                elif quantum_final and not ema_allows_i:
                    qe_eblocked[n][i] = 1.0
                    n_eblocked += 1
            else:
                if quantum_final:
                    qe_entry_s[n][i] = 1.0
                    qe_entry[i] = 1.0
                    n_final += 1

    # ------------------------------------------------------------------
    # 5) السلاسل — zzfetqe_* الجديدة + تمرير الكمية zzfetq_* والترندية zzfet_*
    # ------------------------------------------------------------------
    # (أ) مرايا الكمومية zzfetq_* → zzfetqe_* (نفس القيم بت-بت)
    quantum_ema_series: Dict[str, List[Optional[float]]] = {}
    for k, v in base_series.items():
        ks = str(k)
        if ks.startswith("zzfetq_"):
            quantum_ema_series["zzfetqe_" + ks[len("zzfetq_"):]] = v

    # (ب) أعمدة البوابة النهائية (النهائي + الممنوع بالرصة)
    quantum_ema_series["zzfetqe_entry"] = qe_entry
    for n in (1, 2, 3):
        quantum_ema_series[f"zzfetqe_entry_s{n}"] = qe_entry_s[n]
        quantum_ema_series[f"zzfetqe_entry_eblocked_s{n}"] = qe_eblocked[n]

    # (ج) الخطوط الستة (رسم على فريم الشارت — محسوبة على فريم الساعة)
    for idx_n, n in enumerate(ema_lengths_norm):
        quantum_ema_series[f"zzfetqe_ema_{int(n)}"] = e_lines[idx_n]

    # (د) حالة الرصة وأحداثها وجاهزيتها + ✅ EMAGATE-UNIFIED التشخيص
    #     الهرمي (عمود لكل شرط من السبعة): price_ok (الشرط 1) · ladder_ok
    #     (الشروط 2-7 مجمّعة) · pair_ok_{a}_{b} (كل زوج متجاور في السلّم
    #     على حدة — مؤشرات إنذار للواجهة: أي زوج انكسر).
    quantum_ema_series["zzfetqe_ema_stack_ok"] = e_ok
    quantum_ema_series["zzfetqe_ema_stack_ready"] = e_ready
    quantum_ema_series["zzfetqe_ema_stack_enter"] = e_enter
    quantum_ema_series["zzfetqe_ema_stack_exit"] = e_exit
    quantum_ema_series["zzfetqe_ema_stack_price_ok"] = e_price_ok
    quantum_ema_series["zzfetqe_ema_stack_ladder_ok"] = e_ladder_ok
    for pr in stack_pairs:
        quantum_ema_series[
            f"zzfetqe_ema_stack_pair_ok_{int(pr['a'])}_{int(pr['b'])}"] = pr["ok"]

    # (د-2) ✅ ZONE-EXIT-TF1 — فريم هيكل الخروج (CHoCH على أي فريم):
    #      حساب حدث إغلاق المنطقة (LL+LH) على فريم HTF مستقل وإسقاطه
    #      سببياً على شموع القاعدة. الدخول والمنطقة المسموحة (zone_enter/
    #      zone_on لبوابات الدخول) يبقيان على فريم الشارت كما هما بت-بت —
    #      هذا القسم لا يمس أعمدة الدخول إطلاقاً. عند التعطيل (الافتراضي)
    #      لا يتغير أي عمود بت-بت.
    zone_exit_section: Optional[Dict[str, Any]] = {
        "enabled": False,
        "spec": ZONE_EXIT_TF_SPEC,
        "rule": "هيكل الخروج (CHoCH: LL+LH) محسوب على فريم الشارت نفسه "
                "(السلوك التاريخي) — zone_exit_resolution غير مفعّل.",
    }
    zx_res_raw = norm_zone_exit_resolution(zone_exit_resolution)
    if zx_res_raw is not None:
        try:
            zx_len = int(zone_exit_length) if zone_exit_length is not None else int(length)
        except (TypeError, ValueError):
            zx_len = int(length)
        if zx_len < 2:
            zx_len = 2
        zx = compute_zone_exit_mtf(
            candles,
            resolution=zx_res_raw,
            length=zx_len,
            reverse=reverse,
            levels=levels,
            extend_right=extend_right,
            extend_leg_to_live=extend_leg_to_live,
            mode=mode,
            depth=depth,
            deviation=deviation,
            backstep=backstep,
            launch_touch_ticks=launch_touch_ticks,
        )
        if zx is not None:
            # النسخة الأصلية على فريم الشارت تُحفظ للشفافية (A/B والرسم)
            zx_base_original = list(quantum_ema_series.get("zzfetqe_zone_exit") or [0.0] * N)
            # ⬅ الباب الجديد: حدث الخروج محسوباً على HTF ومسقوطاً سببياً
            quantum_ema_series["zzfetqe_zone_exit"] = zx["zone_exit"]
            quantum_ema_series["zzfetqe_zone_exit_base"] = zx_base_original
            quantum_ema_series["zzfetqe_zone_exit_htf_enter"] = zx["zone_enter"]
            quantum_ema_series["zzfetqe_zone_exit_htf_on"] = zx["zone_on"]
            zx_meta = dict(zx["meta"])
            zone_exit_section = {
                "enabled": True,
                "spec": ZONE_EXIT_TF_SPEC,
                "resolution": zx_meta.get("resolution"),
                "length": zx_meta.get("length"),
                "htf_bars": zx_meta.get("htf_bars"),
                "htf_step_ms": zx_meta.get("htf_step_ms"),
                "base_step_ms": zx_meta.get("base_step_ms"),
                "resolution_clamped_to_chart_tf": zx_meta.get(
                    "resolution_clamped_to_chart_tf", False),
                # ✅ ZONE-EXIT-LTF1 — هل حُسب على شموع فريم أدق حقيقية من طبقة
                # البيانات (True) أم فريم أعلى مبني من شموع الشارت (False)؟
                "ltf_real_context": zx_meta.get("ltf_real_context", False),
                "counts": zx_meta.get("counts") or {},
                "events": zx["events"],
                "rule": (zx_meta.get("rule") or
                          "هيكل الخروج (CHoCH: LL+LH) محسوب على فريم "
                          f"{zx_meta.get('resolution')} (زقزاق length={zx_meta.get('length')}) "
                          "ومسقوط سببياً على شموع القاعدة — الحدث يُعلَم عند إغلاق "
                          "شمعة الفريم المستقل التي أكدته (بلا أي استشراف). الدخول "
                          "والمنطقة المسموحة يبقيان على فريم الشارت بلا أي تغيير. "
                          "عمود الخروج zzfetqe_zone_exit أصبح مستقلاً · النسخة "
                          "الأصلية على فريم الشارت في zzfetqe_zone_exit_base · حالة "
                          "المنطقة المستقلة في zzfetqe_zone_exit_htf_on · أحداث الفتح "
                          "في zzfetqe_zone_exit_htf_enter."),
            }
        else:
            zone_exit_section = {
                "enabled": False,
                "spec": ZONE_EXIT_TF_SPEC,
                "requested_resolution": zx_res_raw,
                "rule": "تعطّل هيكل الخروج HTF دفاعياً (بيانات غير كافية أو فشل "
                        "داخلي) — السلوك التاريخي يسود بت-بت.",
            }

    # (د-3) ✅ STRUCT1 — بوابة الهيكل الكبير (STRUCT-STRICT · إضافة صرفة):
    #      حالة آخر قمة/قاع كبريين مؤكدين (زقزاق الانحراف السببي المتبادل)
    #      تُحسب هنا ولا تُقرأ إلا من أعمدة zzfetqe_struct_* الجديدة — لا
    #      أي عمود قائم يتغير بت-بت (الدخول والمخارج والمنطقة والرصة كما
    #      هي حرفياً؛ البوابة الصارمة تُفعَّل من الحمولة بشروط تشير لهذه
    #      الأعمدة: zzfetqe_struct_last_high > zzfetqe_struct_prev_high ∧
    #      zzfetqe_struct_last_low > zzfetqe_struct_prev_low).
    # ------------------------------------------------------------------
    try:
        struct_r = float(struct_reversal_pct) if struct_reversal_pct is not None \
            else ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_STRUCT_REVERSAL_PCT
    except (TypeError, ValueError):
        struct_r = ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_STRUCT_REVERSAL_PCT
    if struct_r < 2.0:
        struct_r = 2.0
    h_list = [float(x) for x in h]
    l_list = [float(x) for x in l]
    c_list = [float(x) for x in c]
    st_lh, st_ph, st_ll, st_pl, struct_events = _compute_macro_structure(
        h_list, l_list, c_list, struct_r)
    st_hh_hl: List[float] = [0.0] * N
    for i in range(N):
        if (st_lh[i] is not None and st_ph[i] is not None
                and st_ll[i] is not None and st_pl[i] is not None
                and st_lh[i] > st_ph[i] and st_ll[i] > st_pl[i]):
            st_hh_hl[i] = 1.0
    quantum_ema_series["zzfetqe_struct_last_high"] = st_lh
    quantum_ema_series["zzfetqe_struct_prev_high"] = st_ph
    quantum_ema_series["zzfetqe_struct_last_low"] = st_ll
    quantum_ema_series["zzfetqe_struct_prev_low"] = st_pl
    quantum_ema_series["zzfetqe_struct_hh_hl"] = st_hh_hl

    # (د-4) ✅ EBREAK1 — آلة «كسر EMA-N → نزول X% → استرداد قمة الشمعة
    #      الكاسرة» (الدخول الثاني · إضافة صرفة): آلة حالة سببية على خط
    #      EMA-N من عائلة رصة الساعة نفسها (أو خط إضافي بنفس البناء إن
    #      لم يكن ضمن الأطوال). لا تلمس أي عمود قائم بت-بت — أعمدة
    #      zzfetqe_ebreak_* الجديدة فقط تُضاف.
    # ------------------------------------------------------------------
    try:
        eb_len = int(ema_break_length) if ema_break_length is not None \
            else ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_LENGTH
    except (TypeError, ValueError):
        eb_len = ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_LENGTH
    if eb_len < 2:
        eb_len = ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_LENGTH
    try:
        eb_drop = float(ema_break_drop_pct) if ema_break_drop_pct is not None \
            else ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_DROP_PCT
    except (TypeError, ValueError):
        eb_drop = ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_DROP_PCT
    if not (0.0 < eb_drop <= 90.0):
        eb_drop = ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_DROP_PCT
    if eb_len in ema_lengths_norm:
        eb_line = ema_cols.get(f"ema_{int(eb_len)}") or [None] * N
        eb_source = "stack-family"
    else:
        # خط إضافي بنفس بناء العائلة (نفس المصدر/الإزاحة/الفريم) — حتمي
        # ومتطابق بت-بت مع ما كانت العائلة سترجعه لو ضُمّن الطول نفسه
        eb_extra, _ = _compute_mtf_ema_family(
            candles, [int(eb_len)], src_norm, int(ema_offset or 0), str(res_raw))
        eb_line = eb_extra.get(f"ema_{int(eb_len)}") or [None] * N
        eb_source = "extra-family"
    eb_break, eb_ref_high, eb_ref_close, eb_drop_ok, eb_reclaim, eb_events = \
        _compute_ema_break_reclaim(h_list, l_list, c_list, eb_line, eb_drop)
    quantum_ema_series["zzfetqe_ebreak_break"] = eb_break
    quantum_ema_series["zzfetqe_ebreak_ref_high"] = eb_ref_high
    quantum_ema_series["zzfetqe_ebreak_ref_close"] = eb_ref_close
    quantum_ema_series["zzfetqe_ebreak_drop_ok"] = eb_drop_ok
    quantum_ema_series["zzfetqe_ebreak_reclaim"] = eb_reclaim
    for ev in eb_events:
        ev["time"] = int(t[int(ev["bar"])]) if int(ev["bar"]) < len(t) else None
    eb_n_break = int(sum(1 for v in eb_break if v and v > 0))
    eb_n_reclaim = int(sum(1 for v in eb_reclaim if v and v > 0))
    eb_n_armed_events = int(sum(1 for ev in eb_events if ev.get("kind") == "break" and ev.get("armed")))
    ema_break_section: Dict[str, Any] = {
        "enabled": True,
        "spec": "EBREAK1-break-drop-reclaim",
        "break_length": int(eb_len),
        "drop_pct": float(eb_drop),
        "line_source": eb_source,
        "resolution": ema_meta.get("resolution"),
        "rule": "آلة الدخول الثاني (EBREAK1): عند كسر خط EMA-N (أول إغلاق "
                "تحته بعد إغلاق ≥ الخط) تُثبَّت قمة الشمعة الكاسرة وسعر "
                "كسرها (إغلاقها). ثم يُسلَّط الشرط عند نزول السعر X% من "
                "سعر الكسر (أول low ≤ سعر الكسر ×(1−X%)) — من شمعة الكسر "
                "نفسها فصاعداً. وبعد التسليح، أول شمعة تغلق فوق قمة الشمعة "
                "الكاسرة = إشارة دخول ثاني (واحدة لكل حلقة كسر — حلقة "
                "جديدة عند كسر جديد). كل الأعمدة سببية بت-بت (بلا استشراف "
                "وبلا إعادة رسم). الخروج على كسر الخط نفسه يُفعَّل من "
                "الحمولة بقاعدة close < zzfetqe_ema_N — آلة الأعمدة "
                "للدخول الثاني فقط.",
        "columns": {
            "break": "zzfetqe_ebreak_break",
            "ref_high": "zzfetqe_ebreak_ref_high",
            "ref_close": "zzfetqe_ebreak_ref_close",
            "drop_ok": "zzfetqe_ebreak_drop_ok",
            "reclaim": "zzfetqe_ebreak_reclaim",
        },
        "counts": {
            "breaks": eb_n_break,
            "armed_at_break": eb_n_armed_events,
            "reclaims": eb_n_reclaim,
            "events": len(eb_events),
        },
        "events": eb_events,
    }

    for ev in struct_events:
        ev["time"] = int(t[int(ev["bar"])]) if int(ev["bar"]) < len(t) else None
        ev["pivot_time"] = int(t[int(ev["pivot_bar"])]) \
            if int(ev["pivot_bar"]) < len(t) else None
    struct_section: Dict[str, Any] = {
        "enabled": True,
        "spec": "STRUCT1-macro-hh-hl",
        "reversal_pct": float(struct_r),
        "rule": "بوابة الهيكل الكبير (صرامة حرفية): آخر قمة كبرى مؤكدة أعلى "
                "حرفياً من القمة الكبرى السابقة لها ∧ آخر قاع كبرٍ مؤكد أعلى "
                "حرفياً من القاع الكبر السابق له — عند شمعة الإشارة نفسها. "
                "المحاور الكبرى متبادلة قمة/قاع وكل محور يُؤكَّد سببياً فقط: "
                "القمة عند أول إغلاق ≤ قمته×(1−R%) والقاع عند أول إغلاق ≥ "
                "قاعه×(1+R%) — بلا استشراف وبلا إعادة رسم. القيم None قبل "
                "اكتمال أول زوج مؤكد ⇒ البوابة مقفلة (تحفظياً). الأعمدة: "
                "zzfetqe_struct_last_high/prev_high/last_low/prev_low + "
                "العلم zzfetqe_struct_hh_hl (1.0 فقط عند تحقق الشرطين معاً).",
        "columns": {
            "last_high": "zzfetqe_struct_last_high",
            "prev_high": "zzfetqe_struct_prev_high",
            "last_low": "zzfetqe_struct_last_low",
            "prev_low": "zzfetqe_struct_prev_low",
            "hh_hl_flag": "zzfetqe_struct_hh_hl",
        },
        "counts": {
            "confirmed_tops": sum(1 for e in struct_events
                                   if e.get("kind") == "top"),
            "confirmed_bottoms": sum(1 for e in struct_events
                                     if e.get("kind") == "bottom"),
            "hh_hl_bars": int(sum(st_hh_hl)),
        },
        "events": struct_events,
    }

    # (هـ) ✅ تمرير عقدَي الكمومية كما هما (zzfetq_* + zzfet_* — بت-بت)
    passthrough = {k: v for k, v in base_series.items()
                   if str(k).startswith("zzfetq_") or str(k).startswith("zzfet_")}
    full_series: Dict[str, List[Optional[float]]] = dict(passthrough)
    full_series.update(quantum_ema_series)

    # ------------------------------------------------------------------
    # 6) سجل الإشارات — نفس عقد الكمومية + شفافية الرصة على كل حدث دخول
    # ------------------------------------------------------------------
    signals: List[Dict[str, Any]] = []
    for sig in base.get("signals") or []:
        s = dict(sig)
        s["engine"] = ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME
        bar = int(s.get("bar") or 0)
        ema_state = e_ok[bar] > 0.5 if bar < N else False
        if str(s.get("side")) == "buy":
            s["signal"] = str(s.get("signal") or "").replace(
                "ZLF-E2E-Trendy-Quantum Entry", "ZLF-E2E-Trendy-Quantum-EMA Entry")
            gated = int(s.get("states", [0])[0] if s.get("states") else 0) in ema_cells
            if gated and not ema_state:
                # نهائي الكمومية الذي حجبته رصة EMA — أعِد تصنيفه
                s["side"] = "eblocked"
                s["signal"] = s["signal"].replace(
                    "Entry", "EBlocked (ema gate)")
                s["ema_gate_passed"] = False
            else:
                s["ema_gate_passed"] = True if gated else None
        elif str(s.get("side")) == "zblocked":
            s["signal"] = str(s.get("signal") or "").replace(
                "ZLF-E2E-Trendy-Quantum", "ZLF-E2E-Trendy-Quantum-EMA")
        elif str(s.get("side")) == "blocked":
            s["signal"] = str(s.get("signal") or "").replace(
                "ZLF-E2E-Trendy-Quantum Blocked", "ZLF-E2E-Trendy-Quantum-EMA Blocked")
        s["ema_stack_ok"] = float(e_ok[bar]) if bar < N else 0.0
        signals.append(s)
    signals.extend(ema_signals)
    # ✅ ZONE-EXIT-TF1 — أحداث هيكل الخروج HTF في سجل الإشارات (side="zone_htf")
    # للرسم والشفافية على الشارت — بأزمنة JSON-آمنة (int صريح).
    if zone_exit_section.get("enabled"):
        for ev in zone_exit_section.get("events") or []:
            i0 = int(ev.get("base_bar") or 0)
            is_exit = ev.get("kind") == "exit"
            signals.append({
                "bar": i0,
                "time": int(t[i0]) if i0 < len(t) else None,
                "side": "zone_htf",
                "signal": ("ZLF-E2E-Trendy-Quantum-EMA Zone EXIT (LL+LH) @ HTF "
                           f"{zone_exit_section.get('resolution')}")
                          if is_exit else
                          ("ZLF-E2E-Trendy-Quantum-EMA Zone ENTER (HH+HL) @ HTF "
                           f"{zone_exit_section.get('resolution')}"),
                "engine": ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME,
                "kind": ev.get("kind"),
                "htf_bar": int(ev.get("htf_bar") or 0),
                "htf_close_time": int(ev.get("htf_close_time") or 0),
                "resolution": zone_exit_section.get("resolution"),
            })
    signals.sort(key=lambda s: s.get("bar", 0))

    # ------------------------------------------------------------------
    # 7) الحالة الحية (نطاق + ترند + منطقة + رصة) — عقد الكمومية + قسم ema
    # ------------------------------------------------------------------
    current: Optional[Dict[str, Any]] = None
    if base.get("current") is not None:
        current = dict(base["current"])
        current["ema"] = {
            "stack_ok": float(e_ok[N - 1]) if N else 0.0,
            "stack_ready": float(e_ready[N - 1]) if N else 0.0,
            "stack_price_ok": float(e_price_ok[N - 1]) if N else 0.0,
            "stack_ladder_ok": float(e_ladder_ok[N - 1]) if N else 0.0,
            "stack_mode": stack_meta.get("mode"),
            "stack_base": stack_meta.get("base"),
            "values": {
                f"ema_{int(n)}": (e_lines[idx_n][N - 1] if N and idx_n < len(e_lines) else None)
                for idx_n, n in enumerate(ema_lengths_norm)
            },
            "lengths": [int(x) for x in ema_lengths_norm],
            "ladder_lengths": stack_meta.get("ladder_lengths"),
            "fast_lengths": stack_meta.get("fast_lengths"),
            "resolution": ema_meta.get("resolution"),
            "gate": [f"s{x}" for x in ema_cells],
        }

    params_echo = dict(base.get("params") or {})
    params_echo["ema_lengths"] = [int(x) for x in ema_lengths_norm]
    params_echo["ema_resolution"] = ema_meta.get("resolution")
    params_echo["ema_source"] = src_norm
    params_echo["ema_offset"] = int(ema_offset or 0)
    params_echo["ema_gate"] = [f"s{x}" for x in ema_cells]
    # ✅ EMAGATE-UNIFIED — صدى وضع الرصة الهرمي (الشروط السبعة)
    params_echo["ema_stack_mode"] = stack_meta.get("mode")
    params_echo["ema_stack_base"] = stack_meta.get("base")
    # ✅ ZONE-EXIT-TF1 — صدى فريم هيكل الخروج (None = فريم الشارت)
    params_echo["zone_exit_resolution"] = (
        zone_exit_section.get("resolution") if zone_exit_section.get("enabled") else None)
    try:
        params_echo["zone_exit_length"] = (
            int(zone_exit_section.get("length")) if zone_exit_section.get("enabled") else None)
    except (TypeError, ValueError):
        params_echo["zone_exit_length"] = None
    # ✅ STRUCT1 — صدى نسبة انعكاس الهيكل الكبير الفعلية بعد التطبيع
    params_echo["struct_reversal_pct"] = float(struct_r)
    # ✅ EBREAK1 — صدى آلة الدخول الثاني (خط الكسر ونسبة النزول) بعد التطبيع
    params_echo["ema_break_length"] = int(eb_len)
    params_echo["ema_break_drop_pct"] = float(eb_drop)

    base_zone = dict(base.get("zone") or {})

    return {
        "name": "ZigZag Fib E2E Trendy Quantum EMA (ZLF-End-To-End-Trendy-Quantum-EMA — "
                "Trend-gated + Zone-gated + EMA-stack-gated)",
        "engine": ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME,
        "spec": ZLF_E2E_TRENDY_QUANTUM_EMA_SPEC,
        "core": dict(base.get("core") or {}),
        "volume_available": bool(base.get("volume_available")),
        "params": params_echo,
        "legs": base.get("legs") or [],
        "pivots": base.get("pivots") or [],
        "window": dict(base.get("window") or {}),
        "ranges": base.get("ranges") or [],
        "current": current,
        "signals": signals,
        # ✅ السلاسل تحمل عقد التمايز الثلاثة معاً — zzfetqe_* (الجديدة:
        # النهائي + الممنوع بالرصة + الخطوط الستة + حالة الرصة) +
        # zzfetq_* الكمية + zzfet_* الترندية ممرَّرة حرفياً = كل بيانات
        # الكمومية بحذافيرها + بيانات EMA الجديدة.
        "series": full_series,
        "trend": dict(base.get("trend") or {}),
        "zone": base_zone,
        # ✅ ZONE-ENTRY-MTF1 — قسم فريم المنطقة المسموحة للدخول (من الأساس):
        "zone_entry": base.get("zone_entry") or {"enabled": False},
        # ✅ ZONE-EXIT-TF1 — قسم فريم هيكل الخروج (CHoCH على أي فريم):
        "zone_exit": zone_exit_section,
        # ✅ STRUCT1 — قسم الهيكل الكبير (صرامة القمة>القمة ∧ القاع>القاع):
        "struct": struct_section,
        # ✅ EBREAK1 — قسم آلة الدخول الثاني (كسر EMA-N → نزول X% → استرداد):
        "ema_break": ema_break_section,
        "ema": {
            "enabled": True,
            "engine": ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME,
            "spec": ZLF_E2E_TRENDY_QUANTUM_EMA_SPEC,
            "lengths": [int(x) for x in ema_lengths_norm],
            "resolution": ema_meta.get("resolution"),
            "source": src_norm,
            "offset": int(ema_offset or 0),
            "gate": [f"s{x}" for x in ema_cells],
            # ✅ EMAGATE-UNIFIED — عقد الرصة الهرمي المركزي (الشروط السبعة)
            "stack_mode": stack_meta.get("mode"),
            "stack_base": stack_meta.get("base"),
            "stack_ladder_lengths": stack_meta.get("ladder_lengths"),
            "stack_fast_lengths": stack_meta.get("fast_lengths"),
            "stack_pair_labels": stack_meta.get("pair_labels"),
            "stack_rule_ar": stack_meta.get("rule_ar"),
            "gate_rule": (
                "✅ EMAGATE-UNIFIED (الشروط السبعة — شرح صاحب القرار): "
                + str(stack_meta.get("rule_ar", ""))
                + ". المتوسطات محسوبة على فريم "
                + str(ema_meta.get("resolution"))
                + " (resolution=«60» افتراضياً — بلا نظر مستقبلية) بالتزامن "
                "مع المنطقة الكمومية المفتوحة (HH+HL). ema_gate=none يعطل "
                "بوابة الدخول مع بقاء الخطوط والرصة محسوبة ومُرجعة."),
            "colors": {
                # ✅ SPLIT-TP1 — ألوان الأطوال المعروفة (الثمانية الآن مع 8/13)
                # ولوحة الاحتياط لأي طول مخصص آخر — لا خط بلا لون أبداً.
                "ema_8": _ema_line_color(8),
                "ema_13": _ema_line_color(13),
                "ema_21": _ema_line_color(21),
                "ema_50": _ema_line_color(50),
                "ema_100": _ema_line_color(100),
                "ema_200": _ema_line_color(200),
                "ema_350": _ema_line_color(350),
                "ema_500": _ema_line_color(500),
            },
            # ✅ SPLIT-TP1 — لون كل طول مُكوَّن فعلياً (ديناميكي — لا None
            # أبداً): مصدر الرسم الموحد للفرونت لأي مجموعة أطوال يرسلها،
            # بما فيها الترندات الجديدة 8 و13 وأي طول مخصص مستقبلي.
            "color_by_length": {
                str(int(n)): _ema_line_color(int(n)) for n in ema_lengths_norm},
            "color_source": "ZLF_E2E_TRENDY_QUANTUM_EMA_COLORS + fallback palette",
            "htf_bars": ema_meta.get("htf_bars"),
            "htf_step_ms": ema_meta.get("htf_step_ms"),
            "resolution_clamped_to_chart_tf": ema_meta.get("resolution_clamped_to_chart_tf", False),
            "counts": {
                "stack_enters": int(sum(e_enter)),
                "stack_exits": int(sum(e_exit)),
                "stack_ok_bars": int(sum(e_ok)),
                "stack_price_ok_bars": int(sum(e_price_ok)),
                "stack_ladder_ok_bars": int(sum(e_ladder_ok)),
                "final_entries": int(sum(qe_entry)),
                "ema_blocked": int(sum(qe_eblocked[1])) + int(sum(qe_eblocked[2]))
                                + int(sum(qe_eblocked[3])),
            },
            "events": ema_signals,
        },
        "liquidity": dict(base.get("liquidity") or {}),
        "notes": "ZLF-End-To-End-Trendy-Quantum-EMA — «الاستراتيجية الترندية الكمومية "
                 "المتوسطة المتحركة الأسية»: الكمومية بحذافيرها (محرك واحد — لا "
                 "استنساخ: أعمدتها zzfetq_* وzzfet_* تُمرَّر كما هي بت-بت لرسم "
                 "الزقزاق/الفيبو/خطوط الترند/السيولة/المنطقة) + بوابة رصة "
                 "المتوسطات الستة على فريم الساعة (EMA 21/50/100/200/350/500 "
                 "بترتيب تنازلي تحت السعر) فوق إشارات الدخول مع الشفافية "
                 "(entry_eblocked للمنع بالرصة). كل المخرجات الجديدة بأسماء عقد "
                 "التمايز zzfetqe_*/ind_zzfetqe_*.",
    }


# ---------------------------------------------------------------------------
# ✅ التسجيل الذاتي كمؤشر منفصل — zigzag_fib_e2e_trendy_quantum_ema
#    يُستورد مرة واحدة من app/services/indicators/__init__.py
# ---------------------------------------------------------------------------
def _register_quantum_ema_indicator() -> None:
    try:
        from .base import BaseIndicator, IndicatorResult, IndicatorType
        from .registry import IndicatorRegistry
        import pandas as pd

        class ZigZagFibE2ETrendyQuantumEmaIndicator(BaseIndicator):
            """ZLF-End-To-End-Trendy-Quantum-EMA — الكمومية + بوابة رصة EMA."""

            @classmethod
            def get_required_columns(cls):
                return ["open", "high", "low", "close"]

            @classmethod
            def get_default_params(cls):
                # ✅ EMAGATE-UNIFIED — لوحة إعدادات الواجهة (endpoint /params):
                # كل مفاتيح بوابة الرصة الهرمية ظاهرة هنا صريحة.
                return {
                    "length": 100, "mode": "luxalgo",
                    "trend_periods": [7, 15, 25], "trend_confirm": "majority",
                    "trend_gate": ["s1", "s2", "s3"],
                    "zone_gate": ["s1", "s2", "s3"],
                    "ema_lengths": [21, 50, 100, 200, 350, 500],
                    "ema_resolution": "60", "ema_source": "close",
                    "ema_offset": 0, "ema_gate": ["s1", "s2", "s3"],
                    "ema_stack_mode": "hierarchical", "ema_stack_base": 21,
                    # ✅ ZONE-ENTRY-MTF1 — فريم المنطقة المسموحة (None = الشارت)
                    "zone_resolution": None, "zone_length": None,
                    # ✅ STRUCT1 — نسبة انعكاس الهيكل الكبير (افتراضي معايرة)
                    "struct_reversal_pct": 22,
                }

            def calculate(self, data: pd.DataFrame) -> IndicatorResult:
                from .overlay_columns import config_to_overlay_params
                conv = config_to_overlay_params({
                    "name": "zigzag_fib_e2e_trendy_quantum_ema",
                    "params": dict(self.params or {}),
                }) or {"zzfib_e2e_trendy_quantum_ema": {}}
                params = conv.get("zzfib_e2e_trendy_quantum_ema") or {}
                res = zigzag_fib_e2e_trendy_quantum_ema(data, **params)
                values = res["series"].get("zzfetqe_entry") or [None] * len(data)
                series = pd.Series(values, index=data.index, dtype=object)
                return IndicatorResult(
                    name=self.name,
                    values=series,
                    signals=None,
                    metadata={
                        "engine": ZLF_E2E_TRENDY_QUANTUM_EMA_ENGINE_NAME,
                        "overlay": "zzfib_e2e_trendy_quantum_ema",
                        "primary_column": "ind_zzfetqe_entry",
                        "available_columns": sorted(res["series"].keys()),
                    },
                )

        IndicatorRegistry.register(
            "zigzag_fib_e2e_trendy_quantum_ema",
            display_name="ZLF-End-To-End-Trendy-Quantum-EMA — الاستراتيجية الترندية الكمومية المتوسطة المتحركة الأسية",
            description="الكمومية بحذافيرها (S1/S2/S3 + بوابة الترند 7/15/25 + بوابة "
                        "المنطقة الكمومية HH+HL/LL+LH) + بوابة رصة المتوسطات الستة "
                        "على فريم الساعة (EMA 21/50/100/200/350/500 بترتيب تنازلي "
                        "تحت السعر — MTF EMA بلا استشراف). تُرجع كل أعمدة الكمومية "
                        "zzfetq_* والترندية zzfet_* ممرَّرة بت-بت (بيانات الرسم "
                        "الكاملة) + الخطوط الستة zzfetqe_ema_* وحالة الرصة "
                        "zzfetqe_ema_stack_* والشفافية (entry_eblocked). العمود "
                        "الأساسي: ind_zzfetqe_entry · الخام يبقى ind_zzfetq_entry_raw "
                        "· حجب الترند ind_zzfetq_entry_blocked_* · حجب المنطقة "
                        "ind_zzfetq_entry_zblocked_* · حجب الرصة "
                        "ind_zzfetqe_entry_eblocked_*.",
            category=IndicatorType.SUPPORT_RESISTANCE,
        )(ZigZagFibE2ETrendyQuantumEmaIndicator)

        # مرادف قصير — نفس الفئة (نمط العائلة)
        info = IndicatorRegistry._indicators.get("zigzag_fib_e2e_trendy_quantum_ema")
        if info is not None:
            IndicatorRegistry._indicators.setdefault("zzfib_e2e_trendy_quantum_ema", info)
    except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
        logging.getLogger(__name__).exception(
            "ZLF-E2E-Trendy-Quantum-EMA indicator registration failed")


_register_quantum_ema_indicator()
