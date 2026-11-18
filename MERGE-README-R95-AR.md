# حزمة الدمج — ZONE-EXIT-TF1 + ZONE-EXIT-ARM1 (الملفات المعدلة والجديدة فقط)

## طريقة الدمج (على جهازك)

1. خذ نسخة احتياطية من مشروعك الحالي (أو اعتمد على git).
2. فك ضغط هذه الحزمة **فوق جذر المشروع مباشرة** (المسارات داخلها نسبية لجذر
   المشروع — ستستبدل الملفات المعدلة وتضيف الجديدة):
   ```
   unzip backend_PRO95_MERGE-ZONE-EXIT-TF1+ARM1.zip -d /مسار/جذر/مشروعك/
   ```
3. تحقق من سلامة الملفات:
   ```
   md5sum -c FILES-R95-ZONE-EXIT-TF1+ARM1.md5
   ```
4. تحقق التشغيل (اختياري لكنه موصى به):
   ```
   python3 tests-r95/test_zone_exit_unit.py       # ← 39/39 (ميزة فريم الخروج)
   python3 tests-r95/test_zone_exit_arm_unit.py   # ← 105/105 (بوابة الربح)
   python3 tests-r95/champion_ab_harness.py .     # ← بصمة 090525a362e642e9 (توافق بت-بت)
   ```

## ماذا تحوي الإضافتان

### ZONE-EXIT-TF1 (فريم هيكل الخروج)
- `zone_exit_resolution` / `zone_exit_length` داخل `params` المؤشر
  `zigzag_fib_e2e_trendy_quantum_ema`: حساب خروج المنطقة (LL+LH) على أي فريم.
- الدخول والمنطقة المسموحة (HH+HL) لم يُمَسا — فريم الشارت كما هو.
- التوثيق الكامل: `ZONE-EXIT-TF1-FRONTEND-AR.md`

### ZONE-EXIT-ARM1 (بوابة تفعيل الخروج بعد ربح X%)
- `arm_after_gain_pct` على قاعدة الخروج داخل `strategy_config.exit_rules[]`:
  قاعدة خروج المنطقة لا تُطلق خروجاً حتى يصعد السعر X% على الأقل فوق سعر
  الشراء (المركز الأساسي للموجة). غياب الحقل/0/«off» = السلوك التاريخي بت-بت.
- التوثيق الكامل: `ZONE-EXIT-ARM1-FRONTEND-AR.md`

## الملفات المعدلة (7)
| الملف | الإضافة |
|---|---|
| app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema.py | TF1 |
| app/services/indicators/overlays_zlf_e2e_trendy_quantum.py | TF1 |
| app/services/indicators/overlays.py | TF1 |
| app/services/indicators/overlay_columns.py | TF1 |
| app/services/strategy/schemas.py | ARM1 |
| app/services/strategy/strategy_engine1.py | ARM1 |
| app/backtest/engine1.py | ARM1 |

## ملف جديد في الكود (1)
- app/services/indicators/overlays_zone_exit_mtf.py (TF1 — وحدة الإسقاط السببي)

## اختبارات وأدلة (tests-r95/) + تقارير + سكربت جلب البيانات
- بطاريات: 39 (TF1) + 105 (ARM1) + 16 (مسار المعامل) — كلها خضراء.
- نتائج المصفوفة كاملة في tests-r95/results/ (الأساس + الفريمات + البوابة).
- data/history/SOLUSDT_15m.parquet: نسخة البيانات المرجعية (219,690 شمعة
  2020→2026) لضمان إعادة إنتاج نفس الأرقام — يمكن إعادة توليدها بـ
  scripts/fetch_solusdt_15m.py إن أردت.

## نتائج مرجعية (تكوين البطل EMA-60 · التاريخ الكامل)
- الأساس (بدون الخيارين): +9402.45% · 80 صفقة · PF 2.075 · Sharpe 3.28 · DD 44.98%
- بوابة 2.5% فقط:      +13710.16% · 75 صفقة · PF 2.588 · Sharpe 3.60 · DD 43.76%
- خروج 60m/50 فقط:     +8263% · 88 صفقة · PF 2.13 · Sharpe 4.81 · DD 44.99%
- الاثنان معاً:         +10022% · 83 صفقة · PF 2.54 · Sharpe 5.19 · DD 43.61%

⚠️ لا توجد أي تغييرات على: استراتيجية البطل، البريسِتات، الحمولات، قواعد
الدخول، المنطقة المسموحة، أو شكل استجابات الـ API. عدم إرسال الحقول الجديدة
= نظامك كما هو بالضبط (مُثبت بت-بت).
