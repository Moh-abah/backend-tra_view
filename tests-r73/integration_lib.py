#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""مكتبة التكامل الكامل PRO73 — المسار الإنتاجي نفسه (StrategyEngine →
ind_zzfetm_*/ind_zzfbm_* → قرارات → صفقات بنموذج next_open).

مشتركة بين: بطارية PRO73 (القسم F) وسكربت تحقق البطل 1651.25% — تُستدعى في
عملية مستقلة لكل نافذة (عزل الذاكرة: نسخ المستند الـ67 تستهلك ~1.6GB).
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any, Dict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [os.path.join(HERE, ".."), os.path.join(HERE, "..", "src"), HERE]
SRC = next((p for p in CANDIDATES
            if os.path.isfile(os.path.join(p, "app", "services", "indicators", "mtf_oscillator_core.py"))),
           CANDIDATES[0])
if SRC not in sys.path:
    sys.path.insert(0, os.path.abspath(SRC))

os.environ.setdefault("SECRET_KEY", "pro73-integration-secret-key-0123456789")
os.environ.setdefault("DEBUG", "true")

DATA_CANDIDATES = [
    "/home/z/my-project/r70-workspace/data/SOLUSDT_1m.npz",
    os.path.join(HERE, "..", "..", "..", "r70-workspace", "data", "SOLUSDT_1m.npz"),
]
DATA_PATH = next((p for p in DATA_CANDIDATES if os.path.isfile(p)), None)


def load_window_arrays(from_ms: int, to_ms: int):
    """نافذة SOL 1m → (t, o, h, l, c, v, df) — df بفهرس زمني جاهز للمحرك."""
    if DATA_PATH is None:
        raise FileNotFoundError("ملف بيانات SOL غير موجود")
    z = np.load(DATA_PATH)
    t = z["time_ms"].astype(np.int64)
    m = (t >= from_ms) & (t < to_ms)
    T = t[m]
    if not len(T):
        raise ValueError("نافذة فارغة")
    O = z["open"][m].astype(np.float64)
    H = z["high"][m].astype(np.float64)
    L = z["low"][m].astype(np.float64)
    C = z["close"][m].astype(np.float64)
    V = z["volume"][m].astype(np.float64)
    df = pd.DataFrame({"open": O, "high": H, "low": L, "close": C, "volume": V},
                      index=pd.DatetimeIndex(pd.to_datetime(T, unit="ms", utc=True), name="time"))
    return T, O, H, L, C, V, df


def run_integration(strategy_config_payload: Dict[str, Any], T, O, H, L, C, V, df,
                    label: str = "") -> Dict[str, Any]:
    """المسار الإنتاجي الحرفي (نفس بطارية PRO73-F): قرارات → صفقات next_open."""
    from app.services.strategy.schemas import StrategyConfig
    from app.services.strategy.strategy_engine1 import StrategyEngine, DecisionAction

    n = len(df)

    async def _run():
        cfg = StrategyConfig(**strategy_config_payload)
        engine = StrategyEngine(cfg)
        t0 = time.perf_counter()
        full = await engine._prepare_indicators(df)
        engine.full_data = full
        prep_s = time.perf_counter() - t0
        osc_cols = [c for c in full.columns if c.startswith("ind_zzfetm_") or c.startswith("ind_zzfbm_")]
        trades = []
        state = None
        n_buy = n_exit = 0
        t1 = time.perf_counter()
        for i in range(n - 1):
            decision = await engine.run(full, current_index=i, in_position=(state is not None))
            act = decision.action
            if act == DecisionAction.BUY and state is None:
                state = {"entry_bar": i, "entry_price": float(O[i + 1]), "reason": decision.reason}
                n_buy += 1
            elif state is not None and (
                    (isinstance(decision.metadata, dict) and decision.metadata.get("trigger") == "exit_rule")
                    or act == DecisionAction.SELL):
                exit_price = float(O[i + 1])
                trades.append({
                    "entry_bar": state["entry_bar"], "exit_bar": i,
                    "entry": state["entry_price"], "exit": exit_price,
                    "pnl_pct": (exit_price - state["entry_price"]) / state["entry_price"] * 100,
                    "entry_reason": state["reason"], "exit_reason": decision.reason,
                    "entry_t": int(T[state["entry_bar"]]), "exit_t": int(T[i]),
                })
                state = None
                n_exit += 1
        loop_s = time.perf_counter() - t1
        if state is not None:
            trades.append({
                "entry_bar": state["entry_bar"], "exit_bar": n - 1,
                "entry": state["entry_price"], "exit": float(C[-1]),
                "pnl_pct": (float(C[-1]) - state["entry_price"]) / state["entry_price"] * 100,
                "entry_reason": state["reason"], "exit_reason": "end-of-window",
                "entry_t": int(T[state["entry_bar"]]), "exit_t": int(T[n - 1]),
            })
        return trades, n_buy, n_exit, osc_cols, prep_s, loop_s

    trades, n_buy, n_exit, osc_cols, prep_s, loop_s = asyncio.run(_run())
    wins = sum(1 for tr in trades if tr["pnl_pct"] > 0)
    total_ret = sum(tr["pnl_pct"] for tr in trades)
    if label:
        print(f"  [{label}] prep={prep_s:.1f}s loop={loop_s:.1f}s | أعمدة ماكدية={len(osc_cols)} | "
              f"BUY={n_buy} خروج={n_exit} | صفقات={len(trades)} (رابحة {wins}) | مجموع العوائد={total_ret:.2f}%")
    return {
        "osc_columns": len(osc_cols), "buys": n_buy, "trades": len(trades), "wins": wins,
        "total_return_pct": round(total_ret, 4), "prep_s": round(prep_s, 2), "loop_s": round(loop_s, 2),
        "sample_reasons": sorted({tr["entry_reason"] for tr in trades})[:4],
        "trades_full": trades,
    }
