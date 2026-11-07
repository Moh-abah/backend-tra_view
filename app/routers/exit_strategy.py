"""راوتر استراتيجية الخروج — ROUND40.1 (Exit-Engine API).

ست نقاط نهاية تحت /api/v1/exit-strategy — كلها بلا قاعدة بيانات
(DataService بوضع stateless — نفس مسار websocket) وبلا أي تأثير على
المسارات القائمة:

  GET  /health     — هوية المحرك والجولة والاستراتيجيات المدعومة.
  GET  /defaults   — الإعدادات الافتراضية + مخطط كل حقل (نوع/نطاق/خطوة/
                     خيارات + تسمية ووصف عربي) — جاهز لبناء نموذج الواجهة.
  GET  /presets    — الإعدادات الجاهزة (الخطة الحرفية / الموصى بها) —
                     أزرار ضغطة واحدة في الواجهة (جديد 40.1).
  POST /validate   — التحقق من إعدادات معدلة (يرد normalized أو أخطاء عربية).
  POST /describe   — وصف عربي بشري للإعدادات (لعرضه في الواجهة).
  POST /backtest   — الباك-تست الكامل: جلب شموع حقيقية → تشغيل استراتيجية
                     البطل (zzfib | zzfib_e2e | zzfib_e2e_trendy) → استخراج
                     إشارات الدخول وأرضيات الفيبو → محرك الخروج → تقرير
                     صفقات كامل بملخص ومنحنى رأس المال.

الاستقلالية: هذا الراوتر لا يعدّل أي ملف آخر — المحركات تُستدعى كما هي
(بما فيها إعداداتها الخاصة عبر strategy_params)، ومحرك الخروج يعمل فوق
مخرجاتها فقط. إضافةً صرفة بلا أي تغيير سلوكي على الجولات السابقة.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.data_service import DataService
from app.services.exit_engine import (
    EXIT_CONFIG_DEFAULTS,
    EXIT_CONFIG_SCHEMA,
    EXIT_ENGINE_NAME,
    EXIT_ENGINE_PRESETS,
    EXIT_ENGINE_SPEC,
    describe_exit_config,
    extract_entries_for_strategy,
    normalize_exit_config,
    run_exit_backtest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["exit-strategy"])

ROUND = 40.1

# ---------------------------------------------------------------------------
# الثوابت والتحقق
# ---------------------------------------------------------------------------
_STRATEGIES = ("zzfib", "zzfib_e2e", "zzfib_e2e_trendy")

_TIMEFRAME_RE_OK = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"}

_MARKET_MAP = {"crypto": "crypto", "stocks": "stocks", "us": "stocks"}

_DEFAULT_STRATEGY_PARAMS: Dict[str, Dict[str, Any]] = {
    # ✅ نفس افتراضات البطل الحية (ROUND19/ROUND31): وضع TV الكلاسيكي + مرجع سيولة 240
    "zzfib": {"mode": "tradingview", "length": 100, "depth": 12, "deviation": 20.0,
              "backstep": 3, "liq_lookback": 240},
    # ✅ e2e/ترندية: مواصفة luxalgo التعاقدية — length=100 (عقد الجولات 34+)
    "zzfib_e2e": {"length": 100},
    "zzfib_e2e_trendy": {"length": 100},
}

_STRATEGY_PARAMS_ALLOWED: Dict[str, set] = {
    "zzfib": {"mode", "length", "reverse", "extend_right", "extend_leg_to_live",
              "touch_level", "liq_lookback", "liq_signals", "liq_sfp_signals",
              "depth", "deviation", "backstep"},
    "zzfib_e2e": {"length", "reverse", "extend_right", "extend_leg_to_live",
                  "mode", "depth", "deviation", "backstep", "launch_touch_ticks"},
    "zzfib_e2e_trendy": {"length", "reverse", "extend_right", "extend_leg_to_live",
                         "mode", "depth", "deviation", "backstep", "launch_touch_ticks",
                         "trend_periods", "trend_confirm", "trend_gate"},
}


def _validate_request(symbol: str, timeframe: str, market: str, days: int,
                      limit: Optional[int], strategy: str,
                      strategy_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """تحقق موحد برسائل عربية واضحة — يستخدمه /backtest."""
    errors: List[str] = []
    sym = (symbol or "").strip().upper()
    if not sym or not sym.isalnum() or not (2 <= len(sym) <= 20):
        errors.append(f"رمز غير صالح: {symbol!r} — مثال صحيح: BTCUSDT")
    if timeframe not in _TIMEFRAME_RE_OK:
        errors.append(f"فريم غير مدعوم: {timeframe!r} — المدعوم: {sorted(_TIMEFRAME_RE_OK)}")
    mk = (market or "crypto").strip().lower()
    if mk not in _MARKET_MAP:
        errors.append(f"سوق غير مدعوم: {market!r} — المدعوم: crypto | stocks")
    if not (1 <= days <= 365):
        errors.append(f"days خارج النطاق [1..365]: {days}")
    if limit is not None and not (10 <= limit <= 20000):
        errors.append(f"limit خارج النطاق [10..20000]: {limit}")
    st = (strategy or "").strip().lower()
    if st not in _STRATEGIES:
        errors.append(f"استراتيجية غير مدعومة: {strategy!r} — المدعومة: {_STRATEGIES}")
    sp = dict(_DEFAULT_STRATEGY_PARAMS.get(st) or {})
    if strategy_params:
        if not isinstance(strategy_params, dict):
            errors.append("strategy_params يجب أن تكون كائن JSON")
        else:
            allowed = _STRATEGY_PARAMS_ALLOWED.get(st, set())
            for k in strategy_params:
                if k not in allowed:
                    errors.append(
                        f"معامل غير مسموح لاستراتيجية {st}: '{k}' — المسموحة: {sorted(allowed)}"
                    )
            sp.update({k: v for k, v in strategy_params.items() if k in allowed})
            # تحقق قيمة mode (المحركات تتساهل معها بصمت — نمنع المفاجآت هنا)
            if "mode" in sp and str(sp["mode"]) not in ("tradingview", "luxalgo"):
                errors.append(
                    f"mode غير صالح: {sp['mode']!r} — المسموح: 'tradingview' أو 'luxalgo'"
                )
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors, "round": ROUND})
    return {"symbol": sym, "timeframe": timeframe, "market": _MARKET_MAP[mk],
            "days": days, "limit": limit, "strategy": st, "strategy_params": sp}


def _run_strategy(strategy: str, candles: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """يشغّل محرك استراتيجية البطل المطلوب على الشموع (كما هي — بلا تعديل)."""
    if strategy == "zzfib":
        from app.services.indicators.overlays import zigzag_fib
        return zigzag_fib(candles, **params)
    if strategy == "zzfib_e2e":
        from app.services.indicators.overlays_zlf_e2e import zigzag_fib_e2e
        return zigzag_fib_e2e(candles, **params)
    if strategy == "zzfib_e2e_trendy":
        from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy
        return zigzag_fib_e2e_trendy(candles, **params)
    raise ValueError(f"استراتيجية غير مدعومة: {strategy!r}")


def _df_to_candles(df: Any) -> List[Dict[str, Any]]:
    """DataFrame المزوّد (time/open/high/low/close/volume) → list[dict] للمحرك."""
    if df is None or getattr(df, "empty", True):
        return []
    cols = {str(c).lower(): c for c in df.columns}
    tcol = cols.get("time") or cols.get("timestamp") or cols.get("open_time") or cols.get("date")
    out: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        item: Dict[str, Any] = {
            "open": float(row[cols["open"]]),
            "high": float(row[cols["high"]]),
            "low": float(row[cols["low"]]),
            "close": float(row[cols["close"]]),
        }
        if "volume" in cols:
            item["volume"] = float(row[cols["volume"]])
        if tcol is not None:
            item["time"] = int(row[tcol])
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# كاش صغير (نفس نمط overlays — TTL 60 ثانية، 32 طلباً)
# ---------------------------------------------------------------------------
_BT_CACHE_MAX = 32
_BT_TTL_SECONDS = 60.0
_bt_cache: Dict[str, tuple] = {}


def _bt_cache_get(key: str) -> Optional[Dict[str, Any]]:
    hit = _bt_cache.get(key)
    if not hit:
        return None
    ts, payload = hit
    if time.time() - ts > _BT_TTL_SECONDS:
        _bt_cache.pop(key, None)
        return None
    out = dict(payload)
    out["cache"] = "hit"
    return out


def _bt_cache_put(key: str, payload: Dict[str, Any]) -> None:
    if len(_bt_cache) >= _BT_CACHE_MAX:
        oldest = min(_bt_cache, key=lambda k: _bt_cache[k][0])
        _bt_cache.pop(oldest, None)
    _bt_cache[key] = (time.time(), dict(payload))


# ---------------------------------------------------------------------------
# نماذج الطلبات
# ---------------------------------------------------------------------------
class ValidateRequest(BaseModel):
    config: Dict[str, Any] = Field(default_factory=dict, description="إعدادات الخروج المعدلة")


class DescribeRequest(BaseModel):
    config: Optional[Dict[str, Any]] = Field(default=None, description="أرسل {} أو {} للوصف الافتراضي")


class ExitBacktestRequest(BaseModel):
    symbol: str = Field(..., examples=["BTCUSDT"], description="الرمز مثل BTCUSDT")
    timeframe: str = Field("15m", description="فريم الشموع")
    market: str = Field("crypto", description="crypto | stocks")
    days: int = Field(30, description="كم يوماً من التاريخ تُجلب")
    limit: Optional[int] = Field(None, description="قص الشموع لآخر N شمعة بعد الجلب")
    strategy: str = Field("zzfib_e2e", description="zzfib | zzfib_e2e | zzfib_e2e_trendy")
    config: Optional[Dict[str, Any]] = Field(None, description="إعدادات محرك الخروج (اختياري)")
    strategy_params: Optional[Dict[str, Any]] = Field(None, description="معاملات محرك الاستراتيجية نفسها (اختياري)")


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@router.get("/health")
async def exit_strategy_health():
    return {
        "status": "ok",
        "router": "exit-strategy",
        "round": ROUND,
        "engine": {"name": EXIT_ENGINE_NAME, "spec": EXIT_ENGINE_SPEC},
        "strategies": list(_STRATEGIES),
        "endpoints": [
            "GET  /api/v1/exit-strategy/health",
            "GET  /api/v1/exit-strategy/defaults",
            "GET  /api/v1/exit-strategy/presets",
            "POST /api/v1/exit-strategy/validate",
            "POST /api/v1/exit-strategy/describe",
            "POST /api/v1/exit-strategy/backtest",
        ],
        "cache": {"max_entries": _BT_CACHE_MAX, "ttl_seconds": _BT_TTL_SECONDS, "entries": len(_bt_cache)},
    }


# ---------------------------------------------------------------------------
# GET /defaults — الإعدادات + المخطط الكامل لبناء نموذج الواجهة
# ---------------------------------------------------------------------------
@router.get("/defaults")
async def exit_strategy_defaults():
    return {
        "round": ROUND,
        "engine": {"name": EXIT_ENGINE_NAME, "spec": EXIT_ENGINE_SPEC},
        "config_defaults": EXIT_CONFIG_DEFAULTS,
        "config_schema": EXIT_CONFIG_SCHEMA,
        "strategies": {
            "supported": list(_STRATEGIES),
            "default_strategy_params": _DEFAULT_STRATEGY_PARAMS,
            "allowed_strategy_params": {k: sorted(v) for k, v in _STRATEGY_PARAMS_ALLOWED.items()},
        },
        "exit_reasons": {
            "take_profit": "لمس هدف جني الربح — إغلاق كامل بربح",
            "trail_stop": "تراجع من القمة بعد تفعيل الجني المتحرك — إغلاق كامل (اختياري، معطّل افتراضياً)",
            "fib_break": "إغلاق شمعة تحت أدنى مستوى فيبوناتشي (0 أو 1) — إغلاق كامل",
            "end_of_data": "الصفقة ما زالت مفتوحة عند نهاية البيانات — تقييم بالشمعة الأخيرة",
        },
        "presets": [
            {"name": p["name"], "label_ar": p["label_ar"]} for p in EXIT_ENGINE_PRESETS
        ],
        "notes": [
            "هذه الاستراتيجية بلا وقف خسارة نسبي — الوقف الوحيد هو كسر أرضية الفيبو.",
            "كل الحقول قابلة للتعديل من الواجهة — أرسل ما تعدّله فقط في /backtest وسيُكمل الباقي بالافتراضات.",
            "حقول ROUND40.1 (مرشحات الدخول والجني المتحرك) معطّلة افتراضياً — سلوك الخطة الحرفية هو الافتراضي.",
        ],
    }


# ---------------------------------------------------------------------------
# GET /presets — الإعدادات الجاهزة (أزرار ضغطة واحدة في الواجهة)
# ---------------------------------------------------------------------------
@router.get("/presets")
async def exit_strategy_presets():
    return {
        "round": ROUND,
        "presets": EXIT_ENGINE_PRESETS,
        "usage": (
            "اختر preset من الواجهة ثم أرسل قيم config الخاصة به كما هي في /backtest — "
            "أو اعرضها في النموذج ليعدّلها المستخدم قبل التشغيل."
        ),
    }


# ---------------------------------------------------------------------------
# POST /validate — فحص الإعدادات المعدلة قبل التشغيل
# ---------------------------------------------------------------------------
@router.post("/validate")
async def exit_strategy_validate(req: ValidateRequest):
    cfg, errors = normalize_exit_config(req.config)
    if errors:
        return {"valid": False, "round": ROUND, "errors": errors}
    warnings: List[str] = []
    if cfg["max_entries"] == 1:
        warnings.append("max_entries=1 — التعزيزات معطلة: الصفقة مركز واحد فقط.")
    if cfg["dca1_trigger_pct"] > 0 and cfg["dca2_trigger_pct"] == 0 and cfg["max_entries"] >= 3:
        warnings.append("dca2_trigger_pct=0 — التعزيز الثاني معطل بينما الأول مفعّل.")
    if cfg["fees_pct"] == 0:
        warnings.append("fees_pct=0 — النتائج صافية بلا عمولات (الواقع عادة 0.1 لكل عملية).")
    if cfg["tp_trail_arm_pct"] > 0 and cfg["tp_trail_arm_pct"] < cfg["take_profit_pct"]:
        warnings.append(
            f"الجني المتحرك مفعّل (تفعيل عند {cfg['tp_trail_arm_pct']:g}٪) — بعد التفعيل يُلغى الهدف الثابت "
            f"({cfg['take_profit_pct']:g}٪) ويتولى التتبع الإغلاق عند تراجع {cfg['tp_trail_giveback_pct']:g}٪ من القمة."
        )
    if cfg["trend_filter_sma_bars"] > 0:
        warnings.append(
            f"فلتر الاتجاه مفعّل: أي إشارة في أول {cfg['trend_filter_sma_bars']} شمعة من النافذة تُرفض "
            f"تلقائياً (تاريخ غير كافٍ لحساب المتوسط)."
        )
    return {"valid": True, "round": ROUND, "config": cfg, "warnings": warnings}


# ---------------------------------------------------------------------------
# POST /describe — وصف عربي بشري للإعدادات
# ---------------------------------------------------------------------------
@router.post("/describe")
async def exit_strategy_describe(req: DescribeRequest):
    cfg, errors = normalize_exit_config(req.config or {})
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors, "round": ROUND})
    return {
        "round": ROUND,
        "config": cfg,
        "description_ar": describe_exit_config(cfg),
    }


# ---------------------------------------------------------------------------
# POST /backtest — الباك-تست الكامل
# ---------------------------------------------------------------------------
@router.post("/backtest")
async def exit_strategy_backtest(req: ExitBacktestRequest):
    validated = _validate_request(
        req.symbol, req.timeframe, req.market, req.days, req.limit,
        req.strategy, req.strategy_params,
    )
    symbol = validated["symbol"]
    timeframe = validated["timeframe"]
    market = validated["market"]
    strategy = validated["strategy"]
    strategy_params = validated["strategy_params"]

    # الكاش — نفس الطلب يعيد نفس النتيجة خلال 60 ثانية
    cache_key_src = json.dumps(
        ["POST-exit-backtest", symbol, timeframe, market, req.days, req.limit,
         strategy, strategy_params, req.config or {}],
        sort_keys=True, default=str,
    )
    cache_key = hashlib.md5(cache_key_src.encode()).hexdigest()
    cached = _bt_cache_get(cache_key)
    if cached is not None:
        return cached

    cfg, cfg_errors = normalize_exit_config(req.config)
    if cfg_errors:
        raise HTTPException(status_code=422, detail={"errors": cfg_errors, "round": ROUND})

    # 1) جلب الشموع الحقيقية (stateless — بلا DB)
    data_service = DataService(None)
    t0 = time.perf_counter()
    try:
        dataframe = await data_service.get_historical(
            symbol=symbol, timeframe=timeframe, market=market, days=req.days
        )
    except Exception as exc:
        logger.exception("exit-strategy: فشل جلب الشموع لـ %s", symbol)
        raise HTTPException(status_code=502, detail=f"فشل جلب الشموع من المزود: {exc}")

    if dataframe is None or getattr(dataframe, "empty", True):
        raise HTTPException(
            status_code=404,
            detail=f"لا توجد شموع للرمز {symbol} على فريم {timeframe} ({req.days} يوماً)",
        )
    candles = _df_to_candles(dataframe)
    if req.limit is not None and len(candles) > req.limit:
        candles = candles[-req.limit:]

    # 2) تشغيل محرك استراتيجية البطل (كما هي — بلا أي تعديل)
    try:
        strategy_payload = _run_strategy(strategy, candles, strategy_params)
    except TypeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"errors": [f"معاملات غير صالحة لاستراتيجية {strategy}: {exc}"], "round": ROUND},
        )
    except Exception as exc:
        logger.exception("exit-strategy: فشل تشغيل الاستراتيجية %s", strategy)
        raise HTTPException(status_code=500, detail=f"فشل تشغيل محرك الاستراتيجية: {exc}")

    # 3) استخراج إشارات الدخول + أرضيات الفيبو (المُهايئ)
    try:
        entries = extract_entries_for_strategy(strategy, strategy_payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"errors": [str(exc)], "round": ROUND})

    # 4) محرك الخروج
    exit_result = run_exit_backtest(candles, entries, cfg)

    # 5) التجميع والرد
    sig_stats = {
        "strategy_signals_total": len(strategy_payload.get("signals") or []),
        "buy_entries_extracted": len(entries),
        "ranges": len(strategy_payload.get("ranges") or []),
        "pivots": len(strategy_payload.get("pivots") or []),
    }
    response = {
        "ok": True,
        "round": ROUND,
        "cache": "miss",
        "symbol": symbol,
        "timeframe": timeframe,
        "market": market,
        "strategy": strategy,
        "strategy_params": strategy_params,
        "strategy_stats": sig_stats,
        "window": exit_result["window"],
        "last_close": candles[-1]["close"] if candles else None,
        "exit_config": exit_result["config"],
        "engine": exit_result["engine"],
        "trades": exit_result["trades"],
        "summary": exit_result["summary"],
        "notes": exit_result.get("notes", []),
        "took_ms": int((time.perf_counter() - t0) * 1000),
    }
    _bt_cache_put(cache_key, response)
    return response
