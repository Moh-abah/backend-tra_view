#!/usr/bin/env bash
# ============================================================
# ✅ الجولة 11 (v2) — التحقق التلقائي بعد النشر
# عقود وكيل الفرونت الستة كاملة — شغّله بعد docker restart:
#   bash VERIFY-ROUND11.sh [BASE]
# ============================================================
BASE="${1:-http://161.97.73.254:8000}"
ok=0; fail=0
chk() { if [ "$1" = "0" ]; then echo "  ✅ $2"; ok=$((ok+1)); else echo "  ❌ $2"; fail=$((fail+1)); fi; }

echo "== 0) نبض المؤشرات =="
code=$(curl -s -o /tmp/v11h.json -w "%{http_code}" "$BASE/api/v1/overlays/health")
chk $([ "$code" = "200" ] && echo 0 || echo 1) "GET /overlays/health → 200 ($code)"

echo "== 1) المطلوب 5-ب: المسارات المفقودة راجعة =="
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/v1/strategies1/list?active_only=false")
chk $([ "$code" = "200" ] && echo 0 || echo 1) "GET /strategies1/list → 200 ($code)"
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/v1/backtest1/list?limit=5")
chk $([ "$code" = "200" ] && echo 0 || echo 1) "GET /backtest1/list → 200 ($code)"

echo "== 2) المطلوب 1+2: الأسماء الكاملة في السجل =="
curl -s "$BASE/api/v1/indicators/available" | python3 -c "
import json,sys
d=json.load(sys.stdin)
items = d if isinstance(d, list) else d.get('indicators') or d.get('data') or []
names = {str(x.get('name','')).lower() for x in items} if isinstance(items, list) else set()
need = {'zigzag_channels','auto_fib_retracement','auto_trendline','zigzag','fib','trendline'}
missing = need - names
assert not missing, f'missing: {missing}'
print(f'  السجل يضم {len(names)} مؤشراً — الأسماء الستة كلها حاضرة')
"; chk $? "الأسماء الثلاثة (بصيغتيها) في /indicators/available"

echo "== 3) المطلوب 5-أ: validate يرفض المجهول =="
curl -s -X POST "$BASE/api/v1/strategies1/validate" -H "Content-Type: application/json" -d '{
  "name":"NEG","indicators":[{"name":"super_unknown_xyz","type":"support_resistance"}],
  "entry_rules":[{"name":"r","condition":{"type":"indicator_value","operator":">","left_value":"indicator:rsi","right_value":0}}]
}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('valid') == False, d
assert 'غير مسجل في المحرك' in str(d.get('errors')), d
print('  رفض: %s' % d.get('errors'))
"; chk $? "validate → valid:false برسالة عربية للاسم المجهول"

curl -s -X POST "$BASE/api/v1/strategies1/validate" -H "Content-Type: application/json" -d '{
  "name":"POS","indicators":[
    {"name":"zigzag_channels","type":"support_resistance","params":{"length":100}},
    {"name":"auto_fib_retracement","type":"support_resistance"},
    {"name":"auto_trendline","type":"support_resistance"}],
  "entry_rules":[{"name":"r","condition":{"type":"indicator_value","operator":">","left_value":"indicator:rsi","right_value":0}}]
}' | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('valid') == True, d
"; chk $? "validate يقبل الأسماء الكاملة الثلاثة"

echo "== 4) المطلوب 2+3+4: العنونة ثلاثية الأجزاء داخل المحرك (استراتيجية البطل) =="
RUN=$(curl -s -X POST "$BASE/api/v1/strategies1/run?symbol=BTCUSDT&timeframe=1h&market=crypto&days=60&live_mode=false" \
  -H "Content-Type: application/json" -d '{
  "name":"R11 HERO PROBE","version":"1.0.0","base_timeframe":"1h","position_side":"long",
  "indicators":[{"name":"zigzag_channels","type":"support_resistance","params":{"length":100},"enabled":true,"timeframe":"1h"}],
  "entry_rules":[{"name":"HL_Entry","position_side":"long","weight":1,"enabled":true,
    "condition":{"type":"and","conditions":[
      {"type":"indicator_value","operator":">","left_value":"indicator:zigzag_channels:zz_pivot_low","right_value":0},
      {"type":"indicator_value","operator":">","left_value":"indicator:zigzag_channels:zz_pivot_low","right_value":"indicator:zigzag_channels:zz_prev_pivot_low"}
    ]}}],
  "exit_rules":[{"name":"Top_Exit","exit_type":"signal_exit","enabled":true,
    "condition":{"type":"indicator_value","operator":">","left_value":"indicator:zigzag_channels:zz_pivot_high","right_value":0}}],
  "filter_rules":[],
  "risk_management":{"stop_loss_percentage":2.0,"take_profit_percentage":99.0}
}')
echo "$RUN" | python3 -c "
import json,sys
d=json.load(sys.stdin)
total=d.get('total_bars_processed',0); active=d.get('active_decisions_count',0)
assert total>0, 'لا قرارات!'
assert active>0, 'صفر نشطة — الجسر/الأعمدة غير فعالة!'
print(f'  قرارات: {total} | نشطة: {active}')
"; chk $? "شرط HL ثلاثي الأجزاء عبر المحرك → قرارات نشطة > 0 (كانت 0)"

echo "$RUN" | python3 -c "
import json,sys
d=json.load(sys.stdin)
acts=[x for x in d.get('decisions',[]) if x.get('action') in ('BUY','SELL')]
assert acts, 'لا BUY/SELL'
print(f'  أول إشارة: {acts[0][\"action\"]} @ {acts[0][\"timestamp\"][:16]}')
"; chk $? "إشارات BUY/SELL حقيقية من هيكل HL"

echo
echo "===== النتيجة: $ok ناجح / $fail فاشل ====="
if [ "$fail" = "0" ]; then
  echo "🎉 الجولة 11 (v2) حية — عقود الفرونت الستة منفذة كاملة"
else
  echo "⚠️ راجع البنود الفاشلة أعلاه — وأرسل السجلات لوكيل الباكند"
fi
