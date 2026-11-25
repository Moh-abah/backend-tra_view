#!/usr/bin/env python3
# -*- coding utf-8 -*-
"""EBREAK1 دخان المحرك الكامل محلياً — الميكانيكا قبل البث (نمط smoke_a123)."""
import io, json, subprocess, sys
from pathlib import Path

TREE = "/home/z/my-project/trading-system/ebreak-reclaim/runtime_after"
DATA = "/home/z/my-project/trading-system/gold-mc1-structstrict/audit/theta_15m.json"
OUT = Path("/home/z/my-project/trading-system/ebreak-reclaim/results"); OUT.mkdir(exist_ok=True)
WIN_START, WIN_END = "2025-09-01T00:00:00Z", "2026-04-20T20:59:59Z"

CODE = r'''
import sys, json, asyncio, types, io
sys.argv = ["x"]
mod = types.ModuleType("app.services.data_service")
class _S: pass
mod.DataService = _S
sys.modules["app.services.data_service"] = mod
sys.path.insert(0, "{tree}")
import app.backtest.engine1 as e1
from app.backtest.schemas import BacktestConfig
import pandas as pd

payload = json.load(io.open(r"{payload}", encoding="utf-8"))
payload["start_date"] = "{start}"
payload["end_date"] = "{end}"
candles = json.load(io.open(r"{data}", encoding="utf-8"))
df = pd.DataFrame([{{"open": float(c[1]), "high": float(c[2]),
                    "low": float(c[3]), "close": float(c[4]),
                    "volume": float(c[5])}} for c in candles])
df.index = pd.DatetimeIndex(pd.to_datetime([c[0] for c in candles],
                     unit="ms", utc=True), name="time")
df = df[(df.index >= pd.Timestamp("{start}")) & (df.index <= pd.Timestamp("{end}"))]
class StubDS:
    def __init__(self, df): self.dfs = {{"15m": df}}
    async def get_historicallastvirsion(self, symbol, timeframe, market,
            start_date, end_date, use_cache=True, tz_offset_minutes=0):
        return self.dfs.get(str(timeframe), self.dfs["15m"]).copy()
cfg = BacktestConfig(**payload)
eng = e1.BacktestEngine(data_service=StubDS(df))
res = asyncio.run(eng.run_backtest(cfg))
trades = getattr(res, "trades", None) or []
tp = res.trade_points or []
d = {{
 "pnl": float(res.total_pnl), "trades": int(res.total_trades),
 "win_rate": float(res.win_rate),
 "exit_reasons": [str(t.exit_reason) for t in trades],
 "entry_times": [str(getattr(t, "entry_time", "")) for t in trades][:40],
 "n_entry": sum(1 for q in tp if q.get("type") == "entry"),
 "n_exit": sum(1 for q in tp if q.get("type") == "exit"),
}}
json.dump(d, io.open(r"{out}", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("DONE pnl=%s trades=%s" % (d["pnl"], d["trades"]))
'''

def run(tag, payload_path):
    out = str(OUT / f"smoke_{tag}.json")
    code = CODE.format(tree=TREE, payload=payload_path, data=DATA,
                       start=WIN_START, end=WIN_END, out=out)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=900)
    print(f"--- {tag} stdout: {r.stdout.strip()[-200:]}")
    if r.returncode != 0:
        print(f"STDERR: {r.stderr[-800:]}")
        return None
    return json.load(open(out, encoding="utf-8"))

fails = []
FULL = "/home/z/my-project/trading-system/ebreak-reclaim/package/payloads/payload_GOLD_EBREAK_RECLAIM_THETAUSDT.json"
EXITO = "/home/z/my-project/trading-system/ebreak-reclaim/package/payloads/payload_GOLD_EBREAK_EXIT_THETAUSDT.json"

a = run("full", FULL)
b = run("exit_only", EXITO)
if a is None or b is None:
    fails.append("engine crash")
else:
    def count(d, needle):
        return sum(1 for r in d["exit_reasons"] if needle in r)
    print(f"FULL:      pnl={a['pnl']:.2f} trades={a['trades']} wr={a['win_rate']:.1%} "
          f"exit_ebreak={count(a,'EBREAK')} exit_zone={count(a,'ZONE-EXIT')} exit_alm={count(a,'ALMIGHTY')}")
    print(f"EXIT-ONLY: pnl={b['pnl']:.2f} trades={b['trades']} wr={b['win_rate']:.1%} "
          f"exit_ebreak={count(b,'EBREAK')} exit_zone={count(b,'ZONE-EXIT')} exit_alm={count(b,'ALMIGHTY')}")
    if count(a, "EBREAK") == 0:
        fails.append("قاعدة خروج الكسر لم تنفعل")
    if a["trades"] <= b["trades"]:
        fails.append("FULL بلا صفقات دخول ثانٍ إضافية؟")
    print("exit_reasons عينة FULL:", a["exit_reasons"][:8])
print("SMOKE:", "PASS" if not fails else f"FAIL {fails}")
sys.exit(1 if fails else 0)
