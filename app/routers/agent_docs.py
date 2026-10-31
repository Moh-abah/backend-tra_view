"""Agent contract endpoints — مصدر الحقيقة لوكيل الفرونت.

يخدم ثلاثة مسارات تحت /agent:
  GET /agent                 → صفحة HTML عربية RTL (دليل الوكيل)
  GET /agent/contract.json   → عقد آلي كامل (يُبنى من app.routes الفعلية + أمثلة منقّحة)
  GET /agent/contract.md     → نفس العقد بصيغة Markdown

الفكرة: الكتالوج يُولَّد ديناميكياً من الراوترات المسجّلة فعلياً —
أي نقطة تُضاف أو تُحذف تظهر تلقائياً في العقد (صفر انحراف عن الكود).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-docs"], include_in_schema=True)

# ---------------------------------------------------------------------------
# محتوى منقّح: أمثلة حقيقية وبروتوكولات (مُختبرة فعلياً على بيانات Binance)
# ---------------------------------------------------------------------------

_BASE_INFO = {
    "service": "TR Platform — Trading Backend",
    "api_prefix": "/api/v1",
    "local_base_url": "http://localhost:8000",
    "frontend_expected_port": 3018,
    "auth": {
        "type": "JWT Bearer",
        "header": "Authorization: Bearer <access_token>",
        "login": "POST /api/v1/users/login → {access_token, token_type}",
        "note": "بعض نقاط المستخدمين فقط تتطلب توكن؛ بيانات السوق والشموع مفتوحة",
    },
    "markets": {
        "crypto": {"provider": "Binance", "symbols": 774, "alias": ["binance"]},
        "stocks": {"provider": "yfinance", "symbols": 5222, "alias": ["stock"]},
    },
    "docs": {
        "swagger_ui": "/docs",
        "openapi_schema": "/openapi.json",
        "agent_contract": "/agent/contract.json",
        "agent_page": "/agent",
        "demo_chart": "/demo/chart.html",
    },
}

_PAGINATION_PROTOCOL = {
    "title": "بروتوكول الشموع اللانهائية (TradingView-style)",
    "rules": [
        "لا يوجد حد إجمالي على الشموع إطلاقاً — التاريخ الكامل من Binance متاح (BTC منذ 2017)",
        "حد الصفحة الواحدة فقط: limit بين 10 و 5000 (الافتراضي 2000)",
        "الشموع تعود تصاعدية (الأقدم أولاً) مغلقة فقط — جاهزة للدمج المباشر",
        "الاستمرارية عبر has_more + next_before (أقدم وقت في الصفحة بالملي ثانية)",
    ],
    "flow": [
        "1) الطلب الأول: GET /api/v1/market/candles/crypto/BTCUSDT?timeframe=1h&limit=2000",
        "2) ارسم candles كما هي (ترتيب تصاعدي)",
        "3) عند تمرير المستخدم لأقصى اليسار و has_more==true:",
        "   GET ...&before=<next_before>  ← يرجع 2000 شمعة أقدم، ادمجها prepend",
        "4) كرر حتى has_more==false (نهاية التاريخ) — لا فجوات ولا تكرارات",
    ],
    "js_pseudocode": """
// داخل مكوّن الشارت (lightweight-charts)
let oldestLoaded = null;
async function loadPage(symbol, timeframe) {
  const url = `/api/v1/market/candles/crypto/${symbol}` +
    `?timeframe=${timeframe}&limit=2000` +
    (oldestLoaded ? `&before=${oldestLoaded}` : '');
  const r = await fetch(url);           // Next.js rewrite → localhost:8000
  const j = await r.json();
  if (oldestLoaded) chart.prependCandles(j.candles);  // الصفحات التالية
  else chart.setCandles(j.candles);                   // أول تحميل
  oldestLoaded = j.next_before;
  return j.has_more;                    // false = وصلنا لبداية التاريخ
}
// اشتراك النطاق المرئي:
chart.subscribeVisibleLogicalRangeChange(range => {
  if (range.from < 10 && hasMore && !loading) loadPage(sym, tf);
});
""".strip(),
}

_RESPONSE_EXAMPLES = {
    "candles_page": {
        "symbol": "BTCUSDT",
        "market": "crypto",
        "timeframe": "1h",
        "candles": [
            {
                "time": 1767139200000,
                "open": 80216.01,
                "high": 80310.5,
                "low": 80190.2,
                "close": 80285.4,
                "volume": 1234.56,
            },
            {
                "time": 1767142800000,
                "open": 80285.4,
                "high": 80400.0,
                "low": 80270.1,
                "close": 80372.96,
                "volume": 987.65,
            },
        ],
        "count": 2,
        "oldest_time": 1767139200000,
        "newest_time": 1767142800000,
        "has_more": True,
        "next_before": 1767139200000,
    },
    "price": {
        "symbol": "BTCUSDT",
        "price": 80248.55,
        "change_24h": -1.12,
        "high_24h": 81200.0,
        "low_24h": 79900.0,
        "volume_24h": 5250000000.0,
        "timestamp": "2026-01-02T12:00:00",
    },
    "symbols": {
        "market": "crypto",
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "count": 774,
        "timestamp": "2026-01-02T12:00:00",
    },
    "ws_live_kline": {
        "type": "kline",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "kline": {
            "time": 1767146400000,
            "open": 80372.96,
            "high": 80380.0,
            "low": 80360.1,
            "close": 80375.2,
            "volume": 42.5,
            "is_closed": False,
        },
        "timestamp": "2026-01-02T12:00:05.123456",
    },
    "ws_live_closed": {
        "type": "kline_closed",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "kline": {
            "time": 1767146340000,
            "open": 80360.0,
            "high": 80385.0,
            "low": 80355.5,
            "close": 80372.96,
            "volume": 130.2,
            "is_closed": True,
        },
        "timestamp": "2026-01-02T12:00:00.001",
    },
}

_WS_PROTOCOL = {
    "title": "بروتوكول البث الحي (WebSocket)",
    "recommended": {
        "url": "ws://localhost:8000/api/v1/market/ws/live/{market}/{symbol}?timeframe=1m",
        "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
        "messages_server_to_client": [
            {
                "type": "connection_established",
                "desc": "رسالة ترحيب عند القبول",
            },
            {"type": "kline", "desc": "تحديث الشمعة الحية كل تحديث سعر", "shape": _RESPONSE_EXAMPLES["ws_live_kline"]},
            {"type": "kline_closed", "desc": "إغلاق الشمعة — أضفها للتاريخ", "shape": _RESPONSE_EXAMPLES["ws_live_closed"]},
            {"type": "pong", "desc": "رد على {\"type\":\"ping\"} — أرسل ping كل 25 ثانية للإبقاء"},
        ],
        "client_to_server": [{"type": "ping"}, {"type": "pause_stream"}, {"type": "resume_stream"}],
    },
    "fallback_binance": {
        "url": "wss://stream.binance.com:9443/ws/{symbol}@kline_{timeframe}",
        "note": "مصدر الباك نفسه هو Binance — إذا فشل بث الباك لأي سبب اتصل ببث Binance مباشرة بنفس صيغة kline الرسمية",
        "binance_kline_shape": {
            "e": "kline",
            "s": "BTCUSDT",
            "k": {
                "t": 1767146400000,
                "o": "80372.96",
                "h": "80380.00",
                "l": "80360.10",
                "c": "80375.20",
                "v": "42.500",
                "x": False,
                "i": "1m",
            },
        },
    },
    "other_channels": [
        {"url": "/ws/market-overview", "desc": "نظرة عامة على السوق — قد لا يرسل بيانات في بعض البيئات؛ البديل المثبت: بث Binance !miniTicker@arr"},
        {"url": "/ws/stream/start (POST) + /ws", "desc": "بث مُدار: ابدأ ستريم ثم اتصل بـ /ws واستقبل {type: stream_data|historical_data}"},
        {"url": "/ws/filtering", "desc": "فلترة حية: أرسل أولاً {criteria, markets} → تستقبل {type: filter_result}"},
        {"url": "/ws/indicators/{symbol}", "desc": "أرسل أولاً {indicators:[...], timeframe, days} → تستقبل snapshot ثم تحديثات حية"},
        {"url": "/api/v1/market/ws/chart/{symbol}", "desc": "جلسة شارت مشتركة (delta broadcasts) عبر chart_hub"},
    ],
}

_INTEGRATION_CHECKLIST = {
    "title": "قائمة دمج الفرونت (Next.js على 3018)",
    "steps": [
        "1) next.config.ts: أضف rewrite {'/api/v1/:path*': 'http://localhost:8000/api/v1/:path*'} و {'/ws/:path*': 'http://localhost:8000/ws/:path*'} (ws:true)",
        "2) استخدم مسارات نسبية فقط في fetch — ممنوع كتابة localhost:8000 داخل كود الفرونت",
        "3) الشموع: طبّق بروتوكول الترقيم أعلاه (loadPage + subscribeVisibleLogicalRangeChange)",
        "4) البث الحي: ws://localhost:8000/api/v1/market/ws/live/crypto/BTCUSDT?timeframe=1m (أو Binance مباشرة)",
        "5) زمن التحميل الأول قد يصل عدة ثوانٍ عند cache-miss (كاش Parquet يجعله 0.6 ثانية لاحقاً) — اعرض مؤشر تحميل ولا تقطع الطلب",
        "6) timestamp يعيد أحياناً نصاً رقمياً — حوّل دائماً بـ Number(x) قبل new Date",
        "7) للاختبار السريع بدون كود: افتح http://localhost:8000/demo/chart.html",
    ],
}

_ERRORS = {
    "400": "سوق/رمز غير مدعوم أو لا توجد بيانات",
    "401": "مطلوب توكن Bearer (نقاط المستخدمين فقط)",
    "404": "لا توجد بيانات تاريخية لهذا الرمز",
    "422": "معاملات غير صالحة (validate FastAPI — راجع الرسالة)",
    "429/418": "حد معدل Binance مؤقت — أعد المحاولة بعد مهلة، الكاش المحلي يعيد آخر بيانات",
    "502": "مزود السعر لم يعد بيانات",
}

# ---------------------------------------------------------------------------
# بناء الكتالوج الديناميكي من الراوترات الفعلية
# ---------------------------------------------------------------------------
_TAG_ORDER = [
    "meta",
    "market-data",
    "websocket",
    "indicators",
    "strategies",
    "strategies1",
    "backtest",
    "backtest1",
    "filtering",
    "users",
    "settings",
    "stocks-analysis",
    "mtf",
    "core",
    "agent-docs",
]


def _iter_routes(routes, prefix: str = ""):
    """يمشي تكرارياً عبر _IncludedRouter (FastAPI ≥0.160) لجمع كل المسارات.

    في هذا الإصدار include_router لا يفرد المسارات في الأب بل يلفها بـ
    _IncludedRouter (original_router + include_context.prefix) — لذا المشي
    المباشر على app.routes يفقد كل مسارات الراوترات. هذه الدالة تفردها كلها.
    """
    for r in routes:
        if type(r).__name__ == "_IncludedRouter":
            ctx = getattr(r, "include_context", None)
            p = prefix + (getattr(ctx, "prefix", "") or "")
            orig = getattr(r, "original_router", None)
            yield from _iter_routes(getattr(orig, "routes", []) or [], p)
        else:
            yield r, prefix


def _ws_routes_from_app(app) -> List[Dict[str, Any]]:
    """كل مسارات WebSocket الحقيقية (لا تظهر في OpenAPI)."""
    out: List[Dict[str, Any]] = []
    for r, prefix in _iter_routes(app.routes):
        if type(r).__name__ == "APIWebSocketRoute":
            path = prefix + r.path
            endpoint = getattr(r, "endpoint", None)
            doc = (getattr(endpoint, "__doc__", "") or "").strip()
            out.append(
                {
                    "path": path,
                    "methods": ["WS"],
                    "summary": doc.splitlines()[0].strip() if doc else None,
                }
            )
    return out


def _catalog_from_app(app) -> List[Dict[str, Any]]:
    """يبني الكتالوج من مصدرين حقيقيين (صفر انحراف عن الكود):
      1) app.openapi() — كل نقاط REST (المسارات/الوسوم/الملخصات/المعاملات)
      2) مشي تكراري — كل مسارات WebSocket
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    try:
        schema = app.openapi()
    except Exception:
        logger.exception("openapi() failed while building agent contract")
        schema = {"paths": {}}

    for path, ops in schema.get("paths", {}).items():
        for method, op in ops.items():
            if str(method).lower() not in ("get", "post", "put", "delete", "patch"):
                continue
            tag = (op.get("tags") or ["other"])[0]
            desc = op.get("description") or ""
            summary = op.get("summary") or (desc.splitlines()[0].strip() if desc else None)
            entry: Dict[str, Any] = {
                "path": path,
                "methods": [str(method).upper()],
                "summary": summary,
            }
            qps = [
                {"name": p.get("name"), "required": bool(p.get("required", False))}
                for p in op.get("parameters", [])
                if isinstance(p, dict) and p.get("in") == "query"
            ]
            if qps:
                entry["query_params"] = qps
            groups.setdefault(tag, []).append(entry)

    # WebSocket routes — تُجمع تحت وسم websocket دائماً
    for ws in _ws_routes_from_app(app):
        groups.setdefault("websocket", []).append(ws)

    ordered = []
    seen = set()
    for tag in _TAG_ORDER:
        if tag in groups:
            eps = groups[tag]
            eps.sort(key=lambda e: e["path"])
            ordered.append({"tag": tag, "endpoints": eps})
            seen.add(tag)
    for tag, eps in groups.items():
        if tag not in seen:
            eps.sort(key=lambda e: e["path"])
            ordered.append({"tag": tag, "endpoints": eps})
    return ordered


def _build_contract(app) -> Dict[str, Any]:
    try:
        version = getattr(app, "version", "unknown")
        title = getattr(app, "title", "TR Platform")
    except Exception:
        title, version = "TR Platform", "unknown"

    return {
        "readme_for": "وكيل الفرونت — اقرأ هذا الملف كاملاً قبل كتابة أي كود",
        "service": title,
        "version": version,
        "base": _BASE_INFO,
        "golden_rules": [
            "ممنوع حصر عدد الشموع — بروتوكول الترقيم أدناه يعطيك التاريخ كاملاً",
            "استخدم /api/v1/market/candles للشارت (وليس /historical الكبيرة)",
            "استخدم مسارات نسبية عبر بروكسي Next.js — لا بورتات في كود الفرونت",
            "حوّل الأزمنة الرقمية النصية بـ Number() دائماً",
            "البث الحي الأول: /api/v1/market/ws/live — البديل: Binance مباشرة",
            "كل الاستجابات JSON-آمنة (NaN/Inf تُنظف تلقائياً)",
        ],
        "pagination_protocol": _PAGINATION_PROTOCOL,
        "websocket_protocol": _WS_PROTOCOL,
        "round4_updates": {
            "title": "الجولة 4 — قيم المؤشرات الحقيقية + توحيد indicator_id + أدوات الرسم",
            "ws_message_changes": [
                "chart_initialized: data.indicators_results مفاتيحه indicator_id (لا الاسم) + data.indicators_id_map = {id: name} — والقيم حقيقية دائماً (حساب فوري عند التهيئة، لن تجد null×N بعد الآن)",
                "price_update/candle_close: indicators مفاتيحها indicator_id + حقل market_status (open/closed/pre_market/post_market) للأسهم",
                "indicator_added/indicator_updated/indicator_removed: indicators_results مفاتيحها indicator_id",
                "الإزالة تدعم indicator_id أو الاسم — وتحذف من المحفوظات دائماً (removed_from_saved في الرد)",
                "action جديد set_timeframe (أو update_timeframe القديم) — تبديل الفريم داخل نفس الاتصال، الرد timeframe_changed بالشكل نفسه",
            ],
            "rest_new_endpoints": [
                "GET/POST/DELETE /api/v1/chart/drawings/{market}/{symbol}?timeframe= — حفظ أدوات الرسم دائمًا (SQLite)",
                "POST /api/v1/indicators/apply?limit=5000 — يعيد آخر N قيمة فقط (اختياري، 0=الكل)",
                "POST /api/v1/indicators/manage/add | manage/remove | manage/update — REST fallback كامل لإدارة المؤشرات بدون WS (نفس indicator_id)",
                "GET /api/v1/indicators/values/{indicator_id}?symbol=&timeframe=&market=&limit=&from_ms=&to_ms= — إعادة مزامنة قيم مؤشر بعد انقطاع WS (من الذاكرة أو حساب كامل)",
                "GET /api/v1/market/symbols?market=crypto — قائمة رموز الكريبتو (774) كانت موجودة — استخدمها للقائمة المنسدلة",
                "GET /api/v1/stocks/symbols + /stocks/market/summary + /stocks/market/top-movers — تحمل market_status لكل الرموز",
            ],
            "timestamp_guarantee": "كل طوابع الشموع الصادرة (WS وREST) epoch-ms محاذاة الفريم تماماً — لا ميكروثانية، لا +1ms، الشمعة الحية تدمج في bucket آخر شمعة مغلقة بدل إلحاق صف بوقت مزيّف",
            "frontend_cleanup": [
                "احذف self-heal عبر /indicators/apply — القيم تصلك حقيقية في init وindicator_added",
                "احذف حلّ الاسم↔المعرف — كل المفاتيح الآن indicator_id مباشرة",
                "احذف sanitizeCandleTime — الطوابع نظيفة من المصدر",
                "استخدم market_status لإيقاف رسم الشمعة الحية عند إغلاق السوق بدل حماية ×5 فريمات",
            ],
        },
        "response_examples": _RESPONSE_EXAMPLES,
        "integration_checklist": _INTEGRATION_CHECKLIST,
        "error_codes": _ERRORS,
        "dynamic_discovery": {
            "openapi_json": "/openapi.json",
            "note": "المخطط كامل يُولد من الكود الفعلي — إن تغير شيء هنا ستجده هناك",
            "indicator_discovery": "GET /api/v1/indicators/available → قائمة المؤشرات الحية بالأسماء والفئات (لا تعتمد على قائمة ثابتة)",
        },
        "endpoint_catalog": _catalog_from_app(app),
    }


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------

def _to_markdown(contract: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# 📘 عقد الوكيل — {contract['service']} v{contract['version']}")
    lines.append("")
    lines.append("> **اقرأ أولاً:** هذا العقد يُولَّد آلياً من الكود الفعلي — لا انحراف ممكن.")
    lines.append("")
    b = contract["base"]
    lines.append("## 1) الأساسيات")
    lines.append(f"- Base URL محلي: `{b['local_base_url']}` — بادئة API: `{b['api_prefix']}`")
    lines.append(f"- مصادقة: {b['auth']['type']} — `{b['auth']['header']}` — دخول: `{b['auth']['login']}`")
    lines.append(f"- الأسواق: crypto = {b['markets']['crypto']['symbols']} رمز (Binance) / stocks = {b['markets']['stocks']['symbols']} رمز (yfinance)")
    lines.append("")
    lines.append("## 2) القواعد الذهبية")
    for i, r in enumerate(contract["golden_rules"], 1):
        lines.append(f"{i}. {r}")
    lines.append("")
    pp = contract["pagination_protocol"]
    lines.append(f"## 3) {pp['title']}")
    for r in pp["rules"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("**التسلسل:**")
    lines.append("```")
    for f in pp["flow"]:
        lines.append(f)
    lines.append("```")
    lines.append("")
    lines.append("**كود JS جاهز:**")
    lines.append("```js")
    lines.append(pp["js_pseudocode"])
    lines.append("```")
    lines.append("")
    lines.append("## 4) مثال استجابة صفحة شموع")
    lines.append("```json")
    lines.append(json.dumps(contract["response_examples"]["candles_page"], ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    ws = contract["websocket_protocol"]
    lines.append(f"## 5) {ws['title']}")
    rec = ws["recommended"]
    lines.append(f"- **القناة الموصى بها:** `{rec['url']}` — فريمات: {', '.join(rec['timeframes'])}")
    lines.append("- رسائل الخادم:")
    for m in rec["messages_server_to_client"]:
        lines.append(f"  - `{m['type']}` — {m['desc']}")
    lines.append("")
    fb = ws["fallback_binance"]
    lines.append(f"- **البديل الاحتياطي:** `{fb['url']}` — {fb['note']}")
    lines.append("")
    for ch in ws["other_channels"]:
        lines.append(f"- قناة أخرى: `{ch['url']}` — {ch['desc']}")
    lines.append("")
    lines.append("## 6) قائمة الدمج")
    for s in contract["integration_checklist"]["steps"]:
        lines.append(f"- {s}")
    lines.append("")
    lines.append("## 7) رموز الأخطاء")
    for code, meaning in contract["error_codes"].items():
        lines.append(f"- `{code}` — {meaning}")
    lines.append("")
    lines.append("## 8) كتالوج نقاط النهاية (مولّد من الكود)")
    for group in contract["endpoint_catalog"]:
        lines.append("")
        lines.append(f"### 🏷️ {group['tag']} ({len(group['endpoints'])})")
        lines.append("")
        lines.append("| الطريقة | المسار | الوصف |")
        lines.append("|---|---|---|")
        for e in group["endpoints"]:
            m = "/".join(e["methods"])
            s = (e.get("summary") or "").replace("|", "\\|")
            lines.append(f"| `{m}` | `{e['path']}` | {s} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML page (RTL, dark)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>دليل وكيل الفرونت — TR Platform</title>
<style>
  :root { --bg:#0d1117; --card:#161b22; --line:#30363d; --txt:#e6edf3; --dim:#8b949e; --acc:#3fb950; --warn:#d29922; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt); font-family:"Segoe UI",Tahoma,sans-serif; line-height:1.7; }
  .wrap { max-width:1080px; margin:0 auto; padding:24px 16px 80px; }
  h1 { font-size:1.7rem; border-bottom:2px solid var(--acc); padding-bottom:10px; }
  h2 { font-size:1.25rem; color:var(--acc); margin-top:2.2rem; border-right:4px solid var(--acc); padding-right:10px; }
  a { color:#58a6ff; }
  code, pre { font-family:Consolas,Menlo,monospace; direction:ltr; text-align:left; }
  code { background:#21262d; padding:2px 6px; border-radius:6px; font-size:.9em; }
  pre { background:#0a0d12; border:1px solid var(--line); border-radius:10px; padding:14px; overflow-x:auto; font-size:.85rem; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 20px; margin:14px 0; }
  .pill { display:inline-block; background:#1f6feb33; border:1px solid #1f6feb; color:#79c0ff; border-radius:999px; padding:2px 12px; font-size:.8rem; margin:2px; }
  .warn { background:#d2992214; border:1px solid var(--warn); border-radius:10px; padding:10px 14px; }
  table { width:100%; border-collapse:collapse; margin:10px 0; font-size:.9rem; }
  th,td { border:1px solid var(--line); padding:8px 10px; text-align:right; }
  th { background:#21262d; }
  .muted { color:var(--dim); font-size:.85rem; }
</style>
</head>
<body>
<div class="wrap">
<h1>🤖 دليل وكيل الفرونت — TR Platform Backend</h1>
<p class="muted">هذه الصفحة تُولَّد من الكود الفعلي — انسخ روابطها ومرّرها للوكيل، ستجد كل شيء بدون غموض.</p>

<div class="card">
<h2 style="margin-top:0">📚 المصادر الثلاثة</h2>
<ul>
<li><b>العقد الآلي (JSON):</b> <code>GET /agent/contract.json</code> — كتالوج كل نقطة + بروتوكولات + أمثلة — <a href="/agent/contract.json">افتح</a></li>
<li><b>Markdown:</b> <code>GET /agent/contract.md</code> — <a href="/agent/contract.md">افتح</a></li>
<li><b>OpenAPI (Swagger):</b> <code>/docs</code> و <code>/openapi.json</code> — <a href="/docs">افتح</a></li>
</ul>
</div>

<div class="card">
<h2 style="margin-top:0">⚡ الشارت في 30 ثانية</h2>
<pre>GET /api/v1/market/candles/crypto/BTCUSDT?timeframe=1h&amp;limit=2000
GET /api/v1/market/candles/crypto/BTCUSDT?timeframe=1h&amp;limit=2000&amp;before=&lt;next_before&gt;
WS  /api/v1/market/ws/live/crypto/BTCUSDT?timeframe=1m</pre>
<p>→ صفحة 2000 شمعة + <code>has_more</code>/<code>next_before</code> للتمرير اللانهائي بلا أي حد إجمالي + بث kline حي.</p>
</div>

<div class="card">
<h2 style="margin-top:0">🌐 الروابط الحية الآن</h2>
<p><span class="pill">crypto: 774 رمز</span><span class="pill">stocks: 5,222 رمز</span><span class="pill">JWT Bearer للمستخدمين فقط</span></p>
<p class="muted">الديمو الجاهز: <a href="/demo/chart.html">/demo/chart.html</a> — شارت TradingView كامل بدون كتابة كود.</p>
</div>

<div class="warn">
⚠️ القاعدة الأهم: <b>ممنوع حصر الشموع بعدد ثابت</b>. طبّق بروتوكول <code>before</code>/التمرير، وحوّل الأزمنة النصية بـ <code>Number()</code> قبل <code>new Date</code>.
</div>

<p class="muted">TR Platform — تُولَّد آلياً من app/routers/agent_docs.py</p>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/agent/contract.json", summary="العقد الآلي الكامل لوكيل الفرونت (JSON)")
async def agent_contract_json(request: Request):
    """عقد شامل يُبنى من الراوترات الفعلية: كتالوج + بروتوكولات + أمثلة — اقرأه أولاً."""
    contract = _build_contract(request.app)
    return JSONResponse(content=contract)


@router.get("/agent/contract.md", summary="نفس العقد بصيغة Markdown خام")
async def agent_contract_md(request: Request):
    """نسخة Markdown من العقد — مناسبة للقراءة البرمجية أو للصق في أدلة الوكلاء."""
    contract = _build_contract(request.app)
    md = _to_markdown(contract)
    return Response(content=md, media_type="text/markdown; charset=utf-8")


@router.get("/agent", summary="صفحة دليل الوكيل (HTML عربي RTL)", include_in_schema=True)
async def agent_docs_page():
    """صفحة HTML تشرح لوكيل الفرونت كل ما يحتاجه مع روابط العقد والديمو."""
    return HTMLResponse(content=_HTML_TEMPLATE)
