# 📦 حزمة ترقيع الباك اند — الجولة 5 (Round 5)

> **التاريخ**: 2026-10-29 · **الحالة**: مُختبرة حياً محلياً بنفس سيناريو الإنتاج الحرفي
> **الهدف**: إصلاح عطل `IndicatorConfig 'oscillator'` + إنهاء موت اتصالات WS عند الإقلاع (1006) + حفظ بيانات المستخدم عبر إعادة البناء

---

## 🔴 ماذا تعالج هذه الحزمة؟

| # | العطل | الجذر | الإصلاح |
|---|---|---|---|
| 1 | `1 validation error for IndicatorConfig type … input_value='oscillator'` يتكرر كل ثانيتين في لوق الإنتاج | مؤشر محفوظ بنوع `oscillator` (من تصنيف واجهة الفرونت) يُرفض في pydantic | تطبيع الأنواع في **5 طبقات** + **شفاء ذاتي للقاعدة** يعيد كتابتها نظيفة |
| 2 | اتصالات WS تموت `1006` بلا close frame بعد الإقلاع مباشرة | نفس الجذر: init يحمّل المحفوظ المسموم → ValidationError → الاتصال يُقتل قبل `chart_initialized` | الحماية تُسقط التكوين الفاسد **وحده** ولا تقتل الاتصال أبداً |
| 3 | `values/{id}` يرجع `index` فارغاً ويتجاهل `from_ms` بصمت | نتائج الذاكرة قوائم مجردة بلا طوابع زمنية | إعادة حساب + بناء index من أزمنة الشموع (محاذاة من النهاية) |
| 4 | تكوين محفوظ بمعاملات خارجة عن الحدود (مثل `rsi period=3`) يقتل init كاملاً | pydantic يفحص الاشتراك دفعة واحدة | درع: إسقاط التكوين الفاسد فردياً + إغلاق نظيف 1008 في أسوأ الحالات |
| 5 | رؤوس اللوحات تعرض `66B862BF` بدل `RSI` | حقل `name` في النتائج = مفتاح المعرف | `name` نظيف (`rsi`) في init و indicator_added و candle_close و price_update |
| 6 | المؤشرات المحفوظة والرسومات **تُمسح** عند كل `up --build` | `chart_states.db` و `chart_drawings.db` داخل طبقة الحاوية بلا volumes | ربط الملفين من المضيف في docker-compose.yml |

---

## 📁 محتويات الحزمة (6 ملفات — نفس مسارات المشروع)

```
patch_round5/
├── docker-compose.yml                      # + volumes لقاعدتي المستخدم
└── app/
    ├── core/managers.py                    # تطبيع الحقن + الأسماء النظيفة في كل البث
    ├── routers/indicators.py               # إصلاح values/{id}: index + from_ms + limit
    ├── services/indicators/base.py         # coerce_indicator_type + sanitize_indicator_config
    ├── services/indicators/calculator.py   # تطبيع قبل pydantic (خط الدفاع الأخير)
    └── websocket/chart_ws.py               # تطبيع init + شفاء ذاتي للقاعدة + درع الاشتراك
```

---

## 🚀 خطوات النشر على السيرفر (161.97.73.254) — بالترتيب حرفياً

```bash
# 0) انسخ مجلد patch_round5 إلى مجلد المشروع على السيرفر ثم:
cd /path/to/backend_pro          # مجلد المشروع على السيرفر

# 1) نسخة احتياطية سريعة
cp -r app app.bak.$(date +%s)
cp docker-compose.yml docker-compose.yml.bak

# 2) ⚠️ إلزامي: استخرج قاعدتي المستخدم من الحاوية الحالية قبل أي إعادة بناء
#    (وإلا خسرت المؤشرات المحفوظة والرسومات — نفس سبب بلاغ "اختفاء المؤشرات")
docker cp trading-backend:/app/chart_states.db   ./chart_states.db
docker cp trading-backend:/app/chart_drawings.db ./chart_drawings.db

# 3) طبّق الملفات (فوق الموجود)
cp -r patch_round5/app/*   app/
cp    patch_round5/docker-compose.yml docker-compose.yml

# 4) أعد البناء والتشغيل
docker compose up -d --build backend

# 5) تأكد من الإقلاع
docker logs -f trading-backend        # ابحث عن "Database initialized" وبلا أخطاء
curl -s http://localhost:8000/api/v1/health
```

---

## ✅ التحقق بعد النشر (دقيقتان)

**أ) التطبيع والشفاء الذاتي — افتح صفحة الشارت في الواجهة ثم:**
```bash
docker logs trading-backend 2>&1 | grep -E "Sanitized|dropping invalid"
# المتوقع عند أول فتح شارت بعد النشر:
# 🧬 Sanitized 1 saved indicator config(s) with invalid type — self-healing DB
```
> هذا السطر يعني أن المؤشر المحفوظ `rsi_66b862bf` (المسموم `type='oscillator'`) **شُفي** —
> ومن هذه اللحظة **تختفي أخطاء `validation error for IndicatorConfig` نهائياً من اللوق**.

**ب) اتصال WS حي — يجب أن يصل `chart_initialized` فوراً (لا 1006):**
```bash
curl -s "http://localhost:8000/api/v1/indicators/values/rsi_66b862bf?symbol=BTCUSDT&timeframe=1m&market=crypto&limit=50"
# المتوقع: {"count":50,"values":{"data":[...50 قيمة...],"index":[...50 طابع زمني...]},"range":{...}}
#                                ↑↑↑ القيم والطوابع متساوية العدد — كانت index=0 قبل الإصلاح
```

**ج) مجموعة التحقق الكاملة (27 بنداً):** أعد تشغيل `verify_round4.py` — المتوقع 27/27 (كانت 24 + 3 فاشلات زائفة بيئية).

---

## 🛡️ طبقات الحماية الخمس ضد الأنواع الفاسدة (ما يمنع تكرار العطل للأبد)

1. **WS init** — تطبيع كل مؤشر وارد من العميل قبل أي فحص pydantic
2. **قراءة القاعدة** — تطبيع + **كتابة النسخة النظيفة** (الشفاء الذاتي — يحدث مرة واحدة ثم القاعدة نظيفة للأبد)
3. **حقن المؤشر** (add_indicator) — تطبيع قبل الحساب **وقبل الحفظ** فلا يُحفظ مسموم أبداً مستقبلاً
4. **الحاسبة** — تطبيع قبل `IndicatorConfig` (خط الدفاع الأخير لو تسرب شيء)
5. **درع الاشتراك** — أي تكوين فاسد يُسقط وحده بسجل واضح، والاتصال يعيش دائماً

> المزامنة المستقبلية: حتى لو أرسلت واجهة جديدة نوعاً غير معروف، تُطبَّع تلقائياً
> (`oscillator→momentum`, `overlay→trend`, …) مع الرجوع للسجل الرسمي لكل مؤشر.
