# =============================================================================
# ✅ الجولة 10 — Structure Overlays (مؤشرات البنية السعرية) — مطابقة Pine حرفية
# =============================================================================
# ثلاثة مؤشرات رسم/بنية محسوبة في الباكند (مصدر حقيقة واحد للشارت الحي،
# الباك-تست، ومحرك الاستراتيجيات في الخطوة القادمة):
#
#   1) zigzag_channels       — "Zig Zag Channels [LuxAlgo]"
#                               © LuxAlgo — CC BY-NC-SA 4.0
#                               https://creativecommons.org/licenses/by-nc-sa/4.0/
#   2) auto_fib_retracement  — "Auto Fib Retracement Alerts"
#                               © LucemAnb — Mozilla Public License 2.0
#   3) auto_trendline        — "Auto Trendline [DojiEmoji]"
#                               © DojiEmoji — Mozilla Public License 2.0
#
# التصميم:
# - دوال نقية 100% (بلا DB/Redis/شبكة) — قابلة للاستيراد المباشر من محرك
#   الاستراتيجيات: from app.services.indicators.overlays import compute_overlays
# - كل مخرَج JSON-آمن (لا NaN/Inf — None بدلاً منها) وأزمنة بالملي ثانية.
# - لكل مؤشر مخرجان:
#     "geometry" : خطوط/مستويات/ملصقات/علامات جاهزة للرسم في الفرونت.
#     "series"   : أعمدة لكل شمعة (None حيث لا قيمة) للاستخدام الاستراتيجي.
# - مطابقة Pine شري أن يُذكر: منطق na في Pine يُترجم إلى None هنا، وأي
#   قسمة على صفر تُنتج None (في Pine تُنتج na → عناصر لا تُرسم).
# =============================================================================

from __future__ import annotations

import logging
import math
from collections import deque
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "zigzag_channels",
    "auto_fib_retracement",
    "auto_trendline",
    "compute_overlays",
]

# ---------------------------------------------------------------------------
# ألوان افتراضية (مطابقة للسكربتات الأصلية)
# ---------------------------------------------------------------------------
ZZ_COLOR_MID = "#ff5d00"   # خط الزجزاج
ZZ_COLOR_UP = "#ff1100"    # extremity العلوية (dotted)
ZZ_COLOR_DN = "#2157f3"    # extremity السفلية (dotted)

FIB_DEFAULT_LEVELS: List[Tuple[float, bool, str]] = [
    # (ratio, مُفعّل افتراضياً؟, لون)
    (0.0,   True,  "#808080"),
    (0.236, True,  "#a61c00"),
    (0.382, True,  "#95cc28"),
    (0.5,   True,  "#28cc28"),
    (0.618, True,  "#28cc95"),
    (0.786, True,  "#2895cc"),
    (1.0,   True,  "#808080"),
    (1.272, True,  "#82CA89"),
    (1.414, True,  "#F32C42"),
    (1.618, True,  "#2796ED"),
    (2.618, False, "#a61c00"),
    (3.618, False, "#9B03AE"),
    (4.236, False, "#E80065"),
]

TL_COLOR_RECENT = "#800080"      # purple — الخط الحديث (dashed)
TL_COLOR_HIST = "#808080"        # gray  — الخط التاريخي
TL_COLOR_HL = "#0000ff"          # blue  — Higher Low
TL_COLOR_LL = "#808080"          # gray  — Lower Low
TL_COLOR_LH = "#ff0000"          # red   — Lower High
TL_COLOR_HH = "#808080"          # gray  — Higher High


# ---------------------------------------------------------------------------
# تطبيع المدخلات → قوائم floats/ints نقية
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

    def _ts(v: Any) -> int:
        # يدعم ms، ثوانٍ، datetime، pandas Timestamp، نص ISO
        try:
            if hasattr(v, "timestamp") and not isinstance(v, (int, float)):
                return int(v.timestamp() * 1000)
            f = float(v)
            if f < 1e11:          # ثوانٍ → ms
                f *= 1000.0
            return int(f)
        except Exception:
            return 0

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


def _rolling_extreme(arr: Sequence[Optional[float]], w: int, is_max: bool) -> List[Optional[float]]:
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


def _body_extremes_at(bars: List[int], o: List[float], c: List[float]) -> Tuple[List[float], List[float]]:
    """(body_hi, body_lo) = (max(open,close), min(open,close)) لكل فهرس."""
    hi = [max(o[b], c[b]) for b in bars]
    lo = [min(o[b], c[b]) for b in bars]
    return hi, lo


# ===========================================================================
# 1) Zig Zag Channels [LuxAlgo] — © LuxAlgo, CC BY-NC-SA 4.0
# ===========================================================================
def zigzag_channels(
    candles: Any,
    length: int = 100,
    extend: bool = True,
    show_ext: bool = True,
    show_labels: bool = True,
) -> Dict[str, Any]:
    """منفذ حرفي من Pine v4 → Python.

    المنطق (حرفي من السكربت):
      upper = highest(close, length); lower = lowest(close, length)
      os := close[length] > upper ? 0 : close[length] < lower ? 1 : os[1]
      top = os==0 and os[1]!=0   → قمة مؤكدة عند bar (n-length) بسعر high[length]
      btm = os==1 and os[1]!=1   → قاع مؤكد عند bar (n-length) بسعر low[length]
      extremities: أقصى انحراف لجسم الشمعة (max/min لـ open/close) عن خط المقطع،
                   بارامترization مطابق (i/(len-1)) — بما فيه "مطّ" بار واحد
                   الموجود في الأصل.

    ملاحظة استراتيجية مهمة: القمة/القاع تُؤكَّد بعد `length` شمعة من حدوثها
    (بدون repaint إذا قرأتَ الحدث عند شمعة التأكيد، وحدوث repaint متأخر إذا
    قرأتَ العمود عند شمعة القمة نفسها).
    """
    t, o, h, l, c = _norm_candles(candles)
    N = len(c)
    length = max(2, int(length))

    upper = _rolling_extreme(c, length, True)   # highest(close, length)
    lower = _rolling_extreme(c, length, False)  # lowest(close, length)

    os_state: Optional[int] = None
    valtop: Optional[float] = None
    valbtm: Optional[float] = None
    top_n: Optional[int] = None   # شمعة تأكيد القمة
    btm_n: Optional[int] = None   # شمعة تأكيد القاع

    pivots: List[Dict[str, Any]] = []
    segments: List[Dict[str, Any]] = []

    s_pivot_high: List[Optional[float]] = [None] * N
    s_pivot_low: List[Optional[float]] = [None] * N
    s_state: List[Optional[int]] = [None] * N

    def _seg_extremes(p_from: int, p_from_price: float, p_to: int, p_to_price: float) -> Tuple[Optional[float], Optional[float]]:
        """يحسب max_diff_up/dn — مطابق حرفياً لـloop في Pine:
        for i = 0 to len-1:  bar = p_to - i  (من شمعة القمة الجديدة رجوعاً)
            point = p_to_price + i/(len-1) * (p_from_price - p_to_price)
        أي: i=0 → bar=p_to و point=p_to_price؛ i=len-1 → bar=p_from+1 و point=p_from_price.
        (النطاق [p_from+1 .. p_to] — شمعة القمة السابقة نفسها مستثناة — مطابق للأصل)."""
        seg_len = abs(p_to - p_from)
        if seg_len < 2:
            return None, None  # Pine: قسمة على صفر → na → لا خطوط extremity
        md_up = 0.0
        md_dn = 0.0
        for i in range(seg_len):
            bar = p_to - i
            frac = i / (seg_len - 1)
            point = p_to_price + frac * (p_from_price - p_to_price)
            b_hi = max(o[bar], c[bar])
            b_lo = min(o[bar], c[bar])
            d_up = b_hi - point
            d_dn = point - b_lo
            if _clean(d_up) is not None and d_up > md_up:
                md_up = d_up
            if _clean(d_dn) is not None and d_dn > md_dn:
                md_dn = d_dn
        return _clean(md_up), _clean(md_dn)

    for n in range(N):
        new_os = os_state
        if n >= length:
            prev_close = c[n - length]
            up = upper[n]
            lo = lower[n]
            if up is not None and lo is not None and _clean(prev_close) is not None:
                if prev_close > up:
                    new_os = 0
                elif prev_close < lo:
                    new_os = 1
        top_ev = (new_os == 0 and os_state is not None and os_state != 0)
        btm_ev = (new_os == 1 and os_state is not None and os_state != 1)
        os_state = new_os
        s_state[n] = os_state

        if btm_ev:
            pivot_bar = n - length
            pp = l[pivot_bar]
            valbtm = pp
            btm_n = n
            s_pivot_low[pivot_bar] = _clean(pp)
            pivots.append({"bar": pivot_bar, "time": t[pivot_bar], "price": _clean(pp),
                           "kind": "bottom", "confirmed_at_bar": n, "confirmed_at_time": t[n]})
            if show_labels:
                pivots[-1]["label"] = {"text": f"{pp:.4f}".rstrip("0").rstrip("."), "side": "up",
                                       "color": ZZ_COLOR_DN}
            if top_n is not None and valtop is not None:
                from_bar = top_n - length
                md_up, md_dn = _seg_extremes(from_bar, valtop, pivot_bar, pp)
                seg = {
                    "x1": from_bar, "t1": t[from_bar], "y1": _clean(valtop),
                    "x2": pivot_bar, "t2": t[pivot_bar], "y2": _clean(pp),
                    "kind": "bottom", "color": ZZ_COLOR_MID,
                    "ext_up": md_up if show_ext else None,
                    "ext_dn": md_dn if show_ext else None,
                    "ext_color_up": ZZ_COLOR_UP, "ext_color_dn": ZZ_COLOR_DN,
                    "ext_style": "dotted",
                }
                segments.append(seg)

        if top_ev:
            pivot_bar = n - length
            pp = h[pivot_bar]
            valtop = pp
            top_n = n
            s_pivot_high[pivot_bar] = _clean(pp)
            pivots.append({"bar": pivot_bar, "time": t[pivot_bar], "price": _clean(pp),
                           "kind": "top", "confirmed_at_bar": n, "confirmed_at_time": t[n]})
            if show_labels:
                pivots[-1]["label"] = {"text": f"{pp:.4f}".rstrip("0").rstrip("."), "side": "down",
                                       "color": ZZ_COLOR_UP}
            if btm_n is not None and valbtm is not None:
                from_bar = btm_n - length
                md_up, md_dn = _seg_extremes(from_bar, valbtm, pivot_bar, pp)
                seg = {
                    "x1": from_bar, "t1": t[from_bar], "y1": _clean(valbtm),
                    "x2": pivot_bar, "t2": t[pivot_bar], "y2": _clean(pp),
                    "kind": "top", "color": ZZ_COLOR_MID,
                    "ext_up": md_up if show_ext else None,
                    "ext_dn": md_dn if show_ext else None,
                    "ext_color_up": ZZ_COLOR_UP, "ext_color_dn": ZZ_COLOR_DN,
                    "ext_style": "dotted",
                }
                segments.append(seg)

    # --- Extend To Last Bar (barstate.islast and extend) ---
    projection: Optional[Dict[str, Any]] = None
    if extend and N > 0:
        last = N - 1
        src_last = c[last]
        x1 = y1 = None
        if os_state == 1 and btm_n is not None and valbtm is not None:
            x1 = btm_n - length
            y1 = valbtm
        elif os_state == 0 and top_n is not None and valtop is not None:
            x1 = top_n - length
            y1 = valtop
        if x1 is not None and 0 <= x1 < last and _clean(src_last) is not None and _clean(y1) is not None:
            count = last - btm_n + length if os_state == 1 else last - top_n + length
            md_up = 0.0
            md_dn = 0.0
            if count >= 2:
                for i in range(count):
                    bar = last - i
                    if bar < 0 or bar <= x1:
                        break
                    frac = i / (count - 1)
                    point = src_last + frac * (y1 - src_last)
                    b_hi = max(o[bar], c[bar])
                    b_lo = min(o[bar], c[bar])
                    d_up = b_hi - point
                    d_dn = point - b_lo
                    if _clean(d_up) is not None and d_up > md_up:
                        md_up = d_up
                    if _clean(d_dn) is not None and d_dn > md_dn:
                        md_dn = d_dn
            else:
                md_up = md_dn = None
            projection = {
                "x1": x1, "t1": t[x1], "y1": _clean(y1),
                "x2": last, "t2": t[last], "y2": _clean(src_last),
                "kind": "projection", "color": ZZ_COLOR_MID, "extend": "right",
                "ext_up": _clean(md_up) if show_ext else None,
                "ext_dn": _clean(md_dn) if show_ext else None,
                "ext_color_up": ZZ_COLOR_UP, "ext_color_dn": ZZ_COLOR_DN,
                "ext_style": "dotted",
            }

    return {
        "name": "Zig Zag Channels [LuxAlgo]",
        "params": {"length": length, "extend": extend, "show_ext": show_ext, "show_labels": show_labels},
        "pivots": pivots,
        "segments": segments,
        "projection": projection,
        "series": {
            "zz_state": s_state,        # 0=نظام قمم، 1=نظام قيعان، None قبل أول تأكيد
            "zz_pivot_high": s_pivot_high,  # سعر القمة عند شمعة القمة (للعرض — تأكيد متأخر length)
            "zz_pivot_low": s_pivot_low,
        },
        "notes": "القمة/القاع تُؤكد بعد length شمعة من حدوثها. اقرأ zz_state عند شمعة التأكيد للاستراتيجيات (بلا repaint).",
    }


# ===========================================================================
# 2) Auto Fib Retracement Alerts — © LucemAnb, MPL-2.0
# ===========================================================================
def auto_fib_retracement(
    candles: Any,
    depth: int = 10,
    dev_threshold: float = 5.0,
    retracement: float = 0.618,
    level_ratios: Optional[Sequence[float]] = None,
    level_visibility: Optional[Sequence[bool]] = None,
    reverse: bool = False,
    extend_left: bool = False,
    extend_right: bool = True,
) -> Dict[str, Any]:
    """منفذ حرفي من Pine v4 → Python.

    المنطق (حرفي):
      pivots: نافذة 2k+1 (k = depth//2) — المرشح عند bar (n-k) يقبل التعادل (≥).
      pivotFound:
        - نفس الاتجاه والأكثر تطرفاً → مدّ نهاية الرجل (set_xy2).
        - انعكاس + |100*(price-pLast)/price| > dev_threshold → رجل جديدة من (iLast,pLast).
          (لاحظ: القسمة على السعر الجديد — مطابق للسكربت).
      المستويات: من رجل خط lineLast الحالية: p1=y1 (أو معكوس), p2=pLast,
        diff = sign * |p1-p2|، level_r = p1 + diff*r — من بداية الرجل ممتدة يميناً.
      إشارات: buy = p1<p2 و low<=level و high>level؛ التحقيق debounce مطابق
        (barssince(buy)[1] > barssince(p2!=p2[1])).

    انحراف موثّق وحيد: أول رجل في Pine تبدأ من (bar 0, سعر 0) لأن pLast=0
    عند الإقلاع — نحسبها كما هي لكن نوسمها synthetic_anchor=true ونعيّم
    visible=false (لا قيمة رسمية/لا تُرسم)؛ من الرجل الثانية onwards مطابقة تامة.
    """
    t, o, h, l, c = _norm_candles(candles)
    N = len(c)
    k = max(1, int(depth) // 2)
    dev_threshold = float(dev_threshold)

    levels_def: List[Tuple[float, bool]] = []
    if level_ratios is None:
        for ratio, on, _col in FIB_DEFAULT_LEVELS:
            levels_def.append((ratio, on))
    else:
        want = [float(x) for x in level_ratios]
        for i, r in enumerate(want):
            vis = bool(level_visibility[i]) if level_visibility is not None and i < len(level_visibility) else True
            levels_def.append((r, vis))

    isHighLast = False
    lineLast: Optional[Dict[str, Any]] = None
    iLast = 0
    pLast = 0.0
    legs: List[Dict[str, Any]] = []
    last_p2_change: Optional[int] = None       # آخر شمعة تغيّر فيها pLast
    last_buy: Optional[int] = None
    last_sell: Optional[int] = None
    signals: List[Dict[str, Any]] = []

    s_start: List[Optional[float]] = [None] * N
    s_end: List[Optional[float]] = [None] * N
    s_target: List[Optional[float]] = [None] * N

    def _calc_dev(base_price: float, price: float) -> Optional[float]:
        # calc_dev في Pine: 100 * (price - base) / price  ← القسمة على السعر الجديد
        if price == 0 or _clean(price) is None or _clean(base_price) is None:
            return None
        return 100.0 * (price - base_price) / price

    for n in range(N):
        # ---- 1) رصد pivots (الأولوية للقمة عند التزامن — مطابق لترتيب Pine) ----
        cand_h: Optional[Tuple[int, float]] = None
        cand_l: Optional[Tuple[int, float]] = None
        if n >= k:
            barH = n - k
            if barH >= 0:
                ch = h[barH]
                if _clean(ch) is not None:
                    ok = True
                    for i in range(0, 2 * k + 1):
                        b = n - i
                        if b < 0 or b == barH:
                            continue
                        if _clean(h[b]) is not None and h[b] > ch:
                            ok = False
                            break
                    if ok:
                        cand_h = (barH, ch)
                cl = l[barH]
                if _clean(cl) is not None:
                    ok = True
                    for i in range(0, 2 * k + 1):
                        b = n - i
                        if b < 0 or b == barH:
                            continue
                        if _clean(l[b]) is not None and l[b] < cl:
                            ok = False
                            break
                    if ok:
                        cand_l = (barH, cl)

        # ---- 2) معالجة المرشح وفق pivotFound ----
        def _process(is_high: bool, index: int, price: float) -> None:
            nonlocal isHighLast, lineLast, iLast, pLast, last_p2_change
            dev = _calc_dev(pLast, price)
            accepted = False
            new_leg = False
            if isHighLast == is_high and lineLast is not None:
                if (is_high and price > pLast) or ((not is_high) and price < pLast):
                    # مدّ نهاية الرجل الحالية (set_xy2)
                    lineLast["x2"] = index
                    lineLast["t2"] = t[index]
                    lineLast["y2"] = _clean(price)
                    accepted = True
            else:
                if dev is not None and abs(dev) > dev_threshold:
                    leg = {
                        "x1": int(iLast), "t1": t[int(iLast)] if 0 <= iLast < N else 0,
                        "y1": _clean(pLast),
                        "x2": index, "t2": t[index], "y2": _clean(price),
                        "kind": "high" if is_high else "low",
                        "color": "#808080", "style": "dashed", "width": 1,
                        "synthetic_anchor": (_clean(pLast) == 0.0 and iLast == 0),
                    }
                    leg["visible"] = not leg["synthetic_anchor"]
                    if lineLast is not None:
                        # line.delete(lineLast) في Pine — الرجل السابقة تُسقط من الرسم
                        lineLast["visible"] = False
                    legs.append(lineLast) if lineLast is not None else None
                    lineLast = leg
                    new_leg = True
                    accepted = True
            if accepted:
                isHighLast = is_high
                iLast = index
                if pLast != price:
                    last_p2_change = n
                pLast = price

        if cand_h is not None:
            _process(True, cand_h[0], cand_h[1])
        elif cand_l is not None:
            _process(False, cand_l[0], cand_l[1])

        # ---- 3) المستويات + الإشارات (عند نهاية كل شمعة — مطابق) ----
        if lineLast is not None:
            if reverse:
                p1, p2 = pLast, lineLast["y1"]
            else:
                p1, p2 = lineLast["y1"], pLast
            if _clean(p1) is not None and _clean(p2) is not None:
                diff = (-1.0 if p1 > p2 else 1.0) * abs(p1 - p2)
                s_start[n] = _clean(p1)
                s_end[n] = _clean(p2)
                level_val = p1 + diff * float(retracement)
                s_target[n] = _clean(level_val)

                buy = (p1 < p2) and (_clean(l[n]) is not None and l[n] <= level_val) and (_clean(h[n]) is not None and h[n] > level_val)
                sell = (p1 > p2) and (_clean(h[n]) is not None and h[n] >= level_val) and (_clean(l[n]) is not None and l[n] < level_val)

                prev_buy_bs = (n - 1 - last_buy) if last_buy is not None and last_buy <= n - 1 else None
                prev_sell_bs = (n - 1 - last_sell) if last_sell is not None and last_sell <= n - 1 else None
                change_bs = (n - last_p2_change) if last_p2_change is not None else None

                buy_alert = bool(buy and prev_buy_bs is not None and change_bs is not None and prev_buy_bs > change_bs)
                sell_alert = bool(sell and prev_sell_bs is not None and change_bs is not None and prev_sell_bs > change_bs)
                if buy:
                    last_buy = n
                if sell:
                    last_sell = n
                if buy_alert:
                    signals.append({"bar": n, "time": t[n], "side": "buy", "signal": "Buy Retrace",
                                    "price": _clean(level_val), "ratio": float(retracement), "color": "#32cd32"})
                if sell_alert:
                    signals.append({"bar": n, "time": t[n], "side": "sell", "signal": "Sell Retrace",
                                    "price": _clean(level_val), "ratio": float(retracement), "color": "#ff0000"})

    # ---- 4) حالة الرجل الحالية + مستوياتها (آخر حالة — ما يُرسم) ----
    current: Optional[Dict[str, Any]] = None
    if lineLast is not None and _clean(lineLast["y1"]) is not None and _clean(pLast) is not None:
        if reverse:
            p1, p2 = pLast, lineLast["y1"]
        else:
            p1, p2 = lineLast["y1"], pLast
        diff = (-1.0 if p1 > p2 else 1.0) * abs(p1 - p2)
        lv = []
        for ratio, on in levels_def:
            if not on:
                continue
            val = p1 + diff * ratio
            lv.append({"ratio": ratio, "value": _clean(val), "color": "#808080",
                       "x_from": lineLast["x1"], "t_from": lineLast["t1"],
                       "x_to": lineLast["x2"], "t_to": lineLast["t2"],
                       "extend_right": extend_right, "extend_left": extend_left})
        # أعِد الألوان من التعريف الافتراضي عند التطابق
        color_map = {r: col for r, _on, col in FIB_DEFAULT_LEVELS}
        for item in lv:
            if item["ratio"] in color_map:
                item["color"] = color_map[item["ratio"]]
        current = {
            "leg": lineLast,
            "levels": lv,
            "target": {"ratio": float(retracement), "value": _clean(p1 + diff * float(retracement))},
            "p1": _clean(p1), "p2": _clean(p2),
        }

    if lineLast is not None:
        legs.append(lineLast)

    return {
        "name": "Auto Fib Retracement Alerts",
        "params": {"depth": depth, "dev_threshold": dev_threshold, "retracement": retracement,
                   "reverse": reverse, "extend_left": extend_left, "extend_right": extend_right},
        "legs": legs,
        "current": current,
        "signals": signals,
        "series": {"fib_start": s_start, "fib_end": s_end, "fib_target": s_target},
        "notes": "visible=false للرجل السابقة (Pine يحذفها) وللرجل التركيبية الأولى (anchor من سعر 0). المستويات تُرسم من بداية الرجل الحالية ممتدة يميناً.",
    }


# ===========================================================================
# 3) Auto Trendline [DojiEmoji] — © DojiEmoji, MPL-2.0
# ===========================================================================
def auto_trendline(
    candles: Any,
    period: int = 10,
    max_pairs: int = 1,
    extend: str = "right",
) -> Dict[str, Any]:
    """منفذ حرفي من Pine v5 → Python.

    المنطق (حرفي):
      fractals = ta.pivothigh/low(period, period)[1] → فراكتال عند bar p يُعرَف
      عند شمعة (p + period + 1) (الـ[1] في Pine تضيف شمعة تأخير — مطابقة).
      الخطوط: ربط آخر فراكتالين من نفس الجهة (up/dn)، max_pairs يحدد كم زوج
      يُعرض (الأحدث recent-colored، ما قبله historical، وما فوقه يُحذف في Pine
      → visible=false هنا).
      التصنيف: HH/LH (قمم) و HL/LL (قيعان) بمقارنة الفراكتال بسابقه.
      التقاطعات: مس projected للخط عند كل شمعة (بالزوج السائد حينها) و
      ta.cross(close, y) — crossover: a>b و a[1]<=b[1] (مطابق للتعريف الرسمي).
    """
    t, o, h, l, c = _norm_candles(candles)
    N = len(c)
    n = max(2, int(period))
    max_pairs = max(1, int(max_pairs))
    extend = "both" if str(extend).lower() in ("both", "both ways", "bothways") else "right"

    # فراكتال صارم: مركز النافذة أكبر/أصغر من كل ما حوله (تعادل → ليس فراكتالاً)
    def _is_pivot(arr: List[float], p: int, is_high: bool) -> bool:
        # نافذة 2n+1 حول p — الشموع قبل بداية التاريخ تُتجاهل (na في Pine لا يُبطل)
        if p < 0 or p + n >= N:
            return False
        v = arr[p]
        if _clean(v) is None:
            return False
        for b in range(p - n, p + n + 1):
            if b < 0 or b == p:
                continue
            if _clean(arr[b]) is None:
                continue
            if is_high and arr[b] >= v:   # صارم — التعادل يُبطل (سلوك ta.pivothigh)
                return False
            if (not is_high) and arr[b] <= v:
                return False
        return True

    up_fractals: List[Dict[str, Any]] = []
    dn_fractals: List[Dict[str, Any]] = []
    up_lines: List[Dict[str, Any]] = []
    dn_lines: List[Dict[str, Any]] = []

    recent_up1 = recent_up2 = None   # (bar, price)
    recent_dn1 = recent_dn2 = None

    s_upper: List[Optional[float]] = [None] * N
    s_lower: List[Optional[float]] = [None] * N
    s_cross_upper: List[bool] = [False] * N
    s_cross_lower: List[bool] = [False] * N
    crosses: List[Dict[str, Any]] = []

    prev_diff_up: Optional[float] = None
    prev_diff_dn: Optional[float] = None

    def _drop_and_roll(arr: List[Dict[str, Any]]) -> None:
        # الأحدث أولاً (unshift) — عنصر index 1 يصير historical، والزائد يُحذف
        if len(arr) > 1:
            arr[1]["style"] = "historical"
            arr[1]["color"] = TL_COLOR_HIST
        while len(arr) > max_pairs:
            popped = arr.pop()
            popped["visible"] = False

    for m in range(N):
        # ---- فراكتالات مع تأخير [1]: عند الشمعة m نرى مركز (m-1-n) ----
        p_h = m - 1 - n
        if p_h >= 0 and p_h + n < N and _is_pivot(h, p_h, True):
            # up fractal جديد
            recent_up2 = recent_up1
            recent_up1 = (p_h, h[p_h])
            f = {"bar": p_h, "time": t[p_h], "price": _clean(h[p_h]), "side": "up", "label": None}
            if recent_up2 is not None:
                f["label"] = "HH" if h[p_h] > recent_up2[1] else "LH"
                ln = {"side": "up",
                      "x1": recent_up2[0], "t1": t[recent_up2[0]], "y1": _clean(recent_up2[1]),
                      "x2": p_h, "t2": t[p_h], "y2": _clean(h[p_h]),
                      "style": "recent", "color": TL_COLOR_RECENT, "dashed": True,
                      "extend": extend, "visible": True}
                up_lines.insert(0, ln)
                _drop_and_roll(up_lines)
            up_fractals.append(f)
        p_l = m - 1 - n
        if p_l >= 0 and p_l + n < N and _is_pivot(l, p_l, False):
            recent_dn2 = recent_dn1
            recent_dn1 = (p_l, l[p_l])
            f = {"bar": p_l, "time": t[p_l], "price": _clean(l[p_l]), "side": "down", "label": None}
            if recent_dn2 is not None:
                f["label"] = "HL" if l[p_l] > recent_dn2[1] else "LL"
                ln = {"side": "down",
                      "x1": recent_dn2[0], "t1": t[recent_dn2[0]], "y1": _clean(recent_dn2[1]),
                      "x2": p_l, "t2": t[p_l], "y2": _clean(l[p_l]),
                      "style": "recent", "color": TL_COLOR_RECENT, "dashed": True,
                      "extend": extend, "visible": True}
                dn_lines.insert(0, ln)
                _drop_and_roll(dn_lines)
            dn_fractals.append(f)

        # ---- الخط المُسقط عند هذه الشمعة (بالزوج السائد) + التقاطعات ----
        y_up = y_dn = None
        if recent_up1 is not None and recent_up2 is not None and recent_up1[0] != recent_up2[0]:
            m_up = (recent_up2[1] - recent_up1[1]) / (recent_up2[0] - recent_up1[0])
            y_up = m_up * m + recent_up1[1] - m_up * recent_up1[0]
            s_upper[m] = _clean(y_up)
        if recent_dn1 is not None and recent_dn2 is not None and recent_dn1[0] != recent_dn2[0]:
            m_dn = (recent_dn2[1] - recent_dn1[1]) / (recent_dn2[0] - recent_dn1[0])
            y_dn = m_dn * m + recent_dn1[1] - m_dn * recent_dn1[0]
            s_lower[m] = _clean(y_dn)

        if y_up is not None and _clean(c[m]) is not None:
            d = c[m] - y_up
            if prev_diff_up is not None:
                cross_over = d > 0 and prev_diff_up <= 0
                cross_under = d < 0 and prev_diff_up >= 0
                if cross_over or cross_under:
                    s_cross_upper[m] = True
                    crosses.append({"bar": m, "time": t[m], "type": "upper",
                                    "direction": "over" if cross_over else "under",
                                    "close": _clean(c[m]), "line_price": _clean(y_up), "color": "#6495ed"})
            prev_diff_up = d
        else:
            prev_diff_up = None

        if y_dn is not None and _clean(c[m]) is not None:
            d = c[m] - y_dn
            if prev_diff_dn is not None:
                cross_over = d > 0 and prev_diff_dn <= 0
                cross_under = d < 0 and prev_diff_dn >= 0
                if cross_over or cross_under:
                    s_cross_lower[m] = True
                    crosses.append({"bar": m, "time": t[m], "type": "lower",
                                    "direction": "over" if cross_over else "under",
                                    "close": _clean(c[m]), "line_price": _clean(y_dn), "color": "#ff7f50"})
            prev_diff_dn = d
        else:
            prev_diff_dn = None

    # ---- إسقاط الزوج الحالي حتى آخر شمعة ----
    def _projection(pair1, pair2) -> Optional[Dict[str, Any]]:
        if not pair1 or not pair2 or pair1[0] == pair2[0]:
            return None
        slope = (pair2[1] - pair1[1]) / (pair2[0] - pair1[0])
        return {"x1": pair1[0], "t1": t[pair1[0]], "y1": _clean(pair1[1]),
                "x2": pair2[0], "t2": t[pair2[0]], "y2": _clean(pair2[1]),
                "slope": _clean(slope), "y_last": _clean(slope * (N - 1) + pair1[1] - slope * pair1[0]),
                "extend": extend}

    return {
        "name": "Auto Trendline [DojiEmoji]",
        "params": {"period": n, "max_pairs": max_pairs, "extend": extend},
        "fractals": {"up": up_fractals, "down": dn_fractals},
        "lines": {"up": up_lines, "down": dn_lines},
        "projection": {"upper": _projection(recent_up2, recent_up1),
                       "lower": _projection(recent_dn2, recent_dn1)},
        "crosses": crosses,
        "series": {"tl_upper": s_upper, "tl_lower": s_lower,
                   "tl_cross_upper": s_cross_upper, "tl_cross_lower": s_cross_lower},
        "notes": "الفراكتال يُعرَف بعد period+1 شمعة (تأخير [1] مطابق). lines جديدة تُدرج أولاً؛ visible=false للما يتجاوز max_pairs (Pine يحذفها).",
    }


# ===========================================================================
# الموزّع الموحد — نقطة الدخل للمسارات والاستراتيجيات
# ===========================================================================
OVERLAY_TYPES = ("zigzag", "fib", "trendline")


def compute_overlays(
    candles: Any,
    types: Optional[Sequence[str]] = None,
    params: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """يحسب المؤشرات المطلوبة دفعة واحدة على نفس الشموع.

    types: قائمة من ("zigzag","fib","trendline") — الافتراضي الكل.
    params: {"zigzag": {...}, "fib": {...}, "trendline": {...}} — تمرير تجاوزات.
    """
    if types is None:
        types = list(OVERLAY_TYPES)
    wanted = {str(x).strip().lower() for x in types if str(x).strip()}
    wanted = wanted & set(OVERLAY_TYPES)
    params = params or {}

    t, o, h, l, c = _norm_candles(candles)
    N = len(c)
    out: Dict[str, Any] = {
        "bars": N,
        "time_from": t[0] if N else None,
        "time_to": t[-1] if N else None,
        "overlays": {},
    }
    if N == 0:
        return out

    if "zigzag" in wanted:
        zz_params = dict(params.get("zigzag") or {})
        out["overlays"]["zigzag"] = zigzag_channels(candles, **zz_params)
    if "fib" in wanted:
        fib_params = dict(params.get("fib") or {})
        out["overlays"]["fib"] = auto_fib_retracement(candles, **fib_params)
    if "trendline" in wanted:
        tl_params = dict(params.get("trendline") or {})
        out["overlays"]["trendline"] = auto_trendline(candles, **tl_params)

    return out
