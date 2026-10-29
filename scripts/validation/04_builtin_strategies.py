"""Run ALL built-in strategies on REAL market data + evaluate signal engine.

For each builtin strategy (rsi, macd, trend, mean_reversion, test):
  - load its config dict via its module getter
  - run through the central facade run_strategy() on real BTCUSDT candles
  - verify StrategyResult structure + count signals
Also smoke-tests the SignalEngine end-to-end.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

RESULTS: list[tuple[str, str, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, "PASS" if ok else "FAIL", detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label} {detail}")


async def fetch_btc(days: int = 30):
    from app.database import AsyncSessionLocal
    from app.services.data_service import DataService
    async with AsyncSessionLocal() as db:
        ds = DataService(db)
        return await ds.get_historical(symbol="BTCUSDT", timeframe="1h", market="crypto", days=days, use_cache=False)


async def main() -> None:
    from app.services.strategy import run_strategy, validate_strategy_config
    from app.services.strategy.strategys.rsi_strategy import get_rsi_strategy
    from app.services.strategy.strategys.macd_strategy import get_macd_strategy
    from app.services.strategy.strategys.trend_strategy import get_trend_strategy
    from app.services.strategy.strategys.mean_reversion_strategy import get_mean_reversion_strategy

    df = await fetch_btc(30)
    print(f"\nReal BTCUSDT 1h candles: {len(df)} rows")
    check("real data fetched", len(df) > 300, f"rows={len(df)}")

    strategies = {
        "RSI Basic": get_rsi_strategy(),
        "MACD": get_macd_strategy(),
        "Trend": get_trend_strategy(),
        "Mean Reversion": get_mean_reversion_strategy(),
    }

    for name, cfg in strategies.items():
        print(f"\n— {name} —")
        validation = validate_strategy_config(cfg)
        valid = bool(validation.get("valid", False))
        check(f"{name}: config valid", valid, str(validation.get("errors", []))[:120])

        try:
            result = await run_strategy(df, cfg)
            signals = list(getattr(result, "signals", []) or [])
            check(f"{name}: run_strategy executed", True, f"signals={len(signals)}")
            if signals:
                s0 = signals[0]
                has_fields = all(hasattr(s0, a) for a in ("timestamp", "action", "confidence"))
                check(f"{name}: signal structure sane", has_fields,
                      f"first={getattr(s0, 'action', '?')} @{getattr(s0, 'timestamp', '?')}")
            else:
                check(f"{name}: signal structure sane", True, "no signals this period (ok)")
        except Exception as e:
            check(f"{name}: run_strategy executed", False, f"{type(e).__name__}: {e}")

    # SignalEngine end-to-end
    print("\n— SignalEngine —")
    from app.services.signals.engine import SignalEngine
    engine = SignalEngine()
    sigs = await engine.evaluate("BTCUSDT", "1h", df)
    check("SignalEngine.evaluate returns list", isinstance(sigs, list), f"n={len(sigs)}")
    if sigs:
        s0 = sigs[0]
        keys_ok = all(k in s0 for k in ("symbol", "signal_type", "price", "timestamp"))
        check("SignalEngine signal dict keys", keys_ok, f"sample={str(s0)[:110]}")
    else:
        check("SignalEngine signal dict keys", True, "no signals this window (ok)")


if __name__ == "__main__":
    asyncio.run(main())
    print("\n" + "=" * 78)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    for label, verdict, detail in RESULTS:
        print(f"  [{verdict}] {label} {detail}")
    print(f"TOTAL: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASSED")
    sys.exit(1 if fails else 0)
