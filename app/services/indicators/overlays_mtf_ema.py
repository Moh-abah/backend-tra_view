# =============================================================================
# ✅ MTFEMA1 — «MTF EMA» المتوسط الأسي متعدد الفريمات (رسم فقط — لا شروط)
# =============================================================================
# الأصل (Pine Script v5 — من صاحب القرار):
#   htf_ma = ta.ema(src, ma_len)                       // len=100, src=close
#   out    = request.security(tickerid, res, htf_ma)    // res=60 (دقيقة)
#   plot(out, color=red, offset=0)
#   المعاملات: Length / Source / Offset / Resolution — كلها قابلة للتخصيص
#   من الواجهة، والرسم على شارت الباك-تست بلا أي شرط استراتيجي.
#
# ⚠️ MTFEMA1-v2 (إصلاح عطل إنتاجي 2026): النسخة الأولى كانت تستورد
#   TF_REGISTRY من mtf_oscillator_core — اسم غير موجود في نسخة الإنتاج
#   من ذلك الملف → ImportError عند الإقلاع → uvicorn يقتل العمليات
#   في حلقة لا نهائية. هذه النسخة:
#     1) لا تستورد شيئاً من mtf_oscillator_core إطلاقاً (نواة ذاتية بالكامل:
#        سجل فريمات خاص + إعادة تشكيل + EMA بذرة SMA بنمط TradingView).
#     2) استيرادات المستوى الأعلى = مكتبة قياسية + numpy فقط → الملف قابل
#        للإقلاع في أي بيئة ولا يمكن أن يُسقط الخادم عند الاستيراد.
#     3) كل استيرادات التطبيق مؤجلة داخل دوال التسجيل، وكل خطوة تسجيل
#        داخل try/except — فشل أي نقطة تكامل لا يوقف المحرك أبداً.
#     4) تسجيل ذاتي كامل (إضافة فقط — لا مساس بأي ملف قائم): عند الاستيراد
#        من __init__.py يرقّع الموديول نفسه في: overlay_columns (الأسماء/
#        القواعد/الأعمدة التعاقدية/تحويل التكوين/استخراج الأعمدة) +
#        overlays (OVERLAY_TYPES + موزّع compute_overlays) + calculator
#        (جسر البنية + خرائط الأسماء) + سجل المؤشرات (العرض في
#        /indicators/available ومسار الحاسبة الكلاسيكي). كل الترقيعات
#        خرسية العقد (idempotent) — الاستيراد مرتين أو وجود ترقيعات
#        سابقة من حزمة قديمة لا يكسر شيئاً.
#
# العقد مع الفرونت (عمود واحد قابل للرسم):
#   ind_mtfema_value : خط MTF EMA على شموع فريم الشارت الحالي —
#                      قيمة كل شمعة = EMA(HTF) لآخر شمعة HTF مغلقة عند
#                      لحظة ≤ إغلاق شمعة القاعدة (بلا نظر مستقبلية إطلاقاً —
#                      الشريط النامي للفريم الأعلى لا يُرى)، ثم إزاحة plot
#                      offset (موجب = يميناً/المستقبل كما في Pine).
#
# الحدود المتعمدة (بطلب صاحب القرار): لا شروط دخول/خروج، لا إشارات،
#   لا بوابات — رسم فقط. المستقبل: نسخ متعددة بمعاملات مختلفة كبوابات
#   لاستراتيجية «الترندية الكمومية المتحركة» (مؤجل بقرار صريح).
# =============================================================================

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

__all__ = [
    "mtf_ema",
    "MTF_EMA",
    "compute_mtf_ema",
    "multi_timeframe_ema",
    "MTF_EMA_ENGINE_NAME",
    "MTF_EMA_SPEC",
    "MTF_EMA_VERSION",
    "MTF_EMA_BASE",
    "MTF_EMA_DEFAULTS",
    "MTF_EMA_COLUMNS",
]

# ---------------------------------------------------------------------------
# الهوية
# ---------------------------------------------------------------------------
MTF_EMA_ENGINE_NAME = "MTF-EMA"
MTF_EMA_SPEC = "MTFEMA1-mtf-ema"
MTF_EMA_VERSION = "2.0.0"
MTF_EMA_BASE = "mtf_ema"

# افتراضات Pine الحرفية: Length=100 · Source=close · Offset=0 · Resolution=60
MTF_EMA_DEFAULTS: Dict[str, Any] = {
    "length": 100,
    "source": "close",
    "offset": 0,
    "resolution": "60",
}

# العمود التعاقدي الوحيد (رسم فقط)
MTF_EMA_COLUMNS: List[str] = ["ind_mtfema_value"]
_MTF_EMA_SERIES_PREFIX = "mtfema_"
_MTF_EMA_PRIMARY_SERIES = "mtfema_value"
_MTF_EMA_PRIMARY_COLUMN = "ind_mtfema_value"

# أسماء الوصول من الواجهة/الاستراتيجية → القاعدة mtf_ema (يُقبل اسم
# مجرد أو بصيغة نقطية فرعية: mtf_ema / mtfema / mtf_ema.value ...)
_MTF_EMA_NAME_ALIASES: Dict[str, str] = {
    "mtf_ema": MTF_EMA_BASE,
    "mtfema": MTF_EMA_BASE,
    "mtf_ema_overlay": MTF_EMA_BASE,
    "multi_timeframe_ema": MTF_EMA_BASE,
    "mtf_exponential_moving_average": MTF_EMA_BASE,
    "mtf_ema_line": MTF_EMA_BASE,
}

# مرادفات متوافقة (لو استوردتها ملفات حزمة قديمة بأسماء أخرى)
compute_mtf_ema = None  # يُربط بعد التعريف أدناه
multi_timeframe_ema = None
MTF_EMA = None

# ---------------------------------------------------------------------------
# نواة الفريمات الذاتية (بلا أي استيراد من mtf_oscillator_core)
# ---------------------------------------------------------------------------
_SEC = 1_000
_MIN = 60 * _SEC
_HOUR = 60 * _MIN
_DAY = 24 * _HOUR
_WEEK = 7 * _DAY
_MONDAY_EPOCH_MS = 4 * _DAY  # 1970-01-05 (الاثنين) — مرسى أسبوع TradingView

_S_RE = re.compile(r"^(\d+)s$", re.IGNORECASE)
_MIN_RE = re.compile(r"^(\d+)m$")
_H_RE = re.compile(r"^(\d+)h$", re.IGNORECASE)
_DAY_RE = re.compile(r"^(\d+)[dD]$|^day$|^1day$")
_WEEK_RE = re.compile(r"^(\d*)[wW]$|^week$|^1week$")
_MONTH_RE = re.compile(r"^(\d*)M$|^month$|^1month$")  # M كبير = شهر (Pine)


def _canon_minutes_label(m: int) -> str:
    """دقائق → تسمية Pine القانونية: 1m..59m · 60/120/240/720 (ساعات) · 1D/2D."""
    if m < 60:
        return f"{m}m"
    if m % 1440 == 0:
        return f"{m // 1440}D"
    if m % 60 == 0:
        return str(m)
    return f"{m}m"


def _parse_resolution(raw: Any) -> Dict[str, Any]:
    """Resolution خام → {label, step_ms, kind, n}.

    label = التسمية القانونية الموحدة (مدخلات مترادفة تعطي نفس التسمية:
    "1h" و"60" → "60" · "4h" و"240" → "240" · "1d" و"day" و"1440" → "1D" ...).
    kind: "fixed" (ثوانٍ/دقائق/ساعات/أيام — مرسى epoch أرضي) ·
          "week" (مرساة الاثنين) · "month" (بداية شهر تقويمي UTC).
    يقبل صيغ Pine والواجهة معاً: "60"/"1h" (ساعة) · "240"/"4h" · "1D"/"1d"
    · "1W"/"1w" · "1M" · "15m"/"15" · "1s".. · "3M" (ربع سنوي تقويمي).
    """
    s = str(raw if raw is not None else "").strip()
    if not s:
        s = str(MTF_EMA_DEFAULTS["resolution"])

    m = _MONTH_RE.match(s)
    if m:
        n = max(1, int(m.group(1) or 1))
        return {"label": f"{n}M", "step_ms": None, "kind": "month", "n": n}
    m = _WEEK_RE.match(s)
    if m:
        n = max(1, int(m.group(1) or 1))
        return {"label": f"{n}W", "step_ms": n * _WEEK, "kind": "week", "n": n}
    m = _S_RE.match(s)
    if m:
        n = max(1, int(m.group(1)))
        return {"label": f"{n}s", "step_ms": n * _SEC, "kind": "fixed", "n": n}
    m = _MIN_RE.match(s)
    if m:
        n = max(1, int(m.group(1)))
        return {"label": _canon_minutes_label(n), "step_ms": n * _MIN, "kind": "fixed", "n": n}
    m = _H_RE.match(s)
    if m:
        n = max(1, int(m.group(1)))
        return {"label": _canon_minutes_label(n * 60), "step_ms": n * _HOUR, "kind": "fixed", "n": n}
    m = _DAY_RE.match(s)
    if m:
        g = m.group(1)
        n = max(1, int(g) if g else 1)
        return {"label": f"{n}D", "step_ms": n * _DAY, "kind": "fixed", "n": n}
    # أرقام مجردة = دقائق (نمط Pine: "60" = ٦٠ دقيقة)
    if re.match(r"^\d+$", s):
        n = max(1, int(s))
        return {"label": _canon_minutes_label(n), "step_ms": n * _MIN, "kind": "fixed", "n": n}
    # مجهول → الافتراضي الحرفي للسكربت (60) مع تحذير
    logger.warning("MTF-EMA: resolution غير مفهومة '%s' — الرجوع للافتراضي '60'", s)
    return {"label": "60", "step_ms": 60 * _MIN, "kind": "fixed", "n": 60}


def _month_index_of(t_ms: np.ndarray) -> np.ndarray:
    """ms → فهرس الشهر التقويمي (شهور منذ 1970-01 UTC)."""
    return t_ms.astype("datetime64[ms]").astype("datetime64[M]").astype(np.int64)


def _month_start_ms(month_idx: int) -> int:
    return int(
        (np.datetime64("1970-01", "M") + np.timedelta64(int(month_idx), "M"))
        .astype("datetime64[ms]")
        .astype(np.int64)
    )


# ---------------------------------------------------------------------------
# تطبيع الشموع (نفس عقد norm_candles: DataFrame أو list[dict] بمفاتيح مرنة)
# ---------------------------------------------------------------------------
def _to_ms(v: Any) -> int:
    try:
        if hasattr(v, "timestamp") and not isinstance(v, (int, float)):
            return int(v.timestamp() * 1000)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return 0
            try:
                f = float(s)
            except ValueError:
                f = None
            if f is not None:
                return int(f * 1000.0) if f < 1e11 else int(f)
            from datetime import datetime, timezone

            s2 = s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s
            try:
                from datetime import datetime as _dt

                dt = _dt.fromisoformat(s2)
            except ValueError:
                return 0
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        f = float(v)
        return int(f * 1000.0) if f < 1e11 else int(f)
    except Exception:
        return 0


def _norm_candles_arrays(candles: Any) -> Tuple[np.ndarray, ...]:
    """(t_ms, open, high, low, close) كمصفوفات numpy — بلا تلفيق أي شمعة."""
    if candles is None:
        return (np.array([], dtype=np.int64),) + (np.array([], dtype=float),) * 4

    rows: List[Tuple[int, float, float, float, float]] = []

    def _num(v: Any) -> float:
        try:
            f = float(v)
            return f if math.isfinite(f) else float("nan")
        except (TypeError, ValueError):
            return float("nan")

    if hasattr(candles, "iterrows") and hasattr(candles, "columns"):
        cols = {str(x).lower(): x for x in candles.columns}
        ocol = cols.get("open") or cols.get("o")
        hcol = cols.get("high") or cols.get("h")
        lcol = cols.get("low") or cols.get("l")
        ccol = cols.get("close") or cols.get("c") or cols.get("adj close")
        tcol = cols.get("timestamp") or cols.get("time") or cols.get("open_time") or cols.get("date")
        if ocol is None or hcol is None or lcol is None or ccol is None:
            raise ValueError(
                "MTF-EMA: أعمدة الشموع غير مكتملة — مطلوب open/high/low/close"
            )
        for idx, row in candles.iterrows():
            rows.append((
                _to_ms(row[tcol] if tcol is not None else idx),
                _num(row[ocol]), _num(row[hcol]), _num(row[lcol]), _num(row[ccol]),
            ))
    else:
        for row in candles:
            if row is None:
                continue
            if not isinstance(row, dict):
                getter = getattr(row, "model_dump", None) or getattr(row, "dict", None)
                row = getter() if callable(getter) else dict(row.__dict__)
            low = {str(k).lower(): v for k, v in row.items()}
            rows.append((
                _to_ms(low.get("timestamp", low.get("time", low.get("open_time", low.get("date", 0))))),
                _num(low.get("open", low.get("o"))),
                _num(low.get("high", low.get("h"))),
                _num(low.get("low", low.get("l"))),
                _num(low.get("close", low.get("c"))),
            ))

    if not rows:
        return (np.array([], dtype=np.int64),) + (np.array([], dtype=float),) * 4
    arr = np.array(rows, dtype=object)
    t = arr[:, 0].astype(np.int64)
    o = arr[:, 1].astype(float)
    h = arr[:, 2].astype(float)
    l = arr[:, 3].astype(float)
    c = arr[:, 4].astype(float)
    return t, o, h, l, c


def _source_from_ohlc(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray,
                      source: str) -> np.ndarray:
    s = str(source or "close").strip().lower()
    if s in ("open", "o"):
        return o
    if s in ("high", "h"):
        return h
    if s in ("low", "l"):
        return l
    if s in ("hl2", "hloc2"):
        return (h + l) / 2.0
    if s in ("hlc3",):
        return (h + l + c) / 3.0
    if s in ("ohlc4", "oc2"):
        return (o + h + l + c) / 4.0
    return c  # close (الافتراضي الحرفي للسكربت)


def _ema_tv(x: np.ndarray, length: int) -> np.ndarray:
    """EMA بنمط TradingView/ta.ema: بذرة SMA(length) عند أول شريط صالح ثم
    alpha = 2/(length+1) تكرارياً. قبل الإحماء NaN."""
    n = x.size
    out = np.full(n, np.nan, dtype=float)
    if length < 1 or n < length:
        return out
    alpha = 2.0 / (length + 1.0)
    seed = float(np.mean(x[:length]))
    out[length - 1] = seed
    prev = seed
    for k in range(length, n):
        prev = alpha * float(x[k]) + (1.0 - alpha) * prev
        out[k] = prev
    return out


def _build_htf_bars(t: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray,
                    c: np.ndarray, res: Dict[str, Any]
                    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """إعادة تشكيل شموع القاعدة → شموع HTF (start_ms, close_ms, o, h, l, c).

    بلا تلفيق: البَكرات تُبنى فقط من الشموع الموجودة، وترتيبها زمني.
    kind=fixed: أرض epoch UTC · week: مرساة الاثنين · month: تقويم UTC.
    """
    n = t.size
    if n == 0:
        e = np.array([], dtype=np.int64)
        z = np.array([], dtype=float)
        return e, e, z, z, z, z

    kind = res["kind"]
    if kind == "month":
        mi = _month_index_of(t)
        nm = max(1, int(res["n"]))
        key = (mi // nm).astype(np.int64)
        uniq = np.unique(key)
        starts = np.array([_month_start_ms(int(k) * nm) for k in uniq], dtype=np.int64)
        closes = np.array([_month_start_ms((int(k) + 1) * nm) for k in uniq], dtype=np.int64)
    elif kind == "week":
        nm = max(1, int(res["n"]))
        step = int(res["step_ms"])
        key = (t - _MONDAY_EPOCH_MS) // step
        uniq, first_idx = np.unique(key, return_index=True)
        starts = uniq.astype(np.int64) * step + _MONDAY_EPOCH_MS
        closes = starts + step
    else:
        step = int(res["step_ms"])
        key = t // step
        uniq, first_idx = np.unique(key, return_index=True)
        starts = uniq.astype(np.int64) * step
        closes = starts + step

    # تجميع قطعي (sorted keys) — نعمل على ترتيب زمني للبَكرات
    order = np.argsort(key, kind="stable")
    k_sorted = key[order]
    o_s, h_s, l_s, c_s = o[order], h[order], l[order], c[order]
    boundaries = np.flatnonzero(np.diff(k_sorted) != 0)
    seg_starts = np.concatenate(([0], boundaries + 1))
    seg_ends = np.concatenate((boundaries, [k_sorted.size - 1]))

    bar_open = o_s[seg_starts]
    bar_close = c_s[seg_ends]
    bar_high = np.maximum.reduceat(h_s, seg_starts)
    bar_low = np.minimum.reduceat(l_s, seg_starts)
    return starts, closes, bar_open, bar_high, bar_low, bar_close


# ---------------------------------------------------------------------------
# المحرك — MTF EMA (رسم فقط)
# ---------------------------------------------------------------------------
def mtf_ema(
    candles: Any,
    length: int = 100,
    source: str = "close",
    offset: int = 0,
    resolution: str = "60",
) -> Dict[str, Any]:
    """«MTF EMA» متعدد الفريمات — مطابق لروح سكربت Pine:

        htf_ma = ta.ema(src, len)  على شموع HTF (resolution)
        قيمة شمعة القاعدة = آخر شمعة HTF مغلقة عند لحظة ≤ إغلاقها
        (بلا نظر مستقبلية — الشريط النامي لا يُرى إطلاقاً)
        ثم إزاحة plot(offset): موجب = يميناً/المستقبل كما في Pine.

    المعاملات (كلها قابلة للتخصيص من الواجهة):
      length      : طول EMA على الفريم الأعلى (افتراضي 100 — حرفي Pine)
      source      : open/high/low/close/hl2/hlc3/ohlc4 (افتراضي close)
      offset      : إزاحة الرسم بالشموع (افتراضي 0 — موجب يميناً)
      resolution  : فريم HTF — "60"/"1h"/"240"/"4h"/"1D"/"1W"/"1M"/"15m".. (افتراضي "60")

    المخرجات (JSON-آمن — لا NaN/Inf):
      bars, series{mtfema_value}, signals([] — رسم فقط), meta, notes
    """
    t, o, h, l, c = _norm_candles_arrays(candles)
    N = int(t.size)

    out_series: Dict[str, List[Optional[float]]] = {"mtfema_value": [None] * N}
    res_info = _parse_resolution(resolution)

    if N == 0:
        return {
            "bars": 0,
            "time_from": None,
            "time_to": None,
            "series": out_series,
            "signals": [],
            "meta": {"engine": MTF_EMA_ENGINE_NAME, "spec": MTF_EMA_SPEC,
                     "version": MTF_EMA_VERSION, "length": int(length),
                     "source": str(source), "offset": int(offset),
                     "resolution": res_info["label"], "htf_bars": 0},
            "notes": "MTF-EMA (MTFEMA1-v2) — لا شموع؛ رسم فقط بلا أي شرط استراتيجي.",
        }

    # خطوة شمعة القاعدة (أصغر فرق زمني موجب — متين أمام فجوات البيانات)
    if N > 1:
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
            "MTF-EMA: resolution '%s' (%d ms) أدنى من فريم الشارت (%d ms) — "
            "استُخدم فريم الشارت نفسه", res_info["label"], htf_step, base_step)
        htf_step = base_step
        res_info = dict(res_info, step_ms=base_step)
        clamped = True

    starts, closes, b_o, b_h, b_l, b_c = _build_htf_bars(t, o, h, l, c, res_info)
    M = int(starts.size)

    src_htf = _source_from_ohlc(b_o, b_h, b_l, b_c, source)
    ema_htf = _ema_tv(src_htf, int(length)) if M else np.array([], dtype=float)

    # ── التطابق بلا نظر مستقبلية: شمعة القاعدة [t_i, t_i+base_step) ترى
    # آخر شمعة HTF مع close_time ≤ لحظة إغلاقها (t_i + base_step)
    cutoff = t + base_step
    j = np.searchsorted(closes, cutoff, side="right") - 1 if M else np.full(N, -1, dtype=np.int64)
    valid = j >= 0
    j_safe = np.clip(j, 0, max(M - 1, 0))
    vals = np.where(valid, ema_htf[j_safe] if M else np.nan, np.nan)

    # ── إزاحة plot(offset): shifted[i] = value[i - offset] (Pine حرفياً)
    off = int(offset)
    if off != 0:
        idx = np.arange(N, dtype=np.int64)
        src_idx = idx - off
        ok = (src_idx >= 0) & (src_idx < N)
        shifted = np.full(N, np.nan, dtype=float)
        shifted[ok] = vals[src_idx[ok]]
        vals = shifted

    def _jsonable(v: float) -> Optional[float]:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return None
        f = float(v)
        return f if math.isfinite(f) else None

    out_series["mtfema_value"] = [_jsonable(v) for v in vals.tolist()]

    first_valid = next(
        (i for i, v in enumerate(out_series["mtfema_value"]) if v is not None), None)

    return {
        "bars": N,
        "time_from": int(t[0]),
        "time_to": int(t[-1]),
        "series": out_series,
        "signals": [],
        "meta": {
            "engine": MTF_EMA_ENGINE_NAME,
            "spec": MTF_EMA_SPEC,
            "version": MTF_EMA_VERSION,
            "length": int(length),
            "source": str(source),
            "offset": int(offset),
            "resolution": res_info["label"],
            "htf_step_ms": int(htf_step) if htf_step is not None else None,
            "htf_kind": res_info["kind"],
            "htf_bars": M,
            "base_step_ms": base_step,
            "resolution_clamped_to_chart_tf": clamped,
            "first_valid_index": first_valid,
        },
        "notes": "MTF-EMA (MTFEMA1-v2) — «MTF EMA» متعدد الفريمات (رسم فقط، بلا "
                 "أي شرط استراتيجي): EMA(length) على شموع HTF(resolution) ببذرة "
                 "SMA بنمط TradingView، وقيمة كل شمعة قاعدة = آخر شمعة HTF "
                 "مغلقة عند لحظة ≤ إغلاقها (بلا نظر مستقبلية — الشريط النامي لا "
                 "يُرى)، مع إزاحة plot offset (موجب = يميناً كما في Pine). "
                 "العمود التعاقدي: ind_mtfema_value.",
    }


# مرادفات متوافقة مع أي استدعاء بأسماء أخرى
compute_mtf_ema = mtf_ema
multi_timeframe_ema = mtf_ema
MTF_EMA = mtf_ema


# ---------------------------------------------------------------------------
# تطبيع المعاملات (من أي صيغة واجهة → الشكل القانوني الأربعة)
# ---------------------------------------------------------------------------
def _norm_mtf_ema_params(raw: Any) -> Dict[str, Any]:
    p = dict(raw or {})

    def _take_num(keys: Sequence[str], cast, default):
        for k in keys:
            if k in p:
                try:
                    return cast(p[k])
                except (TypeError, ValueError):
                    continue
        return default

    length = _take_num(("length", "len", "ma_len", "ema_length", "period"), int,
                       int(MTF_EMA_DEFAULTS["length"]))
    length = max(1, int(length))
    offset = int(_take_num(("offset", "shift", "plot_offset", "plot_shift"), int,
                           int(MTF_EMA_DEFAULTS["offset"])))

    source = str(p.get("source", p.get("src", p.get("price", ""))) or "").strip().lower()
    if source not in ("open", "high", "low", "close", "hl2", "hlc3", "ohlc4"):
        source = "close"

    res_raw = p.get("resolution", p.get("res", p.get("htf", p.get("htf_timeframe",
              p.get("input_resolution", p.get("timeframe", MTF_EMA_DEFAULTS["resolution"]))))))
    resolution = _parse_resolution(res_raw)["label"]

    return {"length": length, "source": source, "offset": offset, "resolution": resolution}


def _mtfema_columns(res: Dict[str, Any]) -> Dict[str, List[Optional[float]]]:
    """نتيجة mtf_ema → أعمدة ind_mtfema_* (mtfema_X → ind_mtfema_X)."""
    out: Dict[str, List[Optional[float]]] = {}
    s = (res or {}).get("series") or {}
    for key, vals in s.items():
        k = str(key)
        if k.startswith(_MTF_EMA_SERIES_PREFIX):
            out["ind_" + k] = vals if vals is not None else []
    return out


def _is_mtf_ema_name(raw_name: Any) -> bool:
    try:
        base = str(raw_name or "").split(".")[0].strip().lower()
        return base in _MTF_EMA_NAME_ALIASES
    except Exception:
        return False


# ---------------------------------------------------------------------------
# ✅ التسجيل الذاتي — يُستورد مرة واحدة من app/services/indicators/__init__.py
#    (إضافة فقط؛ كل خطوة idempotent وداخل try/except — لا تعطل الخادم أبداً)
# ---------------------------------------------------------------------------
def _patch_overlay_columns() -> None:
    from app.services.indicators import overlay_columns as _oc

    # 1) الأسماء (dict قابل للطفو — آمن ومتكرر)
    for alias, base in _MTF_EMA_NAME_ALIASES.items():
        _oc.OVERLAY_ALIASES.setdefault(alias, base)
    _oc.OVERLAY_ALIASES.setdefault("mtf_ema", MTF_EMA_BASE)

    # 2) القواعد المعروفة (tuple — إعادة ربط خرسية العقد)
    if MTF_EMA_BASE not in _oc.KNOWN_OVERLAY_BASES:
        _oc.KNOWN_OVERLAY_BASES = tuple(_oc.KNOWN_OVERLAY_BASES) + (MTF_EMA_BASE,)

    # 3) الأعمدة التعاقدية
    _oc.CONTRACT_COLUMNS[MTF_EMA_BASE] = list(MTF_EMA_COLUMNS)

    # 4) config_to_overlay_params — غلاف يعترض أسماء mtf_ema (يحوّل المعاملات
    #    بالشكل الصحيح: length/source/offset/resolution) ثم يفوّض الباقي
    orig = _oc.config_to_overlay_params
    if not getattr(orig, "_mtfema_wrap", False):

        def _config_to_overlay_params_mtfema(cfg: Any,
                                             _orig=orig, _oc=_oc) -> Optional[Dict[str, Dict[str, Any]]]:
            try:
                name = str(
                    (cfg or {}).get("name", "") if isinstance(cfg, dict)
                    else getattr(cfg, "name", "") or ""
                )
                if _is_mtf_ema_name(name):
                    raw = (cfg or {}).get("params", {}) if isinstance(cfg, dict) \
                        else (getattr(cfg, "params", None) or {})
                    return {MTF_EMA_BASE: _norm_mtf_ema_params(raw)}
            except Exception:
                logger.exception("MTF-EMA config_to_overlay_params wrapper failed")
            return _orig(cfg)

        _config_to_overlay_params_mtfema._mtfema_wrap = True  # type: ignore[attr-defined]
        _oc.config_to_overlay_params = _config_to_overlay_params_mtfema

    # 5) columns_from_overlays_result — غلاف يستخرج ind_mtfema_* من نتيجة
    #    compute_overlays ويترك الباقي للأصل
    orig_cols = _oc.columns_from_overlays_result
    if not getattr(orig_cols, "_mtfema_wrap", False):

        def _columns_from_overlays_result_mtfema(res: Dict[str, Any],
                                                  _orig=orig_cols) -> Dict[str, List[Optional[float]]]:
            out = _orig(res)
            try:
                ovl = (res or {}).get("overlays") if isinstance(res, dict) else None
                mtf = None
                if isinstance(ovl, dict):
                    mtf = ovl.get(MTF_EMA_BASE)
                if mtf is None and isinstance(res, dict):
                    v = res.get(MTF_EMA_BASE)
                    if isinstance(v, dict):
                        mtf = v
                if isinstance(mtf, dict) and mtf.get("series"):
                    out.update(_mtfema_columns(mtf))
            except Exception:
                logger.exception("MTF-EMA columns_from_overlays_result wrapper failed")
            return out

        _columns_from_overlays_result_mtfema._mtfema_wrap = True  # type: ignore[attr-defined]
        _oc.columns_from_overlays_result = _columns_from_overlays_result_mtfema


def _patch_overlays_module() -> None:
    from app.services.indicators import overlays as _ovl

    # 1) OVERLAY_TYPES — إعادة ربط tuple خرسية العقد
    if MTF_EMA_BASE not in _ovl.OVERLAY_TYPES:
        _ovl.OVERLAY_TYPES = tuple(_ovl.OVERLAY_TYPES) + (MTF_EMA_BASE,)

    # 2) compute_overlays — غلاف: يعترض mtf_ema المطلوب صراحةً ويحسبه
    #    بنفسه (بمعاملاته الصحيحة)، ويفوّض الباقي للأصل كما هو.
    #    طلب «كل الأنواع» الافتراضي (types=None) لا يحسب mtf_ema — نفس
    #    سياسة حماية الأداء المعتمدة للكمومية/الماكدية في اللوحات الحيّة.
    orig = _ovl.compute_overlays
    if not getattr(orig, "_mtfema_wrap", False):

        def _compute_overlays_mtfema(candles: Any,
                                     types: Optional[Sequence[str]] = None,
                                     params: Optional[Dict[str, Dict[str, Any]]] = None,
                                     _orig=orig) -> Dict[str, Any]:
            params = params or {}
            if types is None:
                return _orig(candles, types=types, params=params)
            wanted = [str(x) for x in types if str(x).strip()]
            mtf_requested = any(str(x).strip().lower() == MTF_EMA_BASE for x in wanted)
            rest = [x for x in wanted if str(x).strip().lower() != MTF_EMA_BASE]
            res = _orig(candles, types=rest, params=params)
            if mtf_requested:
                try:
                    norm = _norm_mtf_ema_params(params.get(MTF_EMA_BASE) or {})
                    if not isinstance(res, dict):
                        res = {"overlays": {}}
                    res.setdefault("overlays", {})[MTF_EMA_BASE] = mtf_ema(candles, **norm)
                except Exception:
                    logger.exception("MTF-EMA compute_overlays branch failed")
                    res.setdefault("overlays", {})[MTF_EMA_BASE] = {
                        "series": {"mtfema_value": []}, "signals": [],
                        "notes": "MTF-EMA: فشل الحساب — راجع السجل",
                    }
            return res

        _compute_overlays_mtfema._mtfema_wrap = True  # type: ignore[attr-defined]
        _ovl.compute_overlays = _compute_overlays_mtfema


def _patch_calculator() -> None:
    from app.services.indicators.calculator import IndicatorCalculator

    # خرائط الأسماء/العمود الأساسي على مستوى الفئة (dict — قابل للطفو)
    if isinstance(getattr(IndicatorCalculator, "_OVERLAY_ALIASES", None), dict):
        IndicatorCalculator._OVERLAY_ALIASES.update(_MTF_EMA_NAME_ALIASES)
    if isinstance(getattr(IndicatorCalculator, "_OVERLAY_PRIMARY", None), dict):
        IndicatorCalculator._OVERLAY_PRIMARY[MTF_EMA_BASE] = _MTF_EMA_PRIMARY_COLUMN

    # جسر البنية — غلاف يعترض تكوينات mtf_ema قبل سلسلة if/elif الصلبة
    # في الأصل (التي لا تعرف معاملاتنا) ويعيد النتيجة بالشكل التعاقدي.
    orig = IndicatorCalculator._calculate_overlay_indicator
    if not getattr(orig, "_mtfema_wrap", False):

        def _calculate_overlay_indicator_mtfema(self, dataframe, config,
                                               _orig=orig):
            try:
                raw_name = str((config or {}).get("name") or "")
                if _is_mtf_ema_name(raw_name):
                    params = _norm_mtf_ema_params(dict((config or {}).get("params") or {}))
                    res = mtf_ema(dataframe, **params)
                    cols = _mtfema_columns(res)
                    idx = list(dataframe.index)
                    data = cols.get(_MTF_EMA_PRIMARY_COLUMN) or [None] * len(dataframe)
                    return {
                        "name": raw_name,
                        "values": {"data": data, "index": idx, "dtype": "object"},
                        "signals": None,
                        "metadata": {
                            "overlay": MTF_EMA_BASE,
                            "sub": _MTF_EMA_PRIMARY_COLUMN,
                            "params": params,
                            "available_columns": sorted(cols.keys()),
                            "description": (
                                "MTF EMA (رسم فقط) — العمود: " + _MTF_EMA_PRIMARY_COLUMN +
                                " · معاملات: length/source/offset/resolution"
                            ),
                            "engine": MTF_EMA_ENGINE_NAME + " (" + MTF_EMA_SPEC + " v" + MTF_EMA_VERSION + ")",
                        },
                    }
            except Exception:
                logger.exception("MTF-EMA bridge wrapper failed — تفويض للأصل")
            return _orig(self, dataframe, config)

        _calculate_overlay_indicator_mtfema._mtfema_wrap = True  # type: ignore[attr-defined]
        IndicatorCalculator._calculate_overlay_indicator = _calculate_overlay_indicator_mtfema


def _register_indicator_class() -> None:
    from .base import BaseIndicator, IndicatorResult, IndicatorType
    from .registry import IndicatorRegistry
    import pandas as pd

    class MtfEmaIndicator(BaseIndicator):
        """«MTF EMA» — المتوسط الأسي متعدد الفريمات (رسم فقط — لا شروط)."""

        @classmethod
        def get_required_columns(cls) -> List[str]:
            return ["open", "high", "low", "close"]

        @classmethod
        def get_default_params(cls) -> Dict[str, Any]:
            return dict(MTF_EMA_DEFAULTS)

        def calculate(self, data: pd.DataFrame) -> IndicatorResult:
            from .overlay_columns import config_to_overlay_params
            conv = config_to_overlay_params({
                "name": MTF_EMA_BASE,
                "params": dict(self.params or {}),
            }) or {MTF_EMA_BASE: {}}
            params = conv.get(MTF_EMA_BASE) or {}
            res = mtf_ema(data, **params)
            values = res["series"].get(_MTF_EMA_PRIMARY_SERIES) or [None] * len(data)
            series = pd.Series(values, index=data.index, dtype=object)
            return IndicatorResult(
                name=self.name,
                values=series,
                signals=None,
                metadata={
                    "engine": MTF_EMA_ENGINE_NAME,
                    "overlay": MTF_EMA_BASE,
                    "primary_column": _MTF_EMA_PRIMARY_COLUMN,
                    "available_columns": sorted(_mtfema_columns(res).keys()),
                    "params": params,
                },
            )

    if IndicatorRegistry.get_indicator_info(MTF_EMA_BASE) is None:
        IndicatorRegistry.register(
            MTF_EMA_BASE,
            display_name="MTF EMA — المتوسط الأسي متعدد الفريمات (رسم فقط)",
            description=(
                "«Multi Time Frame Exponential Moving Average» (MTFEMA1): EMA(length) "
                "محسوبة على شموع فريم أعلى (resolution) ثم تُرسم على شموع فريم الشارت — "
                "قيمة كل شمعة = EMA لآخر شمعة HTF مغلقة عند لحظة ≤ إغلاقها (بلا نظر "
                "مستقبلية؛ الشريط النامي لا يُرى) مع إزاحة plot offset. معاملات: "
                "length (افتراضي 100) · source (close/open/high/low/hl2/hlc3/ohlc4) · "
                "offset (0) · resolution («60» = ساعة · «240»/«4h» · «1D» · «1W» · «1M»). "
                "رسم فقط بلا أي شرط استراتيجي — العمود: ind_mtfema_value."
            ),
            category=IndicatorType.TREND,
        )(MtfEmaIndicator)

        # مرادف قصير — نفس الفئة (نمط العائلة)
        info = IndicatorRegistry._indicators.get(MTF_EMA_BASE)
        if info is not None:
            IndicatorRegistry._indicators.setdefault("mtfema", info)


def _register_mtf_ema() -> None:
    steps = (
        ("overlay_columns", _patch_overlay_columns),
        ("overlays", _patch_overlays_module),
        ("calculator", _patch_calculator),
        ("indicator_registry", _register_indicator_class),
    )
    for label, fn in steps:
        try:
            fn()
        except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
            logger.exception("MTF-EMA registration step '%s' failed — متابعة", label)


_register_mtf_ema()
