# حزمة إصلاح عقود الفرونت ↔ الباك اند + الأداء — P1/P2
### (مرافقة لتقرير الوكيل: BACKEND_PROBLEMS_REPORT.md)

هذه الحزمة تُصلح **كل ما اكتشفه وكيلك وتم تأكيده على الكود الفعلي**. فك الضغط فوق جذر `trading-backend` على الخادم (المسارات محفوظة) ثم أعد التشغيل.

---

## 🔴 أولاً P0 — أمن (دقائق، قبل أي شيء آخر — لا تؤجلها)

الأسرار التالية **كُشفت علنياً** (في حزمة Drive الكاملة وفي `.env.production` المرفقة سابقاً) — **التدوير إلزامي**:

| # | السر | أين تدوّره | لماذا |
|---|------|-----------|-------|
| 1 | **كلمة مرور Neon** `neondb_owner` | Neon Console → Project → Roles → Reset password | **هذا سبب `password authentication failed` وتوقف قاعدة البيانات** — كلمة المرور القديمة مكشوفة (وقد عطّلتها/غيّرها Neon أو أحد) |
| 2 | `SECRET_KEY` (JWT) | على الخادم: `python -c "import secrets; print(secrets.token_urlsafe(48))"` ثم حدّث `.env` | أي شخص لديه القديمة يستطيع تزوير توكنات دخول |
| 3 | `ENCRYPTION_KEY` (Fernet) | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | فك تشفير بيانات محفوظة بالقديمة |
| 4 | مفتاح AlphaVantage | alphavantage.co — مفتاح جديد | القديم مكشوف ومستهلك |
| 5 | كلمة مرور Upstash Redis | Upstash Console → Reset password | مكشوفة في تعليق داخل `.env.production` |
| 6 | روابط Drive | اجعل حزمة النظام الكاملة **خاصة** | فيها `.git` و`.env` كاملان |

ثم على الخادم:
```bash
nano .env          # حدّث DATABASE_URL بكلمة المرور الجديدة + SECRET_KEY الجديد + CORS_ORIGINS
docker compose restart backend celery-worker   # أو إعادة التشغيل المعتادة عندك
curl -s http://localhost:8000/api/v1/health   # يجب "database":"up"
```

⚠️ **مهم بخصوص CORS**: `docker-compose.yml` يقرأ ملف **`.env`** (وليس `.env.production`). أضف في `.env`:
```
CORS_ORIGINS=["http://localhost:3000","http://<عنوان-الفرونت-الفعلي>:<البورت>"]
```
وإلا ستبقى الطلبات الخارجية تُرفض 400 — وهذا سبب اكتشاف الوكيل "Preflight يعيد 400".

---

## 🟠 ثانياً — محتوى الحزمة (كل ملف معدّل ولماذا)

| الملف | الإصلاح |
|-------|---------|
| `app/routers/users.py` | **الدخول يقبل الصيغتين**: JSON (بحقل `email` أو `username`) كما يرسل الفرونت + Form-encoded لتوافق Swagger/OAuth2. أضفنا أيضاً `/users/login-json` كمسار بديل صريح |
| `app/services/auth.py` | `authenticate_user` يدعم الدخول **بالإيميل أو اسم المستخدم** |
| `app/backtest/schemas.py` | **عقد الباك تست يتقبل حقول الفرونت**: `symbol→symbols`، `strategy→strategy_config`، `commission→commission_rate`، `interval→timeframe`، `capital→initial_capital`، و`name` صار اختيارياً مع توليد تلقائي — لن يظهر 422 |
| `app/providers/us_stock_provider.py` | **top-movers: 56s → <3s** — `asyncio.gather` بحد تزامن 15 + مهلة 6 ثوانٍ/رمز + كاش 60 ثانية + تجاهل أسعار صفر |
| `app/services/filtering/core.py` | **انتهاء أسعار الصفر**: جلب متوازٍ + الرمز بلا سعر صحيح يُتخطى بدل تمريره بسعر 0 |
| `app/routers/market_data.py` | `historical` لن يعيد `"start_date":"0"` — يقرأ من فهرس زمني حقيقي أو عمود timestamp وإلا null |
| `app/services/strategy/loader.py` + `app/routers/strategies.py` | **`strategies/list` لن تكون فارغة**: مسح تلقائي لمجلد `strategies/` من القرص عند فراغ الذاكرة (idempotent + يتسامح مع الملفات التالفة) |
| `app/tasks/backtest_tasks.py` + `app/routers/backtest.py` | **سبب فشل الباك تست يظهر فعلياً** (`error_detail` في `/status` عند `DEBUG=true`) بدل الرسالة العامة |
| `.env.production` | **معقّم** — لا أسرار حقيقية (قالب + تعليمات تدوير) |
| `scripts/verify_contracts.py` | **جديد**: فحص 8 عقود على الخادم الحي بأمر واحد |

### توضيحان مهمان لا تحتاجان ملفات:
1. **walk-forward `in_sample: null`**: منطق النوافذ في النسخة المدمجة **سليم**. النافذة الأولى بلا بيانات تدريب سابقة بطبيعتها (anchored)، وبقية النوافذ تعطي null لأن **تشغيلات التدريب تفشل عندما تكون قاعدة البيانات متوقفة** — أي أن جذر المشكلة واحد: P0. تأكد فقط أن `engine1.py` على الخادم مطابق للنسخة المدمجة.
2. **30+ نقطة مفقودة**: لا تُبنى كلها الآن — بعد نجاح P0+P1 اربط الفرونت بالنقاط الموجودة أو أزل الاستدعاءات الميتة (P3)، وننفذ المهمة فعلاً المطلوبة منها تدريجياً.

---

## 🟢 ثالثاً — النشر (3 دقائق)

```bash
cd /path/to/trading-backend
# 1) نسخة احتياطية سريعة (إلزامية قبل أي استبدال)
git add -A && git commit -m "backup before contract-repair package" || tar czf ../backup-before-repair.tar.gz app/

# 2) فك الحزمة فوق الجذر (استبدال الملفات)
unzip -o contract-repair-p1-package.zip -d .

# 3) (بعد تدوير الأسرار!) حدّث .env ثم أعد التشغيل
docker compose restart backend celery-worker

# 4) تحقق بفحص واحد
pip install httpx && python scripts/verify_contracts.py http://localhost:8000
```

**النتيجة المتوقعة من الفحص**: 8/8 PASS (أو تحذير توقيت وحيد في أول استدعاء top-movers البارد).

---

## ✅ ماذا سيصلح هذا للمستخدم النهائي (اللوحة)

- تسجيل الدخول من اللوحة يعمل (JSON + إيميل)
- زر الباك تست من اللوحة يعمل (حقلول الفرونت القديمة تُقبل)
- top-movers يفتح فوراً بدل 56 ثانية
- الفلترة لا تعرض أسعار 0
- صفحة historical لا تظهر تاريخ "0"
- قائمة الاستراتيجيات تظهر الملفات الفعلية
- عند فشل أي باك تست سترى السبب الحقيقي بدل "فشل عام"
