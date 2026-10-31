# =============================================================================
# ✅ الجولة 11 (v2) — أعمدة مؤشرات البنية ind_* — العقد الملزم مع الفرونت
# =============================================================================
# مصدر الحقيقة الوحيد لتحويل نتائج compute_overlays إلى أعمدة مسطّحة لكل شمعة
# تُستهلك في: محرك الاستراتيجيات (_prepare_indicators)، الباك-تست، chart-data.
#
# العقد (نهائي ملزم — الواجهة بُنيت عليه):
#
#   Zig Zag Channels:
#     ind_zz_state           : 0 = نظام قمم، 1 = نظام قيعان (None قبل التمهيد)
#     ind_zz_pivot           : +1 = قمة مؤكدة عند هذه الشمعة، -1 = قاع مؤكد، 0 لا شيء
#     ind_zz_pivot_high      : سعر القمة المؤكدة (عند شمعة التأكيد فقط، وإلا None)
#     ind_zz_pivot_low       : سعر القاع المؤكد (عند شمعة التأكيد فقط، وإلا None)
#     ind_zz_prev_pivot_low  : سعر القاع المؤكد السابق (يبقى حتى القاع التالي)
#     ind_zz_prev_pivot_high : سعر القمة المؤكدة السابقة
#
#   Auto Fib Retracement:
#     ind_fib_dir      : +1 ساق صاعدة / -1 هابطة / 0
#     ind_fib_start    : بداية الساق (p1)
#     ind_fib_end      : نهاية الساق (p2)
#     ind_fib_target   : مستوى الهدف (0.618 افتراضياً) عند كل شمعة
#     ind_fib_signal   : +1 = Buy Retrace · -1 = Sell Retrace · 0
#                        (منطق أول لمس + إعادة تسليح مطابق للسكربت — موجود
#                         أصلاً في signals[] من compute_overlays)
#
#   Auto Trendline:
#     ind_atl_upper       : سعر مسقط الخط العلوي عند الشمعة (None إن لا خط)
#     ind_atl_lower       : سعر مسقط الخط السفلي
#     ind_atl_signal      : +1 = إغلاق قطع العلوي لأعلى · -1 = إغلاق قطع السفلي
#                           لأسفل · 0 (اتجاها over-السفلي/under-العلوي لا يُعدان)
#     ind_atl_cross_upper : 1/0 (تقاطع بأي اتجاه مع العلوي)
#     ind_atl_cross_lower : 1/0
#
# ملاحظة repaint: أعمدة الزيجزاج تُكتب عند شمعة التأكيد (confirmed_at_bar =
# نقطة + length) لا عند شمعة النقطة — لذا القراءة عند شمعة التأكيد بلا repaint.
#
# الأسماء المقبولة في strategy_config.indicators[].name (كلها مرادفات):
#   zigzag | zigzag_channels           → base "zigzag"
#   fib | auto_fib_retracement         → base "fib"
#   trendline | auto_trendline         → base "trendline"
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = [
    "OVERLAY_ALIASES",
    "CONTRACT_COLUMNS",
    "KNOWN_OVERLAY_BASES",
    "normalize_overlay_name",
    "is_known_indicator_name",
    "config_to_overlay_params",
    "columns_from_overlays_result",
    "columns_for_configs",
]

# ---------------------------------------------------------------- الأسماء ---

# اسم وارد من الواجهة → base الدالة في overlays.py
OVERLAY_ALIASES: Dict[str, str] = {
    "zigzag": "zigzag",
    "zigzag_channels": "zigzag",
    "fib": "fib",
    "auto_fib_retracement": "fib",
    "trendline": "trendline",
    "auto_trendline": "trendline",
}

KNOWN_OVERLAY_BASES = ("zigzag", "fib", "trendline")

# أسماء الأعمدة التعاقدية لكل base (للتوثيق والفحص)
CONTRACT_COLUMNS: Dict[str, List[str]] = {
    "zigzag": [
        "ind_zz_state", "ind_zz_pivot", "ind_zz_pivot_high", "ind_zz_pivot_low",
        "ind_zz_prev_pivot_low", "ind_zz_prev_pivot_high",
    ],
    "fib": [
        "ind_fib_dir", "ind_fib_start", "ind_fib_end", "ind_fib_target", "ind_fib_signal",
    ],
    "trendline": [
        "ind_atl_upper", "ind_atl_lower", "ind_atl_signal",
        "ind_atl_cross_upper", "ind_atl_cross_lower",
    ],
}


def normalize_overlay_name(raw: str) -> Optional[str]:
    """اسم مؤشر (قد يحوي نقطة فرعية) → base إن كان من مؤشرات البنية وإلا None.

    أمثلة: 'zigzag_channels' → 'zigzag' · 'zigzag.zz_state' → 'zigzag'
           'auto_fib_retracement' → 'fib' · 'rsi' → None
    """
    if not raw:
        return None
    base = str(raw).split(".")[0].strip().lower()
    return OVERLAY_ALIASES.get(base)


def is_known_indicator_name(raw: str) -> bool:
    """هل الاسم معروف للمحرك؟ (مؤشرات البنية أو سجل المؤشرات الكلاسيكي)"""
    if not raw:
        return False
    name = str(raw).strip()
    if normalize_overlay_name(name) is not None:
        return True
    try:
        from app.services.indicators.registry import IndicatorRegistry
        return IndicatorRegistry.get_indicator_info(name.lower()) is not None
    except Exception:
        return False


def config_to_overlay_params(cfg: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """تكوين مؤشر من الاستراتيجية → {base: params} لـ compute_overlays.

    يقبل كائن pydantic (IndicatorConfig) أو dict. يعيد None إن لم يكن من البنية.
    المرادفات المدعومة في params:
      zigzag: length
      fib: depth, dev_threshold (dev/deviation/deviation_threshold),
           retracement (ret/target_ratio), level_ratios (levels),
           reverse, extend_left, extend_right
      trendline: period (n/fractal_period), max_pairs (pairs/max_tl), extend
    """
    base = normalize_overlay_name(str((cfg or {}).get("name", "") if isinstance(cfg, dict) else getattr(cfg, "name", "") or ""))
    if base is None:
        return None
    raw_params = (cfg or {}).get("params", {}) if isinstance(cfg, dict) else (getattr(cfg, "params", None) or {})
    p = dict(raw_params or {})
    out: Dict[str, Any] = {}

    def _num(key_aliases: Sequence[str], cast=float, default=None):
        for k in key_aliases:
            if k in p:
                try:
                    return cast(p[k])
                except (TypeError, ValueError):
                    continue
        return default

    if base == "zigzag":
        length = _num(("length",), int)
        if length is not None:
            out["length"] = max(2, length)
    elif base == "fib":
        depth = _num(("depth",), int)
        if depth is not None:
            out["depth"] = max(1, depth)
        dev = _num(("dev_threshold", "dev", "deviation", "deviation_threshold"))
        if dev is not None:
            out["dev_threshold"] = dev
        ret = _num(("retracement", "ret", "target_ratio"))
        if ret is not None:
            out["retracement"] = ret
        lv = p.get("level_ratios", p.get("levels"))
        if isinstance(lv, (list, tuple)) and lv:
            try:
                out["level_ratios"] = [float(x) for x in lv]
            except (TypeError, ValueError):
                pass
        for k in ("reverse", "extend_left", "extend_right"):
            if k in p:
                out[k] = bool(p[k])
    else:  # trendline
        period = _num(("period", "n", "fractal_period"), int)
        if period is not None:
            out["period"] = max(2, period)
        pairs = _num(("max_pairs", "pairs", "max_tl"), int)
        if pairs is not None:
            out["max_pairs"] = max(1, pairs)
        if "extend" in p:
            out["extend"] = str(p["extend"])

    return {base: out}


# ------------------------------------------------------- بناء الأعمدة ---


def _zigzag_columns(zz: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    s = zz.get("series") or {}
    state = list(s.get("zz_state") or [])
    n = len(state)
    zz_state: List[Optional[float]] = [None if v is None else float(v) for v in state]
    zz_pivot: List[float] = [0.0] * n
    zz_ph: List[Optional[float]] = [None] * n
    zz_pl: List[Optional[float]] = [None] * n

    # الأحداث من pivots — تُكتب عند شمعة التأكيد confirmed_at_bar (بلا repaint)
    for pv in zz.get("pivots") or []:
        try:
            c = int(pv.get("confirmed_at_bar"))
        except (TypeError, ValueError):
            continue
        if not (0 <= c < n):
            continue
        price = pv.get("price")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        if str(pv.get("kind")) == "top":
            zz_pivot[c] = 1.0
            zz_ph[c] = price
        else:
            zz_pivot[c] = -1.0
            zz_pl[c] = price

    # prev: آخر قمة/قاع مؤكدة قبل الشمعة الحالية (عند شمعة التأكيد نفسها
    # تبقى القيمة القديمة — يجعل شرط HL/HH صحيحاً: الجديد > السابق)
    prev_pl: List[Optional[float]] = [None] * n
    prev_ph: List[Optional[float]] = [None] * n
    cur_btm: Optional[float] = None
    cur_top: Optional[float] = None
    for i in range(n):
        if zz_pl[i] is not None:
            prev_pl[i] = cur_btm
            cur_btm = zz_pl[i]
        else:
            prev_pl[i] = cur_btm
        if zz_ph[i] is not None:
            prev_ph[i] = cur_top
            cur_top = zz_ph[i]
        else:
            prev_ph[i] = cur_top

    return {
        "ind_zz_state": zz_state,
        "ind_zz_pivot": zz_pivot,
        "ind_zz_pivot_high": zz_ph,
        "ind_zz_pivot_low": zz_pl,
        "ind_zz_prev_pivot_low": prev_pl,
        "ind_zz_prev_pivot_high": prev_ph,
    }


def _fib_columns(fib: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    s = fib.get("series") or {}
    n = len(s.get("fib_start") or [])
    direction: List[float] = [0.0] * n
    start: List[Optional[float]] = [None] * n
    end: List[Optional[float]] = [None] * n
    target: List[Optional[float]] = [None] * n

    try:
        retr = float((fib.get("params") or {}).get("retracement", 0.618) or 0.618)
    except (TypeError, ValueError):
        retr = 0.618

    # رجل صالحة = غير التركيبية (anchor من سعر 0). امتداد الرجل الزمني =
    # من بدايتها حتى بداية الرجل التالية (آخر رجل حتى نهاية البيانات).
    legs = [lg for lg in (fib.get("legs") or []) if not lg.get("synthetic_anchor")]
    for k, leg in enumerate(legs):
        try:
            x1 = int(leg.get("x1"))
            y1 = float(leg.get("y1"))
            y2 = float(leg.get("y2"))
        except (TypeError, ValueError):
            continue
        if k + 1 < len(legs):
            try:
                span_end = int(legs[k + 1].get("x1"))
            except (TypeError, ValueError):
                span_end = n
        else:
            span_end = n
        span_end = max(x1 + 1, min(n, span_end))
        if not (0 <= x1 < n):
            continue
        diff = y2 - y1
        sign = 1.0 if diff > 0 else (-1.0 if diff < 0 else 0.0)
        tgt = (y1 + sign * abs(diff) * retr) if sign != 0.0 else None
        for i in range(x1, span_end):
            direction[i] = sign
            start[i] = y1
            end[i] = y2
            target[i] = tgt

    # الإشارات: منطق أول لمس + إعادة تسليح مطابق للسكربت (محسوب أصلاً في compute)
    sig: List[float] = [0.0] * n
    for ev in fib.get("signals") or []:
        try:
            bar = int(ev.get("bar"))
        except (TypeError, ValueError):
            continue
        if not (0 <= bar < n):
            continue
        side = str(ev.get("side") or "").strip().lower()
        sig_name = str(ev.get("signal") or "").strip().lower()
        if side == "buy" or sig_name.startswith("buy"):
            sig[bar] = 1.0
        elif side == "sell" or sig_name.startswith("sell"):
            sig[bar] = -1.0

    return {
        "ind_fib_dir": direction,
        "ind_fib_start": start,
        "ind_fib_end": end,
        "ind_fib_target": target,
        "ind_fib_signal": sig,
    }


def _trendline_columns(tl: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    s = tl.get("series") or {}
    upper_raw = list(s.get("tl_upper") or [])
    lower_raw = list(s.get("tl_lower") or [])
    cross_up_raw = list(s.get("tl_cross_upper") or [])
    cross_dn_raw = list(s.get("tl_cross_lower") or [])
    n = len(upper_raw)

    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n
    for i in range(n):
        v = upper_raw[i]
        if v is not None:
            try:
                upper[i] = float(v)
            except (TypeError, ValueError):
                pass
        v = lower_raw[i]
        if v is not None:
            try:
                lower[i] = float(v)
            except (TypeError, ValueError):
                pass

    cross_up: List[float] = [1.0 if bool(x) else 0.0 for x in cross_up_raw[:n]]
    cross_up += [0.0] * (n - len(cross_up))
    cross_dn: List[float] = [1.0 if bool(x) else 0.0 for x in cross_dn_raw[:n]]
    cross_dn += [0.0] * (n - len(cross_dn))

    # الإشارة التعاقدية: قطع العلوي لأعلى = +1 · كسر السفلي لأسفل = -1
    sig: List[float] = [0.0] * n
    for cr in tl.get("crosses") or []:
        try:
            bar = int(cr.get("bar"))
        except (TypeError, ValueError):
            continue
        if not (0 <= bar < n):
            continue
        line = str(cr.get("type") or "").strip().lower()
        direction = str(cr.get("direction") or "").strip().lower()
        if line == "upper" and direction == "over":
            sig[bar] += 1.0
        elif line == "lower" and direction == "under":
            sig[bar] -= 1.0
    sig = [max(-1.0, min(1.0, v)) for v in sig]

    return {
        "ind_atl_upper": upper,
        "ind_atl_lower": lower,
        "ind_atl_signal": sig,
        "ind_atl_cross_upper": cross_up,
        "ind_atl_cross_lower": cross_dn,
    }


def columns_from_overlays_result(res: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """نتيجة compute_overlays → أعمدة ind_* التعاقدية (فقط للأنواع المحسوبة)."""
    out: Dict[str, List[Optional[float]]] = {}
    ovl = (res or {}).get("overlays") if isinstance(res, dict) else None
    if ovl is None and isinstance(res, dict):
        # يقبل أيضاً القاموس المجرّد {zigzag:..., fib:..., trendline:...}
        ovl = {k: v for k, v in res.items() if k in KNOWN_OVERLAY_BASES and isinstance(v, dict)}
    if not ovl:
        return out
    zz = ovl.get("zigzag")
    if isinstance(zz, dict) and zz.get("series"):
        out.update(_zigzag_columns(zz))
    fb = ovl.get("fib")
    if isinstance(fb, dict) and fb.get("series"):
        out.update(_fib_columns(fb))
    tl = ovl.get("trendline")
    if isinstance(tl, dict) and tl.get("series"):
        out.update(_trendline_columns(tl))
    return out


def columns_for_configs(
    candles: Any,
    indicator_configs: Sequence[Any],
) -> Dict[str, List[Optional[float]]]:
    """تكوينات الاستراتيجية + الشموع → أعمدة ind_* جاهزة للحقن في DataFrame.

    تجمع معاملات كل مؤشرات البنية المفعّلة، تحسب المطلوب منها مرة واحدة
    (نوع واحد لكل base — آخر تكرار مفعّل يفوز مع تحذير)، وتعيد الأعمدة.
    """
    from app.services.indicators.overlays import compute_overlays

    merged_params: Dict[str, Dict[str, Any]] = {}
    wanted: List[str] = []
    for cfg in indicator_configs or []:
        conv = config_to_overlay_params(cfg)
        if conv is None:
            continue
        base, params = next(iter(conv.items()))
        if base not in merged_params:
            wanted.append(base)
        elif params != merged_params[base]:
            name = str((cfg or {}).get("name", "") if isinstance(cfg, dict) else getattr(cfg, "name", ""))
            logger.warning("overlay duplicate base '%s' with different params (from '%s') — last enabled wins", base, name)
        merged_params[base] = params

    if not wanted:
        return {}

    try:
        res = compute_overlays(candles, types=wanted, params=merged_params)
    except Exception:
        logger.exception("compute_overlays failed for types=%s", wanted)
        return {}

    cols = columns_from_overlays_result(res)
    # سلامة: أعِد الأعمدة بطول موحّد (طول الشموع)
    try:
        n = len(candles)
    except TypeError:
        n = 0
    if n:
        for k, v in cols.items():
            if len(v) < n:
                v = v + [None] * (n - len(v))
            cols[k] = v[:n]
    return cols
