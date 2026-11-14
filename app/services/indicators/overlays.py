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

# ✅ ROUND34 — المحرك الموحد: المصدر الوحيد للزقزاق/الفيبو/التطبيع.
# كل الأدوات المساعدة المحلية أصبحت أسماء مستعارة للنواة (نفس السلوك حرفياً)
# — لا نسخ مكررة بعد الآن في أي ملف.
from app.services.indicators.zigzag_fib_core import (  # noqa: F401
    ZIGZAG_FIB_CORE_SPEC,
    ZIGZAG_FIB_CORE_VERSION,
    build_ranges,
    clean_float as _clean,
    infer_price_tick as _infer_price_tick,
    level_tag as _level_tag,
    luxalgo_state_machine,
    norm_candles as _norm_candles,
    norm_volume as _norm_volume,
    range_levels_geometry,
    range_public,
    rolling_extreme as _rolling_extreme,
    zigzag_detect,
)

logger = logging.getLogger(__name__)

__all__ = [
    "zigzag_channels",
    "auto_fib_retracement",
    "auto_trendline",
    "zigzag_fib",
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
    # ✅ الجولة 12 (سياسة المستخدم الحرفية): النطاق المسموح [0, 1] حصراً —
    # كل مستويات الامتداد (> 1) غير مفعّلة افتراضياً ولا تُرسم ولا تُعاد،
    # ولا تُتاح إلا بتمريرها صراحة عبر params.level_ratios.
    (0.0,   True,  "#808080"),
    (0.236, True,  "#a61c00"),
    (0.382, True,  "#95cc28"),
    (0.5,   True,  "#28cc28"),
    (0.618, True,  "#28cc95"),
    (0.786, True,  "#2895cc"),
    (1.0,   True,  "#808080"),
    (1.272, False, "#82CA89"),
    (1.414, False, "#F32C42"),
    (1.618, False, "#2796ED"),
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

    # ✅ ROUND34 — الكشف عبر المحرك الموحد (نفس آلة الحالة حرفياً):
    # لا آلة زقزاق منفصلة هنا بعد اليوم — luxalgo_state_machine من النواة
    # هو نفسه المستخدم في zigzag_fib وE2E والترندية (مصدر حقيقة واحد).
    confirmed, s_state = luxalgo_state_machine(c, h, l, length)

    valtop: Optional[float] = None
    valbtm: Optional[float] = None
    top_n: Optional[int] = None   # شمعة تأكيد القمة
    btm_n: Optional[int] = None   # شمعة تأكيد القاع

    pivots: List[Dict[str, Any]] = []
    segments: List[Dict[str, Any]] = []

    s_pivot_high: List[Optional[float]] = [None] * N
    s_pivot_low: List[Optional[float]] = [None] * N

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

    # إعادة بناء نقاط/مقاطع الأصل من قائمة النقاط الموحدة (نفس الترتيب
    # والقيم — الأحداث تتناوب قاع/قمة فترتيبها في القائمة هو ترتيب حدوثها)
    for pv in confirmed:
        n = int(pv["confirmed_at_bar"])
        pivot_bar = int(pv["bar"])
        pp = pv["price"]
        if pv["kind"] == "bottom":
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
        else:
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

    os_state = s_state[-1] if N else None

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
    _explicit_levels = level_ratios is not None   # ✅ الجولة 12: سياسة [0,1]
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
            # ✅ الجولة 12 (سياسة حرفية من المستخدم): النطاق [0, 1] حصراً على
            # المسار الافتراضي — مستويات الامتداد تُرسم فقط إذا مُرّرت صراحة.
            if not _explicit_levels and not (0.0 <= float(ratio) <= 1.0):
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

    # ✅ الجولة 12.1 (بند 5-ب.1): out_of_range — المستويات المفعّلة خارج [0,1]
    # (الافتراضي مستويات [0,1] حصراً؛ الامتدادات صراحة عبر params تظهر هنا)
    _effective_ratios = sorted({round(float(_r), 6) for _r in (level_ratios or [r for r, _on, _c in FIB_DEFAULT_LEVELS if _on])})
    out_of_range = [r for r in _effective_ratios if r < 0.0 or r > 1.0]

    return {
        "name": "Auto Fib Retracement Alerts",
        "params": {"depth": depth, "dev_threshold": dev_threshold, "retracement": retracement,
                   "reverse": reverse, "extend_left": extend_left, "extend_right": extend_right},
        "legs": legs,
        "current": current,
        "signals": signals,
        "series": {"fib_start": s_start, "fib_end": s_end, "fib_target": s_target},
        "out_of_range": out_of_range,
        "notes": "visible=false للرجل السابقة (Pine يحذفها) وللرجل التركيبية الأولى (anchor من سعر 0). المستويات تُرسم من بداية الرجل الحالية ممتدة يميناً. ✅ الجولة 12: الافتراضي مستويات [0,1] حصراً — الامتدادات بتمرير صريح عبر params.level_ratios.",
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
# 4) ZigZag Fib Retracement (ZigZag-anchored) — الجولة 12
#    فيبو مركّب على الساق الأخيرة للزيجزاق — مطابق لمحرك الواجهة
#    (src/components/charts/overlays/zigzag-fib.ts)
# ===========================================================================
ZZFIB_DEFAULT_LEVELS: List[float] = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

# ✅ الجولة 13.2 (ZLF) — خط الانطلاقة المعتمد: 0.382 بمقياس المحرك.
# التبرير المصادق (ثلاث جهات): خط 0.618 في صور المستخدم مثبَّت بأسلوب معكوس
# (0 عند نهاية المسار) — وبمعادلة المحرك price(level) = p1 + diff × level
# يقابله 0.382 حرفياً (إثبات من صوره: 63,011.6+0.382×720.9=63,287.0
# و 53,223.5−0.382×3,668.4=51,822.2).
ZZF_LAUNCH_LEVEL: float = 0.382


def zigzag_fib(
    candles: Any,
    length: int = 100,
    reverse: bool = False,
    levels: Optional[Sequence[float]] = None,
    extend_right: bool = True,
    extend_leg_to_live: bool = True,
    touch_level: float = 0.618,
    liq_lookback: int = 20,
    liq_signals: bool = True,
    liq_arm_bars: int = 60,
    liq_sfp_signals: bool = False,
    mode: str = "luxalgo",
    depth: int = 12,
    deviation: float = 20.0,
    backstep: int = 3,
) -> Dict[str, Any]:
    """فيبو تصحيحي مبني على الساق الأخيرة للزيجزاق (بلا أي ثبات تاريخي).

    ✅ الجولة 19 (ROUND19) — وضعا الزقزاق (معامل mode):
      "tradingview" — زقزاق MT4/TV الكلاسيكي (Depth/Deviation/Backstep على
         high/low — بتمريرتين وآلة تناوب بإحلال الطرف الأقوى):
           depth     : نافذة القصوى حول الطرف (TV الافتراضي 12)
           deviation : عتبة الانحراف بوحدات TV (أعشار المئة): 20 ⇒ 2.0% · 5 ⇒ 0.5% ·
                       100 ⇒ 10% — نسبية من سعر الطرف لتعمل على كل الرموز
           backstep  : أقل مسافة بين طرفين من نفس النوع (TV الافتراضي 3)
         الأطراف تقع على القصوى الحقيقية (high/low) — نفس شكل TV البصري.
         السببية: confirmed_at_bar = شمعة قبول/إحلال الطرف (تُعرف عند إغلاق
         شمعتها)؛ قيم الشمعة n لا تُعاد كتابة أبداً — الإحلال يقع على شموع لاحقة
         فقط. الساق المرجعية عند كل شمعة = آخر طرفين مقبولين عندها (نفس ما
         يعرضه TV — بما فيه الطرف الحي قبل تأكيده بالانعكاس).
      "luxalgo"  — السلوك التاريخي حرفياً (نافذة إغلاقات length — الافتراضي
         للتوافق الرجعي؛ الكشف على الإغلاقات والتأكيد بعد length شمعة).
    المعاملات المشتركة للوضعين: reverse/levels/extend_right/extend_leg_to_live/
    touch_level/liq_* — السيولة (S1/S2/S3) والانطلاقة والخطة البديلة لا تتغير؛
    الوضع يغيّر مصدر قمم/قيعان الساق المرجعية فقط.

    المطابقة حرفية مع الواجهة (وضع luxalgo):
      1) كشف القمم/القيعان = نفس خوارزمية zigzag_channels (LuxAlgo) حرفياً:
         upper = highest(close, length); lower = lowest(close, length)
         os := close[length] > upper ? 0 : close[length] < lower ? 1 : os[1]
         القمة/القاع تُؤكَّد بعد `length` شمعة (confirmed_at_bar) — بلا repaint.
      2) الساق = آخر نقطتين متعاكستين مؤكدتين: a = pivots[-2] و b = pivots[-1]
         (الزيجزاق يتناوب top/btm دائماً).
      3) p1 = a.price و p2 = b.price (و reverse يبدّلهما) — الاتجاه up إذا p1 < p2.
      4) المستويات: price(level) = p1 + diff × level
         حيث diff = (p1 > p2 ? -1 : +1) × |p1 - p2|.
      5) التمديد الحي: القيم تُعاد عند كل شمعة — الساق تتحرك مع كل قمة/قاع جديد.

    السلاسل سببية 100% (causal): قيم الشمعة n مبنية من النقاط التي تأكدت عند n فقط.

    ind_zzf_touch: +1 أول لمس للمستوى الهدف (0.618) في ساق صاعدة (نطاق الشمعة
    يحتوي المستوى low <= lvl <= high) و -1 عكسها في الهابطة — لمس واحد فقط لكل
    ساق، وتُعاد التسليح عند تغيّر الساق (أول لمس فقط / re-arm on leg change).

    ✅ الجولة 13.2 (ZLF v13.2 — المصفوفة المصادقة من ثلاث جهات: قراءة الوكيلين
    + تصديق المستخدم — إعادة تعريف الإشارات الثلاث حرفياً حسب نص الصور):

    R (مرجع السيولة) = الشمعة صاحبة أكبر حجم في النافذة [i − liq_lookback, i − 1]
    (قبيل الشمعة الحالية — سببية 100%) بشرط أن تكون حمراء (close < open) —
    «أكبر بار سيولة أحمر حجمًا». إن كانت أكبر شمعة في النافذة خضراء → لا مرجع
    (state 0) · ولا مرجع إطلاقاً → state 0.
    ref_high = أعلى high لشمعة حمراء داخل النافذة نفسه (ليس بالضرورة قمة R) —
    محور «الاختراق» الموحد للحالات الثلاث.
    G (شمعة الإشارة) = خضراء (close > open) وتحقق شرطين مشتركين:
      1) الانطلاقة: low_G ≥ price(0.382) لآخر ساق زيجزاق مؤكدة (أي اتجاه).
         (خط 0.618 بمقياس المستخدم — 0 عند نهاية المسار — = price(0.382)
         بمعادلة المحرك price(level) = p1 + diff × level.)
      2) هيمنة الخضراء: volume_G > حجم كل الشموع الخضراء الواقعة حصرياً
         بين R وG (لا R ولا G ضمن المقارنة).
    المصفوفة (تقسيم كامل — التقسيم بعلاقة الحجم مع الحمراء لا بالإغلاق):
      S1 — الحالة الأولى: high_G > ref_high  و  volume_G > volume_R
      S2 — الحالة الثانية: high_G > ref_high  و  volume_G ≤ volume_R
      S3 — الحالة الثالثة: high_G ≤ ref_high  و  volume_G > volume_R
      الرابعة (لا اختراق + حجم أقل) = لا إشارة عمداً (ضوضاء).
    الدخول = عند شمعة الإشارة نفسها (الحدث = الدخول؛ التقييم عند إغلاق شمعة
    الإشارة والتنفيذ عند افتتاح التالية — fill next_open روح البطل)، على أي
    اتجاه لآخر ساق مؤكدة (أُلغي اشتراط الساق الصاعدة — الصورة الثالثة مرسومة
    على ساق هابطة). خطة بديلة وحيدة: إن لم تكن الساق مؤكدة بعد لحظة الحدث
    يُسلَّح الحدث ويدخل عند أول شمعة تحقق شرط الانطلاقة خلال liq_arm_bars
    (FIFO: أقدم حدث مسلَّح أولاً — كل دخول يحمل اسم إشارته الواحدة).
    SFP (اختيارية — مطفأة افتراضياً بـ liq_sfp_signals=False): إشارة رابعة
    «اختراق كاذب» = اختراق بالضلع لكن الإغلاق رجع تحت ref_high بحجم أكبر —
    تستبدل S1 على شمعتها حين تُفعَّل (لا تضاعف إشارة أبداً) حتى لا تلوث
    decision_reason. مطفأة افتراضياً = لا ذكر لها إطلاقاً في أي مخرجات.
    ملاحظة زمنية مهمة: مع length كبير (مثل 100) تتأكد نقطة الزيجزاق بعد length
    شمعة — لذا قد يسبق الحدث السيولي تأكيد الساق؛ عندها يعمل مسار التسليح
    (الخطة البديلة). على فريم الدقيقة يُنصح برفع liq_lookback (مثل 240) لتغطية
    النطاق المرسوم.
    """
    t, o, h, l, c = _norm_candles(candles)
    N = len(c)
    length = max(2, int(length))
    lvls = [float(x) for x in (levels if levels is not None else ZZFIB_DEFAULT_LEVELS)]
    try:
        touch_target = float(touch_level)
    except (TypeError, ValueError):
        touch_target = 0.618
    try:
        liq_w = max(1, int(liq_lookback))
    except (TypeError, ValueError):
        liq_w = 20
    try:
        liq_arm = max(1, int(liq_arm_bars))
    except (TypeError, ValueError):
        liq_arm = 60
    liq_enabled = bool(liq_signals)
    sfp_enabled = bool(liq_sfp_signals) and liq_enabled
    vols = _norm_volume(candles) if liq_enabled else []
    if liq_enabled and len(vols) != N:
        vols = [None] * N

    # --- 1) كشف النقاط + أرجل الرسم — ✅ ROUND34: المحرك الموحد (وضعان) ---
    _lv_keys_pre = [(r, f"zzf_level_{_level_tag(r)}") for r in lvls]
    _det = zigzag_detect(
        t, o, h, l, c, N,
        mode=mode, length=length, depth=depth, deviation=deviation,
        backstep=backstep, reverse=reverse, lv_keys=_lv_keys_pre,
        touch_target=touch_target, want_series=True, want_touch=True,
    )
    confirmed = _det["confirmed"]
    legs = _det["legs"]

    # --- ✅ الجولة 13.2 (ZLF v13.2) — المصفوفة المصادقة (سببية 100%) ---
    # R = أكبر حجم في [i−liq_w, i−1] بشرط أن يكون أحمر (close<open) — وإلا لا مرجع.
    # ref_high = أعلى قمة حمراء داخل النافذة (محور الاختراق الموحد).
    # G = خضراء + انطلاقة (low ≥ price(0.382)) + هيمنة الخضراء الحصرية بين R وG.
    # S1 = اختراق ∧ حجم أكبر · S2 = اختراق ∧ حجم أقل أو مساوٍ · S3 = رفض ∧ حجم أكبر
    # · الرابعة = لا إشارة. الدخول بشمعة الحدث نفسها، والخطة البديلة = التسليح.
    s_entry: List[float] = [0.0] * N
    signals: List[Dict[str, Any]] = []
    liq_state: List[float] = [0.0] * N
    liq_ref_high: List[Optional[float]] = [None] * N
    liq_ref_vol: List[Optional[float]] = [None] * N
    liq_vol_ok: List[float] = [0.0] * N
    liq_s1: List[float] = [0.0] * N
    liq_s2: List[float] = [0.0] * N
    liq_s3: List[float] = [0.0] * N
    liq_any: List[float] = [0.0] * N
    liq_sfp: List[float] = [0.0] * N           # اختيارية — أصفار دائماً افتراضياً
    liq_entry_s1: List[float] = [0.0] * N
    liq_entry_s2: List[float] = [0.0] * N
    liq_entry_s3: List[float] = [0.0] * N
    liq_entry_sfp: List[float] = [0.0] * N     # اختيارية
    liq_events = 0
    liq_same_candle_entries = 0
    liq_fallback_entries = 0

    # أرجل لكل شمعة (سببية): آخر نقطتين مؤكدتين عند كل شمعة — لشرط الانطلاقة.
    # ✅ ROUND34: من المحرك الموحد (وضعا tradingview/luxalgo بنفس الدلالة).
    _ser = _det["series"]
    leg_ready = _ser["leg_ready"]
    leg_p1_arr = _ser["leg_p1"]
    leg_diff_arr = _ser["leg_diff"]

    if liq_enabled:
        dq_all: deque = deque()   # monotonic تنازلي بالحجم (كل الشموع) — front = أكبر حجم بالنافذة
        dq_red: deque = deque()   # monotonic تنازلي بالقمة (الحمراء فقط) — front = أعلى قمة حمراء بالنافذة
        # التسليح (الخطة البديلة الوحيدة): خانة لكل إشارة — S1/S2/S3 (+SFP اختيارية)
        cell_names = ("S1", "S2", "S3", "SFP")
        sig_cols = (liq_s1, liq_s2, liq_s3, liq_sfp)
        ent_cols = (liq_entry_s1, liq_entry_s2, liq_entry_s3, liq_entry_sfp)
        n_slots = 4 if sfp_enabled else 3
        pending = [0] * n_slots        # 1 = حدث مسلَّح بانتظار تأكد الساق/الانطلاقة
        pending_arm = [-1] * n_slots   # شمعة الحدث المسلِّح (انتهاء الصلاحية = arm + liq_arm)

        def _candle_red(j: int) -> bool:
            oj, cj = _clean(o[j]), _clean(c[j])
            return oj is not None and cj is not None and cj < oj

        def _candle_green(j: int) -> bool:
            oj, cj = _clean(o[j]), _clean(c[j])
            return oj is not None and cj is not None and cj > oj

        for i in range(N):
            # 1) إسقاط ما خرج من النافذة [i−liq_w, i−1]
            while dq_all and dq_all[0] < i - liq_w:
                dq_all.popleft()
            while dq_red and dq_red[0] < i - liq_w:
                dq_red.popleft()

            # 2) قراءة المرجع R — فقط بعد اكتمال النافذة (i >= liq_w)
            have_ref = False
            ref_idx = -1
            ref_h: Optional[float] = None
            ref_v: Optional[float] = None
            if i >= liq_w and dq_all:
                cand = dq_all[0]
                # ✅ v13.2: أكبر شمعة يجب أن تكون حمراء — أكبر شمعة خضراء → لا مرجع (V5)
                if _candle_red(cand):
                    ref_idx = cand
                    ref_h = _clean(h[dq_red[0]]) if dq_red else None
                    ref_v = _clean(vols[cand])
                    if ref_h is not None and ref_v is not None:
                        have_ref = True
            hi_n, lo_n, c_n, o_n = _clean(h[i]), _clean(l[i]), _clean(c[i]), _clean(o[i])
            v_n = _clean(vols[i]) if i < len(vols) else None

            if have_ref:
                liq_ref_high[i] = ref_h
                liq_ref_vol[i] = ref_v
                if v_n is not None:
                    # vol_ok = علاقة الحجم الخام مع المرجع (> مطلوب في S1/S3 · ≤ يمنح S2)
                    liq_vol_ok[i] = 1.0 if v_n > ref_v else 0.0

            # 3) G — ✅ ROUND35 (قرار المالك #R68): لا مانع من نوع الشمعة:
            #    الدوجي/الحمراء مؤهلة للإشارة ما دامت تملك سيولة وتصرخ صعوداً.
            #    «الخضراء» بمفهوم الاستراتيجية = شمعة بمنطقنا، لا لونها. الهيمنة
            #    (خطوة 4) تظل تقارن بالخضراء الصريحة فقط.
            signal_ok = c_n is not None and o_n is not None
            cell = 0
            if have_ref and signal_ok and v_n is not None and hi_n is not None:
                breakout = hi_n > ref_h
                vol_dom = v_n > ref_v
                if breakout and vol_dom:
                    cell = 1
                    # ✅ SFP الاختيارية (مطفأة افتراضياً): اختراق بالضلع لكن الإغلاق
                    # رجع تحت القمة بحجم أكبر — تستبدل S1 على شمعتها (لا تضاعف إشارة).
                    if sfp_enabled and c_n is not None and c_n <= ref_h:
                        cell = 4
                elif breakout:
                    cell = 2
                elif vol_dom:
                    cell = 3
                # الرابعة (لا اختراق + حجم أقل) = لا إشارة عمداً — state يبقى 0
                liq_state[i] = float(cell) if cell else 0.0
            elif have_ref:
                liq_state[i] = 0.0

            # 4) هيمنة الخضراء: volume_G > حجم كل الخضراء حصرياً بين R وG (V4/V8)
            if cell:
                dominant = True
                for j in range(ref_idx + 1, i):
                    if _candle_green(j):
                        vj = _clean(vols[j]) if j < len(vols) else None
                        if vj is not None and vj >= v_n:
                            dominant = False
                            break
                if not dominant:
                    cell = 0   # خضراء أكبر بينها وبين المرجع → لا إشارة

            # 5) الانطلاقة: low_G ≥ price(0.382) لآخر ساق مؤكدة (أي اتجاه)
            launch_line: Optional[float] = None
            launch_ok = False
            if cell and leg_ready[i]:
                launch_line = leg_p1_arr[i] + leg_diff_arr[i] * ZZF_LAUNCH_LEVEL
                if lo_n is not None and lo_n >= launch_line:
                    launch_ok = True

            # 6) الحدث → دخول فوري بشمعة الحدث (المثالي: الحدث = الدخول)
            #    أو تسليح إن لم تكن الساق مؤكدة لحظة الحدث (الخطة البديلة الوحيدة).
            slot = cell - 1 if cell else -1
            if cell and (launch_ok or not leg_ready[i]):
                liq_events += 1
                sig_cols[slot][i] = 1.0
                liq_any[i] = 1.0
                signals.append({
                    "bar": i, "time": t[i], "side": "liquidity",
                    "signal": "ZLF Liquidity %s" % cell_names[slot],
                    "states": [slot + 1], "state": float(cell),
                    "ref_high": ref_h, "ref_vol": ref_v,
                    "price": hi_n if cell in (1, 2, 4) else c_n,
                    "volume": v_n,
                    "launch_line": launch_line,
                })
                if launch_ok:
                    ent_cols[slot][i] = 1.0
                    s_entry[i] = 1.0
                    liq_same_candle_entries += 1
                    signals.append({
                        "bar": i, "time": t[i], "side": "buy",
                        "signal": "ZLF Entry %s" % cell_names[slot],
                        "states": [slot + 1],
                        "price": c_n, "launch_line": launch_line,
                        "fallback": False, "color": "#28cc95",
                    })
                else:
                    pending[slot] = 1
                    pending_arm[slot] = i

            # 7) الخطة البديلة: أول شمعة تحقق الانطلاقة خلال النافذة (FIFO —
            #    أقدم حدث مسلَّح أولاً، وكل دخول يحمل اسم إشارته الواحدة).
            if not (cell and launch_ok) and leg_ready[i] and lo_n is not None:
                fb_line = leg_p1_arr[i] + leg_diff_arr[i] * ZZF_LAUNCH_LEVEL
                if lo_n >= fb_line:
                    alive = [k for k in range(n_slots)
                             if pending[k] and i <= pending_arm[k] + liq_arm]
                    if alive:
                        k0 = min(alive, key=lambda k: (pending_arm[k], k))
                        ent_cols[k0][i] = 1.0
                        s_entry[i] = 1.0
                        pending[k0] = 0
                        liq_fallback_entries += 1
                        signals.append({
                            "bar": i, "time": t[i], "side": "buy",
                            "signal": "ZLF Entry %s" % cell_names[k0],
                            "states": [k0 + 1],
                            "price": c_n, "launch_line": fb_line,
                            "fallback": True, "color": "#28cc95",
                        })

            # 8) دفع الشمعة الحالية للمرشحين (التعادل: الأحدث يفوز)
            v_cur = _clean(vols[i]) if i < len(vols) else None
            if v_cur is not None:
                while dq_all and (_clean(vols[dq_all[-1]]) is not None and _clean(vols[dq_all[-1]]) <= v_cur):
                    dq_all.pop()
                dq_all.append(i)
            if hi_n is not None and _candle_red(i):
                while dq_red and (_clean(h[dq_red[-1]]) is not None and _clean(h[dq_red[-1]]) <= hi_n):
                    dq_red.pop()
                dq_red.append(i)

    # --- 2..5) سلاسل لكل شمعة (causal) — ✅ ROUND34: من المحرك الموحد ---
    # (الوضعان بنفس الدلالة التاريخية: tradingview بُنيت داخل التمريرة
    # التتابعية وluxalgo عبر المسح السببي — كلاهما من نواة واحدة الآن)
    lv_keys = [(r, f"zzf_level_{_level_tag(r)}") for r in lvls]
    s_dir = _ser["s_dir"]
    s_p1 = _ser["s_p1"]
    s_p2 = _ser["s_p2"]
    s_i1 = _ser["s_i1"]
    s_i2 = _ser["s_i2"]
    level_series = _ser["level_series"]
    s_touch = _ser["s_touch"]
    signals.extend(_ser["touch_signals"])

    # --- حالة الساق الحالية + مستوياتها (ما يُرسم الآن) ---
    current: Optional[Dict[str, Any]] = None
    if len(confirmed) >= 2:
        a, b = confirmed[-2], confirmed[-1]
        p1, p2 = (b["price"], a["price"]) if reverse else (a["price"], b["price"])
        if p1 is not None and p2 is not None:
            diff = (-1.0 if p1 > p2 else 1.0) * abs(p1 - p2)
            last_bar = N - 1
            lv = []
            for r in lvls:
                x_to = last_bar if extend_right else b["bar"]
                lv.append({
                    "ratio": r, "tag": _level_tag(r),
                    "value": _clean(p1 + diff * r),
                    "x_from": a["bar"], "t_from": t[a["bar"]],
                    "x_to": x_to, "t_to": t[x_to] if 0 <= x_to < N else None,
                    "extend_right": extend_right,
                })
            current = {
                "leg": legs[-1] if legs else None,
                "levels": lv,
                "target": {"ratio": touch_target, "value": _clean(p1 + diff * touch_target)},
                "p1": _clean(p1), "p2": _clean(p2),
                "dir": 1.0 if p1 < p2 else -1.0,
                "i1": a["bar"], "i2": b["bar"],
                "live_extension": {
                    "enabled": extend_leg_to_live,
                    "x1": b["bar"], "t1": t[b["bar"]], "y1": _clean(p2),
                    "x2": last_bar, "t2": t[last_bar], "y2": _clean(c[last_bar]),
                },
            }

    # ✅ الجولة 12.1 (بند 5-ب.1): out_of_range — المستويات المفعّلة خارج [0,1]
    _effective_ratios_zf = sorted({round(float(_r), 6) for _r in lvls})
    out_of_range_zf = [r for r in _effective_ratios_zf if r < 0.0 or r > 1.0]

    # ✅ v13.2: ترتيب الإشارات زمنياً (أحداث السيولة حُسبت في مرور مستقل)
    signals.sort(key=lambda s: s.get("bar", 0))

    _zf_series: Dict[str, List[Optional[float]]] = {
        "zzf_dir": s_dir, "zzf_p1": s_p1, "zzf_p2": s_p2,
        "zzf_i1": s_i1, "zzf_i2": s_i2,
        **level_series,
        "zzf_touch": s_touch,
        # ✅ الجولة 13.2 (ZLF v13.2) — الأعمدة الـ12 بدلالات المصفوفة المصادقة
        "zzf_liq_state": liq_state,
        "zzf_liq_ref_high": liq_ref_high,
        "zzf_liq_ref_vol": liq_ref_vol,
        "zzf_liq_vol_ok": liq_vol_ok,
        "zzf_signal_s1": liq_s1,
        "zzf_signal_s2": liq_s2,
        "zzf_signal_s3": liq_s3,
        "zzf_signal_any": liq_any,
        "zzf_entry": s_entry,
        "zzf_entry_s1": liq_entry_s1,
        "zzf_entry_s2": liq_entry_s2,
        "zzf_entry_s3": liq_entry_s3,
    }
    if sfp_enabled:
        # أعمدة امتداد اختيارية خارج عقد الأعمدة الـ25 — تظهر فقط عند التفعيل
        _zf_series["zzf_signal_sfp"] = liq_sfp
        _zf_series["zzf_entry_sfp"] = liq_entry_sfp

    return {
        "name": "ZigZag Fib Retracement (ZigZag-anchored)",
        "params": {"mode": mode, "length": length, "reverse": reverse, "levels": lvls,
                   "extend_right": extend_right, "extend_leg_to_live": extend_leg_to_live,
                   "touch_level": touch_target,
                   "depth": depth, "deviation": deviation, "backstep": backstep,
                   "liq_lookback": liq_w, "liq_signals": liq_enabled,
                   "liq_arm_bars": liq_arm, "liq_sfp_signals": sfp_enabled},
        "legs": legs,
        "current": current,
        "signals": signals,
        "series": _zf_series,
        "liquidity": {
            "enabled": liq_enabled,
            "spec": "v13.2",
            "lookback": liq_w,
            "events": liq_events,
            "entries_same_candle": liq_same_candle_entries,
            "entries_fallback": liq_fallback_entries,
            "reference_rule": "R = الشمعة صاحبة أكبر حجم في [i−lookback, i−1] بشرط أنها حمراء (close<open) — أكبر شمعة خضراء → لا مرجع (state 0)",
            "ref_high_rule": "ref_high = أعلى high لشمعة حمراء داخل النافذة نفسه — محور الاختراق الموحد للحالات الثلاث",
            "states": {
                "1": "S1 — الحالة الأولى: اختراق قمة الحمراء بحجم أكبر (high>ref_high و volume>volume_R)",
                "2": "S2 — الحالة الثانية: اختراق قمة الحمراء بحجم أقل أو مساوٍ (high>ref_high و volume≤volume_R) — «ويبرغم عندها لفل حجم سيولتها من شمعة أكبر بار سيولة أحمر حجمًا»",
                "3": "S3 — الحالة الثالثة: رفض بلا اختراق بحجم أكبر (high≤ref_high و volume>volume_R)",
                **({"4": "SFP (اختيارية) — اختراق بالضلع وإغلاق رجع تحت القمة بحجم أكبر — تستبدل S1 على شمعتها"} if sfp_enabled else {}),
            },
            "common_conditions": [
                "G خضراء (close>open)",
                "الانطلاقة: low_G ≥ price(0.382) لآخر ساق مؤكدة (أي اتجاه) — خط 0.618 بمقياس المستخدم (0 عند نهاية المسار) = price(0.382) بمقياس المحرك",
                "هيمنة الخضراء: volume_G > حجم كل الشموع الخضراء الواقعة حصرياً بين R وG (لا R ولا G ضمن المقارنة)",
            ],
            "excluded_cell": "الخلية الرابعة (لا اختراق + حجم أقل) = لا إشارة عمداً (ضوضاء)",
            "volume_rule": "S1/S3: volume_G > volume_R · S2: volume_G ≤ volume_R (تقسيم بعلاقة الحجم مع الحمراء لا بالإغلاق)",
            "entry_rule": "الدخول عند شمعة الإشارة نفسها (الحدث = الدخول؛ تقييم عند الإغلاق وتنفيذ عند افتتاح التالية — next_open) على أي اتجاه للساق المؤكدة؛ خطة بديلة وحيدة: إن لم تكن الساق مؤكدة لحظة الحدث → أول شمعة تحقق الانطلاقة خلال liq_arm_bars (FIFO: أقدم حدث مسلَّح أولاً)",
            "launch_level": ZZF_LAUNCH_LEVEL,
            "arm_bars": liq_arm,
            "sfp_enabled": sfp_enabled,
        },
        "out_of_range": out_of_range_zf,
        "notes": "مطابق لمحرك الواجهة zigzag-fib.ts: كشف النقاط بنفس خوارزمية zigzag_channels "
                 "(تأكيد بعد length شمعة)، الساق = آخر نقطتين متعاكستين، والمستويات تُعاد عند كل شمعة. "
                 "zzf_touch: أول لمس للمستوى الهدف في الساق (إعادة تسليح عند تغيّر الساق) — عقد الجولة 12 بلا تغيير. "
                 "✅ الجولة 13.2 (ZLF v13.2 — المصفوفة المصادقة): R = أكبر حجم أحمر بالنافذة، ref_high = أعلى قمة حمراء، "
                 "G = خضراء + انطلاقة price(0.382) + هيمنة الخضراء الحصرية، S1/S2/S3 بعلاقة الحجم مع الحمراء، "
                 "الدخول بشمعة الحدث نفسها (أو الخطة البديلة)، وSFP إشارة رابعة اختيارية مطفأة افتراضياً.",
    }


# ===========================================================================
# الموزّع الموحد — نقطة الدخل للمسارات والاستراتيجيات
# ===========================================================================
OVERLAY_TYPES = ("zigzag", "fib", "trendline", "zzfib",
                 "zzfib_e2e",  # ✅ ROUND22: ZLF-End-To-End — المحرك المنفصل الجديد (إضافة تسجيل فقط — لا تغيير على الأربعة الأصليين)
                 # ✅ ROUND32: «الزقزاق البطل e2e الترنديه» — الاستنساخ المعزول ببوابة الترند
                 # + مؤشر الترند المستقل (فراكتالات Pine Auto Trendline — يرسل إحداثياته
                 # للباك اند ويحسب محرك الاستراتيجية الإشارة منها) — إضافة تسجيل فقط.
                 "zzfib_e2e_trendy",
                 # 🔥 R69: «الترندية الملتهبة» (ZLF-End-To-End-Blazing) — الترندية بت-بت
                 # + إشارتا R68 المُقاستان N5 «إشعال بلا مرجع» وN6 «الاختراق الهادئ» —
                 # محرك معزول جديد كلياً (أسماء zzfb_*) — إضافة تسجيل فقط، لا مساس بأي قائم.
                 "zzfib_e2e_blazing",
                 # ✅ PRO73: «الترندية الماكدية» — الترندية بت-بت + مصفوفة موشرات
                 # RSI/MACD/Momentum متعددة النسخ/الفريمات (14 فريماً) + بوابة شروط
                 # قابلة للتركيب (and/or/not بأي عمق) — محرك معزول جديد كلياً.
                 "zzfib_e2e_trendy_macd",
                 # 🔥 PRO73: «الملتهبة الماكدية» — الملتهبة بت-بت (S1/S2/S3 + N5/N6)
                 # + نفس مصفوفة الموشرات والبوابة القابلة للتركيب — محرك معزول جديد كلياً.
                 "zzfib_e2e_blazing_macd",
                 "trend_fractal")


def _normalize_overlay_params(base: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """✅ الجولة 12.1: توحيد أسماء المعاملات مع صيغة الواجهة الحرفية.

    الوكيل الواجهة يرسل (نصاً في أوامر القبول):
      params.fib.levels / params.zzfib.levels — والنمط الداخلي للدوال
      level_ratios (المطابق للسكربت Pine). كنا نُعيد 500
      "unexpected keyword argument 'levels'" عند أي تمرير حرفي.
    المرادفات المقبولة (الأولوية للصيغة الداخلية):
      levels / level_ratios → level_ratios
      length / depth        → depth (fib)
      length                → length (zigzag/zzfib كما هي)
    """
    out = dict(raw or {})
    if "levels" in out and "level_ratios" not in out:
        out["level_ratios"] = out.pop("levels")
    if base == "fib" and "length" in out and "depth" not in out:
        out["depth"] = out.pop("length")
    # مرشّح المفاتيح غير المعروفة للدالة (بصمت بدل 500) — احتياط توافق
    known = {
        "fib": {"depth", "dev_threshold", "retracement", "level_ratios",
                "level_visibility", "reverse", "extend_left", "extend_right"},
        # ✅ v13.2: أُضيف liq_arm_bars (كان يُفلتر بصمت في 13.1 — عيب كامن أُصلح)
        # و liq_sfp_signals (الإشارة الرابعة الاختيارية مطفأة افتراضياً).
        # ✅ ROUND19: وضع زقزاق TradingView — mode/depth/deviation/backstep.
        "zzfib": {"length", "reverse", "levels", "extend_right",
                  "extend_leg_to_live", "touch_level", "level_ratios",
                  "liq_lookback", "liq_signals", "liq_arm_bars", "liq_sfp_signals",
                  "mode", "depth", "deviation", "backstep"},
        # ✅ ROUND22: ZLF-End-To-End — المحرك المنفصل (نفس معاملات الزقزاق
        # + launch_touch_ticks؛ لا liq_* — النطاق يعتمد لحظة ظهور الزقزاق
        # ونافذة الحساب = عمر النطاق، لا نافذة منزلقة بعدد شموع).
        "zzfib_e2e": {"length", "reverse", "levels", "extend_right",
                      "extend_leg_to_live", "mode", "depth", "deviation",
                      "backstep", "launch_touch_ticks"},
        # ✅ ROUND32: الترندية — نفس معاملات E2E + قوالب الترند الثلاثة
        # (الفترات/الإجماع/الأنواع المبوّبة — كلها قالبية بلا أرقام داخل الكود).
        "zzfib_e2e_trendy": {"length", "reverse", "levels", "extend_right",
                             "extend_leg_to_live", "mode", "depth", "deviation",
                             "backstep", "launch_touch_ticks",
                             "trend_periods", "trend_confirm", "trend_gate"},
        # 🔥 R69: الملتهبة — نفس معاملات الترندية حرفياً (بوابة ترند قبل s1/s2/s3/n5/n6).
        "zzfib_e2e_blazing": {"length", "reverse", "levels", "extend_right",
                              "extend_leg_to_live", "mode", "depth", "deviation",
                              "backstep", "launch_touch_ticks",
                              "trend_periods", "trend_confirm", "trend_gate"},
        # ✅ PRO73: الترندية الماكدية — نفس معاملات الترندية + قالبا الموشرات
        # (osc_instances: نسخ rsi/macd/mom بأي عدد و14 فريماً · osc_conditions:
        # شجرة and/or/not قابلة للتركيب — كلاهما يُمرّر كما هو للمحرك).
        "zzfib_e2e_trendy_macd": {"length", "reverse", "levels", "extend_right",
                                  "extend_leg_to_live", "mode", "depth", "deviation",
                                  "backstep", "launch_touch_ticks",
                                  "trend_periods", "trend_confirm", "trend_gate",
                                  "osc_instances", "osc_conditions"},
        # 🔥 PRO73: الملتهبة الماكدية — نفس معاملات الملتهبة + القالبان نفسيهما.
        "zzfib_e2e_blazing_macd": {"length", "reverse", "levels", "extend_right",
                                   "extend_leg_to_live", "mode", "depth", "deviation",
                                   "backstep", "launch_touch_ticks",
                                   "trend_periods", "trend_confirm", "trend_gate",
                                   "osc_instances", "osc_conditions"},
        # ✅ ROUND32: مؤشر الترند المستقل (فراكتالات Pine) — فترات قالبية بأي طول.
        "trend_fractal": {"periods", "confirm_mode"},
        "zigzag": {"length", "extend_right"},
        "trendline": {"period", "max_pairs"},
    }
    if base in known:
        # zzfib يقبل levels أصلاً كاسم رسمي — لا نحذفه
        allow = known[base] | ({"levels"} if base == "zzfib" else set())
        out = {k: v for k, v in out.items() if k in allow}
    return out


def compute_overlays(
    candles: Any,
    types: Optional[Sequence[str]] = None,
    params: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """يحسب المؤشرات المطلوبة دفعة واحدة على نفس الشموع.

    types: قائمة من ("zigzag","fib","trendline","zzfib") — الافتراضي الكل.
    params: {"zigzag": {...}, "fib": {...}, "trendline": {...}, "zzfib": {...}}.
    """
    _default_all = types is None
    if types is None:
        types = list(OVERLAY_TYPES)
    wanted = {str(x).strip().lower() for x in types if str(x).strip()}
    wanted = wanted & set(OVERLAY_TYPES)
    params = params or {}

    # ✅ PRO73 — حماية أداء مسار «كل الأنواع» الافتراضي: محركات الماكدية
    # بلا قالب موشرات (osc_instances/osc_conditions) = وضع الهوية (مرآة
    # الترندية/الملتهبة بت-بت). في طلب «الكل» الافتراضي تكون مجرد مضاعفة
    # حساب بلا أي بيانات جديدة — نتجاوزها (طلبها الصريح — مع قالب أو بدونه —
    # يحسبها دائماً).
    if _default_all:
        for _b in ("zzfib_e2e_trendy_macd", "zzfib_e2e_blazing_macd"):
            _p = params.get(_b) or {}
            if not (_p.get("osc_instances") or _p.get("osc_conditions")):
                wanted.discard(_b)

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
        zz_params = _normalize_overlay_params("zigzag", params.get("zigzag") or {})
        out["overlays"]["zigzag"] = zigzag_channels(candles, **zz_params)
    if "fib" in wanted:
        fib_params = _normalize_overlay_params("fib", params.get("fib") or {})
        out["overlays"]["fib"] = auto_fib_retracement(candles, **fib_params)
    if "trendline" in wanted:
        tl_params = _normalize_overlay_params("trendline", params.get("trendline") or {})
        out["overlays"]["trendline"] = auto_trendline(candles, **tl_params)
    if "zzfib" in wanted:
        zzf_params = _normalize_overlay_params("zzfib", params.get("zzfib") or {})
        out["overlays"]["zzfib"] = zigzag_fib(candles, **zzf_params)
    if "zzfib_e2e" in wanted:
        # ✅ ROUND22: ZLF-End-To-End — استدعاء مؤجل للملف المنفصل
        # (استنساخ مستقل — لا يعتمد على هذا الملف ولا يعدّل عليه).
        from app.services.indicators.overlays_zlf_e2e import zigzag_fib_e2e
        e2e_params = _normalize_overlay_params("zzfib_e2e", params.get("zzfib_e2e") or {})
        out["overlays"]["zzfib_e2e"] = zigzag_fib_e2e(candles, **e2e_params)
    if "zzfib_e2e_trendy" in wanted:
        # ✅ ROUND32: «الزقزاق البطل e2e الترنديه» — استدعاء مؤجل للاستنساخ
        # المعزول (E2E حرفياً + بوابة الترند القالبية) — بلا أي مساس بالأصل.
        from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy
        trendy_params = _normalize_overlay_params("zzfib_e2e_trendy", params.get("zzfib_e2e_trendy") or {})
        out["overlays"]["zzfib_e2e_trendy"] = zigzag_fib_e2e_trendy(candles, **trendy_params)
    if "zzfib_e2e_blazing" in wanted:
        # 🔥 R69: «الترندية الملتهبة» — استدعاء مؤجل للمحرك المعزول الجديد
        # (الترندية بت-بت + N5/N6) — بلا أي مساس بأي محرك قائم.
        from app.services.indicators.overlays_zlf_e2e_blazing import zigzag_fib_e2e_blazing
        blazing_params = _normalize_overlay_params("zzfib_e2e_blazing", params.get("zzfib_e2e_blazing") or {})
        out["overlays"]["zzfib_e2e_blazing"] = zigzag_fib_e2e_blazing(candles, **blazing_params)
    if "zzfib_e2e_trendy_macd" in wanted:
        # ✅ PRO73: «الترندية الماكدية» — الترندية بت-بت + مصفوفة الموشرات
        # (RSI/MACD/Momentum متعددة النسخ/الفريمات) + بوابة الشروط القابلة للتركيب.
        # ✅ PRO73-R4 (لوحات الحي): بلا osc_instances ممرّرة = مكتبة المستند الكاملة
        # (67 نسخة) افتراضياً — تفعيل الويدجت من الواجهة (types=... بلا params)
        # يرجع كل سلاسل اللوحات الثلاث للرسم فوراً. البوابة تبقى هوية (بلا شروط).
        from app.services.indicators.overlays_zlf_e2e_trendy_macd import zigzag_fib_e2e_trendy_macd
        tmacd_params = _normalize_overlay_params("zzfib_e2e_trendy_macd", params.get("zzfib_e2e_trendy_macd") or {})
        if "osc_instances" not in tmacd_params:
            from app.services.indicators.osc_cases import OSC_DOC_INSTANCES
            tmacd_params["osc_instances"] = OSC_DOC_INSTANCES
        out["overlays"]["zzfib_e2e_trendy_macd"] = zigzag_fib_e2e_trendy_macd(candles, **tmacd_params)
    if "zzfib_e2e_blazing_macd" in wanted:
        # 🔥 PRO73: «الملتهبة الماكدية» — الملتهبة بت-بت (S1/S2/S3 + N5/N6) +
        # نفس مصفوفة الموشرات والبوابة القابلة للتركيب.
        # ✅ PRO73-R4 (لوحات الحي): نفس الافتراض — بلا قالب = مكتبة المستند 67.
        from app.services.indicators.overlays_zlf_e2e_blazing_macd import zigzag_fib_e2e_blazing_macd
        bmacd_params = _normalize_overlay_params("zzfib_e2e_blazing_macd", params.get("zzfib_e2e_blazing_macd") or {})
        if "osc_instances" not in bmacd_params:
            from app.services.indicators.osc_cases import OSC_DOC_INSTANCES
            bmacd_params["osc_instances"] = OSC_DOC_INSTANCES
        out["overlays"]["zzfib_e2e_blazing_macd"] = zigzag_fib_e2e_blazing_macd(candles, **bmacd_params)
    if "trend_fractal" in wanted:
        # ✅ ROUND32: مؤشر الترند المستقل — إحداثيات الخطوط وسلاسلها (Pine حرفياً).
        from app.services.indicators.trend_fractals import auto_trendlines_fractal
        trf_params = _normalize_overlay_params("trend_fractal", params.get("trend_fractal") or {})
        out["overlays"]["trend_fractal"] = auto_trendlines_fractal(candles, **trf_params)

    return out
