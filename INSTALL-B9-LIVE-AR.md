# دليل تثبيت B9 v4.2 (LIVE1) — على آخر إصدار من نظامك (متوافق مع تعديلات EBREAK1)

> **قاعدة الحزمة**: آخر إصدار من نظامك بما فيه تعديلات EBREAK1 + إضافة `htf_mode` فقط.
> **مهم**: هذه v4.2 — لا تثبت v4.1 القديمة (ستلغي تعديلات EBREAK1).
> **الوقت المطلوب**: ~5 دقائق. **قابلية التراجع**: كاملة (نسخة احتياطية).

---

## 1) نسخة احتياطية (30 ثانية — لا تتجاوزها)

من جذر مشروع السيرفر:

```bash
cp app/services/indicators/overlays_b9_macd_gates.py  ~/backup_b9_v41/overlays_b9_macd_gates.py.orig
cp app/services/indicators/overlays.py                ~/backup_b9_v41/overlays.py.orig
cp app/services/indicators/overlay_columns.py        ~/backup_b9_v41/overlay_columns.py.orig
cp tools/verify_b9.py                                 ~/backup_b9_v41/verify_b9.py.orig
mkdir -p ~/backup_b9_v41 2>/dev/null   # إن لم تكن موجودة، أنشئها أولاً ثم أعد النسخ
```

(أنشئ المجلد أولاً: `mkdir -p ~/backup_b9_v41` ثم انسخ الملفات الأربعة إليه.)

## 2) نسخ ملفات الحزمة (3 ملفات كود + أداة + 6 حمولات)

فك ضغط `B9-LIVE1-v4.2.zip` ثم من داخل مجلدها:

```bash
# الكود الثلاثة (نسخك الحالية بتعديلاتك + htf_mode فقط — EBREAK1 محفوظ)
cp app/services/indicators/overlays_b9_macd_gates.py  /مسار/مشروعك/app/services/indicators/
cp app/services/indicators/overlays.py                /مسار/مشروعك/app/services/indicators/
cp app/services/indicators/overlay_columns.py        /مسار/مشروعك/app/services/indicators/

# أداة التحقق المدموجة (كل فحوصك السابقة + التغطية + live)
cp tools/verify_b9.py                                 /مسار/مشروعك/tools/

# الحمولات الست — ملفات جديدة لا تستبدل شيئاً
cp payloads/payload_B9_T100_LIVE_ETHUSDT.json    /مسار/مشروعك/payloads/
cp payloads/payload_B9_T100_LIVE_XRPUSDT.json    /مسار/مشروعك/payloads/
cp payloads/payload_B9_T100_LIVE_MBLUSDT.json    /مسار/مشروعك/payloads/
cp payloads/payload_B9_T100_LIVE_W_ETHUSDT.json  /مسار/مشروعك/payloads/
cp payloads/payload_B9_T100_LIVE_W_XRPUSDT.json  /مسار/مشروعك/payloads/
cp payloads/payload_B9_T100_LIVE_W_MBLUSDT.json  /مسار/مشروعك/payloads/
```

## 3) إعادة التشغيل

```bash
# حسب طريقة تشغيلك — المعتادة:
sudo systemctl restart uvicorn   # أو خدمة الـ API عندك
sudo systemctl restart celery    # إن كانت الباك-تستات تمر عبر celery
# أو يدوياً: أوقف uvicorn/celery وشغّلهما من جديد
```

## 4) التحقق الفوري (أقل من دقيقة)

```bash
cd /مسار/مشروعك
python3 tools/verify_b9.py ETHUSDT
# المتوقع: «✅ VERIFY-B9 PASS» — 13 ناجح · 0 فاشل
#   (فحص التغطية [6] يتخطى بأمان إن كان كاش البيانات أقل من سنتين — هذا طبيعي)

# الفحص الكامل (اختياري — يتطلب كاش بيانات سنتين+):
python3 tools/verify_b9.py ETHUSDT 1400
# المتوقع: «✅ VERIFY-B9 PASS» — 14 ناجح · 0 فاشل
```

## 5) تشغيل الحمولات

من واجهة المنصة أو عبر API — مثل أي باك-تست عادي:

| الهدف | الحمولة |
|---|---|
| رؤية كل الإشارات عبر التاريخ (مناطق ما قبل الصعود) | `payload_B9_T100_LIVE_ETHUSDT.json` (وXRP/MBL) |
| نفس إعدادك الحالي (نافذة التقييم) لكن برؤية TV الحية | `payload_B9_T100_LIVE_W_ETHUSDT.json` (وXRP/MBL) |
| سلوكك السابق تماماً (للمقارنة) | حمولاتك الثلاث الحالية — لم تُمس وستعطي نفس نتائجها السابقة بت-بت |

**كيف تعرف أن live يعمل؟** افتح نتيجة الباك-تست وابحث في meta المؤشر عن
`"htf_mode": "live"` — أو لاحظ عدد حلقات الإشارات (أضعاف النسخة المؤكدة).

## 6) تحويل أي حمولة أخرى إلى live (سطر واحد)

داخل الحمولة: `strategy_config → indicators[0] → params` أضف:

```json
"htf_mode": "live"
```

بجانب `active_start`/`active_end`. بدون هذا السطر = confirmed = سلوكك الحالي.

## 7) التراجع الكامل (لو احتجت يوماً)

```bash
cp ~/backup_b9_v41/overlays_b9_macd_gates.py.orig  /مسار/مشروعك/app/services/indicators/overlays_b9_macd_gates.py
cp ~/backup_b9_v41/overlays.py.orig                /مسار/مشروعك/app/services/indicators/overlays.py
cp ~/backup_b9_v41/overlay_columns.py.orig        /مسار/مشروعك/app/services/indicators/overlay_columns.py
cp ~/backup_b9_v41/verify_b9.py.orig               /مسار/مشروعك/tools/verify_b9.py
# ثم أعد تشغيل uvicorn + celery — عاد كل شيء كما كان (الحمولات الست الجديدة
# ستعمل حينها confirmed تلقائياً لأن htf_mode سيُحذف من قائمة السماح القديمة).
```

## 8) ملاحظات أمان مهمة

- **لا يوجد أي مسار يمكن أن يعمل فيه النظام بطريقة مختلفة عن سلوكك الحالي إلا بسطر
  `htf_mode: "live"` صريح منك** — الافتراضي confirmed بت-بت.
- القيمة غير المفهومة لـ `htf_mode` → تحذير + confirmed (لا انفجار).
- `presets.py` وقالب B9_TREND100 **غير مشمولين** في الحزمة — واجهة إنشاء الباك-تست
  عندك لن تتغير، والقالب يبقى confirmed.
