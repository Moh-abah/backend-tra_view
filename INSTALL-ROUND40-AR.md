# 🛠️ تثبيت الجولة 40 — محرك استراتيجية الخروج (Exit-Engine)

## محتويات الحزمة (3 ملفات كود + وثيقتان)

| الملف | الحالة | الوصف |
|---|---|---|
| `app/services/exit_engine.py` | **جديد** | محرك الخروج النقي + المُهايئات + تطبيع الإعدادات |
| `app/routers/exit_strategy.py` | **جديد** | راوتر `/api/v1/exit-strategy` (5 نقاط نهاية) |
| `app/main.py` | **معدَّل — سطران مضافان فقط** | استيراد + تسجيل الراوتر (مبني على نسختك الحالية نفسها) |
| `EXIT-STRATEGY-CONTRACT-AR.md` | وثيقة | **عقد وكيل الفرونت-إند** — سلّمه له كاملاً |
| `MD5SUMS.txt` | بصمات | تحقق ذاتي بعد النسخ |

> `main.py` في الحزمة = نسختك الحالية بالضبط + سطرَي `exit_strategy` (تحقق بالفرق:
> `diff main.pyالقديم main.pyالجديد` = سطران مضافان فقط، لا حذف ولا تعديل لأي شيء آخر).

## خطوات التثبيت (على السيرفر)

```bash
cd ~/TR_platform/backend

# 1) خذ نسخة احتياطية سريعة من main.py الحالي
cp app/main.py /tmp/main.py.backup_r39

# 2) فك الحزمة
unzip backend_ROUND40_exit_engine.zip -d r40
cd r40 && md5sum -c MD5SUMS.txt && cd ..

# 3) انسخ الملفات الثلاثة
cp -v r40/app/services/exit_engine.py   app/services/
cp -v r40/app/routers/exit_strategy.py  app/routers/
cp -v r40/app/main.py                   app/

# 4) إعادة البناء والإقلاع
docker compose up -d --build
```

## التحقق بعد الإقلاع (بالأمر وبالعين)

```bash
# أ) الخادم أقلع بلا أخطاء
docker logs --tail 5 trading-backend        # ← "Application startup complete."

# ب) راوتر الجولة 40 حاضر
curl -s http://localhost:8000/api/v1/exit-strategy/health
#   ← {"status":"ok","round":40,"engine":{"name":"Exit-Engine",...}}

# ج) الإعدادات الافتراضية + المخطط (لبناء الواجهة)
curl -s http://localhost:8000/api/v1/exit-strategy/defaults | head -c 400

# د) باك-تست حقيقي كامل (BTCUSDT 15m)
curl -s -X POST http://localhost:8000/api/v1/exit-strategy/backtest \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","timeframe":"15m","days":30,"limit":2000,"strategy":"zzfib_e2e"}' \
  | head -c 600

# هـ) الجولات السابقة لم تُمس (يجب أن يبقى 39)
curl -s http://localhost:8000/api/v1/overlays/health | grep -o '"round": 39'
```

## التراجع (إن لزم)

```bash
cp /tmp/main.py.backup_r39 app/main.py
rm app/services/exit_engine.py app/routers/exit_strategy.py
docker compose up -d --build
```

## ملاحظات

- **لا قاعدة بيانات جديدة ولا هجرات** — الراوتر يعمل بوضع stateless (نفس مسار websocket) فوق مزوّد Binance مباشرة.
- كل بصمات ملفات الجولات 34→39.1 **لم تتغير** (تحقق md5 بعد التعديل — انظر تقرير الجولة).
- الحزمة **آمنة للنسخ الكامل**: كل ملفاتها إما جديدة أو نسختك نفسها بسطرَين موثقَين.
