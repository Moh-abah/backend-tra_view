# trading_backend\app\providers\binance_provider.py

import aiohttp
import asyncio
import json
import logging
import os
import threading
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from app.config import settings
from ..services.data_provider import MarketDataProvider

logger = logging.getLogger(__name__)

# Binance weight limits: klines(limit=1000) costs 5 weight against a 1200/min
# budget → ~240 requests/min ceiling. A bounded semaphore + 429 backoff keeps
# us safely under it while still fetching many batches IN PARALLEL instead of
# one-by-one (the old sequential loop needed minutes for a year of 1m data).
_KLINES_WEIGHT = 5
_WEIGHT_BUDGET_PER_MIN = 1200
_MAX_PARALLEL_BATCHES = 8
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
_BAN_STATE = {"until": 0.0, "reason": ""}
_BAN_LOCK = threading.Lock()


def _ban_active() -> bool:
    return _time.monotonic() < _BAN_STATE["until"]


def _ban_wait() -> float:
    """الثواني المتبقية في التهدئة الحالية (0 إذا لا تهدئة)."""
    return max(0.0, _BAN_STATE["until"] - _time.monotonic())


def _trigger_ban(seconds: float, reason: str) -> None:
    with _BAN_LOCK:
        until = _time.monotonic() + max(1.0, float(seconds))
        if until > _BAN_STATE["until"]:
            _BAN_STATE["until"] = until
            _BAN_STATE["reason"] = reason
            logger.warning(
                "🚫 Binance %s — تهدئة عامة %.0fs (إيقاف فوري لبقية الدفعات؛ الفجوات تُملأ في الطلب التالي)",
                reason, seconds,
            )


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
        self._history_locks: Dict[str, asyncio.Lock] = {}
        self._http_semaphore = asyncio.Semaphore(_MAX_PARALLEL_BATCHES)

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
        session: aiohttp.ClientSession,
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
            # بوابة التهدئة المشتركة: 418 (حظر طويل) → فشل فوري؛
            # 429 (تهدئة قصيرة) → انتظار واحد مشترك ثم إعادة المحاولة.
            if _ban_active():
                if _BAN_STATE.get("reason", "").startswith("418"):
                    return None
                wait = _ban_wait()
                if wait > 0:
                    await asyncio.sleep(wait)
            try:
                async with self._http_semaphore:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data:
                                return pd.DataFrame()
                            # parse ~1000 rows off the event loop (528 batches
                            # of 2ms CPU each add up to a noticeable freeze)
                            return await asyncio.to_thread(_parse_rows, data)
                        if resp.status == 418:
                            # حظر IP مؤقت من Binance (عادة دقائق) — تهدئة عامة
                            # وفشل فوري: بدل 4×15 ثانية لكل دفعة (السبب التاريخي
                            # للصفحات ذات 22-56 ثانية).
                            retry_after = float(resp.headers.get("Retry-After", 120.0))
                            _trigger_ban(min(retry_after, 300.0), "418 IP-ban")
                            return None
                        if resp.status == 429:
                            # تجاوز وزن مؤقت — تهدئة قصيرة مشتركة (≤10s) ثم إعادة
                            retry_after = float(resp.headers.get("Retry-After", 2.0))
                            _trigger_ban(min(retry_after, 10.0), "429 rate-limit")
                            continue
                        if resp.status in (403, 451):
                            body = (await resp.text())[:200]
                            logger.error("Binance geo/blocked %s for %s: %s", resp.status, symbol, body)
                            return None
                        logger.warning("Binance klines HTTP %s (attempt %s)", resp.status, attempt + 1)
                        await asyncio.sleep(0.5 * (attempt + 1))
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                logger.warning("Binance klines network error (attempt %s): %s", attempt + 1, exc)
                await asyncio.sleep(0.5 * (attempt + 1))
        return None

    async def get_historicalcandl(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime = None
    ) -> pd.DataFrame:
        """كل الشموع التاريخية حتى آخر شمعة مغلقة — متوازٍ + كاش قرص Parquet.

        الأداء: الجلب الأول لسنة دقيقة (528 طلبًا) يتم بدفعات متوازية (~دقيقتان
        بدل 5+ دقائق متسلسلة)، وأي طلب لاحق يقرأ من الكاش ويجلب الذيل الجديد فقط
        (طلب أو اثنان ≈ ثانية واحدة).
        """
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "4h": "4h", "1d": "1d"
        }
        interval = interval_map.get(timeframe, "1h")
        tf_ms = self._timeframe_to_minutes(timeframe) * 60 * 1000

        if end_date is None:
            end_date = datetime.utcnow()
        # آخر شمعة مغلقة (الشمعة الحالية لم تُغلق بعد)
        end_ms = int((end_date - timedelta(minutes=self._timeframe_to_minutes(timeframe))).timestamp() * 1000)
        # محاذاة البداية على حدود الشمعة (floor)
        start_ms = (int(start_date.timestamp() * 1000) // tf_ms) * tf_ms
        if end_ms < start_ms:
            return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

        lock = self._history_locks.setdefault(f"{symbol.upper()}:{interval}", asyncio.Lock())
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
                async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(limit=_MAX_PARALLEL_BATCHES + 4)
                ) as session:
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
                    logger.warning("⚠️ No candles fetched for %s %s", symbol, timeframe)
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
        """تحويل الإطار الزمني إلى دقائق"""
        if timeframe.endswith('m'):
            return int(timeframe[:-1])
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 24 * 60
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
        """الحصول على بيانات تاريخية"""
        # ✅ أضف 30m إلى interval_map
        interval_map = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"
        }
        
        # تحقق من وجود timeframe مدعوم
        if timeframe not in interval_map:
            raise ValueError(f"Unsupported timeframe for Binance: {timeframe}. "
                            f"Supported: {list(interval_map.keys())}")
        
        interval = interval_map[timeframe]
        
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