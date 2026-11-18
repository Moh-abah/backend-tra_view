#!/usr/bin/env bash
# e2e_api_test.sh — اختبار المسار الكامل عبر خادم API الحقيقي (أمر واحد).
set -u
cd /home/z/drive-download/backend_PRO95_extracted

export DATABASE_URL="sqlite+aiosqlite:////home/z/drive-download/backend_PRO95_extracted/db/local_test.db"
export REDIS_URL="redis://localhost:6379/0"
export CELERY_BROKER_URL="redis://localhost:6379/1"
export CELERY_RESULT_BACKEND="redis://localhost:6379/2"

echo ">>> starting uvicorn..."
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8100 > /tmp/uvicorn_e2e.log 2>&1 &
UVI_PID=$!

# انتظار الجاهزية
for i in $(seq 1 40); do
  sleep 2
  if curl -s --max-time 3 "http://127.0.0.1:8100/api/v1/strategies/presets" | grep -q "ZLF\|ALMIGHTY\|presets"; then
    echo ">>> server ready after $((i*2))s"
    break
  fi
done

echo ">>> preparing payloads (baseline + zx=60)..."
python3 - <<'PYEOF'
import json
from pathlib import Path
p = json.loads(Path("payloads/zlf_almighty_quantum_ema_full_history.json").read_text(encoding="utf-8"))
# نافذة أقصر للاختبار (سنة 2023) — يكفي لإثبات المسار عبر API ويوفر الوقت
p["start_date"] = "2023-01-01T00:00:00Z"
p["end_date"] = "2023-12-31T23:59:59Z"
p["name"] = "E2E-ZONE-EXIT-TF1 baseline"
Path("/tmp/e2e_baseline.json").write_text(json.dumps(p), encoding="utf-8")
p2 = json.loads(json.dumps(p))
p2["name"] = "E2E-ZONE-EXIT-TF1 zx=60"
p2["strategy_config"]["indicators"][0]["params"]["zone_exit_resolution"] = "60"
Path("/tmp/e2e_zx60.json").write_text(json.dumps(p2), encoding="utf-8")
print("payloads ready")
PYEOF

run_backtest () {
  local payload="$1"; local tag="$2"
  echo ">>> POST /api/v1/backtest1/run ($tag) ..."
  local task_id=$(curl -s --max-time 30 -X POST "http://127.0.0.1:8100/api/v1/backtest1/run" \
    -H "Content-Type: application/json" -d @"$payload" | python3 -c "import json,sys; print(json.load(sys.stdin).get('task_id',''))")
  echo "    task_id=$task_id"
  for i in $(seq 1 110); do
    sleep 3
    local st=$(curl -s --max-time 10 "http://127.0.0.1:8100/api/v1/backtest1/status/$task_id")
    local status=$(echo "$st" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status') or d.get('state') or '')" 2>/dev/null || echo "?")
    if [ "$status" = "completed" ] || [ "$status" = "SUCCESS" ] || [ "$status" = "success" ] || [ "$status" = "done" ]; then
      echo "    status=$status after $((i*3))s"
      local btid=$(echo "$st" | python3 -c "import json,sys; d=json.load(sys.stdin); r=d.get('result') or {}; print(d.get('backtest_id') or d.get('result_id') or r.get('backtest_id') or r.get('id') or '')" 2>/dev/null)
      echo "    backtest_id=$btid"
      if [ -n "$btid" ]; then
        curl -s --max-time 30 "http://127.0.0.1:8100/api/v1/backtest1/get/$btid" > "/tmp/e2e_result_$tag.json"
        python3 - "$tag" <<'PYEOF'
import json, sys
tag = sys.argv[1]
d = json.load(open(f"/tmp/e2e_result_{tag}.json"))
res = d if "metrics" not in d else d.get("result", d)
m = res.get("metrics") or {}
# البحث المرن عن المقاييس
def find(*keys):
    for k in keys:
        if k in res: return res[k]
        if k in m: return m[k]
    return None
print(f"  [{tag}] trades={find('total_trades')} pnl%={find('total_pnl_percent','total_return_pct')} "
      f"wr={find('win_rate','win_rate_pct')} dd={find('max_drawdown_percent','max_drawdown_pct')}")
trades = res.get("trades") or []
ers = {}
for t in trades:
    ers[t.get("exit_reason","")] = ers.get(t.get("exit_reason",""), 0) + 1
print(f"  [{tag}] n_trades={len(trades)} exit_reasons={list(ers.keys())[:2]}")
PYEOF
      fi
      return 0
    fi
    if [ "$status" = "failed" ] || [ "$status" = "FAILURE" ] || [ "$status" = "error" ]; then
      echo "    FAILED: $st" | head -c 600
      return 1
    fi
  done
  echo "    TIMEOUT waiting for $task_id"
  return 1
}

run_backtest /tmp/e2e_baseline.json baseline
run_backtest /tmp/e2e_zx60.json zx60

echo ">>> stopping server..."
kill $UVI_PID 2>/dev/null
sleep 2
echo "E2E_API_DONE"
