# app/routers/backtest.py
"""
Backtest router — Celery-backed.

- POST /run            : يرسل مهمة الباك-تست إلى Celery (config JSON-آمن) ويعيد task_id
- GET  /status/{id}    : حالة المهمة من Celery Result Backend
- GET  /list           : قائمة الباك-تستات المخزنة (BacktestRun)
- GET  /get/{id}       : تفاصيل باك-تست كاملة من قاعدة البيانات
- GET  /{id}/chart-data: بيانات الرسم البياني من عمود chart_data في BacktestRun
- DELETE /delete/{id}  : حذف باك-تست
- POST /walk-forward   : تحليل مشي للأمام (محرك لكل طلب — بلا cache عالمي)
- POST /monte-carlo    : محاكاة مونت كارلو (محرك لكل طلب)
- GET  /metrics        : قائمة المقاييس المتاحة
"""
import asyncio
import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.backtest.engine1 import BacktestEngine, MAX_MONTE_CARLO_SIMULATIONS, MAX_WALK_FORWARD_WINDOWS
from app.backtest.schemas import BacktestConfig
from app.celery_app import celery_app
from app.database import get_db, async_session_maker
from app.models.backtest_run import BacktestRun
from app.services.data_service import DataService
from app.services.indicators.overlays import OVERLAY_TYPES as _OVL_TYPES, compute_overlays as _compute_overlays  # ✅ الجولة 10
from app.tasks.backtest_tasks import run_backtest_task

router = APIRouter(tags=["backtest"])
logger = logging.getLogger(__name__)


# ===========================================================================
# ✅ ROUND30 — جعل الفيبو يصل افتراضياً في بيانات رسم الباك تست
# ---------------------------------------------------------------------------
# الجذور المثبتة لعدم رسم الفيبو في شارت الباك تست (كلها من طرف الباكند):
# 1) طبقات الفيبو (zzfib/fib/zzfib_e2e) لا تُحسب إلا إذا مرر العميل overlays=...
#    — وغيابها يعني استجابة بلا قسم overlays إطلاقاً.
# 2) تقرير الجولة 22 وجّه الواجهة لمسار خاطئ (/visual — غير موجود، 404 مثبت)
#    والمسار الصحيح /{id}/chart-data — فبقي الطلب بلا طبقات.
# 3) محول الزمن _ts في overlays.py كان يفشل على سلسلة ISO
#    ("2026-10-21T16:30:00Z") فيعود 0 — فتصبح كل أزمنة الطبقة (t1/t2/t_from/t_to)
#    صفرية حتى لو حُسبت الطبقات — لا يمكن رسمها على محور الزمن.
# هنا نحل (1): الافتراضي يحسب الطبقات البنيوية الثلاث ما لم يمرر العميل قيمة
# صريحة أو يعطلها بـ overlays=none، وبسقف شموع آمن يمنع تضخم الاستجابة.
# (2) صُحح في FRONTEND-BRIEF-FIB-BACKTEST-AR.md و(3) في overlays.py نفسه.
# ===========================================================================
_OVERLAYS_DEFAULT = "zzfib,fib,zzfib_e2e"
_OVERLAYS_DEFAULT_MAX_BARS = 50000
_OVERLAYS_OFF_TOKENS = ("none", "off", "false", "0")


# ===========================================================================
# 🔥 R69.1 — طبقة الزقزاق/الفيبو لاستراتيجية التشغيل نفسها (طلب المالك)
# ---------------------------------------------------------------------------
# ملاحظة المالك على التشغيل المدمج (R69): «طبقة الزقزاق/الفيبو معطلة — لا
# توجد إحداثيات من الباك اند» عند استراتيجية الملتهبة. السبب المثبت:
# الافتراضي أعلاه (zzfib,fib,zzfib_e2e) لا يشمل عائلة الاستراتيجية المشغّلة
# نفسها، فلا تصل إحداثيات الرسم الخاصة بها (legs/pivots/ranges[].levels/
# trend.lines/current.live_extension) في قسم overlays → يطفئ الفرونت
# طبقتها بلا إحداثيات، بينما تحمل نفس عقد e2e حرفياً.
# الإصلاح: عند غياب overlays الصريحة نضيف تلقائياً طبقة عائلة الاستراتيجية
# التي أنتجت التشغيل (نكشفها من أعمدة ind_* في شموعه) — فتحمل الملتهبة
# كل خصائص الترندية بالرسم + إضافاتها بلا أي طلب صريح من الفرونت.
# ===========================================================================
def _strategy_family_overlays(indicator_names: Any) -> List[str]:
    """أعمدة ind_* لاستراتيجية التشغيل → طبقات عائلتها (رسم مطابق لإشاراتها).

    ind_zzfb_*  → zzfib_e2e_blazing (🔥 الملتهبة — S1/S2/S3 + N5/N6)
    ind_zzfet_* → zzfib_e2e_trendy   (✅ الترندية)
    ind_zzfe_*  → zzfib_e2e          (✅ E2E الأصل)
    (العائلات مستقلة — استراتيجية تحمل مؤشرين تصلها طبقتاهما معاً.)
    """
    names = {str(n) for n in (indicator_names or [])}
    fams: List[str] = []
    if any(n.startswith("ind_zzfb_") for n in names):
        fams.append("zzfib_e2e_blazing")
    if any(n.startswith("ind_zzfet_") for n in names):
        fams.append("zzfib_e2e_trendy")
    if any(n.startswith("ind_zzfe_") and not n.startswith("ind_zzfeb_") for n in names):
        fams.append("zzfib_e2e")
    return fams


def _resolve_overlays_request(overlays: Any, raw_len: int) -> Optional[str]:
    """يعيد سلسلة الأنواع الفعالة لطبقات overlays أو None لتعطيلها.

    - str صالحة → تُحترم حرفياً (نفس عقد الجولة 10)؛ "none/off/false/0" → None.
    - غياب (None أو FieldInfo من الاستدعاء المباشر — جولة 12.1) → الافتراضي
      _OVERLAYS_DEFAULT إذا raw_len ≤ _OVERLAYS_DEFAULT_MAX_BARS وإلا None
      (حماية من تضخم الاستجابة على حمولات السنوات؛ تُمرر صراحة وقتها).
    """
    if isinstance(overlays, str):
        s = overlays.strip()
        if s:
            return None if s.lower() in _OVERLAYS_OFF_TOKENS else s
    if raw_len and raw_len <= _OVERLAYS_DEFAULT_MAX_BARS:
        return _OVERLAYS_DEFAULT
    return None

# ---------------------------------------------------------------------------
# In-process fallback registry (when Celery/Redis broker is unavailable).
#
# POST /run normally enqueues a Celery task and the client polls /status.
# Without a broker the old code hard-failed 503 and the dashboard backtest
# button was dead. Now: the same engine runs **inside the API process** as a
# background asyncio task, and /status serves its state from this registry
# with the exact same response contract ({task_id, state, backtest_id, ...}).
# ---------------------------------------------------------------------------
_inprocess_tasks: Dict[str, Dict[str, Any]] = {}

# ✅ الجولة 14.1: مراجع قوية للمهام الداخلية — asyncio.create_task بلا مرجع
# قوي قد يُجمعها GC في منتصف التشغيل (حاشية asyncio الرسمية).
_inprocess_task_refs: set = set()

# ✅ الجولة 14.1: سقف زمني لمسار التشغيل الداخلي (كان بلا مهلة إطلاقاً —
# حمولة مرضية مثل 1m لأعوام كانت تعمل بلا سقف على حلقة الـAPI).
# مطابق لسقف Celery task_time_limit=3700. قابل للتجاوز بمتغير البيئة.
import os as _os
_INPROCESS_TIMEOUT_SECONDS: int = int(_os.getenv("BACKTEST_INPROCESS_TIMEOUT", "3700"))

# ===========================================================================
# ✅ الجولة 9: كاش باكند لنتائج الباك-تست (بيانات تاريخية ثابتة لا تتغير أبداً)
# ---------------------------------------------------------------------------
# قياس الإنتاج: chart-data?include_indicators=true كان يأخذ 109-231 ثانية
# في كل طلب لنفس البيانات الثابتة. السبب: إعادة تحميل عمود JSON الضخم
# وإعادة حساب كل شيء في كل طلب بلا أي تخزين بيني.
#
# التصميم:
# - بناء **أساس معالج واحد** لكل backtest_id عند أول طلب (شموع مسطحة بكل
#   مفاتيح ind_* + نقاط تداول + منحنيات + metadata) ثم كل طلب لاحق
#   مجرد تقطيع/نسخ خفيف من الأساس — أداء ثابت مهما تعددت المعاملات.
# - LRU محدود (12 باك-تست) لضبط الذاكرة؛ الأحدث استخداماً يبقى.
# - الإبطال عند الحذف + عند إعادة تشغيل نفس المعرف (run جديد على نفس id).
# ===========================================================================
from collections import OrderedDict as _OrderedDict

# ✅ R49 — سعتان للكاش: عدد مداخل + **ميزانية بايتات**.
# الدافع المُثبت: مستند ثقيل واحد (129K شمعة) يخزَّن كـ base كائنات
# (~350MB) + getbytes/get1bytes (77MB ×2) + resp bytes (208MB) ≈ 700MB+ —
# وLRU=3 مداخل تجاوز 2GB فقتلت العملية (OOM داخل بيئة 4GB). الميزانية
# تطرد الأقدم حتى النزول تحت الحد، وتُرفع عبر BACKTEST_CACHE_BUDGET_MB
# للخوادم الأكبر.
_BT_CACHE_MAX = int(_os.getenv("BACKTEST_CACHE_MAX", "12"))
_BT_CACHE_BUDGET_MB = float(_os.getenv("BACKTEST_CACHE_BUDGET_MB", "900"))
# ✅ R50.1 (تدقيق الرئيس): سقف مستقل للهياكل المفكوكة (الكائنات لا البايتات).
# القياس الفعلي: أساس مستند ثقيل ≈ 337MB و overlays كاملة ≈ 300MB ككائنات —
# تخزينها في الكاش كان يضخّم RSS فوق 2.1GB فيقتل OOM العملية (نفس بصمة
# موت الحاوية في الإنتاج). البايتات المضغوطة (gz ~2.6MB) تبقى دائمًا.
_BT_PARSED_CACHE_MAX_MB = float(_os.getenv("BACKTEST_PARSED_CACHE_MAX_MB", "300"))
_BT_BYTES_PER_CANDLE = 0.0026  # MB تقديريًا لكل شمعة ككائن dict (قياس R49)
_bt_cache: "_OrderedDict[str, Dict[str, Any]]" = _OrderedDict()


def _bt_entry_size_mb(value: Any) -> float:
    """حجم مدخل الكاش بالميغابايت (bytes مباشرة، الكائنات تقديرًا بعدد الشموع)."""
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], (bytes, bytearray)):
        # ✅ R50: مدخلات البايتات المضغوطة ("gz"|"raw", bytes)
        return len(value[1]) / 1e6
    if isinstance(value, (bytes, bytearray)):
        return len(value) / 1e6
    if isinstance(value, dict):
        if isinstance(value.get("flat_candles"), list):
            return value.get("raw_len", 0) * _BT_BYTES_PER_CANDLE + 1.0
        # ✅ R50.1: حمولة overlays (bars + overlays) كانت تُقدَّر بـ 0.05MB
        # وهي تحمل فعليًا عشرات إلى مئات الميغابايت (bar لكل شمعة + 5
        # مؤشرات مسطحة) — تقدير كاذب يفتح باب OOM تحت الضغط المتواصل.
        # القياس الفعلي (تدقيق R50.1): ≈ 2.6KB لكل شمعة للحمولة الكاملة.
        _bars = value.get("bars")
        if isinstance(_bars, list):
            _est = len(_bars) * _BT_BYTES_PER_CANDLE
            _ovl = value.get("overlays")
            if isinstance(_ovl, dict):
                _est += sum(
                    len(_v) * _BT_BYTES_PER_CANDLE
                    for _v in _ovl.values() if isinstance(_v, list)
                )
            return _est + 0.5
        vc = value.get("visual_candles")
        if isinstance(vc, list):
            return len(vc) * _BT_BYTES_PER_CANDLE + 0.5
    return 0.05


def _bt_cache_get(key: str) -> Optional[Dict[str, Any]]:
    if key in _bt_cache:
        _bt_cache.move_to_end(key)
        return _bt_cache[key]
    return None


def _bt_cache_put(key: str, value: Dict[str, Any]) -> None:
    # ✅ R50.1: سقف الهياكل المفكوكة — الكائن المفكوك الضخم (أساس ~337MB،
    # overlays كاملة ~300MB) لا يدخل الكاش أصلًا: البايتات المضغوطة الرخيصة
    # تبقى دائمًا، والمفكوك الضخم يُعاد بناؤه عند الطلب (ثوانٍ داخل خيط عامل
    # والحلقة حية). هذا هو الإصلاح الذي أغلق ثغرة OOM نهائيًا.
    if isinstance(value, dict):
        _est_mb = _bt_entry_size_mb(value)
        if _est_mb > _BT_PARSED_CACHE_MAX_MB:
            logger.info(
                "🚫 [R50.1] تخطي تخزين كائن مفكوك ضخم [%s] (~%.0fMB > سقف %.0fMB) — تُخزَّن البايتات المضغوطة فقط",
                key[:12], _est_mb, _BT_PARSED_CACHE_MAX_MB,
            )
            return
    _bt_cache[key] = value
    _bt_cache.move_to_end(key)
    # ✅ R49: الإخلاء بالميزانية — لا نطرد المدخل المُدرج للتو مهما كان
    # ضخمًا (مستند وحيد عملاق أفضل من كاش فارغ)، لكن كل ما عداه يُطرد
    # الأقدم أولاً حتى ننزل تحت السعتين.
    while len(_bt_cache) > 1 and (
        len(_bt_cache) > _BT_CACHE_MAX
        or sum(_bt_entry_size_mb(v) for v in _bt_cache.values()) > _BT_CACHE_BUDGET_MB
    ):
        _bt_cache.popitem(last=False)
    logger.info(
        "💾 Backtest cache stored [%s] (entries=%d, ~%.0fMB budget=%.0fMB)",
        key[:12], len(_bt_cache),
        sum(_bt_entry_size_mb(v) for v in _bt_cache.values()), _BT_CACHE_BUDGET_MB,
    )


def _bt_cache_drop(backtest_id: str) -> None:
    dropped = [k for k in list(_bt_cache.keys()) if k == backtest_id or k.startswith(f"{backtest_id}|")]
    for k in dropped:
        _bt_cache.pop(k, None)
    if dropped:
        logger.info("🧹 Backtest cache invalidated for %s (%d entries)", backtest_id, len(dropped))


def _inprocess_status_payload(task_id: str) -> Dict[str, Any]:
    state_entry = _inprocess_tasks.get(task_id)
    if not state_entry:
        return {"task_id": task_id, "state": "PENDING", "message": "Task is waiting to be processed."}
    state = state_entry["state"]
    response: Dict[str, Any] = {"task_id": task_id, "state": state}
    if state == "PENDING":
        response["message"] = "Task is waiting to be processed."
    elif state == "PROGRESS":
        response["message"] = state_entry.get("status", "Processing...")
    elif state == "SUCCESS":
        response["message"] = "Backtest completed successfully."
        response["backtest_id"] = state_entry.get("backtest_id")
        response["result"] = {"status": "SUCCESS", "backtest_id": state_entry.get("backtest_id")}
    else:  # FAILURE
        response["message"] = "Task failed."
        response["error"] = "Backtest execution failed. See server logs for details."
        if state_entry.get("error"):
            response["error_detail"] = state_entry["error"]
    return response


async def _run_backtest_inprocess(task_id: str, config_dict: dict) -> None:
    """Execute the same celery task body inside the API process.

    ✅ الجولة 14.1 — إصلاح تجميد الخادم:
    - المحرك متزامن ثقيل (CPU-bound pandas) — تنفيذه مباشرة على حلقة الأحداث
      كان يجمّد كل الـAPI والـWebSocket طيلة المحاكاة. الآن يعمل داخل خيط
      عامل بحلقة أحداث خاصة (asyncio.run في to_thread) فتبقى الحلقة الرئيسية
      حرة تخدم الطلبات.
    - جلسة قاعدة بيانات معزولة (NullPool) لأن اتصالات المسبح المشترك مرتبطة
      بحلقة الـAPI ولا يصح استخدامها من حلقة الخيط.
    - مهلة قصوى (_INPROCESS_TIMEOUT_SECONDS) — المهلة ترفع FAILURE للـ/status
      (خيط المحرك لا يمكن إجهاضه قسرياً لكن نتيجته تُهمل ويعمل في الخلفية حتى ينتهي).
    - ✅ HOTFIX 2026-11-03 (تعليق «معالجة» الأبدي): الاستيرادات نُقلت داخل كتلة
      try — كانت قبلها، فأي ImportError (مثل غياب build_isolated_session_maker
      من session.py في حاوية غير مُحدَّثة بالكامل) يتحطم به بصمت قبل تسجيل
      FAILURE وتبقى المهمة PROGRESS للأبد. الآن: أي فشل استيراد/تشغيل يرفع
      FAILURE مع error_detail يظهر في /status فوراً.
    """
    if task_id not in _inprocess_tasks:  # مسجَّلة مسبقاً في /run — حماية للاستدعاء المباشر
        _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": "Starting Backtest Engine..."}
    try:
        from app.tasks.backtest_tasks import _execute_backtest
        from app.database.session import build_isolated_session_maker

        def _run_isolated() -> str:
            async def _inner() -> str:
                session_maker, iso_engine = build_isolated_session_maker()
                try:
                    return await _execute_backtest(config_dict, None, session_maker=session_maker)
                finally:
                    try:
                        await iso_engine.dispose()
                    except Exception:  # noqa: BLE001
                        pass
            return asyncio.run(_inner())

        backtest_id = await asyncio.wait_for(
            asyncio.to_thread(_run_isolated),
            timeout=_INPROCESS_TIMEOUT_SECONDS,
        )
        _inprocess_tasks[task_id] = {
            "state": "SUCCESS",
            "backtest_id": backtest_id,
        }
        logger.info(f"✅ [in-process] Backtest {backtest_id} completed (task {task_id})")
    except asyncio.TimeoutError:
        _inprocess_tasks[task_id] = {
            "state": "FAILURE",
            "error": f"Backtest exceeded in-process timeout of {_INPROCESS_TIMEOUT_SECONDS}s",
        }
        logger.error(f"⏰ [in-process] Backtest task {task_id} timed out after {_INPROCESS_TIMEOUT_SECONDS}s")
    except Exception as exc:  # noqa: BLE001
        _inprocess_tasks[task_id] = {
            "state": "FAILURE",
            "error": str(exc)[:400] or exc.__class__.__name__,
        }
        logger.exception(f"❌ [in-process] Backtest task {task_id} failed: {exc}")



# ==========================================
# Helpers
# ==========================================

def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
    """
    يحول قاموساً متداخلاً مثل: {"bb": {"upper": 3000, "lower": 2900}}
    إلى قاموس مسطح مثل: {"bb_upper": 3000, "bb_lower": 2900}
    """
    items: Dict[str, Any] = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def _compute_drawdown_curve(equity_curve: List[float]) -> List[float]:
    """منحنى الانخفاض (نفس منطق PerformanceMetrics._calculate_drawdown_curve)"""
    if not equity_curve:
        return []
    peak = equity_curve[0]
    drawdowns: List[float] = []
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdowns.append((peak - equity) / peak * 100 if peak > 0 else 0.0)
    return drawdowns


async def _get_backtest_row(db: AsyncSession, backtest_id: str) -> BacktestRun:
    """جلب سجل BacktestRun أو رفع 404
    ✅ R44 — القراءة عبر درع القفل: هذه هي النقطة المركزية التي تتغذى عليها
    /get و /chart-data و /delete — حمايتها تحمي الثلاثة دفعة واحدة."""
    from app.database.session import execute_with_lock_retry

    result = await execute_with_lock_retry(
        db,
        select(BacktestRun).where(BacktestRun.id == backtest_id),
        what=f"backtest/get {backtest_id}",
    )
    backtest = result.scalar_one_or_none()
    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return backtest


# ===========================================================================
# ✅ R50 — جلب المستندات الثقيلة بلا تجميد حلقة الأحداث
# ---------------------------------------------------------------------------
# المشكلة المُثبتة بالقياس (baseline على PG 17.4): select(BacktestRun)
# الكامل يُنزّل أعمدة JSON الضخمة (chart_data 52-208MB للمستند الثقيل)
# ثم تُفَك داخل حلقة الأحداث (json.loads أثناء معالجة النتائج في greenlet
# الحلقة نفسها) — ثوانٍ تجميد كامل لكل /get أو /list، و/health خلفها
# يفشل → healthcheck يقتل الحاوية (بصمة إعادة التشغيل عند المستخدم).
#
# الحل:
#   1) الأعمدة الثقيلة تُجلب كنص خام CAST(... AS TEXT) — الشبكة والـ memcpy
#      فقط داخل الحلقة (C-speed)، صفر JSON parsing.
#   2) json.loads للنص الضخم داخل asyncio.to_thread — الحلقة تخدم الجميع.
#   3) بعد الجلب مباشرة نُغلق معاملة القراءة (commit) فتعود وصلة المسبح
#      للحمّام قبل أي عمل ثقيل — لا استنزاف pool تحت الضغط.
# ===========================================================================

import types as _types


def _doc_shim(row, summary: Any, chart_data: Any, full_config: Any):
    """كائن خفيف بنفس واجهة BacktestRun التي يستهلكها البناء/العرض
    (id/name/created_at/summary/chart_data/full_config/...) — بلا ORM."""
    return _types.SimpleNamespace(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        summary=summary,
        chart_data=chart_data,
        full_config=full_config,
        total_pnl_percent=row.total_pnl_percent,
        win_rate=row.win_rate,
        total_trades=row.total_trades,
        timeframe=row.timeframe,
        symbol=row.symbol,
    )


def _parse_heavy_doc(row):
    """(CPU ثقيل — خيط عامل فقط) فك JSON الأعمدة الضخمة إلى قواميس.

    ✅ R50: orjson عند توفره — فك 52MB يستغرق ~150-250ms بدل ~700ms
    فيتقلص احتجاز GIL (نافذة التأثير على بقية النقاط) بنفس النسبة.
    """
    from app.utils.json_safe import _fast_loads

    def _p(txt):
        try:
            return _fast_loads(txt) if txt else None
        except Exception:  # noqa: BLE001
            return None

    return _doc_shim(row, _p(row.summary_t), _p(row.chart_t), _p(row.config_t))


async def _fetch_backtest_doc(db: AsyncSession, backtest_id: str):
    """جلب مستند باك-تست كامل بلا تجميد الحلقة — عمود واحد خفيف + نص خام.

    يعيد shim بنفس واجهة BacktestRun (بما فيها chart_data المفكوك) أو 404.
    ✅ R50: أثبتنا في القياس أن المسار القديم كان يجمد الحلقة 3-10 ثوانٍ
    للمستند الواحد — هذا المساس يستبدله بجلب نصي سريع + فك في خيط عامل.
    """
    from sqlalchemy import Text, cast

    stmt = select(
        BacktestRun.id, BacktestRun.name, BacktestRun.created_at,
        BacktestRun.total_pnl_percent, BacktestRun.win_rate,
        BacktestRun.total_trades, BacktestRun.timeframe, BacktestRun.symbol,
        cast(BacktestRun.summary, Text).label("summary_t"),
        cast(BacktestRun.chart_data, Text).label("chart_t"),
        cast(BacktestRun.full_config, Text).label("config_t"),
    ).where(BacktestRun.id == backtest_id)
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Backtest not found")
    # ✅ R50: إعادة الوصلة للمسبح فورًا — البناء/التسلسل الثقيل لا يحبسها
    try:
        await db.commit()
    except Exception:  # noqa: BLE001
        pass
    return await asyncio.to_thread(_parse_heavy_doc, row)


# ===========================================================================
# ✅ R49 — إصلاح التجميد: كل البناء الثقيل خارج حلقة الأحداث
# ---------------------------------------------------------------------------
# التشخيص المُثبت (إعادة إنتاج على PG 17.4 حقيقي):
#   * GET /backtest1/get و /backtest/get كانا يعيدان بناء 129,600 شمعة
#     (تسطيح مؤشرات + نسخ dict لكل شمعة) **داخل حلقة الأحداث** — 10.6 ثانية
#     لكل طلب والطلبات الأخرى (بما فيها /health) تتجمد خلفها.
#   * GET /{id}/chart-data مع overlays=... (5 أنواع على كامل السلسلة) كان
#     يحجز الحلقة 46 ثانية — والتعليق التاريخي في الكود يقيس 109-231 ثانية
#     في الإنتاج — طوالها تجميد كامل للـ API ثم فشل healthcheck وإعادة
#     تشغيل الحاوية (بصمة لوج المستخدم: Started server process [1] بلا أي
#     traceback = SIGKILL بعد فشل الصحة/الذاكرة).
#   * الذاكرة: الكاش كان يخزّن نسخًا متعددة مستقلة (raw + get + chart +
#     ovl_candles) للمستند نفسه — 1.22GB RSS بعد 4 طلبات على مستند 87MB.
#
# الإصلاح (ثلاثة محاور):
#   1) أساس واحد مُشارَك لكل backtest_id (flat_candles واحدة فقط في الذاكرة)
#     تُبنى داخل asyncio.to_thread — الحلقة تظل تخدم /health و/status والجميع.
#   2) كل التقطيع/الفلترة/overlays داخل to_thread أيضًا.
#   3) LRU أصغر (3 افتراضيًا، متغير البيئة BACKTEST_CACHE_MAX).
# ===========================================================================


def _flatten_candle(candle: Dict[str, Any]) -> Dict[str, Any]:
    """شمعة واحدة بمؤشراتها المتداخلة مسطّحة بمفاتيح ind_* (نفس منطق الجولات 9/12 حرفيًا)."""
    formatted = dict(candle)
    indicators_data = formatted.pop("indicators", {}) or {}
    flat = flatten_dict(indicators_data) if isinstance(indicators_data, dict) else {}
    for ind_name, ind_value in flat.items():
        # ✅ الجولة 12: لا بادئة مزدوجة — أعمدة البنية ind_zz_*/ind_zzf_* تأتي
        # مسبوقة أصلاً من المحرك فتُمرّر كما هي
        _k = str(ind_name)
        formatted[_k if _k.startswith("ind_") else f"ind_{_k}"] = ind_value
    return formatted


def _build_chart_base(backtest) -> Dict[str, Any]:
    """(CPU ثقيل — يُستدعى عبر to_thread فقط)

    الأساس المُعالَج الواحد لكل backtest_id — يُبنى مرة واحدة ويُخزَّن في
    الكاش، وكل من /get و /chart-data و /backtest1/get يقتطعان منه.
    لا يُخزَّن سوى نسخة واحدة من الشموع المسطّحة (كانت 3-4 نسخ قبل R49).
    """
    chart = backtest.chart_data if isinstance(backtest.chart_data, dict) else {}
    summary = backtest.summary if isinstance(backtest.summary, dict) else {}
    full_config = backtest.full_config if isinstance(backtest.full_config, dict) else {}

    raw_candles = chart.get("visual_candles") or []
    raw_trade_points = chart.get("trade_points") or []

    if not raw_candles and not raw_trade_points:
        raise HTTPException(status_code=404, detail="No chart data available for this backtest")

    # فهرس زمني سريع لربط نقاط التداول بمواقعها
    timestamp_index = {
        c.get("timestamp"): idx for idx, c in enumerate(raw_candles) if isinstance(c, dict)
    }

    # شموع مسطحة بكل مفاتيح ind_* (النسخة الوحيدة المحفوظة)
    flat_candles: List[Dict[str, Any]] = [
        _flatten_candle(c) for c in raw_candles if isinstance(c, dict)
    ]

    # نقاط التداول: نسخة خام (عقد get) + نسخة مفهرسة (عقد chart-data)
    trade_points_raw: List[Dict[str, Any]] = [
        tp for tp in raw_trade_points if isinstance(tp, dict)
    ]
    trade_points: List[Dict[str, Any]] = []
    for tp in trade_points_raw:
        marker = dict(tp)
        marker["index"] = timestamp_index.get(tp.get("timestamp"))
        trade_points.append(marker)

    # منحنى رأس المال (من chart_data أو مشتق من الشموع)
    initial_capital = summary.get("initial_capital", full_config.get("initial_capital"))
    equity_curve = chart.get("equity_curve")
    if not equity_curve:
        derived = [c.get("account_balance") for c in raw_candles if isinstance(c, dict)]
        derived = [float(v) for v in derived if isinstance(v, (int, float))]
        if derived:
            equity_curve = (
                ([float(initial_capital)] if isinstance(initial_capital, (int, float)) else [])
                + derived
            )
        else:
            equity_curve = None

    # منحنى الانخفاض (من chart_data أو مشتق)
    drawdown_curve = chart.get("drawdown_curve")
    if not drawdown_curve and equity_curve:
        drawdown_curve = _compute_drawdown_curve(equity_curve)

    # Metadata
    timestamps = [c.get("timestamp") for c in raw_candles if isinstance(c, dict) and c.get("timestamp")]
    metadata = {
        "backtest_id": backtest.id,
        "name": backtest.name or summary.get("name", "Backtest"),
        "symbol": backtest.symbol or (full_config.get("symbols") or [None])[0],
        "timeframe": backtest.timeframe or summary.get("timeframe"),
        "initial_capital": initial_capital,
        "final_capital": summary.get("final_capital"),
        "total_pnl": summary.get("total_pnl"),
        "total_pnl_percent": backtest.total_pnl_percent if backtest.total_pnl_percent is not None else summary.get("total_pnl_percent"),
        "total_trades": backtest.total_trades if backtest.total_trades is not None else summary.get("total_trades"),
        "win_rate": backtest.win_rate if backtest.win_rate is not None else summary.get("win_rate"),
        "max_drawdown_percent": summary.get("max_drawdown_percent"),
        "sharpe_ratio": summary.get("sharpe_ratio"),
        "start_date": timestamps[0] if timestamps else None,
        "end_date": timestamps[-1] if timestamps else None,
        "created_at": backtest.created_at.isoformat() if backtest.created_at else None,
    }

    # ✅ الجولة 12 (بند 5-ب.3): توثيق الرموز — display_symbol هو الافتراضي
    metadata["display_symbol"] = metadata["symbol"]
    metadata["symbols"] = full_config.get("symbols") or ([metadata["symbol"]] if metadata["symbol"] else [])

    # أسماء المؤشرات المتاحة (من أول شمعة كاملة)
    available_indicators: List[str] = []
    for candle in raw_candles:
        if isinstance(candle, dict) and isinstance(candle.get("indicators"), dict):
            available_indicators = sorted(flatten_dict(candle["indicators"]).keys())
            break

    base: Dict[str, Any] = {
        "raw_len": len(raw_candles),
        "flat_candles": flat_candles,
        "trade_points": trade_points,
        "trade_points_raw": trade_points_raw,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
        "metadata": metadata,
        "available_indicators": available_indicators,
        # بقية حقول chart_data الخام (equity/drawdown إن وُجدت أصلاً + أي حقول مستقبلية)
        "get_extras": {
            k: v for k, v in chart.items()
            if k not in ("visual_candles", "trade_points")
        },
    }

    # ✅ الجولة 12 (بند 5-ب.3): chart_data_by_symbol للشموع المسطّحة
    try:
        _by_sym: Dict[str, List[Dict[str, Any]]] = {}
        for _c in flat_candles:
            if isinstance(_c, dict) and _c.get("symbol"):
                _by_sym.setdefault(str(_c["symbol"]), []).append(_c)
        if _by_sym:
            _tps_sym: Dict[str, List[Dict[str, Any]]] = {}
            for _p in trade_points:
                if isinstance(_p, dict) and _p.get("symbol"):
                    _tps_sym.setdefault(str(_p["symbol"]), []).append(_p)
            base["chart_data_by_symbol"] = {
                _s: {"visual_candles": _cl, "trade_points": _tps_sym.get(_s, []),
                     "candles_count": len(_cl)}
                for _s, _cl in _by_sym.items()
            }
            metadata["symbols_in_candles"] = sorted(_by_sym.keys())
    except Exception:  # noqa: BLE001
        logger.exception("chart-data: chart_data_by_symbol build failed")
    return base


async def _heavy_json_response(payload: Any, status_code: int = 200):
    """✅ R49 — تسلسل الردود الضخمة داخل خيط عامل.

    SafeJSONResponse.render (sanitize + json.dumps) لاستجابة 87MB+
    (129K شمعة) كان يعمل داخل حلقة الأحداث فيحجزها 5-10 ثوانٍ لكل طلب
    **رغم كاش البناء** — أُثبت حياً في R49: الطلب الثاني لـ /backtest1/get
    ظل 8.9 ثانية. الآن كامل التسلسل في to_thread والحلقة تخدم الجميع،
    ونفس منطق SafeJSONResponse حرفياً (نفس headers/الترميز).
    """
    from starlette.responses import Response
    from app.utils.json_safe import SafeJSONResponse

    renderer = SafeJSONResponse(content=None)
    body = await asyncio.to_thread(renderer.render, payload)
    return Response(content=body, status_code=status_code,
                    media_type="application/json")


# ===========================================================================
# ✅ R50 — ردود ضخمة مضغوطة بلا لمس حلقة الأحداث إطلاقاً
# ---------------------------------------------------------------------------
# GZipMiddleware يضغط داخل حلقة الأحداث (52MB = ~1.5s تجميد!) — هنا:
#   * التسلسل + الضغط كلاهما داخل خيط عامل.
#   * الكاش يخزّن البايتات **المضغوطة** (7MB بدل 52MB — سعة أكبر 7×
#     بنفس ميزانية الذاكرة).
#   * المستعرض يفك الضغط تلقائياً (يطلب gzip افتراضياً) — والعميل
#     النادر بلا دعم gzip يفك له الخادم في خيط عامل.
#   * الوسيط يرى Content-Encoding جاهزاً فيمرّر البايتات كما هي
#     (سلوك starlette 0.50 — لا ضغط مزدوج).
# ===========================================================================

def _gzip_level() -> int:
    import os as _os

    return int(_os.getenv("HEAVY_GZIP_LEVEL", "6") or 6)


async def _serve_heavy_doc(
    request,
    payload: Any,
    cache_key: Optional[str] = None,
    status_code: int = 200,
):
    """تسلسل + ضغط مستند ضخم داخل خيط عامل مع كاش بايتات مضغوطة."""
    import gzip as _gzip

    from starlette.responses import Response
    from app.utils.json_safe import SafeJSONResponse

    accepts_gzip = bool(
        request is not None and "gzip" in (request.headers.get("accept-encoding") or "")
    )

    # 1) كاش البايتات الجاهزة (مضغوطة إن قبل العميل gzip)
    if cache_key:
        cached = _bt_cache_get(cache_key)
        if cached is not None:
            tag, data = cached
            if tag == "gz":
                if accepts_gzip:
                    return Response(
                        content=data, status_code=status_code,
                        media_type="application/json",
                        headers={"Content-Encoding": "gzip"},
                    )
                raw = await asyncio.to_thread(_gzip.decompress, data)
                return Response(content=raw, status_code=status_code,
                                media_type="application/json")
            return Response(content=data, status_code=status_code,
                            media_type="application/json")

    # 2) بناء جديد: تسلسل داخل خيط ثم ضغط داخل خيط — الحلقة حرة تماماً
    renderer = SafeJSONResponse(content=None)
    body = await asyncio.to_thread(renderer.render, payload)
    if accepts_gzip:
        gz_body = await asyncio.to_thread(_gzip.compress, body, _gzip_level())
        if cache_key:
            _bt_cache_put(cache_key, ("gz", gz_body))
        return Response(
            content=gz_body, status_code=status_code,
            media_type="application/json",
            headers={"Content-Encoding": "gzip"},
        )
    if cache_key:
        _bt_cache_put(cache_key, ("raw", body))
    return Response(content=body, status_code=status_code,
                    media_type="application/json")


async def _get_or_build_base(db: AsyncSession, backtest_id: str,
                             backtest: Optional[BacktestRun] = None) -> Dict[str, Any]:
    """الأساس من الكاش أو بناؤه مرة واحدة داخل خيط عامل (R49 — لا تجميد للحلقة).

    ✅ R50: عند غياب السجل يُجلب المستند عبر _fetch_backtest_doc — عمود JSON
    الضخم يُفَك داخل خيط عامل لا داخل حلقة الأحداث (كان يجمدها ثوانٍ).
    """
    cache_key = f"{backtest_id}|chart"
    base = _bt_cache_get(cache_key)
    if base is not None:
        # ✅ R50.1: الأساس في الكاش — المستند الخام الذي جلبه المستدعي
        # لم يعد لازمًا: حرّره فورًا (كان يبقى محتجزًا حتى نهاية الطلب
        # ومثله ~500MB عابرة لكل طلب ثقيل).
        if backtest is not None and getattr(backtest, "chart_data", None) is not None:
            backtest.chart_data = None
        return base
    if backtest is None:
        backtest = await _fetch_backtest_doc(db, backtest_id)
    base = await asyncio.to_thread(_build_chart_base, backtest)
    # ✅ R50.1: تحرير المستند الخام فور بناء الأساس — كان يبقى محتجزًا في
    # ذاكرة الطلب حتى نهايته. الأساس يحمل كل ما تحتاجه الحمولات لاحقًا
    # (id/name/created_at/summary/full_config أعمدة خفيفة لا عمود chart_data).
    if getattr(backtest, "chart_data", None) is not None:
        backtest.chart_data = None
    _bt_cache_put(cache_key, base)
    return base


def _build_get_payload(base: Dict[str, Any], backtest) -> Dict[str, Any]:
    """(خفيف — عقد GET /backtest/get حرفيًا كما كان قبل R49)

    يشارك كائنات الشموع المسطّحة نفسها مع الأساس — بلا نسخ إضافية في الذاكرة.
    """
    chart_data: Dict[str, Any] = dict(base["get_extras"])
    chart_data["visual_candles"] = base["flat_candles"]
    chart_data["trade_points"] = base["trade_points_raw"]

    # ✅ نفس منطق _add_chart_data_by_symbol القديم (by_symbol + توثيق الرموز)
    if base.get("chart_data_by_symbol"):
        chart_data["chart_data_by_symbol"] = base["chart_data_by_symbol"]
    metadata = chart_data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {
            "symbol": getattr(backtest, "symbol", None),
            "timeframe": getattr(backtest, "timeframe", None),
        }
        chart_data["metadata"] = metadata
    if base["metadata"].get("symbols_in_candles"):
        metadata["symbols_in_candles"] = base["metadata"]["symbols_in_candles"]
    if not metadata.get("symbols"):
        metadata["symbols"] = metadata.get("symbols_in_candles") or base["metadata"].get("symbols")
    metadata.setdefault("display_symbol", metadata.get("symbol"))
    metadata.setdefault(
        "default_display_note",
        "الرمز الافتراضي المعروض = display_symbol (الرمز الأول في symbols)؛ "
        "بيانات كل رمز على حدة في chart_data_by_symbol، وكل شمعة موسومة بحقل symbol.",
    )

    return {
        "success": True,
        "backtest_id": backtest.id,
        "name": backtest.name,
        "created_at": backtest.created_at.isoformat() if backtest.created_at else None,
        "summary": backtest.summary,
        "chart_data": chart_data,
        "config": backtest.full_config,
    }


# ==========================================
# ✅ الجولة 42.1 — درع الصراحة (لا تجاهل صامت)
# ==========================================

def _reject_exit_strategy_r421(config: BacktestConfig) -> None:
    """كتلة exit_strategy تُنفّذ فقط في POST /api/v1/backtest1/run (المسار
    الموحد ج42). إرسالها إلى هذا المسار كان سيُقبلها من المخطط المشترك ثم
    يتجاهلها بصمت — ممنوع: 422 فوري برسالة صريحة تعلّم المتصل بالمسار الصحيح."""
    if getattr(config, "exit_strategy", None) is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "كتلة exit_strategy تُنفّذ فقط في المسار الموحد "
                "POST /api/v1/backtest1/run (الجولة 42) — هذا المسار لا ينفّذها "
                "ولن يتجاهلها بصمت. أعد توجيه الطلب إلى /api/v1/backtest1/run "
                "(وكيل الفرونت: تأكد أن البروكسي لا يعيد كتابة backtest1 إلى backtest)."
            ),
        )


# ==========================================
# 1. تشغيل باك-تست عبر Celery
# ==========================================

@router.post("/run")
async def run_backtest(config: BacktestConfig = Body(...)):
    """
    يرسل طلب الباك-تست إلى Celery Worker ويعيد task_id فوراً.

    ✅ Fallback بدون Redis/Celery: إذا لم يكن الـ broker متاحاً تُنفَّذ نفس
    المهمة داخل عملية الـ API كخلفية asyncio (نفس المحرك ونفس الحفظ في
    BacktestRun) ويعيد /status نفس العقد تماماً — زر الباك تست في اللوحة
    يعمل بلا Redis.

    ✅ الجولة 45 — رقم عملية تسلسلي + سجل دائم: المعرّف لم يعد عشوائياً
    (f397b2fa...) بل رقم مؤسساتي صريح 10000001 ثم 10000002 ... حتى
    99999999، يُخصَّص من عدّاد ذرّي في قاعدة البيانات، ويُسجَّل صف كامل
    (حالة/تقدّم/مدة/نتيجة سطحية) في جدول backtest_tasks — يُسترجع من
    GET /backtest1/tasks ويبقى سجلاً دائماً بعد إعادة التشغيل.

    ملاحظة: backtest_id يُنشأ داخل المهمة عند حفظ النتيجة في BacktestRun —
    استرجعه من GET /status/{task_id} بعد نجاح المهمة (حقل backtest_id).
    """
    _reject_exit_strategy_r421(config)  # ✅ ج42.1: درع الصراحة
    # ✅ فحص سريع لتوفر الـ broker قبل النشر — كان الطلب يعلّق لِدقائق
    # بإعادة محاولة kombu الافتراضية عندما يكون Redis/Celery غير متاح.
    # ✅ 14.1: الفحص شبكة متزامنة — يُنفَّذ في خيط عامل حتى لا يثبّت حلقة
    # الأحداث ~2 ثانية مع كل طلب عند سقوط Redis.
    from app.celery_app import is_broker_available

    # ✅ R45 — تخصيص رقم العملية التسلسلي وتسجيلها في السجل الدائم
    from app.services.task_registry import TaskRegistry

    symbol0 = str((config.symbols[0] if config.symbols else "") or "?")
    strategy0 = (
        (config.strategy_config or {}).get("name") if config.strategy_config else None
    )
    reg = TaskRegistry()
    task_number = await reg.allocate_id()
    task_id = str(task_number)
    _meta_common = None

    broker_available = await asyncio.to_thread(is_broker_available, 2.0)
    if not broker_available:
        # ✅ مسار احتياطي داخل العملية — لا 503 بعد اليوم
        config_dict = config.model_dump(mode="json")
        config_dict["_r45_task_id"] = task_number  # ✅ R45: رقم العملية للمُنفّذ
        await reg.register(
            task_number,
            name=config.name,
            mode="inprocess",
            symbol=symbol0.strip().upper()[:32],
            timeframe=str(config.timeframe or "1d")[:16],
            market=str(config.market or "crypto").strip().lower()[:16],
            strategy=str(strategy0 or "")[:64] or None,
        )
        _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": "Starting Backtest Engine..."}
        _task = asyncio.create_task(_run_backtest_inprocess(task_id, config_dict))
        _inprocess_task_refs.add(_task)  # ✅ 14.1: مرجع قوي يمنع GC في منتصف التشغيل
        _task.add_done_callback(_inprocess_task_refs.discard)
        logger.warning(
            "Celery broker unavailable → running backtest in-process (task %s, strategy '%s')",
            task_id, config.name,
        )
        return {
            "success": True,
            "task_id": task_id,
            "task_number": task_number,
            "status": "queued",
            "mode": "inprocess",
            "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
            "poll": f"/api/v1/backtest/status/{task_id}",
        }
    try:
        # ✅ model_dump(mode="json") يحول datetime إلى ISO strings —
        # dict()/json.dumps كان يفشل مع Celery JSON serializer (EncodeError)
        config_dict = config.model_dump(mode="json")
        config_dict["_r45_task_id"] = task_number  # ✅ R45: رقم العملية للعامل
        task = run_backtest_task.delay(config_dict)
        # ✅ R56 — درع مضاد للتوائم: المهمة سبق أن أُرسلت للعامل بنجاح —
        # أي فشل لاحق في تسجيل السجل (register/meta) كان يُمسكه المقبض
        # العام فتُعاد المحاكاة داخل عملية الـAPI (توأم + OOM). الآن
        # يُسجّل التحذير فقط ويعود الرد بنجاح — المهمة عند العامل.
        try:
            await reg.register(
                task_number,
                name=config.name,
                mode="celery",
                symbol=symbol0.strip().upper()[:32],
                timeframe=str(config.timeframe or "1d")[:16],
                market=str(config.market or "crypto").strip().lower()[:16],
                strategy=str(strategy0 or "")[:64] or None,
                meta={"celery_task_id": task.id},  # شفاء المتأخر + الانتقال السلس
            )
        except Exception:  # noqa: BLE001 — السجل لا يُفشل إرسالاً تمّ بنجاح
            logger.exception(
                "[R56] registry register after dispatch failed (non-fatal, task %s)",
                task_number,
            )
        logger.info(f"Dispatched backtest task {task.id} for '{config.name}'")
    except Exception:
        # ✅ R45: فشل النشر لا يترك صف سجل معلقاً — نذيبه إلى inprocess
        try:
            await reg.register(
                task_number,
                name=config.name,
                mode="inprocess",
                symbol=symbol0.strip().upper()[:32],
                timeframe=str(config.timeframe or "1d")[:16],
                market=str(config.market or "crypto").strip().lower()[:16],
                strategy=str(strategy0 or "")[:64] or None,
            )
            _inprocess_tasks[task_id] = {"state": "PROGRESS", "status": "Starting Backtest Engine..."}
            _task = asyncio.create_task(_run_backtest_inprocess(task_id, config_dict))
            _inprocess_task_refs.add(_task)
            _task.add_done_callback(_inprocess_task_refs.discard)
            logger.warning(
                "Celery dispatch failed → in-process fallback (task %s)", task_id
            )
            return {
                "success": True,
                "task_id": task_id,
                "task_number": task_number,
                "status": "queued",
                "mode": "inprocess",
                "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
                "poll": f"/api/v1/backtest/status/{task_id}",
            }
        except Exception:
            logger.exception("Failed to enqueue backtest task")
            raise HTTPException(
                status_code=503,
                detail="Failed to queue backtest task. The task broker may be unavailable."
            )

    return {
        "success": True,
        "task_id": task_id,
        "task_number": task_number,
        "status": "queued",
        "mode": "celery",
        "celery_task_id": task.id,
        "progress": {"percent": 2.0, "phase": "register", "message": "تم استلام العملية"},
        "poll": f"/api/v1/backtest/status/{task_id}",
    }


# ==========================================
# 2. حالة المهمة
# ==========================================

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """فحص حالة مهمة Celery أو مهمة داخلية (fallback بلا broker) — JSON-آمن

    ✅ الجولة 45: المعرّفات الرقمية (10000001...) تُقرأ من سجل العمليات
    الدائم في قاعدة البيانات — الحالة والتقدّم والمدة وETA تبقى صحيحة
    حتى بعد إعادة تشغيل الخدمة، ويُشفى صف celery المتأخر تلقائياً.
    المعرّفات السداسية القديمة تسلك مسارها التاريخي كاملاً.
    """
    # ✅ R45 — السجل الدائم أولاً للأرقام التسلسلية
    if task_id.isdigit():
        from app.services.task_registry import get_registry_status

        payload = await get_registry_status(task_id)
        if payload is not None:
            return payload

    # ✅ مهام المسار الاحتياطي داخل العملية تُدار من السجل المحلي أولاً
    if task_id in _inprocess_tasks:
        return _inprocess_status_payload(task_id)
    try:
        # ✅ R50 — قراءة حالة celery (شبكة Redis متزامنة) داخل خيط عامل
        def _read_celery():
            tr = AsyncResult(task_id, app=celery_app)
            st = tr.state
            if st == "PROGRESS":
                return st, (tr.info if isinstance(tr.info, dict) else {}), None, None
            if st == "SUCCESS":
                return st, None, tr.result, None
            if st == "FAILURE":
                return st, None, None, tr.info
            return st, None, None, None

        try:
            state, progress_info, success_result, failure_info = await asyncio.to_thread(_read_celery)
        except Exception:  # noqa: BLE001 — broker ساقط: لا 500 — تحلّل آمن
            return {
                "task_id": task_id,
                "state": "PENDING",
                "message": "Task state temporarily unavailable (broker offline) — retry shortly.",
            }
        response: Dict[str, Any] = {"task_id": task_id, "state": state}

        if state == 'PENDING':
            response['message'] = "Task is waiting to be processed."
        elif state == 'STARTED':
            response['message'] = "Task has started."
        elif state == 'PROGRESS':
            info = progress_info or {}
            response['message'] = info.get('status', 'Processing...')
        elif state == 'SUCCESS':
            result = success_result
            if isinstance(result, dict) and result.get("status") == "FAILURE":
                # (مهمة قديمة أرجعت FAILURE كقيمة نجاح — نتعامل معها)
                logger.warning(f"Task {task_id} returned embedded FAILURE: {result.get('error')}")
                response['state'] = 'FAILURE'
                response['message'] = "Task failed."
                response['error'] = "Backtest execution failed. See server logs for details."
            else:
                response['message'] = "Backtest completed successfully."
                if isinstance(result, dict):
                    response['backtest_id'] = result.get("backtest_id")
                response['result'] = result
        elif state == 'FAILURE':
            # نسجّل الاستثناء الحقيقي server-side ولا نكشفه للعميل،
            # ✅ لكن عند DEBUG نعرض السبب الحقيقي (Bugfix: كان الفشل يظهر
            # برسالة عامة بلا تفاصيل فيصعب تشخيصه مثل تعطل قاعدة البيانات).
            logger.error(f"Task {task_id} failed: {failure_info}")
            response['message'] = "Task failed."
            response['error'] = "Backtest execution failed. See server logs for details."
            from app.config import settings as _settings
            if _settings.DEBUG:
                info = failure_info
                if isinstance(info, dict) and info.get("error"):
                    response['error_detail'] = info["error"]
                elif isinstance(info, Exception):
                    response['error_detail'] = str(info)[:400]
                elif info:
                    response['error_detail'] = str(info)[:400]
        else:  # RETRY, REVOKED, ...
            response['message'] = f"Task state: {state}"

        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Failed to read status for task {task_id}")
        raise HTTPException(status_code=500, detail="Failed to read task status.")


# ==========================================
# 3. قائمة الباك-تستات
# ==========================================

@router.get("/list")
async def list_backtests(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """جلب قائمة عمليات الباك-تست المخزنة (الأحدث أولاً)

    ✅ R50 — قائمة خفيفة حرفياً: كان الاستعلام يحمّل كامل الكيان
    (بما فيه chart_data 52-208MB لكل صف!) ففتح صفحة المكتبة يُنزّل
    غيغابايتات JSONB داخل حلقة الأحداث — القياس الفعلي: 4 مستندات
    ثقيلة = 2.9 ثانية لكل /list والنظام كله متجمد خلفها. الآن:
    أعمدة العرض الخفيفة فقط — نفس الرد بالضبط بسرعة الملّي ثانية.
    """
    try:
        # ✅ R44 — قراءة عبر درع القفل (rollback + إعادة محاولة تصاعدية)
        from app.database.session import execute_with_lock_retry

        # ✅ R50 — load_only: صفر أعمدة JSON ضخمة في قائمة المكتبة
        from sqlalchemy.orm import load_only

        query = (
            select(BacktestRun)
            .options(load_only(
                BacktestRun.id, BacktestRun.name, BacktestRun.created_at,
                BacktestRun.total_pnl_percent, BacktestRun.win_rate,
                BacktestRun.total_trades, BacktestRun.timeframe, BacktestRun.symbol,
            ))
            .order_by(BacktestRun.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await execute_with_lock_retry(db, query, what="backtest/list")
        backtests = result.scalars().all()

        backtests_list = [
            {
                "id": bt.id,
                "name": bt.name,
                "created_at": bt.created_at.isoformat() if bt.created_at else None,
                "summary_stats": {
                    "total_pnl_percent": bt.total_pnl_percent,
                    "win_rate": bt.win_rate,
                    "total_trades": bt.total_trades,
                    "timeframe": bt.timeframe,
                    "symbol": bt.symbol,
                },
            }
            for bt in backtests
        ]

        return {
            "success": True,
            "count": len(backtests_list),
            "data": backtests_list,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error listing backtests")
        raise HTTPException(status_code=500, detail="Failed to list backtests.")


# ==========================================
# 4. تفاصيل باك-تست محدد
# ==========================================

def _add_chart_data_by_symbol(chart_data: Dict[str, Any], backtest) -> None:
    """
    ✅ الجولة 12 (بند 5-ب.3): تعارض الرموز في الباك-تست متعدد الرموز.

    كانت شموع كل الرموز تُدمج في visual_candles واحدة بينما metadata.symbol
    يعرض الرمز الأول فقط — فيعرض الشارت ملصق رمز مع بيانات رمز آخر.

    المعالجة (الحلّان معاً كما في الطلب):
    1) كل شمعة/نقطة موسومة بحقل symbol (من المحرك — الجديد).
    2) chart_data_by_symbol = {symbol: {visual_candles, trade_points}} —
       بيانات كل رمز على حدة.
    3) metadata.symbols = كل رموز التشغيل، metadata.display_symbol = الرمز
       الافتراضي المعروض (الرمز الأول في config.symbols)، وmetadata.symbols_in_candles
       = الرموز الموجودة فعلياً موسومة داخل الشموع.

    ملاحظة: السجلات القديمة (قبل الجولة 12) بلا وسم symbol → chart_data_by_symbol
    تُترك فارغة {} ويب(metadata.symbol) كما هو.
    """
    try:
        if not isinstance(chart_data, dict):
            return
        candles = chart_data.get("visual_candles")
        tps = chart_data.get("trade_points")
        if not isinstance(candles, list) or not candles:
            return

        by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        for c in candles:
            if not isinstance(c, dict):
                continue
            sym = c.get("symbol")
            if sym:
                by_symbol.setdefault(str(sym), []).append(c)

        if not by_symbol:
            return  # سجل قديم بلا وسم

        tp_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
        if isinstance(tps, list):
            for p in tps:
                if isinstance(p, dict) and p.get("symbol"):
                    tp_by_symbol.setdefault(str(p["symbol"]), []).append(p)

        chart_data["chart_data_by_symbol"] = {
            sym: {
                "visual_candles": c_list,
                "trade_points": tp_by_symbol.get(sym, []),
                "candles_count": len(c_list),
            }
            for sym, c_list in by_symbol.items()
        }

        metadata = chart_data.get("metadata")
        if not isinstance(metadata, dict):
            # ✅ المستند من قاعدة البيانات (wait=true / get) قد لا يحتوي metadata —
            # نُنشئه هنا حتى لا يعود بند الرموز فارغاً في أي مسار عرض.
            metadata = {
                "symbol": getattr(backtest, "symbol", None),
                "timeframe": getattr(backtest, "timeframe", None),
            }
            chart_data["metadata"] = metadata
        metadata["symbols_in_candles"] = sorted(by_symbol.keys())
        if not metadata.get("symbols"):
            metadata["symbols"] = metadata["symbols_in_candles"]
        metadata.setdefault("display_symbol", metadata.get("symbol"))
        metadata.setdefault(
            "default_display_note",
            "الرمز الافتراضي المعروض = display_symbol (الرمز الأول في symbols)؛ "
            "بيانات كل رمز على حدة في chart_data_by_symbol، وكل شمعة موسومة بحقل symbol.",
        )
    except Exception:  # noqa: BLE001 — لا نعطل العرض أبداً بسبب هذا
        logger.exception("chart_data_by_symbol build failed")


@router.get("/get/{backtest_id}")
async def get_backtest_details(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """جلب تفاصيل باك-تست محدد مع بيانات الشارت بالكامل (من قاعدة البيانات)
    ✅ الجولة 9: الكاش — البيانات ثابتة فلا إعادة حساب بعد أول طلب.
    ✅ R49: البناء الثقيل داخل خيط عامل (لا تجميد للحلقة) + مشاركة الأساس
    مع /chart-data (نسخة شموع واحدة في الذاكرة بدل نسختين).
    ✅ R50: تسلسل + ضغط gzip داخل خيط عامل وكاش البايتات المضغوطة
    (7MB بدل 52MB) — الوسيط لا يعيد ضغطها (Content-Encoding جاهز)."""
    try:
        cached = _bt_cache_get(f"{backtest_id}|getbytes")
        if cached is not None:
            from starlette.responses import Response
            if isinstance(cached, tuple):
                tag, data = cached
                if tag == "gz":
                    if request is not None and "gzip" in (request.headers.get("accept-encoding") or ""):
                        return Response(content=data, media_type="application/json",
                                        headers={"Content-Encoding": "gzip"})
                    import gzip as _gz
                    raw = await asyncio.to_thread(_gz.decompress, data)
                    return Response(content=raw, media_type="application/json")
                # ✅ R56 — زوج ("raw", bytes): كان السقوط يمرّر الزوج
                # لـ Response فينفجر بـ 'tuple' object has no attribute
                # 'encode' → 500 دائم لكل طلب لاحق (نفس إصلاح backtest1/get).
                if tag == "raw":
                    return Response(content=data, media_type="application/json")
            return Response(content=cached, media_type="application/json")

        # ✅ R50: جلب نصي خام + فك JSON في خيط عامل (كان يفك 52-208MB داخل الحلقة)
        backtest = await _fetch_backtest_doc(db, backtest_id)
        base = await _get_or_build_base(db, backtest_id, backtest)
        payload = await asyncio.to_thread(_build_get_payload, base, backtest)
        return await _serve_heavy_doc(request, payload, cache_key=f"{backtest_id}|getbytes")
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Error getting backtest details for {backtest_id}")
        raise HTTPException(status_code=500, detail="Failed to get backtest details.")


# ==========================================
# 5. بيانات الرسم البياني (من عمود chart_data في ORM)
# ==========================================

@router.get("/{backtest_id}/chart-data")
async def get_chart_data(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    start_index: int = Query(None, ge=0),
    limit: int = Query(None, ge=1),
    include_indicators: Optional[List[str]] = Query(None),
    # ✅ الجولة 10: مؤشرات البنية — overlays=zigzag,fib,trendline (اختياري)
    overlays: Optional[str] = Query(None, description="zigzag,fib,trendline — يضيف حقل overlays للاستجابة"),
    zz_length: int = Query(100, ge=2, le=2000),
    fib_depth: int = Query(10, ge=1, le=500),
    fib_dev: float = Query(5.0, ge=0.0, le=100.0),
    fib_ret: float = Query(0.618, ge=-10.0, le=10.0),
    tl_period: int = Query(10, ge=2, le=500),
    tl_pairs: int = Query(1, ge=1, le=250),
):
    """
    جلب بيانات الرسم البياني من BacktestRun.chart_data (JSON column).

    الاستجابة: {metadata, equity_curve, drawdown_curve, visual_candles, trade_points}
    - equity_curve/drawdown_curve: من chart_data إن وُجدت، وإلا تُشتق من
      account_balance في الشموع، وإلا None (بدون انهيار).
    - 404 أنيق عندما لا توجد بيانات رسم على الإطلاق.

    ✅ الجولة 9:
    - كاش الأساس المعالج لكل backtest_id — كل طلب لاحق تقطيع خفيف (أداء ثابت).
    - `include_indicators=true` (قيمة منطقية حرفية) تعني **تضمين كل المؤشرات**
      بدل تفسيرها كاسم مؤشر اسمه "true" — هذا كان يُسقط حقول ind_* بالخطأ.
    - `include_indicators=true` يعمل الآن مع limit معاً (حقل ind_* لا يُسقط).

    ✅ R49 — إصلاح التجميد الجذري:
    - كل البناء الثقيل (الأساس + التقطيع + الفلترة + overlays على كامل
      السلسلة) داخل asyncio.to_thread — حلقة الأحداث تظل تخدم بقية
      النقاط (/health و/status و/tasks) طوال الوقت.
    - overlays يُحسب على كامل الشموع كما كان (نفس النتائج بالضبط) لكن
      داخل خيط عامل، ويُخزَّن بكاشه المستقل — الطلبات التالية فورية.
    """
    try:
        # ---- تطبيع معامل المؤشرات (قبل الكاش — الرموز المنطقية ليست أسماء) ----
        inc_norm: Optional[List[str]]
        if isinstance(include_indicators, (list, tuple, set)) and include_indicators:
            flags = {str(x).strip().lower() for x in include_indicators}
            if flags & {"true", "1", "yes", "all", "full"}:
                inc_norm = None          # "true" → كل المؤشرات
            elif flags & {"false", "0", "no", "none"}:
                inc_norm = []            # "false" → بلا مؤشرات
            else:
                inc_norm = [str(x) for x in include_indicators]
        else:
            inc_norm = None if not include_indicators else [str(x) for x in include_indicators]

        # ---- الأساس المعالج (يُبنى مرة واحدة لكل باك-تست — داخل خيط عامل) ----
        was_cached = _bt_cache_get(f"{backtest_id}|chart") is not None
        base = await _get_or_build_base(db, backtest_id)

        # ---- تجهيز الاستجابة من الأساس (تقطيع/نسخ خفيف — داخل خيط عامل) ----
        def _slice_and_filter():
            flat_candles = base["flat_candles"]
            offset = start_index or 0
            if start_index is not None or limit is not None:
                window = flat_candles[offset: offset + limit] if limit else flat_candles[offset:]
            else:
                window = flat_candles

            if inc_norm is None:
                formatted = window                      # الشكل الشامل كما هو
            else:
                wanted = {str(n) for n in inc_norm}
                formatted = [
                    {k: v for k, v in c.items() if not k.startswith("ind_") or k[4:] in wanted}
                    for c in window
                ]
            return window, formatted

        window, formatted_candles = await asyncio.to_thread(_slice_and_filter)

        metadata = base["metadata"]
        available_indicators = base["available_indicators"]
        raw_len = base["raw_len"]

        visible_range_start = start_index or 0
        visible_range_end = visible_range_start + len(formatted_candles)

        # ✅ الجولة 10: مؤشرات البنية — تُحسب مرة واحدة على كامل الشموع (لا النافذة)
        # وتُخزن بكاش مستقل بمعاملاتها — الطلبات المتتالية لحظية.
        # ✅ R49: الحساب داخل خيط عامل — كان يحجز حلقة الأحداث 46-231 ثانية.
        overlays_payload: Optional[Dict[str, Any]] = None
        # ✅ ROUND30: الفيبو يصل افتراضياً — عند غياب overlays نحسب الطبقات البنيوية
        # (zzfib,fib,zzfib_e2e) ما دام عدد الشموع ضمن السقف الآمن، وoverlays=none
        # يعطلها صراحة. (جولة 12.1: FieldInfo من الاستدعاء المباشر يُعامَل كغياب.)
        ovl_effective = _resolve_overlays_request(overlays, int(raw_len or 0))
        if ovl_effective:
            wanted_ovl = [t.strip().lower() for t in str(ovl_effective).split(",") if t.strip()]
            if not wanted_ovl or "all" in wanted_ovl or "*" in wanted_ovl:
                wanted_ovl = list(_OVL_TYPES)
            # 🔥 R69.1 — المسار الافتراضي (بلا overlays صريحة من الفرونت):
            # أضف طبقة عائلة استراتيجية التشغيل نفسها تلقائياً — فتصل
            # إحداثيات زقزاقها/فيبوها/ترندها مع الافتراضيات البنيوية،
            # والطلب الصريح يُحترم حرفياً كما كان (لا تغيير على عقد الجولة 10).
            _ovl_requested = (
                isinstance(overlays, str) and overlays.strip()
                and overlays.strip().lower() not in _OVERLAYS_OFF_TOKENS
            )
            if not _ovl_requested:
                for _fam in _strategy_family_overlays(available_indicators):
                    if _fam not in wanted_ovl:
                        wanted_ovl = wanted_ovl + [_fam]
            unknown = [t for t in wanted_ovl if t not in _OVL_TYPES]
            if unknown:
                raise HTTPException(status_code=400, detail=f"أنواع overlays غير معروفة: {unknown}. المسموح: {list(_OVL_TYPES)}")
            ovl_params: Dict[str, Dict[str, Any]] = {
                "zigzag": {"length": zz_length},
                "fib": {"depth": fib_depth, "dev_threshold": fib_dev, "retracement": fib_ret},
                "trendline": {"period": tl_period, "max_pairs": tl_pairs},
                # ✅ ROUND19: رسم zzfib في الباك-تست بوضع زقزاق TV الكلاسيكي —
                # نفس معاملات البريسِت الحي (ZLF) حتى يطابق الرسم الإشارات المولّدة
                # بنفس الوضع (اتساق بصري كامل بين الحي والباك-تست وTV).
                "zzfib": {"mode": "tradingview", "depth": 12,
                          "deviation": 20, "backstep": 3},
                # ✅ ROUND22: رسم المحرك المنفصل ZLF-End-To-End بوضع شارت المنصة
                # (luxalgo length=100) — نفس معاملات قالب zlf_e2e الحي حتى يطابق
                # الرسم الإشارات المولّدة بنفس الوضع (اتساق بصري كامل).
                "zzfib_e2e": {"mode": "luxalgo", "length": 100},
                # ✅ ROUND32: رسم «الترندية» (طلب صريح overlays=zzfib_e2e_trendy) —
                # نفس معاملات قالب zlf_e2e_trendy الحي: الفترات قالبية [7,15,25]
                # (غيّرها/أضف رابعاً 30 من القالب) + بوابة majority على s1/s2/s3.
                "zzfib_e2e_trendy": {"mode": "luxalgo", "length": 100,
                                     "trend_periods": [7, 15, 25],
                                     "trend_confirm": "majority",
                                     "trend_gate": ["s1", "s2", "s3"]},
                # ✅ ROUND32: رسم مؤشر الترند المستقل (طلب صريح overlays=trend_fractal)
                "trend_fractal": {"periods": [7, 15, 25]},
                # 🔥 R69: رسم «الترندية الملتهبة» — نفس معاملات قالب
                # zlf_e2e_blazing الحي (luxalgo length=100 — وضع شارت
                # المنصة) حتى يطابق الرسم الإشارات المولّدة بنفس الوضع
                # (اتساق بصري كامل): الفترات قالبية [7,15,25] majority
                # والبوابة على الأنواع الخمسة s1/s2/s3/n5/n6.
                "zzfib_e2e_blazing": {"mode": "luxalgo", "length": 100,
                                      "trend_periods": [7, 15, 25],
                                      "trend_confirm": "majority",
                                      "trend_gate": ["s1", "s2", "s3", "n5", "n6"]},
            }
            ovl_key_src = json.dumps([wanted_ovl, ovl_params, raw_len], sort_keys=True, default=str)
            ovl_key = f"{backtest_id}|ovl|{hashlib.md5(ovl_key_src.encode()).hexdigest()}"
            overlays_payload = _bt_cache_get(ovl_key)
            ovl_cached = overlays_payload is not None
            if overlays_payload is None:
                # ✅ ROUND34 — الحجم يجب أن يمر مع الشموع في مسار رسم overlays
                # للباك تست (نفس إصلاح ROUND28 للشارت الحي): بدون الحجم لا
                # يُبنى المرجع R في zzfib_e2e/zzfib_e2e_trendy فتظهر النطاقات
                # بلا مراجع وبلا إشارات في حمولة الرسم — بينما الاستراتيجية
                # نفسها حسبت إشاراتها بالحجم الكامل. (الأزمنة أُصلحت جذرياً
                # في ROUND34 عبر المحرك الموحد: timestamp كسلسلة ISO يُحلَّل
                # فعلياً الآن — كانت كل أزمنة الرسم صفراً.)
                def _build_overlays():
                    ovl_candles = [
                        {"time": c.get("timestamp"), "open": c.get("open"), "high": c.get("high"),
                         "low": c.get("low"), "close": c.get("close"),
                         "volume": c.get("volume")}
                        for c in base["flat_candles"] if isinstance(c, dict)
                    ]
                    ovl_result = _compute_overlays(ovl_candles, types=wanted_ovl, params=ovl_params)
                    return {
                        "types": wanted_ovl,
                        "bars": ovl_result["bars"],
                        "time_from": ovl_result["time_from"],
                        "time_to": ovl_result["time_to"],
                        "overlays": ovl_result["overlays"],
                    }

                overlays_payload = await asyncio.to_thread(_build_overlays)
                _bt_cache_put(ovl_key, overlays_payload)
            overlays_payload = dict(overlays_payload)
            overlays_payload["cache"] = "hit" if ovl_cached else "built"
            # ✅ ROUND30: شفافية المصدر — طلب صريح من العميل أم افتراضي الجولة 30؟
            overlays_payload["source"] = (
                "requested" if (isinstance(overlays, str) and overlays.strip()
                                and overlays.strip().lower() not in _OVERLAYS_OFF_TOKENS)
                else "default"
            )

        _payload = {
            "backtest_id": metadata["backtest_id"],
            "metadata": metadata,
            "equity_curve": base["equity_curve"],
            "drawdown_curve": base["drawdown_curve"],
            "visual_candles": formatted_candles,
            "trade_points": base["trade_points"],
            # ✅ الجولة 12 (بند 5-ب.3): بيانات كل رمز على حدة (إن وُجد وسم)
            **({"chart_data_by_symbol": base["chart_data_by_symbol"]}
               if base.get("chart_data_by_symbol") else {}),
            **({"overlays": overlays_payload} if overlays_payload is not None else {}),
            "summary": {
                "total_candles": raw_len,
                "total_trades": len(base["trade_points"]),
                "win_rate": metadata["win_rate"],
                "total_pnl": metadata["total_pnl"],
                "total_pnl_percent": metadata["total_pnl_percent"],
                "max_drawdown_percent": metadata["max_drawdown_percent"],
                "sharpe_ratio": metadata["sharpe_ratio"],
                "available_indicators": available_indicators,
                "visible_range": f"{visible_range_start}-{visible_range_end}",
                "has_more_data": visible_range_end < raw_len,
                # ✅ الجولة 9: شفافية الكاش للتشخيص
                "cache": "hit" if was_cached else "built",
            },
        }
        # ✅ R49 → R50 — كاش bytes الجاهزة لمفتاح المعاملات الكامل: التنقل
        # المتكرر بين المكتبة والشارت (نفس الطلب) يصبح فوريًا — التسلسل +
        # الضغط (70-208MB رد) يحدث مرة واحدة داخل خيط عامل ثم يُخزَّن
        # **مضغوطاً** (7-25MB) فتتسع سعة الكاش عدة أضعاف بنفس الميزانية.
        _resp_key_src = json.dumps(
            [backtest_id, start_index, limit, inc_norm, ovl_effective,
             zz_length, fib_depth, fib_dev, fib_ret, tl_period, tl_pairs],
            sort_keys=True, default=str,
        )
        _resp_key = f"{backtest_id}|resp|{hashlib.md5(_resp_key_src.encode()).hexdigest()}"
        return await _serve_heavy_doc(request, _payload, cache_key=_resp_key)
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Error building chart data for {backtest_id}")
        raise HTTPException(status_code=500, detail="Failed to build chart data.")


# ==========================================
# 6. حذف باك-تست
# ==========================================

@router.delete("/delete/{backtest_id}")
async def delete_backtest_run(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
):
    """حذف نتيجة باك-تست محددة من قاعدة البيانات"""
    try:
        backtest = await _get_backtest_row(db, backtest_id)
        name = backtest.name

        await db.delete(backtest)
        await db.commit()

        # ✅ الجولة 9: إبطال كاش الباك-تست المحذوف
        _bt_cache_drop(backtest_id)

        return {
            "success": True,
            "message": f"Backtest '{name}' deleted successfully",
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception(f"Error deleting backtest {backtest_id}")
        raise HTTPException(status_code=500, detail="Failed to delete backtest.")


# ==========================================
# 7. Walk-Forward Analysis (محرك لكل طلب)
# ==========================================

@router.post("/walk-forward")
async def run_walk_forward_analysis(
    config: BacktestConfig = Body(...),
    train_days: Optional[int] = Query(None, ge=1, description="طول نافذة التدريب بالأيام (افتراضي: 3× test_days)"),
    test_days: Optional[int] = Query(None, ge=1, description="طول نافذة الاختبار بالأيام (افتراضي: تقسيم الفترة)"),
    max_windows: int = Query(5, ge=1, le=MAX_WALK_FORWARD_WINDOWS, description="أقصى عدد نوافذ"),
):
    """
    تشغيل تحليل المشي للأمام (Anchored Walk-Forward).

    المحرك يُنشأ لكل طلب (بدون cache عالمي يحتفظ بجلسة DB قديمة) ويُغلق مع الجلسة.
    """
    _reject_exit_strategy_r421(config)  # ✅ ج42.1: درع الصراحة
    try:
        async with async_session_maker() as db:
            engine = BacktestEngine(DataService(db))
            result = await engine.run_walk_forward_analysis(
                config,
                train_days=train_days,
                test_days=test_days,
                max_windows=max_windows,
            )

        overall = result.get("overall", {})
        return {
            "success": True,
            "method": result.get("method"),
            "train_days": result.get("train_days"),
            "test_days": result.get("test_days"),
            "windows": result.get("windows", []),
            "periods_summary": [
                {
                    "period": w.get("window"),
                    "start_date": w.get("test_start"),
                    "end_date": w.get("test_end"),
                    "pnl_percent": (w.get("out_of_sample") or {}).get("total_pnl_percent"),
                    "win_rate": (w.get("out_of_sample") or {}).get("win_rate"),
                }
                for w in result.get("windows", [])
            ],
            "overall": overall,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Walk-forward analysis failed")
        raise HTTPException(
            status_code=500,
            detail="Walk-forward analysis failed. Check server logs for details."
        )


# ==========================================
# 8. Monte Carlo Simulation (محرك لكل طلب)
# ==========================================

@router.post("/monte-carlo")
async def run_monte_carlo_simulation(
    config: BacktestConfig = Body(...),
    n_simulations: int = Query(100, ge=1, le=MAX_MONTE_CARLO_SIMULATIONS, description="عدد المحاكاات (1-500)"),
    random_seed: Optional[int] = Query(None, ge=0, description="بذرة عشوائية للتكرارية"),
):
    """
    تشغيل محاكاة مونت كارلو (bootstrap على صفقات باك-تست أساسي واحد).
    المحرك يُنشأ لكل طلب ويُغلق مع الجلسة.
    """
    _reject_exit_strategy_r421(config)  # ✅ ج42.1: درع الصراحة
    try:
        async with async_session_maker() as db:
            engine = BacktestEngine(DataService(db))
            results = await engine.run_monte_carlo_simulation(
                config,
                n_simulations=n_simulations,
                random_seed=random_seed,
            )

        prob_of_profit = results.get("probability_of_profit")
        return {
            "success": True,
            "results": results,
            "interpretation": {
                "probability_of_profit": (
                    f"{prob_of_profit * 100:.1f}%" if isinstance(prob_of_profit, (int, float)) else None
                )
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Monte Carlo simulation failed")
        raise HTTPException(
            status_code=500,
            detail="Monte Carlo simulation failed. Check server logs for details."
        )


# ==========================================
# 9. المقاييس المتاحة
# ==========================================

@router.get("/metrics")
async def get_available_metrics():
    """الحصول على المقاييس المتاحة"""
    return {
        "return_metrics": ["total_pnl", "sharpe_ratio", "win_rate"],
        "risk_metrics": ["max_drawdown", "volatility"],
        "trade_metrics": ["total_trades", "avg_win", "avg_loss"],
    }
