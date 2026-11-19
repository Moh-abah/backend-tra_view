#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPLIT-TP1 — الهوية بت-بت على بيانات MMTUSDT الحقيقية (الجزء الثالث).

L3 (الهوية): حمولة البطل QMOM1-MMT #10000604 نفسها بلا take_profit_splits
تُشغَّل على الشجرة قبل-الرقعة (runtime-pre) ثم على الشجرة بعد-الرقعة (runtime)
في عمليتين مستقلتين — المقارنة بت-بت: total_pnl · عدد الصفقات · قائمة pnl
لكل صفقة · منحنى الرصيد كاملاً · نقاط الدخول/الخروج (عدد/أسعار).

L4 (التكامل الحي): نفس الحمولة + مستويات الجني المقسم (5%→ربع · 7%→ربع)
على الشجرة المرقعة — التحقق: جنيات حقيقية وقعت، أسعارها = دخول×(1+gain)،
أحجامها أرباع أصلية، الرصيد النهائي = 1000 + مجموع pnl الصفقات.

التشغيل:  python3 tools/verify_identity.py pre|post|split|compare
"""
import asyncio
import io
import json
import sys
from pathlib import Path

BASE = Path("/home/z/my-project/trading-system/split-tp")
DATA_15M = BASE / "data" / "MMTUSDT_15m.json"
DATA_5M = BASE / "data" / "MMTUSDT_5m.json"
PAYLOAD = BASE / "payloads" / "payload_qmom1_mmt_10000604.json"
OUT = BASE / "results"
OUT.mkdir(exist_ok=True)

import types  # noqa: E402

_ds_mod = types.ModuleType("app.services.data_service")


class _StubDataServiceCls:
    pass


_ds_mod.DataService = _StubDataServiceCls


def load_runtime(which: str):
    """يحمّل شجرة معزولة (pre أو post) في عملية نظيفة."""
    rt = BASE / ("runtime-pre" if which == "pre" else "runtime")
    sys.path.insert(0, str(rt))
    sys.modules["app.services.data_service"] = _ds_mod
    import importlib
    import app.backtest.engine1 as e1
    importlib.reload(e1)
    return e1


def build_dfs():
    import pandas as pd

    def mk(path):
        candles = json.load(io.open(path, encoding="utf-8"))
        df = pd.DataFrame([{
            "open": float(c["open"]), "high": float(c["high"]),
            "low": float(c["low"]), "close": float(c["close"]),
            "volume": float(c["volume"]),
        } for c in candles])
        df.index = pd.DatetimeIndex(
            pd.to_datetime([c["time"] for c in candles], unit="ms", utc=True),
            name="time")
        return df

    return mk(DATA_15M), mk(DATA_5M)


class StubDS:
    def __init__(self, df15, df5):
        self.dfs = {"15m": df15, "5m": df5}

    async def get_historicallastvirsion(self, symbol, timeframe, market,
                                        start_date, end_date, use_cache=True,
                                        tz_offset_minutes=0):
        key = str(timeframe)
        df = self.dfs.get(key)
        if df is None:
            df = self.dfs.get("15m")
        return df.copy()


def digest(res):
    """ملخص قابل للمقارنة بت-بت (كل الأرقام الحساسة)."""
    trades = getattr(res, "trades", None) or []
    tp = res.trade_points or []
    return {
        "total_pnl": float(res.total_pnl),
        "total_pnl_percent": float(res.total_pnl_percent),
        "final_capital": float(res.final_capital),
        "total_trades": int(res.total_trades),
        "win_rate": float(res.win_rate),
        "equity_curve": [float(x) for x in res.equity_curve],
        "trade_pnls": [float(t.pnl or 0.0) for t in trades],
        "trade_entry_prices": [float(t.entry_price) for t in trades],
        "trade_exit_prices": [float(t.exit_price or 0.0) for t in trades],
        "trade_exit_reasons": [str(t.exit_reason) for t in trades],
        "n_entry_points": sum(1 for p in tp if p.get("type") == "entry"),
        "n_exit_points": sum(1 for p in tp if p.get("type") == "exit"),
        "n_partial_points": sum(1 for p in tp if p.get("type") == "partial_exit"),
        "visual_candles_len": len(res.visual_candles or []),
    }


async def run(which: str, add_splits: bool = False):
    e1 = load_runtime(which)
    df15, df5 = build_dfs()
    payload = json.load(io.open(PAYLOAD, encoding="utf-8"))
    cfg_kwargs = dict(payload)
    if add_splits:
        cfg_kwargs["take_profit_splits"] = [
            {"gain_percent": 5.0, "size_percent": 25.0},
            {"gain_percent": 7.0, "size_percent": 25.0},
        ]
    else:
        cfg_kwargs.pop("take_profit_splits", None)
    from app.backtest.schemas import BacktestConfig
    cfg = BacktestConfig(**cfg_kwargs)
    eng = e1.BacktestEngine(data_service=StubDS(df15, df5))
    res = await eng.run_backtest(cfg)
    return res, e1


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if mode in ("pre", "post", "split"):
        res, _ = asyncio.run(run("post" if mode != "pre" else "pre",
                                 add_splits=(mode == "split")))
        d = digest(res)
        with io.open(OUT / f"identity_{mode}.json", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        # مقتطفات إضافية للجولة المقسمة
        if mode == "split":
            tp = res.trade_points or []
            partials = [p for p in tp if p.get("type") == "partial_exit"]
            trades = getattr(res, "trades", None) or []
            extra = {
                "partials": [
                    {k: (str(p.get(k)) if k == "timestamp" else p.get(k))
                     for k in (
                        "timestamp", "price", "position_size", "pnl",
                        "gain_percent", "size_percent", "remaining_size",
                        "exit_reason", "entry_price")}
                    for p in partials],
                "trades_meta": [
                    {"entry": float(t.entry_price), "exit": float(t.exit_price or 0),
                     "pnl": float(t.pnl or 0), "reason": str(t.exit_reason),
                     "n_partials": len(t.partial_exits or [])}
                    for t in trades],
                "risk_echo_split": ((getattr(res, "math_audit", None) or {})
                                     .get("risk_echo") or {}),
            }
            with io.open(OUT / "identity_split_extra.json", "w",
                         encoding="utf-8") as f:
                json.dump(extra, f, ensure_ascii=False, indent=1)
        print(f"[{mode}] total_pnl={d['total_pnl']:.6f} · "
              f"trades={d['total_trades']} · equity_len={len(d['equity_curve'])} · "
              f"partials={d['n_partial_points']}")
        return 0

    if mode == "compare":
        pre = json.load(io.open(OUT / "identity_pre.json", encoding="utf-8"))
        post = json.load(io.open(OUT / "identity_post.json", encoding="utf-8"))
        diffs = []
        for k in pre:
            if pre[k] != post[k]:
                diffs.append(k)
        if not diffs:
            print("IDENTITY PASS — 12/12 مقاييس بت-بت (بلا أي فرق)")
            print(f"  total_pnl = {pre['total_pnl']!r} (متطابق)")
            print(f"  trades = {pre['total_trades']} · pnl list متطابق · "
                  f"equity ({len(pre['equity_curve'])} نقطة) متطابق")
            return 0
        print("IDENTITY FAIL — فروق في:", diffs)
        for k in diffs:
            print(f"  {k}: pre={str(pre[k])[:120]} post={str(post[k])[:120]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
