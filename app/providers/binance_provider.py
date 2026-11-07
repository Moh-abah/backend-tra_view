# trading_backend\app\providers\binance_provider.py

import aiohttp
import asyncio
import json
import logging
import os
import threading
import time as _time
import warnings
import weakref
from pathlib import Path

# ✅ إصلاح 2026-11-02 (طبقة 3 — بصمة العميل ضد 418):
# Binance يطبّق عقابات 418 منضبطة ببصمة العميل (IP + TLS/HTTP fingerprint):
# بصمة aiohttp (HTTP/1.1 + JA3 بايثون) تتجاوز العتبة بسرعة حتى بمعدل منخفض
# (مثبت تجريبياً: 3 طلبات aiohtml ← 418 في اللحظة التي يعطي فيها curl 200)،
# بينما بصمة المتصفح (HTTP/2 + JA3 كروم عبر curl_cffi) عتبتها أعلى بكثير.
# نستخدم curl_cffi بانتحال chrome في مسار klines مع سقوط آمن إلى aiohttp.
try:  # pragma: no cover — يعتمد على توفر الحزمة في البيئة
    from curl_cffi.requests import AsyncSession as _CurlAsyncSession
    _CURL_CFFI_OK = True
except Exception:  # noqa: BLE001
    _CurlAsyncSession = None
    _CURL_CFFI_OK = False

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
from app.config import settings
from ..services.data_provider import MarketDataProvider

logger = logging.getLogger(__name__)

# ✅ الجولة 13.3 — عقد الفريمات الموحد (نفس قائمة Binance المباشرة الموجودة في
# get_last_closed_candles أعلاه). كل فريمات وحدات ثابتة المدة مسموحة مباشرة؛
# ما عداها يُرفض برسالة صريحة (لا سقوط صامت إلى 1h إطلاقاً — كان العيب القديم:
# timeframe=2h/6h/8h/12h/3m/3d/1w كانت تجلب فريم 1h بصمت وتوسمه بالفريم المطلوب).
# ملاحظة 1M (شهر): Binance يعيدها بشبكة تقويمية غير ثابتة المدة (28–31 يوماً) —
# شبكة الكاش parquet ومحاذاة الشموع مبنية على ثبات المدة، لذا تُرفض صراحةً
# في مسار الباك-تست حتى توثق حاجة حقيقية لها.
BINANCE_DIRECT_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w",
}

# ===========================================================================
# ✅ الجولة 13.4 — عقد «أي فريم» في الباك-تست: RESAMPLING حقيقي لا غش
# ===========================================================================
# قبل 13.3: فريمات خارج القائمة الأصلية كانت تجلب 1h بصمت وتوسم النتائج
# زوراً (وعيب lower() كان يُسقط '1M' الشهرية إلى دقيقة واحدة!).
# في 13.3: أُغلقت الثغرة بالرفض الصريح — لكن ذلك جعل فريمات مثل 45m/1M
# مستحيلة رغم أنها مطلوبة من الواجهة.
# بعد 13.4: كل فريم يُبنى بأرقامه الحقيقية:
#   · أي فريم ثابت العرض يُجمَّع من أكبر فريم أصلي يقسمه بالتساوي:
#     45m = 15m×3 · 90m = 30m×3 · 10m = 5m×2 · 7m = 1m×7 · 2w = 1w×2 …
#   · '1M' الشهرية تُبنى تجميعاً تقويمياً حقيقياً من فريم اليوم (1d) على
#     حدود أشهر UTC — وآخر شهر قيد التكوّن يُسقط (سببية كاملة لا repaint).
#   · الغش ممنوع: النافذة غير المكتملة (شموع أساس ناقصة أو نافذة لم تنتهِ)
#     تُسقط ولا تُصنع منها شمعة بأرقام مشطورة.
#   · المطابقة حساسة لحالة الأحرف عمداً: '1M' شهر ≠ '1m' دقيقة.
# ===========================================================================

_MONTH_INTERVAL = "1M"

# ✅ الجولة 14.0 — فريمات تُرفض مع إزاحة توقيت ≠ 0:
# تثبيتها الأصلي في Binance ليس شبكة Epoch (الأسبوع يبدأ الاثنين UTC)،
# فإعادة تجميع مزاحة ستعطي حدوداً لا تطابق شموع Binance الأصلية لنفس
# الفريم — نرفض صراحة بدل إنتاج أرقام بمعنى مزدوج.
_TZ_SHIFT_REJECTED_INTERVALS = {"3d", "1w", "2w"}


def parse_fixed_interval_minutes(tf: str) -> Optional[int]:
    """دقائق الفريم ثابت العرض (لواحق m/h/d/w حرفياً) أو None.

    حساسة لحالة الأحرف عمداً: '1M' (شهر تقويمي) ليست فريماً ثابت العرض
    → None، بينما '1m' دقيقة. هذا القفل ضد عيب lower() التاريخي الذي كان
    يُسقط الشهرية إلى الدقيقة بصمت (كشفه الاختبار U-T8 في الجولة 13.3)."""
    if not isinstance(tf, str) or len(tf) < 2:
        return None
    try:
        if tf.endswith("m"):
            v = int(tf[:-1])
            return v if v > 0 else None
        if tf.endswith("h"):
            v = int(tf[:-1])
            return v * 60 if v > 0 else None
        if tf.endswith("d"):
            v = int(tf[:-1])
            return v * 1440 if v > 0 else None
        if tf.endswith("w"):
            v = int(tf[:-1])
            return v * 10080 if v > 0 else None
    except ValueError:
        return None
    return None


def pick_resample_base_interval(n_minutes: int, tz_offset_minutes: int = 0) -> Optional[str]:
    """أكبر فريم أصلي يقسم n_minutes وtz_offset_minutes معاً بالتساوي.

    أمثلة (off=0): 45m → '15m' (وليس 5m) · 90m → '30m' · 36h → '12h' ·
    10m → '5m' · 7m → '1m' · 2w → '1w'. والفريم الأصلي بحد ذاته لا يدخل
    هذا المسار أصلاً (يُجلَب مباشرة).

    ✅ الجولة 14.0 — قاعدة الإزاحة: عرض الأساس B يجب أن يقسم الإزاحة off
    أيضاً (off % B == 0) — وإلا فإن شموع الأساس تعتدي على حدود النوافذ
    المزاحة (straddle) فتُنسب أجزاء منها للنافذة الخطأ.
    أمثلة (off=+180): 4h → '1h' (وليس 2h لأن 180%120≠0) · 1d → '1h' ·
    2h → '1h'. وعند off=0 تنهار القاعدة إلى السلوك القديم حرفياً."""
    best: Optional[str] = None
    best_minutes = 0
    for name in BINANCE_DIRECT_INTERVALS:
        m = parse_fixed_interval_minutes(name)
        if m and m < n_minutes and n_minutes % m == 0 and tz_offset_minutes % m == 0 and m > best_minutes:
            best, best_minutes = name, m
    return best


def resample_candles_to_minutes(
    df: pd.DataFrame,
    n_minutes: int,
    base_minutes: int,
    now_ms: Optional[int] = None,
    tz_offset_minutes: int = 0,
) -> pd.DataFrame:
    """تجميع الشموع على شبكة ثابتة العرض مثبتة على Epoch (UTC).

    ✅ الجولة 14.0 — tz_offset_minutes: إزاحة مرساة الشبكة (مثال +180 =
    UTC+3 السعودية): نافذة الفريم تبدأ عند «منتصف الليل المحلي» بدل منتصف
    ليل UTC. رياضياً: grid = ((t + off) // step) * step - off — وعند
    off % step == 0 تنهار الإزاحة إلى الشبكة القديمة حرفياً (لا فرق إطلاقاً
    للفريمات 1m/3m/5m/15m/30m/1h مقابل +3h).

    open = أول افتتاح · high = الأعلى · low = الأدنى · close = آخر إغلاق ·
    volume = المجموع — الشمعة المجمّعة تعادل حسابياً شمعة Binance الأصلية
    لنفس الشبكة (منهجية التجميع القياسية).

    السببية (لا repaint): تُسقط أي نافذة (1) لم تنتهِ بعد
    (time + step > now_ms) أو (2) عدد شموعها الأساسية أقل من المكتمل
    (فجوة بيانات/عملة مدرجة حديثاً) — لا شموع مشطورة إطلاقاً.

    ملاحظة: الطوابع الناتجة تبقى epoch-ms UTC دائماً — الإزاحة تغيّر
    «أين تقع الحدود» فقط، لا تمثيل الوقت."""
    cols = ["time", "open", "high", "low", "close", "volume"]
    if df is None or df.empty or n_minutes <= 0 or base_minutes <= 0:
        return pd.DataFrame(columns=cols)
    if n_minutes % base_minutes != 0:
        raise ValueError(
            f"resample impossible: {n_minutes}min not divisible by {base_minutes}min"
        )
    step = int(n_minutes) * 60_000
    off_ms = int(tz_offset_minutes or 0) * 60_000
    expected = int(n_minutes) // int(base_minutes)
    out = df.copy()
    out["time"] = out["time"].astype("int64")
    # ✅ 14.0: المرساة المزاحة — ((t + off) // step) * step - off
    grid = (((out["time"] + off_ms) // step) * step - off_ms).rename("time")
    grouped = out.sort_values("time").groupby(grid, sort=True)
    res = grouped.agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    ).reset_index()
    sizes = grouped.size().rename("_n").reset_index().rename(columns={"time": "time"})
    res = res.merge(sizes, on="time", how="left")
    keep = res["_n"] == expected
    if now_ms is not None:
        keep = keep & ((res["time"] + step) <= int(now_ms))
    res = res[keep][cols].reset_index(drop=True)
    return res


def resample_candles_to_month(
    df: pd.DataFrame, now_ms: Optional[int] = None, tz_offset_minutes: int = 0
) -> pd.DataFrame:
    """تجميع تقويمي حقيقي على حدود الأشهر — فريم '1M'.

    ✅ الجولة 14.0 — tz_offset_minutes: حدود الشهر تُحسب على جدار التوقيت
    المطلوب (مثال +180: الشهر يبدأ 00:00 مكة = 21:00 UTC لآخر يوم من الشهر
    السابق بدل 00:00 UTC لليوم الأول).

    ⚠️ شرط الصحة (قاعدة straddle): مع إزاحة ≠ 0 يجب أن يكون أساس التجميع
    فريماً يقسم الإزاحة (1h للسعودية) — التجميع من فريم اليوم الأصلي يُنتج
    حدوداً منحرفة 3 ساعات لأن شمعة اليوم تعتدي على منتصف ليل الشهر المحلي.
    الموزّع (get_historicalcandl) يفرض هذا الشرط تلقائياً.

    open = افتتاح أول شمعة أساس · high = الأعلى · low = الأدنى ·
    close = إغلاق آخر شمعة أساس · volume = المجموع، ووقت الشمعة = بداية
    الشهر (بجدار التوقيت المطلوب — تُخزَّن epoch-ms UTC). آخر شهر قيد
    التكوّن (شهر end_date الجاري) يُسقط — سببية كاملة.
    ملاحظة بطبيعة التقويم: نافذة الشهر غير ثابتة العرض (28–31 يوماً)."""
    cols = ["time", "open", "high", "low", "close", "volume"]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    off_ms = int(tz_offset_minutes or 0) * 60_000
    off_td = pd.Timedelta(milliseconds=off_ms)
    out = df.copy()
    out["time"] = out["time"].astype("int64")
    # نحول إلى التوقيت المطلوب أولاً ثم نأخذ بداية الشهر ثم نرجع إلى UTC
    t = pd.to_datetime(out["time"], unit="ms", utc=True) + off_td
    # (to_timestamp يعيد naive على جدار UTC ثم نعيد تثبيت المنطقة — توافق كل إصدارات pandas)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        month_start = t.dt.to_period("M").dt.to_timestamp().dt.tz_localize("UTC") - off_td
    out["_month_ms"] = month_start.astype("int64") // 1_000_000
    grouped = out.sort_values("time").groupby("_month_ms", sort=True)
    res = grouped.agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    ).reset_index()
    res = res.rename(columns={"_month_ms": "time"})
    if now_ms is not None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cur_month_start_ms = (
                (
                    pd.Timestamp(int(now_ms), unit="ms", tz="UTC") + off_td
                ).to_period("M").to_timestamp().tz_localize("UTC") - off_td
            ).value // 1_000_000
        res = res[res["time"] < cur_month_start_ms]
    res = res[cols].reset_index(drop=True)
    return res

# Binance weight limits: klines(limit=1000) costs 5 weight against a 1200/min
# budget → ~240 requests/min ceiling. A bounded semaphore + 429 backoff keeps
# us safely under it while still fetching many batches IN PARALLEL instead of
# one-by-one (the old sequential loop needed minutes for a year of 1m data).
_KLINES_WEIGHT = 5
_WEIGHT_BUDGET_PER_MIN = 1200
_MAX_PARALLEL_BATCHES = 8

# 🔧 إصلاح 2026-11-02 (طبقة 2 — منع 418 IP-ban أساساً):
# العاصفة الباردة (مسح متوازي لعشرات الرموز، كل رمز ~3 دفعات) تضرب Binance
# بعدة طلبات في ثوانٍ → 418 IP-ban (حظر دقائق يُفرّغ المسح كله).
# السقف التزامني (_MAX_PARALLEL_BATCHES) يحدّ العدد المتزامن لكنه لا يحدّ
# المعدل اللحظي — لذا نضيف بوابة معدل (token bucket) تضمن تباعد أدنى بين
# طلبات klines الفعلية: ~4 طلب/ث ← ~480 وزن/دقيقة (حد الحظر 6000) بهامش
# واسع، وتكلفة باردة لـ 96 دفعة ≈ 24 ثانية فقط (IP مشترك مضغوط يفرض الأهدأ).
_KLINES_MIN_INTERVAL_SECONDS = 0.25

# صبر محدود على انتهاء العقاب (418): لو بقي أقل من هذا على التهدئة ننتظره
# بدل الفشل الفوري — يحوّل «عاصفة في آخر ثواني العقاب» إلى نجاح بدل موجة 503
# أخرى. مقيّد بـ 6 ثوانٍ حتى لا يجمّد الطلب قرب سقف المهلة (45s).
_BAN_PATIENCE_SECONDS = 6.0


class _KlinesRateGate:
    """بوابة تباعد أدنى بين طلبات klines (لكل حلقة أحداث — انظر أعلاه)."""

    def __init__(self, min_interval: float):
        self._min_interval = float(min_interval)
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def wait_slot(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            wait = self._next_slot - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = loop.time()
            self._next_slot = max(self._next_slot, now) + self._min_interval


_BATCH_SLEEP = 0.02  # tiny politeness gap; real throttling comes from the semaphore

# ---------------------------------------------------------------------------
# Disk (parquet) history cache — directory resolution with safe fallback.
#
# سبب العطل في Docker: المسار كان نسبياً (data/history) والمجلد المركّب من
# Windows غير قابل للكتابة من مستخدم الحاوية → PermissionError على كل طلب
# وإعادة تنزيل من Binance في كل مرة. الحل:
#   1) مسارات مطلقة دائماً (بيئة → جذر التطبيق → بديل مؤقت دائماً قابل للكتابة)
#   2) فحص قابلية الكتابة مرة واحدة عند أول استخدام
#   3) قاطع دارة: بعد 3 فشل متتالية نُعطّل الكتابة للعملية الحالية بسجل واحد
# ---------------------------------------------------------------------------
_CACHE_STATE = {
    "dir": None,        # المسار المُحلَّول (Path) أو None إذا لم يُحلَّل بعد
    "disabled": False,  # قاطع الدارة — تعطيل الكتابة نهائياً بعد فشل متكرر
    "failures": 0,      # عداد الفشل المتتالي
    "traceback_logged": False,
}

# ---------------------------------------------------------------------------
# مرآة الكاش في الذاكرة (بتحقق mtime):
#
# قبل هذا: كل صفحة before= كانت تعيد قراءة ملف parquet كامل (~20MB لسنة 1m)
# وفرزه من الصفر عند كل طلب تمرير — ثوانٍ إضافية على كل صفحة.
# الآن: القرص يُقرأ مرة واحدة لكل ملف وتُعاد القراءة فقط إذا تغيّر
# mtime/حجم الملف (بعد أي حفظ جديد). الإطارات المشتركة للقراءة فقط —
# كل المسارات المستهلكة لها (concat/filter/mask) لا تُعدّل الأصل.
# ---------------------------------------------------------------------------
_DISK_MEM: Dict[str, tuple] = {}   # path -> (mtime_ns, size, df)
_DISK_MEM_MAX = 6                  # حدود معقولة للذاكرة (~6 سلاسل نشطة)
_DISK_MEM_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# بوابة الحظر/التهدئة المشتركة (418 / 429):
#
# الجذر الحقيقي للصفحات البطيئة (22-56 ثانية): Binance يعيد 418 (حظر IP مؤقت)
# أو 429 (تجاوز الوزن) فتحرق كل دفعة 4 محاولات × 15 ثانية انتظار متسلسلة،
# وكل الدفعات المتوازية تضرب الحائط معاً → 30-56 ثانية للصفحة وبيانات ناقصة.
# الحل: أول 418/429 يفعّل تهدئة عامة قصيرة تُوقف كل الدفعات فوراً (فشل سريع
# بدون حرق انتظارات)، والصفحة تعود سريعاً بما هو متوفر. الفجوات تُملأ
# تلقائياً في الطلبات التالية لأن _missing_ranges تعيد اكتشافها (كاش يُصلح
# نفسه)، وبما أن الكاش يتراكم الآن فكل نطاق يُجلَب مرة واحدة فقط.
# ---------------------------------------------------------------------------
# ✅ إصلاح 2026-11-02 (طبقة 4 — تعدد المضيفين host failover):
# الـIP المشترك مضغوط وعتبته عند Binance ~10-15 طلب klines حتى بعد سكون —
# أي بصمة وأي إيقاع. Binance توفر رسمياً مرآة البيانات العامة
# data-api.binance.vision بعتبة منفصلة وأكثر تسامحاً (مثبت تجريبياً:
# 15/15 نجاح بينما الأساسي يوقظ 418). عند 418/429 من مضيف → تهدئة *له وحده*
# والدفعة تُعاد فوراً على المضيف الآخر — حظر مضيف واحد لا يعطل المسح.
_KLINES_HOSTS: List[str] = [
    settings.BINANCE_API_URL.rstrip("/"),
    "https://data-api.binance.vision",
]
_HOST_COOLDOWN: Dict[str, Dict[str, float]] = {
    h: {"until": 0.0, "reason": ""} for h in _KLINES_HOSTS
}
_HOST_LOCK = threading.Lock()
_PREFERRED_HOST = {"idx": 0}  # آخر مضيف نجح — زوجة توجيه لتقليل التنقل


def _host_trigger_ban(host: str, seconds: float, reason: str) -> None:
    with _HOST_LOCK:
        until = _time.monotonic() + max(1.0, float(seconds))
        st = _HOST_COOLDOWN[host]
        if until > st["until"]:
            st["until"] = until
            st["reason"] = reason
    logger.warning(
        "🚫 Binance %s على %s — تهدئة %.0fs له وحده؛ الدفعات تُحوّل فوراً للمضيف البديل",
        reason, host, seconds,
    )


def _host_mark_ok(host: str) -> None:
    with _HOST_LOCK:
        try:
            _PREFERRED_HOST["idx"] = _KLINES_HOSTS.index(host)
        except ValueError:
            pass


def _pick_klines_host() -> Optional[str]:
    """المضيف المفضّل إن كان صالحاً وإلا أول غير مهدّأ (None = الكل مهدّأ)."""
    with _HOST_LOCK:
        order = ([_KLINES_HOSTS[_PREFERRED_HOST["idx"]]]
                 + [h for i, h in enumerate(_KLINES_HOSTS) if i != _PREFERRED_HOST["idx"]])
        now = _time.monotonic()
        for h in order:
            if now >= _HOST_COOLDOWN[h]["until"]:
                return h
    return None


def _min_hosts_remaining() -> float:
    """أقصر تهدئة متبقية بين المضيفين (0 = يوجد مضيف متاح)."""
    with _HOST_LOCK:
        now = _time.monotonic()
        return min(max(0.0, st["until"] - now) for st in _HOST_COOLDOWN.values())


def _all_hosts_cooling() -> bool:
    with _HOST_LOCK:
        now = _time.monotonic()
        return all(now < st["until"] for st in _HOST_COOLDOWN.values())


def _resolve_cache_dir() -> Optional[Path]:
    """يحدد أول مجلد قابل للكتابة من قائمة مرشحين مطلقين. يُنادى مرة واحدة."""
    import tempfile

    app_root = Path(__file__).resolve().parents[2]  # .../backend_pro (أو /app داخل Docker)

    candidates: List[Path] = []
    env_dir = os.getenv("HISTORY_CACHE_DIR")
    if env_dir:
        p = Path(env_dir)
        candidates.append(p if p.is_absolute() else (app_root / p))
    settings_dir = str(getattr(settings, "DATA_CACHE_DIR", "") or "").strip()
    if settings_dir:
        p = Path(settings_dir)
        candidates.append(p if p.is_absolute() else (app_root / p))
    candidates.append(app_root / "data" / "history")
    candidates.append(Path(tempfile.gettempdir()) / "tr_history_cache")

    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write_probe"
            with open(probe, "a", encoding="utf-8"):
                pass
            probe.unlink(missing_ok=True)
            if cand != candidates[0]:
                logger.warning(
                    "⚠️ Cache dir %s غير قابل للكتابة — تحويل كاش الشموع إلى %s",
                    candidates[0], cand,
                )
            return cand
        except (PermissionError, OSError):
            continue
    logger.error("❌ لا يوجد أي مجلد قابل للكتابة لكاش الشموع — الكاش معطّل")
    return None


class BinanceProvider(MarketDataProvider):
    def __init__(self):
        self.base_url = settings.BINANCE_API_URL
        self.ws_url = settings.BINANCE_WS_URL
        self.symbols_cache = None
        self.cache_expiry = None
        # One lock per (symbol, interval) so concurrent dashboard requests for
        # the same series trigger ONE network fetch and then share the cache,
        # instead of stampeding Binance with 528-request runs in parallel.
        #
        # 🔧 إصلاح 2026-11-02 — «bound to a different event loop»:
        # asyncio.Semaphore/Lock في Python 3.10+ يُربط بأول حلقة أحداث ينتظرها
        # تحت التنافس (contended acquire) ويرفض أي حلقة أخرى بـ RuntimeError.
        # المزود singleton مشترك بين حلقة الـAPI الرئيسية وحلقات مؤقتة لمهام
        # الباك تست الداخلية (asyncio.run داخل to_thread) — التخزين القديم
        # (_http_semaphore الواحد + _history_locks الدائم) كان ينفجر عند أول
        # تنافس من حلقة ثانية (عاصفة مسح الفرونت المتوازي → 503 متسلسلة).
        # الحل: نسخة primitive لكل حلقة (WeakKeyDictionary على الحلقة نفسها) —
        # تموت الحلقة تُنظّف آلياً، وداخل الحلقة الواحدة السلوك مطابق للسابق.
        self._history_locks_by_loop: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
        self._http_semaphores: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
        self._rate_gates: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
        self._prims_guard = threading.Lock()

    def _get_http_semaphore(self) -> asyncio.Semaphore:
        """بوابة التهدئة المشتركة (سقف _MAX_PARALLEL_BATCHES) — لكل حلقة أحداث.

        الربط يحدث فقط عند التنافس (value=0) — لهذا العيب كان كامناً في
        التشغيل الخفيف واندلع مع المسح المتوازي للمئات من الرموز.
        """
        loop = asyncio.get_running_loop()
        sem = self._http_semaphores.get(loop)
        if sem is None:
            with self._prims_guard:
                sem = self._http_semaphores.get(loop)
                if sem is None:
                    sem = asyncio.Semaphore(_MAX_PARALLEL_BATCHES)
                    self._http_semaphores[loop] = sem
        return sem

    def _get_history_lock(self, key: str) -> asyncio.Lock:
        """قفل تسلسل التاريخ لكل (رمز:فريم) — لكل حلقة أحداث على حدة.

        داخل الحلقة الواحدة (الرئيسية) الدلالات مطابقة تماماً للقديم: دمج
        الطلبات المتزامنة لنفس السلسلة في جلب شبكي واحد + كاش مشترك.
        """
        loop = asyncio.get_running_loop()
        with self._prims_guard:
            loop_locks = self._history_locks_by_loop.get(loop)
            if loop_locks is None:
                loop_locks = {}
                self._history_locks_by_loop[loop] = loop_locks
            lock = loop_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                loop_locks[key] = lock
        return lock

    def _get_klines_rate_gate(self) -> _KlinesRateGate:
        """بوابة معدل klines — لكل حلقة أحداث (نفس مبرر السيمافور)."""
        loop = asyncio.get_running_loop()
        gate = self._rate_gates.get(loop)
        if gate is None:
            with self._prims_guard:
                gate = self._rate_gates.get(loop)
                if gate is None:
                    gate = _KlinesRateGate(_KLINES_MIN_INTERVAL_SECONDS)
                    self._rate_gates[loop] = gate
        return gate

    def is_rate_limited(self) -> bool:
        """هل كل مضيفي klines في تهدئة (418/429) الآن؟ — فحص عام صريح.

        تستخدمه الخدمات العليا لتمييز الفشل المؤقت (503 قابل للمحاولة)
        عن الخلل الدائم (400) — عقد الإشارة الحية. وجود مضيف سليم
        (مثل مرآة data-api) يعني عدم الحظر الكلي.
        """
        return _all_hosts_cooling()

    async def get_live_price(self, symbol: str) -> Dict:
        """الحصول على السعر الحالي لرمز محدد"""
        url = f"{self.base_url}/api/v3/ticker/price"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params={"symbol": symbol.upper()}) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "symbol": data["symbol"],
                            "price": float(data["price"]),
                            "timestamp": datetime.utcnow(),
                            "source": "binance"
                        }
                    else:
                        raise Exception(f"Binance API error: {response.status}")
        except Exception as e:
            print(f"Error fetching live price: {e}")
            return {}

    async def get_last_closed_candles(self, symbol: str, timeframe: str, limit: int = 3000):
        """
        جلب آخر N شمعة مغلقة مع دعم Pagination لـ 3000 شمعة
        """
        import logging
        logger = logging.getLogger(__name__)
        
        # 1️⃣ قائمة الفريمات المدعومة مباشرة من Binance
        binance_supported_intervals = {
            "1m", "3m", "5m", "15m", "30m", 
            "1h", "2h", "4h", "6h", "8h", "12h", 
            "1d", "3d", "1w", "1M"
        }
        
        # 2️⃣ خريطة الـ Resample للفريمات غير المدعومة مباشرة
        resample_map = {
            "30s": ("1s", "30S"),
            "2m": ("1m", "2T"),
            "10m": ("1m", "10T"),
            "3h": ("1h", "3H"),
            "2d": ("1d", "2D"),
            "2w": ("1w", "2W"),
            "3d": ("1d", "3D"),
        }
        
        # 3️⃣ تحقق إذا كان الفريم مدعوم مباشرة أو يحتاج Resample
        requires_resample = timeframe in resample_map
        is_directly_supported = timeframe in binance_supported_intervals
        
        if not is_directly_supported and not requires_resample:
            logger.warning(f"⚠️ Timeframe {timeframe} not fully supported. Using 1m as fallback.")
            timeframe = "1m"  # Fallback
            requires_resample = False
            is_directly_supported = True
        
        # 4️⃣ حدد الفريم الفعلي لطلبه من API
        if requires_resample:
            original_interval, resample_rule = resample_map[timeframe]
            # حساب مضاعف التحميل للـ Resample
            target_minutes = self._timeframe_to_minutes(timeframe)
            source_minutes = self._timeframe_to_minutes(original_interval)
            resample_multiplier = max(1, int(target_minutes / source_minutes))
            api_interval = original_interval
            api_limit = limit * resample_multiplier * 2  # نجلب أكثر لضمان كفاية البيانات بعد الـ Resample
        else:
            api_interval = timeframe
            api_limit = limit
            resample_rule = None
        
        # 5️⃣ حدود Binance
        BINANCE_MAX_LIMIT = 1000  # الحد الأقصى لطلب واحد
        
        # 6️⃣ Pagination لجلب كل البيانات
        all_candles = []
        current_end_time = None  # سنبدأ من الوقت الحالي ونرجع للخلف
        
        try:
            async with aiohttp.ClientSession() as session:
                remaining = api_limit
                
                while remaining > 0:
                    # حساب حجم هذه الدفعة
                    batch_size = min(remaining, BINANCE_MAX_LIMIT)
                    
                    # إعداد الباراميترات
                    params = {
                        "symbol": symbol.upper(),
                        "interval": api_interval,
                        "limit": batch_size,
                    }
                    
                    # أضف endTime إذا كنا نطلب دفعات سابقة
                    if current_end_time:
                        params["endTime"] = current_end_time
                    
                    logger.debug(f"📥 Fetching batch: {batch_size} candles, endTime: {current_end_time}")
                    
                    # محاولة SPOT API أولاً
                    url = "https://api.binance.com/api/v3/klines"
                    try:
                        async with session.get(url, params=params, timeout=15) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                
                                if not data or len(data) == 0:
                                    logger.info(f"⏹️ No more candles available for {symbol}")
                                    break
                                
                                # معالجة الدفعة
                                batch_df = pd.DataFrame(data, columns=[
                                    'open_time', 'open', 'high', 'low', 'close',
                                    'volume', 'close_time', 'quote_volume',
                                    'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
                                ])
                                
                                # تحويل الأنواع
                                numeric_cols = ['open', 'high', 'low', 'close', 'volume']
                                batch_df[numeric_cols] = batch_df[numeric_cols].astype(float)
                                batch_df['time'] = batch_df['open_time'].astype(int)
                                
                                # إزالة الشمعة الحية الحالية (إذا كانت موجودة)
                                # نتحقق من آخر شمعة إذا كانت وقت إغلاقها في المستقبل
                                current_time_ms = int(datetime.utcnow().timestamp() * 1000)
                                if len(batch_df) > 0:
                                    last_candle_close = batch_df.iloc[-1]['close_time']
                                    if last_candle_close > current_time_ms:
                                        batch_df = batch_df.iloc[:-1]
                                
                                # إضافة الدفعة للنتائج
                                if len(batch_df) > 0:
                                    all_candles.append(batch_df[['time', 'open', 'high', 'low', 'close', 'volume']])
                                    remaining -= len(batch_df)
                                    
                                    # تحديث current_end_time للطلب التالي (للخلف في الزمن)
                                    oldest_time = batch_df['time'].min()
                                    current_end_time = oldest_time - 1
                                    
                                    logger.debug(f"✅ Batch fetched: {len(batch_df)} candles, remaining: {remaining}")
                                else:
                                    break
                                    
                            else:
                                # إذا فشل SPOT، حاول FUTURES
                                logger.debug(f"SPOT API failed ({resp.status}), trying FUTURES...")
                                url = "https://fapi.binance.com/fapi/v1/klines"
                                async with session.get(url, params=params, timeout=15) as resp2:
                                    if resp2.status == 200:
                                        data = await resp2.json()
                                        # نفس معالجة البيانات...
                                        if not data:
                                            break
                                        
                                        batch_df = pd.DataFrame(data, columns=[
                                            'open_time', 'open', 'high', 'low', 'close',
                                            'volume', 'close_time', 'quote_volume',
                                            'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
                                        ])
                                        
                                        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
                                        batch_df[numeric_cols] = batch_df[numeric_cols].astype(float)
                                        batch_df['time'] = batch_df['open_time'].astype(int)
                                        
                                        if len(batch_df) > 0:
                                            all_candles.append(batch_df[['time', 'open', 'high', 'low', 'close', 'volume']])
                                            remaining -= len(batch_df)
                                            oldest_time = batch_df['time'].min()
                                            current_end_time = oldest_time - 1
                                        else:
                                            break
                                    else:
                                        logger.error(f"❌ Both APIs failed: SPOT {resp.status}, FUTURES {resp2.status}")
                                        break
                                    
                    except asyncio.TimeoutError:
                        logger.warning(f"⏱️ Timeout fetching batch for {symbol}")
                        break
                    except Exception as e:
                        logger.error(f"❌ Error in batch fetch: {e}")
                        break
                    
                    # تأخير قصير لتجنب rate limiting
                    await asyncio.sleep(0.1)
            
            # 7️⃣ دمج كل الدفعات
            if all_candles:
                df = pd.concat(all_candles, ignore_index=True)
                
                # إزالة التكرارات
                df = df.drop_duplicates(subset=['time'], keep='last')
                
                # ترتيب من الأقدم إلى الأحدث
                df = df.sort_values('time', ascending=True).reset_index(drop=True)
                
                # 8️⃣ تطبيق الـ Resample إذا مطلوب
                if requires_resample and resample_rule:
                
                    df = self._resample_dataframe(df, resample_rule)
                
                # 9️⃣ أخذ العدد المطلوب فقط
                if len(df) > limit:
                    df = df.tail(limit)
                
          
                # التحقق من عدم وجود قيم NaN
                df = df.dropna()
                
                # تحويل الأنواع النهائية
                df['time'] = df['time'].astype(int)
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    df[col] = df[col].astype(float)
                
               
                return df
            else:
                logger.warning(f"⚠️ No candles fetched for {symbol} {timeframe}")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"❌ Critical error fetching candles for {symbol} {timeframe}: {e}", exc_info=True)

            raise Exception(f"Failed to fetch candles for {symbol} {timeframe}: {e}")


    def _resample_dataframe(self, df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """
        دالة مساعدة لدمج البيانات من فريم صغير إلى كبير
        rule: مثلاً '2T' (2 دقيقة), '3H' (3 ساعات), '2D' (يومانين)
        """
        # تعيين الوقت كـ Index للتسهيل
        df.set_index('time', inplace=True)
        # تحويل الوقت إلى datetime للعمل عليه (وهو بالأساس ms)
        df.index = pd.to_datetime(df.index, unit='ms')
        
        # تطبيق التجميع
        ohlc_dict = {
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }
        
        # الدمج بناءً على القاعدة
        df_resampled = df.resample(rule).agg(ohlc_dict).dropna()
        
        # إعادة تحويل الـ Index إلى ms (int) لأن النظام يتوقع ذلك
        df_resampled.index = df_resampled.index.astype('int64') // 10**6 # ns to ms
        
        # تصفير العمود المساعد وإرجاع time كعمود عادي
        df_resampled = df_resampled.reset_index().rename(columns={'index': 'time'})
        
        return df_resampled


    # ------------------------------------------------------------------
    # Disk (parquet) history cache
    # ------------------------------------------------------------------
    @staticmethod
    def _cache_path(symbol: str, interval: str) -> Optional[Path]:
        """مسار مطلق داخل مجلد مُثبت قابليته للكتابة (أو None إذا تعذّر كل شيء)."""
        if _CACHE_STATE["dir"] is None:
            _CACHE_STATE["dir"] = _resolve_cache_dir()
        base = _CACHE_STATE["dir"]
        if base is None:
            return None
        return base / f"{symbol.upper()}_{interval}.parquet"

    @staticmethod
    def _load_disk_cache(path: Optional[Path]) -> Optional[pd.DataFrame]:
        """يقرأ كاش القرص عبر مرآة الذاكرة — القرص مرة واحدة لكل نسخة ملف.

        الأداء: أول استدعاء يقرأ parquet ويخزّنه في الذاكرة؛ الاستدعاءات
        التالية لنفس الملف (صفحات التمرير before= المتتالية) تعيد نسخة
        الذاكرة فوراً بدون IO. نعيد القراءة فقط إذا تغيّر mtime أو الحجم
        (بعد أي حفظ جديد). الإطار المعاد للقراءة فقط — لا يُعدّله أحد.
        """
        if path is None:
            return None
        try:
            if not path.exists():
                return None
            key = str(path)
            st = path.stat()

            # 1) نسخة الذاكرة الصالحة — صفر IO
            with _DISK_MEM_LOCK:
                entry = _DISK_MEM.get(key)
                if entry is not None and entry[0] == st.st_mtime_ns and entry[1] == st.st_size:
                    return entry[2]

            # 2) قراءة من القرص + معالجة
            df = pd.read_parquet(path)
            if df.empty or "time" not in df.columns:
                return None
            df["time"] = df["time"].astype("int64")
            for col in ("open", "high", "low", "close", "volume"):
                if col not in df.columns:
                    return None
            df = df[["time", "open", "high", "low", "close", "volume"]]
            # نكتبها مفروزة دائماً؛ الفرز هنا تحصين رخيص عند الحاجة فقط
            if not df["time"].is_monotonic_increasing:
                df = df.sort_values("time")
            df = df.reset_index(drop=True)

            # 3) تخزين المرآة مع إخلاء الأقدم عند التجاوز
            with _DISK_MEM_LOCK:
                _DISK_MEM[key] = (st.st_mtime_ns, st.st_size, df)
                while len(_DISK_MEM) > _DISK_MEM_MAX:
                    _DISK_MEM.pop(next(iter(_DISK_MEM)))
            return df
        except Exception:
            logger.warning("Disk cache read failed for %s — refetching", path.name, exc_info=True)
            return None

    @staticmethod
    def _save_disk_cache(path: Optional[Path], df: pd.DataFrame) -> None:
        """Atomic save: write to a temp file then os.replace (never corrupts).

        قاطع الدارة: بعد 3 فشل متتالية (صلاحيات/قرص) نُعطّل الكتابة لهذه
        العملية برسالة واحدة — بدلاً من طوفان Traceback في كل طلب.
        """
        if path is None or _CACHE_STATE["disabled"]:
            return
        try:
            tmp = path.with_suffix(".parquet.tmp")
            df.to_parquet(tmp, index=False)
            os.replace(tmp, path)
            _CACHE_STATE["failures"] = 0
        except Exception as exc:
            _CACHE_STATE["failures"] += 1
            if _CACHE_STATE["failures"] >= 3:
                _CACHE_STATE["disabled"] = True
                logger.error(
                    "🚫 عُطّل كاش القرص نهائياً بعد %d فشل متتالية (آخر خطأ: %s: %s) — "
                    "الجلب المباشر من Binance سيستمر بشكل طبيعي",
                    _CACHE_STATE["failures"], type(exc).__name__, exc,
                )
                return
            if not _CACHE_STATE["traceback_logged"]:
                # التتبع الكامل مرة واحدة فقط لأغراض التشخيص
                logger.warning("Disk cache write failed for %s (will retry)", path.name, exc_info=True)
                _CACHE_STATE["traceback_logged"] = True
            else:
                logger.warning("Disk cache write failed for %s (%s: %s)", path.name, type(exc).__name__, exc)

    @staticmethod
    def _missing_ranges(times: np.ndarray, tf_ms: int, start_ms: int, end_ms: int) -> List[tuple]:
        """Compute [start_ms, end_ms] sub-ranges NOT covered by a sorted `times` array."""
        if len(times) == 0:
            return [(start_ms, end_ms)]
        win = times[(times >= start_ms) & (times <= end_ms)]
        if len(win) == 0:
            return [(start_ms, end_ms)]
        ranges: List[tuple] = []
        if win[0] > start_ms:
            ranges.append((start_ms, int(win[0]) - 1))
        if len(win) > 1:
            diffs = np.diff(win)
            for i in np.where(diffs > tf_ms)[0]:
                ranges.append((int(win[i]) + tf_ms, int(win[i + 1]) - 1))
        if win[-1] < end_ms:
            ranges.append((int(win[-1]) + tf_ms, end_ms))
        return ranges

    def _range_batches(self, start_ms: int, end_ms: int, tf_ms: int) -> List[tuple]:
        """Split a missing range into deterministic 1000-candle request windows."""
        span = tf_ms * 1000
        batches = []
        cur = (start_ms // tf_ms) * tf_ms  # align to candle boundary
        while cur <= end_ms:
            batches.append((cur, min(cur + span - 1, end_ms)))
            cur += span
        return batches

    async def _fetch_klines_window(
        self,
        session,  # aiohttp.ClientSession أو curl_cffi AsyncSession (بحسب التوفر)
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> Optional[pd.DataFrame]:
        """Fetch one deterministic window with retry/backoff on 429/418/5xx/timeout."""
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 1000,
        }
        url = f"{self.base_url}/api/v3/klines"

        def _parse_rows(raw: list) -> pd.DataFrame:
            df = pd.DataFrame(raw, columns=[
                'open_time', 'open', 'high', 'low', 'close',
                'volume', 'close_time', 'quote_volume',
                'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            df[['open', 'high', 'low', 'close', 'volume']] = df[
                ['open', 'high', 'low', 'close', 'volume']].astype(float)
            df['time'] = df['open_time'].astype("int64")
            return df[['time', 'open', 'high', 'low', 'close', 'volume']]

        for attempt in range(4):
            # اختيار المضيف: المفضّل إن كان صالحاً وإلا أول غير مهدّأ —
            # 418/429 من مضيف لا يوقف الدفعة، تُعاد فوراً على المضيف البديل.
            host = _pick_klines_host()
            if host is None:
                # كل المضيفين في تهدئة — صبر محدود على الأقرب انتهاءً
                remaining = _min_hosts_remaining()
                if 0 < remaining <= _BAN_PATIENCE_SECONDS:
                    await asyncio.sleep(remaining + 0.25)
                    host = _pick_klines_host()
                if host is None:
                    return None
            url = f"{host}/api/v3/klines"
            try:
                async with self._get_http_semaphore():
                    # بوابة المعدل داخل السيمافور: تضمن تباعد طلبات klines الفعلية
                    # (منع 418 IP-ban — انظر توثيق _KLINES_MIN_INTERVAL_SECONDS)
                    await self._get_klines_rate_gate().wait_slot()
                    if _CURL_CFFI_OK:
                        # بصمة متصفح (HTTP/2 + JA3 chrome) — مستوى ثقة أعلى عند Binance
                        resp = await session.get(url, params=params, timeout=30)
                        status = resp.status_code
                        resp_headers = resp.headers
                        data = resp.json() if status == 200 else None
                    else:
                        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            status = resp.status
                            resp_headers = resp.headers
                            data = await resp.json() if status == 200 else None
                    if status == 200:
                        _host_mark_ok(host)
                        if not data:
                            return pd.DataFrame()
                        # parse ~1000 rows off the event loop (528 batches
                        # of 2ms CPU each add up to a noticeable freeze)
                        return await asyncio.to_thread(_parse_rows, data)
                    if status == 418:
                        # حظر مؤقت لهذا المضيف — تهدئة له وحده والدفعة تُعاد
                        # فوراً على المضيف البديل (host failover).
                        retry_after = float(resp_headers.get("Retry-After", 120.0))
                        _host_trigger_ban(host, min(retry_after, 300.0), "418 IP-ban")
                        continue
                    if status == 429:
                        # تجاوز وزن مؤقت على هذا المضيف — تهدئة قصيرة ثم تحويل
                        retry_after = float(resp_headers.get("Retry-After", 2.0))
                        _host_trigger_ban(host, min(retry_after, 10.0), "429 rate-limit")
                        continue
                    if status in (403, 451):
                        logger.error("Binance geo/blocked %s for %s", status, symbol)
                        return None
                    logger.warning("Binance klines HTTP %s (attempt %s)", status, attempt + 1)
                    await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as exc:  # noqa: BLE001 — عميلان محتملان (curl_cffi/aiohttp) بأخطاء مختلفة
                logger.warning("Binance klines network error (attempt %s): %s", attempt + 1, exc)
                await asyncio.sleep(0.5 * (attempt + 1))
        return None

    async def get_historicalcandl(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime = None,
        tz_offset_minutes: int = 0,
    ) -> pd.DataFrame:
        """كل الشموع التاريخية حتى آخر شمعة مغلقة — متوازٍ + كاش قرص Parquet.

        الأداء: الجلب الأول لسنة دقيقة (528 طلبًا) يتم بدفعات متوازية (~دقيقتان
        بدل 5+ دقائق متسلسلة)، وأي طلب لاحق يقرأ من الكاش ويجلب الذيل الجديد فقط
        (طلب أو اثنان ≈ ثانية واحدة).

        ✅ الجولة 13.4 — عقد «أي فريم»: موزّع ثلاثي المسارات:
          1) فريم أصلي (14 فريماً Binance ثابت المدة) → جلب مباشر.
          2) فريم ثابت العرض غير أصلي (45m/90m/10m/2w/…) → جلب أكبر فريم
             أصلي يقسمه بالتساوي ثم إعادة تجميع حقيقية (لا غش ولا شموع مشطورة).
          3) '1M' شهرية → تجميع تقويمي حقيقي من فريم اليوم (حدود أشهر UTC).
          ما عدا ذلك يُرفض برسالة العقد الكاملة (حساسة لحالة الأحرف:
          '1M' شهر ≠ '1m' دقيقة — قفل عيب lower() التاريخي من 13.3).

        ✅ الجولة 14.0 — إزاحة توقيت (tz_offset_minutes، مثال +180 = السعودية):
          · القاعدة: الإزاحة تغيّر حدود الفريم فقط إذا off % عرض_الفريم ≠ 0
            → +180 لا تغيّر 1m/3m/5m/15m/30m/1h إطلاقاً (جلب مباشر كما هو)،
            وتزحزح فعلاً 2h/4h/6h/8h/12h/1d (تُبنى إعادة تجميع مُزاحة من
            أكبر أساس أصلي) و'1M' (حدود أشهر على جدار التوقيت المطلوب).
          · {3d, 1w, 2w} مع إزاحة ≠ 0 تُرفض صراحة (تثبيت Binance الأصلي
            لها ليس شبكة Epoch — انظر _TZ_SHIFT_REJECTED_INTERVALS).
          · الطوابع الناتجة epoch-ms UTC دائماً؛ الكاش القرصي يخزن الأساس
            الأصلي UTC فقط ⇒ صفر تلوث بين متغيرات التوقيت.
        """
        tf = str(timeframe).strip()
        off_min = int(tz_offset_minutes or 0)

        # (1) فريم أصلي — مباشر فقط إذا كانت الإزاحة لا تغيّر حدوده
        if tf in BINANCE_DIRECT_INTERVALS:
            tf_min = self._timeframe_to_minutes(tf)
            if off_min == 0 or (tf_min > 0 and off_min % tf_min == 0):
                return await self._get_historical_native(symbol, tf, start_date, end_date)
            if tf in _TZ_SHIFT_REJECTED_INTERVALS:
                raise ValueError(
                    f"Timezone-shifted candles are not supported for {tf!r} "
                    f"(offset {off_min} min): Binance anchors this interval to "
                    "its own calendar, not the Epoch grid, so a shifted resample "
                    "would not match the native UTC candles. Shifted boundaries "
                    "are supported for 1m/3m/5m/15m/30m/1h (unchanged), "
                    "2h/4h/6h/8h/12h/1d (true shift) and '1M'. "
                    f"Keep timezone='UTC' for {tf!r}."
                )
            # وإلا: يسقط إلى مسار إعادة التجميع المُزاحة أدناه

        if end_date is None:
            end_date = datetime.utcnow()
        now_ms = int(end_date.timestamp() * 1000)

        # (2) فريم ثابت العرض → إعادة تجميع حقيقية (مزاحة بالتوقيت عند الحاجة)
        n_min = parse_fixed_interval_minutes(tf)
        if n_min is not None and n_min >= 2:
            if n_min >= 10080 and off_min != 0:
                raise ValueError(
                    f"Timezone-shifted candles are not supported for {tf!r} "
                    f"(width ≥ 1 week, offset {off_min} min) — week-anchored "
                    "frames stay UTC-only. Shifted boundaries are supported "
                    "for widths < 1w and '1M'."
                )
            base = pick_resample_base_interval(n_min, off_min)
            if base is None:
                # 1m يقسم أي عرض وإزاحة صحيحتين — شبكة أمان لا تفشل أبداً
                base = "1m"
            base_min = parse_fixed_interval_minutes(base) or 1
            step_ms = n_min * 60_000
            off_ms = off_min * 60_000
            # محاذاة البداية على حدود شبكة الفريم الهدف (أرضية) حتى تكون
            # أول نافذة مجمّعة مكتملة وليست مشطورة من طرفها
            # ✅ 14.0: الأرضية على الشبكة المُزاحة ((t + off) // step) * step - off
            t0 = int(start_date.timestamp() * 1000)
            floored_ms = ((t0 + off_ms) // step_ms) * step_ms - off_ms
            start_floored = datetime.fromtimestamp(
                floored_ms / 1000.0,
                tz=timezone.utc,
            )
            logger.info(
                "🧱 %s %s: إعادة تجميع حقيقية من %s (×%d شمعة أساس لكل نافذة%s)",
                symbol, tf, base, n_min // base_min,
                f"، إزاحة توقيت +{off_min}د" if off_min else "",
            )
            base_df = await self._get_historical_native(
                symbol, base, start_floored, end_date
            )
            return resample_candles_to_minutes(
                base_df, n_min, base_min, now_ms=now_ms,
                tz_offset_minutes=off_min,
            )

        # (3) الشهرية التقويمية الحقيقية '1M' من فريم يوم/ساعة
        if tf == _MONTH_INTERVAL:
            s = start_date.astimezone(timezone.utc)
            off_td = timedelta(minutes=off_min)
            # ✅ 14.0: بداية الشهر على جدار التوقيت المطلوب
            # (مثال +180: الشهر يبدأ 00:00 مكة = 21:00 UTC لآخر يوم من الشهر السابق)
            s_shifted = s + off_td
            month_start = datetime(
                s_shifted.year, s_shifted.month, 1, tzinfo=timezone.utc
            ) - off_td
            if off_min != 0:
                # ✅ 14.0 — قاعدة straddle للشهرية: فريم اليوم الأصلي يعتدي على
                # منتصف ليل الشهر المحلي (21:00 UTC للسعودية) — لذا مع إزاحة ≠ 0
                # يُبنى الشهر من أكبر فريم أصلي يقسم الإزاحة (1h للسعودية)
                # لتكون الأشهر ساعة-دقيقة تماماً. وعند off=0 يبقى 1d كما في 13.4.
                month_base = pick_resample_base_interval(1440, off_min) or "1h"
            else:
                month_base = "1d"
            logger.info(
                "🧱 %s 1M: شهرية تقويمية حقيقية → تجميع فريم %s على حدود أشهر %s",
                symbol, month_base,
                f"التوقيت المطلوب (إزاحة +{off_min}د)" if off_min else "UTC",
            )
            base_df = await self._get_historical_native(
                symbol, month_base, month_start, end_date
            )
            return resample_candles_to_month(
                base_df, now_ms=now_ms, tz_offset_minutes=off_min
            )

        raise ValueError(
            f"Unsupported timeframe for backtest: {timeframe!r} — "
            f"Supported: 14 native Binance intervals "
            f"{sorted(BINANCE_DIRECT_INTERVALS, key=self._timeframe_to_minutes)} "
            "+ any fixed-width interval auto-resampled from them "
            "(e.g. '45m'=15m×3, '90m'=30m×3, '10m'=5m×2, '2w'=1w×2) "
            "+ '1M' calendar month (real month aggregation from 1d). "
            "Matching is case-sensitive: '1M' (month) ≠ '1m' (minute). "
            f"Timezone (R14.0, offset={off_min}min): shifted boundaries "
            "supported for widths < 1w and '1M'; "
            f"{sorted(_TZ_SHIFT_REJECTED_INTERVALS)} stay UTC-only."
        )

    async def _get_historical_native(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime = None
    ) -> pd.DataFrame:
        """المسار الأصلي (فريمات Binance المباشرة فقط) — كاش Parquet + جلب متوازٍ.

        الجولة 13.4: أصبح مساراً داخلياً يستدعيه موزّع get_historicalcandl
        مباشرة للفريم الأصلي، أو كأساس بيانات لإعادة التجميع (45m من 15m،
        1M من 1d). الحارس الدفاعي يمنع أي فريم غير أصلي من دخوله هنا —
        الغش الصامت (مثل سقوط 1M إلى دقيقة) مستحيل بنيوياً."""
        if timeframe not in BINANCE_DIRECT_INTERVALS:
            raise ValueError(
                f"Internal contract violation: native interval expected, "
                f"got {timeframe!r} — non-native intervals must go through "
                "the resample dispatcher (get_historicalcandl)."
            )
        tf = timeframe
        interval = tf
        tf_ms = self._timeframe_to_minutes(tf) * 60 * 1000

        if end_date is None:
            end_date = datetime.utcnow()
        # آخر شمعة مغلقة (الشمعة الحالية لم تُغلق بعد)
        end_ms = int((end_date - timedelta(minutes=self._timeframe_to_minutes(timeframe))).timestamp() * 1000)
        # محاذاة البداية على حدود الشمعة (floor)
        start_ms = (int(start_date.timestamp() * 1000) // tf_ms) * tf_ms
        if end_ms < start_ms:
            return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

        lock = self._get_history_lock(f"{symbol.upper()}:{interval}")
        async with lock:
            t0 = _time.perf_counter()
            # parquet read of ~20MB is CPU/IO work — keep it off the event loop
            cached = await asyncio.to_thread(self._load_disk_cache, self._cache_path(symbol, interval))
            cached_times = cached["time"].to_numpy(dtype="int64") if cached is not None else np.empty(0, dtype="int64")

            missing = self._missing_ranges(cached_times, tf_ms, start_ms, end_ms)
            failed_batches = 0  # يُستخدم لوسم fetch_incomplete حتى في مسار الكاش الكامل
            if missing:
                batches: List[tuple] = []
                for r_start, r_end in missing:
                    batches.extend(self._range_batches(r_start, r_end, tf_ms))
                total_candles = sum(int((b[1] - b[0]) / tf_ms) + 1 for b in batches)
                logger.info(
                    "📥 %s %s: %d kline batches to fetch (~%d candles, %d cached)",
                    symbol, interval, len(batches), total_candles, len(cached_times),
                )
                fetched: List[pd.DataFrame] = []
                # ✅ جلسة curl_cffi ببصمة chrome عند توفرها (أعلى عتبة 418)،
                # وإلا aiohttp كما كان — نفس منطق الدفعات والإعادة.
                if _CURL_CFFI_OK:
                    session_cm = _CurlAsyncSession(impersonate="chrome")
                else:
                    session_cm = aiohttp.ClientSession(
                        connector=aiohttp.TCPConnector(limit=_MAX_PARALLEL_BATCHES + 4)
                    )
                async with session_cm as session:
                    results = await asyncio.gather(
                        *(self._fetch_klines_window(session, symbol, interval, b0, b1)
                          for b0, b1 in batches)
                    )
                for r in results:
                    if r is None:
                        failed_batches += 1
                    elif not r.empty:
                        fetched.append(r)
                if failed_batches:
                    logger.warning(
                        "⚠️ %s %s: فشل %d/%d دفعة (حظر/تهدئة Binance) — نُعيد المتوفر الآن والفجوات تُملأ في الطلب التالي",
                        symbol, interval, failed_batches, len(batches),
                    )
                parts = ([cached] if cached is not None else []) + fetched
                if not parts:
                    logger.warning("⚠️ No candles fetched for %s %s", symbol, tf)
                    empty = pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    if failed_batches:
                        empty.attrs["fetch_incomplete"] = True
                    return empty

                def _merge_parts() -> pd.DataFrame:
                    # ⚠️ إصلاح جوهري (كان يقتل الأداء في الإنتاج):
                    # كان الفلتر merged["time"] <= end_ms يُطبَّق على الدمج الكامل،
                    # فعند جلب صفحة تاريخية قديمة تُحذف كل الشموع الحديثة المخزَّنة
                    # ويُعاد حفظ الملف بالنافذة القديمة فقط → الكاش لا يتراكم أبداً
                    # وكل صفحة تمرير تعيد جلب ~6000 شمعة من Binance من الصفر
                    # (22-56 ثانية للصفحة على سيرفر الإنتاج بسبب rate-limit).
                    # الصحيح: فلترة الدفعات المجلوبة فقط (لإسقاط الشمعة غير
                    # المغلقة في طرفه) والإبقاء على الكاش السابق كما هو.
                    frames = []
                    if cached is not None:
                        frames.append(cached)
                    for r in fetched:
                        frames.append(r[r["time"] <= end_ms])
                    if not frames:
                        return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    merged = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0].copy()
                    merged = merged.drop_duplicates(subset=["time"], keep="last").sort_values("time")
                    return merged.reset_index(drop=True)

                # concat+dedupe+sort of 500k+ rows blocks the loop for seconds
                # if done inline — run it in a worker thread.
                df = await asyncio.to_thread(_merge_parts)
                if fetched:
                    # extend the disk cache with everything we now know (cap 3M rows)
                    to_save = df
                    if len(to_save) > 3_000_000:
                        to_save = to_save.tail(3_000_000).reset_index(drop=True)
                    await asyncio.to_thread(self._save_disk_cache, self._cache_path(symbol, interval), to_save)
                    logger.info(
                        "💾 %s %s: cache now %d candles (added ~%d) in %.1fs",
                        symbol, interval, len(df),
                        len(df) - len(cached_times) if cached is not None else len(df),
                        _time.perf_counter() - t0,
                    )
            else:
                df = cached  # full window already cached — zero network
                logger.info("⚡ %s %s: served %d candles from disk cache in %.2fs",
                            symbol, interval, len(df), _time.perf_counter() - t0)

            result = df[(df["time"] >= start_ms) & (df["time"] <= end_ms)].reset_index(drop=True)
            result = result[["time", "open", "high", "low", "close", "volume"]]
            # وسم الصفحة الناقصة (فشل دفعات بسبب حظر مؤقت) — الراوتر يستخدمه
            # لمنع إعلان نهاية التاريخ زوراً (has_more=false) وإيقاف التمرير.
            if failed_batches:
                result.attrs["fetch_incomplete"] = True
            return result
    
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """تحويل الإطار الزمني إلى دقائق — ✅ الجولة 13.3: دعم w (أسبوع).
        (1M شهر غير مدعوم في مسار الباك-تست — شبكة تقويمية غير ثابتة)."""
        if timeframe.endswith('m'):
            return int(timeframe[:-1])
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 24 * 60
        elif timeframe.endswith('w'):
            return int(timeframe[:-1]) * 7 * 24 * 60
        else:
            return 1

# في BinanceProvider.get_historical()
    async def get_historical(
        self, 
        symbol: str, 
        timeframe: str,
        start_date: datetime,
        end_date: datetime = None
    ) -> pd.DataFrame:
        """الحصول على بيانات تاريخية — ✅ الجولة 13.3: نفس عقد الفريمات الموحد
        (مطابقة حساسة لحالة الأحرف — "1M" شهرية تُرفض صراحة)."""
        tf = str(timeframe).strip()
        if tf not in BINANCE_DIRECT_INTERVALS:
            # ✅ 13.4: هذا المسار القديم يبقى أصلياً فقط — مسار الباك-تست
            # (get_historicalcandl) هو الذي يدعم إعادة التجميع و'1M' التقويمية.
            raise ValueError(f"Unsupported timeframe for Binance: {timeframe}. "
                            f"Supported (native): {sorted(BINANCE_DIRECT_INTERVALS, key=self._timeframe_to_minutes)} — "
                            "the backtest path (get_historicalcandl) additionally supports "
                            "resampled fixed-width intervals and '1M' calendar month.")
        
        interval = tf
        
        print(f"📊 BinanceProvider: Requesting {symbol} with interval {interval} "
            f"(timeframe: {timeframe})")
        
        url = f"{self.base_url}/api/v3/klines"
        
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": int(start_date.timestamp() * 1000),
            "limit": 1000
        }
        if end_date:
            params["endTime"] = int(end_date.timestamp() * 1000)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if not data:
                            print(f"⚠️ No data returned from Binance for {symbol}")
                            return pd.DataFrame()
                        
                        print(f"✅ Got {len(data)} candles from Binance")
                        
                        df = pd.DataFrame(data, columns=[
                            'open_time', 'open', 'high', 'low', 'close',
                            'volume', 'close_time', 'quote_volume',
                            'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'
                        ])
                        
                        # التحقق من الفاصل الزمني
                        if len(data) > 1:
                            time_diff = (pd.to_datetime(data[1][0], unit='ms') - 
                                        pd.to_datetime(data[0][0], unit='ms')).total_seconds() / 60
                            print(f"⏱️ Binance interval: {time_diff} minutes")
                        
                        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
                        df[numeric_cols] = df[numeric_cols].astype(float)
                        df['timestamp'] = pd.to_datetime(df['open_time'], unit='ms')
                        df.set_index('timestamp', inplace=True)
                        return df[['open', 'high', 'low', 'close', 'volume']]
                    else:
                        error_text = await response.text()
                        print(f"❌ Binance API error {response.status}: {error_text}")
                        return pd.DataFrame()
        except Exception as e:
            print(f"❌ Error fetching Binance data: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()


    async def stream_live(self, symbol: str, timeframe: str = "1m"):
        """بث بيانات حية عبر WebSocket"""
        import websockets # type: ignore
        
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m",
            "1h": "1h", "4h": "4h", "1d": "1d"
        }
        interval = interval_map.get(timeframe, "1m")
        stream_name = f"{symbol.lower()}@kline_{interval}"
        
        async with websockets.connect(f"{self.ws_url}/{stream_name}") as ws:
            async for message in ws:
                data = json.loads(message)
                if 'k' in data:
                    kline = data['k']
                    yield {
                        "symbol": kline['s'],
                        "timeframe": timeframe,
                        "open": float(kline['o']),
                        "high": float(kline['h']),
                        "low": float(kline['l']),
                        "close": float(kline['c']),
                        "volume": float(kline['v']),
                        "is_closed": kline['x'],
                        "timestamp": datetime.utcfromtimestamp(kline['t'] / 1000),
                        "source": "binance"
                    }


                    
    _SYMBOLS_DISK_CACHE = "data/binance_symbols_cache.json"  # ✅ الجولة 4

    async def get_symbols(self) -> List[str]:
        """الحصول على جميع الرموز المتاحة.

        ✅ الجولة 4: كاش قرص دائم — القائمة نادراً ما تتغير، فنجلبها مرة
        ونخزنها على القرص؛ وعند حظر/فشل REST نخدم الكاش المحفوظ بدل إعادة
        قائمة فارغة (كان يكسر قائمة اختيار الرموز في الفرونت)."""
        # استخدام الكاش لتقليل الطلبات
        if self.symbols_cache and self.cache_expiry > datetime.utcnow():
            return [s for s in self.symbols_cache if s.endswith(("USDT", "USDC"))]

        try:
            # إنشاء الجلسة باستخدام aiohttp
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/v3/exchangeInfo"
                async with session.get(url) as response:
                    if response.status != 200:
                        raise Exception(f"Failed to fetch: {response.status}")

                    data = await response.json()
                    symbols = [
                        s['symbol']
                        for s in data['symbols']
                        if s['status'] == "TRADING"
                    ]

                    # تحديث الكاش
                    self.symbols_cache = symbols
                    self.cache_expiry = datetime.utcnow() + timedelta(hours=1)

                    # ✅ حفظ على القرص للتعويض الذاتي عند الحظر لاحقاً
                    try:
                        import json as _json
                        import os as _os
                        _os.makedirs("data", exist_ok=True)
                        with open(self._SYMBOLS_DISK_CACHE, "w") as _f:
                            _json.dump({"ts": datetime.utcnow().isoformat(),
                                        "symbols": symbols}, _f)
                    except Exception:  # noqa: BLE001
                        pass

                    filtered_symbols = [s for s in symbols if s.endswith(("USDT", "USDC"))]
                    return filtered_symbols

        except Exception as e:
            # ✅ الجولة 4: fallback للكاش الدائم على القرص
            try:
                import json as _json
                with open(self._SYMBOLS_DISK_CACHE) as _f:
                    disk = _json.load(_f)
                cached = disk.get("symbols") or []
                if cached:
                    self.symbols_cache = cached
                    self.cache_expiry = datetime.utcnow() + timedelta(minutes=10)
                    filtered = [s for s in cached if s.endswith(("USDT", "USDC"))]
                    print(f"Failed to get symbols: {e} → serving disk cache ({len(filtered)} symbols)")
                    return filtered
            except Exception:  # noqa: BLE001
                pass
            print(f"Failed to get symbols: {e}")
            return []