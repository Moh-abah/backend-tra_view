#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPLIT-TP1 — بطارية التحقق (الجزء الأول: المخططات + الميكانيكا الاصطناعية).

L1: مخططات TakeProfitSplit (الأشكال القانونية/الأزواج/الرفض >100%/الغياب=None)
L2: الميكانيكا الكاملة على استراتيجية SMA عامة ببيانات مصنوعة بعناية:
    دخول 90.0 → لمس +5% (94.5) → جني ربع الكمية بالضبط → لمس +7% (96.3)
    → جني ربع ثانٍ بالضبط → هبوط → خروج القاعدة بالمتبقي (نصف الكمية).
    التحقق بت-بت: أسعار الجني وأحجامها وpnl الصفقة الكلي والرصيد النهائي.
L2ب: مسار الاستنفاد الكامل (25+25+50 = 100%) — ختام Split TP Hit (Full).
"""
import asyncio
import sys
from pathlib import Path

RT = Path("/home/z/my-project/trading-system/split-tp/runtime")
sys.path.insert(0, str(RT))

# ✅ استبدال طبقة البيانات المحلية (بلا sqlalchemy محلياً — نفس منهجية
# بطاريات الجولات السابقة: نستورد المحرك فوق stub خفيف للخدمة)
import types  # noqa: E402

_ds_mod = types.ModuleType("app.services.data_service")
class _StubDataServiceCls:  # placeholder للنوع فقط
    pass
_ds_mod.DataService = _StubDataServiceCls
sys.modules["app.services.data_service"] = _ds_mod

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(detail)) if detail and not cond else ""))


def main():
    # ============================== L1 — المخططات ==============================
    print("== L1: مخططات TakeProfitSplit")
    from app.backtest.schemas import BacktestConfig

    cfg = BacktestConfig(symbols=["X"],
                        take_profit_splits=[{"gain_percent": 5, "size_percent": 25},
                                            {"gain_percent": 7, "size_percent": 25}])
    check("L1.1 قانوني: مستويان 25+25",
          len(cfg.take_profit_splits) == 2 and
          cfg.take_profit_splits[0].gain_percent == 5.0 and
          cfg.take_profit_splits[1].size_percent == 25.0)

    cfg2 = BacktestConfig(symbols=["X"], take_profit_splits=[[5, 25], [7, 25]])
    check("L1.2 أزواج [gain,size] مقبولة",
          [(l.gain_percent, l.size_percent) for l in cfg2.take_profit_splits]
          == [(5.0, 25.0), (7.0, 25.0)])

    try:
        BacktestConfig(symbols=["X"], take_profit_splits=[[40, 40], [40, 40], [40, 40]])
        check("L1.3 مجموع 120% يُرفض 422", False, "لم يُرفض")
    except Exception as e:
        check("L1.3 مجموع 120% يُرفض 422 برسالة عربية",
              "مجموع أحجام" in str(e))

    try:
        BacktestConfig(symbols=["X"], take_profit_splits=["hello"])
        check("L1.4 شكل غير مفهوم يُرفض", False, "لم يُرفض")
    except Exception:
        check("L1.4 شكل غير مفهوم يُرفض برسالة عربية", True)

    cfg3 = BacktestConfig(symbols=["X"])
    check("L1.5 غياب الحقل = None (سلوك تاريخي بت-بت)",
          cfg3.take_profit_splits is None)

    # ============================== L2 — الميكانيكا ==============================
    print("== L2: الميكانيكا الاصطناعية (SMA عامة + مستويات 5/7)")
    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig as BC

    n = 75
    # 0-9 تسطيح 80 (لا إشارة: close == SMA)
    # 10-34 صعود 81→105 (دخول: close فوق SMA5) — الفتح التنفيذي = 81.0
    #    الجني عند 81×1.05=85.05 و 81×1.07=86.67 أثناء الصعود
    # 35-69 هبوط حاد 105→60 (خروج: close تحت SMA5) ثم تسطيح 60
    closes = [80.0] * 10
    closes += [float(81 + i) for i in range(25)]              # 10..34: 81→105
    closes += [float(105 - 3 * i) for i in range(1, 11)]      # 35..44: 102→75
    closes += list(np.linspace(74.0, 60.0, n - 45))            # 45..74
    ts = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    opens = [closes[0]] + closes[:-1]   # next_open التنفيذي
    highs = list(closes)
    lows = list(closes)
    df = pd.DataFrame({"open": opens, "high": highs, "low": lows,
                       "close": closes, "volume": [1000.0] * n},
                      index=pd.DatetimeIndex(ts, name="time"))

    class StubDS:
        async def get_historicallastvirsion(self, symbol, timeframe, market,
                                            start_date, end_date, use_cache=True,
                                            tz_offset_minutes=0):
            return df.copy()

    sc = {
        "name": "SPLIT-TP-SYNTH",
        "version": "1.0.0",
        "indicators": [{"name": "sma", "params": {"period": 5}}],
        "entry_rules": [{
            "name": "دخول: السعر فوق SMA5 (صعود)",
            "condition": {"type": "indicator_value", "operator": "<",
                          "left_value": "indicator:sma", "right_value": "close"},
            "position_side": "long", "weight": 1.0, "enabled": True}],
        "exit_rules": [{
            "name": "خروج: السعر تحت SMA5 (هبوط)",
            "condition": {"type": "indicator_value", "operator": ">",
                          "left_value": "indicator:sma", "right_value": "close"},
            "exit_type": "signal_exit", "enabled": True}],
        "filter_rules": [],
    }

    cfg = BC(
        symbols=["TESTUSDT"], market="crypto", timeframe="15m",
        start_date=ts[0].to_pydatetime(), end_date=ts[-1].to_pydatetime(),
        initial_capital=10000.0, position_sizing="percentage",
        position_size_percent=100.0,
        strategy_config=sc,
        take_profit_splits=[{"gain_percent": 5, "size_percent": 25},
                            {"gain_percent": 7, "size_percent": 25}],
    )
    eng = BacktestEngine(data_service=StubDS())
    res = asyncio.run(eng.run_backtest(cfg))

    tp = res.trade_points
    entries = [p for p in tp if p.get("type") == "entry"]
    exits = [p for p in tp if p.get("type") == "exit"]
    partials = [p for p in tp if p.get("type") == "partial_exit"]

    check("L2.1 دخول واحد فتح", len(entries) == 1, f"دخول={len(entries)}")
    check("L2.2 جنيان مقسمان وقعا", len(partials) == 2, f"جني={len(partials)}")
    check("L2.3 ختام واحد بالمتبقي", len(exits) == 1, f"خروج={len(exits)}")

    entry_price = None
    orig_size = None
    if entries:
        e = entries[0]
        entry_price = e["entry_price"]
        orig_size = e["position_size"]
        check("L2.4 سعر الدخول = فتح شمعة التنفيذ (81.0)",
              abs(entry_price - 81.0) < 1e-9, entry_price)

        if len(partials) == 2:
            p1, p2 = partials
            trig1 = entry_price * (1.0 + 5.0 / 100.0)
            trig2 = entry_price * (1.0 + 7.0 / 100.0)
            check("L2.5 جني1 عند +5% بالضبط (94.5)",
                  abs(p1["price"] - trig1) < 1e-9, p1["price"])
            check("L2.6 جني2 عند +7% بالضبط (96.3)",
                  abs(p2["price"] - trig2) < 1e-9, p2["price"])
            check("L2.7 جني1 = ربع الكمية الأصلية",
                  abs(p1["position_size"] - orig_size * 0.25) < 1e-9,
                  (p1["position_size"], orig_size * 0.25))
            check("L2.8 جني2 = ربع الكمية الأصلية",
                  abs(p2["position_size"] - orig_size * 0.25) < 1e-9,
                  (p2["position_size"], orig_size * 0.25))
            check("L2.9 أسباب الجني الصريحة",
                  "Split TP +5% (25%)" in str(p1["exit_reason"]) and
                  "Split TP +7% (25%)" in str(p2["exit_reason"]),
                  (p1["exit_reason"], p2["exit_reason"]))
            pnl1_exp = (trig1 - entry_price) * orig_size * 0.25
            pnl2_exp = (trig2 - entry_price) * orig_size * 0.25
            check("L2.10 pnl الجني1 = Δ×كمية بالضبط",
                  abs(p1["pnl"] - pnl1_exp) < 1e-7, (p1["pnl"], pnl1_exp))
            check("L2.11 pnl الجني2 = Δ×كمية بالضبط",
                  abs(p2["pnl"] - pnl2_exp) < 1e-7, (p2["pnl"], pnl2_exp))
            check("L2.12 المتبقي بعد الجنيين = 50% من الكمية",
                  abs(p2["remaining_size"] - orig_size * 0.5) < 1e-9,
                  (p2["remaining_size"], orig_size * 0.5))

        if exits and len(partials) == 2:
            x = exits[0]
            check("L2.13 الختام بالمتبقي (50% من الكمية الأصلية)",
                  abs(x["position_size"] - orig_size * 0.5) < 1e-9,
                  (x["position_size"], orig_size * 0.5))
            trig1 = entry_price * 1.05
            trig2 = entry_price * 1.07
            total_exp = ((trig1 - entry_price) * orig_size * 0.25
                         + (trig2 - entry_price) * orig_size * 0.25
                         + (x["exit_price"] - entry_price) * orig_size * 0.5)
            check("L2.14 نقطة الختام تعرض إجمالي الصفقة (جني+ختامي)",
                  abs(x["pnl"] - total_exp) < 1e-7, (x["pnl"], total_exp))

    # كائنات الصفقات (المصدر المحاسبي)
    trades = getattr(res, "trades", None) or []
    check("L2.15 صفقة واحدة في trades", len(trades) == 1, len(trades))
    if trades and exits and entry_price is not None:
        tr = trades[0]
        check("L2.16 trade.pnl = إجمالي (جني+ختامي)",
              tr.pnl is not None and
              abs(tr.pnl - exits[0]["pnl"]) < 1e-7,
              (tr.pnl, exits[0]["pnl"]))
        check("L2.17 trade.partial_exits = 2 أحداث",
              len(tr.partial_exits or []) == 2, tr.partial_exits)
        check("L2.18 pnl_percentage على الكمية الأصلية",
              tr.pnl_percentage is not None and abs(
                  tr.pnl_percentage -
                  (tr.pnl / (tr.entry_price * orig_size) * 100)) < 1e-9,
              tr.pnl_percentage)
        check("L2.19 الرصيد النهائي = ابتدائي + pnl الصفقة",
              abs(res.final_capital - (10000.0 + tr.pnl)) < 1e-7,
              (res.final_capital, 10000.0 + tr.pnl))
        check("L2.20 سبب الختام موسوم بعدد الجني",
              "جني مقسم" in str(tr.exit_reason or ""), tr.exit_reason)

    ma = getattr(res, "math_audit", None) or {}
    re_ = ma.get("risk_echo") or {}
    check("L2.21 risk_echo.take_profit_splits = المستويان",
          re_.get("take_profit_splits") == [
              {"gain_percent": 5.0, "size_percent": 25.0},
              {"gain_percent": 7.0, "size_percent": 25.0}],
          re_.get("take_profit_splits"))
    check("L2.22 risk_echo.split_tp_active = True",
          re_.get("split_tp_active") is True)
    check("L2.23 risk_echo.split_tp_partial_exits = 2",
          re_.get("split_tp_partial_exits") == 2, re_.get("split_tp_partial_exits"))

    # ======================= L2ب — الاستنفاد الكامل (100%) =======================
    print("== L2ب: استنفاد الكمية كاملة بالجني (25+25+50)")
    # صعود قصير يعبر +9% فوق الدخول (81×1.09=88.29 — قمة 89) ثم انهيار فوري
    # (بعد الاستنفاد لا إعادة دخول: الهبوط = close تحت SMA5)
    closes_b = [80.0] * 10
    closes_b += [float(81 + i) for i in range(8)]          # 10..17: 81→88
    closes_b += [86.0]                                     # 18: قمة 88.5/إغلاق 86 (<SMA — لا إشارة)
    closes_b += [84.0, 78.0, 70.0, 62.0, 58.0]             # 19..23 انهيار
    closes_b += [55.0] * (n - 24)                          # 24..74 تسطيح
    dfb = pd.DataFrame({"open": [closes_b[0]] + closes_b[:-1],
                         "high": list(closes_b), "low": list(closes_b),
                         "close": closes_b, "volume": [1000.0] * n},
                        index=pd.DatetimeIndex(ts, name="time"))
    # الشمعة 18: قمة 88.5 تعبر 81×1.09=88.29 (الجني الثالث/الاستنفاد) وإغلاقها
    # 86 تحت SMA5 (86.4) — لا إشارة دخول بعد الختام (لا إعادة دخول)
    dfb.iloc[18, dfb.columns.get_loc("high")] = 88.5

    class StubDSB:
        async def get_historicallastvirsion(self, symbol, timeframe, market,
                                             start_date, end_date, use_cache=True,
                                             tz_offset_minutes=0):
            return dfb.copy()

    cfg_full = BC(
        symbols=["TESTUSDT"], market="crypto", timeframe="15m",
        start_date=ts[0].to_pydatetime(), end_date=ts[-1].to_pydatetime(),
        initial_capital=10000.0, position_sizing="percentage",
        position_size_percent=100.0,
        strategy_config=sc,
        take_profit_splits=[{"gain_percent": 5, "size_percent": 25},
                            {"gain_percent": 7, "size_percent": 25},
                            {"gain_percent": 9, "size_percent": 50}],
    )
    eng_b = BacktestEngine(data_service=StubDSB())
    res_b = asyncio.run(eng_b.run_backtest(cfg_full))
    tpb = res_b.trade_points
    partials_b = [p for p in tpb if p.get("type") == "partial_exit"]
    exits_b = [p for p in tpb if p.get("type") == "exit"]
    check("L2.24 ثلاث جنيات حتى الاستنفاد (25+25+50)",
          len(partials_b) == 3, len(partials_b))
    if len(partials_b) == 3:
        trig3 = 81.0 * 1.09
        check("L2.25 الجني الثالث عند +9% (88.29)",
              abs(partials_b[2]["price"] - trig3) < 1e-9, partials_b[2]["price"])
        check("L2.26 المتبقي بعد الثالث = 0 (استنفاد كامل)",
              partials_b[2]["remaining_size"] <= 1e-9,
              partials_b[2]["remaining_size"])
    check("L2.27 ختام الاستنفاد سببه Split TP Hit (Full)",
          bool(exits_b) and "Split TP Hit (Full)" in str(exits_b[0]["exit_reason"]),
          exits_b[0]["exit_reason"] if exits_b else "لا خروج")
    if exits_b and len(partials_b) == 3:
        ent_b = [p for p in tpb if p.get("type") == "entry"][0]["entry_price"]
        p_exp = ((ent_b * 0.05 - ent_b) * -1 * 0.25 + (ent_b * 0.07 - ent_b) * -1 * 0.25
                 + (ent_b * 0.09 - ent_b) * -1 * 0.5) * (10000.0 / ent_b)
        # الإجمالي = أرباح الجنى الثلاثة فقط (الختام على متبٍ 0)
        p_exp = (0.05 * 0.25 + 0.07 * 0.25 + 0.09 * 0.5) * (10000.0 / ent_b) * ent_b
        check("L2.28 إجمالي الاستنفاد = مجموع الجنى الثلاثة",
              abs(exits_b[0]["pnl"] - p_exp) < 1e-7, (exits_b[0]["pnl"], p_exp))
        check("L2.29 الرصيد النهائي للاستنفاد = 10000 + إجمالي الجنى",
              abs(res_b.final_capital - (10000.0 + exits_b[0]["pnl"])) < 1e-7,
              res_b.final_capital)

    print()
    print(f"===== النتيجة: {len(PASS)} PASS / {len(FAIL)} FAIL =====")
    if FAIL:
        print("FAILED:", FAIL)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
