"""Unified-Backtest — طبقة العرض الموحدة (ROUND42).

الغرض التعاقدي: جعل POST /api/v1/backtest1/run هو البوابة الوحيدة لكل
تشغيل — بما فيه استراتيجية الخروج (الجني المتحرك/التريلينق، جني الربح،
تعزيزات DCA، كسر الفيبو). هذه الوحدة هي الجسر النقي بين:

  • محرك استراتيجية البطل (zzfib / zzfib_e2e / zzfib_e2e_trendy)
      → إشارات الدخول + أرضيات الفيبو
  • محرك الخروج الج41 (Exit-Engine: ROUND41-hero-exit-trailing)
      → إدارة الصفقة كاملة (دخول/تعزيز/خروج)
  • عقد نتائج backtest1 نفسه (summary + chart_data)
      → نفس الحقول التي يقرؤها الفرونت اليوم، بلا أي مسار موازٍ.

التصميم: دوال نقية 100% — لا قواعد بيانات ولا HTTP ولا مزوّدي بيانات.
مدخلها (شموع + استراتيجية + إعدادات خروج منظمة) ومخرجها مستندان
جاهزان للتخزين في BacktestRun مثلها مثل نتائج المحرك الرئيسي تماماً.

======================================================================
 عقد الاستدعاء (ROUND42)
======================================================================
 الحمولة إلى POST /api/v1/backtest1/run تبقى BacktestConfig كما هي
 حرفياً (توافق بت-بت عند غياب exit_strategy)، مع حقل اختياري واحد جديد:

    "exit_strategy": {
        "strategy": "zzfib_e2e",              # اختياري — يُشتق من
                                               # strategy_config.name وإلا zzfib
        "strategy_params": {"length": 100},   # اختياري — افتراضات البطل
        "config": {                           # اختياري — عقد ج41 كاملاً
            "use_trailing": true,
            "trailing_giveback_pct": 20.0,
            "take_profit_pct": 5.0,
            ...
        }
    }

 عند وجود exit_strategy يُنفَّذ الطلب بالمحرك الموحد (هذه الوحدة) وتعود
 النتيجة من نفس /status/{task_id} → /get/{backtest_id} بلا أي فرق شكلي.

======================================================================
 مقاييس الجولة 42 — الصيغ (موثقة أيضاً داخل math_audit في كل رد)
======================================================================
 المصفوفة الأساسية هي عوائد الصفقات المغلقة r_i = pnl_pct/100:
   • mean_r / std_r (عينة) / downside (انحرار العوائد السالبة فقط)
   • window_days = مدة النافذة بالأيام من الشموع نفسها
   • trades_per_year = n_closed ÷ (window_days/365)
   • sharpe      = (mean_r ÷ std_r) × √trades_per_year
   • sortino     = (mean_r ÷ downside) × √trades_per_year
   • volatility  = std_r × √trades_per_year × 100
   • annual_ret  = total_pnl_percent × (365 ÷ window_days)
   • max_dd      = أقصى هبوط من منحنى رأس المال (نقطة لكل شمعة)
   • calmar      = annual_ret ÷ max_dd
   • var95/cvar95 = المئين الخامس من {r_i} ومتوسط ما تحته
   • sqn         = √n × mean_r ÷ std_r
   • kelly       = W − (1−W)÷R  حيث R = متوسط الربح٪ ÷ |متوسط الخسارة٪|
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# الهوية
# ---------------------------------------------------------------------------
UNIFIED_ENGINE_NAME = "Unified-Backtest"
UNIFIED_ENGINE_SPEC = "ROUND42-unified-backtest1"
UNIFIED_ROUND = 42

# ---------------------------------------------------------------------------
# تحقق واحد مشترك (يستخدمه مخطط BacktestConfig والمنفذ معاً — مصدر واحد)
# ---------------------------------------------------------------------------
def validate_exit_block(
    strategy: Optional[str],
    strategy_params: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """تحقق كامل لكتلة exit_strategy — يعيد (exit_config_المنظم, أخطاء).

    نفس قواعد راوتر محرك الخروج حرفياً (استراتيجيات البطل الثلاث،
    معاملاتها المسموحة، وعقد ج41 للإعدادات) — مصدر تحقق واحد داخل
    backtest1/run: الخطأ يُرفض 422 فوراً في نفس الطلب، لا فشل صامت
    بعد dispatch.
    """
    # استيراد مؤجَّل — نفس نمط المشروع (لا دورات استيراد عند الإقلاع)
    from app.routers.exit_strategy import (
        _DEFAULT_STRATEGY_PARAMS,
        _STRATEGIES,
        _STRATEGY_PARAMS_ALLOWED,
    )
    from app.services.exit_engine import normalize_exit_config

    errors: List[str] = []

    st: Optional[str] = None
    if strategy is not None:
        st = str(strategy).strip().lower()
        if st not in _STRATEGIES:
            errors.append(f"exit_strategy.strategy غير مدعومة: {strategy!r} — المدعومة: {_STRATEGIES}")

    sp: Dict[str, Any] = {}
    if strategy_params is not None:
        if not isinstance(strategy_params, dict):
            errors.append("exit_strategy.strategy_params يجب أن تكون كائن JSON")
        else:
            allowed = _STRATEGY_PARAMS_ALLOWED.get(st or "", set())
            for k in strategy_params:
                if st is not None and k not in allowed:
                    errors.append(
                        f"معامل غير مسموح لاستراتيجية {st}: '{k}' — المسموحة: {sorted(allowed)}"
                    )
            sp = dict(strategy_params)

    cfg, cfg_errors = normalize_exit_config(config)
    errors.extend(cfg_errors)

    normalized: Optional[Dict[str, Any]] = None
    if not errors:
        normalized = {
            "strategy": st,
            "strategy_params": sp,
            "config": cfg,
        }
    return normalized, errors


# ---------------------------------------------------------------------------
# المنفذ النقي
# ---------------------------------------------------------------------------
def run_unified_exit_backtest(
    candles: List[Dict[str, Any]],
    strategy: str,
    strategy_params: Dict[str, Any],
    exit_cfg: Dict[str, Any],
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    """تنفيذ التشغيل الموحد كاملاً على شموع جاهزة وإنتاج مستندي
    (summary + chart_data) بنفس عقد backtest1/get — نقية 100%.

    المعاملات:
      candles         شموع المزوّد [{time, open, high, low, close, volume}]
      strategy        zzfib | zzfib_e2e | zzfib_e2e_trendy
      strategy_params معاملات الاستراتيجية (تُدمج فوق افتراضات البطل)
      exit_cfg        إعدادات الخروج المنظمة (من normalize_exit_config)
      meta            {symbol, timeframe, market, initial_capital, timezone,
                       tz_offset_minutes, name}
    """
    from app.routers.exit_strategy import (
        _DEFAULT_STRATEGY_PARAMS,
        _STRATEGIES,
        _STRATEGY_PARAMS_ALLOWED,
        _run_strategy,
    )
    from app.services.exit_engine import (
        EXIT_ENGINE_NAME,
        EXIT_ENGINE_SPEC,
        describe_exit_config,
        extract_entries_for_strategy,
        run_exit_backtest,
    )

    t0 = time.perf_counter()
    symbol = str(meta.get("symbol") or "?")
    timeframe = str(meta.get("timeframe") or "?")
    market = str(meta.get("market") or "crypto")
    initial_capital = float(meta.get("initial_capital") or 10000.0)

    st = str(strategy or "zzfib").strip().lower()
    if st not in _STRATEGIES:
        raise ValueError(f"استراتيجية غير مدعومة: {strategy!r} — المدعومة: {_STRATEGIES}")

    # 1) معاملات الاستراتيجية: افتراضات البطل + ما أرسله المستخدم (المسموح فقط)
    params: Dict[str, Any] = dict(_DEFAULT_STRATEGY_PARAMS.get(st) or {})
    allowed = _STRATEGY_PARAMS_ALLOWED.get(st, set())
    params.update({k: v for k, v in (strategy_params or {}).items() if k in allowed})

    # 2) استراتيجية البطل — إشارات الدخول + أرضيات الفيبو
    strategy_payload = _run_strategy(st, candles, params)

    # 3) محرك الخروج الج41 — إدارة الصفقة كاملة
    entries = extract_entries_for_strategy(st, strategy_payload)
    exit_result = run_exit_backtest(candles, entries, exit_cfg)
    trades = exit_result["trades"]
    exsum = exit_result["summary"]
    notes: List[str] = list(exit_result.get("notes") or [])

    # 4) المقاييس القياسية + chart_data (منحنى رأس المال يُحسب مرة واحدة ويُشارك)
    metrics = _standard_metrics(candles, trades, initial_capital)
    chart_data = _build_chart_data(
        candles, trades, exit_cfg, symbol, strategy_payload, st,
        initial_capital=initial_capital,
        equity_curve=metrics["_equity_curve"],
    )
    took_ms = int((time.perf_counter() - t0) * 1000)

    closed = [tr for tr in trades if not tr["was_open_at_end"]]
    realized = float(exsum["pnl"]["realized_usd"])
    unrealized = float(exsum["pnl"]["unrealized_usd_open_at_end"])
    total_pnl = realized + unrealized

    # 5) التشكيل الفعّال لاستراتيجية الخروج — يُعاد للفرونت ليمثّله على الشاشة
    trailing_on = bool(exit_cfg["use_trailing"]) and exit_cfg["trailing_giveback_pct"] > 0
    exit_strategy_view: Dict[str, Any] = {
        "strategy": st,
        "strategy_params": params,
        "config_effective": dict(exit_cfg),
        "description_ar": describe_exit_config(exit_cfg),
        "trailing": {
            "active": trailing_on,
            "giveback_pct": float(exit_cfg["trailing_giveback_pct"]) if trailing_on else None,
            "cancelled_take_profit": trailing_on,
            "cancelled_fib_stop": trailing_on,
        },
        "take_profit": {
            "active": not trailing_on,
            "pct": None if trailing_on else float(exit_cfg["take_profit_pct"]),
            "reference": exit_cfg["tp_reference"],
        },
        "dca": {
            "max_entries": int(exit_cfg["max_entries"]),
            "dca1_trigger_pct": float(exit_cfg["dca1_trigger_pct"]),
            "dca2_trigger_pct": float(exit_cfg["dca2_trigger_pct"]),
            "dca1_fired": int(exsum["dca_usage"]["dca1_fired"]),
            "dca2_fired": int(exsum["dca_usage"]["dca2_fired"]),
        },
        "entry_exec": exit_cfg["entry_exec"],
        "cooldown_bars": int(exit_cfg["cooldown_bars"]),
        "allow_overlap": bool(exit_cfg["allow_overlap"]),
        "fees_pct": float(exit_cfg["fees_pct"]),
    }

    summary: Dict[str, Any] = {
        # --- الحقول القياسية (نفس أسماء المحرك الرئيسي بت-بت) ---
        "name": meta.get("name"),
        "timeframe": timeframe,
        "timezone": str(meta.get("timezone") or "UTC"),
        "tz_offset_minutes": int(meta.get("tz_offset_minutes") or 0),
        "initial_capital": initial_capital,
        "final_capital": round(initial_capital + total_pnl, 6),
        "total_pnl": round(total_pnl, 6),
        "total_pnl_percent": round(total_pnl / initial_capital * 100.0, 6) if initial_capital else 0.0,
        "total_trades": int(exsum["trades_total"]),
        "winning_trades": int(exsum["wins"]),
        "losing_trades": int(exsum["losses"]),
        "win_rate": float(exsum["win_rate_pct"] or 0.0),
        "max_drawdown_percent": metrics["max_drawdown_percent"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "sortino_ratio": metrics["sortino_ratio"],
        "calmar_ratio": metrics["calmar_ratio"],
        "profit_factor": exsum["pnl"]["profit_factor"],
        "expectancy": metrics["expectancy_usd"],
        "annual_return_percent": metrics["annual_return_percent"],
        "volatility_annual": metrics["volatility_annual"],
        "var_95": metrics["var_95"],
        "cvar_95": metrics["cvar_95"],
        "system_quality_number": metrics["sqn"],
        "kelly_criterion": metrics["kelly"],
        "execution_time_seconds": round((time.perf_counter() - t0), 3),
        "architecture_mode": "Unified-Exit-Engine-R42",
        "fees_applied": round(float(exsum["pnl"]["total_fees_usd"]), 6),
        "fill_model": str(exit_cfg["entry_exec"]),
        "math_audit": metrics["math_audit"],
        "effective_config": dict(exit_cfg),
        # --- إضافات الجولة 42 (المصدر الموحد لاستراتيجية الخروج) ---
        "engine": {
            "name": EXIT_ENGINE_NAME,
            "spec": EXIT_ENGINE_SPEC,
            "unified_via": "POST /api/v1/backtest1/run",
            "unified_spec": UNIFIED_ENGINE_SPEC,
        },
        "symbols": [symbol],
        "exit_strategy": exit_strategy_view,
        "exit_reasons": dict(exsum["exits"]),
        "exit_summary": exsum,
        "exit_trades": trades,
        "signal_stats": {
            "strategy_signals_total": len(strategy_payload.get("signals") or []),
            "buy_entries_extracted": len(entries),
            "ranges": len(strategy_payload.get("ranges") or []),
            "pivots": len(strategy_payload.get("pivots") or []),
            **{k: int(v) for k, v in (exsum.get("entry_signals") or {}).items()},
        },
        "window": exit_result.get("window"),
        "took_ms": took_ms,
        "notes": notes,
    }

    return {"summary": summary, "chart_data": chart_data, "notes": notes}


# ---------------------------------------------------------------------------
# المقاييس القياسية — من عوائد الصفقات المغلقة
# ---------------------------------------------------------------------------
def _standard_metrics(
    candles: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    initial_capital: float,
) -> Dict[str, Any]:
    closed = [tr for tr in trades if not tr["was_open_at_end"]]

    # نافذة زمنية من الشموع نفسها
    window_days = 0.0
    if candles:
        try:
            t_first = int(candles[0].get("time") or 0)
            t_last = int(candles[-1].get("time") or 0)
            window_days = max(0.0, (t_last - t_first) / 86400000.0)
        except (TypeError, ValueError):
            window_days = 0.0

    returns = [float(tr["pnl_pct"]) / 100.0 for tr in closed]
    n = len(returns)
    mean_r = sum(returns) / n if n else 0.0
    var_r = sum((r - mean_r) ** 2 for r in returns) / (n - 1) if n > 1 else 0.0
    std_r = math.sqrt(var_r) if var_r > 0 else 0.0
    neg = [r for r in returns if r < 0]
    downside = math.sqrt(sum(r * r for r in neg) / len(neg)) if neg else 0.0

    trades_per_year = (n / (window_days / 365.0)) if window_days > 0 and n else 0.0

    def _safe_div(a: float, b: float) -> Optional[float]:
        try:
            if b == 0 or not math.isfinite(b):
                return None
            v = a / b
            return round(v, 4) if math.isfinite(v) else None
        except (ZeroDivisionError, OverflowError):
            return None

    sharpe = _safe_div(mean_r, std_r)
    sharpe = round(sharpe * math.sqrt(trades_per_year), 4) if sharpe is not None and trades_per_year > 0 else (sharpe or 0.0)
    sortino = _safe_div(mean_r, downside)
    sortino = round(sortino * math.sqrt(trades_per_year), 4) if sortino is not None and trades_per_year > 0 else (sortino or 0.0)
    sqn = _safe_div(math.sqrt(n) * mean_r, std_r) if n else None

    # منحنى رأس المال لكل شمعة → أقصى هبوط
    equity, max_dd = _equity_and_drawdown(candles, trades, initial_capital)

    total_pnl = sum(float(tr["pnl_usd"]) for tr in trades)
    total_pnl_pct = (total_pnl / initial_capital * 100.0) if initial_capital else 0.0
    annual_ret = round(total_pnl_pct * (365.0 / window_days), 4) if window_days > 0 else 0.0
    calmar = _safe_div(annual_ret, max_dd) if max_dd and max_dd > 0 else (None if max_dd == 0 else None)
    volatility = round(std_r * math.sqrt(trades_per_year) * 100.0, 4) if trades_per_year > 0 else 0.0

    # VAR/CVAR على المئين الخامس من العوائد
    var95 = cvar95 = None
    if returns:
        ordered = sorted(returns)
        k = max(1, math.ceil(0.05 * len(ordered)))
        tail = ordered[:k]
        var95 = round(tail[0] * 100.0, 4)
        cvar95 = round((sum(tail) / len(tail)) * 100.0, 4)

    # كيلي: W − (1−W)/R
    kelly = None
    if closed:
        wins = [float(tr["pnl_pct"]) for tr in closed if tr["pnl_usd"] > 0]
        losses = [abs(float(tr["pnl_pct"])) for tr in closed if tr["pnl_usd"] <= 0]
        w = len(wins) / len(closed)
        avg_w = sum(wins) / len(wins) if wins else 0.0
        avg_l = sum(losses) / len(losses) if losses else 0.0
        if avg_l > 0 and avg_w > 0:
            kelly = round(w - (1 - w) / (avg_w / avg_l), 4)

    expectancy_usd = round(sum(float(tr["pnl_usd"]) for tr in closed) / n, 6) if n else 0.0

    math_audit = {
        "round": UNIFIED_ROUND,
        "returns_basis": "pnl_pct لكل صفقة مغلقة ÷ 100",
        "window_days": round(window_days, 3),
        "closed_trades": n,
        "trades_per_year": round(trades_per_year, 4),
        "formulas": {
            "sharpe": "(mean_r ÷ std_r) × √trades_per_year",
            "sortino": "(mean_r ÷ downside_rms) × √trades_per_year",
            "volatility_annual": "std_r × √trades_per_year × 100",
            "annual_return_percent": "total_pnl_percent × (365 ÷ window_days)",
            "max_drawdown_percent": "أقصى هبوط من منحنى رأس المال (نقطة لكل شمعة)",
            "calmar": "annual_return ÷ max_drawdown",
            "var_95/cvar_95": "المئين الخامس من عوائد الصفقات ومتوسط ما تحته (%)",
            "sqn": "√n × mean_r ÷ std_r",
            "kelly": "W − (1−W) ÷ R",
            "expectancy": "متوسط pnl_usd للصفقة المغلقة",
        },
        "equity_curve_basis": "initial + realized(المغلقة حتى الشمعة) + unrealized(المفتوحة عند الإغلاق)",
    }

    return {
        "sharpe_ratio": float(sharpe or 0.0),
        "sortino_ratio": float(sortino or 0.0),
        "calmar_ratio": float(calmar) if calmar is not None else 0.0,
        "max_drawdown_percent": round(max_dd, 4),
        "annual_return_percent": annual_ret,
        "volatility_annual": volatility,
        "var_95": var95,
        "cvar_95": cvar95,
        "sqn": sqn,
        "kelly": kelly,
        "expectancy_usd": expectancy_usd,
        "math_audit": math_audit,
        "_equity_curve": equity,
    }


def _equity_and_drawdown(
    candles: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    initial_capital: float,
) -> Tuple[List[float], float]:
    """منحنى رأس المال نقطة-لكل-شمعة: initial + realized + unrealized،
    ثم أقصى هبوط منه (نفس منطق _compute_drawdown_curve في الراوتر)."""
    n = len(candles)
    equity: List[float] = []
    if not n:
        return [], 0.0

    closed_by_bar = sorted(
        [tr for tr in trades if not tr["was_open_at_end"]],
        key=lambda x: x["exit"]["bar"],
    )
    opens = [tr for tr in trades]

    realized = 0.0
    ci = 0  # مؤشر الصفقات المغلقة المستهلكة
    closes = [float(c.get("close") or 0.0) for c in candles]

    for i in range(n):
        while ci < len(closed_by_bar) and int(closed_by_bar[ci]["exit"]["bar"]) <= i:
            realized += float(closed_by_bar[ci]["pnl_usd"])
            ci += 1
        eq = initial_capital + realized
        # غير محقق للصفقة المفتوحة عند الشمعة i (بعد شمعة دخولها)
        for tr in opens:
            ob = int(tr["opened_at_bar"])
            xb = int(tr["exit"]["bar"])
            if ob <= i <= xb and i > ob:
                qty = float(tr["qty_total"])
                invested = float(tr["invested_usd"])
                price = closes[i] if closes[i] else float(tr["entries"][0]["price"])
                eq += qty * price - invested
        equity.append(round(eq, 6))

    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    return equity, max_dd


# ---------------------------------------------------------------------------
# chart_data — نفس عقد المحرك الرئيسي (visual_candles + trade_points + منحنيات)
# ---------------------------------------------------------------------------
def _build_chart_data(
    candles: List[Dict[str, Any]],
    trades: List[Dict[str, Any]],
    exit_cfg: Dict[str, Any],
    symbol: str,
    strategy_payload: Dict[str, Any],
    strategy: str,
    initial_capital: float = 10000.0,
    equity_curve: Optional[List[float]] = None,
) -> Dict[str, Any]:
    from datetime import datetime, timezone as _tz

    n = len(candles)
    trailing_on = bool(exit_cfg["use_trailing"]) and exit_cfg["trailing_giveback_pct"] > 0

    def _ts(ms: Any) -> str:
        try:
            return datetime.fromtimestamp(int(ms) / 1000.0, tz=_tz.utc).isoformat()
        except (TypeError, ValueError, OSError):
            return datetime.utcnow().isoformat()

    # خريطة الشمعة → الصفقة المفتوحة فيها (لوسم position_state)
    open_at = {}  # bar -> trade
    exit_at = {}  # bar -> [trades]
    dca_at = {}   # bar -> [(trade, entry)]
    for tr in trades:
        ob = int(tr["opened_at_bar"])
        xb = int(tr["exit"]["bar"])
        open_at[ob] = tr
        exit_at.setdefault(xb, []).append(tr)
        for en in tr["entries"]:
            if en.get("kind", "entry") != "entry":
                dca_at.setdefault(int(en["bar"]), []).append((tr, en))

    # عمودا ساق الزقزاق (إن وُجدا — zzfib فقط) كأعمدة ind_ للرسم
    series = strategy_payload.get("series") or {}
    zzf_p1 = list(series.get("zzf_p1") or [])
    zzf_p2 = list(series.get("zzf_p2") or [])

    visual_candles: List[Dict[str, Any]] = []
    for i, c in enumerate(candles):
        vc: Dict[str, Any] = {
            "timestamp": _ts(c.get("time")),
            "open": float(c.get("open") or 0.0),
            "high": float(c.get("high") or 0.0),
            "low": float(c.get("low") or 0.0),
            "close": float(c.get("close") or 0.0),
            "volume": float(c.get("volume") or 0.0),
            "indicators": {},
            "strategy_decision": None,
            "triggered_rules": [],
            "confidence": None,
            "position_state": "NEUTRAL",
            "symbol": symbol,
            "trade_action": None,
            "trade_id": None,
            "trade_price": None,
            "trade_size": None,
            "account_balance": None,
            "cumulative_pnl": None,
            "position_size": None,
            "entry_price": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward_ratio": None,
            "current_pnl": None,
            "unrealized_pnl": None,
            "pnl": None,
            "pnl_percentage": None,
        }
        if i < len(zzf_p1) and zzf_p1[i] is not None:
            vc["indicators"]["zzf_p1"] = float(zzf_p1[i])
        if i < len(zzf_p2) and zzf_p2[i] is not None:
            vc["indicators"]["zzf_p2"] = float(zzf_p2[i])

        tr_open = open_at.get(i)
        if tr_open is not None:
            first = tr_open["entries"][0]
            vc["trade_action"] = "ENTRY_LONG"
            vc["trade_id"] = str(tr_open["trade_id"])
            vc["trade_price"] = float(first["price"])
            vc["trade_size"] = float(first["qty"])
            vc["entry_price"] = float(first["price"])
            vc["position_state"] = "LONG"
            vc["stop_loss"] = None  # محرك الخروج: لا وقف نسبي — الوقف كسر الفيبو
            vc["take_profit"] = None if trailing_on else _tp_view(tr_open, exit_cfg)
            vc["floor_price"] = float(tr_open["floor"]["value"])

        dca_here = dca_at.get(i)
        if dca_here:
            tr_d, en_d = dca_here[0]
            vc["trade_action"] = f"DCA_{en_d['kind'].upper()}"
            vc["trade_id"] = str(tr_d["trade_id"])
            vc["trade_price"] = float(en_d["price"])
            vc["trade_size"] = float(en_d["qty"])
            vc["position_state"] = "LONG"

        exits_here = exit_at.get(i)
        if exits_here:
            tr_x = exits_here[0]
            vc["trade_action"] = "EXIT_LONG"
            vc["trade_id"] = str(tr_x["trade_id"])
            vc["trade_price"] = float(tr_x["exit"]["price"])
            vc["pnl"] = round(float(tr_x["pnl_usd"]), 6)
            vc["pnl_percentage"] = round(float(tr_x["pnl_pct"]), 6)
            vc["position_state"] = "NEUTRAL"
            vc["exit_reason"] = tr_x["exit"]["reason"]

        visual_candles.append(vc)

    # نقاط الدخول/الخروج — نفس شكل المحرك الرئيسي + إثراءات ج42
    trade_points: List[Dict[str, Any]] = []
    for tr in trades:
        tid = str(tr["trade_id"])
        first = tr["entries"][0]
        entry_bar = int(tr["opened_at_bar"])
        entry_price = float(first["price"])
        floor_v = float(tr["floor"]["value"])

        trade_points.append({
            "timestamp": _ts(first.get("time")),
            "type": "entry",
            "trade_id": tid,
            "price": entry_price,
            "position_type": "long",
            "position_size": float(first["qty"]),
            "entry_price": entry_price,
            "stop_loss": None,
            "take_profit": None if trailing_on else _tp_view(tr, exit_cfg),
            "indicators_snapshot": {"fib_floor": floor_v},
            "decision_reason": "؛ ".join(str(s) for s in (tr["signal"].get("signals") or [])) or None,
            "confidence": None,
            "account_balance_before": None,
            "commission": round(float(tr["fees_usd"]) / 2.0, 6) if tr["fees_usd"] else 0.0,
            "fill_entry": str(tr["entry_exec"]),
            "direction": "long",
            "symbol": symbol,
            # --- إثراءات ج42 ---
            "floor_price": floor_v,
            "floor_meta": tr["floor"].get("meta") or {},
        })
        for en in tr["entries"]:
            if en.get("kind", "entry") == "entry":
                continue
            trade_points.append({
                "timestamp": _ts(en.get("time")),
                "type": "dca",
                "dca_kind": en["kind"],
                "trade_id": tid,
                "price": float(en["price"]),
                "position_type": "long",
                "position_size": float(en["qty"]),
                "entry_price": float(en["price"]),
                "symbol": symbol,
            })

        ex = tr["exit"]
        exit_p = {
            "timestamp": _ts(ex.get("time")),
            "type": "exit",
            "trade_id": tid,
            "price": float(ex["price"]),
            "exit_price": float(ex["price"]),
            "exit_reason": ex["reason"],
            "pnl": round(float(tr["pnl_usd"]), 6),
            "pnl_percentage": round(float(tr["pnl_pct"]), 6),
            "position_type": "long",
            "entry_price": entry_price,
            "entry_time": _ts(first.get("time")),
            "fill_exit": str(tr["entry_exec"]),
            "direction": "long",
            "symbol": symbol,
            "bars_held": int(tr["bars_held"]),
            "invested_usd": round(float(tr["invested_usd"]), 6),
            "mfe_pct": round(float(tr["mfe_pct"]), 4),
            "mae_pct": round(float(tr["mae_pct"]), 4),
            "dca_fired": list(tr["dca_fired"]),
        }
        if ex.get("peak_price") is not None:
            exit_p["peak_price"] = float(ex["peak_price"])
        trade_points.append(exit_p)

    # خط السقف المتحرك لكل صفقة عند تفعيل التريلينق (للرسم على الشاشة)
    trail_lines: Dict[str, List[Dict[str, Any]]] = {}
    if trailing_on and candles:
        highs = [float(c.get("high") or 0.0) for c in candles]
        for tr in trades:
            ob = int(tr["opened_at_bar"])
            xb = int(tr["exit"]["bar"])
            first_price = float(tr["entries"][0]["price"])
            peak = first_price
            line: List[Dict[str, Any]] = []
            for i in range(ob, min(xb + 1, n)):
                if i > ob and highs[i] > peak:
                    peak = highs[i]
                line.append({
                    "timestamp": _ts(candles[i].get("time")),
                    "price": round(peak, 8),
                })
            trail_lines[str(tr["trade_id"])] = line

    if equity_curve is None:
        equity_curve, _dd = _equity_and_drawdown(candles, trades, initial_capital)
    equity_curve_vals = list(equity_curve)
    drawdown_vals = _drawdown_from_equity(equity_curve_vals)

    return {
        "visual_candles": visual_candles,
        "trade_points": trade_points,
        "equity_curve": equity_curve_vals,
        "drawdown_curve": drawdown_vals,
        # --- إثراءات ج42 (يقرأها الفرونت اختيارياً — تُتجاهل إن لم تُستخدم) ---
        "trail_lines": trail_lines,
        "trailing_active": trailing_on,
        "exit_engine": {
            "config": dict(exit_cfg),
            "trades_count": len(trades),
        },
    }


def _drawdown_from_equity(equity: List[float]) -> List[float]:
    out: List[float] = []
    peak = equity[0] if equity else 0.0
    for v in equity:
        if v > peak:
            peak = v
        out.append(round((peak - v) / peak * 100.0, 6) if peak > 0 else 0.0)
    return out


def _tp_view(tr: Dict[str, Any], exit_cfg: Dict[str, Any]) -> Optional[float]:
    """سعر هدف جني الربح للعرض (كما يحسبه محرك الخروج تماماً)."""
    if bool(exit_cfg["use_trailing"]) and exit_cfg["trailing_giveback_pct"] > 0:
        return None
    tp_pct = float(exit_cfg["take_profit_pct"]) / 100.0
    if exit_cfg["tp_reference"] == "first":
        base = float(tr["entries"][0]["price"])
    else:
        base = float(tr["avg_price"])
    return round(base * (1.0 + tp_pct), 8)
