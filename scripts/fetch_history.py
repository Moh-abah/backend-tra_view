#!/usr/bin/env python3
"""
fetch_history.py — جلب البيانات التاريخية الحقيقية من Binance REST
====================================================================
يجلب شموع Spot لرموز وفريمات متعددة لسنة كاملة سابقة، مع:
  - ترقيم صفحات كامل (limit=1000/طلب) في الاتجاهين (قديم→جديد)
  - تخزين Parquet في data/history/{SYMBOL}_{INTERVAL}.parquet
  - تقرير سلامة بيانات (فجوات، NaN، صلاحية OHLC، الحجم) → data/history/_integrity.json
  - إعادة المحاولة عند الفشل الشبكي (429/418/backoff)

Usage:
  python scripts/fetch_history.py --symbols BTCUSDT,ETHUSDT \
      --intervals 1m,5m,15m,1h,4h,1d --days 366
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BINANCE_BASE = "https://api.binance.com"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data" / "history"

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}

COLUMNS = ["open_time", "open", "high", "low", "close", "volume",
           "close_time", "quote_volume", "trades",
           "taker_buy_base", "taker_buy_quote"]


def http_get_json(url: str, retries: int = 6, timeout: int = 20):
    """GET مع backoff أسّي عند 429/418/5xx وأخطاء الشبكة."""
    delay = 1.0
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "trading-backend-validation/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 418) or e.code >= 500:
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError(f"GET failed after {retries} retries: {url} — {last_err}")


def fetch_range(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """يجلب كل الشموع بين start_ms و end_ms (شمعة [start,end))."""
    step = INTERVAL_MS[interval]
    all_rows = []
    cur = start_ms
    while cur < end_ms:
        url = (f"{BINANCE_BASE}/api/v3/klines?symbol={symbol}&interval={interval}"
               f"&startTime={cur}&endTime={end_ms - 1}&limit=1000")
        batch = http_get_json(url)
        if not batch:
            break
        all_rows.extend(batch)
        last_open = int(batch[-1][0])
        cur = last_open + step
        if len(batch) < 1000:
            # لا مزيد من البيانات في هذا النطاق
            if last_open + step >= end_ms:
                break
    df = pd.DataFrame(all_rows)
    if df.empty:
        return df
    # الأعمدة الـ 11 الأولى كافية؛ Binance قد يضيف ignore حقل
    df = df.iloc[:, :11]
    df.columns = COLUMNS
    # إزالة التكرارات وترتيب
    df = df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    for c in ["open", "high", "low", "close", "volume", "quote_volume",
              "taker_buy_base", "taker_buy_quote"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    df["trades"] = pd.to_numeric(df["trades"], errors="coerce").fillna(0).astype("int64")
    df["open_time"] = df["open_time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    return df


def check_integrity(df: pd.DataFrame, interval: str) -> dict:
    """فحص شامل لسلامة الشموع."""
    report = {}
    step = INTERVAL_MS[interval]
    n = len(df)
    report["rows"] = n
    if n == 0:
        return {"rows": 0, "status": "EMPTY"}

    ts = df["open_time"].to_numpy()
    report["first_utc"] = datetime.fromtimestamp(ts[0] / 1000, tz=timezone.utc).isoformat()
    report["last_utc"] = datetime.fromtimestamp(ts[-1] / 1000, tz=timezone.utc).isoformat()

    # 1) الترتيب والفجوات
    diffs = np.diff(ts)
    expected_gaps = int((diffs != step).sum())
    gap_values = diffs[diffs != step]
    report["gap_count"] = expected_gaps
    report["gap_details_ms"] = [int(g) for g in gap_values[:10]]
    report["sorted"] = bool((diffs > 0).all())
    report["duplicates"] = int((diffs == 0).sum())

    # 2) NaN
    ohlcv = df[["open", "high", "low", "close", "volume"]].to_numpy()
    report["nan_ohlcv"] = int(np.isnan(ohlcv).sum())

    # 3) صلاحية OHLC
    o, h, l, c = df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    v = df["volume"].to_numpy()
    valid = (~np.isnan(ohlcv).any(axis=1))
    bad_high = int(((h < np.maximum(o, c)) | (h <= 0))[valid].sum())
    bad_low = int(((l > np.minimum(o, c)) | (l <= 0))[valid].sum())
    bad_vol = int((v < 0)[valid].sum())
    nonpositive = int((~(o > 0)).sum())
    report["bad_high"] = bad_high
    report["bad_low"] = bad_low
    report["bad_volume"] = bad_vol
    report["nonpositive_price"] = nonpositive

    # 4) نسبة الاكتمال المتوقع
    expected_rows = (end := ts[-1]) and None  # placeholder to keep linter calm
    span = ts[-1] - ts[0] + step
    expected = span // step
    report["expected_rows_in_span"] = int(expected)
    report["completeness_pct"] = round(100.0 * n / expected, 4) if expected else 0.0

    ok = (report["nan_ohlcv"] == 0 and bad_high == 0 and bad_low == 0
          and bad_vol == 0 and nonpositive == 0 and report["sorted"]
          and report["duplicates"] == 0)
    report["status"] = "OK" if ok else "ISSUES"
    return report


def fetch_one(symbol: str, interval: str, days: int) -> dict:
    out_path = OUT_DIR / f"{symbol}_{interval}.parquet"
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    t0 = time.perf_counter()
    df = fetch_range(symbol, interval, start_ms, end_ms)
    elapsed = time.perf_counter() - t0

    if df.empty:
        return {"symbol": symbol, "interval": interval, "status": "EMPTY"}

    df["dt"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("dt").drop(columns=["open_time"])
    df.to_parquet(out_path, index=True)

    # إعادة القراءة للفحص (تحقق من الملف المخزّن)
    back = pd.read_parquet(out_path)
    rep = check_integrity(back.reset_index().rename(columns={"dt": "open_time"}).assign(
        open_time=lambda d: (d["open_time"].astype("int64") // 1_000_000)
    ), interval)
    rep.update({
        "symbol": symbol, "interval": interval,
        "file": str(out_path.relative_to(PROJECT_ROOT)),
        "fetch_seconds": round(elapsed, 1),
        "bars_per_second": round(len(df) / elapsed, 0) if elapsed > 0 else None,
    })
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    ap.add_argument("--intervals", default="1m,5m,15m,1h,4h,1d")
    ap.add_argument("--days", type=int, default=366)
    ap.add_argument("--workers", type=int, default=3, help="طلبات متوازية (احترام حدود Binance)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    intervals = [i.strip() for i in args.intervals.split(",") if i.strip()]
    for iv in intervals:
        if iv not in INTERVAL_MS:
            print(f"UNKNOWN INTERVAL: {iv}", file=sys.stderr)
            sys.exit(2)

    jobs = [(s, iv) for s in symbols for iv in intervals]
    print(f"Fetching {len(jobs)} series: {symbols} × {intervals} × {args.days}d")
    results = []
    # 1m هو الأثقل — شغّله أولاً
    jobs.sort(key=lambda j: INTERVAL_MS[j[1]])

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_one, s, iv, args.days): (s, iv) for s, iv in jobs}
        for fut in as_completed(futs):
            s, iv = futs[fut]
            try:
                rep = fut.result()
            except Exception as e:
                rep = {"symbol": s, "interval": iv, "status": "ERROR", "error": str(e)}
            results.append(rep)
            print(f"  [{rep.get('status','?'):7}] {s} {iv:>3} rows={rep.get('rows','—')} "
                  f"completeness={rep.get('completeness_pct','—')}% "
                  f"fetch={rep.get('fetch_seconds','—')}s")

    results.sort(key=lambda r: (r.get("symbol", ""), r.get("interval", "")))
    out_json = OUT_DIR / "_integrity.json"
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    all_ok = all(r.get("status") == "OK" for r in results)
    print(f"\nIntegrity report → {out_json}")
    print("ALL_OK" if all_ok else "SOME_ISSUES — see report")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
