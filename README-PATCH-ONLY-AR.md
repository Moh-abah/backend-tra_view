# 🎯 حزمة «الملفات المعدّلة فقط» — الجولة R55

## ما هذه الحزمة (باختصار)
هذه الحزمة هي **تعديلات الجولة R55 فقط — 7 ملفات كود + 3 مستندات توثيق**،
بلا بقية المشروع. مخصصة لمن عنده مشروع كامل ويريد تركيب التعديلات فوقه
مباشرة بدل تحميل المشروع كاملًا من جديد.

> إذا أردت المشروع كاملًا (531 ملفك + هذه التعديلات مدمجة): حمّل
> `backend_R55_FIXED.zip` — محتوى الملفات السبعة فيه **مطابق بت-بت**
> لهذه الحزمة.

## محتوى الحزمة (10 ملفات)
```
app/backtest/schemas.py          ← الكونفيق النظيف: غير المُرسل = null + سقف تريلينق 50
app/backtest/engine1.py          ← تريلينق من الجذر + مراكز متعددة + SL حرفي (0/100/عدم إرسال = تعطيل)
app/services/exit_engine.py      ← سقف رقمي max_concurrent_positions (1..10) بدل allow_overlap
app/services/unified_backtest.py ← _build_chart_data: أعمدة ind_* + سقف 20,000 شمعة + منحنى لكل صفقة
app/routers/exit_strategy.py     ← محوّل الشموع + تطبيع بوابة السقف
app/routers/backtest1.py         ← نافذة الجذر الحرفية عبر _fetch_unified_candles + تمرير max_positions
app/tasks/backtest_tasks.py      ← نفس التعديلين لنسخة Celery + صدى risk_echo/effective_config
BACKEND-REPORT-R55-AR.md         ← التقرير الكامل: التشخيص والإصلاحات والاختبارات بالأرقام
INSTALL-R55-AR.md                ← دليل التثبيت والتحقق (4 خطوات بعد التثبيت)
FILES-R55.md5                    ← بيان بصمات «قبل/بعد» للملفات السبعة
```

## التركيب فوق مشروعك (نسختان — اختر واحدة)

### أ) فك الضغط فوق المشروع مباشرة
```bash
# من داخل مجلد مشروعك (حيث يوجد مجلد app/)
unzip -o backend_R55_PATCH_ONLY.zip -d /مسار/مشروعك
```
خيار `-o` يستبدل الملفات السبعة القديمة بالمعدّلة — ولا يلمس أي ملف آخر.

### ب) النسخ اليدوي ملفًا ملفًا
انسخ كل ملف من `app/...` إلى المسار نفسه في مشروعك (القائمة أعلاه).

## التحقق من سلامة الملفات بعد الفك (دقيقة واحدة)
```bash
cd /مسار/مشروعك
md5sum app/backtest/schemas.py app/backtest/engine1.py \
      app/services/exit_engine.py app/services/unified_backtest.py \
      app/routers/exit_strategy.py app/routers/backtest1.py \
      app/tasks/backtest_tasks.py
```
قارن مع عمود «MD5 بعد (معدّل)» في `FILES-R55.md5` — يجب التطابق بت-بت:

| الملف | MD5 (المعدّل) |
|---|---|
| app/backtest/schemas.py | f176de5eb3558e1d82e3cccdb54b1d85 |
| app/backtest/engine1.py | c06071b712ffd0ed29d31930883f2fb5 |
| app/services/exit_engine.py | f7c80dedcaf5752648cf5e68f177d9ad |
| app/services/unified_backtest.py | 875970a0594542528b41eb2f3b52dde8 |
| app/routers/exit_strategy.py | fa8205894af97bd1420b8c80d5d22d36 |
| app/routers/backtest1.py | b4801337183a95c0d66580ee91aa8d26 |
| app/tasks/backtest_tasks.py | fc86a32d3c3c79a6540c2878ec8bb4e9 |

## بعد التركيب
1. أعد بناء/تشغيل الخدمة: `docker compose up -d --build` أو أعد تشغيل
   uvicorn + celery worker.
2. **لا توجد هجرات قاعدة بيانات** — الجداول كما هي.
3. اتبع خطوات التحقق الأربع في `INSTALL-R55-AR.md` (المرجع → نافذة الجذر
   → ماكس اوبن → SL التعطيل).
