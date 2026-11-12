# ساندبوكس إثبات R45 — محرك الخروج الموحد (ج42) بنفس عقد المداخل/المخارج
import hashlib
import os
import time
from typing import Any, Dict, List, Tuple


def validate_exit_block(
    strategy: str, strategy_params: Dict, config: Dict
) -> Tuple[Dict, List]:
    cfg = dict(config or {})
    cfg.setdefault("use_trailing", True)
    cfg.setdefault("trailing_giveback_pct", 20.0)
    return {"config": cfg, "strategy_params": dict(strategy_params or {})}, []


def run_unified_exit_backtest(
    candles: List[Dict[str, Any]],
    strategy: str,
    strategy_params: Dict,
    exit_cfg: Dict,
    ctx: Dict,
) -> Dict[str, Any]:
    delay = float(os.environ.get("SANDBOX_SIM_DELAY", "0") or 0)
    if delay:
        time.sleep(delay)

    seed = int(hashlib.md5(str(ctx.get("name", "")).encode()).hexdigest()[:6], 16)
    n = len(candles)
    trades = max(1, n // 20)
    wins = trades * 13 // 23
    win_rate = round(100.0 * wins / trades, 2)
    pnl = round((seed % 4000) / 100.0 - 5.0, 2)

    summary = {
        "name": ctx.get("name"),
        "symbol": ctx.get("symbol"),
        "timeframe": ctx.get("timeframe"),
        "initial_capital": float(ctx.get("initial_capital", 10000.0)),
        "final_capital": round(float(ctx.get("initial_capital", 10000.0)) * (1 + pnl / 100.0), 2),
        "total_pnl": round(float(ctx.get("initial_capital", 10000.0)) * pnl / 100.0, 2),
        "total_pnl_percent": pnl,
        "total_trades": trades,
        "winning_trades": wins,
        "losing_trades": trades - wins,
        "win_rate": win_rate,
        "max_drawdown_percent": round(abs(pnl) / 3.0 + 1.5, 2),
        "sharpe_ratio": 1.31,
        "sortino_ratio": 1.72,
        "calmar_ratio": 1.15,
        "profit_factor": 1.83,
        "expectancy": 42.5,
        "annual_return_percent": round(pnl * 3.2, 2),
        "execution_time_seconds": 0.71,
        "architecture_mode": "Unified-Exit-Engine-R42",
        "exit_strategy": {"trailing": {"active": bool(exit_cfg.get("use_trailing"))}},
        "exit_reasons": {"trailing": trades // 2, "take_profit": trades // 3},
        "candles_consumed": n,
    }
    chart = {
        "visual_candles": candles[:4000],
        "trade_points": [
            {"time": c["time"], "type": "entry" if i % 2 == 0 else "exit", "price": c["close"]}
            for i, c in enumerate(candles[: trades * 2])
        ],
    }
    return {"summary": summary, "chart_data": chart}
