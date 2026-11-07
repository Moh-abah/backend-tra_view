# =============================================================================
# ✅ ROUND34 — المحرك الموحد للزقزاق والفيبوناتشي (ONE ENGINE FOR ALL)
# =============================================================================
# ⚠️ عقد هذه الجولة (توجيه صاحب القرار 2026-11-05):
#   «سويه محرك الزقزاق واحد لكل الاستراتيجيات ومحرك الفيبوناتشي واحد أيضاً
#    للثلاث الاستراتيجيات البطل والبطل e2e والبطل e2e الترنديه» —
#   كان النظام يحمل 4 نسخ من آلة luxalgo و3 نسخ من آلة TradingView و3 نسخ
#   من مصفوفة الفيبو/النطاقات (استنساخ حرفي في overlays.py و
#   overlays_zlf_e2e.py وoverlays_zlf_e2e_trendy.py) — ~1,300 سطر منطق
#   مكرر، وأخطر من ذلك: إصلاح ROUND30 (تحليل نص ISO في _ts) وُضع في نسخة
#   واحدة فقط (overlays.py) فبقيت النسخ المستنسخة تُرجع time=0 لكل
#   إحداثيات الرسم في شارت الباك تست — وهذا كان جذر «الرسومات العشوائية».
#
# هذا الملف هو الآن المصدر الوحيد (Single Source of Truth) لـ:
#   1) تطبيع المدخلات: norm_candles/norm_volume/to_ms — تحليل كامل:
#      ms · ثوانٍ · datetime · pandas Timestamp · نص ISO مع/بدون Z
#      (بلا منطقة زمنية → UTC كتخزين المنصة) — موحّد للجميع.
#   2) كشف الزقزاق: وضعان معتمدان بنفس السلوك التاريخي حرفياً:
#      · "luxalgo"      — آلة الإغلاقات المنزلقة (length) — تأكيد بعد length
#                         شمعة؛ «لحظة الظهور» = confirmed_at_bar (مواصفة E2E
#                         المصادقة بالبكسل: قمة 15:14 → قاع 15:28 → ظهور 17:08).
#      · "tradingview"  — Depth/Deviation/Backstep على high/low — الأطراف على
#                         القصوى الحقيقية (إحلال الأقوى — سببية صارمة).
#      المخرجات موحدة لأي وضع: pivots + legs + pair_events (لحظة ظهور كل
#      زوج = ميلاد النطاق) + سلاسل سببية لكل شمعة.
#   3) الفيبوناتشي الموحد: price(level) = p1 + diff × level حيث
#      diff = sign(p1→p2) × |p1−p2| — المعادلة المصادقة بالبكسل (خط 0.618
#      بمقياس المستخدم = price(0.382) بالمحرك).
#   4) دورة حياة النطاق: الولادة = لحظة ظهور الزقزاق (anchor)، الموت =
#      ولادة النطاق التالي (death) — وكل نطاق يحمل مستويات فيبو الخاصة به
#      بحدود رسم كاملة: تبدأ من خط الولادة (بدايته منذ لحظة ولادته) وتنتهي
#      عند نهاية عمره (death−1) أو آخر شمعة للنطاق الحي — «يجب أن يكون
#      للفيبوناتشي نهاية كي لا يشوّه الشارت».
#
# المستهلكون (كلهم فوق هذا المحرك — لا منطق زقزاق/فيبو مكرر بعده):
#   · overlays.py                    → zigzag_channels · zigzag_fib (البطل ZLF)
#   · overlays_zlf_e2e.py            → zigzag_fib_e2e (البطل e2e — النطاق)
#   · overlays_zlf_e2e_trendy.py     → zigzag_fib_e2e_trendy (الترندية — نطاق+ترند)
#   · trend_fractals.py              → تطبيع الشموع/الوقت (فراكتالات الترند)
#   · routers/backtest.py            → overlays شارت الباك تست (volume يمر الآن)
#   · routers/overlays.py            → الشارت الحي
#
# السببية (عقد عدم إعادة الرسم — محفوظ حرفياً):
#   - كل نقطة تحمل confirmed_at_bar = الشمعة التي عُرفت عندها (لا استشراف).
#   - قيم الشمعة n في السلاسل مبنية من معلومات ≤ n فقط؛ الإحلال يقع على
#     شموع لاحقة فقط. أي حساب ينتهي عند T يعطي نفس نتيجة نافذة أطول.
# =============================================================================

from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    # هوية المحرك الموحد
    "ZIGZAG_FIB_CORE_SPEC",
    "ZIGZAG_FIB_CORE_VERSION",
    # تطبيع المدخلات (المصدر الوحيد)
    "clean_float",
    "to_ms",
    "norm_candles",
    "norm_volume",
    "rolling_extreme",
    "level_tag",
    "infer_price_tick",
    # كشف الزقزاق الموحد
    "zigzag_detect",
    "causal_leg_series",
    "luxalgo_state_machine",
    # الفيبوناتشي الموحد + النطاقات
    "fib_leg_math",
    "build_ranges",
    "range_levels_geometry",
    "range_public",
]

# ---------------------------------------------------------------------------
# هوية المحرك الموحد — تظهر في كل المخرجات والتقارير (شفافية الإصدار)
# ---------------------------------------------------------------------------
ZIGZAG_FIB_CORE_SPEC = "ROUND34-unified-zigzag-fib"
ZIGZAG_FIB_CORE_VERSION = "34.0.0"


# ===========================================================================
# (1) تطبيع المدخلات — نسخة واحدة للجميع (تشمل إصلاح ROUND30 كاملاً)
# ===========================================================================
def clean_float(v: Optional[float]) -> Optional[float]:
    """None أو رقم JSON-آمن (يستبدل NaN/±Inf بـ None)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def to_ms(v: Any) -> int:
    """تحليل زمني موحد → ملي ثانية (int). يعيد 0 عند الفشل.

    يقبل: ms (int/float ≥ 1e11) · ثوانٍ (< 1e11 → ×1000) · datetime ·
    pandas Timestamp · نص رقمي ("1700000000") · نص ISO مع/بدون Z
    (بلا منطقة زمنية → UTC — تخزين المنصة الموحد).

    ✅ ROUND30 (الجذر المُصلَح): كان float("2026-10-21T16:30:00Z") يرمي
    ValueError فتعود 0 — ولهذا كانت كل أزمنة overlays في شارت الباك تست
    صفرية (مسار chart-data يمرر timestamp كسلسلة ISO). الإصلاح كان موجوداً
    في overlays.py فقط؛ هذه النسخة الموحدة تجعله واحداً للجميع إلى الأبد.
    """
    try:
        if hasattr(v, "timestamp") and not isinstance(v, (int, float)):
            return int(v.timestamp() * 1000)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return 0
            try:
                f = float(s)              # رقم كسلسلة "1700000000"
            except ValueError:
                f = None
            if f is not None:
                if f < 1e11:              # ثوانٍ → ms
                    f *= 1000.0
                return int(f)
            s2 = s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s
            try:
                dt = datetime.fromisoformat(s2)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except ValueError:
                return 0
        f = float(v)
        if f < 1e11:          # ثوانٍ → ms
            f *= 1000.0
        return int(f)
    except Exception:
        return 0


def norm_candles(candles: Any) -> Tuple[List[int], List[float], List[float], List[float], List[float]]:
    """يحوّل الشموع إلى (times_ms, open, high, low, close).

    يقبل: list[dict] بمفاتيح مرنة (timestamp|time|open_time, open|o, ...)
          أو pandas DataFrame بأعمدة open/high/low/close (الفهرس زمني أو
          عمود timestamp). الأزمنة عبر to_ms الموحد (ISO مُحلَّل فعلياً).
    """
    times: List[int] = []
    o: List[float] = []
    h: List[float] = []
    l: List[float] = []
    c: List[float] = []

    def _num(v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    if candles is None:
        return times, o, h, l, c

    # pandas DataFrame
    if hasattr(candles, "iterrows") and hasattr(candles, "columns"):
        cols = {str(x).lower(): x for x in candles.columns}
        ocol = cols.get("open") or cols.get("o")
        hcol = cols.get("high") or cols.get("h")
        lcol = cols.get("low") or cols.get("l")
        ccol = cols.get("close") or cols.get("c") or cols.get("adj close")
        tcol = cols.get("timestamp") or cols.get("time") or cols.get("open_time") or cols.get("date")
        if ocol is None or hcol is None or lcol is None or ccol is None:
            raise ValueError(
                f"أعمدة الشموع غير مكتملة: available={list(candles.columns)} — مطلوب open/high/low/close"
            )
        for idx, row in candles.iterrows():
            if tcol is not None:
                times.append(to_ms(row[tcol]))
            else:
                times.append(to_ms(idx))
            o.append(_num(row[ocol]))
            h.append(_num(row[hcol]))
            l.append(_num(row[lcol]))
            c.append(_num(row[ccol]))
        # توحيد: أي قيمة غير صالحة (NaN/Inf) تصبح None — كل الدوال اللاحقة تدعم None
        return times, [clean_float(x) for x in o], [clean_float(x) for x in h], \
            [clean_float(x) for x in l], [clean_float(x) for x in c]

    # list[dict] / list[model]
    for row in candles:
        if row is None:
            continue
        if not isinstance(row, dict):
            getter = getattr(row, "model_dump", None) or getattr(row, "dict", None)
            row = getter() if callable(getter) else dict(row.__dict__)
        low = {str(k).lower(): v for k, v in row.items()}
        times.append(to_ms(low.get("timestamp", low.get("time", low.get("open_time", low.get("date", 0))))))
        o.append(_num(low.get("open", low.get("o"))))
        h.append(_num(low.get("high", low.get("h"))))
        l.append(_num(low.get("low", low.get("l"))))
        c.append(_num(low.get("close", low.get("c"))))

    # توحيد: أي قيمة غير صالحة (NaN/Inf) تصبح None
    return times, [clean_float(x) for x in o], [clean_float(x) for x in h], \
        [clean_float(x) for x in l], [clean_float(x) for x in c]


def norm_volume(candles: Any) -> List[Optional[float]]:
    """استخراج عمود الحجم بنفس مرونة norm_candles.

    يقبل: list[dict] (volume|vol|v) أو pandas DataFrame (volume|vol|v).
    يعيد قائمة بنفس طول الشموع — None لكل شمعة بلا حجم صالح.
    بدون الحجم لا يُبنى المرجع R ولا تُصنَّف S1/S2/S3 (مواصفة صحيحة —
    لكن يجب أن يصل الحجم فعلاً: مسار chart-data في الباك تست كان يمرر
    الشموع بلا volume — أُصلح في ROUND34).
    """
    vols: List[Optional[float]] = []
    if candles is None:
        return vols

    def _num(v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    if hasattr(candles, "iterrows") and hasattr(candles, "columns"):
        cols = {str(x).lower(): x for x in candles.columns}
        vcol = cols.get("volume") or cols.get("vol") or cols.get("v")
        if vcol is None:
            return [None] * len(candles)
        for _idx, row in candles.iterrows():
            vols.append(_num(row[vcol]))
        return [clean_float(x) for x in vols]

    for row in candles:
        if row is None:
            vols.append(float("nan"))
            continue
        if not isinstance(row, dict):
            getter = getattr(row, "model_dump", None) or getattr(row, "dict", None)
            row = getter() if callable(getter) else dict(row.__dict__)
        low = {str(k).lower(): v for k, v in row.items()}
        vols.append(_num(low.get("volume", low.get("vol", low.get("v")))))
    return [clean_float(x) for x in vols]


def rolling_extreme(arr: Sequence[Optional[float]], w: int, is_max: bool) -> List[Optional[float]]:
    """أقصى/أدنى نافذة منزلقة بحجم w (يشمل الشمعة الحالية) — deque O(n).
    يعيد None قبل اكتمال النافذة الأولى (مطابق لسلوك na في Pine)."""
    n = len(arr)
    out: List[Optional[float]] = [None] * n
    dq: deque = deque()  # فهارس مرشحة monotonic
    for i in range(n):
        v = arr[i]
        if v is None:
            # نتجاهل الشموع غير الصالحة (لا تحطم النافذة)
            if dq and dq[0] <= i - w:
                dq.popleft()
            out[i] = arr[dq[0]] if (dq and i >= w - 1) else None
            continue
        while dq and ((arr[dq[-1]] is not None and (
                (arr[dq[-1]] <= v) if is_max else (arr[dq[-1]] >= v)))):
            dq.pop()
        dq.append(i)
        while dq[0] <= i - w:
            dq.popleft()
        out[i] = arr[dq[0]] if i >= w - 1 else None
    return out


def level_tag(r: float) -> str:
    """تسمية عمود المستوى بحذف النقطة العشرية: 0.236 → '0236' · 0.5 → '05'."""
    s = ("%g" % float(r)).strip()
    return s.replace(".", "").replace("-", "neg")


def infer_price_tick(*price_arrays: Sequence[Optional[float]]) -> Optional[float]:
    """استنتاج تيك الرمز من البيانات: أصغر فرق موجب بين مستويات سعرية فعلية.

    أسعار المنصات مُكمّمة بخطوة السعر (tick size) — أصغر فروق موجبة بين
    القيم المُرتّبة الفريدة = التيك (أو مضاعفاته عند كثافة البيانات).
    يعيد None إن لم تُستنتَج (بيانات قليلة/غير مُكمّمة).
    """
    vals: set = set()
    for arr in price_arrays:
        for v in arr:
            if v is not None:
                f = float(v)
                if math.isfinite(f) and f > 0:
                    vals.add(round(f, 12))
    if len(vals) < 2:
        return None
    s = sorted(vals)
    min_diff = None
    for a, b in zip(s, s[1:]):
        d = b - a
        if d > 0 and (min_diff is None or d < min_diff):
            min_diff = d
    return min_diff


# ===========================================================================
# (2) كشف الزقزاق الموحد — وضعان بنفس السلوك التاريخي المعتمد
# ===========================================================================
def luxalgo_state_machine(
    c: List[Optional[float]],
    h: List[Optional[float]],
    l: List[Optional[float]],
    length: int,
) -> Tuple[List[Dict[str, Any]], List[Optional[int]]]:
    """آلة LuxAlgo (الوضع التاريخي المعتمد) — كشف القمم/القيعان على الإغلاقات.

    المنطق (حرفي من "Zig Zag Channels [LuxAlgo]" — السلوك المعتمد منذ الجولة 10):
      upper = highest(close, length); lower = lowest(close, length)
      os := close[length] > upper ? 0 : close[length] < lower ? 1 : os[1]
      top_ev = os==0 ∧ os[1]!=0 → قمة عند bar (n−length) بسعر high[n−length]
      btm_ev = os==1 ∧ os[1]!=1 → قاع عند bar (n−length) بسعر low[n−length]

    يعيد (confirmed, state_series):
      confirmed: [{bar, price, kind, confirmed_at_bar}] — append-only بلا إحلال
                 (confirmed_at_bar = n = لحظة الظهور بعد length شمعة).
      state_series: zz_state لكل شمعة (None قبل أول تحديد · 0 نظام قمم · 1 قيعان).

    ملاحظة استراتيجية: القمة/القاع تُؤكَّد بعد `length` شمعة من حدوثها — اقرأ
    الحدث عند شمعة التأكيد (بلا repaint).
    """
    N = len(c)
    length = max(2, int(length))
    upper = rolling_extreme(c, length, True)   # highest(close, length)
    lower = rolling_extreme(c, length, False)  # lowest(close, length)

    os_state: Optional[int] = None
    confirmed: List[Dict[str, Any]] = []
    s_state: List[Optional[int]] = [None] * N

    for n in range(N):
        new_os = os_state
        if n >= length:
            prev_close = c[n - length]
            up = upper[n]
            lo = lower[n]
            if up is not None and lo is not None and clean_float(prev_close) is not None:
                if prev_close > up:
                    new_os = 0
                elif prev_close < lo:
                    new_os = 1
        top_ev = (new_os == 0 and os_state is not None and os_state != 0)
        btm_ev = (new_os == 1 and os_state is not None and os_state != 1)
        os_state = new_os
        s_state[n] = os_state
        if top_ev:
            pb = n - length
            confirmed.append({"bar": pb, "price": clean_float(h[pb]), "kind": "top",
                              "confirmed_at_bar": n})
        elif btm_ev:
            pb = n - length
            confirmed.append({"bar": pb, "price": clean_float(l[pb]), "kind": "bottom",
                              "confirmed_at_bar": n})
    return confirmed, s_state


def _zigzag_tv_engine(
    h: List[Optional[float]],
    l: List[Optional[float]],
    t: List[int],
    N: int,
    depth: int,
    dev_frac: float,
    backstep: int,
    lv_keys: List[Tuple[float, str]],
    touch_target: float,
    reverse: bool,
    want_series: bool,
) -> Dict[str, Any]:
    """زقزاق MT4/TradingView الكلاسيكي — Depth/Deviation/Backstep على high/low.

    بنية النقل الموثقة (نفس وصف طبقة الفرونت — المصدر المشترك):
      1) مرشّحات الأطراف: قمة مرشحة عند i إذا h[i] ≥ أعلى high في نافذة Depth
         تشمل i (إلى الماضي فقط — سببية)، وقاع مرشح بالمثل على low.
      2) آلة التناوب بإحلال الطرف الأقوى + الانحراف النسبي (كل مرشح يُعالج
         في شمعته — سببية صارمة):
         - نفس النوع: الأقوى (قمة أعلى / قاع أدنى، والتعادل للأحدث) يحل محل
           الطرف الأخير الحي (تمديد الموجة — كما يرسم TV الموجة الواحدة حتى
           انعكاسها). هذا الإحلال هو المنفّذ الدلالي لـBackstep (الأضعف
           المتقارب يُهمل والأقوى/الأحدث يبقى — نفس نتيجة تنظيف backstep
           في MT4 دون أي نظرة مستقبلية).
         - نوع معاكس: يُقبل فقط إذا ابتعد عن سعر الطرف الأخير بنسبة ≥ dev_frac
           (وحدات TV: deviation=20 ⇒ 2.0% من سعر الطرف) — عندها يُثبّت الطرف
           السابق ويبدأ طرف جديد.

    want_series=True يعيد أيضاً السلاسل السببية لكل شمعة (leg_ready/leg_p1/
    leg_diff/s_dir/s_p1/s_p2/s_i1/s_i2/level_series/s_touch + touch_signals)
    — نفس مخرجات محرك ZLF التاريخي حرفياً (بُنيت أثناء نفس التمريرة).
    want_series=False يتخطاها (E2E/الترندية لا تحتاجها — تُبنى النطاقات من
    pair_events مباشرة).

    pair_events (سجل تغيّرات الزوج المرسوم — أساس «لحظة اعتماد النطاق»):
      يُكتب بعد كل قبول طرف جديد ("new") أو إحلال أقوى ("replace") —
      event_bar = الشمعة التي ظهر فيها التغيير (لحظة ظهور الزقزاق).
    """
    depth_i = max(2, int(depth))
    back_i = max(1, int(backstep))  # مُوثّق: يُنفّذ دلالياً عبر إحلال الأقوى
    dev = max(0.0, float(dev_frac))

    # --- التمريرة 1: مرشّحات الأطراف (نافذة Depth على high/low — سببية) ---
    tops: List[Tuple[int, float]] = []
    btms: List[Tuple[int, float]] = []
    for i in range(depth_i - 1, N):
        hi, lo = h[i], l[i]
        if hi is not None:
            peak = True
            for j in range(i - depth_i + 1, i):
                hj = h[j]
                if hj is not None and hj > hi:
                    peak = False
                    break
            if peak:
                tops.append((i, hi))
        if lo is not None:
            trough = True
            for j in range(i - depth_i + 1, i):
                lj = l[j]
                if lj is not None and lj < lo:
                    trough = False
                    break
            if trough:
                btms.append((i, lo))

    events: List[Tuple[str, int, float]] = sorted(
        [("top", b, p) for b, p in tops] + [("bottom", b, p) for b, p in btms],
        key=lambda x: (x[1], 0 if x[0] == "top" else 1),
    )

    # --- التمريرة 2: آلة التناوب (إحلال الأقوى) + الانحراف + سببية السلاسل ---
    pivots: List[Dict[str, Any]] = []
    pair_events: List[Dict[str, Any]] = []   # سجل تغيّرات الزوج المرسوم

    def _snap_pair(event_bar: int, ev_kind: str) -> None:
        # كتابة سجل فقط — لا تأثير على منطق الزقزاق إطلاقاً
        if len(pivots) >= 2:
            a, b = pivots[-2], pivots[-1]
            pair_events.append({
                "event_bar": int(event_bar),
                "event_kind": ev_kind,
                "p_a": {"bar": int(a["bar"]), "price": clean_float(a["price"]), "kind": a["kind"]},
                "p_b": {"bar": int(b["bar"]), "price": clean_float(b["price"]), "kind": b["kind"]},
            })

    leg_ready: List[bool] = [False] * N
    leg_p1: List[Optional[float]] = [None] * N
    leg_diff: List[Optional[float]] = [None] * N
    s_dir: List[float] = [0.0] * N
    s_p1: List[Optional[float]] = [None] * N
    s_p2: List[Optional[float]] = [None] * N
    s_i1: List[Optional[float]] = [None] * N
    s_i2: List[Optional[float]] = [None] * N
    level_series: Dict[str, List[Optional[float]]] = {key: [None] * N for _r, key in lv_keys}
    s_touch: List[float] = [0.0] * N
    touch_signals: List[Dict[str, Any]] = []
    touched = False
    leg_key = None
    ev_i = 0
    for n in range(N):
        while ev_i < len(events) and events[ev_i][1] <= n:
            kind, bar, px = events[ev_i]
            ev_i += 1
            if not pivots:
                pivots.append({"bar": bar, "price": px, "kind": kind, "confirmed_at_bar": bar})
                continue
            last = pivots[-1]
            if kind == last["kind"]:
                stronger = (px >= last["price"]) if kind == "top" else (px <= last["price"])
                if stronger:
                    # إحلال حي للطرف الأخير غير المؤكد — نفس سلوك TV
                    pivots[-1] = {"bar": bar, "price": px, "kind": kind, "confirmed_at_bar": bar}
                    _snap_pair(n, "replace")   # إعادة رسم الشكل = زوج جديد
            else:
                base = last["price"] or 0.0
                accept = (base - px >= base * dev) if kind == "bottom" else (px - base >= base * dev)
                if accept:
                    pivots.append({"bar": bar, "price": px, "kind": kind, "confirmed_at_bar": bar})
                    _snap_pair(n, "new")       # طرف جديد = زوج جديد
        if want_series and len(pivots) >= 2:
            a, b = pivots[-2], pivots[-1]
            q1, q2 = a["price"], b["price"]
            if reverse:
                q1, q2 = q2, q1
            if q1 is not None and q2 is not None:
                diff = (-1.0 if q1 > q2 else 1.0) * abs(q1 - q2)
                direction = 1.0 if q1 < q2 else -1.0
                leg_ready[n] = True
                leg_p1[n] = clean_float(q1)
                leg_diff[n] = diff
                s_dir[n] = direction
                s_p1[n] = clean_float(q1)
                s_p2[n] = clean_float(q2)
                s_i1[n] = float(a["bar"])
                s_i2[n] = float(b["bar"])
                for r, key in lv_keys:
                    level_series[key][n] = clean_float(q1 + diff * r)
                # عقد أول لمس على نفس الساق المرئية (re-arm on leg change)
                key_leg = (a["bar"], b["bar"], direction)
                if key_leg != leg_key:
                    leg_key = key_leg
                    touched = False
                if not touched:
                    hi, lo_ = h[n], l[n]
                    tgt = q1 + diff * touch_target
                    if clean_float(hi) is not None and clean_float(lo_) is not None and lo_ <= tgt <= hi:
                        s_touch[n] = direction
                        touched = True
                        touch_signals.append({
                            "bar": n, "time": t[n],
                            "side": "buy" if direction > 0 else "sell",
                            "signal": "ZZFib Touch Up" if direction > 0 else "ZZFib Touch Down",
                            "price": clean_float(tgt), "ratio": touch_target,
                            "color": "#28cc95" if direction > 0 else "#ff0000",
                        })

    # --- أرجل الرسم (كل زوج نقطتين متعاكستين متتاليتين — بما فيها الطرف الحي) ---
    legs: List[Dict[str, Any]] = []
    for k in range(1, len(pivots)):
        a, b = pivots[k - 1], pivots[k]
        pa, pb_ = a["price"] or 0.0, b["price"] or 0.0
        legs.append({
            "x1": a["bar"], "t1": t[a["bar"]], "y1": clean_float(a["price"]),
            "x2": b["bar"], "t2": t[b["bar"]], "y2": clean_float(b["price"]),
            "kind": b["kind"], "confirmed_at_bar": b["confirmed_at_bar"],
            "dir": 1 if pb_ > pa else (-1 if pb_ < pa else 0),
            "visible": True,
        })

    return {
        "confirmed": pivots,
        "legs": legs,
        "pair_events": pair_events,
        "leg_ready": leg_ready,
        "leg_p1": leg_p1,
        "leg_diff": leg_diff,
        "s_dir": s_dir, "s_p1": s_p1, "s_p2": s_p2, "s_i1": s_i1, "s_i2": s_i2,
        "level_series": level_series,
        "s_touch": s_touch,
        "touch_signals": touch_signals,
    }


def causal_leg_series(
    confirmed: List[Dict[str, Any]],
    N: int,
    lv_keys: List[Tuple[float, str]],
    reverse: bool,
    t: Optional[List[int]] = None,
    h: Optional[List[Optional[float]]] = None,
    l: Optional[List[Optional[float]]] = None,
    touch_target: float = 0.618,
    want_touch: bool = False,
) -> Dict[str, Any]:
    """السلاسل السببية لكل شمعة من قائمة النقاط المؤكدة (وضع luxalgo).

    عند كل شمعة n: آخر نقطتين تأكدتا حتى n (confirmed_at_bar ≤ n) هما الساق
    المرجعية — نفس سلوك zigzag_fib التاريخي في وضع luxalgo حرفياً.

    want_touch=True يضيف عقد zzf_touch الأصلي: أول لمس للمستوى الهدف في
    الساق (نطاق الشمعة يحتوي المستوى) — لمس واحد فقط لكل ساق، وإعادة
    تسليح عند تغيّر الساق (نفس منطق محرك TV داخل تمريرته).
    """
    leg_ready: List[bool] = [False] * N
    leg_p1: List[Optional[float]] = [None] * N
    leg_diff: List[Optional[float]] = [None] * N
    s_dir: List[float] = [0.0] * N
    s_p1: List[Optional[float]] = [None] * N
    s_p2: List[Optional[float]] = [None] * N
    s_i1: List[Optional[float]] = [None] * N
    s_i2: List[Optional[float]] = [None] * N
    level_series: Dict[str, List[Optional[float]]] = {key: [None] * N for _r, key in lv_keys}
    s_touch: List[float] = [0.0] * N
    touch_signals: List[Dict[str, Any]] = []
    touched = False
    leg_key = None

    _pi_leg = 0
    for n in range(N):
        while _pi_leg < len(confirmed) and confirmed[_pi_leg]["confirmed_at_bar"] <= n:
            _pi_leg += 1
        if _pi_leg < 2:
            continue
        _a, _b = confirmed[_pi_leg - 2], confirmed[_pi_leg - 1]
        _q1, _q2 = _a["price"], _b["price"]
        if reverse:
            _q1, _q2 = _q2, _q1
        if _q1 is None or _q2 is None:
            continue
        _diff = (-1.0 if _q1 > _q2 else 1.0) * abs(_q1 - _q2)
        _direction = 1.0 if _q1 < _q2 else -1.0
        leg_ready[n] = True
        leg_p1[n] = _q1
        leg_diff[n] = _diff
        s_dir[n] = _direction
        s_p1[n] = _q1
        s_p2[n] = _q2
        s_i1[n] = float(_a["bar"])
        s_i2[n] = float(_b["bar"])
        for r, key in lv_keys:
            level_series[key][n] = clean_float(_q1 + _diff * r)

        if want_touch:
            key_leg = (_a["bar"], _b["bar"], _direction)
            if key_leg != leg_key:
                leg_key = key_leg
                touched = False
            tgt = _q1 + _diff * touch_target
            if not touched and h is not None and l is not None:
                hi, lo_ = h[n], l[n]
                if clean_float(hi) is not None and clean_float(lo_) is not None and lo_ <= tgt <= hi:
                    s_touch[n] = _direction
                    touched = True
                    touch_signals.append({
                        "bar": n, "time": t[n] if t is not None else 0,
                        "side": "buy" if _direction > 0 else "sell",
                        "signal": "ZZFib Touch Up" if _direction > 0 else "ZZFib Touch Down",
                        "price": clean_float(tgt), "ratio": touch_target,
                        "color": "#28cc95" if _direction > 0 else "#ff0000",
                    })

    out = {
        "leg_ready": leg_ready, "leg_p1": leg_p1, "leg_diff": leg_diff,
        "s_dir": s_dir, "s_p1": s_p1, "s_p2": s_p2, "s_i1": s_i1, "s_i2": s_i2,
        "level_series": level_series,
    }
    if want_touch:
        out["s_touch"] = s_touch
        out["touch_signals"] = touch_signals
    return out


def zigzag_detect(
    t: List[int],
    o: List[Optional[float]],
    h: List[Optional[float]],
    l: List[Optional[float]],
    c: List[Optional[float]],
    N: int,
    mode: str = "luxalgo",
    length: int = 100,
    depth: int = 12,
    deviation: float = 20.0,
    backstep: int = 3,
    reverse: bool = False,
    lv_keys: Optional[List[Tuple[float, str]]] = None,
    touch_target: float = 0.618,
    want_series: bool = False,
    want_state_series: bool = False,
    want_touch: bool = False,
) -> Dict[str, Any]:
    """الكشف الموحد للزقزاق — نقطة الدخل الوحيدة لكل المحركات الثلاثة.

    الأوضاع (نفس السلوك التاريخي المعتمد حرفياً — بلا أي تغيير دلالي):
      "luxalgo"      — آلة الإغلاقات المنزلقة (length): الكشف على الإغلاقات
                      والتأكيد بعد length شمعة. «لحظة الظهور» = confirmed_at_bar.
      "tradingview"  — Depth/Deviation/Backstep على high/low: الأطراف على
                      القصوى الحقيقية، إحلال الأقوى، سببية صارمة.

    المخرجات الموحدة (نفس البنية لأي وضع — عقد الرسم الموحد للفرونت):
      confirmed:    [{bar, price, kind, confirmed_at_bar}] — النقاط المؤكدة.
      legs:         أرجل الرسم [{x1,t1,y1,x2,t2,y2,kind,confirmed_at_bar,dir,visible}]
                    — نفس شكل عقد OVERLAYS-CONTRACT (الرسم بـ time لا bar).
      pair_events:  سجل تغيّرات الزوج المرسوم — event_bar = لحظة الظهور
                    (ميلاد النطاق) لكل زوج [الطرف الظاهر أولاً، الثاني].
      series:       السلاسل السببية (فقط عند want_series=True — لوضع
                    tradingview تُبنى داخل نفس التمريرة؛ لوضع luxalgo عبر
                    causal_leg_series). zz_state عند want_state_series=True.
    """
    try:
        mode = str(mode or "luxalgo").strip().lower()
    except Exception:
        mode = "luxalgo"
    if lv_keys is None:
        lv_keys = []
    lv_keys = [(float(r), str(k)) for r, k in lv_keys]

    out: Dict[str, Any] = {
        "mode": mode,
        "core_spec": ZIGZAG_FIB_CORE_SPEC,
        "confirmed": [],
        "legs": [],
        "pair_events": [],
        "series": None,
        "state_series": None,
    }

    if mode == "tradingview":
        _tv = _zigzag_tv_engine(
            h, l, t, N, depth, float(deviation) / 1000.0, backstep,
            lv_keys, touch_target, reverse, want_series,
        )
        out["confirmed"] = _tv["confirmed"]
        out["legs"] = _tv["legs"]
        out["pair_events"] = _tv["pair_events"]
        if want_series:
            out["series"] = {
                "leg_ready": _tv["leg_ready"], "leg_p1": _tv["leg_p1"],
                "leg_diff": _tv["leg_diff"],
                "s_dir": _tv["s_dir"], "s_p1": _tv["s_p1"], "s_p2": _tv["s_p2"],
                "s_i1": _tv["s_i1"], "s_i2": _tv["s_i2"],
                "level_series": _tv["level_series"],
                "s_touch": _tv["s_touch"], "touch_signals": _tv["touch_signals"],
            }
        return out

    # --- luxalgo (السلوك التاريخي حرفياً) ---
    confirmed, s_state = luxalgo_state_machine(c, h, l, length)
    out["confirmed"] = confirmed
    out["state_series"] = s_state if want_state_series else None

    # أرجل الرسم (كل زوج نقطتين متعاكستين متتاليتين)
    legs: List[Dict[str, Any]] = []
    for k in range(1, len(confirmed)):
        a, b = confirmed[k - 1], confirmed[k]
        pa, pb_ = a["price"] or 0.0, b["price"] or 0.0
        legs.append({
            "x1": a["bar"], "t1": t[a["bar"]], "y1": clean_float(a["price"]),
            "x2": b["bar"], "t2": t[b["bar"]], "y2": clean_float(b["price"]),
            "kind": b["kind"], "confirmed_at_bar": b["confirmed_at_bar"],
            "dir": 1 if pb_ > pa else (-1 if pb_ < pa else 0),
            "visible": True,
        })
    out["legs"] = legs

    # pair_events: لحظة ظهور الزوج = confirmed_at_bar للطرف الثاني
    # (شمعة الظهور — وليس شمعة القاع/القمة نفسها) — أساس ولادة النطاق.
    pair_events: List[Dict[str, Any]] = []
    for k in range(1, len(confirmed)):
        a, b = confirmed[k - 1], confirmed[k]
        pair_events.append({
            "event_bar": int(b["confirmed_at_bar"]),  # ✅ لحظة ظهور الزقزاق
            "event_kind": "new",
            "p_a": {"bar": int(a["bar"]), "price": clean_float(a["price"]), "kind": a["kind"]},
            "p_b": {"bar": int(b["bar"]), "price": clean_float(b["price"]), "kind": b["kind"]},
        })
    out["pair_events"] = pair_events

    if want_series:
        out["series"] = causal_leg_series(
            confirmed, N, lv_keys, reverse,
            t=t, h=h, l=l, touch_target=touch_target,
            want_touch=want_touch,
        )
    return out


# ===========================================================================
# (3) الفيبوناتشي الموحد — معادلة واحدة + حدود رسم (ولادة → نهاية)
# ===========================================================================
def fib_leg_math(p1: Optional[float], p2: Optional[float], reverse: bool = False) -> Dict[str, Any]:
    """حساب مسار الفيبو الموحد بين طرفي الساق/النطاق.

    المعادلة المصادقة بالبكسل:
      q1, q2 = (p2, p1) إذا reverse وإلا (p1, p2)
      diff = (q1 > q2 ? -1 : +1) × |q1 − q2|
      price(level) = q1 + diff × level
      direction = +1 صاعد (q1 < q2) وإلا −1
    ملاحظة المقياس: خط 0.618 بمقياس رسم المستخدم (1 عند الطرف الأول، 0 عند
    الثاني) = price(0.382) بالمحرك — بغضّ الاتجاه.
    """
    if p1 is None or p2 is None:
        return {"q1": None, "q2": None, "diff": None, "dir": 0.0, "rng": 0.0, "degenerate": True}
    q1, q2 = p1, p2
    if reverse:
        q1, q2 = q2, q1
    rng = abs(q1 - q2)
    diff = (-1.0 if q1 > q2 else 1.0) * rng
    direction = 1.0 if q1 < q2 else -1.0
    return {"q1": q1, "q2": q2, "diff": diff, "dir": direction,
            "rng": rng, "degenerate": not (rng > 0)}


def build_ranges(
    pair_events: List[Dict[str, Any]],
    t: List[int],
    N: int,
    reverse: bool,
    launch_engine_level: float,
) -> List[Dict[str, Any]]:
    """بناء النطاقات المتعاقبة من سجل تغيّرات زوج الزقزاق المرسوم.

    ✅ مواصفة E2E المصادقة (ROUND26): النطاق يولد لحظة ظهور الزقزاق —
    anchor = شمعة الظهور (وليس شمعة القمة/القاع). كل ما قبل الظهور ليس
    نطاقاً بعد. الموت (death) = ولادة النطاق التالي (أو N للأخير الحي).
    الأزواج تتناوب طبيعياً: قمة→قاع ثم قاع→قمة.

    launch = خط الانطلاقة (0.618 بمقياس المستخدم = price(launch_engine_level)
    بمقياس المحرك — 0.382 افتراضياً).
    """
    ranges: List[Dict[str, Any]] = []
    for k, ev in enumerate(pair_events):
        p_a, p_b = ev.get("p_a"), ev.get("p_b")
        if not p_a or not p_b:
            continue
        pa_p, pb_p = p_a.get("price"), p_b.get("price")
        if pa_p is None or pb_p is None:
            continue
        lo = min(pa_p, pb_p)
        hi = max(pa_p, pb_p)
        rng = hi - lo
        m = fib_leg_math(pa_p, pb_p, reverse)
        launch = clean_float(m["q1"] + m["diff"] * float(launch_engine_level)) if rng > 0 else None
        ranges.append({
            "index": k,
            "p1": p_a, "p2": p_b,
            "lo": clean_float(lo), "hi": clean_float(hi),
            "diff": m["diff"], "dir": m["dir"],
            "launch": launch,
            "ref": None,          # المرجع الحي يُبنى أثناء المسح الزمني (ROUND26)
            "anchor": int(ev["event_bar"]),
            "anchor_time": t[int(ev["event_bar"])] if 0 <= int(ev["event_bar"]) < N else None,
            "death": None,        # تُملأ بعد الحلقة
            "degenerate": not (rng > 0),
        })
    for k in range(len(ranges)):
        ranges[k]["death"] = ranges[k + 1]["anchor"] if k + 1 < len(ranges) else N
    return ranges


def range_levels_geometry(
    r: Dict[str, Any],
    t: List[int],
    N: int,
    levels: Sequence[float],
    extend_right: bool = True,
) -> List[Dict[str, Any]]:
    """مستويات فيبو النطاق بحدود رسم كاملة — البداية خط الولادة والنهاية نهاية العمر.

    ✅ ROUND34 (طلب صاحب القرار): «بدايته منذ لحظة ولادته التي تُجلب بخط
    ولادته بإحداثياته... ويجب أن يكون للفيبوناتشي نهاية كي لا يشوّه الشارت»:
      x_from/t_from = anchor (خط ولادة النطاق — لحظة ظهور الزقزاق)
      x_to/t_to     = death − 1 للنطاقات الميتة (نهاية طبيعية) ·
                      آخر شمعة للنطاق الحي (آخر نطاق: يمتد حتى الحافة إن
                      كان extend_right وإلا يقف عند نهايته)
    لكل مستوى: ratio/tag/value — نفس معادلة المحرك الموحد
    price(level) = q1 + diff × level.
    """
    out: List[Dict[str, Any]] = []
    if not r or r.get("p1") is None or r.get("p2") is None:
        return out
    p1 = r["p1"].get("price") if isinstance(r["p1"], dict) else None
    p2 = r["p2"].get("price") if isinstance(r["p2"], dict) else None
    m = fib_leg_math(p1, p2)
    if m["diff"] is None:
        return out
    anchor = int(r["anchor"]) if not isinstance(r.get("anchor"), dict) else int(r["anchor"]["bar"])
    death = r.get("death")
    death_bar = int(death["bar"]) if isinstance(death, dict) else (int(death) if death is not None else None)
    last_bar = N - 1
    is_live = death_bar is None or death_bar >= N
    if is_live:
        x_to = last_bar if extend_right else max(anchor, min((death_bar or N) - 1, last_bar))
    else:
        x_to = max(anchor, min(death_bar - 1, last_bar))
    # ✅ ROUND39 (رداً على طلبات وكيل الفرونت ج38 — إضافات صرفة بلا أي
    # تغيير سلوك): display = تسمية المستوى باصطلاح TV/المستخدم (عقد
    # ROUND18: engine(L) ≡ frontend(1−L) ⇒ الملصق = 1−ratio) · is_launch =
    # علم خط الانطلاقة (launch_line = price(launch_engine_level) بنفس
    # معادلة المستويات حرفياً فالمطابقة تامة — النطاقات المنحلة بلا علم).
    launch = r.get("launch")
    for rr in levels:
        try:
            rr = float(rr)
        except (TypeError, ValueError):
            continue
        val = clean_float(m["q1"] + m["diff"] * rr)
        out.append({
            "ratio": rr, "tag": level_tag(rr),
            "value": val,
            "display": round(1.0 - rr, 5),
            "is_launch": bool(launch is not None and val is not None
                              and abs(val - launch) < 1e-9),
            "x_from": anchor,
            "t_from": t[anchor] if 0 <= anchor < N else None,
            "x_to": x_to,
            "t_to": t[x_to] if 0 <= x_to < N else None,
            "extend_right": bool(is_live and extend_right),
        })
    return out


def range_public(r: Dict[str, Any], t: List[int], N: int,
                 levels: Optional[Sequence[float]] = None,
                 extend_right: bool = True) -> Dict[str, Any]:
    """الشكل العام للنطاق في المخرجات (للرسم والتوثيق).

    ✅ ROUND34: يضيف levels[] لكل نطاق (فيبو من خط الولادة إلى نهاية العمر)
    — كان موجوداً فقط للنطاق الحي (current). الآن كل نطاق تاريخي يُرسم
    بفيبو مكتمل البداية والنهاية فلا يمتد قديمٌ فيشوّه الشارت.
    """
    p1, p2 = r["p1"], r["p2"]
    death = r["death"]
    death_bar = int(death["bar"]) if isinstance(death, dict) else death
    pub = {
        "index": r["index"],
        "p1": {"bar": p1["bar"], "time": t[p1["bar"]] if 0 <= p1["bar"] < N else None,
               "price": clean_float(p1["price"]), "kind": p1["kind"]},
        "p2": {"bar": p2["bar"], "time": t[p2["bar"]] if 0 <= p2["bar"] < N else None,
               "price": clean_float(p2["price"]), "kind": p2["kind"]},
        "anchor": {"bar": r["anchor"], "time": r["anchor_time"]},
        "death": {"bar": death_bar,
                  "time": t[death_bar] if (death_bar is not None and 0 <= death_bar < N) else None},
        "dir": float(r["dir"]),
        "launch_line": r["launch"],
        "ref": ({"bar": r["ref"]["bar"], "time": r["ref"]["time"],
                 "high": clean_float(r["ref"]["high"]), "vol": clean_float(r["ref"]["vol"])}
                if r["ref"] else None),
        "degenerate": bool(r["degenerate"]),
    }
    if levels is not None:
        pub["levels"] = range_levels_geometry(r, t, N, levels, extend_right)
    return pub
