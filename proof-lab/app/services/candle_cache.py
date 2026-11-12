# app/services/candle_cache.py
"""✅ الجولة 45 — كاش الشموع الدائم في قاعدة البيانات (Candle Cache).

مشكلة الإنتاج (كلام المستخدم حرفياً): «اذا اردت اسوي اختبار سنه لعمله
بيتكوين بموشرات مختلفه واستراتيجيه مختلفه لفريم دقيقه فكل مره بيجلب
شموع جديده ومفروض يخزن الشموع ويستخدم ... ويجلب فوقها اخر شموع».

السلوك الجديد (بدون أي تغيير في نتائج المحاكاة):
  * التشغيل الأول لرمز/فريم: يجلب النافذة كاملة من المزوّد (كما اليوم)
    ثم يحفظ الشموع في جدول candle_cache — نهائياً، ليس ذاكرة مؤقتة.
  * كل تشغيل تالٍ لنفس الرمز/الفريم: يقرأ الشموع من القاعدة فوراً، ثم
    يجلب فقط ما نقص من الرأس (آخر شمعة مخزنة ← الآن) ويدمجها فوق
    المخزون — «يجلب فوقها آخر شموع» حرفياً.
  * إذا طلب المستخدم نافذة أعمق مما يغطي المخزون (كاش 30 يوم وطلب
    سنة): يجلب النافذة كاملة ويدمجها مع المخزون فيصبح المخزون أعمق
    تدريجياً مع كل استخدام.

مساحتا عمل معزولتان (راجع app/models/candle_cache.py):
  * فضاء c: المسار الموحد ج42 — يخزّن نفس قواميس الشموع التي يستهلكها
    محرك الخروج حرفياً (صفر مخاطرة تنسيق).
  * فضاء d: المسار القياسي — يخزّن سجلات DataFrame + مخطط الأعمدة
    والأنواع ويعيد بناء الإطار بنفس الشكل الذي أنتجه المزوّد.

فلسفة الأمان: أي استثناء داخل مسار الكاش (تنسيق غير متوقع، قفل، قراءة
فاشلة) ⇦ تجاوز إلى الجلب المباشر — أسوأ حالة هي سلوك اليوم، لا كسر
باك-تست أبداً. الكاش اختياري بالبيئة CANDLE_CACHE_ENABLED=false.
"""
from __future__ import annotations

import inspect
import logging
import math
import os
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import delete as sa_delete, select, update as sa_update

from app.config import settings
from app.database.session import with_lock_retry

logger = logging.getLogger("app.services.candle_cache")

# مفاتيح الزمن المتوقعة داخل قاموس الشمعة/السجل — بالأولوية
_TIME_KEYS = ("time", "timestamp", "open_time", "date", "datetime", "ts", "t")

# فواصل الفريمات بالثواني
_INTERVALS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400, "3d": 259200, "1w": 604800,
}

_MAX_CANDLES = int(getattr(settings, "CANDLE_CACHE_MAX_CANDLES", 600000) or 600000)
_ENABLED = bool(getattr(settings, "CANDLE_CACHE_ENABLED", True))
_DFSPACE_ENABLED = bool(getattr(settings, "CANDLE_CACHE_DFSPACE", True))
_REFRESH_HEAD = bool(getattr(settings, "CANDLE_CACHE_REFRESH_HEAD", True))


# ==========================================================================
# أدوات التطبيع الزمني
# ==========================================================================
def _norm_epoch(value: Any) -> Optional[int]:
    """تحويل قيمة زمنية (epoch s/ms، ISO، datetime، Timestamp) إلى ثوانٍ."""
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            v = float(value)
            if v <= 0:
                return None
            # قيم بالميلي ثانية (أكبر من 10^11) ⇦ ثوانٍ
            return int(v / 1000.0) if v > 1e11 else int(v)
        if isinstance(value, datetime):
            return int(value.replace(tzinfo=timezone.utc).timestamp())
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            if s.replace(".", "", 1).isdigit():
                return _norm_epoch(float(s))
            return int(
                datetime.fromisoformat(s.replace("Z", "+00:00"))
                .astimezone(timezone.utc)
                .timestamp()
            )
    except Exception:  # noqa: BLE001
        return None
    return None


def _candle_time(candle: Dict[str, Any]) -> Optional[int]:
    """استخراج زمن الشمعة بأي مفتاح متعارف عليه — None يعني تنسيقاً مجهولاً."""
    for key in _TIME_KEYS:
        if key in candle:
            t = _norm_epoch(candle[key])
            if t is not None:
                return t
    return None


def _infer_interval(
    timeframe: Optional[str], candles: List[Dict[str, Any]]
) -> Optional[int]:
    """فاصل الشموع بالثواني: من جدول الفريمات، وإلا من الفروق المرصودة."""
    tf = str(timeframe or "").strip().lower()
    if tf in _INTERVALS:
        return _INTERVALS[tf]
    if len(candles) >= 3:
        times = [t for t in (_candle_time(c) for c in candles) if t]
        if len(times) >= 3:
            diffs = sorted(b - a for a, b in zip(times, times[1:]) if b > a)
            if diffs:
                return diffs[len(diffs) // 2]
    return None


def _json_safe(obj: Any) -> Any:
    """تنقية JSON كاملة: datetime⇦ISO، numpy⇦أصلي، NaN/Inf⇦None."""
    import json

    import numpy as np
    import pandas as pd

    class _Cleaner(json.JSONEncoder):
        def default(self, o):  # noqa: D102
            if isinstance(o, (datetime, pd.Timestamp)):
                return o.isoformat()
            if isinstance(o, np.integer):
                return int(o)
            if isinstance(o, np.floating):
                f = float(o)
                return None if (math.isnan(f) or math.isinf(f)) else f
            if isinstance(o, np.ndarray):
                return o.tolist()
            return super().default(o)

    return json.loads(json.dumps(obj, cls=_Cleaner, allow_nan=False))


def _merge_dedupe(
    old: List[Dict[str, Any]], new: List[Dict[str, Any]]
) -> Optional[List[Dict[str, Any]]]:
    """دمج تصاعدي مع إزالة التكرار بالزمن (الأحدث يغلب).

    يعيد None إذا وُجدت شمعة بلا زمن قابل للاستخراج — إشارة تنسيق مجهول
    يستوجب تجاوز الكاش (لا نخزن ما لا نستطيع دمجه بأمان).
    """
    by_time: Dict[int, Dict[str, Any]] = {}
    for c in old:
        t = _candle_time(c)
        if t is None:
            return None
        by_time[t] = c
    for c in new:
        t = _candle_time(c)
        if t is None:
            return None
        by_time[t] = c
    return [by_time[t] for t in sorted(by_time.keys())]


def _clip(candles: List[Dict[str, Any]], start_epoch: int) -> List[Dict[str, Any]]:
    """قص الشموع إلى النافذة المطلوبة (من start_epoch فصاعداً)."""
    return [c for c in candles if (_candle_time(c) or 0) >= start_epoch]


# ==========================================================================
# مخطط DataFrame (فضاء d) — التقاط وإعادة بناء بنفس الشكل
# ==========================================================================
def _capture_df_schema(df) -> Optional[Dict[str, Any]]:
    """التقاط مخطط الإطار: الأعمدة، الأنواع، والفهرس — لإعادة بناء مطابقة."""
    try:
        import pandas as pd

        had_index = not isinstance(df.index, pd.RangeIndex)
        index_col = None
        work = df
        if had_index:
            work = df.reset_index()
            # اسم العمود الناتج عن الفهرس: اسمه أو "index"/"level_0"
            new_cols = [c for c in work.columns if c not in df.columns]
            if not new_cols:
                return None
            index_col = str(new_cols[0])
        return {
            "columns": [str(c) for c in work.columns],
            "dtypes": {str(c): str(work[c].dtype) for c in work.columns},
            "had_index": had_index,
            "index_col": index_col,
        }
    except Exception:  # noqa: BLE001
        return None


def _records_from_df(df) -> Optional[List[Dict[str, Any]]]:
    """سجلات JSON-آمنة من الإطار (مع الفهرس إن وجد كعمود)."""
    try:
        work = df
        if not isinstance(df.index, __import__("pandas").RangeIndex):
            work = df.reset_index()
        recs = work.to_dict("records")
        return _json_safe(recs)
    except Exception:  # noqa: BLE001
        return None


def _df_from_records(
    records: List[Dict[str, Any]], schema: Optional[Dict[str, Any]]
) -> Optional[Any]:
    """إعادة بناء DataFrame بنفس أعمدة وأنواع وفهرس الأصل."""
    if not schema:
        return None
    try:
        import pandas as pd

        df = pd.DataFrame(records)
        columns = schema.get("columns") or []
        for c in columns:
            if c not in df.columns:
                df[c] = None
        if columns:
            df = df[columns]
        for col, dtype in (schema.get("dtypes") or {}).items():
            if col not in df.columns:
                continue
            dt = str(dtype)
            try:
                if dt.startswith("datetime64"):
                    df[col] = pd.to_datetime(df[col])
                elif dt in ("float64", "float32", "Float64"):
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype(dt)
                elif dt in ("int64", "int32", "Int64"):
                    df[col] = pd.to_numeric(df[col], errors="raise").astype(dt)
                elif dt == "bool":
                    df[col] = df[col].astype(bool)
            except (ValueError, TypeError):
                # عمود واحد فاسد لا يُسقط الكاش كله — يبقى بأقرب نوع
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if schema.get("had_index") and schema.get("index_col") in df.columns:
            df = df.set_index(schema["index_col"])
        return df
    except Exception:  # noqa: BLE001
        return None


# ==========================================================================
# نتيجة الجلب الموحدة
# ==========================================================================
@dataclass
class CacheResult:
    candles: List[Dict[str, Any]]
    cache_hit: bool
    cached_count: int = 0
    fetched_new: int = 0
    total: int = 0
    note: str = ""
    extra: Optional[Dict[str, Any]] = None  # نقل داخلي (الإطار المُعاد بناؤه)

    def as_meta(self) -> Dict[str, Any]:
        return {
            "cache": {
                "hit": self.cache_hit,
                "cached": self.cached_count,
                "fetched_new": self.fetched_new,
                "total": self.total or len(self.candles),
                "note": self.note,
            }
        }


# ==========================================================================
# الخدمة
# ==========================================================================
class CandleCacheService:
    """قراءة/دمج/حفظ الشموع لكل (symbol, timeframe, market) — دائم في القاعدة."""

    def __init__(self, session_maker=None, clock: Optional[Callable[[], float]] = None):
        self._sm = session_maker
        self._clock = clock or self._default_clock
        # آخر نتيجة (للشفافية: يقرأها المستدعي ليعرض إحصاءات الكاش)
        self.last_meta: Dict[str, Any] = {}
        # مخطط الـDataFrame الملتقط في هذا الطلب (فضاء d)
        self._captured_schema: Optional[Dict[str, Any]] = None

    @staticmethod
    def _default_clock() -> float:
        """ساعة حقيقية، مع خطاف اختبار (R45_TEST_CLOCK_EPOCH) للبيئات
        المضبوطة زمنياً فقط — لا أثر له في الإنتاج مطلقاً."""
        epoch = os.environ.get("R45_TEST_CLOCK_EPOCH")
        if epoch:
            try:
                return float(epoch)
            except ValueError:
                pass
        return _time.time()

    def _resolve_sm(self):
        if self._sm is not None:
            return self._sm
        from app.database.session import AsyncSessionLocal

        return AsyncSessionLocal

    # ------------------------------------------------------------------
    # واجهة فضاء الشموع (المسار الموحد ج42)
    # ------------------------------------------------------------------
    async def get_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        market: str,
        days: int,
        fetch_df: Callable[[int], Any],
        df_to_candles: Callable[[Any], List[Dict[str, Any]]],
    ) -> CacheResult:
        """شموع المسار الموحد: كاملة من الكاش + تحديث الرأس عند الحاجة."""
        if not _ENABLED:
            df = await fetch_df(days)
            candles = df_to_candles(df)
            result = CacheResult(
                candles=candles, cache_hit=False,
                fetched_new=len(candles), note="cache disabled",
            )
            self.last_meta = result.as_meta()
            return result
        try:
            result = await self._cached_window(
                namespace="c",
                symbol=symbol, timeframe=timeframe, market=market, days=days,
                fetch_records=self._wrap_fetcher(fetch_df, df_to_candles),
            )
        except Exception as exc:  # noqa: BLE001 — تجاوز آمن دائماً
            logger.warning("🛡️ [R45] candle-cache bypass (c): %s", exc)
            df = await fetch_df(days)
            candles = df_to_candles(df)
            result = CacheResult(
                candles=candles, cache_hit=False, fetched_new=len(candles),
                note=f"bypass: {exc}",
            )
        self.last_meta = result.as_meta()
        return result

    # ------------------------------------------------------------------
    # واجهة فضاء الـDataFrame (المسار القياسي)
    # ------------------------------------------------------------------
    async def get_dataframe(
        self,
        *,
        symbol: str,
        timeframe: str,
        market: str,
        days: int,
        fetch_df: Callable[[int], Any],
    ) -> Any:
        """إطار المسار القياسي: نفس الأعمدة/الأنواع/الفهرس التي أنتجها
        المزوّد — يُعاد بناؤها من الكاش عند التغطية، مع تحديث الرأس."""
        if not (_ENABLED and _DFSPACE_ENABLED):
            return await fetch_df(days)
        try:
            result = await self._cached_window(
                namespace="d",
                symbol=symbol, timeframe=timeframe, market=market, days=days,
                fetch_records=self._wrap_fetcher(fetch_df, None),
            )
            # الإطار المُعاد بناؤه يصل عبر البند الخاص في stats
            df = result.extra.get("_df") if result.extra else None
            if df is None:
                raise ValueError("df rebuild produced nothing")
            self.last_meta = result.as_meta()
            return df
        except Exception as exc:  # noqa: BLE001 — تجاوز آمن دائماً
            logger.warning("🛡️ [R45] candle-cache bypass (d): %s", exc)
            self.last_meta = {"cache": {"hit": False, "note": f"bypass: {exc}"}}
            return await fetch_df(days)

    # ------------------------------------------------------------------
    # الجوهر المشترك
    # ------------------------------------------------------------------
    async def _cached_window(
        self,
        *,
        namespace: str,
        symbol: str,
        timeframe: str,
        market: str,
        days: int,
        fetch_records: Callable[[int], Any],
    ) -> CacheResult:
        from app.services.task_registry import ensure_registry_tables

        await ensure_registry_tables()
        sm = self._resolve_sm()

        key = f"{namespace}:{market}:{symbol}:{timeframe}"
        now = self._clock()
        need_start = int(now - max(1, int(days)) * 86400)

        entry = await self._load(sm, key)
        if entry is not None and namespace == "d" and not entry.get("schema"):
            entry = None  # سجل فضاء c لا يصلح لفضاء d

        interval = _INTERVALS.get(str(timeframe).lower()) or (
            _infer_interval(timeframe, entry["candles"]) if entry else None
        )
        extra: Dict[str, Any] = {}

        # ---------------- تغطية كاملة: اقرأ من القاعدة + حدّث الرأس --------
        if entry is not None and entry["first_time"] <= need_start + (interval or 0):
            candles = list(entry["candles"])
            cached_count = len(candles)
            fetched_new = 0
            note = "full coverage from cache"
            last_t = entry["last_time"]

            if _REFRESH_HEAD and interval and last_t < now - interval:
                gap = now - last_t
                head_days = max(1, math.ceil(gap / 86400.0))
                head_recs = await fetch_records(head_days)
                merged = _merge_dedupe(candles, head_recs)
                if merged is not None:
                    fetched_new = max(0, len(merged) - cached_count)
                    candles = merged
                    note = f"head refresh: fetched {head_days}d, +{fetched_new} candles"
                    await self._save(
                        sm, key, namespace, symbol, timeframe, market,
                        candles, entry.get("schema"), note,
                    )
            out_records = _clip(candles, need_start - (interval or 0))
            result = CacheResult(
                candles=out_records, cache_hit=True,
                cached_count=cached_count, fetched_new=fetched_new,
                total=len(out_records), note=note,
            )
        # ---------------- لا تغطية: جلب كامل + دمج مع المخزون -------------
        else:
            recs = await fetch_records(days)
            if entry is not None:
                merged = _merge_dedupe(entry["candles"], recs)
                if merged is not None:
                    recs_all, note = merged, "full fetch merged with cache"
                else:
                    recs_all, note = recs, "full fetch (merge incompatible)"
            else:
                recs_all, note = recs, "full fetch (cold cache)"
            fetched_new = len(recs)
            await self._save(
                sm, key, namespace, symbol, timeframe, market,
                recs_all, self._captured_schema, note,
            )
            out_records = _clip(recs_all, need_start - (interval or 0))
            result = CacheResult(
                candles=out_records, cache_hit=False,
                cached_count=max(0, len(recs_all) - fetched_new),
                fetched_new=fetched_new, total=len(out_records), note=note,
            )

        # فضاء d: أعد بناء الإطار من السجلات بالمخطط (الملقوط أو المخزون)
        if namespace == "d":
            schema = self._captured_schema or (entry or {}).get("schema")
            if not schema:
                raise ValueError("missing df schema for namespace d")
            df = _df_from_records(out_records, schema)
            if df is None:
                raise ValueError("df rebuild failed")
            extra["_df"] = df
            result.extra = extra
        return result

    def _wrap_fetcher(
        self,
        fetch_df: Callable[[int], Any],
        df_to_candles: Optional[Callable[[Any], List[Dict[str, Any]]]],
    ) -> Callable[[int], Any]:
        """تغليف الجالب: DataFrame ⇦ سجلات JSON-آمنة (+ التقاط مخطط d)."""
        svc = self

        async def _fetch(days: int) -> List[Dict[str, Any]]:
            df = await fetch_df(days)
            if df_to_candles is not None:
                return _json_safe(df_to_candles(df))
            schema = _capture_df_schema(df)
            recs = _records_from_df(df)
            if schema is None or recs is None:
                raise ValueError("unrecognized dataframe shape")
            svc._captured_schema = schema
            return recs

        return _fetch

    # ------------------------------------------------------------------
    # التخزين
    # ------------------------------------------------------------------
    async def _load(self, sm, key: str) -> Optional[Dict[str, Any]]:
        from app.models.candle_cache import CandleCache

        try:
            async with sm() as db:
                result = await db.execute(
                    select(CandleCache).where(CandleCache.cache_key == key)
                )
                row = result.scalar_one_or_none()
                if row is None or not row.candles:
                    return None
                candles = row.candles
                if not isinstance(candles, list) or not candles:
                    return None
                if _candle_time(candles[0]) is None:
                    return None
                return {
                    "candles": candles,
                    "schema": row.schema_json,
                    "first_time": int(row.first_time or 0),
                    "last_time": int(row.last_time or 0),
                    "count": int(row.count or 0),
                }
        except Exception:  # noqa: BLE001
            logger.exception("[R45] cache load failed for %s", key)
            return None

    async def _save(
        self,
        sm,
        key: str,
        namespace: str,
        symbol: str,
        timeframe: str,
        market: str,
        candles: List[Dict[str, Any]],
        schema: Optional[Dict[str, Any]],
        note: str,
    ) -> bool:
        """حفظ/تحديث السجل — فشله لا يكسر التشغيل أبداً (يُسجَّل فقط).

        ملاحظة التزامن: دمجَان متزامنان لنفس المفتاح قد يكتب أحدهما فوق
        الآخر (نافذة مفقودة) — ذاتية الشفاء: تحديث الرأس التالي يجلبها.
        الكتابة نفسها تسلسلية عبر قفل الكتابة في القاعدة + درع R44.
        """
        from app.models.candle_cache import CandleCache
        from app.services.task_registry import utcnow_naive

        if not candles:
            return False
        if len(candles) > _MAX_CANDLES:
            candles = candles[-_MAX_CANDLES:]
        times = [_candle_time(c) for c in candles]
        if any(t is None for t in times):
            return False
        now = utcnow_naive()
        values = {
            "candles": candles,
            "schema_json": schema,
            "first_time": int(min(times)),
            "last_time": int(max(times)),
            "count": len(candles),
            "last_fetch_note": (note or "")[:500],
            "updated_at": now,
        }

        async def _do_save() -> None:
            async with sm() as db:
                result = await db.execute(
                    sa_update(CandleCache).where(CandleCache.cache_key == key),
                    values,
                )
                if not (result.rowcount or 0):
                    db.add(
                        CandleCache(
                            cache_key=key,
                            symbol=str(symbol)[:32],
                            timeframe=str(timeframe)[:16],
                            market=str(market)[:16],
                            namespace=namespace,
                            created_at=now,
                            **values,
                        )
                    )
                await db.commit()

        try:
            await with_lock_retry(_do_save, what=f"candle-cache save {key}")
            return True
        except Exception:  # noqa: BLE001 — فشل الحفظ لا يكسر التشغيل
            logger.exception("[R45] cache save failed for %s", key)
            return False

    # ------------------------------------------------------------------
    # إدارة الكاش (شفافية للواجهة)
    # ------------------------------------------------------------------
    async def list_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        from app.models.candle_cache import CandleCache
        from app.services.task_registry import ensure_registry_tables

        await ensure_registry_tables()
        sm = self._resolve_sm()
        async with sm() as db:
            rows = (
                (
                    await db.execute(
                        select(CandleCache)
                        .order_by(CandleCache.updated_at.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            out = []
            for r in rows:
                out.append(
                    {
                        "cache_key": r.cache_key,
                        "namespace": r.namespace,
                        "symbol": r.symbol,
                        "timeframe": r.timeframe,
                        "market": r.market,
                        "count": r.count,
                        "first_time": r.first_time,
                        "last_time": r.last_time,
                        "first_time_iso": datetime.fromtimestamp(
                            int(r.first_time or 0), tz=timezone.utc
                        ).isoformat(),
                        "last_time_iso": datetime.fromtimestamp(
                            int(r.last_time or 0), tz=timezone.utc
                        ).isoformat(),
                        "last_fetch_note": r.last_fetch_note,
                        "updated_at": (
                            r.updated_at.isoformat() if r.updated_at else None
                        ),
                    }
                )
            return out

    async def delete_entry(self, cache_key: str) -> bool:
        from app.models.candle_cache import CandleCache
        from app.services.task_registry import ensure_registry_tables

        await ensure_registry_tables()
        sm = self._resolve_sm()
        async with sm() as db:
            result = await db.execute(
                sa_delete(CandleCache).where(CandleCache.cache_key == cache_key)
            )
            await db.commit()
            return bool(result.rowcount)


# ==========================================================================
# غلاف شفاف لـDataService (المسار القياسي) — كاش بلا تعديل المحرك
# ==========================================================================
class CachedDataService:
    """وكيل كاش حول DataService.get_historical.

    يعترض نداءات جلب الشموع ويخدمها من كاش القاعدة عند التغطية، ويجلب
    فقط الرأس الناقص فوقها. كل ما عدا get_historical يُمرَّر حرفياً إلى
    الخدمة الأصلية عبر __getattr__ — المحرك لا يرى أي فرق.

    ربط الوسائط يتم عبر توقيع الدالة الأصلية نفسه (inspect.bind) فيصح
    الاعتراض سواء استُدعيت بالكلمات المفتاحية أو بالموقع.
    """

    def __init__(self, inner: Any, session_maker=None):
        self._inner = inner
        self._cache = CandleCacheService(session_maker=session_maker)
        self.stats: Dict[str, Any] = {"hits": 0, "misses": 0, "last": None}

    @property
    def last_meta(self) -> Dict[str, Any]:
        """إحصاءات آخر جلب (مثل CandleCacheService) — بلا تمرير للأصل."""
        return self._cache.last_meta or {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def get_historical(self, *args, **kwargs):
        try:
            sig = inspect.signature(self._inner.get_historical)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            symbol = bound.arguments.get("symbol")
            timeframe = bound.arguments.get("timeframe")
            market = bound.arguments.get("market") or "crypto"
            days = bound.arguments.get("days")
            if not symbol or not timeframe or not days:
                raise KeyError("missing symbol/timeframe/days")
        except (KeyError, TypeError):
            # توقيع لا نستطيع ربطه بأمان ⇦ تمرير حرفي بلا كاش
            self.stats["misses"] += 1
            self.stats["last"] = "delegate (unbindable call)"
            return await self._inner.get_historical(*args, **kwargs)

        async def _fetch(fetch_days: int):
            call_kw = dict(bound.arguments)
            call_kw["days"] = fetch_days
            try:
                return await self._inner.get_historical(**call_kw)
            except TypeError:
                # وسائط موقعية-فقط في التوقيع الأصلي ⇦ أعد التركيب كما كان
                pos, kw = [], {}
                for p in sig.parameters.values():
                    if p.name in call_kw:
                        if p.kind in (
                            inspect.Parameter.POSITIONAL_ONLY,
                            inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        ):
                            pos.append(call_kw[p.name])
                        else:
                            kw[p.name] = call_kw[p.name]
                return await self._inner.get_historical(*pos, **kw)

        df = await self._cache.get_dataframe(
            symbol=str(symbol),
            timeframe=str(timeframe),
            market=str(market or "crypto"),
            days=int(days),
            fetch_df=_fetch,
        )
        hit = bool((self._cache.last_meta or {}).get("cache", {}).get("hit"))
        self.stats["hits" if hit else "misses"] += 1
        self.stats["last"] = (self._cache.last_meta or {}).get("cache", {}).get("note")
        return df
