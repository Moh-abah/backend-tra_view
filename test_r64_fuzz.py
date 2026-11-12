# -*- coding: utf-8 -*-
"""ضباب عشوائي R64 — المحرك القديم مقابل الجديد بت-بت على سيناريوهات عشوائية."""
import importlib.util
import json
import random
import sys

def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

OLD = load_module("/home/z/r64-workspace/exit_engine_ORIGINAL.py", "old")
NEW = load_module("/home/z/r64-workspace/app/services/exit_engine.py", "new")

SCENARIOS = 300
mismatches = 0
total_trades = 0

for seed in range(SCENARIOS):
    rnd = random.Random(seed * 7919)
    n = rnd.randint(30, 220)
    price = rnd.uniform(10.0, 5000.0)
    candles = []
    for i in range(n):
        o = price
        drift = rnd.uniform(-0.05, 0.05)
        c = max(0.5, o * (1.0 + drift))
        hi = max(o, c) * (1.0 + rnd.uniform(0.0, 0.02))
        lo = min(o, c) * (1.0 - rnd.uniform(0.0, 0.02))
        candles.append({"time": 1700000000000 + i * 60000, "open": o, "high": hi,
                        "low": lo, "close": c, "volume": rnd.uniform(10, 10000)})
        price = c
    # إشارات عشوائية بأرضيات فيبو عشوائية
    entries = []
    for bar in sorted(rnd.sample(range(n), k=rnd.randint(0, min(6, n)))):
        p = candles[bar]["close"]
        entries.append({"bar": bar, "time": candles[bar]["time"], "price": p,
                        "floor": p * rnd.uniform(0.85, 1.02),
                        "floor_meta": {"source": "fuzz"}, "signal": {}})
    # حمولات متنوعة (كلها بدون حقول R64 = يجب التطابق التام)
    payloads = [
        None,
        {"use_trailing": True, "trailing_giveback_pct": rnd.choice([5.0, 20.0, 40.0])},
        {"tp_trail_arm_pct": rnd.choice([0.0, 1.5]), "tp_trail_giveback_pct": 1.0},
        {"dca1_trigger_pct": 2.0, "dca2_trigger_pct": 4.0, "max_entries": 3},
        {"cooldown_bars": 3, "trend_filter_sma_bars": 5, "min_floor_distance_pct": 1.0},
        {"allow_overlap": True},
        {"entry_exec": "next_open"},
    ]
    for cfg in payloads:
        r_old = OLD.run_exit_backtest(candles, entries, dict(cfg) if cfg else None)
        r_new = NEW.run_exit_backtest(candles, entries, dict(cfg) if cfg else None)
        total_trades += len(r_old["trades"])
        if (json.dumps(r_old["trades"], sort_keys=True) != json.dumps(r_new["trades"], sort_keys=True)
                or json.dumps(r_old["summary"], sort_keys=True) != json.dumps(r_new["summary"], sort_keys=True)
                or json.dumps(r_old.get("notes", []), sort_keys=True) != json.dumps(r_new.get("notes", []), sort_keys=True)):
            mismatches += 1
            print(f"❌ عدم تطابق: seed={seed} cfg={cfg}")

print(f"سيناريوهات: {SCENARIOS} × 7 حمولات = {SCENARIOS * 7} تشغيلة · {total_trades} صفقة إجمالاً")
print(f"عدم التطابق: {mismatches}")
if mismatches == 0:
    print("✅ تطابق بت-بت كامل — الانحدار مثبت على 2100 تشغيلة عشوائية")
    sys.exit(0)
sys.exit(1)
