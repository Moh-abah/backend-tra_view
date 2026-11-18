#!/usr/bin/env python3
"""champion_ab_harness.py — منصة تشغيل باك-تست البطل أوفلاين (A/B).

تشغيل:
  python3 champion_ab_harness.py <project_root> [zone_exit_resolution] [zone_exit_length] [arm_after_gain_pct]

يقرأ حمولة البطل payloads/zlf_almighty_quantum_ema_full_history.json من جذر
المشروع المعطى، ويشغل محرك الباك تست الحقيقي (engine1) ببيانات parquet
المحلية، ويطبع المقاييس + بصمة الصفقات (hash) للمقارنة بت-بت.

المعلمات الاختيارية:
  zone_exit_resolution — فريم هيكل الخروج (ZONE-EXIT-TF1)
  zone_exit_length     — طول زقزاق الخروج على الفريم الأعلى
  arm_after_gain_pct   — بوابة تفعيل خروج المنطقة بعد ربح X% فوق الدخول
                         (ZONE-EXIT-ARM1 — تُحقن في exit_rules[0])
"""
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(sys.argv[1]).resolve()
ZX_RES = sys.argv[2] if len(sys.argv) > 2 else None
ZX_LEN = sys.argv[3] if len(sys.argv) > 3 else None
ARM_PCT = sys.argv[4] if len(sys.argv) > 4 else None

sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402


HIST = PROJECT_ROOT / "data" / "history"


class LocalParquetDataService:
    """بديل DataService للباك-تست أوفلاين: يقرأ data/history/{SYM}_{TF}.parquet."""

    def __init__(self):
        self._cache = {}

    def _load(self, symbol: str, timeframe: str) -> pd.DataFrame:
        key = (symbol, timeframe)
        if key not in self._cache:
            path = HIST / f"{symbol}_{timeframe}.parquet"
            if not path.exists():
                raise FileNotFoundError(f"No local history: {path}")
            df = pd.read_parquet(path)
            self._cache[key] = df
        return self._cache[key]

    async def get_historicallastvirsion(self, symbol, timeframe, market="crypto",
                                        start_date=None, end_date=None, use_cache=True,
                                        tz_offset_minutes=0):
        return await self.get_historical_last_version(
            symbol, timeframe, market, start_date, end_date, use_cache)

    async def get_historical_last_version(self, symbol, timeframe, market="crypto",
                                          start_date=None, end_date=None, use_cache=True,
                                          tz_offset_minutes=0):
        df = self._load(symbol, timeframe)
        out = df
        if start_date is not None:
            sd = pd.Timestamp(start_date)
            if sd.tzinfo is None:
                sd = sd.tz_localize("UTC")
            sd_ms = int(sd.timestamp() * 1000)
            out = out[out["time"] >= sd_ms]
        if end_date is not None:
            ed = pd.Timestamp(end_date)
            if ed.tzinfo is None:
                ed = ed.tz_localize("UTC")
            ed_ms = int(ed.timestamp() * 1000)
            out = out[out["time"] <= ed_ms]
        return out.copy()


def main():
    import logging
    logging.disable(logging.WARNING)

    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig

    payload = json.loads(
        (PROJECT_ROOT / "payloads" / "zlf_almighty_quantum_ema_full_history.json")
        .read_text(encoding="utf-8"))

    # حقن فريم هيكل الخروج عند طلبه (المعاينة فقط — الحمولة الأصلية بلا تغيير)
    if ZX_RES and ZX_RES.lower() not in ("none", "off", "-", "base"):
        params = payload["strategy_config"]["indicators"][0]["params"]
        params["zone_exit_resolution"] = ZX_RES
        if ZX_LEN and ZX_LEN.lower() not in ("none", "-", "default"):
            params["zone_exit_length"] = int(ZX_LEN)

    # ✅ ZONE-EXIT-ARM1 — حقن بوابة تفعيل الخروج بعد ربح X% (المعاينة فقط)
    if ARM_PCT and str(ARM_PCT).lower() not in ("none", "off", "-", "base", "0"):
        _arm_val = float(ARM_PCT)
        payload["strategy_config"]["exit_rules"][0]["arm_after_gain_pct"] = _arm_val

    cfg = payload
    config = BacktestConfig(
        name=cfg["name"],
        description=cfg.get("description", ""),
        mode=cfg.get("mode", "standard"),
        start_date=pd.Timestamp(cfg["start_date"]).to_pydatetime(),
        end_date=pd.Timestamp(cfg["end_date"]).to_pydatetime(),
        timeframe=cfg["timeframe"],
        timezone=cfg.get("timezone", "UTC"),
        market=cfg.get("market", "crypto"),
        symbols=cfg["symbols"],
        initial_capital=float(cfg["initial_capital"]),
        position_sizing=cfg.get("position_sizing", "fixed"),
        position_size_percent=float(cfg.get("position_size_percent", 1.0)),
        max_positions=int(cfg.get("max_positions", 1)),
        compounding=bool(cfg.get("compounding", False)),
        multi_position_compounding=bool(cfg.get("multi_position_compounding", False)),
        commission_rate=float(cfg.get("commission_rate", 0.0)),
        slippage_percent=float(cfg.get("slippage_percent", 0.0)),
        fill_model=cfg.get("fill_model", "next_open"),
        max_daily_loss_percent=float(cfg.get("max_daily_loss_percent", 5.0)),
        enable_short_selling=bool(cfg.get("enable_short_selling", False)),
        enable_margin=bool(cfg.get("enable_margin", False)),
        leverage=float(cfg.get("leverage", 1.0)),
        require_confirmation=bool(cfg.get("require_confirmation", False)),
        strategy_config=cfg["strategy_config"],
    )

    ds = LocalParquetDataService()
    engine = BacktestEngine(ds)

    t0 = time.perf_counter()
    result = asyncio.run(engine.run_backtest(config))
    elapsed = time.perf_counter() - t0

    trades = list(getattr(result, "trades", []) or [])
    metrics = {
        "project_root": str(PROJECT_ROOT),
        "zone_exit_resolution": ZX_RES or None,
        "zone_exit_length": ZX_LEN or None,
        "arm_after_gain_pct": (float(ARM_PCT) if ARM_PCT and str(ARM_PCT).lower() not in ("none", "off", "-", "base", "0") else None),
        "total_trades": int(getattr(result, "total_trades", 0) or 0),
        "win_rate_pct": round(float(getattr(result, "win_rate", 0.0) or 0.0), 4),
        "total_pnl_percent": round(float(getattr(result, "total_pnl_percent", 0.0) or 0.0), 6),
        "final_capital": round(float(getattr(result, "final_capital", 0.0) or 0.0), 6),
        "total_pnl": round(float(getattr(result, "total_pnl", 0.0) or 0.0), 6),
        "profit_factor": (None if getattr(result, "profit_factor", None) is None
                          else round(float(result.profit_factor), 6)),
        "sharpe": round(float(getattr(result, "sharpe_ratio", 0.0) or 0.0), 4),
        "sortino": round(float(getattr(result, "sortino_ratio", 0.0) or 0.0), 4),
        "calmar": round(float(getattr(result, "calmar_ratio", 0.0) or 0.0), 4),
        "max_drawdown_pct": round(float(getattr(result, "max_drawdown_percent", 0.0) or 0.0), 4),
        "avg_trade_duration_hours": round(
            float(getattr(result, "avg_trade_duration_hours", 0.0) or 0.0), 4),
        "expectancy": round(float(getattr(result, "expectancy", 0.0) or 0.0), 6),
        "execution_seconds": round(elapsed, 2),
    }

    # بصمة الصفقات (مقارنة بت-بت بين التشغيلات)
    sig_lines = []
    for tr in trades:
        sig_lines.append("|".join(str(x) for x in [
            getattr(tr, "symbol", ""), getattr(tr, "entry_time", ""),
            getattr(tr, "exit_time", ""), getattr(tr, "entry_price", ""),
            getattr(tr, "exit_price", ""), getattr(tr, "pnl", ""),
            getattr(tr, "pnl_percentage", ""), getattr(tr, "exit_reason", ""),
            getattr(tr, "size", ""), getattr(tr, "side", ""),
        ]))
    trades_hash = hashlib.sha256("\n".join(sig_lines).encode()).hexdigest()[:16]

    out = {
        "metrics": metrics,
        "trades_hash": trades_hash,
        "n_trades_listed": len(trades),
        "exit_reasons": {},
    }
    for tr in trades:
        er = str(getattr(tr, "exit_reason", ""))
        out["exit_reasons"][er] = out["exit_reasons"].get(er, 0) + 1

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    # حفظ تفاصيل الصفقات للفحص
    _tag_parts = [f"zx_{ZX_RES or 'base'}"]
    if ZX_LEN and ZX_LEN not in ("none", "-", "default"):
        _tag_parts.append(f"len{ZX_LEN}")
    if ARM_PCT and str(ARM_PCT).lower() not in ("none", "off", "-", "base", "0"):
        _tag_parts.append(f"arm{ARM_PCT}")
    tag = "_".join(_tag_parts)
    outdir = Path("/home/z/drive-download/backend_PRO95_extracted/tests-r95/results")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"ab_{tag}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (outdir / f"trades_{tag}.json").write_text(
        json.dumps(sig_lines, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"SAVED -> tests-r95/results/ab_{tag}.json")


if __name__ == "__main__":
    main()
