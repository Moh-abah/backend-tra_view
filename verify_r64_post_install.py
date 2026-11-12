# -*- coding: utf-8 -*-
"""
تحقق R64 ما بعد التثبيت — يعمل على سيرفرك الفعلي بعد الدمج.
يستورد محرك الخروج الحقيقي (app.services.exit_engine) ويفحص:
  1) الحقلين موجودين في الافتراضيات والسكيما
  2) الزر معطّل: خروج الفيبو لا يعمل والوقف النسبي يعمل بالسعر الصحيح
  3) فجوة الافتتاح تحت الوقف
  4) بلا وقف نهائياً عند التعطيل دون بديل
  5) التريلينق يُلغي الاثنين
  6) التطبيع: رفض الأنواع الخاطئة
  7) الوصف العربي الديناميكي

شغّله من جذر المشروع:  python3 verify_r64_post_install.py
"""
import json
import sys

try:
    from app.services.exit_engine import (
        EXIT_CONFIG_DEFAULTS, EXIT_CONFIG_SCHEMA,
        describe_exit_config, normalize_exit_config, run_exit_backtest,
    )
except Exception as exc:  # noqa: BLE001
    print(f"❌ فشل استيراد app.services.exit_engine: {exc}")
    print("   شغّل السكربت من جذر المشروع حيث مجلد app/ موجود.")
    sys.exit(2)

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")


def candle(i, o, h, l, c):
    return {"time": 1700000000000 + i * 60000, "open": o, "high": h, "low": l,
            "close": c, "volume": 1000.0}


CANDLES = [
    candle(0, 100.0, 100.5, 99.5, 100.2),
    candle(1, 100.2, 101.0, 100.0, 100.8),
    candle(2, 100.8, 101.5, 100.5, 101.2),
    candle(3, 101.2, 101.8, 101.0, 101.6),
    candle(4, 101.6, 104.5, 101.5, 103.0),
    candle(5, 103.0, 103.5, 102.5, 102.8),
    candle(6, 102.8, 103.2, 102.0, 102.5),
    candle(7, 102.5, 102.8, 101.8, 102.0),
    candle(8, 102.0, 102.2, 89.0, 89.5),
    candle(9, 89.5, 90.0, 86.0, 87.0),
    candle(10, 87.0, 88.0, 84.0, 85.0),
    candle(11, 85.0, 86.0, 82.0, 83.0),
]
ENTRIES = [{"bar": 0, "time": CANDLES[0]["time"], "price": 100.2, "floor": 90.0,
            "floor_meta": {"source": "verify"}, "signal": {}}]

print("R64 — تحقق ما بعد التثبيت")
print("=" * 60)

# 1) الحقلان في العقد
check("1: fibo_floor_exit في الافتراضيات (=true)", EXIT_CONFIG_DEFAULTS.get("fibo_floor_exit") is True)
check("1: stop_loss_pct في الافتراضيات (=0.0)", EXIT_CONFIG_DEFAULTS.get("stop_loss_pct") == 0.0)
check("1: الحقلان في السكيما (للفرونت)", "fibo_floor_exit" in EXIT_CONFIG_SCHEMA and "stop_loss_pct" in EXIT_CONFIG_SCHEMA)

# 2) الزر معطّل + وقف 5% → stop_loss عند 95.19 (لا fib_break)
r = run_exit_backtest(CANDLES, ENTRIES, {"fibo_floor_exit": False, "stop_loss_pct": 5.0})
sl = [t for t in r["trades"] if t["exit"]["reason"] == "stop_loss"]
check("2: stop_loss وقع", len(sl) == 1, f"reasons={[t['exit']['reason'] for t in r['trades']]}")
if sl:
    check("2: السعر = 100.2×0.95", abs(sl[0]["exit"]["price"] - 95.19) < 1e-9,
          f"price={sl[0]['exit']['price']}")
check("2: صفر fib_break", all(t["exit"]["reason"] != "fib_break" for t in r["trades"]))

# 3) فجوة افتتاح تحت الوقف
cs = list(CANDLES)
cs[8] = candle(8, 90.0, 90.5, 89.5, 89.5)
r3 = run_exit_backtest(cs, ENTRIES, {"fibo_floor_exit": False, "stop_loss_pct": 5.0})
sl3 = [t for t in r3["trades"] if t["exit"]["reason"] == "stop_loss"]
check("3: تنفيذ عند الافتتاح 90.0", sl3 and abs(sl3[0]["exit"]["price"] - 90.0) < 1e-9,
      f"price={sl3[0]['exit']['price'] if sl3 else None}")

# 4) بلا وقف نهائياً
r4 = run_exit_backtest(CANDLES, ENTRIES, {"fibo_floor_exit": False, "stop_loss_pct": 0.0})
check("4: لا stop_loss ولا fib_break",
      all(t["exit"]["reason"] not in ("stop_loss", "fib_break") for t in r4["trades"]),
      f"reasons={[t['exit']['reason'] for t in r4['trades']]}")

# 5) التريلينق يُلغي الاثنين
r5 = run_exit_backtest(CANDLES, ENTRIES, {
    "use_trailing": True, "trailing_giveback_pct": 3.0,
    "fibo_floor_exit": False, "stop_loss_pct": 1.0})
check("5: الخروج الوحيد trailing_stop",
      all(t["exit"]["reason"] == "trailing_stop" for t in r5["trades"]),
      f"reasons={[t['exit']['reason'] for t in r5['trades']]}")

# 6) التطبيع
_, errs = normalize_exit_config({"fibo_floor_exit": "yes"})
check("6: رفض fibo_floor_exit نصي", any("fibo_floor_exit" in e for e in errs), f"errs={errs}")
_, errs = normalize_exit_config({"stop_loss_pct": 150})
check("6: رفض stop_loss_pct>100", any("stop_loss_pct" in e for e in errs), f"errs={errs}")
cfg_ok, errs = normalize_exit_config({"fibo_floor_exit": False, "stop_loss_pct": 4.0})
check("6: قبول الصحيح", errs == [] and cfg_ok["stop_loss_pct"] == 4.0)

# 7) الوصف العربي
d_on = describe_exit_config(normalize_exit_config({})[0])
d_off = describe_exit_config(normalize_exit_config({"fibo_floor_exit": False, "stop_loss_pct": 4.0})[0])
check("7: وصف الافتراضي (فيبو تاريخي)", "فيبوناتشي" in d_on and "لا وقف نسبي" in d_on)
check("7: وصف التعطيل (وقف نسبي 4٪)", "4٪" in d_off and "معطّل" in d_off)

# 8) عقد الجذر — وجود الحقول في صدى النتيجة
check("8: الصدى يعيد الحقلين", r["config"].get("fibo_floor_exit") is False and r["config"].get("stop_loss_pct") == 5.0)

print("=" * 60)
print(f"R64 {'OK' if FAIL == 0 else 'FAILED'} — {PASS}/{PASS + FAIL}")
sys.exit(0 if FAIL == 0 else 1)
