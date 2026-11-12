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

✅ R61 — إصلاح فجوة الكاش (مقارنة النطاق المطلوب بالنطاق المخزون):
  * عيب R58 المُثبت بالإنتاج: فرع «التغطية الكاملة» كان يفحص first_time
    فقط، و«تحديث الرأس» كان يدمج أي شظية يعيدها المزوّد بلا تحقق.
    النتيجة: #10000098 استلم 5,779 من 43,200 شمعة (13.4%) بحالة
    hit:true صامتة و0 صفقات، بينما #10000099 (نفس الطلب بعد حذف
    المفتاح) استلم 43,200 كاملة و9 صفقات (−2.06%).
  * الآن: عند كل cache hit تُحسب القطع المغطاة فعلياً داخل النافذة
    (segments) والفجوات فوق التحمّل الطبيعي (holes) — بادئة وداخلية
    وذيلية — ثم تُجلب كل فجوة من المصدر وتُدمج (نفس مسار الدمج المُثبت
    في 688,139 شمعة). ما أكّد المصدر فراغه ⇦ فجوة طبيعية معلَنة، وما
    فشل جلبه ⇦ بطاقة تغطية صريحة (coverage_pct/gaps_remaining) —
    ممنوع النجاح الصامت.
  * بطاقة الشفافية (كائن cache في حمولة المهمة): requested_start/end،
    stored_start/end، expected_candles، delivered_candles،
    coverage_pct، gap_filled، gaps_detected/remaining، natural_gaps،
    fill_calls، fetch_incomplete.
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

# ✅ R61 — إصلاح فجوة الكاش: عتبات مقارنة النطاق المطلوب بالنطاق المخزون.
# عيب R58 المُثبت بالإنتاج (#10000098 مقابل #10000099): فرع «التغطية الكاملة»
# كان يكتفي بِـ first_time <= need_start فتُسلَّم شظية رأس مدموجة فوق جبنٍ
# سويسري سابق بحالة hit:true صامتة — المحرك يستلم 13% من نافذته ويخرج
# بـ 0 صفقات «بنجاح». الآن: تُحسب القطع المغطاة فعلياً داخل النافذة، وكل
# فراغ فوق التحمّل الطبيعي فجوةٌ تُجلب من المصدر وتُدمج، وما عجز المصدر
# عن ملئه يُعلَن بصدق (بطاقة تغطية كاملة في كائن cache) — لا نجاح صامت.
_GAP_TOL_MULT = max(1, int(getattr(settings, "CANDLE_CACHE_GAP_TOLERANCE_MULT", 3) or 3))
_MAX_GAP_FETCHES = max(1, int(getattr(settings, "CANDLE_CACHE_MAX_GAP_FETCHES", 6) or 6))
# أسهم الأسواق الأمريكية لا تتداول ليلاً/عطلات — فجواتها الطبيعية ضخمة
# مقارنة بعرض الشمعة، فالتهاون الخاص بها يمنع إعادة جلب عقيمة كل طلب.
_STOCKS_NATURAL_GAP_S = int(3.5 * 86400)


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


def _clip_end(candles: List[Dict[str, Any]], end_epoch: int) -> List[Dict[str, Any]]:
    """✅ R57 — قصّ نهاية النافذة: لا شمعة تفتح بعد end_epoch.

    جذر الخلل المُبلَّغ من الاختبار الحي (S4 — مستند التوأم الموحد):
    طلب نافذة 2024-06-01 → 2024-06-04 عبر المسار الموحد نفّذ حتى «الآن»
    (2026-11-08) — البداية كانت تُحترم والنهاية لا. السبب: فضاء d يخزّن
    شموعاً أبعد من نهاية الطلب (من أي جلب «آخر N يوم من الآن» سابق)،
    و _clip أعلاه يقصّ البداية فقط فكان ذيل الكاش يتسرب إلى النتيجة.
    هذا القصّ يعيد النهاية بدلالات المزوّد نفسها: آخر شمعة مغلقة داخل
    النافذة (open ≤ end − عرض الفريم) — فالمساران بارد/دافئ حتميان.
    """
    return [c for c in candles if (_candle_time(c) or 0) <= end_epoch]


# ==========================================================================
# ✅ R61 — بطاقة تغطية النافذة: مقارنة النطاق المطلوب بالنطاق المخزون فعلياً
# ==========================================================================
def _iso_utc(epoch: Optional[int]) -> Optional[str]:
    """epoch ثوانٍ ⇦ ISO-8601 UTC — لحقول الشفافية في بطاقة الكاش."""
    if not epoch:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):  # noqa: BLE001
        return None


def _expected_candles(need_start: int, need_end: int, interval: Optional[int]) -> Optional[int]:
    """عدد الشموع المتوقع نظرياً للنافذة (مدة ÷ عرض الفريم).

    365d·1m ⇦ 525,600 بالضبط (نفس أرقام بطاقة المستخدم) — مرجع حسابي
    للمقارنة، لا عتبة صرامة: الشموع الفعلية قد تقل قليلاً (إغلاق آخر شمعة،
    دقائق صيانة) والعتبة الزمنية للفجوات هي الحكم.
    """
    if not interval or need_end <= need_start:
        return None
    return int((need_end - need_start) // interval)


def _natural_tolerance_s(interval: Optional[int], market: str) -> int:
    """أقصى فراغ زمني يُعتبر طبيعياً بين شمعتين متتاليتين."""
    tol = int(interval or 0) * _GAP_TOL_MULT
    if str(market).strip().lower() == "stocks":
        tol = max(tol, _STOCKS_NATURAL_GAP_S)
    return tol


def _analyze_window_coverage(
    times: List[int],
    need_start: int,
    need_end: int,
    interval: Optional[int],
    natural_tolerance: int,
) -> Dict[str, Any]:
    """R61 — تحليل التغطية الفعلية داخل النافذة المطلوبة.

    لا يُكتفى بِـ first_time (عيب R58 القاتل): نمرّ على أوقات الشموع داخل
    النافذة، ندمج المتقاربات (فراغ ≤ التحمّل الطبيعي) في قطع مغطاة،
    ونُخرج الفجوات فوق التحمّل — بادئة كانت أم داخلية أم ذيلية. الحدود
    الطرفية على شبكة الشموع (لا فجوة «بـ16 ثانية» لمجرد أن بداية الطلب
    غير موائمة للشبكة).

    يعيد:
      segments    [(s,e)] القطع المغطاة فعلاً (ممدودة إلى حافتي النافذة
                  عند انتفاء الفجوة الطرفية المقابلة)
      holes       [(s,e)] الفجوات: بادئة (need_start ← أول شمعة)، وسطى
                  (بين قطعتين بفراغ > التحمّل)، ذيلية (بعد آخر شمعة
                  المتوقعة)
      coverage_pct نسبة التغطية الزمنية داخل النافذة (0..100)
      covered_s / window_s   الثواني المغطاة / مدة النافذة
    """
    card: Dict[str, Any] = {
        "segments": [],
        "holes": [],
        "leading_hole": False,
        "covered_s": 0,
        "window_s": max(0, int(need_end) - int(need_start)),
        "coverage_pct": None,
    }
    if need_end <= need_start:
        card["coverage_pct"] = 100.0
        return card
    win = [t for t in times if need_start <= t <= need_end]
    if not win:
        # لا شمعة إطلاقاً داخل النافذة ⇦ النافذة كلها فجوة بادئة
        card["holes"] = [(int(need_start), int(need_end))]
        card["leading_hole"] = True
        card["coverage_pct"] = 0.0
        return card
    if not interval:
        # بلا عرض فريم معروف لا يمكن تعريف «فجوة» — تغطية تقريبية بالامتداد
        s0, e0 = max(win[0], need_start), min(win[-1], need_end)
        card["segments"] = [(s0, e0)]
        card["covered_s"] = max(0, e0 - s0)
        card["coverage_pct"] = round(
            min(100.0, 100.0 * card["covered_s"] / card["window_s"]), 2
        )
        return card
    interval = int(interval)
    # الحدود المتوقعة على شبكة الشموع: أول شمعة يفترض أن توجد، وآخر شمعة
    # مغلقة يمكن أن توجد داخل النافذة.
    first_expected = -(-int(need_start) // interval) * interval  # ceil
    last_expected = max(first_expected, (int(need_end) - interval) // interval * interval)
    # قطع مغطاة: متتاليات بفروق ≤ التحمّل تندمج (الفراغات الصغيرة طبيعية)
    segs: List[List[int]] = [[win[0], win[0]]]
    for t in win[1:]:
        if t - segs[-1][1] <= natural_tolerance:
            segs[-1][1] = t
        else:
            segs.append([t, t])
    # الفجوات: بادئة / وسطى / ذيلية — كلها بحدود قابلة للجلب مباشرة
    holes: List[tuple] = []
    if win[0] > first_expected:
        holes.append((int(need_start), win[0]))
        leading = True
    else:
        leading = False
    for (prev_s, prev_e), (next_s, _next_e) in zip(segs, segs[1:]):
        if next_s - prev_e > natural_tolerance:
            holes.append((prev_e, next_s))
    if win[-1] < last_expected:
        holes.append((win[-1] + interval, int(need_end)))
    # القطع المغطاة للنسبة: ممدودة إلى حافتي النافذة عند انتفاء الفجوة
    # الطرفية المقابلة (كاش مكتمل حتى آخر شمعة مغلقة ⇦ 100.0 نظيفة)
    cov: List[tuple] = []
    for i, (s, e) in enumerate(segs):
        s2 = int(need_start) if i == 0 and win[0] <= first_expected else s
        e2 = (
            int(need_end)
            if i == len(segs) - 1 and win[-1] >= last_expected
            else min(e + interval, int(need_end))
        )
        cov.append((s2, max(s2, e2)))
    covered = sum(e - s for s, e in cov)
    card["segments"] = cov
    card["holes"] = holes
    card["leading_hole"] = leading
    card["covered_s"] = covered
    card["coverage_pct"] = round(min(100.0, 100.0 * covered / card["window_s"]), 2)
    return card


def _plan_gap_fetches(holes: List[tuple]) -> List[tuple]:
    """تخطيط جلب الفجوات: دقيقة ما أمكن، مدموجة عند التفشّط.

    ≤ _MAX_GAP_FETCHES فجوة ⇦ جلب كل واحدة بنطاقها الحقيقي (لا نعيد جلب
    ما هو مخزون أصلاً). فوقها (جبن سويسري من دموج شظايا سابقة) ⇦ جلب
    واحد موحّد [أول فجوة ← آخر فجوة] — حد أعلى صارم لنداءات المزوّد.
    """
    if not holes:
        return []
    if len(holes) <= _MAX_GAP_FETCHES:
        return [(int(s), int(e)) for s, e in holes]
    return [(int(min(s for s, _ in holes)), int(max(e for _, e in holes)))]


# ==========================================================================
# مخطط DataFrame (فضاء d) — التقاط وإعادة بناء بنفس الشكل
# ==========================================================================
def _schema_is_usable(schema: Optional[Dict[str, Any]]) -> bool:
    """مخطط صالح لإعادة البناء: فيه نوع معروف واحد على الأقل.

    المزوّد يعيد للنوافذ الفارغة إطاراً بأعمدة object كلها — مخطط مسخ
    لو طغى على المخطط الجيد لفسدت إعادة البناء (R45.1: جرح جلب الرأس
    الفارغ). نطلب نوعاً معروفاً واحداً على الأقل (زمني/عددي) لنقبله.
    """
    if not schema:
        return False
    dtypes = schema.get("dtypes") or {}
    if not dtypes:
        return False
    known = ("datetime64", "float64", "float32", "int64", "int32", "bool")
    return any(str(v).startswith(known) or str(v) in known for v in dtypes.values())


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
    # ---- ✅ R61 — بطاقة تغطية الشفافية (كائن cache في حمولة المهمة) ----
    requested_start: Optional[int] = None   # بداية النافذة المطلوبة (epoch s)
    requested_end: Optional[int] = None     # نهاية النافذة المطلوبة (epoch s)
    stored_start: Optional[int] = None      # أول شمعة في المخزون بعد الدمج
    stored_end: Optional[int] = None        # آخر شمعة في المخزون بعد الدمج
    expected_candles: Optional[int] = None  # المتوقع النظري (مدة ÷ عرض الفريم)
    delivered_candles: int = 0              # ما استلمه المحرك فعلاً داخل نافذته
    coverage_pct: Optional[float] = None    # نسبة التغطية الزمنية داخل النافذة
    gaps_detected: int = 0                  # فجوات فوق التحمّل وجدت عند الطلب
    gaps_remaining: int = 0                 # فجوات بقيت بعد كل محاولات الملء
    natural_gaps: int = 0                   # فجوات أكّد المصدر أنها فارغة أصلاً
    gap_filled: bool = True                 # true ⇔ لا فجوة ناقصة في التسليم
    fill_calls: int = 0                     # نداءات جلب أُنفذت لملء الفجوات
    fetch_incomplete: bool = False          # المزوّد وسم جلبه بالنقص (تهدئة)

    def as_meta(self) -> Dict[str, Any]:
        return {
            "cache": {
                # الحقول التاريخية (R45) — كما هي للتوافق المطلق
                "hit": self.cache_hit,
                "cached": self.cached_count,
                "fetched_new": self.fetched_new,
                "total": self.total or len(self.candles),
                "note": self.note,
                # ✅ R61 — بطاقة التغطية (بطاقة الفرونت تعرضها فوراً)
                "requested_start": _iso_utc(self.requested_start),
                "requested_end": _iso_utc(self.requested_end),
                "stored_start": _iso_utc(self.stored_start),
                "stored_end": _iso_utc(self.stored_end),
                "expected_candles": self.expected_candles,
                "delivered_candles": self.delivered_candles or (self.total or len(self.candles)),
                "coverage_pct": self.coverage_pct,
                "gaps_detected": self.gaps_detected,
                "gaps_remaining": self.gaps_remaining,
                "natural_gaps": self.natural_gaps,
                "gap_filled": self.gap_filled,
                "fill_calls": self.fill_calls,
                "fetch_incomplete": self.fetch_incomplete,
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
        # ✅ R61 — وسم المزوّد للجلب الناقص (تهدئة/حظر): يُلتقط من attrs
        # في الغلافين ويظهر في بطاقة التغطية (fetch_incomplete)
        self._fetch_incomplete: bool = False

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
    # واجهة فضاء الـDataFrame بنطاق تواريخ صريح (get_historical_last_version)
    # ------------------------------------------------------------------
    async def get_dataframe_range(
        self,
        *,
        symbol: str,
        timeframe: str,
        market: str,
        start_ts: int,
        end_ts: int,
        fetch_range_df: Callable[[int, int], Any],
    ) -> Any:
        """إطار المسار القياسي بنطاق [start_ts, end_ts] بالثواني.

        المحرك القياسي (engine1) يستدعي get_historicallastvirsion /
        get_historical_last_version بتواريخ صريحة — هذه الواجهة تخدمهما:
        نفس الأعمدة/الأنواع/الفهرس التي أنتجها المزوّد، مع تحديث الرأس.
        """
        if not (_ENABLED and _DFSPACE_ENABLED):
            return await fetch_range_df(start_ts, end_ts)
        try:
            result = await self._cached_window(
                namespace="d",
                symbol=symbol, timeframe=timeframe, market=market, days=0,
                fetch_records=None,
                window_start=int(start_ts), window_end=int(end_ts),
                fetch_range=self._wrap_range_fetcher(fetch_range_df, None),
            )
            df = result.extra.get("_df") if result.extra else None
            if df is None:
                raise ValueError("df rebuild produced nothing")
            self.last_meta = result.as_meta()
            return df
        except Exception as exc:  # noqa: BLE001 — تجاوز آمن دائماً
            logger.warning("🛡️ [R45] candle-cache bypass (d-range): %s", exc)
            self.last_meta = {"cache": {"hit": False, "note": f"bypass: {exc}"}}
            return await fetch_range_df(start_ts, end_ts)

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
        fetch_records: Optional[Callable[[int], Any]] = None,
        window_start: Optional[int] = None,
        window_end: Optional[int] = None,
        fetch_range: Optional[Callable[[int, int], Any]] = None,
    ) -> CacheResult:
        from app.services.task_registry import ensure_registry_tables

        await ensure_registry_tables()
        sm = self._resolve_sm()

        key = f"{namespace}:{market}:{symbol}:{timeframe}"
        now = self._clock()
        # وضع النطاق (تواريخ صريحة): الإطار الزمني من الطلب نفسه
        range_mode = (
            window_start is not None
            and window_end is not None
            and fetch_range is not None
        )
        eff_now = int(window_end) if range_mode else now
        if range_mode:
            need_start = int(window_start)
        else:
            need_start = int(now - max(1, int(days)) * 86400)
        # ✅ R61 — نهاية النافذة صريحة في المسارين (أعيد اكتشاف الفجوات
        # الذيلية التي كان «تحديث الرأس» يخاطها بلا تحقق)
        need_end = int(eff_now)

        entry = await self._load(sm, key)
        if entry is not None and namespace == "d" and not entry.get("schema"):
            entry = None  # سجل فضاء c لا يصلح لفضاء d

        interval = _INTERVALS.get(str(timeframe).lower()) or (
            _infer_interval(timeframe, entry["candles"]) if entry else None
        )
        tol = _natural_tolerance_s(interval, market)
        extra: Dict[str, Any] = {}
        self._fetch_incomplete = False  # R61 — وسم المزوّد (تهدئة) يلتقطه الغلاف

        # ------------------------------------------------------------------
        # ✅ R61 — المنطق الجديد: بطاقة تغطية ⇦ املأ الفجوة ⇦ اصرح بالباقي
        #
        # عيب R58: فرع «التغطية الكاملة» كان يفحص first_time فقط، وفرع
        # «تحديث الرأس» كان يدمج أي شظية يعيدها المزوّد بلا تحقق. النتيجة
        # الإنتاجية: #10000098 استلم 5,779 من 43,200 شمعة (13.4%) بحالة
        # hit:true صامتة و0 صفقات، بينما #10000099 (بعد حذف المفتاح)
        # استلم 43,200 كاملة و9 صفقات. الآن:
        #   1) تُقارن النافذة المطلوبة بالمخزون قطعةً قطعة (لا first_time).
        #   2) كل فجوة فوق التحمّل الطبيعي ⇦ تُجلب من المصدر وتُدمج
        #      (نفس مسار الدمج المُثبت في 688,139 شمعة).
        #   3) ما أكّد المصدر أنه فارغ ⇦ فجوة طبيعية معلَنة، وما فشل جلبه
        #      ⇦ يُعاد بحالة صريحة — ممنوع النجاح الصامت.
        # ------------------------------------------------------------------
        def _times_of(cands: List[Dict[str, Any]]) -> List[int]:
            ts = [t for t in (_candle_time(c) for c in cands) if t]
            if not all(a < b for a, b in zip(ts, ts[1:])):
                ts = sorted(set(ts))
            return ts

        candles: List[Dict[str, Any]] = list(entry["candles"]) if entry else []
        cached_count = len(candles)
        fetched_new = 0
        fill_calls = 0
        natural_ranges: List[tuple] = []
        gaps_detected = 0
        hit = False
        note = "full fetch (cold cache)"
        saved = False

        pre_card = (
            _analyze_window_coverage(
                _times_of(candles), need_start, need_end, interval, tol
            )
            if candles
            else None
        )
        pre_holes = list(pre_card["holes"]) if pre_card else []
        gaps_detected = len(pre_holes)
        # ✅ R61 — الفجوة البادئة علمٌ بنيوي من المحلّل (فجوة وسطى ملاصقة
        # لأول شمعة عند بداية النافذة ليست بادئة — علامها قد تتساوى مع
        # need_start فلا يصح الحكم بالقيمة)
        leading_gap = bool(pre_card and pre_card.get("leading_hole"))

        async def _merge_and_save(
            new_recs: List[Dict[str, Any]], schema, save_note: str
        ) -> bool:
            """دمج سجلات جديدة فوق المخزون وحفظه — False يعني دمجاً فاشلاً."""
            nonlocal candles, saved
            merged = _merge_dedupe(candles, new_recs)
            if merged is None:
                return False
            candles = merged
            await self._save(
                sm, key, namespace, symbol, timeframe, market,
                candles, schema, save_note,
            )
            saved = True
            return True

        # ================== مسار الكاش البارد (لا مخزون) ==================
        if entry is None:
            if range_mode:
                recs = await fetch_range(need_start, eff_now)
            else:
                recs = await fetch_records(days)
            fetched_new = len(recs)
            candles = recs
            note = "full fetch (cold cache)"
            await self._save(
                sm, key, namespace, symbol, timeframe, market,
                candles, self._captured_schema, note,
            )
            saved = True
            hit = False
            # ✅ R61 — حتى الجلب البارد يُحاسَب: شظية مهدَّلة من المزوّد
            # (فشل دفعات/حظر) كانت تُسلَّم بصمت في R58 — الآن يُعاد كشف
            # فجواتها ومحاولة ملئها (نطاقاً) أو إعلانها (أيامياً).
            if range_mode and interval:
                post = _analyze_window_coverage(
                    _times_of(candles), need_start, need_end, interval, tol
                )
                for s, e in _plan_gap_fetches(list(post["holes"])):
                    fill_calls += 1
                    try:
                        recs2 = await fetch_range(s, e)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "🩹 [R61] gap re-fetch failed (%s %s): %s",
                            symbol, timeframe, exc,
                        )
                        continue
                    before = len(candles)
                    if await _merge_and_save(
                        recs2, self._captured_schema, "cold fetch + gap re-fetch"
                    ):
                        added = len(candles) - before
                        if added > 0:
                            fetched_new += added
                            note = f"cold fetch + gap re-fill: +{added} candles"
                        elif not self._fetch_incomplete:
                            # المصدر أكّد فراغها — طبيعية (لا نقص حقيقاً)
                            natural_ranges.append((s, e))

        # ============ مسار الكاش: المخزون يغطي بداية النافذة =============
        elif interval and not leading_gap:
            hit = True
            if not pre_holes:
                # تغطية كاملة فعلية — حتى شرط تحديث رأس R58 محتوم هنا:
                # لا فجوة ذيلية ⇔ آخر شمعة ≥ النهاية − عرض الفريم.
                note = "full coverage from cache"
            elif range_mode:
                # ✅ R61 — فجوات داخلية/ذيلية: جلب دقيق (أو مدموج عند
                # التفشّط) + دمج — بدل تسليم الجبن السويسري بصمت.
                note = "full coverage from cache"
                for s, e in _plan_gap_fetches(pre_holes):
                    fill_calls += 1
                    try:
                        recs = await fetch_range(s, e)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "🩹 [R61] gap fill failed (%s %s [%d..%d]): %s",
                            symbol, timeframe, s, e, exc,
                        )
                        continue
                    before = len(candles)
                    if await _merge_and_save(
                        recs, entry.get("schema"), "cache + gap fill"
                    ):
                        added = len(candles) - before
                        if added > 0:
                            fetched_new += added
                            note = f"cache + gap fill: +{fetched_new} candles"
                        elif not self._fetch_incomplete:
                            # المصدر أكّد أن هذا الفراغ فارغ أصلاً — طبيعي
                            natural_ranges.append((s, e))
            else:
                # وضع الأيام: الجالب يفهم «آخر N يوم من الآن» فقط —
                # الفجوة الذيلية = تحديث الرأس التقليدي، والفجوات
                # الداخلية تُرقّى إلى جلب كامل (يجلب النافذة كلها من
                # المصدر فيشفى المخزون دفعة واحدة).
                last_t = entry["last_time"]
                note = "full coverage from cache"
                if _REFRESH_HEAD and last_t < eff_now - interval:
                    head_days = max(1, math.ceil((eff_now - last_t) / 86400.0))
                    head_recs = await fetch_records(head_days)
                    ok = await _merge_and_save(
                        head_recs, entry.get("schema"),
                        "head refresh",
                    )
                    if ok:
                        fetched_new = max(0, len(candles) - cached_count)
                        note = f"head refresh: fetched {head_days}d, +{fetched_new} candles"
                mid = _analyze_window_coverage(
                    _times_of(candles), need_start, need_end, interval, tol
                )
                if mid["holes"]:
                    # فجوات بقيت (داخلية أو شظية رأس لم تُسدّ) ⇦ جلب كامل
                    recs = await fetch_records(days)
                    fetched_new += len(recs)
                    await _merge_and_save(
                        recs, entry.get("schema"), "hole-healing full fetch"
                    )
                    hit = False
                    note = f"hole-healing full fetch: +{len(recs)} candles"
                    # بعد جلب النافذة كاملة من المصدر، ما بقي فارغاً طبيعي
                    # — إلا إذا وسم المزوّد جلبه بالنقص (تهدئة) فلا نثق به
                    if not self._fetch_incomplete:
                        final0 = _analyze_window_coverage(
                            _times_of(candles), need_start, need_end, interval, tol
                        )
                        natural_ranges.extend(final0["holes"])

        # ======= مسار الجلب الأساسي: فجوة بادئة (المخزون أحدث من الطلب) =======
        else:
            # ✅ R61 — وضع النطاق: اجلب الفجوات بدقتها (بادئة/داخلية/ذيلية)
            # وادمجها فوق المخزون — بدل إعادة جلب النافذة كاملة (سلوك R58)
            # مع الحفاظ على نفس مسار الدمج المُثبت.
            if range_mode and interval:
                for s, e in _plan_gap_fetches(pre_holes):
                    fill_calls += 1
                    try:
                        recs = await fetch_range(s, e)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "🩹 [R61] leading gap fill failed (%s %s): %s",
                            symbol, timeframe, exc,
                        )
                        continue
                    before = len(candles)
                    if await _merge_and_save(
                        recs, entry.get("schema"),
                        "gap fetch merged with cache",
                    ):
                        added = len(candles) - before
                        if added > 0:
                            fetched_new += added
                        elif not self._fetch_incomplete:
                            natural_ranges.append((s, e))
                note = (
                    f"gap fetch merged with cache: +{fetched_new} candles"
                    if fetched_new
                    else "gap fetch: nothing new from source"
                )
            else:
                # وضع الأيام أو فريم مجهول العرض ⇦ سلوك R58 حرفياً:
                # جلب كامل + دمج مع المخزون (وضع النطاق يستخدم fetch_range)
                if range_mode:
                    recs = await fetch_range(need_start, eff_now)
                else:
                    recs = await fetch_records(days)
                fetched_new = len(recs)
                merged = _merge_dedupe(candles, recs)
                if merged is not None:
                    candles = merged
                    note = "full fetch merged with cache"
                else:
                    candles = recs
                    note = "full fetch (merge incompatible)"
                await self._save(
                    sm, key, namespace, symbol, timeframe, market,
                    candles,
                    self._captured_schema or (entry or {}).get("schema"),
                    note,
                )
                saved = True
            hit = False

        # ------------------------------------------------------------------
        # ✅ R61 — التسليم + بطاقة التغطية النهائية (لا نجاح صامت بعدها)
        # ------------------------------------------------------------------
        out_records = _clip(candles, need_start - (interval or 0))
        # ✅ R57 — وضع النطاق (تواريخ صريحة): احترام النهاية حرفياً.
        # ذيل الكاش بعد end المطلوب لا يُعاد أبداً — نفس حافة المزوّد
        # الباردة (آخر شمعة مغلقة ≤ end) فلا تسريب إلى «الآن».
        if range_mode:
            out_records = _clip_end(out_records, eff_now - (interval or 0))

        final_card = (
            _analyze_window_coverage(
                _times_of(candles), need_start, need_end, interval, tol
            )
            if interval
            else None
        )
        natural_s = 0
        if natural_ranges and final_card:
            # الفجوات المؤكدة طبيعية لا تُحسب نقصاً (المصدر أعلن فراغها)
            # لكنها تُعلَن بعدّها — شفافية كاملة بلا ذعر كاذب.
            for s, e in natural_ranges:
                natural_s += max(0, min(e, need_end) - max(s, need_start))
        if final_card:
            eff_window = max(1, final_card["window_s"] - natural_s)
            holes_final = [
                (s, e)
                for s, e in final_card["holes"]
                if not any(
                    min(e, ne) - max(s, ns) > 0 for ns, ne in natural_ranges
                )
            ]
            coverage_pct = round(
                min(100.0, 100.0 * final_card["covered_s"] / eff_window), 2
            )
            gaps_remaining = len(holes_final)
        else:
            coverage_pct = None
            gaps_remaining = 0
        gap_filled = gaps_remaining == 0

        stored_times = _times_of(candles) if candles else []
        result = CacheResult(
            candles=out_records, cache_hit=hit,
            cached_count=cached_count if hit else max(0, len(candles) - fetched_new),
            fetched_new=fetched_new, total=len(out_records), note=note,
            requested_start=need_start, requested_end=need_end,
            stored_start=stored_times[0] if stored_times else None,
            stored_end=stored_times[-1] if stored_times else None,
            expected_candles=_expected_candles(need_start, need_end, interval),
            delivered_candles=len(out_records),
            coverage_pct=coverage_pct,
            gaps_detected=gaps_detected,
            gaps_remaining=gaps_remaining,
            natural_gaps=len(natural_ranges),
            gap_filled=gap_filled,
            fill_calls=fill_calls,
            fetch_incomplete=bool(self._fetch_incomplete),
        )
        if not gap_filled:
            # الممنوع صراحة: إنجاح المهمة والمحرك استلم أقل من نافذته —
            # نُعلنها في الملاحظة وفي السجل معاً (بطاقة التغطية أعلاه
            # تحمل الأرقام كاملة للواجهة).
            result.note = (
                f"⚠️ partial coverage {coverage_pct}%: {gaps_remaining} gap(s) "
                f"unfilled after {fill_calls} fetch attempt(s) — was: {note}"
            )
            logger.error(
                "🚨 [R61] %s %s: partial window delivery %.2f%% "
                "(%d/%d expected, %d gaps remain)",
                symbol, timeframe, coverage_pct or 0.0,
                len(out_records),
                _expected_candles(need_start, need_end, interval) or -1,
                gaps_remaining,
            )

        # فضاء d: أعد بناء الإطار من السجلات بالمخطط (الملقوط أو المخزون)
        if namespace == "d":
            # ✅ R45.1: أفضل مخطط صالح — الملتقط قد يكون مسخاً (جلب فارغ)
            # فلا يُسمح له بالتقدم على المخزون الجيد.
            candidates = [
                self._captured_schema,
                (entry or {}).get("schema"),
            ]
            schema = next((s for s in candidates if _schema_is_usable(s)), None)
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
            # ✅ R61 — وسم النقص من المزوّد يُنقل إلى بطاقة التغطية
            try:
                if bool(getattr(df, "attrs", {}).get("fetch_incomplete")):
                    svc._fetch_incomplete = True
            except Exception:  # noqa: BLE001
                pass
            if df_to_candles is not None:
                return _json_safe(df_to_candles(df))
            # ✅ R45.1: الإطار الفارغ (نافذة رأس لا شموع فيها) لا يُلتقط
            # مخططه — أعمدته كلها object فيفسد إعادة البناء. المخطط الجيد
            # إما المخزون أو جلبٌ لاحق غير فارغ.
            if df is None or len(df) == 0:
                return []
            schema = _capture_df_schema(df)
            recs = _records_from_df(df)
            if schema is None or recs is None:
                raise ValueError("unrecognized dataframe shape")
            svc._captured_schema = schema
            return recs

        return _fetch

    def _wrap_range_fetcher(
        self,
        fetch_range_df: Callable[[int, int], Any],
        df_to_candles: Optional[Callable[[Any], List[Dict[str, Any]]]],
    ) -> Callable[[int, int], Any]:
        """تغليف جالب النطاق: (start_ts, end_ts) ⇦ سجلات JSON-آمنة."""
        svc = self

        async def _fetch(start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
            df = await fetch_range_df(start_ts, end_ts)
            # ✅ R61 — وسم النقص من المزوّد يُنقل إلى بطاقة التغطية
            try:
                if bool(getattr(df, "attrs", {}).get("fetch_incomplete")):
                    svc._fetch_incomplete = True
            except Exception:  # noqa: BLE001
                pass
            if df_to_candles is not None:
                return _json_safe(df_to_candles(df))
            # ✅ R45.1: نفس درع الإطار الفارغ — جلب رأس بنافذة أقصر من
            # شمعة واحدة يرجع 0 صفوف بأعمدة object؛ لا يُسمح له بطمس
            # المخطط الجيد الملتقط أو المخزن.
            if df is None or len(df) == 0:
                return []
            schema = _capture_df_schema(df)
            recs = _records_from_df(df)
            if schema is None or recs is None:
                raise ValueError("unrecognized dataframe shape (range)")
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
        from sqlalchemy.orm import load_only

        from app.models.candle_cache import CandleCache
        from app.services.task_registry import ensure_registry_tables

        await ensure_registry_tables()
        sm = self._resolve_sm()
        async with sm() as db:
            # ✅ R50 — قائمة خفيفة: كان select(CandleCache) يحمّل عمود
            # candles كاملاً (JSON بحجم عشرات-مئات الميغابايتات للرموز
            # الثقيلة!) ليعرض بعدها حقولاً سطحية فقط. الآن أعمدة العرض.
            rows = (
                (
                    await db.execute(
                        select(CandleCache)
                        .options(load_only(
                            CandleCache.id, CandleCache.cache_key,
                            CandleCache.namespace, CandleCache.symbol,
                            CandleCache.timeframe, CandleCache.market,
                            CandleCache.count, CandleCache.first_time,
                            CandleCache.last_time, CandleCache.last_fetch_note,
                            CandleCache.created_at, CandleCache.updated_at,
                        ))
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

    # ------------------------------------------------------------------
    # R45.1 — مسار المحرك القياسي: get_historical_last_version وأختها
    # (الاسم القديم بحرف الخطأ get_historicallastvirsion هو ما يستدعيه
    # engine1.run_backtest فعلياً). مخطط BacktestConfig يطبّع التواريخ إلى
    # UTC واعية قبل الوصول هنا — فالتحويل إلى ثوانٍ epoch آمن تماماً.
    # ------------------------------------------------------------------
    async def _serve_range(self, method_name: str, *args, **kwargs):
        inner_fn = getattr(self._inner, method_name, None)
        if inner_fn is None:
            self.stats["misses"] += 1
            self.stats["last"] = f"delegate (no {method_name} on inner)"
            raise AttributeError(method_name)
        try:
            sig = inspect.signature(inner_fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            symbol = bound.arguments.get("symbol")
            timeframe = bound.arguments.get("timeframe")
            market = bound.arguments.get("market") or "crypto"
            start_date = bound.arguments.get("start_date")
            end_date = bound.arguments.get("end_date")
            if not symbol or not timeframe or start_date is None or end_date is None:
                raise KeyError("missing symbol/timeframe/start_date/end_date")
        except (KeyError, TypeError):
            # توقيع لا نستطيع ربطه بأمان ⇦ تمرير حرفي بلا كاش
            self.stats["misses"] += 1
            self.stats["last"] = f"delegate (unbindable {method_name})"
            return await inner_fn(*args, **kwargs)

        def _to_epoch(d) -> int:
            if d.tzinfo is None:
                return int(d.replace(tzinfo=timezone.utc).timestamp())
            return int(d.timestamp())

        start_ts = _to_epoch(start_date)
        end_ts = _to_epoch(end_date)

        def _rebuild_kwargs(new_start, new_end):
            call_kw = dict(bound.arguments)
            call_kw["start_date"] = new_start
            call_kw["end_date"] = new_end
            return call_kw

        async def _fetch_range(range_start_ts: int, range_end_ts: int):
            new_start = datetime.fromtimestamp(int(range_start_ts), tz=timezone.utc)
            new_end = datetime.fromtimestamp(int(range_end_ts), tz=timezone.utc)
            call_kw = _rebuild_kwargs(new_start, new_end)
            try:
                return await inner_fn(**call_kw)
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
                return await inner_fn(*pos, **kw)

        df = await self._cache.get_dataframe_range(
            symbol=str(symbol),
            timeframe=str(timeframe),
            market=str(market or "crypto"),
            start_ts=start_ts,
            end_ts=end_ts,
            fetch_range_df=_fetch_range,
        )
        hit = bool((self._cache.last_meta or {}).get("cache", {}).get("hit"))
        self.stats["hits" if hit else "misses"] += 1
        self.stats["last"] = (self._cache.last_meta or {}).get("cache", {}).get("note")
        return df

    async def get_historical_last_version(self, *args, **kwargs):
        """اعتراض المسار القياسي الحديث (الاسم الصحيح المكتوب)."""
        return await self._serve_range(
            "get_historical_last_version", *args, **kwargs
        )

    async def get_historicallastvirsion(self, *args, **kwargs):
        """اعتراض المسار الذي يستدعيه engine1 فعلياً (الاسم القديم بحرف الخطأ)."""
        return await self._serve_range(
            "get_historicallastvirsion", *args, **kwargs
        )
