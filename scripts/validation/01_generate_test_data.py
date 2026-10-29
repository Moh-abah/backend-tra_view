"""Generate synthetic OHLCV datasets with KNOWN mathematical properties.

Each dataset is deterministic (seeded) so validation is reproducible:
  1. constant.csv   — flat price 100          (SMA=100, RSI≈50, ATR=0, OBV flat)
  2. linear_up.csv  — +0.5% per bar           (monotonic uptrend, RSI→100-ish, MACD>0)
  3. linear_down.csv— -0.5% per bar           (monotonic downtrend, RSI→0-ish)
  4. sawtooth.csv   — strict +2/-2 alternation (analytically computable RSI)
  5. v_shape.csv    — 200 bars down, 200 up   (known max drawdown window)
  6. random_walk.csv— seeded geometric random walk with volume bursts (realistic)
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT, exist_ok=True)


def _frame(times, opens, highs, lows, closes, vols) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
        },
        index=pd.DatetimeIndex(times, name="time"),
    )
    return df


def _hours(n: int, start="2026-01-01 00:00:00+00:00") -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq="1h", tz="UTC")


def constant(n: int = 300) -> pd.DataFrame:
    t = _hours(n)
    p = np.full(n, 100.0)
    v = np.full(n, 1000.0)
    return _frame(t, p, p, p, p, v)


def linear_up(n: int = 300, pct: float = 0.005) -> pd.DataFrame:
    t = _hours(n)
    closes = 100.0 * (1 + pct) ** np.arange(n)
    opens = np.concatenate([[100.0], closes[:-1]])
    spread = closes * 0.001
    vols = np.full(n, 1000.0)
    return _frame(t, opens, closes + spread, closes - spread, closes, vols)


def linear_down(n: int = 300, pct: float = 0.005) -> pd.DataFrame:
    df = linear_up(n, pct)
    t = df.index
    closes = 100.0 * (1 - pct) ** np.arange(n)
    opens = np.concatenate([[100.0], closes[:-1]])
    spread = closes * 0.001
    return _frame(t, opens, closes + spread, closes - spread, closes, df["volume"].values)


def sawtooth(n: int = 300) -> pd.DataFrame:
    """Strict +2 / -2 alternation around 100 → analytic RSI = 50.0 exactly
    (gains and losses average equal over the long run with Wilder smoothing)."""
    t = _hours(n)
    closes = 100.0 + np.where(np.arange(n) % 2 == 0, 0.0, 2.0)
    closes = np.concatenate([[100.0], closes[1:]])
    closes[::2] = 100.0
    closes[1::2] = 102.0
    highs = closes + 0.5
    lows = closes - 0.5
    vols = np.full(n, 1000.0)
    return _frame(t, closes, highs, lows, closes, vols)


def v_shape(n: int = 400, drop_pct: float = 0.004, rise_pct: float = 0.006) -> pd.DataFrame:
    half = n // 2
    t = _hours(n)
    down = 100.0 * (1 - drop_pct) ** np.arange(half)
    up = down[-1] * (1 + rise_pct) ** np.arange(n - half)
    closes = np.concatenate([down, up])
    opens = np.concatenate([[100.0], closes[:-1]])
    spread = closes * 0.001
    vols = np.full(n, 1000.0)
    return _frame(t, opens, closes + spread, closes - spread, closes, vols)


def random_walk(n: int = 720, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(loc=0.0002, scale=0.008, size=n)
    closes = 25000.0 * np.exp(np.cumsum(rets))  # BTC-like levels
    opens = np.concatenate([[25000.0], closes[:-1]])
    spread = np.abs(rng.normal(0, 0.002, n)) * closes
    highs = np.maximum(opens, closes) + spread
    lows = np.minimum(opens, closes) - spread
    vols = rng.lognormal(mean=6.5, sigma=0.7, size=n)
    # inject volume bursts every ~60 bars (climax test fodder)
    burst_idx = np.arange(59, n, 60)
    vols[burst_idx] *= rng.uniform(3.0, 5.0, len(burst_idx))
    return _frame(_hours(n), opens, highs, lows, closes, vols)


DATASETS = {
    "constant": constant,
    "linear_up": linear_up,
    "linear_down": linear_down,
    "sawtooth": sawtooth,
    "v_shape": v_shape,
    "random_walk": random_walk,
}

if __name__ == "__main__":
    for name, fn in DATASETS.items():
        df = fn()
        path = os.path.join(OUT, f"{name}.csv")
        df.to_csv(path)
        print(f"{name:12s} rows={len(df):4d} → {path}")
    print("All datasets generated.")
