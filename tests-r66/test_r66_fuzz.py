# -*- coding: utf-8 -*-
"""ضباب عشوائي R66 — توافق رجعي بت-بت: المحرك قبل R66 مقابل بعده.

2100 تشغيلة عشوائية بحمولات **بلا الحقول الجديدة** (كل الإعدادات
التاريخية): trades + summary + notes + window + ok يجب أن تتطابق حرفياً.
(مفتاح config مستثنى من المقارنة: صدى الإعدادات يتوسع بحقول R66
الافتراضية بالتصميم — عقد الجولة 4.1.)
"""
import importlib.util
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# يعمل في تخطيطين: <جذر>/tests-r66 مع <جذر>/src/app (بيئة التطوير)
# أو <جذر>/tests-r66 مع <جذر>/app مباشرة (جذر مشروع المستخدم).
_CANDIDATES = [os.path.join(HERE, "..", "src"), os.path.join(HERE, "..")]
SRC = next((p for p in _CANDIDATES
            if os.path.isfile(os.path.join(p, "app", "services", "exit_engine.py"))),
           _CANDIDATES[0])
sys.path.insert(0, os.path.abspath(SRC))

from app.services import exit_engine as NEW  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "exit_engine_r64_baseline", os.path.join(HERE, "exit_engine_r64_baseline.py")
)
OLD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OLD)

rng = random.Random(66666 + 66)
RUNS = 2100
mismatch = 0
total_trades = 0
total_entries = 0
total_pnl = 0.0

for run in range(RUNS):
    n = rng.randint(30, 220)
    vals = []
    p = rng.uniform(30, 90000)
    regime = 1.0
    for _ in range(n):
        if rng.random() < 0.05:
            regime = rng.choice([-1.0, 1.0])
        p = max(1.0, p * (1.0 + regime * rng.uniform(0.0, 0.04) + rng.uniform(-0.02, 0.02)))
        vals.append(round(p, 4))
    candles = []
    ts = 1735689600000
    for i, c in enumerate(vals):
        o = vals[i - 1] if i else vals[0]
        wick = rng.uniform(0.0, 0.012)
        candles.append({"time": ts + i * 60000, "open": o,
                        "high": round(max(o, c) * (1 + wick), 4),
                        "low": round(min(o, c) * (1 - wick), 4), "close": c})
    nsig = rng.randint(0, 8)
    signals = []
    for _ in range(nsig):
        b = rng.randint(1, n - 2)
        px = candles[b]["close"]
        signals.append({"bar": b, "time": candles[b]["time"], "price": px,
                        "floor": round(px * rng.uniform(0.75, 0.99), 4),
                        "floor_meta": {"source": "range"},
                        "signal": {"signal": rng.choice(["S1_Entry", "S2_Entry", "S3_Entry"]),
                                   "side": "buy"}})
    cfg = {}
    if rng.random() < 0.8:
        cfg["position_size_usd"] = float(rng.choice([20, 100, 333]))
    if rng.random() < 0.7:
        cfg["take_profit_pct"] = round(rng.uniform(0.5, 20), 1)
    if rng.random() < 0.5:
        cfg["tp_reference"] = rng.choice(["first", "avg"])
    if rng.random() < 0.6:
        cfg["dca1_trigger_pct"] = round(rng.uniform(0, 15), 1)
    if rng.random() < 0.6:
        cfg["dca2_trigger_pct"] = round(rng.uniform(0, 25), 1)
    if rng.random() < 0.5:
        cfg["max_entries"] = rng.randint(1, 5)
    if rng.random() < 0.4:
        cfg["entry_exec"] = rng.choice(["signal_close", "next_open"])
    if rng.random() < 0.3:
        cfg["cooldown_bars"] = rng.randint(0, 8)
    if rng.random() < 0.25:
        cfg["allow_overlap"] = rng.choice([True, False])
    if rng.random() < 0.2:
        cfg["max_concurrent_positions"] = rng.randint(1, 4)
    if rng.random() < 0.3:
        cfg["fees_pct"] = round(rng.uniform(0, 0.5), 2)
    if rng.random() < 0.25:
        cfg["trend_filter_sma_bars"] = rng.randint(0, 30)
    if rng.random() < 0.2:
        cfg["min_floor_distance_pct"] = round(rng.uniform(0, 8), 1)
    if rng.random() < 0.25:
        cfg["tp_trail_arm_pct"] = round(rng.uniform(0, 10), 1)
    if rng.random() < 0.25:
        cfg["tp_trail_giveback_pct"] = round(rng.uniform(0.2, 5), 1)
    if rng.random() < 0.3:
        cfg["use_trailing"] = rng.choice([True, False])
    if rng.random() < 0.4:
        cfg["trailing_giveback_pct"] = round(rng.uniform(1, 60), 1)
    if rng.random() < 0.35:
        cfg["fibo_floor_exit"] = rng.choice([True, False])
    if rng.random() < 0.5:
        cfg["stop_loss_pct"] = round(rng.uniform(0, 30), 1)

    ro = OLD.run_exit_backtest(candles, signals, dict(cfg))
    rn = NEW.run_exit_backtest(candles, signals, dict(cfg))
    total_trades += len(rn.get("trades") or [])
    total_entries += sum(len(t["entries"]) for t in rn.get("trades") or [])
    total_pnl += float(rn.get("summary", {}).get("pnl", {}).get("total_usd") or 0.0)

    same = (
        json.dumps({k: ro.get(k) for k in ("trades", "summary", "notes", "window", "ok")}, sort_keys=True)
        == json.dumps({k: rn.get(k) for k in ("trades", "summary", "notes", "window", "ok")}, sort_keys=True)
    )
    if not same:
        mismatch += 1
        if mismatch <= 3:
            print("MISMATCH at run", run, "cfg:", json.dumps(cfg, sort_keys=True))

print(f"runs={RUNS} trades={total_trades} entries={total_entries} "
      f"total_pnl={round(total_pnl, 2)} mismatches={mismatch}")
if mismatch == 0:
    print("R66 FUZZ OK — توافق رجعي بت-بت مثبت (بلا أي انحراف)")
    sys.exit(0)
print("R66 FUZZ FAILED")
sys.exit(1)
