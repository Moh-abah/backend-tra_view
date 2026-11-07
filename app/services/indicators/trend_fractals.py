# =============================================================================
# ✅ ROUND32 — محرك الترند المعزول — Fractal Auto Trendlines
# =============================================================================
# المحرك المستقل الجديد (استنساخ معزول — لا يعتمد على أي محرك قائم ولا يعدّل
# عليه) ينفّذ منطق سكربت Pine المعتمد «Auto Trendline [DojiEmoji]» حرفياً:
#
#   1) الفراكتال = ta.pivothigh(n, n)[1] / ta.pivotlow(n, n)[1]:
#      الشمعة p فراكتال قمة ⇔ high[p] أكبر صرامةً من n شموع قبلها و n شموع
#      بعدها (كل الجوار سارٍ — أي قيمة ناقصة تلغي التأكيد مثل Pine)،
#      والشمعة p فراكتال قاع ⇔ low[p] أصغر صرامةً من n شموع قبلها و n شموع
#      بعدها (التوأم التام — نوافذ MIN).
#      ⚠️ ROUND33: كانت الجولة 32 تطبق نوافذ MAX على القيعان أيضاً فيصل
#      «الخط السفلي» أعلى القيعان لا قيعانها الحقيقية — صُحّح إلى MIN
#      بتماثل تام مع منطق القمم (تثبيت: مرجع مستقل O(n²) — العلوي بلم
#      تغيير، والسفلي يطابق ta.pivotlow حرفياً).
#      لاحظ إزاحة [1] في السكربت: الفراكتال p «يظهر» (يُعرف) عند الشمعة
#      i = p + n + 1 — والسكربت يمسك سعره بـ high[n+1]/low[n+1] وباره بـ
#      bar_index-n-1. ننفّذ نفس لحظة الظهور هذه حرفياً (بلا إعادة رسم).
#   2) الخط العلوي يصل آخر فراكتالَي قمة (الأقدم → الأحدث) والسفلي يصل آخر
#      فراكتالَي قاع — لحظة ظهور فراكتال جديد يُعاد الوصل (خط جديد يولد
#      عند شمعة الظهور ويبقى حتى الظهور التالي) — نفس سلوك
#      recent_up1/recent_up2 و recent_dn1/recent_dn2 في السكربت.
#   3) قيمة الخط عند أي شمعة = تمديد الخط الأيمن (extend.right):
#      y(i) = y1 + m × (i − x1) حيث m = ميل الخط بين الفراكتالَين —
#      نفس معادلة get_slope/y_up/y_dn في السكربت.
#   4) التقاطعات بوفاء ta.cross: تقاطع علوي = انقلاب إشارة (close − y_up)
#      بين الشمعة الحالية والسابقة (تساوي الحدّ = لا تقاطع — cross_over
#      يتطلب > على الحالية و ≤ على السابقة) — والأحداث الموجَّعة الأربعة
#      (اختراق علوي صاعد/هابط · استعادة سفلية صاعدة/كسر سفلي هابط) مشتقة
#      من نفس التعريف.
#
# ⚠️ عقد ROUND32 (من صاحب القرار):
#   - «الترند يرسل إحداثياته للباك اند والباك اند يحسب الإشارة بناء عليه»:
#     هذا المحرك يُنتج الإحداثيات الكاملة (x/t/y للطرفين + الميل + لحظة
#     الولادة + امتداد الحي) في قسم lines — وحساب الإشارات يتم في محرك
#     الاستراتيجية (overlays_zlf_e2e_trendy.py) من هذه السلاسل.
#   - «الأرقام لا تُكتب داخل الكود»: الفترات قالبية بالكامل — معامل واحد
#     periods (قائمة بأي طول: 7/15/25 افتراضياً، وإضافة رابعة 30 = تعديل
#     القالب فقط بلا أي كود). لا يوجد أي تفريع if period == 7 في المنطق —
#     الحلقة عامة على القائمة.
#   - أسماء السلاسل: trf_p{period}_* → أعمدة ind_trf_p{period}_*، والمجاميع
#     trf_bias / trf_trend_ok → ind_trf_bias / ind_trf_trend_ok.
# =============================================================================

from __future__ import annotations

from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "auto_trendlines_fractal",
    "TRF_ENGINE_NAME",
    "TRF_SPEC",
    "TRF_DEFAULT_PERIODS",
]

# ---------------------------------------------------------------------------
# هوية المحرك المعزول
# ---------------------------------------------------------------------------
TRF_ENGINE_NAME = "Fractal-Auto-Trendlines"
TRF_SPEC = "ROUND33-dojiemoji-fidelity"  # ROUND33: تصحيح فراكتال القيعان (MIN بدل MAX)

# القالب الافتراضي فقط (وقوع احتياطي عند الاستدعاء بلا معاملات) — القالب
# المعتمد فعلياً يعيش في بريسِت الاستراتيجية ويمكن تغييره/توسيعه (حتى إضافة
# ترند رابع 30) بتعديل القالب وحده — لا أرقام فترات داخل أي منطق.
TRF_DEFAULT_PERIODS: Tuple[int, ...] = (7, 15, 25)
# ---------------------------------------------------------------------------
# ✅ ROUND34 — التطبيع من المحرك الموحد (إصلاح ISO: أزمنة الرسم صحيحة في
#    كل المسارات — كانت النسخة المستنسخة تفشل مع timestamp كسلسلة ISO
#    فترجع 0 لأزمنة خطوط الترند في شارت الباك تست).
# ---------------------------------------------------------------------------
from app.services.indicators.zigzag_fib_core import (
    ZIGZAG_FIB_CORE_SPEC,
    clean_float as _clean,
    norm_candles as _norm_candles,
)


def _parse_periods(raw: Any) -> List[int]:
    """تطبيع قائمة الفترات — تقبل قائمة/صفّ/نصاً مفصولاً بفواصل («7,15,25»).

    ⚠️ القالبية: لا افتراض لعدد الفترات ولا لقيمها — أي طول يُقبل (إضافة ترند
    رابع 30 = تمرير [7,15,25,30] بلا أي كود). أدنى فترة 2 (مثل minval=2 في
    السكربت) — القيم المكررة تُبطل بعد التفرد مع حفظ الترتيب.
    """
    if raw is None:
        return list(TRF_DEFAULT_PERIODS)
    if isinstance(raw, str):
        raw = [x for x in raw.replace(";", ",").split(",") if str(x).strip()]
    out: List[int] = []
    for x in raw:
        try:
            v = int(float(x))
        except (TypeError, ValueError):
            continue
        if v >= 2:
            out.append(v)
    # تفرد مع حفظ الترتيب
    seen = set()
    uniq = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq or list(TRF_DEFAULT_PERIODS)


def _resolve_threshold(confirm_mode: Any, n_periods: int) -> Tuple[Any, int]:
    """حل عتبة الإجماع من صيغة confirm_mode القالبية.

    majority → أكثر من النصف (floor(P/2)+1 — مع 3 فترات = 2 من 3)
    all      → الإجماع الكامل (P)
    any      → فترة واحدة تكفي (1)
    رقم      → عتبة صريحة تُقصّ إلى [1, P]
    """
    mode_raw = confirm_mode
    mode_name = "majority"
    if isinstance(mode_raw, str):
        s = str(mode_raw).strip().lower()
        if s in ("majority", "most", "اغلبية", "أغلبية"):
            mode_name = "majority"
        elif s in ("all", "كل", "الكل"):
            mode_name = "all"
        elif s in ("any", "one", "أي", "اي"):
            mode_name = "any"
        else:
            try:
                mode_name = int(float(s))
            except (TypeError, ValueError):
                mode_name = "majority"
    elif isinstance(mode_raw, (int, float)) and not isinstance(mode_raw, bool):
        try:
            mode_name = int(float(mode_raw))
        except (TypeError, ValueError):
            mode_name = "majority"
    if mode_name == "majority":
        thr = n_periods // 2 + 1
    elif mode_name == "all":
        thr = n_periods
    elif mode_name == "any":
        thr = 1
    else:
        try:
            thr = int(mode_name)
        except (TypeError, ValueError):
            thr = n_periods // 2 + 1
        thr = max(1, min(int(thr), n_periods))
    return mode_name, thr


def _rolling_window_max(arr: List[Optional[float]], w: int, none_prefix: List[int]) -> List[Optional[float]]:
    """أقصى نافذة صارمة بحجم w تنتهي عند i (شاملة i) — deque O(n).

    تعيد None إذا كانت النافذة غير مكتملة أو تحتوي أي قيمة ناقصة
    (وفاء Pine: ta.pivothigh مع na في النافذة → na = لا فراكتال).
    """
    n = len(arr)
    out: List[Optional[float]] = [None] * n
    dq: deque = deque()  # فهارس قيم سارية monotonic تنازلية
    for i in range(n):
        v = arr[i]
        if v is not None:
            while dq and arr[dq[-1]] is not None and arr[dq[-1]] <= v:
                dq.pop()
            dq.append(i)
        # إسقاط ما خرج من النافذة [i-w+1 .. i]
        while dq and dq[0] < i - w + 1:
            dq.popleft()
        if i >= w - 1:
            lo = i - w + 1
            # أي None داخل النافذة → لا أقصى صارم
            if none_prefix[lo] == none_prefix[i + 1] and dq:
                out[i] = arr[dq[0]]
    return out


def _rolling_window_min(arr: List[Optional[float]], w: int, none_prefix: List[int]) -> List[Optional[float]]:
    """أدنى نافذة صارمة بحجم w تنتهي عند i (شاملة i) — التوأم التام لـ _rolling_window_max.

    تنفيذ deque O(n) بمتغيرات monotonic تصاعدية — نفس تعاقد None:
    تعيد None إذا كانت النافذة غير مكتملة أو تحتوي أي قيمة ناقصة
    (وفاء Pine: ta.pivotlow مع na في النافذة → na = لا فراكتال).
    """
    n = len(arr)
    out: List[Optional[float]] = [None] * n
    dq: deque = deque()  # فهارس قيم سارية monotonic تصاعدية
    for i in range(n):
        v = arr[i]
        if v is not None:
            while dq and arr[dq[-1]] is not None and arr[dq[-1]] >= v:
                dq.pop()
            dq.append(i)
        # إسقاط ما خرج من النافذة [i-w+1 .. i]
        while dq and dq[0] < i - w + 1:
            dq.popleft()
        if i >= w - 1:
            lo = i - w + 1
            # أي None داخل النافذة → لا أدنى صارم
            if none_prefix[lo] == none_prefix[i + 1] and dq:
                out[i] = arr[dq[0]]
    return out


def _pivot_events(
    arr: List[Optional[float]], n: int, kind: str,
) -> List[Tuple[int, int, float]]:
    """فراكتالات مصفوفة بنافذة n يميناً ويساراً — يعيد [(confirm_bar, pivot_bar, price)].

    الفراكتال p يظهر (يُعرف) عند الشمعة p + n + 1 — وفاء إزاحة [1] في
    ta.pivothigh(n, n)[1] / ta.pivotlow(n, n)[1] (السكربت يمسك الفراكتال بـ
    high[n+1]/low[n+1] وباره بـ bar_index-n-1).
    الترتيب: حسب شمعة الظهور (ثم شمعة الفراكتال).

    ⚠️ ROUND33 — إصلاح القيعان (كانت معكوسة في الجولة 32):
      kind="upper" على المصفوفة h: قمم — v أكبر صرامةً من الجارين (نوافذ MAX).
      kind="lower" على المصفوفة l: قيعان — v أصغر صرامةً من الجارين (نوافذ MIN
      — التوأم التام لمنطق القمم) — وفاء ta.pivotlow: القاع يجب أن يكون أدنى
      من كل جيرانه، لا أعلاهم (كانت الجولة 32 تستخدم MAX على القيعان فيصل
      «الخط السفلي» أعلى القيعان لا قيعانها الحقيقية).
    """
    N = len(arr)
    if N < 2 * n + 1:
        return []
    # none_prefix[i] = عدد القيم الناقصة في arr[0..i-1]
    none_prefix = [0] * (N + 1)
    for i, v in enumerate(arr):
        none_prefix[i + 1] = none_prefix[i] + (0 if v is not None else 1)
    is_low = (kind == "lower")
    window = _rolling_window_min if is_low else _rolling_window_max
    # نافذة اليسرى [p-n .. p-1] واليمنى [p+1 .. p+n] — بأقصى القمم/أدنى القيعان
    left = window(arr, n, none_prefix)                       # تنتهي عند i شاملة
    # النافذة اليمنى = نافذة معاكسة تنتهي عند p+n → نحسبها على المصفوفة المعكوسة
    rev = list(reversed(arr))
    none_prefix_rev = [0] * (N + 1)
    for i, v in enumerate(rev):
        none_prefix_rev[i + 1] = none_prefix_rev[i] + (0 if v is not None else 1)
    rev_ext = window(rev, n, none_prefix_rev)   # rev_ext[j] = أقصى/أدنى rev[j-n+1..j]
    # نافذة اليمنى للفراكتال p = [p+1 .. p+n] وفي المصفوفة المعكوسة تنتهي
    # عند rev index N-1-(p+1) (نافذة حجم n تنتهي شاملة) ⇒ rev_ext[N-1-(p+1)]
    events: List[Tuple[int, int, float]] = []
    for p in range(n, N - n):
        v = arr[p]
        if v is None:
            continue
        lm = left[p - 1] if p - 1 >= 0 else None             # أقصى/أدنى [p-n .. p-1]
        jr = N - 1 - (p + 1)
        rm = rev_ext[jr] if 0 <= jr < N else None            # أقصى/أدنى [p+1 .. p+n]
        if lm is None or rm is None:
            continue
        # أي قيمة ناقصة داخل إحدى النافذتين → القيم أعلاه None أصلاً
        if is_low:
            hit = (v < lm) and (v < rm)                      # قاع: أدنى صرامةً من الجيرين
        else:
            hit = (v > lm) and (v > rm)                      # قمة: أكبر صرامةً من الجيرين
        if hit:
            cf = p + n + 1                                    # لحظة الظهور (وفاء [1])
            # نحتفظ بالفراكتال حتى لو تجاوز ظهوره آخر شمعة متاحة —
            # لن يدخل السلاسل قبل شمعة ظهوره (الفحص في _fill_line_series)
            events.append((cf, p, v))
    events.sort(key=lambda x: (x[0], x[1]))
    return events


def _fill_line_series(
    events: List[Tuple[int, int, float]], N: int, t: List[int], kind: str,
) -> Tuple[List[Optional[float]], List[float], List[Dict[str, Any]]]:
    """سلسلة قيم الخط (تمديد أيمن) + سلسلة أحداث الولادة + سجل الإحداثيات.

    عند شمعة ظهور فراكتال جديد يُعاد الوصل من الفراكتال السابق إليه — الخط
    الجديد يولد عند شمعة الظهور ويحكم القيم حتى ظهور التالي (نفس
    draw_trendline/init_fractal في السكربت: الخط يُرسم لحظة الظهور بإحداثيات
    الفراكتالَين).
    """
    y: List[Optional[float]] = [None] * N
    born: List[float] = [0.0] * N
    lines: List[Dict[str, Any]] = []
    # آخر فراكتالين مؤكدين (ظهورهما بلغ شمعة متاحة)
    prev: Optional[Tuple[int, float]] = None     # (bar, price) الأقدم
    last: Optional[Tuple[int, float]] = None     # الأحدث
    ev_idx = 0
    for i in range(N):
        # تطبيق أحداث الظهور التي بلغت شمعتها
        while ev_idx < len(events) and events[ev_idx][0] <= i:
            _cf, pb, px = events[ev_idx]
            ev_idx += 1
            if last is None:
                last = (pb, px)          # أول فراكتال — لا خط بعد (يحتاج طرفين)
                prev = None
                continue
            prev = last
            last = (pb, px)
            x2, y2 = prev
            x1, y1 = last
            if x1 == x2:
                m = 0.0
            else:
                m = (y1 - y2) / float(x1 - x2)
            line = {
                "kind": kind,
                "x1": int(x1), "t1": t[x1] if 0 <= x1 < N else None, "y1": _clean(y1),
                "x2": int(x2), "t2": t[x2] if 0 <= x2 < N else None, "y2": _clean(y2),
                "slope": _clean(m),
                "formed_at_bar": int(i),
                "formed_at_time": t[i] if 0 <= i < N else None,
                "active": True,
                "replaced_at_bar": None,
            }
            if lines:
                lines[-1]["active"] = False
                lines[-1]["replaced_at_bar"] = int(i)
            lines.append(line)
            born[i] = 1.0
        # قيمة الخط الحي عند هذه الشمعة (تمديد أيمن من الطرف الأحدث)
        if last is not None and prev is not None:
            x1, y1 = last
            x2, y2 = prev
            m = 0.0 if x1 == x2 else (y1 - y2) / float(x1 - x2)
            y[i] = _clean(y1 + m * float(i - x1))
    return y, born, lines


def auto_trendlines_fractal(
    candles: Any,
    periods: Any = None,
    confirm_mode: Any = "majority",
) -> Dict[str, Any]:
    """محرك الترند المعزول — خطوط أوتوماتيكية بوصل آخر فراكتالَين (وفاء Pine).

    المعاملات (كلها قالبية — لا أرقام داخل الكود):
      periods:      قائمة فترات الفراكتال (7/15/25 افتراضياً — وأي طول: أضف 30
                    من القالب وحده) — تقبل قائمة أو نصاً «7,15,25».
      confirm_mode: majority (أكثر من النصف — 2 من 3) | all | any | رقم صريح.

    المخرجات:
      series: trf_p{p}_upper/lower (قيم الخطوط الممتدة) · trf_p{p}_bias ·
              trf_p{p}_cross_upper/lower (تقاطع بأي اتجاه — ta.cross) ·
              trf_p{p}_cross_upper_up/dn و trf_p{p}_cross_lower_up/dn
              (الأحداث الموجَّعة) · trf_p{p}_new_upper/lower (ولادة خط) ·
              trf_bull_votes / trf_bear_votes / trf_bias / trf_trend_ok /
              trf_threshold
      lines:  إحداثيات كل خط ولِد (x/t/y للطرفين + الميل + لحظة الولادة +
              لحظة الإحلال + الحي منه) لكل فترة — «الترند يرسل إحداثياته
              للباك اند» حرفياً.
      current: الخطان الحيان لكل فترة + قيمتهما الممتدة عند آخر شمعة.
    """
    t, o, h, l, c = _norm_candles(candles)
    N = len(c)
    per = _parse_periods(periods)
    mode_name, threshold = _resolve_threshold(confirm_mode, len(per))

    series: Dict[str, List[Optional[float]]] = {}
    lines_by_period: Dict[str, Any] = {}
    current_by_period: Dict[str, Any] = {}
    events_count: Dict[str, Dict[str, Any]] = {}

    bias_rows: List[List[float]] = []   # لكل فترة سلسلة bias (+1/0/-1)

    for p in per:
        tag = f"p{p}"
        ups = _pivot_events(h, p, "upper")
        dns = _pivot_events(l, p, "lower")
        y_up, born_up, lines_up = _fill_line_series(ups, N, t, "upper")
        y_dn, born_dn, lines_dn = _fill_line_series(dns, N, t, "lower")

        s_upper: List[Optional[float]] = [None] * N
        s_lower: List[Optional[float]] = [None] * N
        s_bias: List[float] = [0.0] * N
        s_cu: List[float] = [0.0] * N          # تقاطع علوي بأي اتجاه (ta.cross)
        s_cl: List[float] = [0.0] * N          # تقاطع سفلي بأي اتجاه
        s_cu_up: List[float] = [0.0] * N       # اختراق علوي صاعد
        s_cu_dn: List[float] = [0.0] * N       # عودة تحت العلوي
        s_cl_up: List[float] = [0.0] * N       # استعادة فوق السفلي
        s_cl_dn: List[float] = [0.0] * N       # كسر السفلي هابطاً
        s_new_up: List[float] = born_up
        s_new_dn: List[float] = born_dn

        for i in range(N):
            yu, yd = y_up[i], y_dn[i]
            s_upper[i] = yu
            s_lower[i] = yd
            ci = c[i]
            cp = c[i - 1] if i >= 1 else None
            yup = y_up[i - 1] if i >= 1 else None
            ydp = y_dn[i - 1] if i >= 1 else None
            # الانحياز (state): فوق الخط العلوي = صاعد · تحت السفلي = هابط
            if ci is not None and yu is not None and ci > yu:
                s_bias[i] = 1.0
            elif ci is not None and yd is not None and ci < yd:
                s_bias[i] = -1.0
            # التقاطعات — وفاء ta.cross/ta.crossover/ta.crossunder:
            # cross_over  = a > b  ∧ a[1] ≤ b[1]   (تساوي الحدّ لا يقطع)
            # cross_under = a < b  ∧ a[1] ≥ b[1]
            if ci is not None and yu is not None and cp is not None and yup is not None:
                if ci > yu and cp <= yup:
                    s_cu[i] = 1.0
                    s_cu_up[i] = 1.0
                elif ci < yu and cp >= yup:
                    s_cu[i] = 1.0
                    s_cu_dn[i] = 1.0
            if ci is not None and yd is not None and cp is not None and ydp is not None:
                if ci > yd and cp <= ydp:
                    s_cl[i] = 1.0
                    s_cl_up[i] = 1.0
                elif ci < yd and cp >= ydp:
                    s_cl[i] = 1.0
                    s_cl_dn[i] = 1.0

        series[f"trf_{tag}_upper"] = s_upper
        series[f"trf_{tag}_lower"] = s_lower
        series[f"trf_{tag}_bias"] = s_bias
        series[f"trf_{tag}_cross_upper"] = s_cu
        series[f"trf_{tag}_cross_lower"] = s_cl
        series[f"trf_{tag}_cross_upper_up"] = s_cu_up
        series[f"trf_{tag}_cross_upper_dn"] = s_cu_dn
        series[f"trf_{tag}_cross_lower_up"] = s_cl_up
        series[f"trf_{tag}_cross_lower_dn"] = s_cl_dn
        series[f"trf_{tag}_new_upper"] = s_new_up
        series[f"trf_{tag}_new_lower"] = s_new_dn
        bias_rows.append(s_bias)

        lines_by_period[tag] = {"period": int(p), "upper": lines_up, "lower": lines_dn}
        last_bar = N - 1
        cur_up = lines_up[-1] if lines_up else None
        cur_dn = lines_dn[-1] if lines_dn else None
        current_by_period[tag] = {
            "period": int(p),
            "upper": (dict(cur_up, value_now=s_upper[last_bar]) if cur_up else None),
            "lower": (dict(cur_dn, value_now=s_lower[last_bar]) if cur_dn else None),
        }
        events_count[tag] = {
            "pivot_highs": len(ups), "pivot_lows": len(dns),
            "upper_lines": len(lines_up), "lower_lines": len(lines_dn),
            "cross_upper": int(sum(s_cu)), "cross_lower": int(sum(s_cl)),
        }

    # --- المجاميع القالبية عبر الفترات (بوابة الترند) ---
    P = len(per)
    s_bull: List[float] = [0.0] * N
    s_bear: List[float] = [0.0] * N
    s_bias: List[float] = [0.0] * N
    s_ok: List[float] = [0.0] * N
    s_thr: List[float] = [float(threshold)] * N
    for i in range(N):
        bull = 0
        bear = 0
        for row in bias_rows:
            if row[i] > 0:
                bull += 1
            elif row[i] < 0:
                bear += 1
        s_bull[i] = float(bull)
        s_bear[i] = float(bear)
        if bull >= threshold and bull > bear:
            s_bias[i] = 1.0
            s_ok[i] = 1.0
        elif bear >= threshold and bear > bull:
            s_bias[i] = -1.0

    series["trf_bull_votes"] = s_bull
    series["trf_bear_votes"] = s_bear
    series["trf_bias"] = s_bias
    series["trf_trend_ok"] = s_ok
    series["trf_threshold"] = s_thr

    return {
        "name": "Fractal Auto Trendlines (DojiEmoji-faithful)",
        "engine": TRF_ENGINE_NAME,
        "spec": TRF_SPEC,
        "params": {
            "periods": [int(x) for x in per],
            "confirm_mode": mode_name,
            "threshold": int(threshold),
            "template_editable": True,
        },
        "series": series,
        "lines": lines_by_period,
        "current": current_by_period,
        "events": events_count,
        "notes": "محرك الترند المعزول ROUND32 — فراكتالات ta.pivothigh/pivotlow(n,n)[1] بوفاء "
                 "السكربت المعتمد (الظهور عند p+n+1 بلا إعادة رسم) · وصل آخر فراكتالَين لكل "
                 "اتجاه بتمديد أيمن · تقاطعات ta.cross بالدلالة الحرفية (تساوي الحدّ لا يقطع) · "
                 "الفترات قالبية بالكامل (أضف ترنداً رابعاً 30 من القالب بلا أي كود) · "
                 "الإشارات تُحسب في محرك الاستراتيجية من إحداثيات هذا المحرك. "
                 "ROUND33: تصحيح فراكتال القيعان — الخط السفلي يصل آخر فراكتالَي قاع حقيقيين "
                 "(أدنى الجوار صرامةً) بتماثل تام مع منطق القمم.",
    }
