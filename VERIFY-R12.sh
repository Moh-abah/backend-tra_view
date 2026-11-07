#!/usr/bin/env bash
# ============================================================================
# VERIFY-R12.sh — اختبارات قبول الجولة 12 ضد بيئة الإنتاج
# يعمل بعد النشر (docker cp + docker restart trading-backend).
# الاستخدام:  bash VERIFY-R12.sh
# ============================================================================
BASE="${BASE:-http://161.97.73.254:8000/api/v1}"
echo "BASE = $BASE"

echo "================ [1] GET /indicators/available — zigzag_fib مسجّل ================"
curl -s "$BASE/indicators/available" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('filter zigzag_fib:', [i['name'] for i in d['indicators'] if i['name']=='zigzag_fib'])
print('filter zzf (حرفي كما في طلب الواجهة — يجد الاسم القصير zzfib):', [i['name'] for i in d['indicators'] if 'zzf' in i['name']])
e=[i for i in d['indicators'] if i['name']=='zigzag_fib']
assert e, 'zigzag_fib غير مسجل!'
print('display_name:', e[0]['display_name'])
print('PASS-1')
"

echo; echo "================ [2] POST /indicators/compute — أعمدة ind_zzf_* ================"
curl -s -X POST "$BASE/indicators/compute?symbol=BTCUSDT&timeframe=1h&days=30" \
  -H "Content-Type: application/json" \
  -d '{"indicators":[{"name":"zigzag_fib","type":"support_resistance","params":{"length":100},"enabled":true,"timeframe":"1h"}]}' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
cols=[k for k in (d.get('columns') or (d.get('data') or [{}])[0].keys()) if 'zzf' in k]
need={'ind_zzf_dir','ind_zzf_p1','ind_zzf_p2','ind_zzf_i1','ind_zzf_i2','ind_zzf_touch'}
assert need.issubset(set(cols)), f'missing: {need-set(cols)}'
print('zzf columns:', sorted(cols))
print('PASS-2')
"

echo; echo "================ [3] POST /strategies1/validate — شرط zzfib_touch ================"
curl -s -X POST "$BASE/strategies1/validate" -H "Content-Type: application/json" -d '{
  "name":"v","indicators":[{"name":"zigzag_fib","type":"support_resistance","params":{"length":100},"enabled":true,"timeframe":"1h"}],
  "entry_rules":[{"name":"t","condition":{"type":"indicator_value","operator":">","left_value":"indicator:zigzag_fib:zzfib_touch","right_value":0},"position_side":"long","weight":1,"enabled":true}],
  "exit_rules":[],"filter_rules":[],"risk_management":{"stop_loss_percentage":2.0}}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('valid') is True, d; print(json.dumps(d, ensure_ascii=False)); print('PASS-3')"

echo; echo "================ [4] GET /overlays/compute?types=zzfib ================"
curl -s "$BASE/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=30&types=zzfib" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
zzf=(d.get('overlays') or {}).get('zzfib')
assert zzf and zzf.get('series') and zzf.get('current'), 'zzfib missing'
cur=zzf['current']
print('keys:', sorted(zzf.keys()), '| current p1=%s p2=%s dir=%s levels=%d' % (cur.get('p1'),cur.get('p2'),cur.get('dir'),len(cur.get('levels') or [])))
print('PASS-4')
"

echo; echo "================ [5] GET /health — بدون redis ================"
curl -s "$BASE/health" | python3 -c "
import json,sys
d=json.load(sys.stdin)
svcs=d.get('services') or {}
assert 'redis' not in svcs, f'redis still present: {svcs}'
print(json.dumps(d, ensure_ascii=False)); print('PASS-5')
"

echo; echo "================ [6] GET /strategies/presets — البطل v2 ================"
curl -s "$BASE/strategies/presets" | python3 -c "
import json,sys
d=json.load(sys.stdin)
p=d['presets'][0]
assert p['payload']['strategy_config']['name']=='ZigZag HL v2'
print('id:', p['id'], '| commission:', p['payload']['commission_rate'], '| slippage:', p['payload']['slippage_percent'])
print('PASS-6')
"

echo; echo "================ [7] BACKTEST البطل — عمولة 0 + math_audit + الشفافية ================"
python3 - <<'PY'
import json, time, urllib.request, sys
BASE = __import__('os').environ.get("R12_BASE", "http://161.97.73.254:8000/api/v1")

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=120).read())

preset = get("/strategies/presets")["presets"][0]["payload"]
payload = dict(preset); payload["days"] = 200
r = post("/backtest/run", payload)
task_id = r["task_id"]
print("task:", task_id)
state = None
for _ in range(400):
    s = get(f"/backtest/status/{task_id}")
    state = s.get("state")
    if state in ("SUCCESS", "FAILURE"):
        break
    time.sleep(3)
assert state == "SUCCESS", f"backtest state={state}: {json.dumps(s)[:300]}"
bt_id = s["result"]["backtest_id"]
d = get(f"/backtest/get/{bt_id}")
summary = d["summary"]; tps = d["chart_data"]["trade_points"]
exits = [t for t in tps if t.get("type") == "exit"]
entries = {t["trade_id"]: t for t in tps if t.get("type") == "entry"}
ma = summary.get("math_audit") or {}
print("total_trades:", summary["total_trades"], "| total_pnl:", round(summary["total_pnl"], 4))
print("fees_applied:", summary.get("fees_applied"), "| fill_model:", summary.get("fill_model"))
print("math_audit:", json.dumps({k: ma.get(k) for k in ("checked_trades","max_abs_error","consistent","total_pnl_matches")}, ensure_ascii=False))
assert all(abs(float(t.get("commission") or 0)) < 1e-12 for t in exits), "commission != 0"
errs = [abs(float(t["pnl"]) - (float(t["exit_price"]) - float(t["entry_price"])) * (t.get("position_size") or 0) * (1 if t.get("direction") == "long" else -1)) for t in exits]
print("max |pnl-(exit-entry)*units|:", round(max(errs or [0]), 10))
ssum = sum(float(t["pnl"]) for t in exits)
print("Σpnl:", round(ssum, 6), "| total_pnl:", round(summary["total_pnl"], 6), "| Δ:", round(abs(ssum - summary["total_pnl"]), 10))
need = ("price_delta","price_delta_pct","direction","result_pct","pnl_gross","commission","fill_entry","fill_exit")
assert all(all(k in t for k in need) for t in exits), "شفافية ناقصة"
assert ma.get("consistent") is True, "math_audit inconsistent"
print("PASS-7  backtest_id:", bt_id)

# [8] chart-data include_indicators
cd = get(f"/backtest/{bt_id}/chart-data?include_indicators=true&limit=300")
ind = set()
for c in cd["visual_candles"][:5]:
    ind |= {k for k in c.keys() if k.startswith("ind_")}
print("[8] chart-data ind_* keys:", sorted(ind))
assert any(k.startswith("ind_zz_") for k in ind), "ind_zz_* missing"
print("PASS-8")
PY

echo
echo "================ [9] مستويات فيبو [0,1] حصراً (5-ب.1) — أمر القبول الحرفي ================"
curl -s -X POST "$BASE/overlays/compute" -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","timeframe":"1h","days":180,"overlays":["fib"]}' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert 'detail' not in d, f'POST failed: {d[\"detail\"]}'
fib=(d.get('overlays') or {}).get('fib') or {}
cur=fib.get('current') or {}
ls=[l['level'] if isinstance(l,dict) and 'level' in l else (l.get('ratio') if isinstance(l,dict) else l) for l in (cur.get('levels') or [])]
bad=[x for x in ls if isinstance(x,(int,float)) and (x<0 or x>1)]
print('levels:', ls)
print('out_of_range:', bad)
assert bad==[], 'FAIL: levels outside [0,1]'
print('PASS-9  (POST صيغة الواجهة يعمل + النطاق [0,1] صارم)')
"

echo
echo "================ [10] WINUSDT — دقة تحت السنت (5-ب.2) — أمر القبول الحرفي ================"
curl -s -X POST "$BASE/backtest1/run?wait=true" -H "Content-Type: application/json" \
  -d '{"name":"t","timeframe":"1h","market":"crypto","symbols":["WINUSDT"],"days":30,"commission_rate":0,"slippage_percent":0,"strategy_config":{"name":"t","base_timeframe":"1h","position_side":"long","indicators":[],"entry_rules":[],"exit_rules":[],"risk_management":{"stop_loss_percentage":2.0}}}' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('status')=='COMPLETED', f'run failed: {json.dumps(d)[:250]}'
c=(d.get('chart_data',{}).get('visual_candles') or [{}])[0]
print('close:',c.get('close'),'| digits ok:', c.get('close',0)<0.01)
assert c.get('close') and c.get('close')<0.01, 'FAIL: close missing/rounded'
print('PASS-10 (الوضع no-signal للاستراتيجية الفارغة + دقة كاملة)')
"

echo
echo "================ [11] تعدد الرموز — chart_data_by_symbol (5-ب.3) ================"
python3 - <<'PY'
import json, urllib.request, os
BASE = os.environ.get("R12_BASE", "http://161.97.73.254:8000/api/v1")
payload = {"name":"multi-sym","timeframe":"1h","market":"crypto","symbols":["BTCUSDT","DOGEUSDT"],
  "days":60,"initial_capital":10000,"position_sizing":"percentage","position_size_percent":1.0,
  "max_positions":1,"commission_rate":0,"slippage_percent":0,
  "strategy_config":{"name":"ms","base_timeframe":"1h","position_side":"long","indicators":[],
   "entry_rules":[],"exit_rules":[],"risk_management":{"stop_loss_percentage":2.0}}}
req = urllib.request.Request(BASE + "/backtest1/run?wait=true", data=json.dumps(payload).encode(),
                             headers={"Content-Type":"application/json"}, method="POST")
d = json.loads(urllib.request.urlopen(req, timeout=600).read())
assert d.get("status")=="COMPLETED", f"run failed: {json.dumps(d)[:250]}"
cd = d["chart_data"]; md = cd.get("metadata") or {}
candles = cd.get("visual_candles") or []
by_sym = cd.get("chart_data_by_symbol") or {}
syms_in = sorted({c.get("symbol") for c in candles if isinstance(c,dict) and c.get("symbol")})
print("metadata.symbol:", md.get("symbol"), "| display_symbol:", md.get("display_symbol"))
print("symbols:", md.get("symbols"), "| symbols_in_candles:", md.get("symbols_in_candles") or syms_in)
print("chart_data_by_symbol:", {k: v.get("candles_count") for k,v in by_sym.items()})
fb = next((c for c in candles if c.get("symbol")=="BTCUSDT"), {})
fd = next((c for c in candles if c.get("symbol")=="DOGEUSDT"), {})
print("BTC close:", fb.get("close"), "| DOGE close:", fd.get("close"))
assert {"BTCUSDT","DOGEUSDT"} <= set(by_sym.keys()), "FAIL: split missing"
assert fd.get("close",1) < 1 < fb.get("close",0), "FAIL: symbol/candle mismatch persists"
print("PASS-11 (كل شمعة موسومة + بيانات كل رمز منفصلة + الرمز الافتراضي موثق)")
PY

echo
echo "================ [12] عقد الـ16 عموداً بالمؤشرات الثلاثة (0-أ) ================"
curl -s -m 90 "$BASE/indicators/compute?symbol=BTCUSDT&timeframe=1h&days=60" \
  -H "Content-Type: application/json" \
  -d '{"indicators":[{"name":"zigzag_channels","type":"support_resistance","params":{"length":100},"enabled":true,"timeframe":"1h"},{"name":"auto_fib_retracement","type":"support_resistance","params":{},"enabled":true,"timeframe":"1h"},{"name":"auto_trendline","type":"support_resistance","params":{},"enabled":true,"timeframe":"1h"}]}' \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
rows=d.get('data') or []
cols=set()
for r in rows[:3]:
    cols |= {k for k in r.keys() if k.startswith('ind_')}
print('ind_ columns count:', len(cols))
print(sorted(cols))
assert len(cols)==16, f'FAIL: expected 16, got {len(cols)}'
print('PASS-12 (عقد الجولة 11 للـ16 عموداً مكتمل)')
"

echo
echo "================ VERIFY-R12 DONE ================"
