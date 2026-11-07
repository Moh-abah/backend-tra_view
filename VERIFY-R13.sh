#!/usr/bin/env bash
# =============================================================================
# VERIFY-R13.sh — معايير قبول الجولة 13 حرفياً (إبادة العمولة + الدقة المتناهية)
#
# الاستخدام:
#   ./VERIFY-R13.sh                    # وضع محلي: يشغّل خادماً على 127.0.0.1:8600 ثم يوقفه
#   R13_BASE=http://161.97.73.254:8000/api/v1 ./VERIFY-R13.sh --external
#                                      # وضع خارجي: يختبر خادماً حياً دون تشغيل محلي
#
# PASS-1  رفض العمولة الصريحة: commission_rate=0.001 → 422 برسالة عربية (Zero-Fee)
# PASS-2  الصيغة الصافية في math_audit (بلا commission/slippage في نص الصيغة)
# PASS-3  التسامح المشدّد: max_abs_error ≤ 1e-9 + precision_report.float64 == true
# PASS-4  /indicators/compute يقبل الصيغة النصية ["zigzag_fib"] → أعمدة ind_zzf_* كاملة
#         (ولا تجاهل صامت لأي صيغة غير صالحة → 422)
# PASS-5  الدقة تحت السنت: WINUSDT — pnl == (exit−entry)×units بدقة 1e-12 نسبياً
#         و ind_zzf_level_0618 == p1 + (p2−p1)×0.618 حرفياً
# PASS-6  تراجع آمن: البطل يعيد صفقاته المرجعية · fees_applied=0.0 · عمود commission=0.0
# =============================================================================
set -u
cd "$(dirname "$0")"
EXTERNAL="${R13_BASE:-}"
MODE_EXTERNAL=0
[ "${1:-}" = "--external" ] && MODE_EXTERNAL=1

if [ "$MODE_EXTERNAL" = "1" ]; then
  BASE="$EXTERNAL"
  LOG=/tmp/r13_external.log
else
  BASE="http://127.0.0.1:8600/api/v1"
  LOG=/tmp/r13_local_uvicorn.log
  pkill -f "uvicorn.*8600" 2>/dev/null; sleep 1
  DEBUG=true \
  DATABASE_URL="sqlite+aiosqlite:///./local_r13.db" \
  SECRET_KEY="r13local_9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08" \
  nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8600 > "$LOG" 2>&1 &
  SRV=$!
  UP=0
  for i in $(seq 1 45); do
    sleep 1
    curl -s -m 3 "$BASE/health" >/dev/null 2>&1 && { UP=1; break; }
  done
  [ "$UP" = "1" ] || { echo "SERVER FAILED TO START — log tail:"; tail -30 "$LOG"; exit 2; }
  echo "local server up (pid=$SRV) after ~${i}s"
fi

FAILURES=0
pass() { echo "✅ $1"; }
fail() { echo "❌ $1"; FAILURES=$((FAILURES+1)); }

# -----------------------------------------------------------------------------
echo
echo "################ PASS-1: رفض العمولة الصريحة (422 + رسالة Zero-Fee) ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]

def post_raw(path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try: return e.code, json.loads(body)
        except Exception: return e.code, {"_raw": body}

champion_fee = {
  "name":"R13 fee-reject test","timeframe":"1h","market":"crypto","symbols":["BTCUSDT"],
  "days":30,"initial_capital":10000,"position_sizing":"percentage","position_size_percent":1.0,
  "max_positions":1,"commission_rate":0.001,"leverage":1,
  "strategy_config":{
    "name":"t","base_timeframe":"1h","position_side":"long",
    "indicators":[{"name":"zigzag_channels","type":"support_resistance","params":{"length":100},"enabled":True,"timeframe":"1h"}],
    "entry_rules":[{"name":"HL","condition":{"type":"and","conditions":[
      {"type":"indicator_value","operator":">","left_value":"indicator:zigzag_channels:zz_pivot_low","right_value":0},
      {"type":"indicator_value","operator":">","left_value":"indicator:zigzag_channels:zz_pivot_low","right_value":"indicator:zigzag_channels:zz_prev_pivot_low"}]},
      "position_side":"long","weight":1,"enabled":True}],
    "exit_rules":[{"name":"CT","condition":{"type":"indicator_value","operator":">","left_value":"indicator:zigzag_channels:zz_pivot_high","right_value":0},"exit_type":"signal_exit","enabled":True}],
    "risk_management":{"stop_loss_percentage":2.0,"take_profit_percentage":99.0}}}

code, body = post_raw("/backtest1/run?wait=true", champion_fee)
txt = json.dumps(body, ensure_ascii=False)
print("HTTP:", code)
print("body:", txt[:400])
assert code == 422, f"FAIL: expected 422 got {code}"
assert "Zero-Fee" in txt and "commission_rate" in txt, "FAIL: no Arabic Zero-Fee message"
print("PASS-1")
PY
[ $? -eq 0 ] && pass "PASS-1 — commission_rate=0.001 → 422 برسالة Zero-Fee" || fail "PASS-1"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-1b: slippage_percent=0.1 → 422 ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def post_raw(path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try: return e.code, json.loads(body)
        except Exception: return e.code, {"_raw": body}

p = {"name":"t","timeframe":"1h","market":"crypto","symbols":["BTCUSDT"],"days":5,
     "slippage_percent":0.1,
     "strategy_config":{"name":"t","base_timeframe":"1h","position_side":"long","indicators":[],
       "entry_rules":[{"name":"always","condition":{"type":"indicator_value","operator":">","left_value":1,"right_value":0},"position_side":"long","weight":1,"enabled":True}],
       "exit_rules":[],"risk_management":{"stop_loss_percentage":2.0}}}
code, body = post_raw("/backtest1/run?wait=true", p)
print("HTTP:", code, "|", json.dumps(body, ensure_ascii=False)[:220])
assert code == 422 and "Zero-Fee" in json.dumps(body, ensure_ascii=False), "FAIL slippage not rejected"
print("PASS-1b")
PY
[ $? -eq 0 ] && pass "PASS-1b — slippage_percent>0 → 422" || fail "PASS-1b"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-2+3+6: تشغيل البطل — الصيغة الصافية + الدقة + Zero-Fee ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def post_raw(path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=280)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

champion = {
  "name":"ZigZag HL v2 — R13 VERIFY","timeframe":"1h","market":"crypto","symbols":["BTCUSDT"],
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

code, run = post_raw("/backtest1/run?wait=true", champion)
print("HTTP:", code, "| status:", run.get("status"), "| mode:", run.get("mode"))
assert code == 200 and run.get("status") == "COMPLETED", f"run failed: {json.dumps(run)[:400]}"
cd_ = run.get("chart_data") or {}
sm = run.get("summary") or run.get("metrics") or {}
if not sm:
    # قد يأتي الملخص بمفتاح summary داخل chart_data أو أعلى المستوى
    sm = run.get("summary") or {}
ma = sm.get("math_audit") or {}
print("trades:", sm.get("total_trades"), "| total_pnl_percent:", sm.get("total_pnl_percent"),
      "| fees_applied:", sm.get("fees_applied"), "| fill_model:", sm.get("fill_model"))
print("formula:", ma.get("formula"))
print("max_abs_error:", ma.get("max_abs_error"), "| tolerance:", ma.get("formula_tolerance"))
print("precision_report:", ma.get("precision_report"))

# PASS-2: الصيغة الصافية — نص الصيغة مطابق حرفياً وبلا كلمة commission/slippage
assert ma.get("formula") == "pnl == (exit_price - entry_price) * units * (long? +1 : -1)", \
    f"FAIL formula mismatch: {ma.get('formula')!r}"
assert "commission" not in ma.get("formula","") and "slippage" not in ma.get("formula","")
print("PASS-2 (الصيغة الصافية حرفياً)")

# PASS-3: التسامح المشدّد + precision_report
assert ma.get("max_abs_error") is not None and ma["max_abs_error"] <= 1e-9, f"FAIL max_abs_error={ma.get('max_abs_error')}"
pr = ma.get("precision_report") or {}
assert pr.get("float64") is True, f"FAIL precision_report.float64={pr.get('float64')}"
assert pr.get("formula_tolerance") == 1e-9, f"FAIL tolerance={pr.get('formula_tolerance')}"
assert pr.get("rounded_fields") == [], "FAIL rounded_fields not empty"
assert ma.get("consistent") is True, "FAIL math_audit.consistent != true"
print("PASS-3 (max_abs_error ≤ 1e-9 + precision_report)")

# PASS-6: Zero-Fee إبادة — fees_applied=0 وcommission=0.0 (DEPRECATED) والصفقات المرجعية
assert sm.get("fees_applied") == 0.0, f"FAIL fees_applied={sm.get('fees_applied')}"
tps = cd_.get("trade_points") or []
exits = [t for t in tps if t.get("type") == "exit"]
assert exits, "FAIL: no exit trade points"
assert all(t.get("commission") == 0.0 for t in exits), "FAIL: commission != 0.0 in trade_points"
assert all(t.get("result_pct") == t.get("price_delta_pct") for t in exits), "FAIL: result_pct != price_delta_pct"
trades_n = sm.get("total_trades")
print("champion trades:", trades_n, "| pnl%:", sm.get("total_pnl_percent"))
assert trades_n and trades_n > 0, "FAIL: champion 0 trades"
print("PASS-6 (fees_applied=0.0 · commission=0.0 · result_pct==price_delta_pct · البطل يعيد صفقات)")

# PASS-5a (على صفقات البطل أيضاً): pnl == (exit−entry)×units بدقة 1e-12 نسبياً
worst = 0.0
for t in exits:
    e, x, u = t.get("entry_price"), t.get("exit_price"), t.get("position_size")
    p, d = t.get("pnl"), t.get("direction")
    if None in (e, x, u, p) or e == 0: continue
    sign = 1.0 if d == "long" else -1.0
    expected = (x - e) * u * sign
    rel = abs(p - expected) / max(abs(expected), 1e-300) if expected != 0 else abs(p - expected)
    worst = max(worst, rel)
print("worst relative pnl error (champion):", worst)
assert worst <= 1e-12, f"FAIL pnl identity rel err {worst}"
print("PASS-5a (هوية pnl بدقة 1e-12 نسبياً على صفقات البطل)")
PY
[ $? -eq 0 ] && pass "PASS-2+3+6+5a" || fail "PASS-2/3/6/5a"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-4: /indicators/compute — الصيغة النصية مدعومة بلا تجاهل صامت ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def post_raw(path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

# (أ) الصيغة النصية → يجب أن تعيد أعمدة ind_zzf_* كاملة
code, body = post_raw("/indicators/compute?symbol=BTCUSDT&timeframe=1h&days=30", {"indicators": ["zigzag_fib"]})
print("HTTP:", code)
assert code == 200, f"string format failed: {json.dumps(body)[:200]}"
cols = body.get("columns") or []
zzf_cols = [c for c in cols if c.startswith("ind_zzf_")]
print("ind_zzf_* columns:", len(zzf_cols), sorted(zzf_cols))
assert len(zzf_cols) >= 13, f"FAIL: expected ≥13 ind_zzf_* columns, got {len(zzf_cols)}"
assert body.get("metadata", {}).get("indicators_requested") == ["zigzag_fib"], "metadata mismatch"
print("PASS-4a (الصيغة النصية → 13+ عمود ind_zzf_*)")

# (ب) صيغة غير صالحة → 422 واضح (لا تجاهل صامت)
code2, body2 = post_raw("/indicators/compute?symbol=BTCUSDT&timeframe=1h&days=30", {"indicators": [42]})
print("invalid format HTTP:", code2, "|", json.dumps(body2, ensure_ascii=False)[:160])
assert code2 == 422, f"FAIL: invalid item silently ignored (got {code2})"
print("PASS-4b (العناصر غير الصالحة تُرفض 422 — لا تجاهل صامت)")
PY
[ $? -eq 0 ] && pass "PASS-4" || fail "PASS-4"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-5: WINUSDT — الدقة تحت السنت + مستوى zzfib 0.618 حرفياً ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def post_raw(path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=280)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

payload = {
  "name":"R13 WINUSDT precision","timeframe":"1m","market":"crypto","symbols":["WINUSDT"],
  "days":5,"initial_capital":10000,"position_sizing":"percentage","position_size_percent":1.0,
  "max_positions":1,"leverage":1,
  "strategy_config":{
    "name":"zzfib touch","base_timeframe":"1m","position_side":"long",
    "indicators":[{"name":"zigzag_fib","type":"support_resistance","params":{"length":100},"enabled":True,"timeframe":"1m"}],
    "entry_rules":[{"name":"touch up","condition":{"type":"indicator_value","operator":">",
      "left_value":"indicator:zigzag_fib:zzfib_touch","right_value":0},"position_side":"long","weight":1,"enabled":True}],
    "exit_rules":[{"name":"touch down","condition":{"type":"indicator_value","operator":"<",
      "left_value":"indicator:zigzag_fib:zzfib_touch","right_value":0},"exit_type":"signal_exit","enabled":True}],
    "risk_management":{"stop_loss_percentage":2.0,"take_profit_percentage":99.0}}}

code, run = post_raw("/backtest1/run?wait=true", payload)
print("HTTP:", code, "| status:", run.get("status"))
assert code == 200 and run.get("status") == "COMPLETED", f"WINUSDT run failed: {json.dumps(run)[:300]}"
cd_ = run.get("chart_data") or {}
candles = cd_.get("visual_candles") or []
sm = run.get("summary") or {}
assert candles, "FAIL: no candles"
c0 = candles[0]
print("WINUSDT close:", repr(c0.get("close")), "| sub-cent:", c0.get("close", 1) < 0.01)
assert c0.get("close", 1) < 0.01, "FAIL: not sub-cent"

# ind_zzf_level_0618 == p1 + (p2−p1)×0.618 حرفياً (بدقة 1e-12 نسبياً)
checked = 0
worst = 0.0
for row in candles:
    p1, p2 = row.get("ind_zzf_p1"), row.get("ind_zzf_p2")
    lv = row.get("ind_zzf_level_0618")
    if p1 is None or p2 is None or lv is None:
        continue
    expected = p1 + (p2 - p1) * 0.618
    denom = max(abs(expected), 1e-300)
    rel = abs(lv - expected) / denom if expected != 0 else abs(lv - expected)
    worst = max(worst, rel)
    checked += 1
    if checked >= 50: break
print("level rows checked:", checked, "| worst relative error:", worst)
assert checked > 0, "FAIL: no rows with ind_zzf_level_0618"
assert worst <= 1e-12, f"FAIL level identity rel err {worst}"
print("PASS-5b (ind_zzf_level_0618 == p1 + (p2−p1)×0.618 حرفياً)")

# pnl identity على صفقات WINUSDT
tps = cd_.get("trade_points") or []
exits = [t for t in tps if t.get("type") == "exit"]
print("WINUSDT trades:", sm.get("total_trades"), "| fees:", sm.get("fees_applied"),
      "| audit consistent:", (sm.get("math_audit") or {}).get("consistent"))
worst_p = 0.0
for t in exits:
    e, x, u, p, d = t.get("entry_price"), t.get("exit_price"), t.get("position_size"), t.get("pnl"), t.get("direction")
    if None in (e, x, u, p): continue
    sign = 1.0 if d == "long" else -1.0
    expected = (x - e) * u * sign
    rel = abs(p - expected) / max(abs(expected), 1e-300) if expected != 0 else abs(p - expected)
    worst_p = max(worst_p, rel)
print("worst relative pnl error (WINUSDT):", worst_p)
assert worst_p <= 1e-12, f"FAIL pnl identity {worst_p}"
assert sm.get("fees_applied") == 0.0, "FAIL fees_applied != 0"
print("PASS-5c (pnl بدقة 1e-12 نسبياً على أسعار تحت السنت)")
PY
[ $? -eq 0 ] && pass "PASS-5" || fail "PASS-5"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-EXTRA: overlays/compute — zzfib levels في summary ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def get(path):
    return json.loads(urllib.request.urlopen(base + path, timeout=120).read())

d = get("/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=30&types=zzfib")
s = d.get("summary") or {}
print("summary.zzfib_levels:", s.get("zzfib_levels"))
print("summary.zzfib_out_of_range:", s.get("zzfib_out_of_range"))
assert s.get("zzfib_levels") == [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0], f"FAIL levels: {s.get('zzfib_levels')}"
assert s.get("zzfib_out_of_range") == [], "FAIL out_of_range not empty"
d2 = get("/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=30&types=fib")
s2 = d2.get("summary") or {}
print("summary.fib_levels:", s2.get("fib_levels"), "| fib_out_of_range:", s2.get("fib_out_of_range"))
assert s2.get("fib_out_of_range") == [], "FAIL fib out_of_range"
print("PASS-EXTRA")
PY
[ $? -eq 0 ] && pass "PASS-EXTRA — levels/out_of_range مرفوعة إلى summary" || fail "PASS-EXTRA"

# -----------------------------------------------------------------------------
echo
if [ "$MODE_EXTERNAL" != "1" ]; then
  pkill -f "uvicorn.*8600" 2>/dev/null
  echo "(local server stopped)"
fi
if [ "$FAILURES" -eq 0 ]; then
  echo "=============================="
  echo "VERIFY-R13: ALL PASS ✅"
  echo "=============================="
else
  echo "=============================="
  echo "VERIFY-R13: $FAILURES FAILURES ❌"
  echo "=============================="
  exit 1
fi
