#!/usr/bin/env bash
# =============================================================================
# VERIFY-ZLF.sh — معايير قبول الجولة 13.2 حرفياً (المصفوفة المصادقة من ثلاث
#                 جهات: قراءة الوكيلين + تصديق المستخدم — ZLF v13.2)
#
# الاستخدام:
#   ./VERIFY-ZLF.sh                    # وضع محلي: يشغّل خادماً على 127.0.0.1:8600 ثم يوقفه
#   ZLF_BASE=http://161.97.73.254:8000/api/v1 ./VERIFY-ZLF.sh --external
#                                      # وضع خارجي: يختبر خادماً حياً دون تشغيل محلي
#
# PASS-Z1  القالب الرسمي zlf_triple_signal_zero_fee موجود بثلاث قواعد دخول S1/S2/S3
# PASS-Z2  /indicators/compute يعيد 25 عمود ind_zzf_* (13 أصلية + 12 جديدة ZLF)
# PASS-Z3  اتساق آلة حالة السيولة على بيانات حية (state/ref_high/vol_ok/signals/entry)
# PASS-Z4  باك-تست ZLF كامل: COMPLETED + math_audit 1e-9 + precision_report + fees 0
# PASS-Z5  كل صفقة دخول تحمل اسم إشارتها (S1/S2/S3) في decision_reason
# PASS-Z6  /strategies1/validate يقبل حمولة ZLF (valid=true)
# =============================================================================
set -u
cd "$(dirname "$0")"
EXTERNAL="${ZLF_BASE:-}"
MODE_EXTERNAL=0
[ "${1:-}" = "--external" ] && MODE_EXTERNAL=1

if [ "$MODE_EXTERNAL" = "1" ]; then
  BASE="$EXTERNAL"
  LOG=/tmp/zlf_external.log
else
  BASE="http://127.0.0.1:8600/api/v1"
  LOG=/tmp/zlf_local_uvicorn.log
  pkill -f "uvicorn.*8600" 2>/dev/null; sleep 1
  DEBUG=true \
  DATABASE_URL="sqlite+aiosqlite:///./local_r13.db" \
  SECRET_KEY="r13local_9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08" \
  HISTORY_CACHE_DIR="${HISTORY_CACHE_DIR:-/tmp/zlf_cache}" \
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
echo "################ PASS-Z1: القالب الرسمي ZLF بثلاث قواعد دخول ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def get(path):
    with urllib.request.urlopen(base + path, timeout=60) as r:
        return json.loads(r.read())

d = get("/strategies1/presets")
presets = d.get("presets") or []
zlf = next((p for p in presets if p.get("id") == "zlf_triple_signal_zero_fee"), None)
print("presets:", [p.get("id") for p in presets])
assert zlf, "FAIL: zlf_triple_signal_zero_fee غير موجود في القوالب"
pl = zlf["payload"]
sc = pl["strategy_config"]
rules = sc["entry_rules"]
names = [r["name"] for r in rules]
print("entry_rules:", names)
assert len(rules) == 3, f"FAIL: expected 3 entry rules, got {len(rules)}"
assert any("S1" in n for n in names) and any("S2" in n for n in names) and any("S3" in n for n in names), \
    f"FAIL: أسماء الإشارات الثلاث غير موجودة: {names}"
refs = [r["condition"]["left_value"] for r in rules]
print("rule refs:", refs)
assert all("zzf_entry_s" in r for r in refs), f"FAIL: مراجع الأعمدة خاطئة: {refs}"
w = sum(r["weight"] for r in rules if r.get("enabled", True))
assert w <= 1.0 + 1e-9, f"FAIL: مجموع الأوزان {w} > 1.0"
ind = sc["indicators"][0]
assert ind["name"] in ("zigzag_fib", "zzfib"), f"FAIL: indicator={ind['name']}"
for k in ("liq_lookback", "liq_signals", "liq_arm_bars", "touch_level", "length"):
    assert k in ind["params"], f"FAIL: param {k} مفقود"
print("params:", ind["params"])
assert len(sc["exit_rules"]) >= 1, "FAIL: لا قواعد خروج"
print("PASS-Z1")
PY
[ $? -eq 0 ] && pass "PASS-Z1 — القالب الرسمي بثلاث إشارات دخول S1/S2/S3" || fail "PASS-Z1"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-Z2: أعمدة ind_zzf_* كاملة (25 عموداً) ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def post(path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

code, d = post("/indicators/compute", {"symbol": "BTCUSDT", "timeframe": "1h", "days": 30,
                                       "indicators": ["zigzag_fib"]})
print("HTTP:", code)
assert code == 200, f"FAIL compute: {json.dumps(d)[:300]}"
cols = d.get("columns") or (d.get("data") or [{}])[0].keys() if d.get("data") else d.get("columns")
rows = d.get("rows") or d.get("data") or []
if not cols and rows:
    cols = list(rows[0].keys())
zzf = [c for c in (cols or []) if str(c).startswith("ind_zzf_")]
print("ind_zzf_* columns:", len(zzf), sorted(zzf))
new_cols = ["ind_zzf_liq_state", "ind_zzf_liq_ref_high", "ind_zzf_liq_ref_vol", "ind_zzf_liq_vol_ok",
            "ind_zzf_signal_s1", "ind_zzf_signal_s2", "ind_zzf_signal_s3", "ind_zzf_signal_any",
            "ind_zzf_entry", "ind_zzf_entry_s1", "ind_zzf_entry_s2", "ind_zzf_entry_s3"]
missing = [c for c in new_cols if c not in zzf]
assert not missing, f"FAIL: أعمدة ZLF مفقودة: {missing}"
assert len(zzf) >= 25, f"FAIL: expected >=25 ind_zzf_*, got {len(zzf)}"
print("PASS-Z2")
PY
[ $? -eq 0 ] && pass "PASS-Z2 — 25 عمود ind_zzf_* (13 أصلية + 12 ZLF)" || fail "PASS-Z2"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-Z3: اتساق آلة حالة السيولة على بيانات حية ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def post(path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

code, d = post("/indicators/compute", {"symbol": "BTCUSDT", "timeframe": "1h", "days": 60,
                                       "indicators": ["zigzag_fib"]})
assert code == 200, f"FAIL compute: {json.dumps(d)[:300]}"
rows = d.get("rows") or d.get("data") or []
assert rows, "FAIL: no rows"

def g(row, *keys):
    for k in keys:
        if k in row:
            return row[k]
    ind = row.get("indicators") or {}
    for k in keys:
        if k in ind:
            return ind[k]
    return None

# ✅ v13.2 — المصفوفة المصادقة: R = أكبر حجم أحمر بالنافذة · ref_high = أعلى قمة
# حمراء · G خضراء · S1/S2/S3 بعلاقة الحجم مع الحمراء (لا بالإغلاق).
# ملاحظة: الهيمنة الخضراء والانطلاقة (0.382) تُفحصان في اختبارات الوحدة (تحتاج
# فهارس R والساق — غير معروضة كأعمدة) — هنا نفحص الشروط الضرورية الخارجية.
st_bad = vol_bad = sig_bad = ent_bad = 0
n_state = n_vol = n_sig = n_ent = 0
for i, row in enumerate(rows):
    state = g(row, "ind_zzf_liq_state")
    if state is None:
        continue
    hi, cl, op, vol = g(row, "high"), g(row, "close"), g(row, "open"), g(row, "volume")
    rh, rv = g(row, "ind_zzf_liq_ref_high"), g(row, "ind_zzf_liq_ref_vol")
    green = (cl is not None and op is not None and cl > op)
    if state == 0:
        # v13.2: state 0 قد يصحب مرجعاً (شمعة غير خضراء أو الخلية الرابعة)
        if rh is not None and green and rv is not None and vol is not None and (hi > rh or vol > rv):
            st_bad += 1
            if st_bad <= 3: print("  state0 bad @", i, "green مع كسر/هيمنة لكن بلا حالة")
        continue
    n_state += 1
    ok = True
    if state == 1.0:
        ok = green and hi > rh and vol > rv          # S1: اختراق ∧ حجم أكبر
    elif state == 2.0:
        ok = green and hi > rh and vol <= rv         # S2: اختراق ∧ حجم أقل أو مساوٍ
    elif state == 3.0:
        ok = green and hi <= rh and vol > rv         # S3: رفض ∧ حجم أكبر
    if not ok:
        st_bad += 1
        if st_bad <= 3: print("  state bad @", i, "state=", state, "hi=", hi, "rh=", rh, "vol=", vol, "rv=", rv, "green=", green)
    volok = g(row, "ind_zzf_liq_vol_ok")
    expect_vol = 1.0 if (rv is not None and vol is not None and vol > rv) else 0.0
    if volok != expect_vol:
        vol_bad += 1
    else:
        n_vol += 1
    s1, s2, s3 = (g(row, "ind_zzf_signal_s1"), g(row, "ind_zzf_signal_s2"), g(row, "ind_zzf_signal_s3"))
    fired = [x for x, v in ((1, s1), (2, s2), (3, s3)) if v == 1.0]
    if fired:
        n_sig += 1
        # الإشارة تستلزم حالتها وحجمها (الشروط الضرورية — الهيمنة/الانطلاقة بالوحدة)
        need_vol_ok = 1.0 if fired[0] in (1, 3) else 0.0
        if state not in fired or volok != need_vol_ok:
            sig_bad += 1
            if sig_bad <= 3: print("  signal bad @", i, "state=", state, "fired=", fired, "volok=", volok)
        if len(fired) > 1:
            sig_bad += 1  # مستحيل: الخلايا متعاداة بالبنية (حدث واحد لكل شمعة)
    ent = g(row, "ind_zzf_entry")
    if ent == 1.0:
        n_ent += 1
        e1, e2, e3 = (g(row, "ind_zzf_entry_s1"), g(row, "ind_zzf_entry_s2"), g(row, "ind_zzf_entry_s3"))
        marks = [x for x, v in ((1, e1), (2, e2), (3, e3)) if v == 1.0]
        if len(marks) != 1:
            ent_bad += 1
            if ent_bad <= 3: print("  entry bad @", i, "marks=", marks, "(يجب إسناد واحد بالضبط)")

print(f"rows with state: {n_state} · vol_ok consistent: {n_vol} · liquidity events: {n_sig} · entries: {n_ent}")
assert n_state > 0, "FAIL: لا صفوف حالة (التمهيد أكل كل شيء؟)"
assert st_bad == 0, f"FAIL: {st_bad} صفوف حالة غير متسقة (مصفوفة v13.2)"
assert vol_bad == 0, f"FAIL: {vol_bad} صفوف vol_ok غير متسقة"
assert sig_bad == 0, f"FAIL: {sig_bad} أحداث غير متسقة"
assert ent_bad == 0, f"FAIL: {ent_bad} دخولات بلا إسناد واحد بالضبط"
print("PASS-Z3")
PY
[ $? -eq 0 ] && pass "PASS-Z3 — آلة حالة السيولة متسقة 100% على بيانات حية" || fail "PASS-Z3"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-Z4+Z5: باك-تست ZLF الكامل — دقة + Zero-Fee + إسناد الإشارات ################"
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

zlf = {
  "name":"ZLF Triple Signal — R13.2 VERIFY","timeframe":"1h","market":"crypto","symbols":["BTCUSDT"],
  "days":200,"initial_capital":10000,"position_sizing":"percentage","position_size_percent":1.0,
  "max_positions":1,"commission_rate":0,"slippage_percent":0,"leverage":1,
  "strategy_config":{
    "name":"ZLF — ZigZag Liquidity Fibonacci (3 Entry Signals)","base_timeframe":"1h","position_side":"long",
    "indicators":[{"name":"zigzag_fib","type":"support_resistance","params":{
        "length":100,"touch_level":0.618,"liq_lookback":20,"liq_signals":True,"liq_arm_bars":60},
        "enabled":True,"timeframe":"1h"}],
    "entry_rules":[
      {"name":"S1 · الحالة الأولى: اختراق قمة الحمراء بحجم أكبر (Breakout + Higher Volume)","condition":{"type":"indicator_value","operator":">",
        "left_value":"indicator:zigzag_fib:zzf_entry_s1","right_value":0},"position_side":"long","weight":0.34,"enabled":True},
      {"name":"S2 · الحالة الثانية: اختراق قمة الحمراء بحجم أقل (Breakout + Lower Volume)","condition":{"type":"indicator_value","operator":">",
        "left_value":"indicator:zigzag_fib:zzf_entry_s2","right_value":0},"position_side":"long","weight":0.33,"enabled":True},
      {"name":"S3 · الحالة الثالثة: رفض بلا اختراق بحجم أكبر (No Break + Higher Volume)","condition":{"type":"indicator_value","operator":">",
        "left_value":"indicator:zigzag_fib:zzf_entry_s3","right_value":0},"position_side":"long","weight":0.33,"enabled":True}],
    "exit_rules":[{"name":"تأكيد قمة — انقلاب الساق إلى هابطة (Confirmed Top → Down Leg)","condition":{"type":"indicator_value","operator":"<",
      "left_value":"indicator:zigzag_fib:zzf_dir","right_value":0},"exit_type":"signal_exit","enabled":True}],
    "risk_management":{"stop_loss_percentage":2.0,"take_profit_percentage":99.0}}}

code, run = post_raw("/backtest1/run?wait=true", zlf)
print("HTTP:", code, "| status:", run.get("status"), "| mode:", run.get("mode"))
assert code == 200 and run.get("status") == "COMPLETED", f"run failed: {json.dumps(run)[:400]}"
cd_ = run.get("chart_data") or {}
sm = run.get("summary") or run.get("metrics") or {}
ma = sm.get("math_audit") or {}
print("trades:", sm.get("total_trades"), "| total_pnl_percent:", sm.get("total_pnl_percent"),
      "| fees_applied:", sm.get("fees_applied"), "| fill_model:", sm.get("fill_model"))
print("formula:", ma.get("formula"))
print("max_abs_error:", ma.get("max_abs_error"), "| precision_report:", ma.get("precision_report"))

# عقد الدقة المتناهية نفسه على استراتيجية ZLF
assert ma.get("formula") == "pnl == (exit_price - entry_price) * units * (long? +1 : -1)", f"FAIL formula: {ma.get('formula')!r}"
assert ma.get("max_abs_error") is not None and ma["max_abs_error"] <= 1e-9, f"FAIL max_abs_error={ma.get('max_abs_error')}"
pr = ma.get("precision_report") or {}
assert pr.get("float64") is True and pr.get("formula_tolerance") == 1e-9 and pr.get("rounded_fields") == [], \
    f"FAIL precision_report={pr}"
assert ma.get("consistent") is True, "FAIL math_audit.consistent != true"
assert sm.get("fees_applied") == 0.0, f"FAIL fees_applied={sm.get('fees_applied')}"
print("PASS-Z4 (COMPLETED · الصيغة الصافية · 1e-9 · precision_report · fees 0)")

# إسناد الإشارات: كل دخول يحمل اسم إشارته S1/S2/S3
tps = cd_.get("trade_points") or []
entries = [t for t in tps if t.get("type") == "entry"]
exits = [t for t in tps if t.get("type") == "exit"]
print("entry points:", len(entries), "| exit points:", len(exits))
sig_counts = {"S1": 0, "S2": 0, "S3": 0}
for t in entries:
    rsn = str(t.get("decision_reason") or "")
    tag = rsn.strip()[:2]
    if tag in sig_counts: sig_counts[tag] += 1
    assert t.get("commission") == 0.0, "FAIL: entry commission != 0.0"
print("إسناد الإشارات للدخولات:", sig_counts)
assert entries, "FAIL: لا نقاط دخول — الاستراتيجية لم تُنتج إشارات"
assert all(str(t.get("decision_reason") or "").strip()[:2] in ("S1", "S2", "S3") for t in entries), \
    "FAIL: دخول بلا إسناد S1/S2/S3: " + json.dumps([t.get("decision_reason") for t in entries][:3], ensure_ascii=False)
assert exits, "FAIL: لا نقاط خروج"
assert all(t.get("commission") == 0.0 for t in exits), "FAIL: exit commission != 0.0"
assert all(t.get("result_pct") == t.get("price_delta_pct") for t in exits), "FAIL: result_pct != price_delta_pct"
print("PASS-Z5 (كل دخول بإشارته · commission=0.0 · result_pct==price_delta_pct)")
PY
[ $? -eq 0 ] && pass "PASS-Z4+Z5 — باك-تست ZLF v13.2 بدقة 1e-9 وإسناد الإشارات الثلاث" || fail "PASS-Z4+Z5"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-Z6: /strategies1/validate يقبل حمولة ZLF ################"
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
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

code, v = post_raw("/strategies1/validate", {
  "name":"ZLF validate","base_timeframe":"1h","position_side":"long",
    "indicators":[{"name":"zigzag_fib","type":"support_resistance","params":{
        "length":100,"touch_level":0.618,"liq_lookback":20,"liq_signals":True,"liq_arm_bars":60},
        "enabled":True,"timeframe":"1h"}],
    "entry_rules":[
      {"name":"S1","condition":{"type":"indicator_value","operator":">",
        "left_value":"indicator:zigzag_fib:zzf_entry_s1","right_value":0},"position_side":"long","weight":0.34,"enabled":True},
      {"name":"S2","condition":{"type":"indicator_value","operator":">",
        "left_value":"indicator:zigzag_fib:zzf_entry_s2","right_value":0},"position_side":"long","weight":0.33,"enabled":True},
      {"name":"S3","condition":{"type":"indicator_value","operator":">",
        "left_value":"indicator:zigzag_fib:zzf_entry_s3","right_value":0},"position_side":"long","weight":0.33,"enabled":True}],
    "exit_rules":[{"name":"top","condition":{"type":"indicator_value","operator":"<",
      "left_value":"indicator:zigzag_fib:zzf_dir","right_value":0},"exit_type":"signal_exit","enabled":True}],
    "risk_management":{"stop_loss_percentage":2.0,"take_profit_percentage":99.0}})
print("HTTP:", code, "| valid:", v.get("valid"))
assert code == 200 and v.get("valid") is True, f"FAIL validate: {json.dumps(v)[:300]}"
print("PASS-Z6")
PY
[ $? -eq 0 ] && pass "PASS-Z6 — validate يقبل حمولة ZLF (valid=true)" || fail "PASS-Z6"

# -----------------------------------------------------------------------------
echo
if [ "$MODE_EXTERNAL" != "1" ]; then
  pkill -f "uvicorn.*8600" 2>/dev/null
fi
if [ "$FAILURES" -eq 0 ]; then
  echo "=============================="
  echo "VERIFY-ZLF: ALL PASS ✅"
  echo "=============================="
else
  echo "=============================="
  echo "VERIFY-ZLF: ${FAILURES} FAILURES ❌"
  echo "=============================="
  exit 1
fi
