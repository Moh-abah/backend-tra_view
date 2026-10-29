#!/usr/bin/env python3
"""
run_year_backtests.py — مصفوفة باك-تيست سنة كاملة (BTC & ETH × كل الفريمات × الاستراتيجيات)
============================================================================================
- يغذي المحرك الحقيقي (BacktestEngine) ببيانات محلية Parquet (جلبناها مسبقاً بسلامة 100%)
  عبر DataService محلي بنفس الواجهة — المسار الحقيقي كله عدا طبقة الشبكة.
- يشغّل كل (رمز × فريم × استراتيجية) ويسجل المقاييس كاملة تدريجياً في JSON
  (تدريجي: أي انقطاع يحفظ ما سبق — كما طلب المستخدم).
- يضيف مرجع Buy & Hold لكل (رمز × فريم).

Usage:
  python scripts/run_year_backtests.py                 # المصفوفة الكاملة
  python scripts/run_year_backtests.py --quick         # عينة سريعة (1h فقط)
  python scripts/run_year_backtests.py --symbols BTCUSDT --intervals 1m,5m
"""

import argparse
import asyncio
import json
import logging
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
logging.disable(logging.WARNING)

REPORT_DIR = PROJECT_ROOT / "reports"
HIST_DIR = PROJECT_ROOT / "data" / "history"


# ============================================================================
# DataService محلي: نفس واجهة get_historicallastvirsion لكن من Parquet
# ============================================================================
class LocalParquetDataService:
    """بديلDataService للباك-تيست أوفلاين: يقرأ data/history/{SYMBOL}_{TF}.parquet"""

    def __init__(self):
        self._cache = {}

    def _load(self, symbol: str, timeframe: str) -> pd.DataFrame:
        key = (symbol, timeframe)
        if key not in self._cache:
            path = HIST_DIR / f"{symbol}_{timeframe}.parquet"
            if not path.exists():
                raise FileNotFoundError(f"No local history for {symbol} {timeframe}: {path}")
            df = pd.read_parquet(path)
            self._cache[key] = df
        return self._cache[key]

    async def get_historicallastvirsion(self, symbol, timeframe, market="crypto",
                                        start_date=None, end_date=None, use_cache=True):
        return await self.get_historical_last_version(symbol, timeframe, market,
                                                      start_date, end_date, use_cache)

    async def get_historical_last_version(self, symbol, timeframe, market="crypto",
                                          start_date=None, end_date=None, use_cache=True):
        df = self._load(symbol, timeframe)
        out = df
        if start_date is not None:
            sd = pd.Timestamp(start_date)
            if sd.tzinfo is None:
                sd = sd.tz_localize("UTC")
            out = out[out.index >= sd]
        if end_date is not None:
            ed = pd.Timestamp(end_date)
            if ed.tzinfo is None:
                ed = ed.tz_localize("UTC")
            out = out[out.index <= ed]
        return out.copy()


# ============================================================================
# الاستراتيجيات المشاركة
# ============================================================================
def get_all_strategies():
    from app.services.strategy.strategys.rsi_strategy import get_rsi_strategy
    from app.services.strategy.strategys.macd_strategy import get_macd_strategy
    from app.services.strategy.strategys.trend_strategy import get_trend_strategy
    from app.services.strategy.strategys.mean_reversion_strategy import get_mean_reversion_strategy

    strategies = {
        "RSI Basic (builtin)": get_rsi_strategy(),
        "MACD (builtin)": get_macd_strategy(),
        "Trend MA (builtin)": get_trend_strategy(),
        "Mean Reversion (builtin)": get_mean_reversion_strategy(),
    }
    for fname in ("volume_climax_reversal_pro.json", "macd_zero_line_momentum.json",
                  "bollinger_oversold_sniper.json"):
        p = PROJECT_ROOT / "strategies" / fname
        strategies[p.stem + " (custom)"] = json.loads(p.read_text())
    return strategies


SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"]


async def run_one(engine, symbol, timeframe, strat_name, strategy_cfg, bounds) -> dict:
    start_ts, end_ts = bounds[symbol][timeframe]
    config = BacktestConfig(
        name=f"{symbol} {timeframe} {strat_name}",
        symbols=[symbol],
        timeframe=timeframe,
        start_date=start_ts.to_pydatetime(),
        end_date=end_ts.to_pydatetime(),
        initial_capital=10_000.0,
        commission_rate=0.001,          # 0.1% — commission حقيقي Binance spot taker
        slippage_percent=0.0005,        # 0.05%
        position_size_percent=0.95,
        strategy_config=strategy_cfg,
    )
    t0 = time.perf_counter()
    result = await engine.run_backtest(config)
    elapsed = time.perf_counter() - t0

    n_bars = bounds_n[(symbol, timeframe)]
    metrics = {
        "symbol": symbol, "timeframe": timeframe, "strategy": strat_name,
        "bars": n_bars, "start_utc": str(start_ts), "end_utc": str(end_ts),
        "execution_seconds": round(elapsed, 2),
        "bars_per_second": round(n_bars / elapsed, 0) if elapsed > 0 else None,
        "total_trades": int(getattr(result, "total_trades", 0) or 0),
        "win_rate_pct": round(float(getattr(result, "win_rate", 0.0) or 0.0), 2),
        "total_return_pct": round(float(getattr(result, "total_pnl_percent", 0.0) or 0.0), 3),
        "final_capital": round(float(getattr(result, "final_capital", 0.0) or 0.0), 2),
        "profit_factor": (None if getattr(result, "profit_factor", None) is None
                          else round(float(result.profit_factor), 3)),
        "sharpe": round(float(getattr(result, "sharpe_ratio", 0.0) or 0.0), 3),
        "sortino": round(float(getattr(result, "sortino_ratio", 0.0) or 0.0), 3),
        "calmar": round(float(getattr(result, "calmar_ratio", 0.0) or 0.0), 3),
        "max_drawdown_pct": round(float(getattr(result, "max_drawdown_percent", 0.0) or 0.0), 2),
        "avg_trade_duration_hours": round(float(getattr(result, "avg_trade_duration_hours", 0.0) or 0.0), 2),
        "expectancy": round(float(getattr(result, "expectancy", 0.0) or 0.0), 4),
        "visual_candles": len(getattr(result, "visual_candles", []) or []),
        "equity_points": len(getattr(result, "equity_curve", []) or []),
    }
    return metrics


def buy_and_hold(symbol, timeframe) -> dict:
    df = pd.read_parquet(HIST_DIR / f"{symbol}_{timeframe}.parquet")
    first_open = float(df["open"].iloc[0])
    last_close = float(df["close"].iloc[-1])
    ret = (last_close / first_open - 1.0) * 100.0
    return {"symbol": symbol, "timeframe": timeframe,
            "return_pct": round(ret, 2),
            "first_open": first_open, "last_close": last_close}


async def main():
    global BacktestConfig, bounds_n
    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig

    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="فريم 1h فقط (عينة سريعة)")
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--intervals", default=None)
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    intervals = ([i.strip() for i in args.intervals.split(",")] if args.intervals
                 else (["1h"] if args.quick else INTERVALS))

    # حدود كل (رمز × فريم) من ملفات parquet نفسها
    bounds = {}
    global bounds_n
    bounds_n = {}
    for s in symbols:
        bounds[s] = {}
        for tf in intervals:
            df = pd.read_parquet(HIST_DIR / f"{s}_{tf}.parquet")
            bounds[s][tf] = (df.index[0], df.index[-1])
            bounds_n[(s, tf)] = len(df)

    strategies = get_all_strategies()
    ds = LocalParquetDataService()
    engine = BacktestEngine(ds)

    jobs = []
    # الترتيب: الأثقل أولاً (1m) ليُنجز مبكراً؟ لا — تدريجياً: الأخف أولاً
    # لتظهر نتائج سريعة، ثم 1m الأخير (كما طلب المستخدم: تدريجي حتى السنة)
    ordered_intervals = [tf for tf in INTERVALS if tf in intervals]
    for tf in ordered_intervals:
        for s in symbols:
            for strat_name, cfg in strategies.items():
                jobs.append((s, tf, strat_name, cfg))

    REPORT_DIR.mkdir(exist_ok=True)
    out_json = REPORT_DIR / "backtest_results.json"
    results = []
    if out_json.exists():
        try:
            results = json.loads(out_json.read_text())
            done_keys = {(r["symbol"], r["timeframe"], r["strategy"]) for r in results}
            jobs = [j for j in jobs if (j[0], j[1], j[2]) not in done_keys]
        except Exception:
            results = []

    print(f"Matrix: {len(jobs)} runs | symbols={symbols} intervals={ordered_intervals}", flush=True)

    for idx, (s, tf, strat_name, cfg) in enumerate(jobs, 1):
        n = bounds_n[(s, tf)]
        print(f"[{idx}/{len(jobs)}] {s} {tf} {strat_name} ({n:,} bars)...", flush=True)
        t0 = time.perf_counter()
        try:
            m = await run_one(engine, s, tf, strat_name, cfg, bounds)
            results.append(m)
            print(f"    → trades={m['total_trades']} ret={m['total_return_pct']}% "
                  f"wr={m['win_rate_pct']}% pf={m['profit_factor']} "
                  f"dd={m['max_drawdown_pct']}% in {m['execution_seconds']}s "
                  f"({m['bars_per_second']:,} bars/s)", flush=True)
        except Exception as e:
            results.append({"symbol": s, "timeframe": tf, "strategy": strat_name,
                            "status": "ERROR", "error": f"{type(e).__name__}: {e}",
                            "trace": traceback.format_exc()[-1500:]})
            print(f"    → ERROR: {e}", flush=True)
        # حفظ تدريجي ذرّي (atomic) بعد كل تشغيل — آمن ضد الانقطاع
        tmp = out_json.with_suffix(".tmp")
        tmp.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        tmp.replace(out_json)

    print(f"\nSaved {len(results)} results → {out_json}", flush=True)
    print("MATRIX_DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
