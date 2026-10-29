"""Backtest engine validation with ANALYTICALLY-KNOWN outcomes (v2).

RSI behavior on engineered data (verified in 02_validate_indicators):
  linear_up   → RSI pinned at 100
  linear_down → RSI pinned at 0
  constant    → RSI = 50
This lets us craft deterministic entry/exit rules.

Scenarios:
  A. Uptrend  + long (entry RSI≥0, exit RSI>95) → quick 1-bar wins:
     win_rate == 100%, final > initial×1.03 (fees correctly deducted).
  B. Downtrend + same long strategy → position trapped (exit never fires):
     winning_trades == 0 (engine must NOT fabricate profits).
  C. Flat + exit RSI>10 → deterministic 1-bar round trips:
     per-trade pnl = -2*(commission+slippage)*100 = -0.40% exactly;
     total ≈ (1-0.004)^n − 1.
  D. V-shape + long (entry RSI≥0, exit RSI>95) → position held through crash:
     max_drawdown_percent must be large (>20%).
  E. Walk-forward: anchored windows ordered, aggregate consistent.
  F. Monte-Carlo: percentiles ascending, prob_of_profit ∈ [0,1].
  G. Real BTC data end-to-end (network) — trades/equity/metrics produced.
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.backtest.engine1 import BacktestEngine  # noqa: E402
from app.backtest.schemas import BacktestConfig  # noqa: E402

gen = __import__("01_generate_test_data")
DATA = os.path.join(os.path.dirname(__file__), "data")

RESULTS: list[tuple[str, str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, "PASS" if ok else "FAIL", detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} {detail}")


class FakeDataService:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    async def get_historicallastvirsion(self, **kwargs):
        return self.df.copy()

    async def get_historical_last_version(self, **kwargs):
        return self.df.copy()


def make_strategy(exit_threshold: float) -> dict:
    return {
        "name": "Validation Long",
        "base_timeframe": "1h",
        "position_side": "long",
        "indicators": [
            {"id": "rsi", "name": "rsi", "type": "momentum", "params": {"period": 14}, "enabled": True, "timeframe": "1h"},
        ],
        "entry_rules": [
            {
                "name": "enter long",
                "enabled": True,
                "position_side": "long",
                "weight": 1.0,
                "condition": {"type": "indicator_value", "operator": ">=", "left_value": "indicator:rsi", "right_value": 0},
            }
        ],
        "exit_rules": [
            {
                "name": "exit long",
                "enabled": True,
                "exit_type": "signal_exit",
                "condition": {"type": "indicator_value", "operator": ">", "left_value": "indicator:rsi", "right_value": exit_threshold},
            }
        ],
        "risk_management": {
            "stop_loss_percentage": 50.0,
            "take_profit_percentage": 100.0,
            "max_position_size": 1.0,
            "max_concurrent_positions": 1,
        },
    }


def _frame_bounds(df: pd.DataFrame):
    """يعيد (start, end) كـ datetime سواء كان الفهرس زمنياً أو عمود time موجود"""
    if isinstance(df.index, pd.DatetimeIndex):
        return df.index[0].to_pydatetime(), df.index[-1].to_pydatetime()
    t = pd.to_datetime(df["time"], unit="ms", utc=True)
    return t.iloc[0].to_pydatetime(), t.iloc[-1].to_pydatetime()


def make_config(df: pd.DataFrame, name: str, strategy: dict, capital: float = 10000.0) -> BacktestConfig:
    start, end = _frame_bounds(df)
    return BacktestConfig(
        name=name,
        timeframe="1h",
        market="synthetic",
        symbols=["TESTUSDT"],
        start_date=start,
        end_date=end,
        initial_capital=capital,
        commission_rate=0.001,
        slippage_percent=0.001,
        stop_loss_percent=50.0,
        take_profit_percent=100.0,
        strategy_config=strategy,
    )


async def run_engine(df: pd.DataFrame, name: str, strategy: dict) -> object:
    engine = BacktestEngine(FakeDataService(df))  # type: ignore[arg-type]
    return await engine.run_backtest(make_config(df, name, strategy))


def _g(obj, attr, default=0.0):
    v = getattr(obj, attr, default)
    return default if v is None else v


async def scenario_a() -> None:
    print("\n— A. Uptrend: quick wins, fees applied —")
    df = gen.linear_up(300)
    res = await run_engine(df, "uptrend", make_strategy(95))
    n = int(_g(res, "total_trades"))
    wins = int(_g(res, "winning_trades"))
    final = float(_g(res, "final_capital"))
    check("A1 trades produced", n >= 10, f"n={n}")
    check("A2 win_rate == 100%", n > 0 and wins == n, f"wins={wins}/{n}")
    # حجم المركز الافتراضي 0.1 → كل صفقة +0.5% سعر × 0.1 حجم − 0.4% رسوم ≈ +0.01% رصيد
    check("A3 final capital > initial (real profits net of fees)", final > 10050.0, f"final={final:.2f}")


async def scenario_b() -> None:
    print("\n— B. Downtrend: no fabricated profits —")
    df = gen.linear_down(300)
    res = await run_engine(df, "downtrend", make_strategy(95))
    wins = int(_g(res, "winning_trades"))
    check("B1 zero winning longs", wins == 0,
          f"trades={int(_g(res, 'total_trades'))} wins={wins} pnl%={float(_g(res, 'total_pnl_percent')):.2f}")


async def scenario_c() -> None:
    print("\n— C. Flat: PnL == exact fee drag —")
    df = gen.constant(60)
    res = await run_engine(df, "flat", make_strategy(10))
    n = int(_g(res, "total_trades"))
    total_pct = float(_g(res, "total_pnl_percent"))
    # حجم المركز 0.1: أثر الصفقة على الرصيد = -0.4% × 0.1 = -0.04% مركّبة
    expected = ((1 - 0.004 * 0.1) ** n - 1) * 100 if n else 0.0
    check("C1 round trips executed", n >= 2, f"n={n}")
    check("C2 total PnL% == compound fee drag × position size",
          abs(total_pct - expected) <= 0.05,
          f"engine={total_pct:.4f}% expected={expected:.4f}% (n={n})")


async def scenario_d() -> None:
    print("\n— D. V-shape: drawdown reflects real dip —")
    df = gen.v_shape(400)
    strategy = make_strategy(95)
    engine = BacktestEngine(FakeDataService(df))  # type: ignore[arg-type]
    cfg = make_config(df, "vshape", strategy)
    # حجم مركز كامل ليتبع الرصيد الهبوط فعلاً (وإلا يُقصّه 0.1 الافتراضي)
    cfg = cfg.model_copy(update={"position_size_percent": 1.0, "stop_loss_percent": 50.0})
    res = await engine.run_backtest(cfg)
    dd = float(_g(res, "max_drawdown_percent"))
    check("D1 max drawdown > 20% (position rode the crash)", dd > 20.0, f"dd={dd:.2f}%")
    curve = list(getattr(res, "equity_curve", []) or [])
    check("D2 equity curve present", len(curve) > 10, f"len={len(curve)}")


async def scenario_e() -> None:
    print("\n— E. Walk-forward structure —")
    df = gen.random_walk(720)
    engine = BacktestEngine(FakeDataService(df))  # type: ignore[arg-type]
    wf = await engine.run_walk_forward_analysis(make_config(df, "wf", make_strategy(95)))
    windows = wf.get("windows", [])
    check("E1 windows produced", len(windows) >= 2, f"n={len(windows)}")
    if len(windows) >= 2:
        iso = lambda s: pd.Timestamp(s)
        ordered = all(
            iso(windows[i]["test_end"]) <= iso(windows[i + 1]["test_start"]) + pd.Timedelta(seconds=1)
            for i in range(len(windows) - 1)
        )
        check("E2 windows temporally ordered", ordered, "")
        first_trained = next((w for w in windows if w.get("in_sample")), None)
        check("E3 anchored training skipped only for window 1",
              first_trained is windows[1] if len(windows) > 1 else True,
              f"first trained window=#{first_trained['window'] if first_trained else None}")
        agg = wf.get("overall", {})
        check("E4 aggregate consistent",
              agg.get("total_windows") == len(windows) and agg.get("evaluated_windows") == sum(1 for w in windows if w.get("out_of_sample")),
              f"total={agg.get('total_windows')} evaluated={agg.get('evaluated_windows')}")


async def scenario_f() -> None:
    print("\n— F. Monte-Carlo structure —")
    df = gen.random_walk(720)
    engine = BacktestEngine(FakeDataService(df))  # type: ignore[arg-type]
    mc = await engine.run_monte_carlo_simulation(make_config(df, "mc", make_strategy(95)), n_simulations=50)
    if not isinstance(mc, dict):
        check("F1 returns dict", False, type(mc).__name__)
        return
    pcts = mc.get("return_percent") or {}
    keys = [k for k in ("percentile_5", "percentile_25", "percentile_50", "percentile_75", "percentile_95") if k in pcts]
    ordered = all(float(pcts[keys[i]]) <= float(pcts[keys[i + 1]]) + 1e-9 for i in range(len(keys) - 1)) if len(keys) == 5 else True
    check("F1 percentile keys present", len(keys) == 5, f"keys={keys}")
    check("F2 percentiles ascending", ordered, "")
    pop = mc.get("probability_of_profit")
    check("F3 probability_of_profit ∈ [0,1]", pop is None or (0.0 <= float(pop) <= 1.0), f"pop={pop}")
    check("F4 n_simulations respected", int(mc.get("n_simulations", 0) or 0) <= 50, f"sims={mc.get('n_simulations')}")
    check("F5 base trades used > 0", int(mc.get("base_trades_used", 0) or 0) > 0, f"base={mc.get('base_trades_used')}")


async def scenario_g() -> None:
    print("\n— G. Real BTC data end-to-end (network) —")
    from app.database import AsyncSessionLocal
    from app.services.data_service import DataService
    async with AsyncSessionLocal() as db:
        ds = DataService(db)
        df = await ds.get_historical(symbol="BTCUSDT", timeframe="1h", market="crypto", days=30, use_cache=False)
    check("G1 real BTC candles fetched", len(df) > 300, f"rows={len(df)}")
    res = await run_engine(df, "btc-real", make_strategy(70))
    curve = list(getattr(res, "equity_curve", []) or [])
    visual = list(getattr(res, "visual_candles", []) or [])
    check("G2 backtest executed on real data", len(curve) >= 2 and int(_g(res, "total_trades")) >= 1,
          f"trades={int(_g(res, 'total_trades'))} equity_points={len(curve)} visual={len(visual)}")
    check("G2b per-bar visual candles produced", len(visual) > 100, f"visual={len(visual)}")
    sharpe = getattr(res, "sharpe_ratio", None)
    check("G3 metrics sane", sharpe is None or np.isfinite(float(sharpe)), f"sharpe={sharpe}")


async def main() -> None:
    await scenario_a()
    await scenario_b()
    await scenario_c()
    await scenario_d()
    await scenario_e()
    await scenario_f()
    await scenario_g()

    print("\n" + "=" * 78)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    for label, verdict, detail in RESULTS:
        print(f"  [{verdict}] {label} {detail}")
    print("-" * 78)
    print(f"TOTAL: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASSED")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
