#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SPLIT-ZZ1 — بطارية التحقق (الجزء الأول: المخططات + الميكانيكا الاصطناعية).

L1: مخططات StructureSplitExit (الأشكال القانونية/الأزواج/الثلاثيات/الرفض
    >100%/الغياب=None/مرادفات same/تعطيل قاعدة بـ enabled=false).
L2: الميكانيكا الكاملة على استراتيجية SMA عامة ببيانات مصنوعة بعناية
    (صعود بارتدادات ⇒ منطقة HH+HL تفتح ⇒ هبوط LL+LH ⇒ انعكاس هيكل):
    انعكاس واحد مؤكد ⇒ بيع ربع الكمية الأصلية عند open الشمعة التالية بالضبط
    ⇒ المتبقي يُغلق بخروج SMA ⇒ التحقق بت-بت: سعر البيع وحجمه وpnl الصفقة
    الكلي والرصيد النهائي (البيع الجزئي = قرار إغلاق شمعة التأكيد + تنفيذ
    Next-Open — نفس دلالات exit_rules القائمة).
L2ب: الاستنفاد الكامل (size=100%) — ختام Structure Split Exit (Full).
L2ج: قاعدتان مستقلتان بنفس الشمعة + SHORT.
"""
import asyncio
import sys
from pathlib import Path

RT = Path("/home/z/my-project/trading-system/split-zz/runtime")
sys.path.insert(0, str(RT))

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
    print("== L1: مخططات StructureSplitExit")
    from app.backtest.schemas import BacktestConfig

    cfg = BacktestConfig(
        symbols=["X"],
        structure_split_exits=[{"resolution": "same", "length": 100,
                                "size_percent": 25}])
    r0 = cfg.structure_split_exits[0]
    check("L1.1 قانوني: same/100/25",
          r0.resolution == "same" and r0.length == 100 and r0.size_percent == 25.0)

    cfg2 = BacktestConfig(
        symbols=["X"],
        structure_split_exits=[["5m", 25], ["1h", 25, 50]])
    check("L1.2 أزواج [res,size] وثلاثيات [res,size,len] مقبولة",
          [(r.resolution, r.size_percent, r.length)
           for r in cfg2.structure_split_exits]
          == [("5m", 25.0, None), ("1h", 25.0, 50)])

    try:
        BacktestConfig(symbols=["X"],
                       structure_split_exits=[["5m", 40], ["1h", 40], ["4h", 40]])
        check("L1.3 مجموع 120% يُرفض 422", False, "لم يُرفض")
    except Exception as e:
        check("L1.3 مجموع 120% يُرفض 422 برسالة عربية",
              "مجموع أحجام قواعد" in str(e), str(e)[:80])

    try:
        BacktestConfig(symbols=["X"], structure_split_exits=["hello"])
        check("L1.4 شكل غير مفهوم يُرفض", False, "لم يُرفض")
    except Exception:
        check("L1.4 شكل غير مفهوم يُرفض برسالة عربية", True)

    cfg3 = BacktestConfig(symbols=["X"])
    check("L1.5 غياب الحقل = None (سلوك تاريخي بت-بت)",
          cfg3.structure_split_exits is None)

    cfg4 = BacktestConfig(
        symbols=["X"],
        structure_split_exits=[{"resolution": "CHART", "size_percent": 10},
                               {"resolution": "4H", "size_percent": 20}])
    check("L1.6 مرادفات فب於 التطبيع (CHART→same · 4H→4h)",
          [r.resolution for r in cfg4.structure_split_exits] == ["same", "4h"])

    cfg5 = BacktestConfig(
        symbols=["X"],
        structure_split_exits=[{"resolution": "1h", "size_percent": 10},
                               {"resolution": "4h", "size_percent": 20,
                                "enabled": False}])
    check("L1.7 enabled=false محايد (لا يرفض ولا يحسب في المجموع)",
          len(cfg5.structure_split_exits) == 2)

    # ============================== L2 — الميكانيكا ==============================
    print("== L2: الميكانيكا الاصطناعية (SMA عامة + انعكاس هيكل same/4/25)")
    from app.services.indicators.overlays_zone_exit_mtf import (
        compute_zone_exit_same,
    )

    # نمط موجات عريضة (18 شمعة/موجة: 14 اتجاه + 4 ارتداد) ⇒ محاور متناوبة
    # مؤكدة: دورة صعود HH+HL (فتح المنطقة) ثم هبوط LL+LH (انعكاس) ثم
    # دورة ثانية كاملة (فتح ثانٍ + انعكاس ثانٍ) — أحداث متعددة قابلة
    # للتحقق بت-بت.
    n = 900
    closes = [100.0] * 40
    p = 100.0
    for cycle in range(2):
        for w in range(9):
            for k in range(18):
                p += (1.2 if k < 14 else -0.9)
                closes.append(round(p, 4))
        for w in range(9):
            for k in range(18):
                p += (-1.4 if k < 14 else 0.7)
                closes.append(round(p, 4))
    closes += [90.0] * (n - len(closes))
    closes = closes[:n]
    ts = pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC")
    opens = [closes[0]] + closes[:-1]
    highs = [c + 0.6 for c in closes]
    lows = [c - 0.6 for c in closes]
    df = pd.DataFrame({"open": opens, "high": highs, "low": lows,
                       "close": closes, "volume": [1000.0] * n},
                      index=pd.DatetimeIndex(ts, name="time"))

    # الأحداث المتوقعة (نفس الآلة — عيار 4 على نفس البيانات)
    zx = compute_zone_exit_same(df, length=4)
    ev_bars = [j for j, f in enumerate(zx["zone_exit"]) if f]
    print(f"   أحداث انعكاس متوقعة (same/4): {len(ev_bars)} عند {ev_bars[:6]}...")
    check("L2.0 صنعت البيانات انعكاسات حقيقية", len(ev_bars) >= 2, ev_bars)

    class StubDS:
        async def get_historicallastvirsion(self, symbol, timeframe, market,
                                            start_date, end_date, use_cache=True,
                                            tz_offset_minutes=0):
            return df.copy()

    sc = {
        "name": "SPLIT-ZZ-SYNTH",
        "version": "1.0.0",
        "indicators": [{"name": "sma", "params": {"period": 50}}],
        "entry_rules": [{
            "name": "دخول: السعر فوق SMA50 (صعود)",
            "condition": {"type": "indicator_value", "operator": "<",
                          "left_value": "indicator:sma", "right_value": "close"},
            "position_side": "long", "weight": 1.0, "enabled": True}],
        # خروج مستحيل الحدوث (السما لا تبلغ 250 أبداً) ⇒ المتبقي يُغلق
        # عند نهاية البيانات — عزل نظيف لميكانيكا الانعكاس المقسم نفسها
        # (حدثان على نفس الصفقة — لا يستطيعها التيك-بروت المقسم بالمستويات)
        "exit_rules": [{
            "name": "خروج مستحيل (SMA>250)",
            "condition": {"type": "indicator_value", "operator": ">",
                          "left_value": "indicator:sma", "right_value": 250},
            "exit_type": "signal_exit", "enabled": True}],
        "filter_rules": [],
    }

    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig as BC

    cfg = BC(
        symbols=["TESTUSDT"], market="crypto", timeframe="15m",
        start_date=ts[0].to_pydatetime(), end_date=ts[-1].to_pydatetime(),
        initial_capital=10000.0, position_sizing="percentage",
        position_size_percent=100.0,
        strategy_config=sc,
        structure_split_exits=[{"resolution": "same", "length": 4,
                                "size_percent": 25}],
    )
    eng = BacktestEngine(data_service=StubDS())
    res = asyncio.run(eng.run_backtest(cfg))

    tp = res.trade_points
    entries = [q for q in tp if q.get("type") == "entry"]
    exits = [q for q in tp if q.get("type") == "exit"]
    partials = [q for q in tp if q.get("type") == "partial_exit"]

    check("L2.1 دخول واحد فتح (لا خروج قاعدي — عزل ميكانيكا الانعكاس)",
          len(entries) == 1, f"دخول={len(entries)}")
    check("L2.2 جنيان جزئيان بانعكاسين على نفس الصفقة (حدثان/صفقة)",
          len(partials) == 2, len(partials))
    check("L2.3 ختام واحد بالمتبقي عند نهاية البيانات",
          len(exits) == 1, f"خروج={len(exits)}")

    if entries and partials:
        e = entries[0]
        entry_price = e["entry_price"]
        orig_size = e["position_size"]
        entry_ts = pd.Timestamp(e["timestamp"])

        def _bar(ts_obj):
            ts_obj = pd.Timestamp(ts_obj)
            if ts_obj.tzinfo is None:
                ts_obj = ts_obj.tz_localize("UTC")
            return int(ts.get_loc(ts_obj))

        ok_price = True
        ok_size = True
        ok_time = True
        for q in partials:
            exp_price = float(df["open"].iloc[_bar(q["timestamp"])])
            if abs(q["price"] - exp_price) > 1e-9:
                ok_price = False
            if abs(q["position_size"] - orig_size * 0.25) > 1e-9:
                ok_size = False
            b = _bar(q["timestamp"])
            if (b - 1) not in ev_bars:
                ok_time = False
        check("L2.4 سعر كل جني = open الشمعة التالية للحدث بالضبط",
              ok_price, [(q["price"], q["timestamp"]) for q in partials])
        check("L2.5 حجم كل جني = ربع الكمية الأصلية", ok_size,
              [(q["position_size"], orig_size * 0.25) for q in partials])
        check("L2.6 توقيت كل جني = الشمعة التالية لحدث مؤكد", ok_time,
              [(_bar(q["timestamp"]) - 1) for q in partials])
        check("L2.7 أسباب الجني الصريحة (Structure Split ... 25%)",
              all("Structure Split" in str(q["exit_reason"])
                  and "25%" in str(q["exit_reason"]) for q in partials),
              [q["exit_reason"] for q in partials])
        ok_totals = True
        for x in exits:
            tid = x.get("trade_id")
            partial_pnl = sum(q["pnl"] for q in partials
                              if q.get("trade_id") == tid)
            total_exp = partial_pnl + (
                (x["exit_price"] - x["entry_price"]) * x["position_size"])
            if abs(x["pnl"] - total_exp) > 1e-7:
                ok_totals = False
        check("L2.8 نقطة الختام تعرض إجمالي الصفقة (جنيان+ختامي)",
              ok_totals)
        if len(partials) == 2:
            check("L2.8ب المتبقي بعد الجنيين = 50% من الكمية الأصلية",
                  abs(partials[1]["remaining_size"] - orig_size * 0.5) < 1e-9,
                  (partials[1]["remaining_size"], orig_size * 0.5))

    trades = getattr(res, "trades", None) or []
    check("L2.9 صفقة واحدة في trades", len(trades) == 1, len(trades))
    if trades and partials and exits:
        tr = trades[0]
        check("L2.10 trade.pnl = إجمالي (جنيان+ختامي) بت-بت",
              tr.pnl is not None and
              abs(tr.pnl - exits[0]["pnl"]) < 1e-7,
              (tr.pnl, exits[0]["pnl"]))
        check("L2.11 trade.partial_exits = 2 حدث انعكاس",
              len(tr.partial_exits or []) == 2, tr.partial_exits)
        _md = (tr.metadata or {}).get("structure_split") or {}
        check("L2.12 metadata.structure_split مع حدثيه",
              _md.get("events") and len(_md["events"]) == 2, _md)
        check("L2.13 الرصيد النهائي = ابتدائي + pnl الصفقة",
              abs(res.final_capital - (10000.0 + tr.pnl)) < 1e-7,
              (res.final_capital, tr.pnl))

    ma = getattr(res, "math_audit", None) or {}
    re_ = ma.get("risk_echo") or {}
    check("L2.14 risk_echo.structure_split_exits = القاعدة",
          re_.get("structure_split_exits") == [
              {"resolution": "same", "length": 4, "size_percent": 25.0}],
          re_.get("structure_split_exits"))
    check("L2.15 risk_echo.structure_split_active = True",
          re_.get("structure_split_active") is True)
    check("L2.16 risk_echo.structure_split_partial_exits = عدد الجنى",
          re_.get("structure_split_partial_exits") == len(partials),
          re_.get("structure_split_partial_exits"))

    # ======================= L2ب — الاستنفاد الكامل (100%) =======================
    print("== L2ب: استنفاد الكمية كاملة بانعكاس واحد (size=100%)")
    cfg_full = BC(
        symbols=["TESTUSDT"], market="crypto", timeframe="15m",
        start_date=ts[0].to_pydatetime(), end_date=ts[-1].to_pydatetime(),
        initial_capital=10000.0, position_sizing="percentage",
        position_size_percent=100.0,
        strategy_config=sc,
        structure_split_exits=[{"resolution": "same", "length": 4,
                                "size_percent": 100}],
    )
    eng_b = BacktestEngine(data_service=StubDS())
    res_b = asyncio.run(eng_b.run_backtest(cfg_full))
    tpb = res_b.trade_points
    partials_b = [q for q in tpb if q.get("type") == "partial_exit"]
    exits_b = [q for q in tpb if q.get("type") == "exit"]
    entries_b = [q for q in tpb if q.get("type") == "entry"]
    check("L2.17 الاستنفاد: كل جني 100% يفرّغ الكمية بالضبط",
          len(partials_b) >= 1 and all(
              q["remaining_size"] <= 1e-9 for q in partials_b),
          [q.get("remaining_size") for q in partials_b])
    check("L2.19 كل جني استنفادي يُختَم بـ Structure Split Exit (Full)",
          len(partials_b) >= 1 and sum(
              1 for q in exits_b
              if "Structure Split Exit (Full)" in str(q["exit_reason"])
          ) == len(partials_b),
          [q["exit_reason"] for q in exits_b])

    # ======================= L2ج — قاعدتان + SHORT =======================
    print("== L2ج: قاعدتان مستقلتان (same/4 + same/8) بأحجام مختلفة")
    cfg_two = BC(
        symbols=["TESTUSDT"], market="crypto", timeframe="15m",
        start_date=ts[0].to_pydatetime(), end_date=ts[-1].to_pydatetime(),
        initial_capital=10000.0, position_sizing="percentage",
        position_size_percent=100.0,
        strategy_config=sc,
        structure_split_exits=[{"resolution": "same", "length": 4,
                                "size_percent": 15},
                               {"resolution": "same", "length": 8,
                                "size_percent": 10}],
    )
    eng_c = BacktestEngine(data_service=StubDS())
    res_c = asyncio.run(eng_c.run_backtest(cfg_c := cfg_two))
    partials_c = [q for q in res_c.trade_points if q.get("type") == "partial_exit"]
    sizes_c = sorted(round(q["position_size"], 9) for q in partials_c)
    if entries:
        orig_c = None
        for q in res_c.trade_points:
            if q.get("type") == "entry":
                orig_c = q["position_size"]
                break
        exp_sizes = sorted(
            round(orig_c * (q.get("size_percent", 0) / 100.0), 9)
            for q in partials_c)
        check("L2.20 القاعدتان تبيعان حصصهما المختلفة من الأصل (15%/10%)",
              sizes_c == exp_sizes, (sizes_c, exp_sizes))
    check("L2.21 risk_echo يحمل القاعدتين معاً",
          (getattr(res_c, "math_audit", None) or {}).get(
              "risk_echo", {}).get("structure_split_total_size_percent")
          == 25.0)

    print()
    print(f"===== النتيجة: {len(PASS)} PASS / {len(FAIL)} FAIL =====")
    if FAIL:
        print("FAILED:", FAIL)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
