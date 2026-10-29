"""Performance benchmarks — real measurements, honest numbers.

Benchmarks:
  B1. Historical fetch: BTCUSDT 365d×1h (network, Binance paged)
  B2. Indicator pipeline: 8 indicators × 720 bars (registry, cache off)
  B3. Indicator cache: LRU bound respected under 400 loads
  B4. Backtest throughput: random-walk 2000 bars (bars/sec, per-phase timing)
  B5. SignalEngine.evaluate on 720 bars
  B6. Strategy decisions (strategy_engine1.run) per-bar latency
  B7. WS /ws/market-overview throughput (live Binance feed, 12s sample)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

gen = __import__("01_generate_test_data")

RESULTS: list[tuple[str, str]] = []


def bench(label: str, value: str) -> None:
    RESULTS.append((label, value))
    print(f"  {label:52s} {value}")


async def main() -> None:
    print("\n— B1. Historical fetch (network) —")
    from app.database import AsyncSessionLocal
    from app.services.data_service import DataService
    t0 = time.perf_counter()
    async with AsyncSessionLocal() as db:
        ds = DataService(db)
        df365 = await ds.get_historical(symbol="BTCUSDT", timeframe="1h", market="crypto", days=365, use_cache=False)
    dt = time.perf_counter() - t0
    bench("fetch 365d×1h BTCUSDT", f"{len(df365)} candles in {dt:.2f}s ({len(df365)/dt:.0f} candles/s)")

    print("\n— B2. Indicator pipeline (8 indicators × 720 bars, cache off) —")
    from app.services.indicators import apply_indicators
    df = gen.random_walk(720)
    cfgs = [{"name": n, "params": p} if p else {"name": n} for n, p in [
        ("rsi", {"period": 14}), ("macd", None), ("ema", {"period": 21}), ("sma", {"period": 50}),
        ("bollinger_bands", {"period": 20, "std": 2.0}), ("atr", {"period": 14}),
        ("stochastic", None), ("obv", None),
    ]]
    t0 = time.perf_counter()
    out = apply_indicators(df, cfgs, use_cache=False)
    dt = time.perf_counter() - t0
    bench("8 indicators on 720 bars", f"{dt*1000:.1f} ms ({dt/720*1e6:.0f} µs/bar)")
    non_null = sum(
        sum(1 for v in (r.get("values", {}).get("data", []) if isinstance(r, dict) else []) if v is not None)
        for r in out.values()
    )
    bench("non-null values produced", f"{non_null} values")

    print("\n— B3. Indicator cache LRU bound —")
    from app.services.indicators.calculator import IndicatorCalculator
    calc = IndicatorCalculator()
    for i in range(400):
        small = gen.linear_up(30)
        calc._cache_set(f"bench-key-{i}", {"i": i})
    bench("cache size after 400 inserts", f"{len(calc.cache)} (bound={calc._max_size})")

    print("\n— B4. Backtest throughput —")
    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig

    class FakeDS:
        def __init__(self, frame):
            self.df = frame

        async def get_historicallastvirsion(self, **kw):
            return self.df.copy()

    big = gen.random_walk(2000)
    strategy = {
        "name": "Bench", "base_timeframe": "1h", "position_side": "long",
        "indicators": [
            {"id": "rsi", "name": "rsi", "type": "momentum", "params": {"period": 14}, "enabled": True, "timeframe": "1h"},
            {"id": "ema21", "name": "ema_21", "type": "trend", "params": {"period": 21}, "enabled": True, "timeframe": "1h"},
        ],
        "entry_rules": [{"name": "e", "enabled": True, "position_side": "long", "weight": 1.0,
                         "condition": {"type": "and", "conditions": [
                             {"type": "indicator_value", "operator": "<", "left_value": "indicator:rsi", "right_value": 70},
                             {"type": "indicator_value", "operator": ">", "left_value": "indicator:rsi", "right_value": 30},
                         ]}}],
        "exit_rules": [{"name": "x", "enabled": True, "exit_type": "signal_exit",
                        "condition": {"type": "indicator_value", "operator": ">", "left_value": "indicator:rsi", "right_value": 75}}],
        "risk_management": {"stop_loss_percentage": 5.0, "take_profit_percentage": 10.0},
    }
    cfg = BacktestConfig(
        name="bench", timeframe="1h", market="synthetic", symbols=["TUSDT"],
        start_date=big.index[0].to_pydatetime(), end_date=big.index[-1].to_pydatetime(),
        initial_capital=10000, strategy_config=strategy,
    )
    engine = BacktestEngine(FakeDS(big))  # type: ignore[arg-type]
    t0 = time.perf_counter()
    res = await engine.run_backtest(cfg)
    dt = time.perf_counter() - t0
    bench("backtest 2000 bars end-to-end", f"{dt:.2f}s ({2000/dt:.0f} bars/s)")
    bench("trades generated", f"{res.total_trades} (wr={res.win_rate:.0f}%)")

    print("\n— B5/B6. Strategy decision latency —")
    from app.services.strategy.strategy_engine1 import StrategyEngine
    from app.services.strategy.schemas import StrategyConfig as SC
    scfg = SC(**strategy)
    seng = StrategyEngine(scfg)
    full = await seng._prepare_indicators(big)
    # warm
    await seng.run(full, current_index=100, in_position=False)
    t0 = time.perf_counter()
    n_dec = 50
    for i in range(100, 100 + n_dec):
        await seng.run(full, current_index=i, in_position=False)
    dt = time.perf_counter() - t0
    bench("strategy decision (prepared data)", f"{dt/n_dec*1000:.2f} ms/decision")

    from app.services.signals.engine import SignalEngine
    sig = SignalEngine()
    t0 = time.perf_counter()
    await sig.evaluate("BTCUSDT", "1h", big)
    dt = time.perf_counter() - t0
    bench("SignalEngine.evaluate (2000 bars)", f"{dt*1000:.0f} ms")


async def ws_benchmark() -> None:
    print("\n— B7. WebSocket market-overview (live) —")
    import websockets
    try:
        async with websockets.connect("ws://127.0.0.1:8899/ws/market-overview") as ws:
            start = time.perf_counter()
            count = 0
            payload_sample = None
            while time.perf_counter() - start < 12:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=13)
                    count += 1
                    if payload_sample is None:
                        payload_sample = msg[:80]
                except asyncio.TimeoutError:
                    break
            dt = time.perf_counter() - start
            bench("WS messages in 12s", f"{count} msgs ({count/dt:.2f} msg/s) first={payload_sample}")
    except Exception as e:
        bench("WS messages in 12s", f"unavailable ({type(e).__name__})")


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(ws_benchmark())
    print("\n" + "=" * 78)
    for label, value in RESULTS:
        print(f"  {label:52s} {value}")
