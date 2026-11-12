# -*- coding: utf-8 -*-
"""
بطارية اختبار R64 — زر تفعيل/إلغاء خروج كسر الفيبو + الوقف النسبي البديل
=========================================================================
تختبر:
  A) انحدار بت-بت: المحرك الأصلي (قبل R64) مقابل المعدّل على حمولات
     تاريخية (الافتراضي) — يجب التطابق التام.
  B) الزر مفعّل صراحةً (fibo_floor_exit=true) = نفس سلوك A.
  C) الزر معطّل + stop_loss_pct>0: خروج الفيبو لا يعمل قط، والوقف النسبي
     يعمل بلمس اللمّة عند الدخول الأول×(1−النسبة) — مع فجوة افتتاح.
  D) الزر معطّل + stop_loss_pct=0: لا وقف نهائياً — الصفقة تُدار للنهاية.
  E) التريلينق الحرفي يُلغي الزر والوقف النسبي معاً.
  F) التطبيع: رفض الأنواع الخاطئة برسائل عربية + الحدود.
  G) الوراثة: stop_loss_pct يُورَث من stop_loss_percent بجذر الكونفيق
     في منطق المسارين (نفس الشرط المنسوخ حرفياً من الكود).
  H) الوصف العربي + exits_view (مفتاح stop_loss يظهر فقط عند التعطيل).
  I) دورة كاملة مع DCA: الوقف النسبي يقيس من سعر الدخول الأول حرفياً.
"""
import importlib.util
import json
import sys
import copy

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
        FAILURES.append(f"{name} — {detail}")
        print(f"  ❌ {name} — {detail}")


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


OLD = load_module("/home/z/r64-workspace/exit_engine_ORIGINAL.py", "exit_engine_old")
NEW = load_module("/home/z/r64-workspace/app/services/exit_engine.py", "exit_engine_new")


# ---------------------------------------------------------------------------
# شموع توليفية: صعود من 100 إلى 115 (TP عند +5% من 100 = 105) مع هبوط لاحق
# تحت الأرضية (90) لاختبار خروج الفيبو، وهبوط إلى 94/93 لاختبار وقف 5%/7%.
# ---------------------------------------------------------------------------
def candle(i, o, h, l, c):
    return {"time": 1700000000000 + i * 60000, "open": o, "high": h, "low": l,
            "close": c, "volume": 1000.0}


def base_candles():
    cs = []
    # 0..3 صعود لطيف فوق الأرضية
    cs += [candle(0, 100.0, 100.5, 99.5, 100.2),
           candle(1, 100.2, 101.0, 100.0, 100.8),
           candle(2, 100.8, 101.5, 100.5, 101.2),
           candle(3, 101.2, 101.8, 101.0, 101.6)]
    # 4: قمة تحت الهدف (هدف +5% من 100.2 = 105.21 — عالية 104.5 لا تلمسه)
    cs.append(candle(4, 101.6, 104.5, 101.5, 103.0))
    # 5..7 هدوء
    cs += [candle(5, 103.0, 103.5, 102.5, 102.8),
           candle(6, 102.8, 103.2, 102.0, 102.5),
           candle(7, 102.5, 102.8, 101.8, 102.0)]
    # 8: هبوط حاد — إغلاق تحت الأرضية 90 (خروج فيبو) ولمس 93.5 (وقف 5.5%؟)
    cs.append(candle(8, 102.0, 102.2, 89.0, 89.5))
    # 9..11 استمرار هبوط
    cs += [candle(9, 89.5, 90.0, 86.0, 87.0),
           candle(10, 87.0, 88.0, 84.0, 85.0),
           candle(11, 85.0, 86.0, 82.0, 83.0)]
    return cs


def entry(bar, price, floor):
    return {"bar": bar, "time": 1700000000000 + bar * 60000, "price": price,
            "floor": floor, "floor_meta": {"source": "synthetic"}, "signal": {}}


ENTRIES = [entry(0, 100.2, 90.0)]  # دخول عند شمعة 0 بسعر 100.2 وأرضية 90

print("=" * 72)
print("A) انحدار بت-بت — الافتراضي (لا حقول R64) والمحرك القديم")
print("=" * 72)
for payload_name, cfg_override in [
    ("الافتراضي الكامل", None),
    ("use_trailing=true", {"use_trailing": True, "trailing_giveback_pct": 20.0}),
    ("tp_trail مشروط", {"tp_trail_arm_pct": 2.0, "tp_trail_giveback_pct": 1.0}),
    ("سقف رقمي R55", {"max_concurrent_positions": 2}),
    ("البريسيت الموصى به", {"take_profit_pct": 3.0, "tp_reference": "avg",
                              "dca1_trigger_pct": 5.0, "dca2_trigger_pct": 8.0,
                              "cooldown_bars": 50}),
]:
    cfg_old = copy.deepcopy(cfg_override)
    cfg_new = copy.deepcopy(cfg_override)
    r_old = OLD.run_exit_backtest(base_candles(), ENTRIES, cfg_old)
    r_new = NEW.run_exit_backtest(base_candles(), ENTRIES, cfg_new)
    same_trades = json.dumps(r_old["trades"], sort_keys=True) == json.dumps(r_new["trades"], sort_keys=True)
    same_summary = json.dumps(r_old["summary"], sort_keys=True) == json.dumps(r_new["summary"], sort_keys=True)
    check(f"A: trades بت-بت [{payload_name}]", same_trades)
    check(f"A: summary بت-بت [{payload_name}]", same_summary)

print()
print("=" * 72)
print("B) الزر مفعّل صراحةً fibo_floor_exit=true = نفس الافتراضي")
print("=" * 72)
r_default = NEW.run_exit_backtest(base_candles(), ENTRIES, None)
r_on = NEW.run_exit_backtest(base_candles(), ENTRIES, {"fibo_floor_exit": True})
check("B: trades متطابقة",
      json.dumps(r_default["trades"], sort_keys=True) == json.dumps(r_on["trades"], sort_keys=True))
check("B: summary متطابق",
      json.dumps(r_default["summary"], sort_keys=True) == json.dumps(r_on["summary"], sort_keys=True))
check("B: الخروج التاريخي fib_break وقع فعلاً (الإغلاق 89.5 < الأرضية 90)",
      any(t["exit"]["reason"] == "fib_break" for t in r_default["trades"]),
      f"reasons={[t['exit']['reason'] for t in r_default['trades']]}")

print()
print("=" * 72)
print("C) الزر معطّل + stop_loss_pct=5 — الوقف النسبي بلمس اللمّة")
print("=" * 72)
r_c = NEW.run_exit_backtest(base_candles(), ENTRIES, {"fibo_floor_exit": False, "stop_loss_pct": 5.0})
t_c = r_c["trades"]
check("C: لا خروج fib_break إطلاقاً",
      all(t["exit"]["reason"] != "fib_break" for t in t_c),
      f"reasons={[t['exit']['reason'] for t in t_c]}")
# الدخول 100.2 → الوقف = 100.2 × 0.95 = 95.19
stop_expected = 100.2 * 0.95
sl_trades = [t for t in t_c if t["exit"]["reason"] == "stop_loss"]
check("C: خروج stop_loss وقع", len(sl_trades) == 1, f"عدد={len(sl_trades)}")
if sl_trades:
    tr = sl_trades[0]
    check("C: سعر الوقف مضبوط (لمّة 89.0 ≤ 95.19 — لكن الشمعة 4 لمست؟)",
          abs(tr["exit"]["price"] - stop_expected) < 1e-9,
          f"exit_price={tr['exit']['price']} expected={stop_expected}")
    check("C: stop_price موثّق في سجل الخروج",
          abs(tr["exit"].get("stop_price", -1) - stop_expected) < 1e-9)
    check("C: أول شمعة تلمس الوقف هي الشمعة 8 (لمّة 89.0 — الشموع 0..7 لم تلمس 95.19)",
          tr["exit"]["bar"] == 8, f"bar={tr['exit']['bar']}")
    # DCA1 عند 3% = 97.194 — الشموع 0..7 لم تلمسه، الشمعة 8 لمست 89 → DCA يطلق قبل الوقف؟
    # ترتيب الفحص: (أ) الوقف قبل (ج) التعزيزات ⇒ الوقف يفوز في نفس الشمعة
    check("C: الوقف له الأولوية على التعزيز في نفس الشمعة (لا dca1)",
          "dca1" not in tr["dca_fired"], f"dca_fired={tr['dca_fired']}")

print()
print("=" * 72)
print("C2) فجوة هبوط تحت الوقف — التنفيذ عند الافتتاح")
print("=" * 72)
cs_gap = base_candles()
# نجعل شمعة 8 تفتح عند 90.0 (تحت الوقف 95.19) بلمّة 89.5
cs_gap[8] = candle(8, 90.0, 90.5, 89.5, 89.5)
r_c2 = NEW.run_exit_backtest(cs_gap, ENTRIES, {"fibo_floor_exit": False, "stop_loss_pct": 5.0})
sl2 = [t for t in r_c2["trades"] if t["exit"]["reason"] == "stop_loss"]
check("C2: خروج stop_loss وقع", len(sl2) == 1)
if sl2:
    check("C2: التنفيذ عند الافتتاح 90.0 (فجوة تحت الوقف 95.19)",
          abs(sl2[0]["exit"]["price"] - 90.0) < 1e-9,
          f"price={sl2[0]['exit']['price']}")

print()
print("=" * 72)
print("D) الزر معطّل + stop_loss_pct=0 — لا وقف نهائياً")
print("=" * 72)
r_d = NEW.run_exit_backtest(base_candles(), ENTRIES, {"fibo_floor_exit": False, "stop_loss_pct": 0.0})
t_d = r_d["trades"]
check("D: لا fib_break ولا stop_loss",
      all(t["exit"]["reason"] not in ("fib_break", "stop_loss") for t in t_d),
      f"reasons={[t['exit']['reason'] for t in t_d]}")
check("D: الصفقة عاشت لنهاية البيانات أو الهدف",
      any(t["exit"]["reason"] in ("end_of_data", "take_profit") for t in t_d))
check("D: exits_view يحمل مفتاح stop_loss (الزر معطّل)",
      "stop_loss" in r_d["summary"]["exits"],
      f"exits={r_d['summary']['exits']}")
check("D: exits_view في الافتراضي لا يحمل مفتاح stop_loss (توافق بت-بت)",
      "stop_loss" not in r_default["summary"]["exits"],
      f"exits={r_default['summary']['exits']}")

print()
print("=" * 72)
print("E) التريلينق الحرفي يُلغي الزر والوقف النسبي معاً")
print("=" * 72)
r_e = NEW.run_exit_backtest(base_candles(), ENTRIES, {
    "use_trailing": True, "trailing_giveback_pct": 3.0,
    "fibo_floor_exit": False, "stop_loss_pct": 1.0,
})
t_e = r_e["trades"]
check("E: الخروج الوحيد trailing_stop",
      all(t["exit"]["reason"] == "trailing_stop" for t in t_e),
      f"reasons={[t['exit']['reason'] for t in t_e]}")
check("E: لا stop_loss ولا fib_break",
      all(t["exit"]["reason"] not in ("stop_loss", "fib_break") for t in t_e))

print()
print("=" * 72)
print("F) التطبيع — الأنواع والحدود")
print("=" * 72)
cfg_ok, errs = NEW.normalize_exit_config({"fibo_floor_exit": False, "stop_loss_pct": 7.5})
check("F: قبول صحيح", errs == [] and cfg_ok["fibo_floor_exit"] is False and cfg_ok["stop_loss_pct"] == 7.5,
      f"errors={errs}")
_, errs = NEW.normalize_exit_config({"fibo_floor_exit": "yes"})
check("F: رفض fibo_floor_exit نصي", any("fibo_floor_exit" in e for e in errs), f"errors={errs}")
_, errs = NEW.normalize_exit_config({"stop_loss_pct": "abc"})
check("F: رفض stop_loss_pct نصي", any("stop_loss_pct" in e for e in errs), f"errors={errs}")
_, errs = NEW.normalize_exit_config({"stop_loss_pct": 150.0})
check("F: رفض stop_loss_pct > 100", any("stop_loss_pct" in e for e in errs), f"errors={errs}")
cfg_def, errs = NEW.normalize_exit_config({})
check("F: الافتراضي fibo_floor_exit=true و stop_loss_pct=0",
      errs == [] and cfg_def["fibo_floor_exit"] is True and cfg_def["stop_loss_pct"] == 0.0)
check("F: الحقلان في EXIT_CONFIG_SCHEMA (الفرونت يبني الزر منهما)",
      "fibo_floor_exit" in NEW.EXIT_CONFIG_SCHEMA and "stop_loss_pct" in NEW.EXIT_CONFIG_SCHEMA)
check("F: الحقلان في /defaults presets تلقائياً",
      all("fibo_floor_exit" in p["config"] for p in NEW.EXIT_ENGINE_PRESETS))

print()
print("=" * 72)
print("G) الوراثة من جذر الكونفيق — نفس شرط المسارين حرفياً")
print("=" * 72)


def apply_r64_inheritance(exit_cfg, block_config_raw, root_stop_loss_percent):
    """نسخة حرفية من منطق R64 في المسارين (tasks + backtest1)."""
    if exit_cfg.get("fibo_floor_exit") is False and "stop_loss_pct" not in (block_config_raw or {}):
        _root_sl_r64 = root_stop_loss_percent
        if _root_sl_r64 is not None and 0.0 < float(_root_sl_r64) < 100.0:
            exit_cfg["stop_loss_pct"] = float(_root_sl_r64)
    return exit_cfg


# G1: تعطيل الفيبو + جذر فيه SL=2 → وراثة
cfg, _ = NEW.normalize_exit_config({"fibo_floor_exit": False})
cfg = apply_r64_inheritance(cfg, None, 2.0)
check("G1: ورث stop_loss_pct=2.0 من الجذر", cfg["stop_loss_pct"] == 2.0, f"cfg={cfg['stop_loss_pct']}")

# G2: الصريح في الكتلة يعلو فوق الجذر
cfg, _ = NEW.normalize_exit_config({"fibo_floor_exit": False, "stop_loss_pct": 3.0})
cfg = apply_r64_inheritance(cfg, {"stop_loss_pct": 3.0}, 2.0)
check("G2: الصريح (3.0) يعلو فوق الجذر (2.0)", cfg["stop_loss_pct"] == 3.0)

# G3: الجذر معطّل (None/0/100) → لا وراثة
for root_val in (None, 0.0, 100.0):
    cfg, _ = NEW.normalize_exit_config({"fibo_floor_exit": False})
    cfg = apply_r64_inheritance(cfg, None, root_val)
    check(f"G3: جذر={root_val} ⇒ بلا وراثة (يبقى 0)", cfg["stop_loss_pct"] == 0.0)

# G4: الفيبو مفعّل → لا وراثة إطلاقاً (الجذر لا يُلمس)
cfg, _ = NEW.normalize_exit_config({})
cfg = apply_r64_inheritance(cfg, None, 2.0)
check("G4: الفيبو مفعّل ⇒ stop_loss_pct يبقى 0 (لا تأثير)", cfg["stop_loss_pct"] == 0.0)

# G5: التحقق من أن الكود الفعلي في المسارين يحتوي الشرط نفسه (تطابق المسارين)
tasks_src = open("/home/z/r64-workspace/app/tasks/backtest_tasks.py", encoding="utf-8").read()
router_src = open("/home/z/r64-workspace/app/routers/backtest1.py", encoding="utf-8").read()
cond = 'if exit_cfg.get("fibo_floor_exit") is False and "stop_loss_pct" not in (block.config or {}):'
check("G5: شرط الوراثة موجود في backtest_tasks.py", cond in tasks_src)
check("G5: شرط الوراثة موجود في backtest1.py", cond in router_src)

print()
print("=" * 72)
print("H) الوصف العربي + الصدى")
print("=" * 72)
desc_on = NEW.describe_exit_config(NEW.normalize_exit_config({})[0])
check("H: وصف الافتراضي يذكر فيبو", "فيبوناتشي" in desc_on and "لا وقف نسبي" in desc_on)
desc_off = NEW.describe_exit_config(NEW.normalize_exit_config({"fibo_floor_exit": False, "stop_loss_pct": 4.0})[0])
check("H: وصف التعطيل يذكر الوقف النسبي 4٪", "معطّل" in desc_off and "4٪" in desc_off and "فيبو" in desc_off)
desc_none = NEW.describe_exit_config(NEW.normalize_exit_config({"fibo_floor_exit": False})[0])
check("H: وصف بلا وقف يصرّح «لا وقف بديل»", "لا وقف بديل" in desc_none, f"desc={desc_none}")
desc_trail = NEW.describe_exit_config(NEW.normalize_exit_config({"use_trailing": True})[0])
check("H: وصف التريلينق يذكر إلغاء الوقف النسبي", "الوقف النسبي البديل" in desc_trail)
r_c_cfg_echo = r_c["config"]
check("H: الصدى يعيد الحقلين (مصدر حقيقة للفرونت)",
      r_c_cfg_echo.get("fibo_floor_exit") is False and r_c_cfg_echo.get("stop_loss_pct") == 5.0)

print()
print("=" * 72)
print("I) دورة مع DCA — الوقف النسبي يقيس من سعر الدخول الأول")
print("=" * 72)
cs_i = base_candles()
# شمعة 5: هبوط يلمس 97.0 (DCA1 عند 3% من 100.2 = 97.194 ✓ داخل النطاق فوق 90)
cs_i[5] = candle(5, 103.0, 103.0, 96.5, 97.5)
# شمعة 6: هبوط أعمق يلمس وقف 5% من الدخول الأول (95.19)
cs_i[6] = candle(6, 97.5, 97.6, 94.0, 95.0)
r_i = NEW.run_exit_backtest(cs_i, ENTRIES, {"fibo_floor_exit": False, "stop_loss_pct": 5.0})
t_i = r_i["trades"]
sl_i = [t for t in t_i if t["exit"]["reason"] == "stop_loss"]
check("I: خروج stop_loss وقع بعد DCA", len(sl_i) == 1, f"reasons={[t['exit']['reason'] for t in t_i]}")
if sl_i:
    tr = sl_i[0]
    check("I: dca1 أُطلق في الشمعة 5", "dca1" in tr["dca_fired"], f"fired={tr['dca_fired']}")
    check("I: مراكز الصفقة 2 (أساسي + dca1)", len(tr["entries"]) == 2)
    # وقف الدخول الأول 100.2 × 0.95 = 95.19 — اللمّة 94.0 لمسته في الشمعة 6
    check("I: سعر التنفيذ = سعر الوقف من الدخول الأول (لا المتوسط)",
          abs(tr["exit"]["price"] - 100.2 * 0.95) < 1e-9,
          f"price={tr['exit']['price']} expected={100.2 * 0.95}")
    check("I: بار الخروج 6", tr["exit"]["bar"] == 6, f"bar={tr['exit']['bar']}")

print()
print("=" * 72)
print(f"النتيجة النهائية: ✅ {PASS} نجح · ❌ {FAIL} فشل")
print("=" * 72)
if FAILURES:
    print("الفشل:")
    for f in FAILURES:
        print(f"  • {f}")
    sys.exit(1)
print("كل الفحوصات نجحت — R64 جاهز للتسليم.")
