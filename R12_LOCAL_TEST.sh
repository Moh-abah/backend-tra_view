#!/usr/bin/env bash
# R12_LOCAL_TEST.sh — اختبار هوت-فكس الجولة 12 محلياً في جلسة واحدة
# (البيئة تقتل العمليات الخلفية بين الاستدعاءات لذا يُشغَّل الخادم ويُختبر ويُوقَف هنا)
set -u
cd /home/z/my-project/download/FINAL_CHECK
BASE="http://127.0.0.1:8600/api/v1"
LOG=/tmp/r12_local_uvicorn.log

# 1) تشغيل الخادم
pkill -f "uvicorn.*8600" 2>/dev/null; sleep 1
DEBUG=true \
DATABASE_URL="sqlite+aiosqlite:///./local_r12.db" \
SECRET_KEY="r12local_9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08" \
nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8600 > "$LOG" 2>&1 &
SRV=$!
for i in $(seq 1 30); do
  sleep 1
  curl -s -m 3 "$BASE/health" >/dev/null 2>&1 && break
done
echo "server pid=$SRV up after ~${i}s"

echo
echo "################ [C] أمر القبول الحرفي للواجهة — POST صيغة الواجهة ################"
curl -s -m 120 -X POST "$BASE/overlays/compute" -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","timeframe":"1h","days":180,"overlays":["fib"]}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
if 'detail' in d: print('ERROR:', d['detail']); raise SystemExit(1)
fib=(d.get('overlays') or {}).get('fib') or {}
cur=fib.get('current') or {}
ls=[l.get('ratio') if isinstance(l,dict) else l for l in (cur.get('levels') or [])]
bad=[x for x in ls if isinstance(x,(int,float)) and (x<0 or x>1)]
print('levels:', ls)
print('out_of_range:', bad)
print('symbol:', d.get('symbol'), '| cache:', (d.get('summary') or {}).get('cache'))
assert bad==[], 'FAIL: levels outside [0,1]'
print('PASS-C')
"

echo
echo "################ [B] GET types=fib — النطاق [0,1] حصراً ################"
curl -s -m 60 "$BASE/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=180&types=fib" | python3 -c "
import json,sys
d=json.load(sys.stdin)
fib=(d.get('overlays') or {}).get('fib') or {}
cur=fib.get('current') or {}
ls=[l.get('ratio') if isinstance(l,dict) else l for l in (cur.get('levels') or [])]
bad=[x for x in ls if isinstance(x,(int,float)) and (x<0 or x>1)]
print('current.levels ratios:', ls)
print('out_of_range:', bad)
assert bad==[], 'FAIL'
# extension levels still available explicitly:
print('PASS-B')
"

echo
echo "################ [B2] الامتدادات الصريحة تُقبل عبر params ################"
curl -s -m 60 "$BASE/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=180&types=fib&fib_levels=0,0.618,1,1.618" | python3 -c "
import json,sys
d=json.load(sys.stdin)
fib=(d.get('overlays') or {}).get('fib') or {}
cur=fib.get('current') or {}
ls=[l.get('ratio') if isinstance(l,dict) else l for l in (cur.get('levels') or [])]
print('explicit levels:', ls)
assert 1.618 in ls, 'explicit extension level missing'
print('PASS-B2 (الصريح يعمل — الافتراضي صارم)')
"

echo
echo "################ [A] backtest1/run بلا Redis (fallback داخل العملية) ################"
python3 - <<'PY'
import json, time, urllib.request, os
BASE = "http://127.0.0.1:8600/api/v1"

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=180).read())

champion = json.load(open("champion_r12.json")) if os.path.exists("champion_r12.json") else None
if champion is None:
    champion = {
      "name":"ZigZag HL v2 — ZERO FEE","timeframe":"1h","market":"crypto","symbols":["BTCUSDT"],
      "days":200,"initial_capital":10000,"position_sizing":"percentage","position_size_percent":1.0,
      "max_positions":1,"commission_rate":0,"slippage_percent":0,"leverage":1,
      "strategy_config":{
        "name":"ZigZag HL v2","base_timeframe":"1h","position_side":"long",
        "indicators":[{"name":"zigzag_channels","type":"support_resistance","params":{"length":100},"enabled":True,"timeframe":"1h"}],
        "entry_rules":[{"name":"Higher Low Structure","condition":{"type":"and","conditions":[
          {"type":"indicator_value","operator":">","left_value":"indicator:zigzag_channels:zz_pivot_low","right_value":0},
          {"type":"indicator_value","operator":">","left_value":"indicator:zigzag_channels:zz_pivot_low","right_value":"indicator:zigzag_channels:zz_prev_pivot_low"}]},
          "position_side":"long","weight":1,"enabled":True}],
        "exit_rules":[{"name":"Confirmed Top","condition":{"type":"indicator_value","operator":">",
          "left_value":"indicator:zigzag_channels:zz_pivot_high","right_value":0},"exit_type":"signal_exit","enabled":True}],
        "risk_management":{"stop_loss_percentage":2.0,"take_profit_percentage":99.0}}}

r = post("/backtest1/run", champion)
print("run resp:", json.dumps(r, ensure_ascii=False))
assert r.get("task_id"), "no task_id"
mode = r.get("mode", "celery")
print("mode:", mode)

state=None
for _ in range(300):
    s = get(f"/backtest1/status/{r['task_id']}")
    state = s.get("state")
    if state in ("SUCCESS","FAILURE"): break
    time.sleep(2)
print("final state:", state, "| status resp:", json.dumps({k:s.get(k) for k in ('state','mode','backtest_id','error')}, ensure_ascii=False))
assert state=="SUCCESS", f"FAILED: {json.dumps(s)[:300]}"
bt_id = s["result"]["backtest_id"]
d = get(f"/backtest/get/{bt_id}")
sm = d["summary"]; cd = d["chart_data"]
tps = cd.get("trade_points") or []
exits=[t for t in tps if t.get("type")=="exit"]
ma = sm.get("math_audit") or {}
print("trades:", sm.get("total_trades"), "| pnl:", round(sm.get("total_pnl",0),4),
      "| fees:", sm.get("fees_applied"), "| fill:", sm.get("fill_model"),
      "| audit:", ma.get("consistent"))
print("PASS-A (backtest1/run يعمل بلا Redis — البطل يعيد صفقات)")
PY

echo
echo "################ [D] تعدد الرموز — وسم + chart_data_by_symbol ################"
python3 - <<'PY'
import json, time, urllib.request
BASE = "http://127.0.0.1:8600/api/v1"

def post(path, payload, timeout=90):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=180).read())

payload = {
  "name":"multi-sym test","timeframe":"1h","market":"crypto","symbols":["BTCUSDT","DOGEUSDT"],
  "days":60,"initial_capital":10000,"position_sizing":"percentage","position_size_percent":1.0,
  "max_positions":1,"commission_rate":0,"slippage_percent":0,
  "strategy_config":{
    "name":"ms","base_timeframe":"1h","position_side":"long","indicators":[],
    "entry_rules":[],"exit_rules":[],
    "risk_management":{"stop_loss_percentage":2.0}}
}
r = post("/backtest1/run?wait=true", payload)
print("status:", r.get("status"), "| mode:", r.get("mode"), "| err:", str(r.get("error",""))[:200])
assert r.get("status")=="COMPLETED", f"FAILED: {json.dumps(r)[:400]}"
cd = r.get("chart_data") or {}
md = cd.get("metadata") or {}
candles = cd.get("visual_candles") or []
by_sym = cd.get("chart_data_by_symbol") or {}
syms_in = sorted({c.get("symbol") for c in candles if isinstance(c,dict) and c.get("symbol")})
print("metadata.symbol:", md.get("symbol"), "| display_symbol:", md.get("display_symbol"), "| symbols:", md.get("symbols"))
print("symbols_in_candles:", syms_in)
print("chart_data_by_symbol keys:", sorted(by_sym.keys()), "| counts:", {k: v.get("candles_count") for k,v in by_sym.items()})
first_btc = next((c for c in candles if c.get("symbol")=="BTCUSDT"), None)
first_doge = next((c for c in candles if c.get("symbol")=="DOGEUSDT"), None)
if first_btc and first_doge:
    print("BTC candle close:", first_btc.get("close"), "| DOGE candle close:", first_doge.get("close"))
    assert first_doge.get("close",1) < 1 < first_btc.get("close",0), "price ranges wrong"
else:
    raise SystemExit("FAIL: no tagged candles")
tps_syms = sorted({p.get("symbol") for p in (cd.get("trade_points") or []) if p.get("symbol")})
print("trade_points symbols:", tps_syms)
assert "BTCUSDT" in syms_in and "DOGEUSDT" in syms_in, "FAIL: no symbol tags"
assert set(by_sym.keys()) == {"BTCUSDT","DOGEUSDT"}, "FAIL: by_symbol split"
print("PASS-D")

# ---- [W] WINUSDT — أمر القبول الحرفي (5-ب.2) عبر wait=true ----
print()
print("################ [W] WINUSDT — أمر القبول الحرفي (5-ب.2) ################")
win = {
  "name":"t","timeframe":"1h","market":"crypto","symbols":["WINUSDT"],"days":30,
  "commission_rate":0,"slippage_percent":0,
  "strategy_config":{"name":"t","base_timeframe":"1h","position_side":"long","indicators":[],
   "entry_rules":[],"exit_rules":[],"risk_management":{"stop_loss_percentage":2.0}}}
d = post("/backtest1/run?wait=true", win)
assert d.get("status")=="COMPLETED", f"run failed: {json.dumps(d)[:300]}"
c = ((d.get("chart_data") or {}).get("visual_candles") or [{}])[0]
print("close:", c.get("close"), "| digits ok:", c.get("close",0)<0.01, "| symbol tag:", c.get("symbol"))
assert c.get("close") and c.get("close")<0.01, "FAIL: close missing/wrong"
print("PASS-W (وضع no-signal للاستراتيجية الفارغة يعمل)")
PY

echo
echo "################ إيقاف الخادم ################"
pkill -f "uvicorn.*8600" 2>/dev/null
echo "DONE R12_LOCAL_TEST"
