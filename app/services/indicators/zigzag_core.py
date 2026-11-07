# =============================================================================
# ✅ الجولة 34 — النواة الموحدة لمحرك الزقزاق والفيبو والترندات — الملف الواحد
# =============================================================================
# أمر صاحب القرار (2026-11-05): «سوّي محرك الزقزاق واحد لكل الاستراتيجيات
# ومحرك الفيبوناتشي واحد أيضاً للثلاث استراتيجيات — البطل والبطل e2e والبطل
# e2e الترنديه — الزقزاق والفيبوناتشي شيء مشترك بين استراتيجية البطل e2e
# واستراتيجية البطل e2e الترنديه». هذا الملف هو تلك النواة الواحدة:
#
#   - كل الدوال المساعدة المشتركة (_clean/_ts/_norm_candles/_norm_volume/
#     _rolling_extreme/_level_tag/_infer_price_tick) بنسخة مرجعية واحدة
#     (نسخة overlays.py المصادقة — بما فيها إصلاح ROUND30 لمحوّل الزمن ISO
#     الذي كان يجعل كل أزمنة رسم الباك تست صفرية → «رسومات عشوائية»).
#   - محرك زقزاق TradingView/MT4 الكلاسيكي «zigzag_tv_core» — جسم واحد
#     حرفي لكل المستهلكين: الشارت الحي (zzfib) وباك تست/قالب البطل e2e
#     (zzfib_e2e) وباك تست/قالب البطل e2e الترنديه (zzfib_e2e_trendy)
#     ومؤشر الترند المستقل (trend_fractal عبر _norm_candles).
#
# عقد الأمان (تثبيت إلزامي): النواة نسخة حرفية من جسم _zigzag_tv_engine
# في overlays.py (المرجع المصادق ج19→ج33) + سجل pair_events المستورد حرفياً
# من استنساخ E2E (سجل تعريفي فقط — لا يلمس منطق الزقزاق إطلاقاً). أي
# استهلاك بعد الدمج يجب أن يعطي نفس المخرجات حرفياً على نفس الشموع (تُثبَت
# بـ A/B نفس-البيانات في حزمة ج34: verify/ab_same_candles.py).
#
# التبعيات الدائرية: لا شيء — هذا الملف لا يستورد من أي ملف استراتيجية،
# والثلاثة تستورده (اتجاه تبعية واحد: استراتيجية → نواة).
# =============================================================================
from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 1) التنظيف الرقمي JSON-آمن
# ---------------------------------------------------------------------------
def _clean(v: Optional[float]) -> Optional[float]:
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


# ---------------------------------------------------------------------------
# 2) تحويل الزمن — نسخة ROUND30 المصادقة (تدعم ISO/Z فعلياً)
# ---------------------------------------------------------------------------
def _ts(v: Any) -> int:
    """زمن → ملي ثانية. يدعم: ms · ثوانٍ · datetime · pandas Timestamp · نص ISO.

    ✅ ROUND30 (المرجع المصادق): نص ISO مثل "2026-10-21T16:30:00Z" يُحلل فعلياً
    (بلا منطقة زمنية → UTC كتخزين المنصة) — النسخة القديمة كانت تُعيد 0 على أي
    سلسلة ISO، وكانت هذه الجذر المُثبت لصفرية كل أزمنة طبقات الرسم في
    الباك-تست (مسار chart-data يمرر timestamp كسلسلة ISO) → «رسومات عشوائية».
    ✅ ROUND34: صارت النواة الموحدة الوحيدة — كل الاستراتيجيات تورثها.
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
                from datetime import datetime, timezone
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


# ---------------------------------------------------------------------------
# 3) تطبيع الشموع والأحجام
# ---------------------------------------------------------------------------
def _norm_candles(candles: Any) -> Tuple[List[int], List[float], List[float], List[float], List[float]]:
    """يحوّل الشموع إلى (times_ms, open, high, low, close).

    يقبل: list[dict] بمفاتيح مرنة (timestamp|time|open_time, open|o, ...)
          أو pandas DataFrame بأعمدة open/high/low/close (الفهرس زمني أو عمود timestamp).
    """
    times: List[int] = []
    o: List[float] = []
    h: List[float] = []
    l: List[float] = []
    c: List[float] = []

    def _num(v: Any) -> float:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return float("nan")
        return f

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
                times.append(_ts(row[tcol]))
            else:
                times.append(_ts(idx))
            o.append(_num(row[ocol]))
            h.append(_num(row[hcol]))
            l.append(_num(row[lcol]))
            c.append(_num(row[ccol]))
        # توحيد: أي قيمة غير صالحة (NaN/Inf) تصبح None — كل الدوال اللاحقة تدعم None
        return times, [_clean(x) for x in o], [_clean(x) for x in h], [_clean(x) for x in l], [_clean(x) for x in c]

    # list[dict] / list[model]
    for row in candles:
        if row is None:
            continue
        if not isinstance(row, dict):
            getter = getattr(row, "model_dump", None) or getattr(row, "dict", None)
            row = getter() if callable(getter) else dict(row.__dict__)
        low = {str(k).lower(): v for k, v in row.items()}
        times.append(_ts(low.get("timestamp", low.get("time", low.get("open_time", low.get("date", 0))))))
        o.append(_num(low.get("open", low.get("o"))))
        h.append(_num(low.get("high", low.get("h"))))
        l.append(_num(low.get("low", low.get("l"))))
        c.append(_num(low.get("close", low.get("c"))))

    # توحيد: أي قيمة غير صالحة (NaN/Inf) تصبح None
    return times, [_clean(x) for x in o], [_clean(x) for x in h], [_clean(x) for x in l], [_clean(x) for x in c]


def _norm_volume(candles: Any) -> List[Optional[float]]:
    """✅ الجولة 13.1 (ZLF) — استخراج عمود الحجم بنفس مرونة _norm_candles.

    يقبل: list[dict] (volume|vol|v) أو pandas DataFrame (volume|vol|v).
    يعيد قائمة بنفس طول الشموع — None لكل شمعة بلا حجم صالح.
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
        return [_clean(x) for x in vols]

    for row in candles:
        if row is None:
            vols.append(float("nan"))
            continue
        if not isinstance(row, dict):
            getter = getattr(row, "model_dump", None) or getattr(row, "dict", None)
            row = getter() if callable(getter) else dict(row.__dict__)
        low = {str(k).lower(): v for k, v in row.items()}
        vols.append(_num(low.get("volume", low.get("vol", low.get("v")))))
    return [_clean(x) for x in vols]


# ---------------------------------------------------------------------------
# 4) النافذة المنزلقة (أقصى/أدنى) — deque O(n)
# ---------------------------------------------------------------------------
def _rolling_extreme(arr: Sequence[Optional[float]], w: int, is_max: bool) -> List[Optional[float]]:
    """أقصى/أدنى نافذة منزلقة بحجم w (تشمل الشمعة الحالية) — deque O(n).
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


# ---------------------------------------------------------------------------
# 5) تسمية المستويات + استنتاج التيك
# ---------------------------------------------------------------------------
def _level_tag(r: float) -> str:
    """تسمية عمود المستوى بحذف النقطة العشرية: 0.236 → '0236' · 0.5 → '05' · 1.0 → '1'."""
    s = ("%g" % float(r)).strip()
    return s.replace(".", "").replace("-", "neg")


def _infer_price_tick(*price_arrays: Sequence[Optional[float]]) -> Optional[float]:
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


# ---------------------------------------------------------------------------
# 6) محرك زقزاق TradingView/MT4 الكلاسيكي — الجسم الواحد لكل الاستراتيجيات
# ---------------------------------------------------------------------------
def zigzag_tv_core(
    h: List[Optional[float]],
    l: List[Optional[float]],
    t: List[int],
    N: int,
    depth: int,
    dev_frac: float,
    backstep: int,
    lv_keys: Optional[List[Tuple[float, str]]] = None,
    touch_target: Optional[float] = None,
    reverse: bool = False,
) -> Dict[str, Any]:
    """زقزاق MT4/TradingView الكلاسيكي — Depth/Deviation/Backstep على high/low.

    ✅ ROUND34 — «المحرك الواحد»: هذا الجسم هو نسخة _zigzag_tv_engine المرجعية
    حرفياً (المرجع المصادق من الجولة 19 حتى 33) + سجل pair_events من استنساخ
    E2E (سجل تعريفي بلا أي مساس بالمنطق). الشارت الحي وقالب البطل e2e وقالب
    البطل e2e الترنديه كلهم يستوردون هذا الجسم — صفر انحراف ممكن.

    بنية النقل الموثقة (نفس وصف طبقة الفرونت — المصدر المشترك):
      1) مرشّحات الأطراف: قمة مرشحة عند i إذا h[i] ≥ أعلى high في نافذة Depth
         تشمل i (إلى الماضي فقط — سببية)، وقاع مرشح بالمثل على low.
      2) آلة التناوب بإحلال الطرف الأقوى + الانحراف النسبي (كل مرشح يُعالج
         في شمعته — سببية صارمة):
         - نفس النوع: الأقوى (قمة أعلى / قاع أدنى، والتعادل للأحدث) يحل محل
           الطرف الأخير الحي (تمديد الموجة — كما يرسم TV الموجة الواحدة حتى
           انعكاسها). ✅ ROUND19: هذا الإحلال هو المنفّز الدلالي لـBackstep
           (الأضعف المتقارب يُهمل والأقوى/الأحدث يبقى — نفس نتيجة تنظيف
           backstep في MT4 دون أي نظرة مستقبلية).
         - نوع معاكس: يُقبل فقط إذا ابتعد عن سعر الطرف الأخير بنسبة ≥ dev_frac
           (وحدات TV: deviation=20 ⇒ 2.0% من سعر الطرف) — عندها يُثبّت الطرف
           السابق ويبدأ طرف جديد.
    السببية (عقد عدم إعادة الرسم):
      - كل نقطة تحمل confirmed_at_bar = شمعة آخر قبول/إحلال لها (يُعرف عند
        إغلاق شمعتها — لا معلومة مستقبلية).
      - السلاسل لكل شمعة n تعكس حالة الأطراف كما هي عند n (الطرف الأخير الحي —
        نفس ما يعرضه TV)، وقيم الشمعة n لا تُعاد كتابة أبداً؛ الإحلال يقع على
        شموع لاحقة فقط، وأي حساب ينتهي عند T يعطي سلاسل T مطابقة حرفياً لأي
        نافذة أطول (تثبيت مُختبَر ببرهان القص الزمني).
      - الساق المرجعية في كل شمعة = آخر طرفين مقبولين عند تلك الشمعة.
    """
    depth_i = max(2, int(depth))
    back_i = max(1, int(backstep))  # مُوثّق: يُنفّذ دلالياً عبر إحلال الأقوى (انظر أعلاه)
    dev = max(0.0, float(dev_frac))
    if lv_keys is None:
        lv_keys = []

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

    # ✅ ROUND19: لا تنظيف backstep منفصل — يُنفّذ دلالياً بإحلال الأقوى داخل
    # آلة التناوب أدناه (كل مرشح يعالج في زمنه — صفر تسريب مستقبلي).

    events: List[Tuple[str, int, float]] = sorted(
        [("top", b, p) for b, p in tops] + [("bottom", b, p) for b, p in btms],
        key=lambda x: (x[1], 0 if x[0] == "top" else 1),
    )

    # --- التمريرة 2: آلة التناوب (إحلال الأقوى) + الانحراف + سببية السلاسل ---
    pivots: List[Dict[str, Any]] = []
    pair_events: List[Dict[str, Any]] = []   # ✅ ROUND34: السجل الموحد (من E2E حرفياً)

    def _snap_pair(event_bar: int, ev_kind: str) -> None:
        # ✅ ZLF-E2E — كتابة سجل، لا تأثير على منطق الزقزاق إطلاقاً
        if len(pivots) >= 2:
            a, b = pivots[-2], pivots[-1]
            pair_events.append({
                "event_bar": int(event_bar),
                "event_kind": ev_kind,
                "p_a": {"bar": int(a["bar"]), "price": _clean(a["price"]), "kind": a["kind"]},
                "p_b": {"bar": int(b["bar"]), "price": _clean(b["price"]), "kind": b["kind"]},
            })

    leg_ready = [False] * N
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
                    _snap_pair(n, "replace")
            else:
                base = last["price"] or 0.0
                accept = (base - px >= base * dev) if kind == "bottom" else (px - base >= base * dev)
                if accept:
                    pivots.append({"bar": bar, "price": px, "kind": kind, "confirmed_at_bar": bar})
                    _snap_pair(n, "new")
        if len(pivots) >= 2:
            a, b = pivots[-2], pivots[-1]
            q1, q2 = a["price"], b["price"]
            if reverse:
                q1, q2 = q2, q1
            if q1 is not None and q2 is not None:
                diff = (-1.0 if q1 > q2 else 1.0) * abs(q1 - q2)
                direction = 1.0 if q1 < q2 else -1.0
                leg_ready[n] = True
                leg_p1[n] = _clean(q1)
                leg_diff[n] = diff
                s_dir[n] = direction
                s_p1[n] = _clean(q1)
                s_p2[n] = _clean(q2)
                s_i1[n] = float(a["bar"])
                s_i2[n] = float(b["bar"])
                for r, key in lv_keys:
                    level_series[key][n] = _clean(q1 + diff * r)
                # عقد أول لمس (zzf_touch — عقد الجولة 12) على نفس الساق المرئية
                key_leg = (a["bar"], b["bar"], direction)
                if key_leg != leg_key:
                    leg_key = key_leg
                    touched = False
                if not touched and touch_target is not None:
                    hi, lo_ = h[n], l[n]
                    tgt = q1 + diff * touch_target
                    if _clean(hi) is not None and _clean(lo_) is not None and lo_ <= tgt <= hi:
                        s_touch[n] = direction
                        touched = True
                        touch_signals.append({
                            "bar": n, "time": t[n],
                            "side": "buy" if direction > 0 else "sell",
                            "signal": "ZZFib Touch Up" if direction > 0 else "ZZFib Touch Down",
                            "price": _clean(tgt), "ratio": touch_target,
                            "color": "#28cc95" if direction > 0 else "#ff0000",
                        })

    # --- أرجل الرسم (كل زوج نقطتين متعاكستين متتاليتين — بما فيها الطرف الحي) ---
    legs: List[Dict[str, Any]] = []
    for k in range(1, len(pivots)):
        a, b = pivots[k - 1], pivots[k]
        pa, pb_ = a["price"] or 0.0, b["price"] or 0.0
        legs.append({
            "x1": a["bar"], "t1": t[a["bar"]], "y1": _clean(a["price"]),
            "x2": b["bar"], "t2": t[b["bar"]], "y2": _clean(b["price"]),
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
