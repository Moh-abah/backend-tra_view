"""Trading Backend — FastAPI application entrypoint.

Wires up application lifecycle (database init/teardown), CORS, core routers
and health/debug endpoints. Run with: uvicorn app.main:app
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.config import settings
from app.database import close_db, init_db
from app.routers import (
    agent_docs,
    api,
    backtest,
    backtest1,  # ✅ الجولة 11: كان موجوداً في الكود وغير مسجّل — سبب 404 على /backtest1/*
    drawings,
    filtering,
    indicators,
    market_data,
    mtf,
    overlays,  # ✅ الجولة 10: مؤشرات البنية (ZigZag/Fib/Trendline)
    settings as settings_router,
    stock_analysis,
    strategies,
    strategies1,
    users,
    websocket,
)

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, str(getattr(settings, "LOG_LEVEL", "INFO")).upper(), logging.INFO),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Application lifespan
# ----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup and release them on shutdown."""
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception:
        logger.exception("Failed to initialize database")
        raise RuntimeError("Database initialization failed; refusing to serve requests")

    # ✅ الجولة 6: تقرير صحة تخزين SQLite عند الإقلاع — يظهر في docker logs
    # ويعطي المسار/الصلاحيات/البديل المُفعّل لكل قاعدة (رؤية كاملة بلا تخمين).
    try:
        from app.core.storage_health import log_storage_report
        log_storage_report()
    except Exception:  # noqa: BLE001
        logger.exception("Storage health report failed (non-fatal)")

    yield

    try:
        await close_db()
        logger.info("Database connection closed")
    except Exception:
        logger.exception("Error while closing database")


# ----------------------------------------------------------------------------
# Application instance
# ----------------------------------------------------------------------------
from app.utils.json_safe import SafeJSONResponse  # noqa: E402 - after settings

_OPENAPI_DESCRIPTION = """
## منصة التداول — الواجهة البرمجية الكاملة | TR Platform API

توثيق كامل **بدون أي غموض** لوكيل الفرونت: نقاط النهاية، نماذج البيانات،
أمثلة استجابات حقيقية، بروتوكول الشموع اللانهائية، وصيغ رسائل البث الحي.

### 🚀 نقطة البداية لوكيل الفرونت (Start Here)
| المورد | الرابط | الاستخدام |
|---|---|---|
| 📘 **عقد الوكيل الكامل** | [`/agent/contract.json`](/agent/contract.json) | **اقرأ أولاً** — عقد آلي كامل: كل نقطة + أمثلة + بروتوكولات |
| 📗 **دليل الوكيل (HTML)** | [`/agent`](/agent) | صفحة عربية RTL تشرح كل شيء خطوة بخطوة |
| 📙 **Markdown خام** | [`/agent/contract.md`](/agent/contract.md) | نسخة نصية للقراءة البرمجية |
| 📕 **OpenAPI Schema** | [`/openapi.json`](/openapi.json) | هذا الملف — يُولَّد من الكود الفعلي (مصدر الحقيقة) |

### ⚡ أهم 3 نقاط لاحتياجات الشارت
```http
GET /api/v1/market/candles/crypto/BTCUSDT?timeframe=1h&limit=2000            ← آخر 2000 شمعة
GET /api/v1/market/candles/crypto/BTCUSDT?timeframe=1h&limit=2000&before=...  ← أقدم (تمرير يسار)
WS  /api/v1/market/ws/live/crypto/BTCUSDT?timeframe=1m                        ← بث حي kline
```
**لا يوجد حد على إجمالي الشموع** — التاريخ الكامل متاح عبر التمرير (`has_more` / `next_before`).

### 🧭 خريطة الوحدات (Tags)
- **market-data**: الشموع + الرموز + الأسعار + البث الحي
- **websocket**: مسارات `/ws` (stream/market-overview/filtering/indicators/chart)
- **indicators**: 54 مؤشراً + Pine Transpiler + الإشارات
- **strategies / backtest / filtering / mtf / stocks-analysis / users / settings**
""".strip()

app = FastAPI(
    title="TR Platform — Trading Backend API",
    version=settings.VERSION,
    lifespan=lifespan,
    default_response_class=SafeJSONResponse,
    description=_OPENAPI_DESCRIPTION,
    openapi_tags=[
        {"name": "meta", "description": "صحة الخدمة والفهارس — service health & root index"},
        {
            "name": "market-data",
            "description": (
                "### الشموع والأسعار والرموز — مصدر حقيقة الشارت\n"
                "- `GET /candles/{market}/{symbol}` — **النقطة الموصى بها للشارت**: ترقيم صفحات cursor-based "
                "(`limit` + `before`) مع `has_more`/`next_before` للتمرير اللانهائي بنمط TradingView.\n"
                "- `GET /historical/{market}/{symbol}` — تاريخ كامل حتى 10 سنوات (استجابة كبيرة — استخدم للتصدير/التحليل).\n"
                "- `GET /price/{market}/{symbol}` — السعر الحي.\n"
                "- `WS /ws/live/{market}/{symbol}` — بث kline حي.\n"
                "الأسواق: `crypto` (774 رمزاً من Binance) و`stocks` (5,222 رمزاً)."
            ),
        },
        {
            "name": "websocket",
            "description": (
                "قنوات البث الحي تحت `/ws`: نظرة عامة على السوق، بث رمز واحد، فلترة حية، "
                "وشاشة المؤشرات. **ملاحظة مهمة لوكيل الفرونت:** بث الشموع الحية للشارت موصى به عبر "
                "`/api/v1/market/ws/live/{market}/{symbol}` (وسم market-data)، والبديل الاحتياطي المعتمد "
                "هو Binance WS مباشر `wss://stream.binance.com:9443/ws/{symbol}@kline_{tf}`."
            ),
        },
        {
            "name": "indicators",
            "description": "54 مؤشراً فنياً + دليل الاعدادات الافتراضية لكل مؤشر + تحويل Pine Script + إشارات تداول مركبة. اكتشف القائمة الحية عبر `GET /available`.",
        },
        {"name": "strategies", "description": "بناء واستعلام استراتيجيات التداول (مؤشرات مركبة وشروط دخول/خروج)"},
        {"name": "strategies1", "description": "واجهة استراتيجيات بديلة/مبسطة — استخدمها فقط إذا احتجت شكلاً مختلفاً"},
        {"name": "backtest", "description": "محرك الاختبار التاريخي: تشغيل استراتيجية على بيانات حقيقية وإرجاع الصفقات والمنحنى"},
        {"name": "backtest1", "description": "محرك اختبار بديل — نفس الغرض مع اختلافات في الحمولة"},
        {"name": "filtering", "description": "فلترة شاملة للرموز حسب معايير فنية (WS + REST) للكاشف والمسح السوقي"},
        {"name": "users", "description": "تسجيل/دخول JWT + الملف الشخصي + قوائم المتابعة — يتغير حسب نقطة بمصادقة Bearer"},
        {"name": "settings", "description": "إعدادات المستخدم والحسابات API للمنصات + تشغيل/اختبار الفلاتر المحفوظة"},
        {"name": "stocks-analysis", "description": "تحليل الأسهم الأمريكية: ملخص، مؤشرات، توصيات مبنية على بيانات yfinance"},
        {"name": "mtf", "description": "تحليل متعدد الفريمات: تصويت موزون (خفيف/متوسط/ثقيل) لمؤشر مركب على عدة فريمات"},
        {"name": "core", "description": "نقاط أساسية مشتركة (رموز/صحة) — بديل قديم، فضّل market-data"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# ✅ الجولة 6: توثيق ذاتي لحد limit الأقصى (طلب الفرونت — تقرير الجولة 5 #3)
# كل استجابات نقاط الشموع تحمل X-Max-Limit بقيمة الحد المقبول للنقطة نفسها:
#   /api/v1/market/candles/{market}/{symbol}        → 5000  (صفحة التمرير)
#   /api/v1/market/candles/{market}/{symbol}/range  → 20000 (نطاق from/to)
# ترويسة ثابتة على كل الاستجابات (200/422/500) ليكتشفها العميل ذاتياً.
# ----------------------------------------------------------------------------
_X_MAX_LIMIT_DEFAULT = 5000
_X_MAX_LIMIT_RANGE = 20000


@app.middleware("http")
async def candles_max_limit_header(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/v1/market/candles"):
        if path.endswith("/range"):
            response.headers["X-Max-Limit"] = str(_X_MAX_LIMIT_RANGE)
        else:
            response.headers["X-Max-Limit"] = str(_X_MAX_LIMIT_DEFAULT)
    return response


# ----------------------------------------------------------------------------
# Routers
# ----------------------------------------------------------------------------
API_PREFIX = settings.API_V1_PREFIX

app.include_router(api.router, prefix=API_PREFIX)
app.include_router(market_data.router, prefix=f"{API_PREFIX}/market")
app.include_router(backtest.router, prefix=f"{API_PREFIX}/backtest")
app.include_router(backtest1.router, prefix=f"{API_PREFIX}/backtest1")  # ✅ الجولة 11: تسجيل الراوتر المفقود
app.include_router(indicators.router, prefix=f"{API_PREFIX}/indicators")
app.include_router(strategies.router, prefix=f"{API_PREFIX}/strategies")
app.include_router(strategies1.router, prefix=f"{API_PREFIX}/strategies1")
app.include_router(websocket.router, prefix="/ws")
app.include_router(filtering.router, prefix=f"{API_PREFIX}/filtering")
app.include_router(users.router, prefix=f"{API_PREFIX}/users")
app.include_router(settings_router.router, prefix=f"{API_PREFIX}/settings")
app.include_router(stock_analysis.router, prefix=f"{API_PREFIX}/stocks")
app.include_router(drawings.router, prefix=f"{API_PREFIX}/chart")  # ✅ الجولة 4: أدوات الرسم
app.include_router(mtf.router, prefix=f"{API_PREFIX}/mtf")
app.include_router(overlays.router, prefix=f"{API_PREFIX}/overlays")  # ✅ الجولة 10: ZigZag/Fib/Trendline


# ----------------------------------------------------------------------------
# Basic endpoints
# ----------------------------------------------------------------------------
@app.get("/", tags=["meta"], summary="فهرس الخدمة — كل روابط التوثيق")
async def root():
    """Service metadata and pointers — نقطة البداية: كل روابط التوثيق والعقد في مكان واحد."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "openapi": "/openapi.json",
        "agent": {
            "contract_json": "/agent/contract.json",
            "contract_md": "/agent/contract.md",
            "guide_html": "/agent",
            "note": "ابدأ هنا يا وكيل الفرونت — عقد كامل بدون غموض",
        },
        "demo_chart": "/demo/chart.html",
        "websocket": "/ws",
    }


@app.get("/health", tags=["meta"])
async def health():
    """Simple liveness probe."""
    return {"status": "ok"}


@app.get("/health/storage", tags=["meta"])
async def health_storage():
    """✅ الجولة 6: تشخيص حي لتخزين SQLite — المسارات، الصلاحيات، المستخدم،
    وأي مسار بديل مُفعّل. أداة إثبات مباشرة أن مشاكل
    'unable to open database file' / 'readonly database' انتهت (أو تشخيصها فوراً)."""
    from app.core.storage_health import storage_status
    return storage_status()


# ----------------------------------------------------------------------------
# Professional chart demo (TradingView-style) — served same-origin from the API
# Open: /demo/chart.html   (uses /api/v1/market/candles + /ws/live automatically)
# ----------------------------------------------------------------------------
from pathlib import Path as _Path  # noqa: E402

_DEMO_DIR = _Path(__file__).resolve().parent.parent / "demo"
if _DEMO_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles  # noqa: E402

    app.mount("/demo", StaticFiles(directory=str(_DEMO_DIR), html=True), name="demo")


# ----------------------------------------------------------------------------
# Agent contract endpoints (/agent, /agent/contract.json, /agent/contract.md)
# ----------------------------------------------------------------------------
app.include_router(agent_docs.router)


if settings.DEBUG:

    @app.get("/debug/routes", tags=["meta"])
    async def debug_routes():
        """List all registered routes (debug builds only)."""
        routes = []
        for route in app.routes:
            if isinstance(route, APIRoute):
                routes.append({"path": route.path, "name": route.name, "methods": sorted(route.methods)})
        return {"routes": routes}
