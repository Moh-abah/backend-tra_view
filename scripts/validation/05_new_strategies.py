"""Invent 3 NEW professional strategies, save them, validate, and backtest
them on REAL market data (BTCUSDT + ETHUSDT, 60d × 1h) with a comparison table.

Invented strategies:
  1. Volume Climax Reversal Pro  — mean-reversion confirmed by volume climax
  2. MACD Zero-Line Momentum     — trend-following confluence (MACD 0-cross + EMA21 + RSI band)
  3. Bollinger Oversold Sniper   — bounce from lower band with double-oversold confirm

Each is saved to strategies/*.json (loader format) and validated through the
official validate_strategy_config gate before any backtest.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

STRATEGIES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "strategies"))

# ----------------------------------------------------------------------------
# 1) Volume Climax Reversal Pro
# ----------------------------------------------------------------------------
VOLUME_CLIMAX_REVERSAL = {
    "name": "Volume Climax Reversal Pro",
    "version": "1.0.0",
    "description": "ارتدادي احترافي: دخول عند تشبع بيعي RSI مع ذروة حجم تؤكد استنفاد البائعين، وخروج عند استعادة الزخم",
    "base_timeframe": "1h",
    "position_side": "long",
    "indicators": [
        {"id": "rsi", "name": "rsi", "type": "momentum", "params": {"period": 14, "overbought": 65, "oversold": 35}, "enabled": True, "timeframe": "1h"},
        {"id": "vc", "name": "volume_climax", "type": "volume", "params": {"period": 20, "ratio_very_high": 1.8, "ratio_high": 1.2}, "enabled": True, "timeframe": "1h"},
        {"id": "ema200", "name": "ema_200", "type": "trend", "params": {"period": 200}, "enabled": True, "timeframe": "1h"},
    ],
    "entry_rules": [
        {
            "name": "Climax Oversold Reversal",
            "enabled": True,
            "position_side": "long",
            "weight": 1.0,
            "condition": {
                "type": "and",
                "conditions": [
                    {"type": "indicator_value", "operator": "<=", "left_value": "indicator:rsi", "right_value": 35},
                    {"type": "indicator_value", "operator": ">=", "left_value": "indicator:vc", "right_value": 1.2},
                ],
            },
        }
    ],
    "exit_rules": [
        {
            "name": "Momentum Restored Exit",
            "enabled": True,
            "exit_type": "signal_exit",
            "condition": {"type": "indicator_value", "operator": ">=", "left_value": "indicator:rsi", "right_value": 60},
        }
    ],
    "risk_management": {"stop_loss_percentage": 5.0, "take_profit_percentage": 10.0, "max_position_size": 0.25, "max_concurrent_positions": 1},
}

# ----------------------------------------------------------------------------
# 2) MACD Zero-Line Momentum Confluence
# ----------------------------------------------------------------------------
MACD_MOMENTUM_CONFLUENCE = {
    "name": "MACD Zero-Line Momentum Confluence",
    "version": "1.0.0",
    "description": "اتباع اتجاه: تقاطع MACD فوق الصفر مع تأكيد EMA21 وزخم RSI صحي 45-75 لتجنب القمم المشبعة",
    "base_timeframe": "1h",
    "position_side": "long",
    "indicators": [
        {"id": "macd", "name": "macd", "type": "momentum", "params": {"fast": 12, "slow": 26, "signal": 9}, "enabled": True, "timeframe": "1h"},
        {"id": "ema21", "name": "ema_21", "type": "trend", "params": {"period": 21}, "enabled": True, "timeframe": "1h"},
        {"id": "rsi", "name": "rsi", "type": "momentum", "params": {"period": 14}, "enabled": True, "timeframe": "1h"},
    ],
    "entry_rules": [
        {
            "name": "Zero-Line Momentum Long",
            "enabled": True,
            "position_side": "long",
            "weight": 1.0,
            "condition": {
                "type": "and",
                "conditions": [
                    {"type": "indicator_crossover", "operator": "cross_above", "left_value": "indicator:macd", "right_value": 0},
                    {"type": "indicator_value", "operator": ">=", "left_value": "indicator:rsi", "right_value": 45},
                    {"type": "indicator_value", "operator": "<=", "left_value": "indicator:rsi", "right_value": 75},
                ],
            },
        }
    ],
    "exit_rules": [
        {
            "name": "Momentum Fade Exit",
            "enabled": True,
            "exit_type": "signal_exit",
            "condition": {
                "type": "or",
                "conditions": [
                    {"type": "indicator_crossover", "operator": "cross_below", "left_value": "indicator:macd", "right_value": 0},
                    {"type": "indicator_value", "operator": "<", "left_value": "indicator:rsi", "right_value": 40},
                ],
            },
        }
    ],
    "risk_management": {"stop_loss_percentage": 4.0, "take_profit_percentage": 8.0, "max_position_size": 0.3, "max_concurrent_positions": 1},
}

# ----------------------------------------------------------------------------
# 3) Bollinger Oversold Sniper
# ----------------------------------------------------------------------------
BOLLINGER_SNIPER = {
    "name": "Bollinger Oversold Sniper",
    "version": "1.1.0",
    "description": "قنص ارتدادات بولينجر: اختراق النطاق السفلي بالسعر مع تشبع مزدوج (RSI+Stochastic)",
    "base_timeframe": "1h",
    "position_side": "long",
    "indicators": [
        {"id": "bbl", "name": "bollinger_lower", "type": "volatility", "params": {"period": 20, "std": 2.0}, "enabled": True, "timeframe": "1h"},
        {"id": "rsi", "name": "rsi", "type": "momentum", "params": {"period": 14}, "enabled": True, "timeframe": "1h"},
        {"id": "stoch", "name": "stochastic", "type": "momentum", "params": {"k_period": 14, "d_period": 3}, "enabled": True, "timeframe": "1h"},
    ],
    "entry_rules": [
        {
            "name": "Lower Band Break Double Oversold",
            "enabled": True,
            "position_side": "long",
            "weight": 1.0,
            "condition": {
                "type": "and",
                "conditions": [
                    {"type": "indicator_crossover", "operator": "cross_below", "left_value": "price:close", "right_value": "indicator:bbl"},
                    {"type": "indicator_value", "operator": "<", "left_value": "indicator:rsi", "right_value": 40},
                    {"type": "indicator_value", "operator": "<", "left_value": "indicator:stoch", "right_value": 30},
                ],
            },
        }
    ],
    "exit_rules": [
        {
            "name": "Mean Reversion Exit",
            "enabled": True,
            "exit_type": "signal_exit",
            "condition": {"type": "indicator_value", "operator": ">=", "left_value": "indicator:rsi", "right_value": 55},
        }
    ],
    "risk_management": {"stop_loss_percentage": 6.0, "take_profit_percentage": 6.0, "max_position_size": 0.25, "max_concurrent_positions": 1},
}

NEW_STRATEGIES = {
    "volume_climax_reversal_pro": VOLUME_CLIMAX_REVERSAL,
    "macd_zero_line_momentum": MACD_MOMENTUM_CONFLUENCE,
    "bollinger_oversold_sniper": BOLLINGER_SNIPER,
}

RESULTS: list[tuple[str, str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, "PASS" if ok else "FAIL", detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} {detail}")


class LiveDataService:
    def __init__(self, cache: dict):
        self._cache = cache

    async def get_historicallastvirsion(self, symbol=None, timeframe=None, market=None, start_date=None, end_date=None, use_cache=True, **kw):
        key = (symbol, timeframe)
        if key not in self._cache:
            from app.database import AsyncSessionLocal
            from app.services.data_service import DataService
            async with AsyncSessionLocal() as db:
                ds = DataService(db)
                self._cache[key] = await ds.get_historical(symbol=symbol, timeframe=timeframe, market=market or "crypto", days=60, use_cache=False)
        df = self._cache[key]
        from app.backtest.engine1 import BacktestEngine
        return BacktestEngine._normalize_candle_index(df.copy())


async def backtest(engine, strategy_cfg: dict, symbol: str, cache: dict) -> dict:
    from app.backtest.schemas import BacktestConfig
    df = await LiveDataService(cache).get_historicallastvirsion(symbol=symbol, timeframe="1h", market="crypto")
    start = df.index[0].to_pydatetime()
    end = df.index[-1].to_pydatetime()
    cfg = BacktestConfig(
        name=f"{strategy_cfg['name']} [{symbol}]",
        timeframe="1h",
        market="crypto",
        symbols=[symbol],
        start_date=start,
        end_date=end,
        initial_capital=10000.0,
        commission_rate=0.001,
        slippage_percent=0.001,
        strategy_config=strategy_cfg,
    )
    t0 = time.perf_counter()
    res = await engine.run_backtest(cfg)
    elapsed = time.perf_counter() - t0
    return {
        "symbol": symbol,
        "trades": int(res.total_trades or 0),
        "wins": int(res.winning_trades or 0),
        "win_rate": float(res.win_rate or 0.0),
        "pnl_percent": float(res.total_pnl_percent or 0.0),
        "final_capital": float(res.final_capital or 0.0),
        "max_dd": float(res.max_drawdown_percent or 0.0),
        "sharpe": float(res.sharpe_ratio or 0.0),
        "profit_factor": float(res.profit_factor) if res.profit_factor is not None else None,
        "engine_seconds": round(elapsed, 2),
        "bars": len(df),
    }


async def main() -> None:
    from app.services.strategy import validate_strategy_config
    from app.backtest.engine1 import BacktestEngine

    print("\n=== 1) Save invented strategies ===")
    os.makedirs(STRATEGIES_DIR, exist_ok=True)
    for fname, cfg in NEW_STRATEGIES.items():
        path = os.path.join(STRATEGIES_DIR, f"{fname}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        check(f"saved {fname}.json", os.path.exists(path), f"{os.path.getsize(path)} bytes")

    print("\n=== 2) Validate through official gate ===")
    for fname, cfg in NEW_STRATEGIES.items():
        v = validate_strategy_config(cfg)
        check(f"{cfg['name']} valid", bool(v.get("valid")), str(v.get("errors", ""))[:150])

    print("\n=== 3) Real backtests (BTCUSDT + ETHUSDT, 60d×1h, $10k, 0.1% fees) ===")
    cache: dict = {}
    engine = BacktestEngine(LiveDataService(cache))  # type: ignore[arg-type]
    rows = []
    for fname, cfg in NEW_STRATEGIES.items():
        for symbol in ("BTCUSDT", "ETHUSDT"):
            try:
                r = await backtest(engine, cfg, symbol, cache)
                r["strategy"] = cfg["name"]
                rows.append(r)
                check(f"{cfg['name']} × {symbol} backtest ran", True,
                      f"trades={r['trades']} pnl={r['pnl_percent']:+.2f}% wr={r['win_rate']:.0f}% dd={r['max_dd']:.1f}% in {r['engine_seconds']}s")
            except Exception as e:
                check(f"{cfg['name']} × {symbol} backtest ran", False, f"{type(e).__name__}: {e}")

    print("\n=== 4) Comparison table ===")
    header = f"{'Strategy':34s} {'Sym':8s} {'Trades':>6s} {'WinRate':>8s} {'PnL%':>8s} {'MaxDD%':>7s} {'Sharpe':>7s} {'PF':>6s} {'Sec':>6s}"
    print(header)
    print("-" * len(header))
    for r in rows:
        pf = f"{r['profit_factor']:.2f}" if r["profit_factor"] is not None else "—"
        print(f"{r['strategy'][:33]:34s} {r['symbol'][:7]:8s} {r['trades']:6d} {r['win_rate']:7.1f}% {r['pnl_percent']:+8.2f} {r['max_dd']:7.2f} {r['sharpe']:7.2f} {pf:>6s} {r['engine_seconds']:6.2f}")


if __name__ == "__main__":
    asyncio.run(main())
    print("\n" + "=" * 78)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    for label, verdict, detail in RESULTS:
        print(f"  [{verdict}] {label} {detail}")
    print(f"TOTAL: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASSED")
    sys.exit(1 if fails else 0)
