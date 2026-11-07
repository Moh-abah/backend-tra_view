═══════════════════════════════════════════════════════════════
 BACKEND v13.0 — الجولة 13: إبادة العمولة + عقد الدقة المتناهية
═══════════════════════════════════════════════════════════════
التاريخ: 2026-11-01
الأساس: v12.9 المنشورة على الإنتاج (تحققت حياً 13/13)
النسخة: 13.0

───────────────────────────────────────────────────────────────
النشر على الإنتاج (نفس أسلوب 12.9):
───────────────────────────────────────────────────────────────
  # 1) انسخ الملفات المعدّلة (13 ملفاً):
  docker cp app/backtest/schemas.py                trading-backend:/app/app/backtest/schemas.py
  docker cp app/backtest/engine1.py                trading-backend:/app/app/backtest/engine1.py
  docker cp app/backtest/metrics.py                trading-backend:/app/app/backtest/metrics.py
  docker cp app/services/strategy/schemas.py       trading-backend:/app/app/services/strategy/schemas.py
  docker cp app/services/strategy/full_strategy.py trading-backend:/app/app/services/strategy/full_strategy.py
  docker cp app/services/strategy/presets.py       trading-backend:/app/app/services/strategy/presets.py
  docker cp app/services/strategy/strategys/rsi_strategy.py           trading-backend:/app/app/services/strategy/strategys/rsi_strategy.py
  docker cp app/services/strategy/strategys/mean_reversion_strategy.py trading-backend:/app/app/services/strategy/strategys/mean_reversion_strategy.py
  docker cp app/services/strategy/strategys/macd_strategy.py          trading-backend:/app/app/services/strategy/strategys/macd_strategy.py
  docker cp app/services/strategy/strategys/test_strategy.py          trading-backend:/app/app/services/strategy/strategys/test_strategy.py
  docker cp app/services/strategy/strategys/trend_strategy.py         trading-backend:/app/app/services/strategy/strategys/trend_strategy.py
  docker cp app/routers/indicators.py              trading-backend:/app/app/routers/indicators.py
  docker cp app/routers/overlays.py                trading-backend:/app/app/routers/overlays.py

  # 2) احذف ملفات المحرك الميتة (تحتوي كود عمولة قديم — غير مستوردة إطلاقاً،
  #    حذفها يضمن أن كود العمولة لا يعود يوماً):
  docker exec trading-backend rm -f /app/app/backtest/engine.py /app/app/backtest/engine_copy.py

  # 3) إعادة التشغيل:
  docker restart trading-backend

  # 4) التحقق الحرفي (من ملف الحزمة):
  ./VERIFY-R13.sh --external
  # أو مباشرة:
  R13_BASE=http://161.97.73.254:8000/api/v1 ./VERIFY-R13.sh --external

───────────────────────────────────────────────────────────────
ما الذي تغيّر (الجولة 13):
───────────────────────────────────────────────────────────────
1) إبادة العمولة بنيوياً (سياسة Zero-Fee — قرار المستخدم الحرفي):
   - commission_rate/slippage_percent في BacktestConfig و StrategyConfig:
     deprecated في OpenAPI + أي قيمة > 0 → 422 برسالة عربية صريحة.
     (0 أو غياب الحقل يُقبل بصمت — توافق خلفي).
   - محرك engine1.py: كود تطبيق العمولة/الانزلاق مُمسوح بالكامل من
     _close_trade_logic ومن فتح الصفقات ومن trade_points — لا فرع شرطي
     ولا fallback في التواقيع.
   - حذف ملفين ميتين بالكامل: app/backtest/engine.py و engine_copy.py
     (غير مستوردين في أي مكان — كانا يحملان كود عمولة قديماً).
   - حقل commission في الاستجابة ثابت 0.0 (DEPRECATED — توافق قرائي جولة واحدة).
   - fees_applied يبقى (إثبات شفافية — ثابت 0.0 دائماً).

2) عقد الدقة المتناهية:
   - math_audit.formula صارت: pnl == (exit_price - entry_price) * units * (long? +1 : -1)
     (بلا أي ذكر لـ commission/slippage).
   - التسامح المشدّد: max_abs_error ≤ 1e-9 (كان 0.01).
   - precision_report = {formula_tolerance: 1e-9, float64: true, rounded_fields: []}.
   - الصيغة الموحدة الموثقة: price_delta_pct = (exit−entry)/entry×100×direction ·
     result_pct = price_delta_pct · pnl بلا خصم · total_pnl_percent = Σpnl/capital×100.

3) الثغرتان:
   - /indicators/compute يقبل الآن الصيغة النصية ["zigzag_fib"] → 13 عمود ind_zzf_*،
     وأي عنصر غير صالح → 422 برسالة عربية (لا تجاهل صامت نهائياً).
   - /overlays/compute يرفع المستويات الفعلية إلى summary:
     zzfib_levels + zzfib_out_of_range (+ fib_levels/fib_out_of_range للتناظر).

4) الترقيم المرجعي محفوظ حرفياً: البطل 10 صفقات · −1.8561111466784315% — مطابق.

───────────────────────────────────────────────────────────────
MD5 (مطابق ROUND13-MD5SUMS.txt):
───────────────────────────────────────────────────────────────
616e4ffa649f76661d3d0dec9d0d5ac4  app/backtest/schemas.py
543d3e0ae93f6011bd2f9d4d81569086  app/backtest/engine1.py
dfd462c24fb62a1224bbcbddb714b510  app/backtest/metrics.py
711c8693c8a491019c2b6aa24fd41ce1  app/services/strategy/schemas.py
9988d8b1ef00613e46bbc3d2a6c1c47a  app/services/strategy/full_strategy.py
c89b0cba779c2d1c08d2be3f150a4934  app/services/strategy/presets.py
9c0e1133c9aca4c292ef2c98c0219857  app/services/strategy/strategys/rsi_strategy.py
7707bdead76a5821c1a94d0a4f23d381  app/services/strategy/strategys/mean_reversion_strategy.py
e6cabb3406b6dc91ed0f69a083480865  app/services/strategy/strategys/macd_strategy.py
a8b692c69eb040bfae4c7e86499a9813  app/services/strategy/strategys/test_strategy.py
02d4dea45dc0231522f9dadb6e533014  app/services/strategy/strategys/trend_strategy.py
2d8ec193f452c2ad25c5e751fbb1d33c  app/routers/indicators.py
e45759b96ca696a777e7d617e5fab951  app/routers/overlays.py
5141662e29c686c3488a2a9da9107aac  VERIFY-R13.sh

ملفات محذوفة (ميتة):
  app/backtest/engine.py        (كان يحمل كود عمولة — غير مستورد)
  app/backtest/engine_copy.py   (نسخة ميتة — غير مستوردة)

التراجع الآمن (PASS-6): استعادة ملفات 12.9 + إعادة تشغيل → كل اختبارات 12.1 تعود PASS.
