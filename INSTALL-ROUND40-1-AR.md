# 🛠️ تثبيت الجولة 40.1 — محرك الخروج المحسّن + دراسة التحسين

> هذه الحزمة **تحل محل حزمة الجولة 40 كاملة** (تتضمن كل ما فيها + التحسينات).
> إن كنت ثبّت ج40 مسبقاً: نفس الخطوات — استبدل الملفات الثلاثة.
> إن كنت قادماً من ج39.1 مباشرة: أيضاً نفس الخطوات — الحزمة مكتملة ذاتياً.

## محتويات الحزمة (3 ملفات كود + 3 وثائق)

| الملف | الحالة | الوصف |
|---|---|---|
| `app/services/exit_engine.py` | **جديد/استبدال** | المحرك النقي v1.1: +4 حقول اختيارية (مرشحا دخول + جني متحرك) + واقعية تنفيذ الفجوات + presets |
| `app/routers/exit_strategy.py` | **جديد/استبدال** | الراوتر v1.1: **6 نقاط نهاية** (أضيفت `GET /presets`) |
| `app/main.py` | **معدَّل — سطران فقط** | استيراد + تسجيل الراوتر (نفس سطري ج40 — لم يتغير عنها حرفياً) |
| `EXIT-STRATEGY-CONTRACT-AR.md` | وثيقة | **عقد وكيل الفرونت-إند v1.1** — سلّمه له كاملاً |
| `OPTIMIZATION-STUDY-AR.md` | وثيقة | **دراسة التحسين الكاملة بالأرقام** (55,296 باك-تست + اختبار نظام السوق) |
| `MD5SUMS.txt` | بصمات | تحقق ذاتي بعد النسخ |

## ما الجديد في 40.1 عن 40 (سلوكياً)

1. **الحرفية محفوظة**: الافتراضات كما نُصّت الخطة — الحقول الجديدة الأربعة معطلة.
2. **`GET /presets`**: زر «الخطة الحرفية» وزر «الموصى بها» (هدف 3% من المتوسط،
   تعزيزان 5%/8%، تبريد 50) — **خسارة أقل بـ75%** في المصفوفة الحديثة مع
   مضاعفة الصفقات الرابحة (الأرقام في دراسة التحسين).
3. **واقعية التنفيذ**: فجوة صعود فوق الهدف تُباع عند الافتتاح (أفضل لك)، فجوة
   هبوط تحت زناد التعزيز تُشترى عند الافتتاح (أرخص لك).
4. سبب خروج رابع اختياري `trail_stop` عند تفعيل الجني المتحرك.

## خطوات التثبيت (على السيرفر)

```bash
cd ~/TR_platform/backend

# 1) نسخة احتياطية سريعة
cp app/main.py /tmp/main.py.backup_before_r401

# 2) فك الحزمة والتحقق من البصمات
unzip backend_ROUND40_1_exit_engine_tuned.zip -d r401
cd r401 && md5sum -c MD5SUMS.txt && cd ..

# 3) انسخ الملفات الثلاثة
cp -v r401/app/services/exit_engine.py   app/services/
cp -v r401/app/routers/exit_strategy.py  app/routers/
cp -v r401/app/main.py                   app/

# 4) إعادة البناء والإقلاع
docker compose up -d --build
```

## التحقق بعد الإقلاع

```bash
# أ) الخادم أقلع
docker logs --tail 5 trading-backend        # ← "Application startup complete."

# ب) الجولة 40.1 حاضرة
curl -s http://localhost:8000/api/v1/exit-strategy/health
#   ← {"status":"ok","round":40.1,"engine":{"spec":"ROUND40.1-hero-exit",...}}

# ج) الإعدادات الجاهزة الجديدة
curl -s http://localhost:8000/api/v1/exit-strategy/presets | head -c 500

# د) باك-تست بالإعدادات الموصى بها (قارنه بالافتراضي بنفس الطلب بلا config)
curl -s -X POST http://localhost:8000/api/v1/exit-strategy/backtest \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","timeframe":"15m","days":30,"limit":2000,"strategy":"zzfib_e2e",
       "config":{"take_profit_pct":3.0,"tp_reference":"avg","dca1_trigger_pct":5.0,
                 "dca2_trigger_pct":8.0,"cooldown_bars":50}}' | head -c 600

# هـ) الجولات السابقة لم تُمس
curl -s http://localhost:8000/api/v1/overlays/health | grep -o '"round": 39'
```

## التراجع (إن لزم)

- **إلى ج39.1** (إزالة محرك الخروج كاملاً):
```bash
cp /tmp/main.py.backup_before_r401 app/main.py   # أو نسخة ج39 الأصلية
rm app/services/exit_engine.py app/routers/exit_strategy.py
docker compose up -d --build
```
- **إلى ج40**: لا نوصي بها (40.1 تتفوق عليها بكل شيء وتحل محلها) — إن أصررت
  فاستخدم حزمة ج40 القديمة بنفس الخطوات.

## ملاحظات

- لا قاعدة بيانات ولا هجرات ولا متغيرات بيئة جديدة — stateless فوق Binance مباشرة.
- عدد المسارات بعد التثبيت: **165** (159 الأساسية + 6 نقاط exit-strategy).
- الحزمة آمنة للنسخ الكامل: ملفان جديدان + main.py بنسختك نفسها وسطرين موثقين.
