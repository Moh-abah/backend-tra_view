# -*- coding: utf-8 -*-
"""بصمة حية للراوتر بعد تركيب ج42 — يشغَّل على السيرفر ويطبع الحقيقة كما هي."""
import json, urllib.request, sys

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return json.loads(r.read().decode())

def post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())

print("== 1) /exit-strategy/defaults (البصمة القديمة — يجب أن تبقى حية) ==")
try:
    d = get("/api/v1/exit-strategy/defaults")
    cfg = d.get("config") or d.get("defaults") or {}
    print("   use_trailing:", cfg.get("use_trailing"), "| trailing_giveback_pct:", cfg.get("trailing_giveback_pct"))
    print("   spec:", (d.get("engine") or {}).get("spec"))
except Exception as e:
    print("   ⚠️", e)

print("\n== 2) backtest1/run مع exit_strategy (المسار الموحد) ==")
code, resp = post("/api/v1/backtest1/run", {
    "symbols": ["BTCUSDT"], "timeframe": "1h", "days": 30,
    "strategy_config": {"name": "zzfib"},
    "exit_strategy": {"strategy": "zzfib",
                      "config": {"use_trailing": True, "trailing_giveback_pct": 20.0}},
})
print("   HTTP", code, "| mode:", resp.get("mode"), "| task:", str(resp.get("task_id"))[:12])
assert code == 200 and resp.get("mode") == "unified-exit", "فرع ج42 لا يعمل!"

import time
bid = None
for _ in range(60):
    s = get(f"/api/v1/backtest1/status/{resp['task_id']}")
    if s.get("state") == "SUCCESS":
        bid = s.get("backtest_id"); break
    if s.get("state") == "FAILURE":
        print("   FAILURE:", s.get("error")); sys.exit(1)
    time.sleep(1)
print("   status: SUCCESS | backtest_id:", str(bid)[:16])
doc = get(f"/api/v1/backtest1/get/{bid}")
sm = doc["summary"]
print("   architecture:", sm.get("architecture_mode"))
print("   engine:", (sm.get("engine") or {}).get("spec"))
print("   trailing:", (sm.get("exit_strategy") or {}).get("trailing"))
print("   exit_reasons:", sm.get("exit_reasons"))
assert sm.get("architecture_mode") == "Unified-Exit-Engine-R42"
assert (sm.get("exit_strategy") or {}).get("trailing", {}).get("active") is True
print("\n== 3) 422 حيّ (use_trailing خاطئ) ==")
code2, _ = post("/api/v1/backtest1/run", {
    "symbols": ["BTCUSDT"], "exit_strategy": {"config": {"use_trailing": "نعم"}}})
print("   HTTP", code2, "(المتوقع 422)")
assert code2 == 422
print("\n✅ ج42 حية على السيرفر: محرك واحد · حمولة واحدة · مصدر واحد")
