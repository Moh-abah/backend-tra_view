# تعليمات تثبيت R64 (زر خروج كسر الفيبو + وراثة الستوب)

## الخطوات

1. **النسخ الاحتياطي** (مستحسن):
   ```bash
   cp app/services/exit_engine.py   app/services/exit_engine.py.bak-R62
   cp app/tasks/backtest_tasks.py   app/tasks/backtest_tasks.py.bak-R62
   cp app/routers/backtest1.py      app/routers/backtest1.py.bak-R62
   cp app/routers/exit_strategy.py  app/routers/exit_strategy.py.bak-R62
   ```

2. **فك الحزمة وانسخ الملفات الأربعة**:
   ```bash
   unzip backend_R64_PATCH_ONLY.zip -d r64
   cp r64/app/services/exit_engine.py   app/services/exit_engine.py
   cp r64/app/tasks/backtest_tasks.py   app/tasks/backtest_tasks.py
   cp r64/app/routers/backtest1.py      app/routers/backtest1.py
   cp r64/app/routers/exit_strategy.py  app/routers/exit_strategy.py
   ```

3. **التحقق من البصمات** (من داخل مجلد الحزمة):
   ```bash
   cd r64 && md5sum -c FILES-R64.md5
   ```

4. **أعد التشغيل** (الاثنان معاً):
   ```bash
   systemctl restart api celery-worker
   # أو: docker compose restart api celery-worker
   ```

5. **تحقق ما بعد التثبيت** (اختياري):
   ```bash
   python3 verify_r64_post_install.py
   ```
   يفترض أن يطبع: `R64 OK — 18/18` — يثبت أن الزر والوقف النسبي والوراثة
   يعملون على سيرفرك الفعلي (يستورد `app.services.exit_engine` الحقيقي).

## لا يوجد أي شيء آخر
- ❌ لا هجرة قواعد بيانات
- ❌ لا متغيرات بيئة جديدة
- ❌ لا endpoints جديدة (الحقلان يظهران تلقائياً في /defaults و Swagger و /agent/contract.json)
- ✅ كل الحمولات القديمة تعمل **بت-بت** (2,100 تشغيلة انحدار بصفر انحراف)

## الاستخدام من الفرونت

| السيناريو | الحمولة |
|---|---|
| الزر مفعّل (الافتراضي — السلوك التاريخي) | `"exit_strategy": {"config": {}}` أو بلا `fibo_floor_exit` |
| الزر معطّل + وراثة الستوب من الجذر | `"stop_loss_percent": 2.0` بالجذر + `"exit_strategy": {"config": {"fibo_floor_exit": false}}` |
| الزر معطّل + وقف صريح (يعلو فوق الجذر) | `"exit_strategy": {"config": {"fibo_floor_exit": false, "stop_loss_pct": 3.5}}` |
| نقطة الخروج المستقلة | `POST /api/v1/exit-strategy/backtest` بـ `config: {"fibo_floor_exit": false, "stop_loss_pct": 5}` |
