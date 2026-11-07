# 🚀 PATCH-ROUND12 — تعليمات النشر السريعة
**الحزمة:** ROUND12-ZIGZAG-FIB.zip · **التاريخ:** 2026-10-31 · **16 ملفاً** (15 تعديلاً + 1 جديد) — بلا قواعد بيانات، بلا اعتماديات جديدة.

## الملفات
```
app/services/indicators/overlays.py          ← دالة zigzag_fib + OVERLAY_TYPES + compute_overlays
app/services/indicators/overlay_columns.py   ← مرادفات zzfib + أعمدة ind_zzf_*
app/services/indicators/overlay_adapters.py  ← تسجيل zigzag_fib في /indicators/available
app/services/indicators/calculator.py        ← جسر zigzag_fib (العنونة الثلاثية)
app/services/strategy/conditions.py          ← مرادفات zzfib_* → ind_zzf_* + رسائل صريحة
app/services/strategy/schemas.py             ← composite remap/رفض واضح + commission 0
app/services/strategy/presets.py             ← (جديد) البطل ZigZag HL v2 — ZERO FEE
app/backtest/schemas.py                      ← commission/slippage=0 + fill_model + أعمدة الشفافية
app/backtest/engine1.py                      ← signal_close + الشفافية + math_audit + إصلاح نقاط الخروج
app/tasks/backtest_tasks.py                  ← summary: fees_applied/fill_model/math_audit
app/routers/indicators.py                    ← (جديد) POST/GET /indicators/compute
app/routers/backtest.py                      ← إصلاح البادئة المزدوجة ind_ind_*
app/routers/strategies.py                    ← GET /strategies/presets
app/routers/strategies1.py                   ← GET /strategies1/presets
app/routers/api.py                           ← /health و /status بدون redis
app/routers/market_data.py                   ← كاش صفحات الشموع + status بدون redis
```

## النشر
```bash
unzip ROUND12-ZIGZAG-FIB.zip -d /tmp/r12 && cd /tmp/r12
for f in $(find app -type f); do docker cp "$f" "trading-backend:/app/$f"; done
docker restart trading-backend
bash VERIFY-R12.sh    # المتوقع: PASS-1 .. PASS-8
```

## ما الذي يتغير للواجهة بعد النشر؟
1. `GET /indicators/available` يضيف `zigzag_fib` (والمقتصر `zzfib`).
2. `POST /indicators/compute` — نقطة جديدة (كانت 404).
3. `/backtest/get/{id}.summary` يضيف `fees_applied` + `fill_model` + `math_audit`.
4. كل exit point في `chart_data.trade_points` يضيف `price_delta/price_delta_pct/direction/result_pct/pnl_gross/fill_entry/fill_exit`.
5. `POST /backtest/run` يقبل `fill_model: "signal_close"|"next_open"` (الافتراضي next_open بلا أي تغيير سلوكي).
6. شكل `{"type":"composite","logic":"and"}` يعمل الآن (يُوحَّد تلقائياً + تحذير)؛ أي شكل آخر يُرفض برسالة عربية واضحة.
7. `GET /strategies/presets` و `/strategies1/presets` — حمولة البطل جاهزة.
8. `/api/v1/health` و `/status` بدون redis (الأولوية لقاعدة البيانات فقط).
9. `chart-data?include_indicators=true` يعيد أعمدة البنية ببادئة واحدة صحيحة `ind_zz_* / ind_zzf_*`.
10. صفحات `/market/candles/...?before=` المتكررة فورية (كاش داخل العملية).

## التراجع
استعادة ملفات v14 السابقة (نفس القائمة أعلاه) + `docker restart trading-backend`.
