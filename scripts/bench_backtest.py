#!/usr/bin/env python3
"""
bench_backtest.py — قياس أداء محرك الباك تست على بيانات حقيقية 1m
يقيس: شموع/ثانية، زرع المؤشرات، قرار لكل شمعة — قبل/بعد التحسين.
"""
import asyncio
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.backtest.engine1 import BacktestEngine
from app.backtest.schemas import BacktestConfig
from app.services.data_service import DataService


def load_df(symbol: str, interval: str, max_rows: int = None) -> pd.DataFrame:
    df = pd.read_parquet(PROJECT_ROOT / "data" / "history" / f"{symbol}_{interval}.parquet")
    if max_rows:
        df = df.tail(max_rows)
    return df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
    strategy_file = sys.argv[2] if len(sys.argv) > 2 else "volume_climax_reversal_pro.json"

    raw = (PROJECT_ROOT / "strategies" / strategy_file).read_text()
    import json
    strategy_cfg = json.loads(raw)

    df = load_df("BTCUSDT", "1m", max_rows=n)
    print(f"Data: BTCUSDT 1m — {len(df):,} bars "
          f"({df.index[0]} → {df.index[-1]})")

    ds = DataService()
    engine = BacktestEngine(ds)

    config = BacktestConfig(
        name=f"Benchmark {strategy_file}",
        symbols=["BTCUSDT"],
        timeframe="1m",
        initial_capital=10_000.0,
        commission_rate=0.001,
        slippage_percent=0.0005,
        position_size_percent=0.95,
        strategy_config=strategy_cfg,
    )

    t0 = time.perf_counter()
    result = await engine.run_backtest(config)
    elapsed = time.perf_counter() - t0

    total_bars = len(df)
    print(f"Backtest wall time : {elapsed:.2f}s")
    print(f"Throughput         : {total_bars / elapsed:,.0f} bars/s")
    print(f"Trades             : {len(result.trades)}")
    print(f"Visual candles     : {len(result.visual_candles):,} (sampled)")
    print(f"Equity points      : {len(result.equity_curve):,}")
    m = result.metrics
    print(f"Total return       : {m.total_return_pct if hasattr(m, 'total_return_pct') else m.get('total_return_pct', '—')}")


if __name__ == "__main__":
    asyncio.run(main())
