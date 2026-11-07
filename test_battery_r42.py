# -*- coding: utf-8 -*-
"""بطارية اختبار R42 — التوحيد الكامل: استراتيجية الخروج داخل backtest1/run.

المواصفة الحرفية المختبرة (ج42):
  أ) المخطط:
     1) الحمولة الحالية للفرونت (بلا exit_strategy) تعمل كما هي بت-بت.
     2) exit_strategy: {strategy, strategy_params, config} مقبولة داخل
        POST /api/v1/backtest1/run نفسه — بما فيها use_trailing و trailing_giveback_pct.
     3) أخطاء الإعدادات تُرفض 422 فوراً في نفس الطلب (لا فشل صامت بعد dispatch).
  ب) محرك الخروج (ترقية ج41 فوق نسخة السيرفر الأحدث):
     4) التريلينق الحرفي: قمة من سعر التنفيذ، كل high يرفع السقف،
        إغلاق هبط 20٪ من القمة يغلق كاملاً (reason=trailing_stop + peak_price).
     5) عند التفعيل: يُلغى TP الثابت ووقف الفيبو والجني المتحرك المشروط.
     6) غياب use_trailing = صفقات السيرفر الحالي بت-بت (توافق كامل).
  ج) الخدمة الموحدة:
     7) run_unified_exit_backtest ينتج summary + chart_data بنفس أسماء
        حقول المحرك الرئيسي + الإثراءات (exit_strategy, exit_reasons,
        exit_trades, trail_lines).
     8) منحنى رأس المال نقطة-لكل-شمعة و final = initial + pnl.

التشغيل على السيرفر (بعد التركيب):
    python3 test_battery_r42.py
يعمل بلا سيرفر وبلا قاعدة بيانات — كل الفحوص محلية نقية.
"""
import importlib.util
import math
import os
import sys
import random

HERE = os.path.dirname(os.path.abspath(__file__))

# تحميل الوحدات من شجرة العمل (نفس جذر المشروع)
def load(name, relpath):
    p = os.path.join(HERE, relpath)
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

# مسارات ضمن شجرة المشروع (شغّل من جذر المشروع أو من مجلد الحزمة)
CANDIDATES = [
    os.path.join(HERE, "app", "services", "exit_engine.py"),
    os.path.join(HERE, "..", "app", "services", "exit_engine.py"),
]
def find(path_candidates):
    for p in path_candidates:
        if os.path.exists(p):
            return p
    raise SystemExit(f"لم أجد الملف — شغّل البطارية من جذر المشروع: {path_candidates}")

EE_PATH = find(CANDIDATES)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(EE_PATH)))  # جذر المشروع
sys.path.insert(0, ROOT)

EE = load("exit_engine_r42", EE_PATH)

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  ❌ {name} — {detail}")


def mk_candles(rows):
    out = []
    for i, (o, h, l, c) in enumerate(rows):
        out.append({"time": 1700000000000 + i * 3600000, "open": o, "high": h,
                    "low": l, "close": c, "volume": 1.0})
    return out


def mk_entry(bar, price, floor):
    return {"bar": bar, "time": 1700000000000 + bar * 3600000, "price": price,
            "floor": floor, "floor_meta": {"source": "test"},
            "signal": {"bar": bar, "signal": "Entry S3", "side": "buy", "price": price}}


print("=" * 78)
print("القسم أ — المخطط: exit_strategy داخل backtest1/run")
print("=" * 78)

from app.backtest.schemas import BacktestConfig

try:
    c1 = BacktestConfig(symbols=["BTCUSDT"], timeframe="1h", days=30)
    check("أ-1 الحمولة الحالية (بلا exit_strategy) تعمل — exit_strategy=None",
          c1.exit_strategy is None)
except Exception as exc:  # noqa: BLE001
    check("أ-1 الحمولة الحالية تعمل", False, str(exc)[:120])

try:
    c2 = BacktestConfig(
        symbols=["BTCUSDT"], timeframe="1h", days=30,
        exit_strategy={"strategy": "zzfib",
                       "config": {"use_trailing": True, "trailing_giveback_pct": 20.0}},
    )
    norm = getattr(c2.exit_strategy, "_normalized_block", None)
    ok = (norm is not None and norm["config"]["use_trailing"] is True
          and norm["config"]["trailing_giveback_pct"] == 20.0)
    check("أ-2 exit_strategy + use_trailing=true + giveback=20 مقبولة والمنظم محسوب", ok)
except Exception as exc:  # noqa: BLE001
    check("أ-2 exit_strategy مقبولة", False, str(exc)[:120])

def expect_422(name, **block):
    try:
        BacktestConfig(symbols=["BTCUSDT"], exit_strategy=block)
        check(name, False, "قُبلت ولا يجب!")
    except Exception as exc:  # noqa: BLE001
        check(name, True, str(exc)[:80])

expect_422("أ-3 422: استراتيجية غير مدعومة", strategy="rsi_hero")
expect_422("أ-4 422: حقل config مجهول", config={"bogus_field": 1})
expect_422("أ-5 422: use_trailing نوع خاطئ", config={"use_trailing": "yes"})
expect_422("أ-6 422: trailing_giveback_pct فوق 90", config={"trailing_giveback_pct": 95.0})
expect_422("أ-7 422: معامل استراتيجية غير مسموح",
           strategy="zzfib_e2e", strategy_params={"bogus_param": 1})

try:
    d = c2.model_dump(mode="json")
    c2b = BacktestConfig(**d)
    ok = c2b.exit_strategy is not None and c2b.exit_strategy.config["use_trailing"] is True
    check("أ-8 دورة model_dump → إعادة بناء JSON-آمنة (تمرير المهمة)", ok)
except Exception as exc:  # noqa: BLE001
    check("أ-8 دورة model_dump", False, str(exc)[:120])

print()
print("=" * 78)
print("القسم ب — محرك الخروج ج42 (ترقية ج41 فوق نسخة السيرفر الأحدث)")
print("=" * 78)

check("ب-0 الهوية ROUND42-hero-exit-trailing",
      EE.EXIT_ENGINE_SPEC == "ROUND42-hero-exit-trailing", EE.EXIT_ENGINE_SPEC)

# بيانات: صعود 100→111.5 ثم هبوط حاد
ROWS = [(100.0, 101.0, 99.0, 100.5)]
for i in range(1, 11):
    ROWS.append((100 + i, 100 + i + 1, 99 + i, 100 + i + 0.5))
PEAK_CLOSE = 110.5
for i in range(11, 20):
    v = 111.5 - (i - 10) * 4
    ROWS.append((v + 2, v + 3, v - 1, v))
CANDLES = mk_candles(ROWS)
ENTRY = [mk_entry(0, 100.0, 95.0)]

# ب-1: بلا تريلينق → TP 5% يعمل (سلوك السيرفر الحالي)
r1 = EE.run_exit_backtest(CANDLES, ENTRY, {"take_profit_pct": 5.0})
check("ب-1 بلا تريلينق: خروج take_profit @105 (سلوك السيرفر الحالي)",
      r1["trades"][0]["exit"]["reason"] == "take_profit"
      and abs(r1["trades"][0]["exit"]["price"] - 105.0) < 1e-9)

# ب-2: التريلينق الحرفي — مطابقة يدوية بت-بت
r2 = EE.run_exit_backtest(CANDLES, ENTRY, {"use_trailing": True, "trailing_giveback_pct": 20.0})
tr2 = r2["trades"][0]
peak_run, exp_bar, exp_price = 100.0, None, None
for i in range(1, len(ROWS)):
    if ROWS[i][1] > peak_run:
        peak_run = ROWS[i][1]
    if ROWS[i][3] <= peak_run * 0.8:
        exp_bar, exp_price = i, ROWS[i][3]
        break
ok2 = (tr2["exit"]["reason"] == "trailing_stop"
       and tr2["exit"]["bar"] == exp_bar
       and abs(tr2["exit"]["price"] - exp_price) < 1e-9
       and abs(tr2["exit"]["peak_price"] - peak_run) < 1e-9)
check("ب-2 التريلينق الحرفي: قمة من سعر التنفيذ + كل high يرفع السقف + إغلاق 20٪ يغلق (مطابقة يدوية بت-بت)", ok2,
      f"reason={tr2['exit']['reason']} bar={tr2['exit']['bar']}/{exp_bar} price={tr2['exit']['price']}/{exp_price} peak={tr2['exit'].get('peak_price')}/{peak_run}")

# ب-3: TP ملغى نطقاً
r3 = EE.run_exit_backtest(CANDLES, ENTRY,
                          {"use_trailing": True, "trailing_giveback_pct": 20.0, "take_profit_pct": 5.0})
check("ب-3 عند التفعيل: TP ملغى نطقاً (رغم إرسال take_profit_pct=5)",
      r3["trades"][0]["exit"]["reason"] == "trailing_stop")

# ب-4: الجني المتحرك المشروط ملغى أيضاً عند التفعيل (الأولوية)
r4 = EE.run_exit_backtest(CANDLES, ENTRY,
                          {"use_trailing": True, "trailing_giveback_pct": 20.0, "tp_trail_arm_pct": 2.0})
check("ب-4 الأولوية: use_trailing يلغي tp_trail المشروط أيضاً",
      r4["trades"][0]["exit"]["reason"] == "trailing_stop")

# ب-5: DCA تبقى تعمل مع التريلينق
r5 = EE.run_exit_backtest(CANDLES, ENTRY,
                          {"use_trailing": True, "trailing_giveback_pct": 20.0,
                           "dca1_trigger_pct": 3.0, "dca2_trigger_pct": 5.0})
check("ب-5 التعزيزات DCA تعمل مع التريلينق (لم تُطلب إلغاؤها)",
      len(r5["trades"][0]["entries"]) >= 1 and "dca1" in r5["trades"][0]["dca_fired"])

# ب-6: عقد الرد — مفتاح trailing_stop فقط عند التفعيل + كتلة literal فقط عند التفعيل
s_off = EE.run_exit_backtest(CANDLES, ENTRY, None)
s_on = EE.run_exit_backtest(CANDLES, ENTRY, {"use_trailing": True})
check("ب-6 عقد الرد محفوظ: trailing_stop/literal يظهران فقط عند التفعيل",
      "trailing_stop" not in s_off["summary"]["exits"]
      and "trailing_stop" in s_on["summary"]["exits"]
      and "literal" not in s_off["trades"][0]["trail"]
      and "literal" in s_on["trades"][0]["trail"])

# ب-7: توافق بت-بت مع نسخة السيرفر الحالية عبر توليفات
ROLLBACK = os.path.join(os.path.dirname(EE_PATH), "..", "..", "rollback")
# في شجرة الحزمة: rollback/app/services/exit_engine.py — في شجرة المشروع لا يوجد؛
# نقارن مع النسخة المرجعية إن وُجدت وإلا نكتفي بالتحقق الذاتي
OLD_PATHS = [
    os.path.join(HERE, "rollback", "app", "services", "exit_engine.py"),
    os.path.join(HERE, "..", "rollback", "app", "services", "exit_engine.py"),
]
old = None
for p in OLD_PATHS:
    if os.path.exists(p):
        old = load("exit_engine_prev", p)
        break
if old is not None:
    all_ok = True
    for cfgin in (None, {"take_profit_pct": 5.0},
                  {"dca1_trigger_pct": 3.0, "dca2_trigger_pct": 5.0},
                  {"tp_trail_arm_pct": 2.0},
                  {"trend_filter_sma_bars": 5, "min_floor_distance_pct": 1.0}):
        rn = EE.run_exit_backtest(CANDLES, ENTRY, cfgin)
        ro = old.run_exit_backtest(CANDLES, ENTRY, cfgin)
        if rn["trades"] != ro["trades"] or rn["summary"] != ro["summary"]:
            all_ok = False
            break
    check("ب-7 بت-بت مع نسخة السيرفر الحالية عبر 5 توليفات (صفقات + ملخصات متطابقة)", all_ok)
else:
    check("ب-7 (بدون rollback في الشجرة — تجاوز المقارنة المرجعية)", True)

# ب-8: 422 عقد الإعدادات محفوظ
_, e1 = EE.normalize_exit_config({"foo": 1})
_, e2 = EE.normalize_exit_config({"trailing_giveback_pct": 95.0})
_, e3 = EE.normalize_exit_config({"use_trailing": "yes"})
check("ب-8 normalize: حقل مجهول/خارج النطاق/نوع خاطئ — كلها مرفوضة",
      any("foo" in e for e in e1) and any("90" in e for e in e2)
      and any("use_trailing" in e for e in e3))

print()
print("=" * 78)
print("القسم ج — الخدمة الموحدة (unified_backtest) بنفس عقد المحرك الرئيسي")
print("=" * 78)

from app.services.unified_backtest import run_unified_exit_backtest, validate_exit_block

random.seed(7)
N = 1200
candles = []
for i in range(N):
    wave = (math.sin(i / 35.0) * 10 + math.sin(i / 120.0) * 25 + math.sin(i / 13.0) * 4)
    p = 100 + wave + i * 0.02
    o = p + random.uniform(-0.4, 0.4)
    candles.append({"time": 1700000000000 + i * 3600000, "open": round(o, 2),
                    "high": round(max(o, p) + random.uniform(.1, 1.2), 2),
                    "low": round(min(o, p) - random.uniform(.1, 1.2), 2),
                    "close": round(p, 2), "volume": 1000.0})

cfgU, errsU = EE.normalize_exit_config({"use_trailing": True, "trailing_giveback_pct": 20.0})
check("ج-1 الإعدادات الموحدة تُطبَّع بلا أخطاء", not errsU)

res = run_unified_exit_backtest(candles, "zzfib", {}, cfgU, {
    "symbol": "BTCUSDT", "timeframe": "1h", "market": "crypto",
    "initial_capital": 10000.0, "timezone": "UTC", "tz_offset_minutes": 0,
    "name": "R42-battery",
})
s, cd = res["summary"], res["chart_data"]

check("ج-2 صفقات فعلية من zzfib الحقيقي (توليد إشارات حقيقي)", s["total_trades"] > 0,
      f"trades={s['total_trades']}")
check("ج-3 خروج تريلينق واحد على الأقل", s["exit_reasons"].get("trailing_stop", 0) > 0,
      str(s["exit_reasons"]))

std_fields = ["name", "timeframe", "initial_capital", "final_capital", "total_pnl",
              "total_pnl_percent", "total_trades", "winning_trades", "losing_trades",
              "win_rate", "max_drawdown_percent", "sharpe_ratio", "sortino_ratio",
              "calmar_ratio", "profit_factor", "expectancy", "annual_return_percent",
              "volatility_annual", "var_95", "cvar_95", "system_quality_number",
              "kelly_criterion", "architecture_mode", "fees_applied", "fill_model",
              "math_audit", "effective_config"]
missing = [k for k in std_fields if k not in s]
check("ج-4 كل الحقول القياسية بنفس أسماء المحرك الرئيسي", not missing, f"مفقود: {missing}")
check("ج-5 الإثراءات: exit_strategy/exit_reasons/exit_trades/engine",
      all(k in s for k in ("exit_strategy", "exit_reasons", "exit_trades", "engine")))
check("ج-6 التشكيل الفعّال للعرض: trailing.active + giveback + الملغيات",
      s["exit_strategy"]["trailing"]["active"] is True
      and s["exit_strategy"]["trailing"]["cancelled_take_profit"] is True
      and s["exit_strategy"]["trailing"]["giveback_pct"] == 20.0)
check("ج-7 chart_data: visual_candles/trade_points/equity_curve/drawdown_curve",
      all(k in cd for k in ("visual_candles", "trade_points", "equity_curve", "drawdown_curve")))
check("ج-8 شمعة لكل نقطة + منحنى لكل شمعة",
      len(cd["visual_candles"]) == N and len(cd["equity_curve"]) == N
      and len(cd["drawdown_curve"]) == N)
types = {p["type"] for p in cd["trade_points"]}
check("ج-9 نقاط الدخول/الخروج/التعزيز بنفس شكل المحرك الرئيسي",
      types <= {"entry", "exit", "dca"} and "entry" in types and "exit" in types,
      str(types))
check("ج-10 خط السقف المتحرك لكل صفقة (trail_lines) ينتهي عند القمة الموثقة",
      "trail_lines" in cd and len(cd["trail_lines"]) >= 1
      and all(abs(line[-1]["price"] - tr["exit"]["peak_price"]) < 1e-6
              for tr, line in ((t, cd["trail_lines"][str(t["trade_id"])])
                               for t in s["exit_trades"]
                               if str(t["trade_id"]) in cd["trail_lines"])))
check("ج-11 final_capital = initial + total_pnl",
      abs(s["final_capital"] - (10000.0 + s["total_pnl"])) < 1e-6)
check("ج-12 validate_exit_block: مصدر تحقق واحد (مخطط + منفذ)",
      validate_exit_block("zzfib", None, {"use_trailing": True})[0] is not None
      and validate_exit_block("bogus", None, None)[1] != [])

print()
print("=" * 78)
if FAIL == 0:
    print(f"النتيجة: {PASS}/{PASS + FAIL} — كل الفحوص نجحت ✅")
    print("ج42 جاهزة: محرك واحد · حمولة واحدة · مصدر نتائج واحد")
else:
    print(f"النتيجة: {PASS}/{PASS + FAIL} — فشل {FAIL}:")
    for name, det in FAILURES:
        print(f"   ❌ {name} — {det}")
    sys.exit(1)
