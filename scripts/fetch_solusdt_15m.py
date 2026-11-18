#!/usr/bin/env python3
"""fetch_solusdt_15m.py — جلب كامل تاريخ SOLUSDT 15m من Binance إلى Parquet.

نسخة متوازية (12 عاملاً) — نفس صيغة data/history: time(ms)/open/high/low/close/volume.
"""
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "data" / "history" / "SOLUSDT_15m.parquet"

BASE_URL = "https://api.binance.com/api/v3/klines"
SYMBOL = "SOLUSDT"
INTERVAL = "15m"
LIMIT = 1000
WORKERS = 12

START_MS = int(pd.Timestamp("2020-03-16T00:00:00Z").timestamp() * 1000)
END_MS = int(time.time() * 1000)


def fetch_range(start_ms: int, end_ms: int) -> list:
    """جلب كل الشموع في نطاق زمني (متسلسل داخل النطاق)."""
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        url = (f"{BASE_URL}?symbol={SYMBOL}&interval={INTERVAL}"
               f"&startTime={cursor}&limit={LIMIT}")
        for attempt in range(5):
            try:
                r = subprocess.run(
                    ["curl", "-s", "--max-time", "30", url],
                    capture_output=True, text=True, timeout=40)
                batch = json.loads(r.stdout)
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(1 + attempt)
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        last_open = batch[-1][0]
        if len(batch) < LIMIT or last_open >= end_ms:
            break
        cursor = last_open + 1
    return rows


def main():
    # تقسيم النطاق إلى أجزاء بالتساوي على العمال
    span = (END_MS - START_MS) // WORKERS + 1
    ranges = [(START_MS + i * span, min(START_MS + (i + 1) * span, END_MS))
              for i in range(WORKERS)]
    print(f"Fetching SOLUSDT {INTERVAL} with {WORKERS} workers "
          f"({pd.Timestamp(START_MS, unit='ms', tz='UTC')} → now)", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(lambda rg: fetch_range(*rg), ranges))
    rows = [r for part in results for r in part]
    if not rows:
        print("NO DATA", flush=True)
        sys.exit(1)
    df = pd.DataFrame(rows, columns=[
        "time", "open", "high", "low", "close", "volume",
        "close_time", "qav", "trades", "tbb", "tbq", "ignore"])
    df = df[["time", "open", "high", "low", "close", "volume"]].copy()
    df["time"] = df["time"].astype("int64")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"SAVED {len(df):,} rows -> {OUT}", flush=True)
    print(f"RANGE: {pd.Timestamp(df['time'].iloc[0], unit='ms', tz='UTC')} -> "
          f"{pd.Timestamp(df['time'].iloc[-1], unit='ms', tz='UTC')}", flush=True)
    print("FETCH_DONE", flush=True)


if __name__ == "__main__":
    main()
