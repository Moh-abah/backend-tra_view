"""Shared DataFrame utilities.

``ensure_datetime_index`` normalizes candle DataFrames to a DatetimeIndex.

Why: ``DataService.get_historical`` returns a RangeIndex (0..n) with a
``time`` column in epoch milliseconds. The backtest engine (engine1) already
converts this centrally, but the direct strategy endpoints
(``/strategies/run``, ``/strategies1/run*``) consumed the raw frame, so any
code doing ``data.index[i].isoformat()`` or
``(t2 - t1).total_seconds()`` crashed with
``'int' object has no attribute ...`` — the "0 signals / generic failure"
class of bugs. This helper mirrors engine1's logic in one place.
"""

from __future__ import annotations

import pandas as pd


def ensure_datetime_index(data: pd.DataFrame) -> pd.DataFrame:
    """Guarantee a UTC DatetimeIndex for candle simulation/decision engines.

    - Already DatetimeIndex  → returned untouched.
    - Has a ``time`` column (epoch ms) → converted; the column is dropped.
    - Index is coercible to datetime (ISO strings etc.) → converted in place.
    - Anything else → returned unchanged (callers keep working as before).
    """
    if isinstance(data.index, pd.DatetimeIndex):
        return data

    if "time" in data.columns:
        t = pd.to_datetime(data["time"], unit="ms", utc=True, errors="coerce")
        if len(t) and t.notna().all():
            out = data.copy()
            out.index = pd.DatetimeIndex(t, name="time")
            return out.drop(columns=["time"])

    try:
        coerced = pd.to_datetime(data.index, utc=True, errors="raise")
        out = data.copy()
        out.index = pd.DatetimeIndex(coerced)
        return out
    except Exception:  # noqa: BLE001 — best effort; keep original frame
        return data
