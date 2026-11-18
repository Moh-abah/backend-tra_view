# =============================================================================
# 🟣 R76 — PRO76-mtf-osc-core v2.0.0 — نواة الموشرات متعددة الفريمات
# =============================================================================
# أمر صاحب القرار (الجولة 76 — 2026-11-15): «اصلح كل ما هو عِلّة في النظام
#   وما دون فريم الدقيقة للثواني وكل الأجزاء التي تحت الدقيقة».
#
# هذا الملف = الاستبدال الكامل لنواة PRO73/74 (PRO73-mtf-osc-core 1.1.0).
# عقد الحمولة متوافق حرفياً مع 1.1.0 (قياس مباشر من الإنتاج 2026-11-15)
# + إضافات/إصلاحات R76:
#
# ✅ B-1 فريمات الثواني (1s/5s/15s/30s) مواطنة من الدرجة الأولى: النسخ
#     الأعلى تُبنى بالتجميع الصاعد، والنسخ الأدنى من فريم القاعدة تصبح
#     متاحة تلقائياً عند تمرير شموع أدق (auto-detect لفريم القاعدة الحقيقي
#     من تباعد الشموع الفعلي — لا من ادّعاء المُستدعي).
# ✅ B-2 الصدق في base_tf: يُستنتج من التباعد الفعلي + base_tf_ms رقم
#     صريح + resolution/view_sampled/view_step عند أخذ عينات للعرض، مع
#     نمط التخزين المخفَّض view (سلاسل عند أعمدة العرض فقط) بلا أي حاجة
#     لبناء قوائم Python بطول الدقة الكاملة.
# ✅ B-3 osc_instances المخصصة تُحترم حرفياً (لا مستند افتراضي مفروض) —
#     القائمة الممررة هي التي تُحسب (وNone ⇒ مستند 67 كما في 1.1.0).
# ✅ B-4 MACD حرفياً كما Pine الأصلي CM_MacD_Ult_MTF (ChrisMoody):
#     line = EMA(fast) − EMA(slow) · signal = SMA(line, signal_len)
#     (وليس EMA — تغيير مقصود بأمر صاحب القرار) · hist = line − signal.
# ✅ B-5 أكواد برمجية للتحذيرات: warnings (النص كما كان) +
#     warning_codes + warnings_v2 [{code, message, instance}].
# ✅ B-6 view_times: أزمنة الأعمدة المخزنة (ms) داخل قسم osc نفسه.
# ✅ B-7 crosses: تقاطعات line×signal لكل نسخة MACD متاحة [{index, up}]
#     — بمقاييس أعمدة العرض في نمط view (مطابقة حرفية لبوابة المحرك).
# ✅ B-8 bars = عدد الأعمدة المخزنة فعلاً في نمط view (full_bars = الدقة
#     الكاملة للحقيقة) — عقد الفهرسة الثنائية للفرونت.
#
# 🩸 علة SIGKILL (العمليات 10000312-14): حقن 256 عمود Python بطول 665K
#   في DataFrame الباك-تست ≈ 5-7GB ⇒ قاتل الذاكرة. الحل هنا بنمط التخزين:
#   · مسار المحرك (باك-تست): osc_series="none" — البوابة والعدادات تُحسب
#     على الدقة الكاملة بـ numpy (ميجابايتات)، ولا سلاسل تُخزَّن في الرد
#     (الرسم يأتي من مسار chart-data عبر osc_base المخزّن المدمج).
#   · مسار chart-data: view_times ممرَّر ⇒ السلاسل تُخزَّن عند أعمدة
#     العرض فقط (~20K عمود) محسوبة من الدقة الكاملة ثم معاينة.
#   · مسار الحساب الحي: بلا view_times ⇒ سلاسل كاملة (المدخل ≤ 50K).
#
# صيغ PRO73/74 محفوظة بت-بت (قياس 4 مؤشرات على الإنتاج 2026-11-15):
#   · MACD line: EMA بطريقة talib (بذرة SMA عند period−1 ثم عودية
#     alpha=2/(p+1)) — تطابق 0.0 بت-بت.
#   · RSI: Wilder بطريقة talib (بذرة SMA) — تطابق 2.8e-14.
#   · RSI ma: EMA-talib(value, ma_length) فوق السلسلة المتدرجة — تطابق 0.0.
#   · RSI BB: ma ± bb_std × std سكّاني (ddof=0) نافذة ma_length.
#   · MOM: line = close − close[length] · pct = (close/close[length]−1)×100 —
#     تطابق 0.0 / 1.1e-14.
#   · الإحماء محايد (None قبل البذرة — إصلاح PRO74 محفوظ).
#
# الذرّة الزمنية للمواءمة (بلا أي نظرة مستقبلية):
#   · نسخة بفريم أعلى: الشريط يكتمل بنهاية دلوه؛ عند شمعة القاعدة i
#     نستخدم آخر شريط مكتمل فقط (دلو B(i)−1) — نفس ما يعرفه المتداول حيّاً.
#   · 1mo = دلاء شهر تقويمي (سنة-شهر) · 2w/3d/2d = دلاء مرساة epoch.
# =============================================================================

from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

__all__ = [
    "OSC_CORE_ENGINE", "OSC_CORE_VERSION", "TF_MS", "normalize_timeframe",
    "DEFAULT_OSC_INSTANCES", "FIELDS_PER_KIND", "build_osc_section",
    "compute_osc_section", "build_mtf_osc", "evaluate_conditions",
    "resolve_instances", "osc_series_names", "MtfOscillatorCore",
    "OSC_RULE_TEXT", "detect_base_tf", "sample_numpy_to_view",
]

OSC_CORE_ENGINE = "PRO76-mtf-osc-core"
OSC_CORE_VERSION = "2.0.0"

# ---------------------------------------------------------------- سجل الفريمات
TF_MS: Dict[str, int] = {
    "1s": 1_000, "5s": 5_000, "15s": 15_000, "30s": 30_000,
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
    "6h": 21_600_000, "8h": 28_800_000, "12h": 43_200_000,
    "1d": 86_400_000, "2d": 172_800_000, "3d": 259_200_000,
    "1w": 604_800_000, "2w": 1_209_600_000, "1mo": 2_592_000_000,
}
_TF_ALIASES: Dict[str, str] = {
    "1S": "1s", "5S": "5s", "15S": "15s", "30S": "30s",
    "3M": "3m", "5M": "5m", "15M": "15m", "30M": "30m",
    "1H": "1h", "2H": "2h", "4H": "4h", "6H": "6h", "8H": "8h", "12H": "12h",
    "1D": "1d", "2D": "2d", "3D": "3d", "1W": "1w", "2W": "2w",
    "1MO": "1mo", "M": "1mo", "month": "1mo",
}


def normalize_timeframe(tf: Any) -> Optional[str]:
    """توحيد اسم الفريم — None لغير المعروف.

    عرف الأسماء: '1M' من الواجهة = الدقيقة (عرف فريمات الشموع القصيرة
    كما في نمط points النهايات)؛ الشهر يُطلب صراحة بـ '1mo'/'M'/'month'."""
    if tf is None:
        return None
    s = str(tf).strip()
    if s in TF_MS:
        return s
    if s == "1M":
        return "1m"
    if s in _TF_ALIASES:
        return _TF_ALIASES[s]
    return None


def tf_to_ms(tf: Any) -> Optional[int]:
    key = normalize_timeframe(tf)
    return TF_MS.get(key) if key else None


# ---------------------------------------------------------------- الصيغ (talib-style)

def _ema_talib(x: np.ndarray, period: int) -> np.ndarray:
    """EMA بطريقة talib/TradingView: بذرة SMA عند الفهرس period−1 ثم عودية
    alpha=2/(period+1) — تطابق الإنتاج بت-بت (قياس 2026-11-15)."""
    n = len(x)
    out = np.full(n, np.nan, dtype=np.float64)
    if n < period or period < 1:
        return out
    out[period - 1] = float(np.mean(x[:period]))
    a = 2.0 / (period + 1.0)
    for i in range(period, n):
        out[i] = a * x[i] + (1.0 - a) * out[i - 1]
    return out


def _sma(x: np.ndarray, period: int) -> np.ndarray:
    """SMA عبر pandas rolling (NaN داخل النافذة ⇒ NaN — حياد الإحماء).
    ✅ B-4: خط إشارة MACD = SMA حرفياً كما Pine (sma(macd, signal))."""
    if period < 1 or len(x) < period:
        return np.full(len(x), np.nan, dtype=np.float64)
    return (pd.Series(np.asarray(x, dtype=np.float64))
            .rolling(window=int(period), min_periods=int(period))
            .mean().to_numpy(dtype=np.float64))


def _rolling_std_pop(x: np.ndarray, period: int) -> np.ndarray:
    """الانحراف السكّاني (ddof=0) لنافذة منزلقة — لأشرطة بولينجر RSI
    (نفس إحماء الإنتاج: أول قيمة عند 27 لنسخة 14/14)."""
    if period < 1 or len(x) < period:
        return np.full(len(x), np.nan, dtype=np.float64)
    return (pd.Series(np.asarray(x, dtype=np.float64))
            .rolling(window=int(period), min_periods=int(period))
            .std(ddof=0).to_numpy(dtype=np.float64))


def _rsi_wilder_talib(x: np.ndarray, period: int) -> np.ndarray:
    """RSI بطريقة Wilder/talib — تطابق الإنتاج بت-بت (2.8e-14)."""
    n = len(x)
    out = np.full(n, np.nan, dtype=np.float64)
    if n <= period or period < 1:
        return out
    d = np.diff(x)
    g = np.clip(d, 0.0, None)
    l = np.clip(-d, 0.0, None)
    ag = float(np.mean(g[:period]))
    al = float(np.mean(l[:period]))
    out[period] = 100.0 if al == 0.0 else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(period, n - 1):
        ag = (ag * (period - 1) + g[i]) / period
        al = (al * (period - 1) + l[i]) / period
        out[i + 1] = 100.0 if al == 0.0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def _macd_talib(close: np.ndarray, fast: int, slow: int, signal: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """✅ B-4 — MACD حرفياً كما Pine الأصلي (ChrisMoody):
    line = EMA(fast) − EMA(slow) · signal = SMA(line, signal) · hist = line−signal.
    الإحماء محايد لكل حقل على حدة (قياس الإنتاج الحي 2026-11-15: line أول
    صالح عند slow−1=12 · signal/hist عند 12+signal−1=15 — لا تقنيع متقاطع)."""
    line = _ema_talib(close, int(fast)) - _ema_talib(close, int(slow))
    sig = _sma(line, int(signal))
    hist = line - sig
    return line, sig, hist


def _mom(close: np.ndarray, length: int) -> Tuple[np.ndarray, np.ndarray]:
    """المومنتم: line = close − close[length] · pct = (close/close[length]−1)×100."""
    n = len(close)
    line = np.full(n, np.nan, dtype=np.float64)
    pct = np.full(n, np.nan, dtype=np.float64)
    if n > length and length >= 1:
        prev = close[:-length]
        cur = close[length:]
        line[length:] = cur - prev
        with np.errstate(divide="ignore", invalid="ignore"):
            pct[length:] = np.where(prev != 0.0, (cur / prev - 1.0) * 100.0, np.nan)
    return line, pct


# ---------------------------------------------------------------- المستند الافتراضي (67 — مطابق للحي بت-بت)

def _mi(kind: str, tf: str, *nums: float) -> Dict[str, Any]:
    d: Dict[str, Any] = {"kind": kind, "timeframe": tf,
                         "id": f"{kind}_{tf}_" + "_".join(str(int(x)) for x in nums)}
    if kind == "macd":
        d["params"] = {"fast": int(nums[0]), "slow": int(nums[1]), "signal": int(nums[2])}
    elif kind == "rsi":
        d["params"] = {"period": int(nums[0]), "ma_length": int(nums[1]), "bb_std": 2.0}
    elif kind == "mom":
        d["params"] = {"length": int(nums[0])}
    return d


DEFAULT_OSC_INSTANCES: List[Dict[str, Any]] = [
    _mi("macd", "1s", 6, 13, 4), _mi("macd", "1s", 12, 26, 4),
    _mi("macd", "5s", 6, 13, 4), _mi("macd", "5s", 12, 26, 4),
    _mi("macd", "30s", 6, 13, 4), _mi("macd", "30s", 12, 26, 4),
    _mi("macd", "1m", 6, 13, 4), _mi("macd", "1m", 12, 26, 4),
    _mi("macd", "5m", 6, 13, 4), _mi("macd", "5m", 12, 26, 4),
    _mi("macd", "15m", 6, 13, 4), _mi("macd", "15m", 12, 26, 4),
    _mi("macd", "1h", 6, 13, 4), _mi("macd", "1h", 12, 26, 4),
    _mi("macd", "4h", 6, 13, 4), _mi("macd", "4h", 12, 26, 4),
    _mi("macd", "1d", 6, 13, 4), _mi("macd", "1d", 12, 26, 4),
    _mi("macd", "2d", 6, 13, 4), _mi("macd", "2d", 12, 26, 4),
    _mi("macd", "3d", 5, 11, 4), _mi("macd", "3d", 6, 13, 4), _mi("macd", "3d", 12, 26, 4),
    _mi("macd", "1w", 6, 13, 4), _mi("macd", "1w", 12, 26, 4), _mi("macd", "1w", 18, 39, 4),
    _mi("macd", "2w", 12, 26, 2),
    _mi("macd", "1mo", 12, 26, 2),
    _mi("rsi", "1s", 14, 14), _mi("rsi", "5s", 14, 14), _mi("rsi", "30s", 14, 14),
    _mi("rsi", "1m", 14, 14), _mi("rsi", "5m", 14, 14), _mi("rsi", "15m", 14, 14),
    _mi("rsi", "1h", 14, 14), _mi("rsi", "4h", 14, 14),
    _mi("rsi", "1d", 10, 14), _mi("rsi", "1d", 14, 14),
    _mi("rsi", "2d", 14, 6), _mi("rsi", "2d", 14, 14), _mi("rsi", "3d", 14, 6),
    _mi("rsi", "1w", 14, 14), _mi("rsi", "2w", 14, 14), _mi("rsi", "1mo", 14, 14),
    _mi("mom", "1s", 10), _mi("mom", "5s", 10), _mi("mom", "30s", 10),
    _mi("mom", "1m", 5), _mi("mom", "1m", 10),
    _mi("mom", "5m", 5), _mi("mom", "5m", 10),
    _mi("mom", "15m", 5), _mi("mom", "15m", 10),
    _mi("mom", "1h", 5), _mi("mom", "1h", 10),
    _mi("mom", "4h", 5), _mi("mom", "4h", 10),
    _mi("mom", "1d", 5), _mi("mom", "1d", 10),
    _mi("mom", "2d", 5), _mi("mom", "2d", 10),
    _mi("mom", "3d", 5), _mi("mom", "3d", 10),
    _mi("mom", "1w", 5), _mi("mom", "1w", 10),
    _mi("mom", "1mo", 5), _mi("mom", "1mo", 10),
]

FIELDS_PER_KIND: Dict[str, List[str]] = {
    "rsi": ["value", "ma", "bb_upper", "bb_lower"],
    "macd": ["line", "signal", "hist"],
    "mom": ["line", "pct"],
}

OSC_RULE_TEXT = (
    "الدخول النهائي = إشارة الترندية/الملتهبة المبوّبة (بوابة الترند) ∧ انطباق "
    "شجرة شروط الموشرات القابلة للتركيب (and/or/not بأي عمق) عند شمعة الإشارة "
    "نفسها — المرجع: osc:<id>.<field> أو رقم · المعامل skip_unavailable لكل "
    "شرط (خطأ عند غياب القيمة ما لم يُطلب التخطي)"
)


# ---------------------------------------------------------------- تطبيع الشموع

def _candle_time_ms(r: Any) -> int:
    if isinstance(r, dict):
        v = r.get("time", r.get("timestamp", r.get("t")))
    elif isinstance(r, (list, tuple, np.ndarray)):
        try:
            v = r[0]
        except Exception:
            return 0
    else:
        # ✅ R76: قيمة مفردة (عدد/سلسلة/تاريخ) — كانت تسقط في r[0] فتُرَدّ 0
        # فتنهار مطابقة view_times كلها (أعمدة العرض كلها 0 — T6).
        v = r
    if v is None:
        return 0
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        if f < 1e11:  # ثوانٍ epoch → ملّي
            f *= 1000.0
        return int(f)
    if hasattr(v, "timestamp"):
        return int(v.timestamp() * 1000.0)
    s = str(v)
    try:
        f = float(s)
        if f < 1e11:
            f *= 1000.0
        return int(f)
    except ValueError:
        try:
            return int(_dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000.0)
        except Exception:
            return 0


def _candle_close(r: Any) -> float:
    if isinstance(r, dict):
        v = r.get("close", r.get("c"))
    else:
        try:
            v = r[4]
        except Exception:
            return float("nan")
    try:
        return float(v) if v is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _norm_candles(candles: Any, return_map: bool = False):
    """شموع (dicts أو DataFrame بأعمدة time/close) → (times_ms, closes) مرتبة.

    ✅ PRO76b (return_map): يعيد إضافةً (keep_idx, inv_sorted, n_orig) —
    مواضع الصفوف الناجية في الدخل الأصلي + مرتبتها بعد الترتيب + عدد
    صفوف الدخل، لإعادة محاذاة بوابة القرار على مقاس شموع الدخل نفسها
    (لا إسقاطاً بصمتاً لصفوف «—» مشوّهة ثم بوابة أقصر من سلاسل المحرك —
    جذر IndexError 4d976421)."""
    if candles is None:
        if return_map:
            return (np.array([], dtype=np.int64), np.array([], dtype=np.float64),
                    np.array([], dtype=np.int64), np.array([], dtype=np.int64), 0)
        return np.array([], dtype=np.int64), np.array([], dtype=np.float64)
    if isinstance(candles, pd.DataFrame):
        tcol = "time" if "time" in candles.columns else candles.columns[0]
        ccol = "close" if "close" in candles.columns else candles.columns[-1]
        t = _col_to_ms(candles[tcol])
        c = pd.to_numeric(candles[ccol], errors="coerce").to_numpy(dtype=np.float64)
    elif isinstance(candles, dict) and "time_ms" in candles and "close" in candles:
        # ✅ نمط osc_base المخزّن (R76): {time_ms: [...], close: [...]}
        t = np.asarray(candles["time_ms"], dtype=np.int64)
        c = np.asarray(candles["close"], dtype=np.float64)
    else:
        rows = list(candles)
        t = np.array([_candle_time_ms(r) for r in rows], dtype=np.int64)
        c = np.array([_candle_close(r) for r in rows], dtype=np.float64)
    mask = ~(np.isnan(c) | (t <= 0))
    # ✅ PRO76b: الصفوف الناجية بمواضعها الأصلية (قبل القناع والترتيب)
    keep_idx = np.nonzero(mask)[0]
    t, c = t[mask], c[mask]
    order: Any = None
    if len(t):
        order = np.argsort(t, kind="stable")
        t, c = t[order], c[order]
    if return_map:
        inv_sorted = np.empty(len(t), dtype=np.int64)
        if order is not None:
            inv_sorted[order] = np.arange(len(t), dtype=np.int64)
        return t, c, keep_idx, inv_sorted, int(len(mask))
    return t, c


def _col_to_ms(col: Any) -> np.ndarray:
    s = pd.Series(col)
    if np.issubdtype(s.dtype, np.number):
        v = s.to_numpy(dtype="float64")
        v = np.where(v < 1e11, v * 1000.0, v)
        return v.astype(np.int64)
    ts = pd.to_datetime(s, errors="coerce", utc=True)
    return (ts.astype("int64") // 1_000_000).to_numpy().astype(np.int64)


def detect_base_tf(t: np.ndarray) -> Optional[str]:
    """فريم القاعدة الحقيقي من وسيط تباعد الشموع (الصدق الكامل — B-2).
    غير المسجل → '<med>ms' صريح (كما كان عقد 1.1.0 يبلّغ العرض المضغوط)."""
    if len(t) < 3:
        return None
    d = np.diff(t)
    d = d[d > 0]
    if not len(d):
        return None
    med = int(np.median(d))
    for name in sorted(TF_MS, key=lambda k: TF_MS[k]):
        ms = TF_MS[name]
        if abs(med - ms) <= max(ms * 0.10, 1_000):
            return name
    return f"{med}ms"


# ---------------------------------------------------------------- التجميع والنمذة

def _month_bucket(t: np.ndarray) -> np.ndarray:
    dt = t.astype("datetime64[ms]").astype("datetime64[M]")
    months = dt.astype("int64")
    _, idx = np.unique(months, return_inverse=True)
    return idx


def _bucket_index(t: np.ndarray, tf: str) -> Tuple[np.ndarray, int]:
    """رقم الدلو لكل شمعة + عدد الدلاء. الشهر تقويمي؛ البقية مرساة epoch."""
    if tf == "1mo":
        b = _month_bucket(t)
        return b, int(b[-1]) + 1
    ms = TF_MS[tf]
    t0 = int(t[0]) // ms * ms
    b = (t - t0) // ms
    return b, int(b[-1]) + 1


def _bucket_closes(c: np.ndarray, b: np.ndarray, nb: int) -> np.ndarray:
    """إغلاق كل دلو = إغلاق آخر شمعة فيه (الدلو الفارغ يرث جارَه السابق)."""
    n = len(b)
    if nb <= 0 or n == 0:
        return np.array([], dtype=np.float64)
    last = np.full(nb, -1, dtype=np.int64)
    last[b] = np.arange(n)  # آخر ظهور (الشموع مرتبة زمنياً)
    for i in range(nb):
        if last[i] == -1:
            last[i] = last[i - 1] if i > 0 else 0
    return c[last]


def _stepped_map(b: np.ndarray, n_base: int) -> Tuple[np.ndarray, np.ndarray]:
    """شبكة الدلاء → شبكة القاعدة: آخر شريط أعلى مكتمل فقط (بلا استشراف).

    الشمعة i داخل الدلو B(i) — الشريط B يكتمل مع إغلاق آخر شمعة فيه،
    والقرار يُقيَّم على الشمعة المغلقة i ⇒ الصالح للاستخدام هو الشريط B(i)−1."""
    usable = b - 1
    neg = usable < 0
    usable_clipped = np.where(neg, 0, usable)
    return usable_clipped.astype(np.int64), ~neg


def _map_stepped_arr(arr: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    """يرفع سلسلة دلاء إلى شبكة القاعدة بخطوة «آخر مكتمل» (ndarray)."""
    bi, ok = _stepped_map(b, n)
    out = np.full(n, np.nan, dtype=np.float64)
    idx_ok = np.where(ok)[0]
    if len(idx_ok) and len(arr):
        take = np.clip(bi[idx_ok], 0, len(arr) - 1)
        out[idx_ok] = arr[take]
    return out


def _tolist(arr: np.ndarray) -> List[Optional[float]]:
    """ndarray → قائمة JSON (NaN → None — حياد الإحماء)."""
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)
            for v in np.asarray(arr, dtype=np.float64)]


def compute_instance_series(inst: Dict[str, Any], t: np.ndarray, c: np.ndarray,
                            base_tf: str) -> Dict[str, np.ndarray]:
    """سلاسل نسخة واحدة على شبكة شموع القاعدة — **ndarray** (ذاكرة محكمة:
    665K × 8 بايت للسلسلة، لا قوائم Python). فارغ إذا كانت أدنى من القاعدة."""
    kind = str(inst.get("kind", "")).lower()
    tf = normalize_timeframe(inst.get("timeframe"))
    if tf is None:
        return {}
    inst_ms = TF_MS.get(tf)
    base_ms = TF_MS.get(base_tf) if base_tf in TF_MS else None
    if inst_ms is None or base_ms is None or inst_ms < base_ms:
        return {}
    n = len(t)
    if n == 0:
        return {}
    p = inst.get("params") or {}
    same = (tf == base_tf)

    if kind == "macd":
        fast = int(p.get("fast", 12)); slow = int(p.get("slow", 26)); sig = int(p.get("signal", 9))
        if same:
            line, sg, hist = _macd_talib(c, fast, slow, sig)
            return {"line": line, "signal": sg, "hist": hist}
        b, nb = _bucket_index(t, tf)
        cb = _bucket_closes(c, b, nb)
        line, sg, hist = _macd_talib(cb, fast, slow, sig)
        return {"line": _map_stepped_arr(line, b, n),
                "signal": _map_stepped_arr(sg, b, n),
                "hist": _map_stepped_arr(hist, b, n)}

    if kind == "rsi":
        period = int(p.get("period", 14)); ma_len = int(p.get("ma_length", 14))
        bb_std = float(p.get("bb_std", 2.0))
        if same:
            val = _rsi_wilder_talib(c, period)
        else:
            b, nb = _bucket_index(t, tf)
            cb = _bucket_closes(c, b, nb)
            v_h = _rsi_wilder_talib(cb, period)
            val = _map_stepped_arr(v_h, b, n)
        ma = _ema_talib_nan(val, ma_len)
        sd = _rolling_std_pop(val, ma_len)
        return {"value": val, "ma": ma,
                "bb_upper": ma + bb_std * sd, "bb_lower": ma - bb_std * sd}

    if kind == "mom":
        length = int(p.get("length", 10))
        if same:
            line, pct = _mom(c, length)
            return {"line": line, "pct": pct}
        b, nb = _bucket_index(t, tf)
        cb = _bucket_closes(c, b, nb)
        ln_h, pct_h = _mom(cb, length)
        return {"line": _map_stepped_arr(ln_h, b, n),
                "pct": _map_stepped_arr(pct_h, b, n)}
    return {}


def _ema_talib_nan(x: np.ndarray, period: int) -> np.ndarray:
    """EMA-talib فوق سلسلة فيها فجوات NaN: البذرة عند أول period قيم صالحة،
    والفجوات بعد البذرة تُثبّت آخر قيمة (حياد الإحماء فقط قبل البذرة)."""
    n = len(x)
    out = np.full(n, np.nan, dtype=np.float64)
    nn = np.where(~np.isnan(x))[0]
    if len(nn) < period or period < 1:
        return out
    seed_i = int(nn[period - 1])
    out[seed_i] = float(np.mean(x[nn[:period]]))
    a = 2.0 / (period + 1.0)
    last = out[seed_i]
    for i in range(seed_i + 1, n):
        if np.isnan(x[i]):
            out[i] = last
        else:
            last = a * x[i] + (1.0 - a) * last
            out[i] = last
    return out


# ---------------------------------------------------------------- شجرة الشروط

_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: abs(a - b) < 1e-12,
    "!=": lambda a, b: abs(a - b) >= 1e-12,
}


def _lookup_ref(ref: Any, series_lookup: Dict[str, Any], i: int) -> Tuple[bool, Optional[float]]:
    """يحل المرجع: رقم مباشر · osc:<id>.<field> · price:<col> (من المحرك).
    السلاسل قد تكون ndarray (ذاكرة محكمة) أو قوائم."""
    if isinstance(ref, (int, float)) and not isinstance(ref, bool):
        return True, float(ref)
    s = str(ref)
    low = s.lower()
    if low.startswith("osc:") or low.startswith("price:"):
        arr = series_lookup.get(low)
        if arr is None or i >= len(arr):
            return False, None
        v = arr[i]
        if v is None:
            return False, None
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return False, None
        if np.isnan(fv):
            return False, None
        return True, fv
    try:
        return True, float(s)
    except ValueError:
        return False, None


def evaluate_conditions(node: Any, series_lookup: Dict[str, Any], i: int) -> bool:
    """تقييم شجرة الشروط عند الشمعة المغلقة i (بلا أي نظرة مستقبلية).

    الأوراق: {left, op, right, skip_unavailable} — المرجع osc:<id>.<field>.
    قيمة مفقودة ⇒ الورقة False ما لم يُطلب skip_unavailable=True.
    العقد: {logic: and|or|not, conditions: [...]}; not = نفي أول عنصر."""
    if node is None:
        return True
    if isinstance(node, bool):
        return node
    if isinstance(node, (int, float)):
        return bool(node)
    if isinstance(node, list):
        return all(evaluate_conditions(sub, series_lookup, i) for sub in node)
    if not isinstance(node, dict):
        return True
    if "left" in node and "op" in node:
        ok_l, v_l = _lookup_ref(node.get("left"), series_lookup, i)
        ok_r, v_r = _lookup_ref(node.get("right"), series_lookup, i)
        if not (ok_l and ok_r):
            return bool(node.get("skip_unavailable", False))
        fn = _OPS.get(str(node.get("op", ">")))
        if fn is None:
            return False
        return bool(fn(v_l, v_r))
    logic = str(node.get("logic", "and")).lower()
    subs = node.get("conditions") or []
    if not isinstance(subs, list):
        subs = [subs]
    if not subs:
        return True
    if logic == "not":
        return not evaluate_conditions(subs[0], series_lookup, i)
    if logic == "or":
        return any(evaluate_conditions(sub, series_lookup, i) for sub in subs)
    return all(evaluate_conditions(sub, series_lookup, i) for sub in subs)


# ---------------------------------------------------------------- التقاطعات (B-7)

def _macd_crosses_np(line: np.ndarray, sig: np.ndarray,
                      cap: int = 20000) -> List[Dict[str, Any]]:
    """تقاطعات line×signal: [{index, up}] — up=true عند صعود الخط فوق الإشارة."""
    n = min(len(line), len(sig))
    out: List[Dict[str, Any]] = []
    if n == 0:
        return out
    diff = line[:n] - sig[:n]
    valid = ~(np.isnan(diff))
    idx = np.where(valid)[0]
    if len(idx) < 2:
        return out
    d = diff[idx]
    for j in range(1, len(idx)):
        pd_prev, pd_cur = d[j - 1], d[j]
        if pd_prev <= 0.0 < pd_cur:
            out.append({"index": int(idx[j]), "up": True})
        elif pd_prev >= 0.0 > pd_cur:
            out.append({"index": int(idx[j]), "up": False})
        if len(out) >= cap:
            break
    return out


def sample_numpy_to_view(arr: np.ndarray, view_idx: np.ndarray,
                          hit: Optional[np.ndarray] = None) -> List[Optional[float]]:
    """عينة ndarray عند فهارس الأعمدة المخزنة → قائمة JSON (NaN→None).

    ✅ PRO76b (HF-A): hit — قناع فوق أعمدة العرض: العمود غير الممثَّل في
    القاعدة (انقطاع/صف مشوّه) يُخزَّن None بدل قيمة الجار المقصورة:
    مقياس العرض = عدد أعمدة العرض نفسها دائماً، لا مقياس المطابقات فقط."""
    if not len(view_idx) or not len(arr):
        return [None] * len(view_idx)
    take = np.clip(view_idx, 0, len(arr) - 1)
    vals = arr[take]
    out = [None if np.isnan(v) else float(v) for v in vals]
    if hit is not None:
        for k in np.nonzero(~np.asarray(hit, dtype=bool))[0]:
            if 0 <= int(k) < len(out):
                out[int(k)] = None
    return out


def _warmup_neutral_horizon(
    conditions: Any,
    combined_lookup: Dict[str, Any],
    n: int,
) -> int:
    """✅ PRO76b (P2) — أفق حياد الإحماء (عقد R74 داخل نواة R76).

    أقصى «أول شريط صالح» عبر كل الأوراق المرجعية بالشجرة (سلاسل النسخ
    المتاحة فقط). قبل هذا الشريط قد تكون قيمة الشجرة False لمجرد أن
    مؤشراً لم تدخل قيمه بعد (NaN الإحماء) — فالحجب زورٌ بلا حكم.
    القاعدة: قبل الأفق البوابة محايدة (مفتوحة)؛ بعده التقييم الطبيعي.
    (كانت مفقودة من نواة PRO76 — انحدار «بوابة الإحماء مغلقة لا محايدة».)
    """
    horizon = 0
    if not isinstance(conditions, dict):
        return horizon

    def _arr_of(ref: Any) -> Optional[np.ndarray]:
        if not (isinstance(ref, str) and ref.lower().startswith("osc:")):
            return None
        return combined_lookup.get(ref.lower())

    def _first_valid(arr: Any) -> int:
        try:
            a = np.asarray(arr, dtype=np.float64)
        except (TypeError, ValueError):
            return n
        if not len(a):
            return n
        try:
            fin = ~np.isnan(a)
        except TypeError:
            return n
        if not bool(fin.any()):
            return n
        return int(np.argmax(fin))

    def _walk(node: Any) -> None:
        nonlocal horizon
        if not isinstance(node, dict):
            return
        if ("logic" in node) and isinstance(node.get("conditions"), (list, tuple)):
            for child in node["conditions"]:
                _walk(child)
            return
        for k in ("left", "right"):
            arr = _arr_of(node.get(k))
            if arr is None:
                continue
            h = _first_valid(arr)
            if h < n and h > horizon:
                horizon = h

    _walk(conditions)
    return horizon


# ---------------------------------------------------------------- توحيد النسخ (B-3)

def resolve_instances(osc_instances: Any) -> List[Dict[str, Any]]:
    """توحيد نسخ المستخدم: قوائم dicts (عقد R74 الحي: معاملات مسطحة أو
    داخل params) أو معرّفات نصية — None ⇒ المستند الافتراضي الكامل 67."""
    if osc_instances is None:
        out = []
        for i, inst in enumerate(DEFAULT_OSC_INSTANCES):
            d = dict(inst)
            d["index"] = i
            d["enabled"] = True
            out.append(d)
        return out
    if isinstance(osc_instances, dict):
        # قاموس واحد = نسخة واحدة (وليس فهرساً)
        first = next(iter(osc_instances.values()), None) if osc_instances else None
        if isinstance(first, dict) and "kind" in first:
            osc_instances = [osc_instances]
        elif "kind" in osc_instances:
            osc_instances = [osc_instances]
        else:
            osc_instances = list(osc_instances.values())
    if not isinstance(osc_instances, (list, tuple)):
        return []
    out: List[Dict[str, Any]] = []
    for i, raw in enumerate(osc_instances):
        if raw is None:
            continue
        if isinstance(raw, str):
            raw = {"id": raw.strip()}
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind", "")).strip().lower()
        tf = normalize_timeframe(raw.get("timeframe"))
        params = raw.get("params") or {}
        flat = {k: v for k, v in raw.items()
                if k not in ("kind", "id", "timeframe", "index", "enabled", "doc", "params")}
        merged: Dict[str, Any] = {}
        merged.update(flat)
        merged.update({k: v for k, v in params.items()})
        d: Dict[str, Any] = {"kind": kind, "timeframe": tf or ""}
        if kind == "macd":
            f = int(merged.get("fast", 12)); s = int(merged.get("slow", 26)); g = int(merged.get("signal", 9))
            d["params"] = {"fast": f, "slow": s, "signal": g}
            d["id"] = str(raw.get("id") or f"macd_{tf}_{f}_{s}_{g}")
        elif kind == "rsi":
            p_ = int(merged.get("period", 14)); m_ = int(merged.get("ma_length", 14))
            b_ = float(merged.get("bb_std", 2.0))
            d["params"] = {"period": p_, "ma_length": m_, "bb_std": b_}
            d["id"] = str(raw.get("id") or f"rsi_{tf}_{p_}_{m_}")
        elif kind == "mom":
            L = int(merged.get("length", 10))
            d["params"] = {"length": L}
            d["id"] = str(raw.get("id") or f"mom_{tf}_{L}")
        else:
            d["params"] = merged
            d["id"] = str(raw.get("id") or f"{kind}_{tf}")
        if raw.get("doc"):
            d["doc"] = raw["doc"]
        d["index"] = int(raw.get("index", i))
        d["enabled"] = bool(raw.get("enabled", True))
        out.append(d)
    return out


def _collect_condition_refs(node: Any) -> set:
    """✅ R76 (ذاكرة) — مراجع شجرة الشروط (osc:<id>.<field> · price:<عمود>).

    يجمعها مسبقاً كي تُحسب فقط النسخ المطلوبة للبوابة ويُتخلص من مصفوفات
    البقية فور أخذ العينات (ذروة ذاكرة نافذة البطل: ~1.4GB → ~150MB)."""
    refs: set = set()
    if node is None:
        return refs
    if isinstance(node, (list, tuple)):
        for sub in node:
            refs |= _collect_condition_refs(sub)
        return refs
    if not isinstance(node, dict):
        return refs
    if "left" in node and "op" in node:
        for side in ("left", "right"):
            v = node.get(side)
            if isinstance(v, str):
                low = v.lower()
                if low.startswith("osc:") or low.startswith("price:"):
                    refs.add(low)
        return refs
    for sub in (node.get("conditions") or []):
        refs |= _collect_condition_refs(sub)
    return refs


def _price_lookup_arrays(candles: Any, wanted_cols: set) -> Dict[str, np.ndarray]:
    """✅ R76 — أعمدة price:<عمود> المطلوبة فقط، ك ndarray بطول الدقة الكاملة.

    يقبل قاموس osc_base ({time_ms, close} — close فقط) أو قائمة شموع أو
    DataFrame. الأعمدة الغائبة تُتجاهل بلا سقوط (المرجع الغائب = False
    fail-closed كما في عقد الشروط)."""
    out: Dict[str, np.ndarray] = {}
    try:
        if isinstance(candles, pd.DataFrame):
            for col in wanted_cols:
                if col in candles.columns:
                    out[f"price:{col}"] = pd.to_numeric(
                        candles[col], errors="coerce").to_numpy(dtype=np.float64)
            return out
        if isinstance(candles, dict) and "close" in candles:
            if "close" in wanted_cols:
                out["price:close"] = np.asarray(candles["close"], dtype=np.float64)
            return out
        rows = list(candles)
        for col in wanted_cols:
            vals = []
            for r in rows:
                if isinstance(r, dict):
                    v = r.get(col)
                else:
                    try:
                        v = r[{"open": 1, "high": 2, "low": 3, "close": 4,
                               "volume": 5}.get(col, -1)]
                    except Exception:
                        v = None
                try:
                    vals.append(float(v) if v is not None else float("nan"))
                except (TypeError, ValueError):
                    vals.append(float("nan"))
            out[f"price:{col}"] = np.asarray(vals, dtype=np.float64)
    except Exception:
        return out
    return out


def osc_series_names(inst: Dict[str, Any], prefix: str) -> List[str]:
    """أسماء سلاسل النسخة: {prefix}_osc_{id}_{field}."""
    return [f"{prefix}_osc_{inst['id']}_{f}"
            for f in FIELDS_PER_KIND.get(str(inst.get("kind", "")).lower(), [])]


# ---------------------------------------------------------------- الباني الرئيسي

def build_osc_section(
    candles: Any,
    *,
    base_timeframe: Any = None,
    osc_instances: Any = None,
    osc_conditions: Any = None,
    view_times: Optional[Sequence[Any]] = None,
    resolution: str = "full",
    prefix: str = "zzfetm",
    entry_series: Optional[Sequence[Optional[float]]] = None,
    entry_label: str = "trend_entries",
    sample_step: int = 1,
    osc_series: str = "full",
) -> Dict[str, Any]:
    """يبني قسم osc الكامل (عقد 1.1.0 + إضافات R76) بذاكرة محكمة.

    candles: شموع القاعدة (أدق المتاح — dicts أو DataFrame بأعمدة
    time/close أو قاموس osc_base المخزّن {time_ms, close}). فريم القاعدة
    يُستنتج من التباعد الفعلي؛ إذا كانت الشموع أدق من المطلوب صراحة فالقاعدة
    الفعلية = أدق شمعة (B-1: نسخ الثواني تعمل عند توفر شموع أدق).

    أنماط التخزين (osc_series) — علاج علة SIGKILL:
      · "full"  (مسار الحساب الحي): سلاسل كاملة بطول المدخل.
      · "view"  (مسار chart-data): يُحسب على الدقة الكاملة ثم تُخزَّن عينات
        عند view_times فقط (B-2) — bars = عدد أعمدة العرض (B-8) وfull_bars
        = الدقة الكاملة.
      · "none"  (مسار محرك الباك-تست): بوابات وعدادات فقط — لا سلاسل في
        الرد (الرسم يُبنى لاحقاً من osc_base المخزّن عبر مسار chart-data).

    entry_series: سلسلة دخول المحرك الخام (قبل بوابة الموشرات) للعدادات.
    entry_label: اسم عداد الدخول الخام (trend_entries / blazing_entries).

    يعيد: {"section", "series", "gate" (list[bool] بطول الدقة الكاملة),
           "gate_view" (بمقياس أعمدة العرض كلها — PRO76b)، "gate_orig"
           (بمقياس صفوف الدخل الأصلية — PRO76b)، "lookup" (ndarray),
           "base_tf", "n"}."""
    t, c, keep_idx, inv_sorted, n_orig = _norm_candles(candles, return_map=True)
    n = len(t)
    detected = detect_base_tf(t) if n else None
    requested = normalize_timeframe(base_timeframe) or detected
    base_tf = requested or detected or "1m"
    base_ms = TF_MS.get(base_tf)
    # ✅ الصدق (B-2): الشموع أدق من المطلوب ⇒ القاعدة الفعلية هي أدق شمعة
    if detected in TF_MS and base_ms is not None and TF_MS[detected] < base_ms:
        base_tf = detected
        base_ms = TF_MS[detected]

    # نمط العرض: view_times صالحة ⇒ عينات عند أعمدة العرض المخزنة
    mode = str(osc_series).strip().lower()
    if mode not in ("full", "view", "none"):
        mode = "full"
    view_idx = np.array([], dtype=np.int64)
    view_hit: Optional[np.ndarray] = None
    view_ms: List[int] = []
    if view_times is not None and mode != "none":
        vt = np.array([_candle_time_ms(v) for v in list(view_times)], dtype=np.int64)
        pos = np.searchsorted(t, vt)
        pos_c = np.clip(pos, 0, max(n - 1, 0))
        hit = (pos_c < n) & (t[pos_c] == vt) if n else np.zeros(len(vt), dtype=bool)
        # ✅ PRO76b (HF-A): مقياس العرض = عدد أعمدة العرض نفسها دائماً —
        # الأعمدة غير الممثَّلة في القاعدة (انقطاع/صف مشوّه) تُدار عند أخذ
        # العينات (None للقيم، حياد للبوابة) لا بقصّ المقياس إلى المطابقات
        # فقط — فلا تعود البوابة أقصر من سلاسل المحرك (جذر انهيار 4d976421
        # عند L133: بوابة بطول المطابقات تُطبَّق على حلقة بطول الشموع).
        view_idx = pos_c
        view_hit = hit
        view_ms = [int(x) for x in vt]
        if len(vt) and n and (len(vt) != n or not bool(hit.all())):
            mode = "view"  # انقطاعات موجودة أو مقياس مختلف — عينات مُدارة
        # (كل الأعمدة موجودة ومطابقة ⇒ "full" — لا حاجة لأخذ عينات)

    instances = resolve_instances(osc_instances)
    warnings: List[str] = []
    warnings_v2: List[Dict[str, Any]] = []
    warning_codes: List[str] = []

    def _warn(code: str, message: str, instance: Optional[str] = None) -> None:
        warnings.append(message)
        warnings_v2.append({"code": code, "message": message, "instance": instance})
        if code not in warning_codes:
            warning_codes.append(code)

    series: Dict[str, List[Optional[float]]] = {}
    inst_meta: List[Dict[str, Any]] = []
    crosses: Dict[str, List[Dict[str, Any]]] = {}

    # ✅ R76 (ذاكرة + عقد الشروط): مراجع الشجرة تُجمع مسبقاً — لا تُحسب إلا
    # النسخ المعروضة أو المطلوبة للبوابة، ويُتخلص من مصفوفات غيرها فور
    # أخذ العينات (ذروة نافذة البطل: ~1.4GB → ~150MB). مفاتيح lookup
    # بالبادئة التعاقدية الكاملة (osc:/price:) — كانت بلا بادئة بينما
    # _lookup_ref يبحث بها فلم يكن أي مرجع يُحلّ أبداً (علة مكتشفة في R76).
    conditions = osc_conditions if osc_conditions is not None else None
    refs: set = _collect_condition_refs(conditions) if conditions else set()
    combined_lookup: Dict[str, np.ndarray] = {}
    if any(r.startswith("price:") for r in refs):
        wanted_price = {r[len("price:"):] for r in refs if r.startswith("price:")}
        combined_lookup.update(_price_lookup_arrays(candles, wanted_price))

    for inst in instances:
        meta: Dict[str, Any] = {
            "id": inst["id"], "kind": inst["kind"], "timeframe": inst["timeframe"],
            "index": inst["index"], "params": inst["params"], "enabled": inst["enabled"],
        }
        if not inst["enabled"]:
            meta.update({"available": False, "why": "disabled", "code": "disabled"})
            inst_meta.append(meta)
            if mode == "full":
                for nm in osc_series_names(inst, prefix):
                    series[nm] = [None] * n
            continue
        tf = normalize_timeframe(inst["timeframe"])
        tf_ms = TF_MS.get(tf) if tf else None
        if tf is None or tf_ms is None:
            meta.update({"available": False, "why": "unknown_timeframe", "code": "unknown_timeframe"})
            _warn("unknown_timeframe",
                  f"النسخة '{inst['id']}' ({inst['kind']} {inst['timeframe']}): فريم غير معروف — القيم None",
                  inst["id"])
            inst_meta.append(meta)
            if mode == "full":
                for nm in osc_series_names(inst, prefix):
                    series[nm] = [None] * n
            continue
        if base_ms is not None and tf_ms < base_ms:
            meta.update({"available": False, "why": "tf_below_base", "code": "tf_below_base"})
            _warn("tf_below_base",
                  f"النسخة '{inst['id']}' ({inst['kind']} {tf}): الفريم أدنى من فريم شموع القاعدة "
                  f"({base_tf}) — لا يمكن بناؤه من بيانات أسمك؛ القيم None (مرر شموعاً أدق لبنائه)",
                  inst["id"])
            inst_meta.append(meta)
            if mode == "full":
                for nm in osc_series_names(inst, prefix):
                    series[nm] = [None] * n
            continue
        inst_id_l = str(inst["id"]).lower()
        inst_ref_prefix = f"osc:{inst_id_l}."
        # ✅ R76 (ذاكرة): نمط المحرك (none) يحتاج فقط النسخ المُشار إليها
        # بالبوابة — ما سواها لا يُحسب أصلاً (لا سلاسل تُخزَّن ولا داعي لها).
        needed_for_gate = any(r.startswith(inst_ref_prefix) for r in refs)
        if mode == "none" and not needed_for_gate:
            meta.update({"available": True, "why": None, "code": None,
                         "computed": False,
                         "note": "نمط المحرك: غير مطلوبة للبوابة ولا للعرض — لم تُحسب"})
            inst_meta.append(meta)
            continue
        vals = compute_instance_series(inst, t, c, base_tf)
        if not vals:
            meta.update({"available": False, "why": "insufficient_data", "code": "insufficient_data"})
            _warn("insufficient_data",
                  f"النسخة '{inst['id']}': بيانات غير كافية لحسابها في هذه النافذة — القيم None",
                  inst["id"])
            inst_meta.append(meta)
            if mode == "full":
                for nm in osc_series_names(inst, prefix):
                    series[nm] = [None] * n
            continue
        meta.update({"available": True, "why": None, "code": None})
        inst_meta.append(meta)
        # التقاطعات تحتاج line/signal قبل التخلص الذكي من المصفوفات
        arr_line = vals.get("line")
        arr_sig = vals.get("signal")
        for field, arr in vals.items():
            ref_key = f"osc:{inst_id_l}.{str(field).lower()}"
            if ref_key in refs:
                combined_lookup[ref_key] = arr
            nm = f"{prefix}_osc_{inst['id']}_{field}"
            if mode == "full":
                series[nm] = _tolist(arr)
            elif mode == "view":
                # ✅ PRO76b (HF-A): العينات بمقياس أعمدة العرض كلها —
                # الانقطاع None لا قيمة جار مقصورة
                series[nm] = sample_numpy_to_view(arr, view_idx, view_hit)
        # ✅ B-7: التقاطعات (بمقاييس التخزين الفعلي للفرونت)
        if inst["kind"] == "macd":
            cr = _macd_crosses_np(arr_line if arr_line is not None else np.array([]),
                                  arr_sig if arr_sig is not None else np.array([]))
            if mode == "view" and len(cr) and view_hit is not None:
                # ✅ PRO76b: الخريطة من موضع القاعدة إلى فهرس عمود العرض —
                # أعمدة الانقطاع لا تُخدع بجار مقصور
                hit_cols = np.nonzero(view_hit)[0]
                pos_map = {int(view_idx[k]): int(k) for k in hit_cols}
                cr = [{"index": pos_map[int(x["index"])], "up": x["up"]}
                      for x in cr if int(x["index"]) in pos_map]
            if mode != "none":
                crosses[inst["id"]] = cr
        vals = None  # 🩸 ذاكرة: تحرير مصفوفات النسخة بعد أخذ العينات/التقاطعات

    # شجرة الشروط + البوابة (عند الشمعة المغلقة نفسها — بلا استشراف،
    # وبطول الدقة الكاملة دائماً: البوابة قرار تداول لا قرار عرض)
    if conditions:
        gate: List[bool] = [bool(evaluate_conditions(conditions, combined_lookup, i)) for i in range(n)]
    else:
        gate = [True] * n

    # ✅ PRO76b (P2 — استعادة عقد حياد الإحماء R74 داخل النواة): قبل
    # جاهزية كل الأوراق المرجعية تكون قيمة الشجرة False لمجرد NaN الإحماء
    # — لا يُحجب دخولٌ زوراً في أسابيع/أشهر البداية الباردة (الباك-تستات).
    # القاعدة: قبل الأفق البوابة محايدة (مفتوحة)؛ بعده التقييم الطبيعي.
    warmup_neutral_bars = 0
    if conditions and n:
        try:
            warmup_neutral_bars = _warmup_neutral_horizon(conditions, combined_lookup, n)
        except Exception:  # noqa: BLE001 — حزام احتياطي: الحياد أمان لا فشل
            warmup_neutral_bars = 0
        if warmup_neutral_bars > 0:
            gate = list(gate)
            for j in range(min(warmup_neutral_bars, n)):
                gate[j] = True
            _warn("warmup_neutral",
                  f"حياد الإحماء: البوابة مفتوحة لأول {warmup_neutral_bars} شريط (إحماء الموشرات) — "
                  "عقد R74 المُستعاد داخل نواة R76", None)

    # ✅ PRO76b (HF-A): بوابة بمقياس صفوف الدخل الأصلية — قرار المحرك
    # يُفهرس بشموعه لا بصفوف القاعدة المُنقاة/المرتبة. الصفوف المسقوطة
    # (قيم «—»/طوابع معطوبة) تبقى حياداً (True): لا حجب على بيانات غائبة
    # — والبوابة لا تعود أقصر من سلاسل المحرك (جذر IndexError 4d976421
    # والانحدارات الصامتة فوق البيانات ذات الفجوات).
    gate_orig: Optional[List[bool]] = None
    _order_identity = bool(
        len(inv_sorted) == 0 or np.array_equal(inv_sorted, np.arange(len(inv_sorted))))
    if n_orig != len(t) or not _order_identity:
        gate_orig = [True] * n_orig
        for i in range(len(keep_idx)):
            gate_orig[int(keep_idx[i])] = bool(gate[int(inv_sorted[i])])
        if n_orig != len(t):
            _warn("gate_realigned",
                  f"بوابة الموشرات أُعيدت محاذاتها على شموع الدخل ({n_orig} صفّاً؛ سقط "
                  f"{n_orig - len(t)} صفّاً مشوّهاً من القاعدة — حياد للصفوف الغائبة)", None)
    else:
        gate_orig = gate

    # ✅ R76 (B-2): بوابة عند أعمدة العرض — لطبقة الرسم في مسار chart-data
    # عندما يكون مصدر الحساب osc_base بالدقة الكاملة (تُطبّق على سلسلة دخول
    # بطول العرض المخزّن فيتوافق المقياسان حرفياً).
    # ✅ PRO76b (HF-A): مقياس gate_view = عدد أعمدة العرض كلها — العمود
    # غير الممثَّل في القاعدة (انقطاع) حياد (True): لا حجب عرضٍ على بيانات
    # غائبة، ولا سوء تطابق أطوال يكسر المحركات فوقه.
    gate_view: Optional[List[bool]] = None
    if mode == "view" and len(view_idx):
        gate_view = []
        for k in range(len(view_idx)):
            if view_hit is not None and not bool(view_hit[k]):
                gate_view.append(True)
            else:
                gate_view.append(bool(gate[int(view_idx[k])]))

    # العدادات على سلسلة دخول المحرك الخام (أساس الدقة الكاملة — أو أساس
    # العرض إذا كانت السلسلة الخام بطول أعمدة العرض: مسار chart-data)
    if entry_series is not None:
        raw = list(entry_series)
        if gate_view is not None and len(raw) == len(gate_view):
            g_basis = gate_view
        else:
            g_basis = gate
        trend_entries = 0
        final_entries = 0
        blocked = 0
        for i in range(min(len(raw), len(g_basis))):
            if raw[i]:
                trend_entries += 1
                if g_basis[i]:
                    final_entries += 1
                else:
                    blocked += 1
        counts: Dict[str, Any] = {entry_label: trend_entries,
                                  "final_entries": final_entries,
                                  "osc_blocked_entries": blocked}
        gate_open = (blocked == 0) if trend_entries else True
        if gate_view is not None and len(raw) == len(gate_view):
            counts["counts_basis"] = "view"
    else:
        counts = {entry_label: 0, "final_entries": 0, "osc_blocked_entries": 0}
        gate_open = True

    stored_bars = len(view_idx) if mode == "view" else n
    section: Dict[str, Any] = {
        "enabled": True,
        "engine": OSC_CORE_ENGINE,
        "version": OSC_CORE_VERSION,
        "base_tf": base_tf,
        "base_tf_ms": base_ms,
        "bars": stored_bars,
        "instances": inst_meta,
        "conditions": conditions,
        "warnings": warnings,
        # ✅ B-5: أكواد برمجية لكل تحذير
        "warning_codes": warning_codes,
        "warnings_v2": warnings_v2,
        "fields_per_kind": FIELDS_PER_KIND,
        "rule": OSC_RULE_TEXT,
        "counts": counts,
        "gate_open": gate_open,
        # ✅ B-7: التقاطعات جاهزة من الباك اند
        "crosses": crosses,
        # ✅ B-2: شفافية الدقة ومصدر الحساب
        "resolution": ("view_sampled_from_full" if mode == "view"
                       else ("engine_run" if mode == "none" else resolution)),
        "view_sampled": bool(mode == "view"),
        "view_step": int(sample_step) if int(sample_step) > 1 else 1,
        # ✅ PRO76b (P2/P5): شفافية الحياد والحالة داخل القسم نفسه
        "warmup_neutral_bars": int(warmup_neutral_bars),
        "mode": mode,
        "status": ("ok" if not warning_codes else "degraded"),
    }
    if mode == "view":
        section["full_bars"] = n  # الدقة الكاملة التي حُسبت عليها (B-8)
        # ✅ PRO76b (HF-A): عدد أعمدة العرض غير الممثّلة في القاعدة (انقطاعات)
        if view_hit is not None:
            _gaps = int(np.count_nonzero(~np.asarray(view_hit, dtype=bool)))
            if _gaps:
                section["view_gaps"] = _gaps
    # ✅ B-6: أزمنة الأعمدة المخزنة داخل قسم osc نفسه — أعمدة العرض كلها
    # (PRO76b: كانت تُقصّ إلى المطابقات فقط فتخون الفرونت عن الأعمدة الغائبة)
    if view_ms:
        section["view_times"] = view_ms
    elif view_times is not None and mode != "none":
        section["view_times"] = [_candle_time_ms(v) for v in list(view_times)]
    if mode == "view":
        # شفافية أساس العدادات في مسار العرض (B-8/B-2)
        section.setdefault("counts_basis", "view")
    return {"section": section, "series": series, "gate": gate, "gate_view": gate_view,
            "gate_orig": gate_orig, "lookup": combined_lookup, "base_tf": base_tf, "n": n}


# أسماء بديلة للتوافق مع مسارات استدعاء PRO73/74 القديمة
def compute_osc_section(candles: Any, **kw: Any) -> Dict[str, Any]:
    return build_osc_section(candles, **kw)


def build_mtf_osc(candles: Any, **kw: Any) -> Dict[str, Any]:
    return build_osc_section(candles, **kw)


class MtfOscillatorCore:
    """واجهة صنفية اختيارية (نفس عقود الدوال)."""

    engine = OSC_CORE_ENGINE
    version = OSC_CORE_VERSION

    def build(self, candles: Any, **kw: Any) -> Dict[str, Any]:
        return build_osc_section(candles, **kw)

    @staticmethod
    def instances() -> List[Dict[str, Any]]:
        return DEFAULT_OSC_INSTANCES


def __getattr__(name: str):
    """توافق مركّب: محركا الماكد يُصدَّران من وحدتيهما (بلا استيراد دائري)."""
    if name in ("zigzag_fib_e2e_trendy_macd", "zigzag_fib_e2e_blazing_macd"):
        import importlib as _il
        mod = _il.import_module(
            "app.services.indicators.overlays_zlf_e2e_trendy_macd"
            if name == "zigzag_fib_e2e_trendy_macd"
            else "app.services.indicators.overlays_zlf_e2e_blazing_macd"
        )
        return getattr(mod, name)
    raise AttributeError(name)
