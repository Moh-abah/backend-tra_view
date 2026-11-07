#!/usr/bin/env bash
# =============================================================================
# VERIFY-TIMEFRAME.sh — الجولة 13.3: عقد تبديل الفريم الزمني في الباك-تست
# =============================================================================
# الاستخدام:
#   ./VERIFY-TIMEFRAME.sh                    # وضع محلي: خادم على 127.0.0.1:8600
#   TF_BASE=http://161.97.73.254:8000/api/v1 ./VERIFY-TIMEFRAME.sh --external
#
# المعايير:
#   PASS-T1  فريم 1h: COMPLETED + summary.timeframe=1h + شبكة الشموع الفعلية
#            = ساعة بالضبط (3600000ms)
#   PASS-T2  فريم 4h (نفس الحمولة، فقط timeframe مبدّل): COMPLETED +
#            summary.timeframe=4h + شبكة فعلية = 4 ساعات (14400000ms) +
#            النتائج تتبدل فعلاً (صفقات/نسب/تواريخ جديدة محسوبة)
#   PASS-T3  فريم غير مدعوم ("45m") → FAILURE صريح برسالة تسرّد المدعوم
#            (لا سقوط صامت إلى 1h — عيب ما قبل 13.3)
#   PASS-T4  الحفظ الدائم: كلا السجلين محفوظان بفريمه الصحيح في القائمة
#   PASS-T5  أعمدة المؤشر ind_zzf_* محسوبة على بيانات الفريم الجديد
# =============================================================================
set -u
cd "$(dirname "$0")"
EXTERNAL="${TF_BASE:-}"
MODE_EXTERNAL=0
[ "${1:-}" = "--external" ] && MODE_EXTERNAL=1

if [ "$MODE_EXTERNAL" = "1" ]; then
  BASE="$EXTERNAL"
  LOG=/tmp/tf_external.log
else
  BASE="http://127.0.0.1:8600/api/v1"
  LOG=/tmp/tf_local_uvicorn.log
  pkill -f "uvicorn.*8600" 2>/dev/null; sleep 1
  DEBUG=true \
  DATABASE_URL="sqlite+aiosqlite:///./local_r13.db" \
  SECRET_KEY="r13local_9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08" \
  HISTORY_CACHE_DIR="${HISTORY_CACHE_DIR:-/tmp/tf_cache}" \
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
echo "################ PASS-T3: الرفض الصريح للفريم غير المدعوم ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
base = sys.argv[1]
def post(path, payload, timeout=300):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

# فريم غير مدعوم → المهمة تفشل برسالة صريحة (كان يجلب 1h زوراً قبل إصلاح 13.3)
code, d = post("/backtest1/run?wait=true", {
    "name": "TF-REJECT-45m", "symbols": ["BTCUSDT"], "timeframe": "45m", "days": 3,
    "initial_capital": 10000, "market": "crypto",
    "strategy_config": {"indicators": [], "entry_rules": [], "exit_rules": []},
})
print("HTTP:", code, "| status:", d.get("status"))
err = str(d.get("error") or "") + json.dumps(d, ensure_ascii=False)[:400]
assert d.get("status") == "FAILURE", f"FAIL: متوقع FAILURE وصلنا {d.get('status')} — {json.dumps(d)[:300]}"
assert "Unsupported timeframe" in err, f"FAIL: الرسالة لا تسرّد العقد: {err[:300]}"
print("error:", str(d.get("error"))[:160])
print("PASS-T3")
PY
[ $? -eq 0 ] && pass "PASS-T3 — الفريم غير المدعوم يُرفض صراحة (FAILURE + رسالة تسرد المدعوم)" || fail "PASS-T3"

# -----------------------------------------------------------------------------
echo
echo "################ PASS-T1/T2/T4/T5: تبديل حي للفريم في نفس الحمولة ################"
python3 - "$BASE" <<'PY'
import json, sys, urllib.request, urllib.error
from collections import Counter
base = sys.argv[1]

def post(path, payload, timeout=420):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.getcode(), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8", "replace"))

def get(path, timeout=120):
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return json.loads(r.read())

def zlf_payload(tf):
    # حمولة ZLF الرسمية — فقط الفريم يتبدل بين التشغيلين (كل شيء آخر ثابت)
    return {
        "name": f"ZLF-TF-CONTRACT-{tf}",
        "timeframe": tf, "market": "crypto", "symbols": ["BTCUSDT"],
        "days": 45, "initial_capital": 10000,
        "position_sizing": "percentage", "position_size_percent": 1.0,
        "max_positions": 1, "commission_rate": 0, "slippage_percent": 0, "leverage": 1,
        "strategy_config": {
            "name": "ZLF — ZigZag Liquidity Fibonacci (3 Entry Signals)",
            "base_timeframe": tf, "position_side": "long",
            "indicators": [{"name": "zigzag_fib", "type": "support_resistance",
                            "params": {"length": 100, "touch_level": 0.618,
                                       "liq_lookback": 20, "liq_signals": True,
                                       "liq_arm_bars": 60},
                            "enabled": True, "timeframe": tf}],
            "entry_rules": [
                {"name": "S1 · اختراق بحجم أكبر", "condition": {"type": "indicator_value",
                 "operator": ">", "left_value": "indicator:zigzag_fib:zzf_entry_s1",
                 "right_value": 0}, "position_side": "long", "weight": 0.34, "enabled": True},
                {"name": "S2 · اختراق بحجم أقل", "condition": {"type": "indicator_value",
                 "operator": ">", "left_value": "indicator:zigzag_fib:zzf_entry_s2",
                 "right_value": 0}, "position_side": "long", "weight": 0.33, "enabled": True},
                {"name": "S3 · رفض بحجم أكبر", "condition": {"type": "indicator_value",
                 "operator": ">", "left_value": "indicator:zigzag_fib:zzf_entry_s3",
                 "right_value": 0}, "position_side": "long", "weight": 0.33, "enabled": True},
            ],
            "exit_rules": [{"name": "تأكيد قمة (provisional)", "condition": {
                "type": "indicator_value", "operator": "<",
                "left_value": "indicator:zigzag_fib:zzf_dir", "right_value": 0},
                "exit_type": "signal_exit", "enabled": True}],
            "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
        },
    }

def run_and_fetch(tf, expect_ms):
    print(f"\n--- تشغيل ZLF بفريم {tf} (days=45 · wait=true) ---")
    code, d = post("/backtest1/run?wait=true", zlf_payload(tf))
    assert code == 200 and d.get("status") == "COMPLETED", \
        f"FAIL run {tf}: HTTP {code} — {json.dumps(d)[:300]}"
    summary = d.get("summary") or {}
    chart = d.get("chart_data") or {}
    candles = chart.get("visual_candles") or []
    bid = d.get("backtest_id")
    # الفريم موثق في الملخص
    stf = summary.get("timeframe")
    assert stf == tf, f"FAIL: summary.timeframe={stf!r} والمطلوب {tf!r}"
    # الشموع موجودة بعدد متوقع (45 يوماً)
    expected_full = 45 * (24 if tf == "1h" else 6)
    assert len(candles) >= int(expected_full * 0.8), \
        f"FAIL: شموع {tf} = {len(candles)} (المتوقع ≈{expected_full})"
    # الشبكة الفعلية = الفريم المطلوب (الفارق الزمني السائد بين الشموع)
    # timestamps تأني كنص ISO ('2026-09-17T16:00:00Z') أو رقم ms — كلاهما يُقبل
    from datetime import datetime as _dt
    ts = []
    for c in candles[:150]:
        raw = c.get("timestamp") or c.get("time")
        if isinstance(raw, str):
            t = int(_dt.fromisoformat(raw.replace("Z", "+00:00")).timestamp() * 1000)
        else:
            t = int(raw)
            ts.append(t if t > 10**12 else t * 1000)
            continue
        ts.append(t)
    gaps = [ts[i+1] - ts[i] for i in range(len(ts) - 1) if ts[i+1] > ts[i]]
    dom = Counter(gaps).most_common(1)[0][0] if gaps else 0
    assert dom == expect_ms, f"FAIL: شبكة {tf} الفعلية={dom}ms والمطلوب={expect_ms}ms"
    trades = summary.get("total_trades")
    pnl = summary.get("total_pnl_percent")
    audit = summary.get("math_audit") or {}
    print(f"    timeframe={stf} · candles={len(candles)} · dominant_gap={dom}ms · "
          f"trades={trades} · pnl%={pnl} · fees={summary.get('fees_applied')} · "
          f"max_abs_error={audit.get('max_abs_error')} · id={bid}")
    return {"trades": trades, "pnl": pnl, "candles": len(candles), "bid": bid,
            "first_ts": ts[0], "doc": d, "summary": summary}

r1 = run_and_fetch("1h", 3_600_000)
r2 = run_and_fetch("4h", 14_400_000)

# T2: النتائج تتبدل فعلاً بين الفريمين — أرقام جديدة محسوبة على بيانات جديدة
first_ts_differs = r1["first_ts"] != r2["first_ts"]
nums_differ = (r1["trades"] != r2["trades"]) or (abs((r1["pnl"] or 0) - (r2["pnl"] or 0)) > 1e-12)
print(f"\nتبدّل النتائج: trades {r1['trades']}→{r2['trades']} · pnl% {r1['pnl']}→{r2['pnl']} · "
      f"أول شمعة تتبدل: {first_ts_differs} · شموع {r1['candles']}→{r2['candles']}")
assert nums_differ or first_ts_differs, \
    "FAIL: النتائج متطابقة بين الفريمين — البيانات لم تتبدل فعلاً"

# T5: أعمدة ind_zzf_* محسوبة على بيانات الفريم الجديد (في الشموع أو flattened)
doc2 = r2["doc"]
c0 = ((doc2.get("chart_data") or {}).get("visual_candles") or [{}])[0]
ind_keys = [k for k in c0.keys() if str(k).startswith("ind_zzf")]
if not ind_keys:
    flat = doc2.get("indicators_flat") or doc2.get("metadata", {}).get("indicators_flat") or {}
    ind_keys = [k for k in flat.keys() if str(k).startswith("ind_zzf")]
print("أعمدة ind_zzf_* على فريم 4h:", len(ind_keys))
assert len(ind_keys) >= 12, f"FAIL: أعمدة ZLF ناقصة على 4h: {ind_keys[:20]}"

# T4: السجلان محفوظان كلٌّ بفريمه في القائمة الدائمة (/backtest/list —
#     الحقل متداخل: data[].summary_stats.timeframe)
lst = get("/backtest/list?limit=20")
items = lst.get("data") or lst.get("backtests") or lst.get("items") or []
tfs = {}
for it in items:
    if isinstance(it, dict):
        ss = it.get("summary_stats") or {}
        tfs[str(it.get("id") or it.get("backtest_id"))] = \
            it.get("timeframe") or ss.get("timeframe")
print("آخر السجلات (id→timeframe):", dict(list(tfs.items())[:8]))
assert tfs.get(str(r1["bid"])) == "1h" and tfs.get(str(r2["bid"])) == "4h", \
    f"FAIL: الحفظ الدائم للفريم غير صحيح: {tfs}"

print("PASS-T1 PASS-T2 PASS-T4 PASS-T5")
PY
[ $? -eq 0 ] && pass "PASS-T1/T2/T4/T5 — تبديل الفريم حي: شبكة صحيحة + أرقام جديدة + حفظ دائم + أعمدة المؤشر" || fail "PASS-T1/T2/T4/T5"

# -----------------------------------------------------------------------------
echo
if [ "$MODE_EXTERNAL" = "0" ]; then
  pkill -f "uvicorn.*8600" 2>/dev/null
  echo "(local server stopped)"
fi
if [ "$FAILURES" -eq 0 ]; then
  echo "✅ ALL PASS — عقد تبديل الفريم الزمني (13.3) مثبت بالكامل"
else
  echo "❌ FAILURES=$FAILURES"
  exit 1
fi
