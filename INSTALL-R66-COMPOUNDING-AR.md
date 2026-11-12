# الجولة 66 — الحجم التراكمي (Compounding) في محرك استراتيجية الخروج

> **حزمة التسليم:** `backend_R66_COMPOUNDING.zip`
> **الأساس:** مشروعك الحالي بالضبط (R64 المدموجة — تحقق بصمات بت-بت قبل البناء، انظر §7)
> **الملفات المعدّلة:** 3 فقط · **التوافق الرجعي:** بت-بت مُثبت ببطارية 61 فحصاً + ضباب 2100 تشغيلة (صفر انحراف)

---

## 1) ما الذي يضيفه R66؟

وضع حجم مركز **تراكمي** بجوار الوضع الثابت الحالي، داخل كتلة إعدادات الخروج نفسها:

| الحقل | القيم | الوظيفة |
|---|---|---|
| `position_sizing` | `fixed_usd` (افتراضي) \| `percent_of_equity` | الوضع الثابت الحالي بت-بت، أو الوضع التراكمي الجديد |
| `position_size_pct` | `0.1 .. 100` | نسبة كل دخول من الرصيد الجاري (1 = 1٪ · 100 = كامل الرصيد) — **إلزامية في التراكمي** |
| `initial_capital` | رقم > 0 | بذرة الرصيد ($) — للمسار المستقل فقط (اختياري، الافتراضي 10000$) |

**قواعد الوضع التراكمي (نص العقد):**
- كل دخول (**الأول + التعزيزان DCA**) = `position_size_pct` × الرصيد الجاري E — بالتساوي 1:1:1 داخل الدورة الواحدة (E لا يتغير أثناء الدورة المفتوحة).
- E يبدأ من البذرة ويتحدّث **بعد كل إغلاق محقق فقط**: `E += pnl_usd` (العمولات مخصومة من pnl أصلاً). غير المحقق لا يلمس الرصيد.
- **أرضية الغبار:** أي حجم تحت 1$ يُثبَّت على 1$ ويُرصد في عدّاد `dust_floored_entries`.
- **جدار التصفية:** استنفاد الرصيد (E ≤ 0) يوقف فتح أي دورة جديدة فوراً (`account_liquidated=true`، وكل إشارة لاحقة تُحصى في `signals_ignored_liquidated`) — نفس فلسفة جدار −100٪ الصلب في المحرك الرئيسي.

**أولوية البذرة:**
- المسار الموحد `/api/v1/backtest1/run`: **جذر الطلب `initial_capital` يحكم دائماً** (الافتراضي 10000، والاسم المستعار `capital`/`balance` يعمل كما اليوم) — لا تُرسل داخل الكتلة هنا.
- المسار المستقل `/api/v1/exit-strategy/backtest`: حقل top-level جديد `initial_capital` > `initial_capital` داخل الكتلة > 10000$.

## 2) الملفات الثلاثة وماذا تغيّر فيها

| الملف | التغيير |
|---|---|
| `app/services/exit_engine.py` | جوهر R66: الوضعان + التحقق العربي + مخطط الحقول + الوصف الديناميكي + التراكم + الأرضية + جدار التصفية + `compounding_audit` الذاتي + مفتاح `signals_ignored_liquidated` الكسول |
| `app/services/unified_backtest.py` | 3 إضافات فقط: تمرير بذرة الجذر للمحرك، صدى الوضع في `exit_strategy` (`position_size_semantics` نص عربي)، وصدى `compounding_audit` في `summary` — كلها **مشروطة بالوضع التراكمي** |
| `app/routers/exit_strategy.py` | حقل `initial_capital` top-level للمسار المستقل + تمريره للمحرك + تحذيران (تجاهل الحجم الثابت عند التراكمي، وتجاوز التعرض 100٪ في الدورة) + صدى `compounding_audit` |

## 3) خطوات التثبيت (دقيقتان)

```bash
# 1) نسخة احتياطية (سلامة أولاً)
cp app/services/exit_engine.py       app/services/exit_engine.py.bak-r65
cp app/services/unified_backtest.py  app/services/unified_backtest.py.bak-r65
cp app/routers/exit_strategy.py      app/routers/exit_strategy.py.bak-r65

# 2) تركيب الملفات الثلاثة (من جذر الحزمة)
cp app/services/exit_engine.py       /مسار-المشروع/app/services/exit_engine.py
cp app/services/unified_backtest.py  /مسار-المشروع/app/services/unified_backtest.py
cp app/routers/exit_strategy.py      /مسار-المشروع/app/routers/exit_strategy.py

# 3) اختبارات القبول (انسخ مجلد tests-r66 كاملاً إلى جذر المشروع)
cp -r tests-r66 /مسار-المشروع/tests-r66
cd /مسار-المشروع
python3 -m py_compile app/services/exit_engine.py \
                      app/services/unified_backtest.py \
                      app/routers/exit_strategy.py && echo "COMPILE OK"

# 4) بطارية القبول — 61 فحصاً
python3 tests-r66/test_r66_battery.py
# المتوقع: النتيجة: 61 نجح · 0 فشل · الإجمالي 61 → R66 OK

# 5) الضباب الرجعي — 2100 تشغيلة عشوائية
python3 tests-r66/test_r66_fuzz.py
# المتوقع: runs=2100 ... mismatches=0 → R66 FUZZ OK

# 6) إعادة تشغيل الخدمة (uvicorn / docker / pm2 — حسب طريقتك)
```

> ملاحظة: ملفا `exit_engine_r64_baseline.py` و`unified_backtest_r64_baseline.py` داخل `tests-r66` هما **نسختا ما قبل R64/R66 المرجعيتان** اللتان تقارن ضدهما البطارية — لا تركَّبان في `app/` أبداً.

## 4) التحقق الحي (30 ثانية)

**المسار الموحد — تراكمي 1٪ من رصيد يبدأ 10000$:**

```bash
curl -X POST "http://SERVER:8000/api/v1/backtest1/run" -H "Content-Type: application/json" -d '{
  "symbols": ["BTCUSDT"], "timeframe": "1h", "days": 30,
  "initial_capital": 10000,
  "strategy_config": {"name": "zzfib"},
  "exit_strategy": {
    "strategy": "zzfib",
    "config": {"position_sizing": "percent_of_equity", "position_size_pct": 1.0,
               "take_profit_pct": 5.0, "dca1_trigger_pct": 3.0, "dca2_trigger_pct": 5.0}
  }
}'
# ثم دورتك المعتادة: status/TASK_ID ثم get/BACKTEST_ID
# في get: summary.compounding_audit.consistent == true
#         summary.exit_summary.capital.final_equity_usd يتغير دورة بعد دورة
#         summary.exit_strategy.position_size_semantics نص عربي بالبذرة والنسبة
```

**المسار المستقل — بذرة top-level:**

```bash
curl -X POST "http://SERVER:8000/api/v1/exit-strategy/backtest" -H "Content-Type: application/json" -d '{
  "symbol": "BTCUSDT", "timeframe": "1h", "market": "crypto", "days": 30,
  "strategy": "zzfib_e2e",
  "initial_capital": 50000,
  "config": {"position_sizing": "percent_of_equity", "position_size_pct": 2.0}
}'
# أول دخول = 2٪ × 50000 = 1000$ بالضبط
```

**أخطاء التحقق العربية (عينات):** `position_sizing='percent_of_equity' يتطلب position_size_pct صالحة [0.1..100]` · `position_size_pct خارج النطاق [0.1..100]` · `initial_capital يجب أن يكون رقماً أكبر من 0`.

## 5) عقد الاستجابة — مفاتيح R66 (تظهر **فقط** في الوضع التراكمي)

```
trades[]:                         cycle_usd · equity_before_usd · equity_after_usd
summary.capital:                  position_sizing · position_size_pct · initial_capital_usd
                                 final_equity_usd · equity_growth_pct
                                 dust_floored_entries · account_liquidated
                                 (position_size_usd = حجم أول دورة — إعادة استخدام توافقية)
summary.equity_curve[]:           equity_usd
summary.entry_signals:            signals_ignored_liquidated   ← كسول: يظهر فقط عند حدوث تجاهل فعلي بعد التصفية
مستوى الجذر:                      compounding_audit {mode, checked_entries, max_abs_error,
                                  formula, seed_usd, final_equity_usd, consistent}
مسار backtest1:                   summary.exit_strategy.position_size_semantics (نص عربي)
                                 summary.exit_strategy.compounding_audit (صدى)
مسار exit-strategy/backtest:      response.compounding_audit (صدى)
```

الحمولات الثابتة (`fixed_usd` أو بلا الحقول إطلاقاً): **لا مفتاح جديد واحد** في أي مستوى — نفس أرقام R64 بت-بت (مضمون بالبطارية A + الضباب).

## 6) خطآن اصطادتهما البطارية وعولجا قبل التسليم (شفافية كاملة)

1. **مفتاح غير مهيأ في المحرك:** عدّاد `signals_ignored_liquidated` كان يُزداد بمفتاح غير موجود في قاموس العدّادات → `KeyError` عند أول تصفية فعلية. **الإصلاح:** مفتاح كسول (`counters.get(...) + 1`) يظهر فقط عند التصفية — لا يظهر في الوضع الثابت مطلقاً (فحص C2 يثبت العدّاد=2 والفحوصات الستون بت-بت تثبت عدم ظهوره).
2. **إعادة تأسيس على أساسك الفعلي:** ملف `unified_backtest.py` كان مبنيّاً على لقطة تسبق R55 (قبل أعمدة `ind_*` وسقف 20000 شمعة مرئية ومنحنى الصفقة-لكل-نقطة). أعدنا تطبيق تغييرات R66 الثلاث على نسختك الحالية بالضبط، مع بطارية تدقيق خاصة أثبتت بقاء كل ميزات R55 سليمة (window identity · visual cap · ind_* · منحنى لكل صفقة · تضمين شموع الصفقات إجبارياً · صدى max_concurrent_positions).

## 7) سلامة الأساس (لماذا هذه الحزمة تنطبق على مشروعك نظيفاً)

قبل البناء تمت مطابقة مشروعك المرفوع (`backend_R66_base.zip`) بصماتٍ بت-بت: `exit_engine.py` و`exit_strategy.py` مطابقان لأساس البناء 100٪ (فروق صفرية)، و`unified_backtest.py` أُعيد تأسيسه على نسختك الحالية (§6.2). كل ملف في هذه الحزمة = نسختك الحالية + إضافات R66 المشروطة فقط — لا تراجع عن أي جولة سابقة (R34…R64 كلها محفوظة).

## 8) الاسترجاع (Rollback)

```bash
cp app/services/exit_engine.py.bak-r65      app/services/exit_engine.py
cp app/services/unified_backtest.py.bak-r65 app/services/unified_backtest.py
cp app/routers/exit_strategy.py.bak-r65     app/routers/exit_strategy.py
rm -rf tests-r66   # اختياري — لا يعتمد عليه الإنتاج
# ثم أعد تشغيل الخدمة
```

بصمات الملفات والاسترجاع في `MD5SUMS.txt`.
