# QMOM1 — حزمة دمج «كموميه الزخم الاولى» + بوابة الشروط المرنة
## BACKEND-QUANTUM-MOMENTUM1-DELIVERY — دليل الدمج الخطوة بخطوة
**التاريخ:** 2026-11-18 · **الأساس:** نسخة ZONEXIT-LTF1 المنشورة (نفس شجرة app كما رُصدت 2026-11-18) · **المُرسل:** السديم
**صاحب القرار:** المهندس محمد — الطلب الحرفي: «سنقوم باضافه بوابه جديده للشروط وتكون مرنه وقابله للتعديل والاضافه ع اي استراتيجيه واكون قادر ع التعديل عليه وتفعيله وتغييره او تغيير اعداداتها … اهم شيء العقود المرنه» + «ونسوي من ZLF-End-To-End-Trendy-Quantum-EMA نسخه باسم: كموميه الزخم الاولى».

---

## 1) ما الذي في الحزمة (بالمسارات)

```
merge_package/
├── app/services/indicators/
│   ├── overlays_zlf_e2e_trendy_quantum_ema_mom.py   ← ملف جديد كلياً (المحرك)
│   ├── overlays.py                                  ← 4 إضافات تسجيل فقط (لا سطر قائم تغيّر)
│   ├── overlay_columns.py                           ← 6 إضافات فقط (مرادفات + تطبيع + أعمدة + أنبوب)
│   ├── __init__.py                                 ← سطر استيراد واحد
│   └── mtf_oscillator_core.py                       ← 3 إضافات صغيرة (دعم enabled:false)
├── strategies/qmom1_كموميه_الزخم_الاولى.json        ← الاستراتيجية كاملة (الشروط الأربعة)
├── payloads/payload_qmom1_sol_full_history.json     ← حمولة البث الحي (SOLUSDT · 15m · كامل التاريخ)
├── diffs/                                           ← فروقات موحدة ضد الأساس (300 سطر — كلها +
├── tools/verify_qmom1.py + verify_result.txt         ← بطارية التحقق (32/32 PASS محلياً)
├── INSTALL-QMOM1-AR.md                              ← هذا الملف
├── FRONTEND-AGENT-BRIEF-QMOM1-AR.md                 ← تقرير الواجهة (عقد الشروط المرنة للفرونت)
└── FILES-QMOM1.md5                                  ← بصمات كل ملف
```

**القرار الهندسي (لماذا تعديل باك-اند هذه المرة — ولماذا هو آمن):**
شرط الدخول الجديد يحتاج MACD/RSI محسوبة على فريمات 4h/3d/1d/1h — ليست مخرجات
أصلية لعائلة الكمومية-EMA، فلا يمكن التعبير عنها JSON خالص فوق النسخة الحالية
(عكس مهمة كسر الترندات السابقة التي كانت عموداً أصلياً). لذلك بُنيت طبقة بوابة
الشروط فوق نواة الموشرات متعددة الفريمات المثبتة في الإنتاج (PRO76-mtf-osc-core
v2.0.0 — نفس نواة عائلة trendy_macd) بمحرك معزول جديد كلياً + تسجيل إضافي فقط:

| الملف | نوع التغيير | الحجم |
|---|---|---|
| `overlays_zlf_e2e_trendy_quantum_ema_mom.py` | **جديد كلياً** | محرك كموميه الزخم (عقد zzfetqem_*) |
| `overlays.py` | +4 كتل | OVERLAY_TYPES + معاملات + حماية كل-الأنواع + موزّع |
| `overlay_columns.py` | +6 كتل | مرادفات + قواعد + عقد أعمدة + فرع تطبيع + دالة أعمدة + أنبوب |
| `__init__.py` | +1 سطر | استيراد التسجيل الذاتي |
| `mtf_oscillator_core.py` | +3 كتل صغيرة | `enabled:false` = ورقة/فرع محايد (تفعيل/تعطيل حي) |

**لا يوجد أي تغيير على أي سطر قائم** — الفروقات في `diffs/` كلها إضافات `+`
(صفر `-` منطقية). أي استراتيجية قائمة لا تذكر `zigzag_fib_e2e_trendy_quantum_ema_mom`
تبقى بت-بت كما هي (المحرك الجديد لا يُطلب أصلاً في مسارها).

---

## 2) خطوات الدمج (على سيرفر الباك-اند)

```bash
# 1) انسخ ملفات الحزمة إلى جذر مشروع الباك-اند (المسارات كما هي):
cp merge_package/app/services/indicators/overlays_zlf_e2e_trendy_quantum_ema_mom.py  <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/overlays.py                                  <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/overlay_columns.py                          <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/__init__.py                                  <PROJECT>/app/services/indicators/
cp merge_package/app/services/indicators/mtf_oscillator_core.py                      <PROJECT>/app/services/indicators/
# 2) (اختياري) الاستراتيجية كقالب جاهز:
cp merge_package/strategies/qmom1_كموميه_الزخم_الاولى.json   <PROJECT>/strategies/
# 3) أعد تشغيل الخدمة (uvicorn/celery كما معتاد) — لا هجرات قواعد بيانات إطلاقاً.
```

**إن كنت تفضل الدمج اليدوي بدل النسخ الكامل:** طبّق `diffs/*.diff` بالاتجاه نفسه
(كل الفروقات إضافات فقط) — أو انسخ الملفات الجديدة وطبّق الكتل الست/الأربع
المؤشرة بتعليقات `# QMOM1` في نهايات `diffs/`.

## 3) التحقق بعد الدمج (الدليل قبل الكلام)

**أ) محلياً (بلا سيرفر):**
```bash
# عدّل RUNTIME/DATA في tools/verify_qmom1.py لبيئتك ثم:
python3 tools/verify_qmom1.py     # متوقع: PASS 32 / FAIL 0
```
بطاريتنا على نسخة runtime المحلية: **32/32 PASS** — أبرزها:
- بوابة الشروط الأربعة = الشجرة بت-بت (mismatch=0 على 33,441 شريط بعد أفق الإحماء)
- **السببية بت-بت**: MACD 4h/3d/1d + RSI 1h/4h/1d كلها = قيمة **آخر شريط أعلى مكتمل**
  فقط (بلا أي استشراف) — مطابقة معمارية مستقلة بالكامل
- `enabled:false` على شرط ⇒ بوابة الشجرة بدونه بت-بت (ويعطّل حساب نسخه أصلاً)
- وضع الهوية (بلا قالب) = مرآة الكمومية-EMA **بت-بت**
- الأنبوب الكامل: `columns_for_configs → ind_zzfetqem_* → مقيّم شروط المحرك` —
  بما فيها الشروط المباشرة على سلاسل الموشرات (مسار المرونة الثاني)

**ب) حياً (البوابة الحقيقية):**
```bash
python3 - << 'EOF'
import json, urllib.request
payload = json.load(open("merge_package/payloads/payload_qmom1_sol_full_history.json", encoding="utf-8"))
payload = {k: v for k, v in payload.items() if v is not None}
req = urllib.request.Request("http://161.97.73.254:8000/api/v1/backtest1/run",
    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
print(urllib.request.urlopen(req, timeout=60).read().decode()[:400])
EOF
```
- الاسم الحي: **«كموميه الزخم الاولى»** · SOLUSDT · 15m · 2020-03-16 → 2026-11-17 · $300 · max_positions=3
- تابعها بـ `GET /status/{task_number}` ثم `GET /get/{backtest_id}`
- **توقع النتيجة بصدق:** البوابة ستُقصّ دخولات البطل (36 خام ⇒ 6 نهائية على نافذة
  الاختبار المحلية MMT) — هذا هدفها: قتل الدخول الخاطئ/المتأخر. الرقم النهائي على
  SOL كامل التاريخ سيخرج من التشغيل نفسه — لا وعد برقم قبل الدليل.

## 4) العزو النظيف (بُعد واحد لكل تجربة)

- ضد البطل #10000499 (A226-FZ الكامل الحراس +10,219%): حمولة `كموميه الزخم
  الاولى` = نفس كل شيء + بوابة الزخم فقط — أي فرق يعزى للبوابة وحدها.
- لتعطيل بوابة كاملة: احذف `osc_conditions` (و`osc_instances`) من باراميترات
  المؤشر ⇒ وضع الهوية (مرآة البطل بت-بت).
- لتعطيل شرط واحد: `"enabled": false` على عقده في الشجرة (محايد — كأنه غير موجود).

## 5) الاسترجاع (Rollback — لا شيء ينكسر)

- احذف `overlays_zlf_e2e_trendy_quantum_ema_mom.py` وأزل كتل `QMOM1` الأربع/الست
  المعلّمة في الملفات الأربعة (أو استرجع نسخ ما قبل الدمج) — لا شيء آخر يعتمد
  عليها: التسجيل إضافي والمحرك معزول ببادئة أعمدة خاصة `zzfetqem_*`.

## 6) روابط العقود

- **عقد الواجهة الكامل** (ما يبنى عليه الفرونت): `FRONTEND-AGENT-BRIEF-QMOM1-AR.md`
- بصمات الملفات: `FILES-QMOM1.md5`
- الاستراتيجية القابلة للقراءة بشروطها الأربعة: `strategies/qmom1_كموميه_الزخم_الاولى.json`
