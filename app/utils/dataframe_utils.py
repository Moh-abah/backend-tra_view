"""Shared DataFrame utilities.

``ensure_datetime_index`` normalizes candle DataFrames to a DatetimeIndex.

Why: ``DataService.get_historical`` returns a RangeIndex (0..n) with a
``time`` column in epoch milliseconds. The backtest engine (engine1) already
converts this centrally, but the direct strategy endpoints
(``/strategies/run``, ``/strategies1/run*``) consumed the raw frame, so any
code doing ``data.index[i].isoformat()`` or
``(t2 - t1).total_seconds()`` crashed with
``'int' object has no attribute ...`` — the "0 signals / generic failure"
class of bugs. This helper mirrors engine1's logic in one place.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# تجميع الفريمات المركبة (resample) — مشترك بين REST candles وWS init
# ---------------------------------------------------------------------------
# الفريمات التي لا يوفرها Binance/Yahoo مباشرة وتُبنى من فريم أساسي:
#   2m ← 1m×2 | 10m ← 5m×2 | 2d ← 1d×2 | 2w ← 1d×14 | 1M ← 1d×31 تقويم شهري
# ملاحظة 2w: الأساس 1d وليس 1w — لأن كاش Parquet في المزود لا يدعم 1w
# (كان يسقط إلى 1h ويحاول جلب ملايين الشموع). التجميع من 1d أدق وأسرع،
# والـ factor = عدد شموع الأساس في bucket الواحد (لحساب النوافذ/العمق).
COMPOSITE_TF_BASE: dict = {
    "2m": ("1m", 2),
    "10m": ("5m", 2),
    "2d": ("1d", 2),
    "2w": ("1d", 14),
    "1M": ("1d", 31),   # متوسط أيام الشهر — التجميع نفسه تقويمي حقيقي
}

# الفريمات المدعومة أصلاً من Binance kline streams
BINANCE_NATIVE_TF = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w",
}


def _tf_key(timeframe: str) -> str:
    """مفتاح البحث في COMPOSITE_TF_BASE — مع الحفاظ على تمييز 1M (شهر) عن 1m (دقيقة)."""
    tf = str(timeframe).strip()
    if tf in COMPOSITE_TF_BASE:
        return tf
    return tf.lower()


def is_composite_tf(timeframe: str) -> bool:
    """هل هذا الفريم مركّب يحتاج تجميعاً من فريم أساسي؟

    ⚠️ حساس لحالة الأحرف في "1M": يجب ألا يُختلط مع "1m" — لذلك نبحث بالأصل
    أولًا ثم بالlowercase (مفاتيح الشهر محفوظة بحرف M كبير).
    """
    if not timeframe:
        return False
    return _tf_key(timeframe) in COMPOSITE_TF_BASE


def composite_base_tf(timeframe: str) -> Tuple[str, Optional[int]]:
    """الفريم الأساسي ومعامل التجميع للفريم المركّب (أو الفريم نفسه)."""
    tf = str(timeframe).strip()
    if tf in COMPOSITE_TF_BASE:
        return COMPOSITE_TF_BASE[tf]
    tf_l = tf.lower()
    if tf_l in COMPOSITE_TF_BASE:
        return COMPOSITE_TF_BASE[tf_l]
    return tf_l, 1


def align_time_ms(ts_ms: int, timeframe: str) -> int:
    """محاذاة زمن (ms) لبداية bucket الفريم — يدعم w (اثنين UTC) وM (أول الشهر)."""
    tf_raw = str(timeframe).strip()
    tf = tf_raw.lower()

    if tf_raw.endswith("M"):
        # تقويم شهري حقيقي — بداية الشهر UTC (الحرف M كبير يميّزه عن الدقيقة)
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
        return int(datetime(dt.year, dt.month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    if tf.endswith("m"):
        try:
            tf_ms = int(tf[:-1]) * 60_000
            return (ts_ms // tf_ms) * tf_ms
        except ValueError:
            return ts_ms
    if tf.endswith("h"):
        try:
            tf_ms = int(tf[:-1]) * 3_600_000
            return (ts_ms // tf_ms) * tf_ms
        except ValueError:
            return ts_ms
    if tf.endswith("d"):
        try:
            n = int(tf[:-1])
            days = ts_ms // 86_400_000
            return ((days // n) * n) * 86_400_000
        except ValueError:
            return ts_ms
    if tf.endswith("w"):
        try:
            n = int(tf[:-1])
            days = ts_ms // 86_400_000
            # 1970-01-01 = خميس؛ أول اثنين = 1970-01-05 (يوم 4 منذ الإبوك)
            weeks = (days - 4) // 7
            weeks -= weeks % n
            return (4 + weeks * 7) * 86_400_000
        except ValueError:
            return ts_ms
    return ts_ms


def resample_candles(
    df: pd.DataFrame,
    target_tf: str,
    time_col: str = "time",
) -> pd.DataFrame:
    """تجميع شموع الفريم الأساسي إلى الفريم المركّب.

    يدخل df بأعمدة time(ms)/open/high/low/close/volume (وأي أعمدة أخرى تُهمل).
    يعيد df بنفس الأعمدة الأساسية مرتبة تصاعدياً — time = بداية الـ bucket.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[time_col, "open", "high", "low", "close", "volume"])

    out = df.copy()
    if time_col not in out.columns:
        if isinstance(out.index, pd.DatetimeIndex):
            out = out.reset_index().rename(columns={out.index.name or "index": time_col})
            out[time_col] = pd.to_datetime(out[time_col], utc=True).astype("int64") // 10**6
        else:
            raise ValueError(f"resample_candles: missing time column '{time_col}'")
    out[time_col] = out[time_col].astype("int64")

    # ملاحظة: time_col لا يُضمّن في الـ agg — وقت الـ bucket يأتي من عمود _bucket
    # نفسه (وإلا تكرّر العمود ورمى pandas "column label not unique")
    ohlcv = {"open": "first", "high": "max",
             "low": "min", "close": "last", "volume": "sum"}

    tf = str(target_tf).strip()
    tf_lower = tf.lower()

    if tf.endswith("M"):
        # تقويم شهري حقيقي — تجميع بمفتاح (سنة×100+شهر) وتوليد بداية الشهر UTC
        dt = pd.to_datetime(out[time_col], unit="ms", utc=True)
        month_key = dt.dt.year * 100 + dt.dt.month
        res = out.groupby(month_key).agg(ohlcv)
        res[time_col] = [
            int(pd.Timestamp(year=int(k) // 100, month=int(k) % 100, day=1, tz="UTC").timestamp() * 1000)
            for k in res.index
        ]
        res = res.reset_index(drop=True)
    elif tf_lower.endswith(("w", "m", "h", "d")):
        out["_bucket"] = out[time_col].map(lambda t: align_time_ms(int(t), tf))
        res = out.groupby("_bucket").agg(ohlcv).reset_index().rename(columns={"_bucket": time_col})
    else:
        return df

    res = res[[time_col, "open", "high", "low", "close", "volume"]]
    res = res.sort_values(time_col).drop_duplicates(subset=[time_col], keep="last")
    return res.reset_index(drop=True)


def ensure_datetime_index(data: pd.DataFrame) -> pd.DataFrame:
    """Guarantee a UTC DatetimeIndex for candle simulation/decision engines.

    - Already DatetimeIndex  → returned untouched.
    - Has a ``time`` column (epoch ms) → converted; the column is dropped.
    - Index is coercible to datetime (ISO strings etc.) → converted in place.
    - Anything else → returned unchanged (callers keep working as before).
    """
    if isinstance(data.index, pd.DatetimeIndex):
        return data

    if "time" in data.columns:
        t = pd.to_datetime(data["time"], unit="ms", utc=True, errors="coerce")
        if len(t) and t.notna().all():
            out = data.copy()
            out.index = pd.DatetimeIndex(t, name="time")
            return out.drop(columns=["time"])

    try:
        coerced = pd.to_datetime(data.index, utc=True, errors="raise")
        out = data.copy()
        out.index = pd.DatetimeIndex(coerced)
        return out
    except Exception:  # noqa: BLE001 — best effort; keep original frame
        return data


def sanitize_candle_time_ms(t_ms: int, timeframe: str, now_ms: Optional[int] = None) -> int:
    """✅ الجولة 4: توحيد كل طوابع شموع الخادم إلى epoch-ms محاذاة الفريم تماماً.

    يعالج الحالات التي وصلت من الفرونت سابقاً:
    - طوابع بالميكروثانية/نانوثانية/ثواني (سنة 33653 وغيرها) → تُحوَّل ms.
    - طوابع في المستقبل البعيد (> الآن + يومان) → تُرفض بتحويل بديل، وإن
      استحال التحويل تُقص إلى بداية bucket الحالي.
    - كل طابع يُمحاذا لبداية bucket الفريم (لا +1ms ولا كسور).

    تُستخدم في مسار الأسهم (yfinance أحياناً يعيد فهارس tz-aware ببواقي) وأي
    مصدر خارجي آخر — مصدر واحد للحقيقة لكل طوابع الشموع الصادرة.
    """
    t = int(t_ms)
    now = int(now_ms) if now_ms else int(datetime.now(timezone.utc).timestamp() * 1000)
    max_valid = now + 2 * 86_400_000

    # تطبيع المقياس: ثواني (< 1e11) / ميكروثانية (> 1e17) / نانو (> 1e20)
    if 0 < t < 100_000_000_000:          # ثواني → ms
        t *= 1000
    elif t > 100_000_000_000_000_000_000:  # نانو ثانية → ms
        t //= 1_000_000
    elif t > 100_000_000_000_000_000:      # ميكرو ثانية → ms
        t //= 1_000

    if t > max_valid:
        # طابع مستحيل — نحوّل بأفضل تفسير بديل ثم نقص إلى الحد الأقصى
        if t >= 100_000_000_000_000_000_000:
            t //= 1_000_000
        elif t >= 100_000_000_000_000_000:
            t //= 1_000
        if t > max_valid:
            t = align_time_ms(now, timeframe)
    elif t <= 0:
        t = align_time_ms(now, timeframe)

    return int(align_time_ms(t, timeframe))
