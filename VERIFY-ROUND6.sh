#!/usr/bin/env bash
# ==============================================================================
# VERIFY-ROUND6.sh — تحقق فوري على خادم الإنتاج بعد النشر (بدون تخمين)
# الاستخدام:  bash VERIFY-ROUND6.sh [HOST]
# مثال:      bash VERIFY-ROUND6.sh http://161.97.73.254:8000
# ==============================================================================
set -u
HOST="${1:-http://161.97.73.254:8000}"
PASS=0; FAIL=0
req() { # name expected method url body
  local name="$1" expect="$2" method="$3" url="$4" body="${5:-}"
  local out
  if [ "$method" = "GET" ]; then out=$(curl -s -m 20 -w "\n%{http_code}" "$url")
  else out=$(curl -s -m 20 -w "\n%{http_code}" -X "$method" -H "Content-Type: application/json" -d "$body" "$url"); fi
  local code=$(echo "$out" | tail -1); local resp=$(echo "$out" | head -n -1)
  if [ "$code" = "$expect" ]; then PASS=$((PASS+1)); echo "✅ PASS | $name | HTTP $code | $(echo $resp | head -c 220)"
  else FAIL=$((FAIL+1)); echo "❌ FAIL | $name | expected=$expect got=$code | $(echo $resp | head -c 300)"; fi
}

echo "==============================================================="
echo " تحقق الجولة 6 — $HOST"
echo "==============================================================="

echo "--- 1) الصحة والتشخيص ---"
req "GET /health" 200 GET "$HOST/health"
req "GET /health/storage (التشخيص الجديد)" 200 GET "$HOST/health/storage"

echo ""
echo "--- 2) تفصيل حالة التخزين ---"
curl -s -m 20 "$HOST/health/storage" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    p=d.get('process',{})
    print(f\"  process: user={p.get('user')} euid={p.get('euid')}\")
    for db in d.get('databases',[]):
        mark='✅' if db.get('ok') else '❌'
        print(f\"  {mark} [{db['label']}] → {db.get('resolved')} | writable={db.get('writable')} fallback={db.get('fallback_active')} err={db.get('last_error')}\")
except Exception as e:
    print('  parse error:', e)
"

echo ""
echo "--- 3) أدوات الرسم: دورة كاملة حفظ→قراءة→حذف ---"
TS=$(date +%s)
req "POST حفظ أداة" 200 POST "$HOST/api/v1/chart/drawings/crypto/BTCUSDT?timeframe=15m" \
  "{\"timeframe\":\"15m\",\"drawings\":[{\"id\":\"verify-$TS\",\"type\":\"trend_line\",\"points\":[{\"time\":$TS,\"price\":1.0}],\"style\":{\"color\":\"#f00\"}}]}"
req "GET قراءة الأداة" 200 GET "$HOST/api/v1/chart/drawings/crypto/BTCUSDT?timeframe=15m"
req "DEL حذف الأداة" 200 "DELETE" "$HOST/api/v1/chart/drawings/crypto/BTCUSDT?timeframe=15m"

echo ""
echo "--- 4) المؤشرات المحفوظة (كانت readonly) ---"
req "POST إضافة مؤشر RSI" 200 POST "$HOST/indicators/manage/add?symbol=BTCUSDT&timeframe=15m&market=crypto" \
  '{"name":"rsi","type":"oscillator","params":{"period":14}}'

echo ""
echo "==============================================================="
echo " النتيجة: $PASS ناجح / $FAIL فاشل"
if [ "$FAIL" = "0" ]; then
  echo " ✅ الجولة 6 مثبتة على الإنتاج — راقب السجل أيضاً:"
  echo "    docker logs --tail 50 trading-backend | grep -E 'Market ticker WS|🩹|Storage'"
  echo "    (يجب أن ترى: 🟢 Market ticker WS connected: ...miniTicker...)"
else
  echo " ⚠️ يوجد فشل — انسخ المخرجات كاملة لوكيل الباك"
fi
echo "==============================================================="
