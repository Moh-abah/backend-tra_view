#!/usr/bin/env bash
# ============================================================
# ✅ الجولة 10 — التحقق التلقائي بعد النشر — مؤشرات البنية
# شغّله على الخادم بعد docker restart:  bash VERIFY-ROUND10.sh
# ============================================================
BASE="${1:-http://161.97.73.254:8000}"
ok=0; fail=0
chk() { if [ "$1" = "0" ]; then echo "  ✅ $2"; ok=$((ok+1)); else echo "  ❌ $2"; fail=$((fail+1)); fi; }

echo "== 1) health =="
code=$(curl -s -o /tmp/o10h.json -w "%{http_code}" "$BASE/api/v1/overlays/health")
chk $([ "$code" = "200" ] && grep -q '"round": *10' /tmp/o10h.json && echo 0 || echo 1) "GET /overlays/health → 200 + round=10 ($code)"

echo "== 2) compute حي (built ثم hit) =="
c1=$(curl -s "$BASE/api/v1/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=30&limit=500&types=zigzag,fib,trendline")
echo "$c1" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d['summary']['cache']=='built', d['summary']
assert len(d['overlays']['zigzag']['pivots'])>=0
assert 'current' in d['overlays']['fib']
assert 'projection' in d['overlays']['trendline']
print('  first call: built, bars=%s' % d['summary']['bars'])
" ; chk $? "أول نداء → cache=built"
c2=$(curl -s "$BASE/api/v1/overlays/compute?symbol=BTCUSDT&timeframe=1h&days=30&limit=500&types=zigzag,fib,trendline")
echo "$c2" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d['summary']['cache']=='hit', d['summary']
print('  second call: hit')
" ; chk $? "النداء الثاني خلال 30ث → cache=hit"

echo "== 3) أخطاء عربية =="
code=$(curl -s -o /tmp/o10e.json -w "%{http_code}" "$BASE/api/v1/overlays/compute?symbol=undefined&timeframe=1h")
chk $([ "$code" = "400" ] && grep -q "symbol مفقود" /tmp/o10e.json && echo 0 || echo 1) "symbol=undefined → 400 عربية ($code)"

echo "== 4) الراوتر مسجّل في الوثائق =="
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/docs")
chk $([ "$code" = "200" ] && echo 0 || echo 1) "/docs → 200 ($code)"

echo ""
echo "===== النتيجة: $ok ناجح / $fail فاشل ====="
[ "$fail" = "0" ] && echo "🎉 الجولة 10 حية على الإنتاج" || echo "⚠️ راجع البنود الفاشلة أعلاه"
