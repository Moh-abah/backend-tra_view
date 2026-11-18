#!/usr/bin/env python3
"""test_zone_exit_arm_unit.py — بطارية اختبارات وحدة ZONE-EXIT-ARM1.

بوابة «تفعيل شرط الخروج بعد ربح X% فوق سعر الدخول»:
  - exit_rules[].arm_after_gain_pct — None/0/«off» ⇒ معطّلة بت-بت.
  - رقم > 0 ⇒ القاعدة لا تُطلق خروجاً حتى صعود السعر X% فوق الدخول.

الطبقات:
  1) تطبيع الحقل في ExitRule (قيم شرعية + قيم معطِّلة + تهكير).
  2) بوابة _exit_rule_armed (LONG/SHORT/حدود/سياق ناقص/فشل مفتوح).
  3) تكاملي عبر محرك الباك-تست الحقيقي engine1 ببيانات اصطناعية محكومة:
     تعطيل = سلوك تاريخي، منع الخروج قبل X%، خروج بعد X%، سببية (قمة ما قبل
     الدخول لا تُفعّل)، ثبات التفعيل (Latch)، SHORT، ونموذج signal_close.

تشغيل:  python3 tests-r95/test_zone_exit_arm_unit.py  (من جذر المشروع)
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

logging.disable(logging.WARNING)

PASS = 0
FAIL = 0
FAILURES = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


# ============================================================================
# أدوات بناء البيانات الاصطناعية والتكوين
# ============================================================================

TF_MIN = 15
T0_MS = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp() * 1000)


def synth_df(bars):
    """bars: قائمة (open, high, low, close) → DataFrame بصيغة المخزن."""
    rows = []
    for i, (o, h, l, c) in enumerate(bars):
        rows.append({
            "time": T0_MS + i * TF_MIN * 60_000,
            "open": float(o), "high": float(h),
            "low": float(l), "close": float(c),
            "volume": 100.0,
        })
    return pd.DataFrame(rows)


def flat(n, price=100.0, high=None, low=None):
    """n شمعة مسطحة مع قمة/قاع قابلين للتخصيص."""
    return [(price, high if high is not None else price,
             low if low is not None else price, price) for _ in range(n)]


class SynthDataService:
    """بديل DataService يرجع DataFrame اصطناعياً ثابتاً."""

    def __init__(self, df):
        self.df = df

    async def get_historicallastvirsion(self, symbol, timeframe, market="crypto",
                                        start_date=None, end_date=None,
                                        use_cache=True, tz_offset_minutes=0):
        return self.df.copy()

    async def get_historical_last_version(self, symbol, timeframe, market="crypto",
                                          start_date=None, end_date=None,
                                          use_cache=True, tz_offset_minutes=0):
        return self.df.copy()


ALWAYS = {"type": "indicator_value", "operator": ">",
          "left_value": "price:close", "right_value": 0}


def make_strategy(arm=None, exit_cond=None, entry_side="long",
                  exit_name="always-exit"):
    entry_rule = {
        "name": "always-enter",
        "condition": ALWAYS,
        "position_side": entry_side,
        "weight": 1.0,
        "enabled": True,
    }
    exit_rule = {
        "name": exit_name,
        "condition": exit_cond or ALWAYS,
        "exit_type": "signal_exit",
        "enabled": True,
    }
    if arm is not None:
        exit_rule["arm_after_gain_pct"] = arm
    return {
        "name": "ARM-UNIT-TEST",
        "base_timeframe": "15m",
        "position_side": entry_side,
        "indicators": [],
        "entry_rules": [entry_rule],
        "exit_rules": [exit_rule],
        "risk_management": {"stop_loss_percentage": 2.0, "take_profit_percentage": 99.0},
    }


def make_config(strategy_config, fill_model="next_open",
                enable_short_selling=False):
    from app.backtest.schemas import BacktestConfig
    return BacktestConfig(
        name="ARM-UNIT",
        description="",
        start_date=pd.Timestamp("2023-12-01").to_pydatetime(),
        end_date=pd.Timestamp("2030-01-01").to_pydatetime(),
        timeframe="15m",
        timezone="UTC",
        market="crypto",
        symbols=["SYNTHUSDT"],
        initial_capital=10000.0,
        position_sizing="percentage",
        position_size_percent=100.0,
        max_positions=1,
        fill_model=fill_model,
        enable_short_selling=enable_short_selling,
        strategy_config=strategy_config,
    )


def run_engine(df, strategy_config, **kw):
    """تشغيل محرك الباك-تست الحقيقي على البيانات الاصطناعية."""
    from app.backtest.engine1 import BacktestEngine
    engine = BacktestEngine(SynthDataService(df))
    cfg = make_config(strategy_config, **kw)
    result = asyncio.run(engine.run_backtest(cfg))
    return [t.__dict__ for t in (getattr(result, "trades", []) or [])]


def bar_time(i):
    return pd.Timestamp(T0_MS + i * TF_MIN * 60_000, unit="ms", tz="UTC")


# ============================================================================
# 1) تطبيع الحقل في ExitRule
# ============================================================================

def test_schema_normalization():
    print("\n[1] تطبيع arm_after_gain_pct في ExitRule")
    from app.services.strategy.schemas import ExitRule

    disabled_values = [None, 0, 0.0, -5, -0.1, "off", "OFF", "false", "False",
                       "none", "NONE", "", " ", "-", "disabled", "no", True,
                       False, "abc", "نان", "!!!", float("nan"), "nan", "inf",
                       float("inf"), [1, 2], {}, {"x": 1}, "1.2.3"]
    for v in disabled_values:
        r = ExitRule(name="t", condition=ALWAYS, exit_type="signal_exit",
                     arm_after_gain_pct=v)
        check(f"معطِّل: {v!r} → None", r.arm_after_gain_pct is None,
              f"got {r.arm_after_gain_pct!r}")

    enabled_values = [(5, 5.0), (10, 10.0), (2.5, 2.5), ("7.5", 7.5),
                      (" 12 ", 12.0), ("040", 40.0), (100, 100.0),
                      (1000.5, 1000.5), ("1e1", 10.0)]
    for raw, exp in enabled_values:
        r = ExitRule(name="t", condition=ALWAYS, exit_type="signal_exit",
                     arm_after_gain_pct=raw)
        check(f"مفعِّل: {raw!r} → {exp}", r.arm_after_gain_pct == exp,
              f"got {r.arm_after_gain_pct!r}")

    r = ExitRule(name="t", condition=ALWAYS, exit_type="signal_exit")
    check("غياب الحقل كلياً → None (توافق خلفي)", r.arm_after_gain_pct is None)

    # الحقل يمر عبر StrategyConfig الكامل (مسار الباك-تست الحقيقي)
    from app.services.strategy.schemas import StrategyConfig
    sc = StrategyConfig(**make_strategy(arm=10))
    check("المرور عبر StrategyConfig: 10 → 10.0",
          sc.exit_rules[0].arm_after_gain_pct == 10.0)
    sc2 = StrategyConfig(**make_strategy(arm="off"))
    check("المرور عبر StrategyConfig: «off» → None",
          sc2.exit_rules[0].arm_after_gain_pct is None)


# ============================================================================
# 2) بوابة _exit_rule_armed (وحدة صرفة)
# ============================================================================

def test_gate_unit():
    print("\n[2] بوابة _exit_rule_armed — وحدة صرفة")
    from app.services.strategy.schemas import ExitRule
    from app.services.strategy.strategy_engine1 import StrategyEngine

    def armed(pct, ctx):
        rule = ExitRule(name="t", condition=ALWAYS, exit_type="signal_exit",
                        arm_after_gain_pct=pct)
        return StrategyEngine._exit_rule_armed(rule, ctx)

    check("معطّلة (None) بدون سياق", armed(None, None) is True)
    check("معطّلة (0) مع سياق", armed(0, {"entry_price": 100}) is True)
    check("مفعّلة + لا سياق ⇒ توافق خلفي (فشل مفتوح)", armed(10, None) is True)
    check("مفعّلة + سياق فارغ ⇒ توافق خلفي", armed(10, {}) is True)

    long_ctx = lambda hi: {"entry_price": 100.0, "direction": "LONG",
                           "peak_high_since_entry": hi,
                           "bottom_low_since_entry": 99.0}
    check("LONG: قمة 109 < 110 ⇒ غير مفعّلة", armed(10, long_ctx(109.0)) is False)
    check("LONG: قمة 110 (الحد بالضبط) ⇒ مفعّلة", armed(10, long_ctx(110.0)) is True)
    check("LONG: قمة 111 ⇒ مفعّلة", armed(10, long_ctx(111.0)) is True)
    check("LONG: قمة 50 (هابطة!) ⇒ غير مفعّلة", armed(10, long_ctx(50.0)) is False)
    check("LONG pct=100: قمة 199 ⇒ غير مفعّلة (يحتاج 200)",
          armed(100, long_ctx(199.0)) is False)
    check("LONG pct=100: قمة 200 ⇒ مفعّلة", armed(100, long_ctx(200.0)) is True)

    short_ctx = lambda lo: {"entry_price": 100.0, "direction": "SHORT",
                            "peak_high_since_entry": 120.0,
                            "bottom_low_since_entry": lo}
    check("SHORT: قاع 90.5 > 90 ⇒ غير مفعّلة", armed(10, short_ctx(90.5)) is False)
    check("SHORT: قاع 90 (الحد) ⇒ مفعّلة", armed(10, short_ctx(90.0)) is True)
    check("SHORT: قاع 89 ⇒ مفعّلة", armed(10, short_ctx(89.0)) is True)
    check("SHORT: قاع 120 (صاعدة!) ⇒ غير مفعّلة", armed(10, short_ctx(120.0)) is False)

    # سياق ناقص/تالف ⇒ فشل مفتوح (لا كسر للنظام)
    check("سياق بلا قمة ⇒ مفعّلة (فشل مفتوح)",
          armed(10, {"entry_price": 100.0, "direction": "LONG"}) is True)
    check("سياق بلا دخول ⇒ مفعّلة (فشل مفتوح)",
          armed(10, {"direction": "LONG", "peak_high_since_entry": 500.0}) is True)
    check("دخول نصي تالف ⇒ مفعّلة (فشل مفتوح)",
          armed(10, {"entry_price": "abc", "direction": "LONG",
                     "peak_high_since_entry": 500.0}) is True)
    check("دخول صفري ⇒ مفعّلة (فشل مفتوح)",
          armed(10, {"entry_price": 0, "direction": "LONG",
                     "peak_high_since_entry": 500.0}) is True)
    check("اتجاه صغير الحروف «long» يُفهم",
          armed(10, {"entry_price": 100.0, "direction": "long",
                     "peak_high_since_entry": 50.0}) is False)
    check("اتجاه مجهول يُعامل LONG",
          armed(10, {"entry_price": 100.0, "direction": "SIDEWAYS",
                     "peak_high_since_entry": 111.0}) is True)

    # Latch على مستوى الأطراف التراكمية: القمة التراكمية لا تنقص أبداً
    check("Latch: القمة التراكمية 111 تبقى مفعِّلة رغم سياق لاحق أدنى",
          armed(10, long_ctx(111.0)) is True)


# ============================================================================
# 3) تكاملي عبر engine1 — بيانات اصطناعية محكومة
# ============================================================================

def test_engine_integration():
    print("\n[3] تكاملي عبر محرك الباك-تست الحقيقي (engine1)")
    n = 80  # ≥ 50 شرط المحرك

    # --- أ) البوابة معطّلة: الخروج الفوري كما هو تاريخياً ---
    bars = flat(n, 100.0)
    trades = run_engine(synth_df(bars), make_strategy(arm=None))
    t0 = trades[0]
    check("أ) معطّلة: صفقات موجودة", len(trades) > 0)
    check("أ) معطّلة: أول صفقة تدخل عند افتتاح الشمعة 1",
          abs((t0["entry_time"] - bar_time(1)).total_seconds()) < 1,
          f"entry={t0['entry_time']}")
    check("أ) معطّلة: الخروج عند افتتاح الشمعة 2 (سلوك تاريخي)",
          abs((t0["exit_time"] - bar_time(2)).total_seconds()) < 1,
          f"exit={t0['exit_time']}")
    check("أ) معطّلة: سبب الخروج من القاعدة",
          "always-exit" in str(t0["exit_reason"]), f"reason={t0['exit_reason']}")
    check("أ) معطّلة: arm=None في الحمولة لا يغيّر شيئاً (نمط متكرر)",
          len(trades) == n // 2, f"n_trades={len(trades)}")

    # --- ب) البوابة «صفر» رقمياً = معطّلة ---
    trades_b = run_engine(synth_df(bars), make_strategy(arm=0))
    check("ب) arm=0 ⇒ نفس عدد الصفقات التاريخي", len(trades_b) == len(trades),
          f"{len(trades_b)} vs {len(trades)}")
    trades_b2 = run_engine(synth_df(bars), make_strategy(arm="off"))
    check("ب) arm=«off» ⇒ نفس عدد الصفقات التاريخي",
          len(trades_b2) == len(trades))

    # --- ج) مفعّلة والسعر لا يصل X% ⇒ لا خروج من القاعدة إطلاقاً ---
    bars_g = flat(n, 100.0, high=109.0)  # قمم 9% فقط
    trades_g = run_engine(synth_df(bars_g), make_strategy(arm=10))
    check("ج) صفقة واحدة فقط (لا دخول جديد بعد الاحتفاظ)", len(trades_g) == 1,
          f"n={len(trades_g)}")
    check("ج) الخروج «End of Data» لا من القاعدة",
          str(trades_g[0]["exit_reason"]) == "End of Data",
          f"reason={trades_g[0]['exit_reason']}")
    check("ج) الاحتفاظ حتى آخر شمعة",
          abs((trades_g[0]["exit_time"] - bar_time(n - 1)).total_seconds()) < 1)

    # --- د) مفعّلة والسعر يصل X% عند الشمعة 10 ⇒ خروج عند افتتاح 11 ---
    bars_a = (flat(10, 100.0) + [(100.0, 111.0, 100.0, 105.0)]
              + flat(n - 11, 105.0, high=105.0))
    trades_a = run_engine(synth_df(bars_a), make_strategy(arm=10))
    t = trades_a[0]
    check("د) الخروج عند افتتاح الشمعة 11 (بعد التفعيل عند 10)",
          abs((t["exit_time"] - bar_time(11)).total_seconds()) < 1,
          f"exit={t['exit_time']}")
    check("د) سبب الخروج من القاعدة بعد التفعيل",
          "always-exit" in str(t["exit_reason"]), f"reason={t['exit_reason']}")
    check("د) سعر الخروج = افتتاح الشمعة 11",
          abs(t["exit_price"] - 105.0) < 1e-9, f"px={t['exit_price']}")

    # --- هـ) سببية: قمة ما قبل الدخول لا تُفعّل البوابة ---
    bars_c = ([(100.0, 111.0, 100.0, 100.0)]  # شمعة 0: قمة قبل الدخول
              + flat(n - 1, 100.0, high=109.0))
    trades_c = run_engine(synth_df(bars_c), make_strategy(arm=10))
    check("هـ) قمة ما قبل الدخول لا تُفعّل: صفقة واحدة",
          len(trades_c) == 1, f"n={len(trades_c)}")
    check("هـ) الخروج End of Data (البوابة بقيت مغلقة)",
          str(trades_c[0]["exit_reason"]) == "End of Data",
          f"reason={trades_c[0]['exit_reason']}")

    # --- و) Latch: التفعيل يبقى رغم الهبوط اللاحق (شرط يطلق لاحقاً) ---
    exit_late = {"type": "indicator_value", "operator": "<",
                 "left_value": "price:close", "right_value": 90}
    bars_l = (flat(20, 100.0) + [(100.0, 111.0, 100.0, 100.0)]  # شمعة 20: تفعيل
              + flat(9, 100.0) + flat(1, 85.0, high=85.0)  # شمعة 30: شرط الخروج
              + flat(n - 31, 85.0, high=85.0))
    trades_l = run_engine(synth_df(bars_l),
                          make_strategy(arm=10, exit_cond=exit_late,
                                        exit_name="late-exit"))
    tl = trades_l[0]
    check("و) Latch: الخروج من القاعدة بعد الهبوط لما بعد التفعيل",
          "late-exit" in str(tl["exit_reason"]), f"reason={tl['exit_reason']}")
    check("و) Latch: الخروج عند افتتاح الشمعة 31",
          abs((tl["exit_time"] - bar_time(31)).total_seconds()) < 1,
          f"exit={tl['exit_time']}")
    # نفس السيناريو بلا صعود ⇒ البوابة مغلقة والشرط لا يطلق
    bars_l2 = (flat(30, 100.0, high=109.0) + flat(1, 85.0, high=85.0)
               + flat(n - 31, 85.0, high=85.0))
    trades_l2 = run_engine(synth_df(bars_l2),
                           make_strategy(arm=10, exit_cond=exit_late,
                                         exit_name="late-exit"))
    check("و) بلا صعود: البوابة مغلقة والشرط لا يطلق (End of Data)",
          str(trades_l2[0]["exit_reason"]) == "End of Data",
          f"reason={trades_l2[0]['exit_reason']}")

    # --- ز) SHORT: التفعيل بهبوط X% تحت الدخول ---
    bars_s = (flat(10, 100.0) + [(100.0, 100.0, 89.0, 95.0)]
              + flat(n - 11, 95.0, high=95.0))
    trades_s = run_engine(synth_df(bars_s),
                          make_strategy(arm=10, entry_side="short"),
                          enable_short_selling=True)
    ts = trades_s[0]
    check("ز) SHORT: الصفقة قائمة", len(trades_s) >= 1)
    check("ز) SHORT: الخروج من القاعدة بعد هبوط 10%",
          "always-exit" in str(ts["exit_reason"]), f"reason={ts['exit_reason']}")
    check("ز) SHORT: الخروج عند افتتاح الشمعة 11",
          abs((ts["exit_time"] - bar_time(11)).total_seconds()) < 1,
          f"exit={ts['exit_time']}")
    # بلا هبوط كافٍ ⇒ لا تفعيل
    bars_s2 = flat(n, 100.0, low=90.5)
    trades_s2 = run_engine(synth_df(bars_s2),
                           make_strategy(arm=10, entry_side="short"),
                           enable_short_selling=True)
    check("ز) SHORT بلا هبوط كافٍ: End of Data",
          str(trades_s2[0]["exit_reason"]) == "End of Data",
          f"reason={trades_s2[0]['exit_reason']}")

    # --- ح) نموذج signal_close: تنفيذ فوري عند إغلاق شمعة الإشارة ---
    bars_sc = (flat(5, 100.0) + [(100.0, 111.0, 100.0, 107.0)]
               + flat(n - 6, 107.0, high=107.0))
    trades_sc = run_engine(synth_df(bars_sc), make_strategy(arm=10),
                           fill_model="signal_close")
    tsc = trades_sc[0]
    check("ح) signal_close: الخروج عند إغلاق شمعة التفعيل نفسها",
          abs((tsc["exit_time"] - bar_time(5)).total_seconds()) < 1,
          f"exit={tsc['exit_time']}")
    check("ح) signal_close: سعر الخروج = إغلاق الشمعة 5",
          abs(tsc["exit_price"] - 107.0) < 1e-9, f"px={tsc['exit_price']}")
    # signal_close + قمة شمعة الدخول نفسها سبقت التنفيذ ⇒ لا تُحتسب
    bars_sc2 = ([(100.0, 130.0, 100.0, 100.0)]  # شمعة 0: قمة عالية قبل التنفيذ
                + flat(5, 100.0, high=109.0)
                + flat(n - 6, 100.0, high=109.0))
    trades_sc2 = run_engine(synth_df(bars_sc2), make_strategy(arm=10),
                            fill_model="signal_close")
    check("ح) signal_close: قمة شمعة الدخول (قبل التنفيذ) لا تُفعّل",
          str(trades_sc2[0]["exit_reason"]) == "End of Data",
          f"reason={trades_sc2[0]['exit_reason']}")


# ============================================================================
# 4) تهكير القيمة عبر مسار المحرك الكامل
# ============================================================================

def test_fuzz_engine():
    print("\n[4] تهكير القيمة عبر المسار الكامل (engine1)")
    n = 60
    bars = flat(n, 100.0, high=115.0)  # صعود كافٍ متاح
    fuzz_disabled = ["off", "false", "none", "", "-", 0, -3, True, False,
                     "nan", "abc", [5], {"a": 1}]
    base = run_engine(synth_df(bars), make_strategy(arm=None))
    for v in fuzz_disabled:
        trades = run_engine(synth_df(bars), make_strategy(arm=v))
        same = (len(trades) == len(base)
                and str(trades[0]["exit_reason"]) == str(base[0]["exit_reason"]))
        check(f"تهكير {v!r} ⇒ معطّل (سلوك تاريخي)", same,
              f"n={len(trades)} first={trades[0]['exit_reason'] if trades else '؟'}")

    for v in [5, 10, 15]:
        trades = run_engine(synth_df(bars), make_strategy(arm=v))
        armed_exit = any("always-exit" in str(t["exit_reason"]) for t in trades)
        check(f"مفعّلة {v}% مع صعود 15% ⇒ يوجد خروج من القاعدة", armed_exit)


# ============================================================================
# 5) بصمة الأداء: لا تباطؤ يُذكر عند التعطيل
# ============================================================================

def test_perf_no_regression_disabled():
    print("\n[5] أداء التعطيل (تدخين سرعة)")
    n = 400
    bars = flat(n, 100.0)
    t0 = time.perf_counter()
    run_engine(synth_df(bars), make_strategy(arm=None))
    t_off = time.perf_counter() - t0
    t0 = time.perf_counter()
    run_engine(synth_df(bars), make_strategy(arm=10))
    t_on = time.perf_counter() - t0
    check(f"التعطيل سريع (<5s): {t_off:.2f}s", t_off < 5.0)
    check(f"التفعيل لا يبطّئ بشكل ملموس: {t_on:.2f}s vs {t_off:.2f}s",
          t_on < t_off * 3.0 + 2.0)


if __name__ == "__main__":
    t_start = time.perf_counter()
    test_schema_normalization()
    test_gate_unit()
    test_engine_integration()
    test_fuzz_engine()
    test_perf_no_regression_disabled()
    elapsed = time.perf_counter() - t_start
    print("\n" + "=" * 64)
    print(f"النتيجة: {PASS} نجح / {FAIL} فشل  (خلال {elapsed:.1f}s)")
    if FAILURES:
        print("الإخفاقات:")
        for name, detail in FAILURES:
            print(f"  - {name}: {detail}")
        sys.exit(1)
    print("ZONE-EXIT-ARM1: كل اختبارات الوحدة نجحت ✓")
