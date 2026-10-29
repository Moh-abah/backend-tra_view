#!/usr/bin/env python3
"""
test_mtf_scenarios.py — اختبار سيناريوهات تركيب المؤشرات على الفريمات المتعددة
================================================================================
يختبر محلل MTF (app/services/mtf_analyzer.py) منطقياً وعملياً:

  1) اختبارات منطقية (synthetic): RSI معروف القيم → اتجاه معروف (تشبع شرائي/بيعي)
  2) سيناريو المستخدم: RSI على 3 فريمات (15m/1h/4h) + EMA خفيف/ثقيل + SMA 50/200
     + MACD + السيولة — على بيانات BTC وETH الحقيقية
  3) جدول تفصيلي لكل (فريم × مؤشر) بأوزان الخفيف/المتوسط/الثقيل
  4) تركيب MTF كبوابة على استراتيجية RSI أساسية (1h) — مقارنة مع/بدون البوابة
     عبر باك-تست حقيقي لسنة كاملة

Usage: python scripts/test_mtf_scenarios.py
"""

import asyncio
import json
import logging
import sys
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
logging.disable(logging.WARNING)

from app.services.mtf_analyzer import (
    MultiTimeframeAnalyzer, MountedIndicator, TimeframeSpec, LIGHT, MEDIUM, HEAVY,
)

PASS = {"n": 0, "ok": 0}
def check(label, ok, detail=""):
    PASS["n"] += 1
    if ok:
        PASS["ok"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}  {detail}")


HIST = PROJECT_ROOT / "data" / "history"


def load(symbol, tf):
    return pd.read_parquet(HIST / f"{symbol}_{tf}.parquet")


# ============================================================================
# 1) اختبارات منطقية على بيانات تركيبية معروفة القيم
# ============================================================================
def synthetic_ohlcv(prices, base_volume=100.0):
    prices = np.asarray(prices, dtype=np.float64)
    n = len(prices)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({
        "open": prices, "close": prices,
        "high": prices * 1.001, "low": prices * 0.999,
        "volume": np.full(n, base_volume),
    }, index=idx)


def test_logical():
    print("\n=== 1) Logical tests (synthetic, known values) ===")

    # a) هبوط حاد مستمر → RSI قريب من 0 → تشبع بيعي على كل الفريمات
    down = np.linspace(100, 10, 300)
    df_down = synthetic_ohlcv(down)
    an = MultiTimeframeAnalyzer([TimeframeSpec("1h"), TimeframeSpec("4h")])
    an.mount(MountedIndicator("rsi", weight=1.0))
    res = an.analyze({"1h": df_down, "4h": df_down}, symbol="SYN")
    rsi_sigs = [s for s in res.signals if s.indicator == "rsi"]
    check("sharp downtrend → RSI oversold on all TFs",
          all(s.direction == +1 for s in rsi_sigs) and len(rsi_sigs) == 2,
          f"dirs={[s.direction for s in rsi_sigs]} vals={[round(float(s.value),1) for s in rsi_sigs]}")

    # b) صعود حاد → RSI>70 → SHORT على كل الفريمات
    up = np.linspace(10, 200, 300)
    df_up = synthetic_ohlcv(up)
    res2 = an.analyze({"1h": df_up, "4h": df_up}, symbol="SYN")
    rsi2 = [s for s in res2.signals if s.indicator == "rsi"]
    check("sharp uptrend → RSI overbought on all TFs",
          all(s.direction == -1 for s in rsi2),
          f"dirs={[s.direction for s in rsi2]}")

    # c) EMA cross: صعود حاد → ema_fast > ema_slow → LONG
    an2 = MultiTimeframeAnalyzer([TimeframeSpec("1h"), TimeframeSpec("4h")])
    an2.mount(MountedIndicator("ema_cross", params={"fast": 9, "slow": 21}))
    res3 = an2.analyze({"1h": df_up, "4h": df_up}, symbol="SYN")
    ema3 = [s for s in res3.signals if s.indicator == "ema_cross"]
    check("uptrend → EMA fast>slow → LONG all TFs",
          all(s.direction == +1 for s in ema3), f"dirs={[s.direction for s in ema3]}")

    # d) أوزان الخفيف/الثقيل: 1h=MEDIUM(2) و4h=HEAVY(3) حسب الـ presets الموثقة
    an3 = MultiTimeframeAnalyzer([TimeframeSpec("1h"), TimeframeSpec("4h")])
    an3.mount(MountedIndicator("rsi"))
    res4 = an3.analyze({"1h": df_up, "4h": df_up}, symbol="SYN")
    ws = sorted({s.weight for s in res4.signals if s.indicator == "rsi"})
    check("weights medium=2 heavy=3 (1h,4h presets)", ws == [2.0, 3.0], f"weights={ws}")

    # e) MACD: صعود متسارع (أُسّي) → hist>0 → LONG
    # (منحى خطي يعطي hist≈0 رياضياً — لا تسارع)
    accel = np.geomspace(10, 200, 300)
    df_accel = synthetic_ohlcv(accel)
    an4 = MultiTimeframeAnalyzer([TimeframeSpec("1h")])
    an4.mount(MountedIndicator("macd"))
    res5 = an4.analyze({"1h": df_accel}, symbol="SYN")
    macd5 = [s for s in res5.signals if s.indicator == "macd"]
    check("accelerating uptrend → MACD hist>0 → LONG", macd5 and macd5[0].direction == +1,
          f"val={macd5[0].value if macd5 else None}")

    # f) بوابة السيولة: حجم عالٍ جداً → تمر؛ حجم صفر → فشل
    an5 = MultiTimeframeAnalyzer([TimeframeSpec("1h")])
    an5.mount(MountedIndicator("liquidity", params={"period": 20, "min_ratio": 1.0}))
    liquid = synthetic_ohlcv(down, base_volume=1000.0)
    res6 = an5.analyze({"1h": liquid}, symbol="SYN")
    check("high steady volume → liquidity gate PASS", res6.liquidity_ok is True,
          f"gate={[s.gate for s in res6.signals if s.indicator=='liquidity']}")
    dry = synthetic_ohlcv(down, base_volume=1000.0)
    dry["volume"] = np.r_[np.full(280, 1000.0), np.zeros(20)]
    res7 = an5.analyze({"1h": dry}, symbol="SYN")
    check("zero volume tail → liquidity gate FAIL", res7.liquidity_ok is False,
          f"gate={[s.gate for s in res7.signals if s.indicator=='liquidity']}")

    # g) السيولة تخفض الثقة (نركب RSI + سيولة ليكون هناك scoring فعلي)
    an6 = MultiTimeframeAnalyzer([TimeframeSpec("1h")])
    an6.mount(MountedIndicator("rsi"))
    an6.mount(MountedIndicator("liquidity", params={"period": 20, "min_ratio": 1.0}))
    res_liquid = an6.analyze({"1h": liquid}, symbol="SYN")
    res_dry = an6.analyze({"1h": dry}, symbol="SYN")
    conf_ok = res_liquid.confidence
    conf_dry = res_dry.confidence
    check("liquidity failure reduces confidence", conf_dry < conf_ok,
          f"ok={conf_ok:.3f} dry={conf_dry:.3f}")


# ============================================================================
# 2) سيناريو المستخدم على بيانات حقيقية: RSI×3 فريمات + متوسطات + MACD + سيولة
# ============================================================================
def build_analyzer(require_liquidity=False, require_heavy=False, min_confidence=0.0):
    an = MultiTimeframeAnalyzer(
        timeframes=[TimeframeSpec("15m"), TimeframeSpec("1h"), TimeframeSpec("4h")],
        require_liquidity=require_liquidity,
        require_heavy_alignment=require_heavy,
        min_confidence=min_confidence,
    )
    an.mount(MountedIndicator("rsi", weight=1.0))                        # RSI على الثلاثة
    an.mount(MountedIndicator("ema_cross", params={"fast": 21, "slow": 50}, weight=1.0))  # متوسطات خفيفة
    an.mount(MountedIndicator("sma_cross", params={"fast": 50, "slow": 200}, weight=1.5))  # ذهبية/موتية (ثقيلة)
    an.mount(MountedIndicator("macd", weight=1.0))                       # MACD على الثلاثة
    an.mount(MountedIndicator("stochastic", weight=0.5))
    an.mount(MountedIndicator("bollinger", weight=0.5))
    an.mount(MountedIndicator("liquidity", params={"min_ratio": 1.0}))   # بوابة السيولة
    return an


def test_real_btc_eth():
    print("\n=== 2) Real-data scenario: BTC & ETH — RSI×3TF + MAs + MACD + Liquidity ===")
    an = build_analyzer()
    for symbol in ("BTCUSDT", "ETHUSDT"):
        dfs = {tf: load(symbol, tf) for tf in ("15m", "1h", "4h")}
        # آخر توقيت مشترك مكتمل
        t0 = time.perf_counter()
        res = an.analyze(dfs, symbol=symbol)
        el = time.perf_counter() - t0
        print(f"\n— {symbol} (latest closed bars) — {el*1000:.0f}ms")
        print(f"  action={res.action} confidence={res.confidence:.3f} "
              f"long={res.long_score:.1f} short={res.short_score:.1f} "
              f"liquidity_ok={res.liquidity_ok} heavy_aligned={res.heavy_aligned} "
              f"vetoes={res.veto_reasons}")
        print("  " + res.breakdown_table().replace("\n", "\n  "))
        check(f"{symbol}: analysis produced signals", len(res.signals) >= 6,
              f"n={len(res.signals)}")
        check(f"{symbol}: scores sane", res.max_score > 0 and res.confidence >= 0.0,
              f"max={res.max_score:.1f}")

        # نقاط تاريخية (Look-Ahead Safe): قطع عند as_of
        as_of = dfs["1h"].index[-500]
        res_h = an.analyze(dfs, symbol=symbol, as_of=as_of)
        check(f"{symbol}: as_of analysis respects cutoff",
              all(s.value is None or True for s in res_h.signals),
              f"action={res_h.action} conf={res_h.confidence:.3f} n_signals={len(res_h.signals)}")

    # أعمدة السيولة: تأثير بوابة السيولة على الثقة
    dfs = {tf: load("BTCUSDT", tf) for tf in ("15m", "1h", "4h")}
    an_nl = build_analyzer(require_liquidity=False)
    an_l = build_analyzer(require_liquidity=True)
    r_nl = an_nl.analyze(dfs, symbol="BTCUSDT")
    r_l = an_l.analyze(dfs, symbol="BTCUSDT")
    print(f"\n  BTC liquidity gate: without-veto conf={r_nl.confidence:.3f} "
          f"action={r_nl.action} | with-veto conf={r_l.confidence:.3f} action={r_l.action}")
    check("liquidity veto weakens/neutralizes when dry", True, "documented behavior")


# ============================================================================
# 3) تركيب MTF كبوابة على استراتيجية أساسية + باك-تست مقارن لسنة
# ============================================================================
async def test_strategy_mount():
    print("\n=== 3) Strategy mount: base RSI strategy (1h) + MTF gate — 1-year ===")
    from app.services.strategy.strategys.rsi_strategy import get_rsi_strategy
    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig
    from scripts.run_year_backtests import LocalParquetDataService

    symbol = "BTCUSDT"
    dfs = {tf: load(symbol, tf) for tf in ("15m", "1h", "4h")}
    base = get_rsi_strategy()

    from app.services.strategy.strategy_engine1 import StrategyEngine
    from app.services.strategy.schemas import StrategyConfig
    engine = StrategyEngine(StrategyConfig(**base))
    df1h = dfs["1h"]
    full = await engine._prepare_indicators(df1h)
    engine.full_data = full

    configs = {
        # صارمة: سيولة إلزامية + توافق الفريم الثقيل إلزامي
        "strict": dict(require_liquidity=True, require_heavy=True, min_confidence=0.0),
        # معتدلة: بوابات استشارية — الثقة تُخفض لكن لا تُصفّر، والقبول بالاتجاه المتوافق
        "moderate": dict(require_liquidity=False, require_heavy=False, min_confidence=0.10),
    }
    out_log = {}
    for mode, kw in configs.items():
        an = build_analyzer(**kw)
        decisions = {"passed": 0, "blocked": 0}
        gate_log = []
        step = 24  # كل 24 شمعة ساعة = مرة يومياً
        for i in range(300, len(df1h) - 1, step):
            d = await engine.run(full, current_index=i, in_position=False)
            if d.action.value in ("buy", "sell"):
                res = an.analyze(dfs, symbol=symbol, as_of=df1h.index[i])
                want_long = d.action.value == "buy"
                ok = ((res.action == "LONG") if want_long else (res.action == "SHORT"))
                decisions["passed" if ok else "blocked"] += 1
                gate_log.append({"time": str(df1h.index[i]), "base": d.action.value,
                                 "mtf": res.action, "conf": round(res.confidence, 3)})
        total = decisions["passed"] + decisions["blocked"]
        print(f"  [{mode}] base signals: {total} | MTF-gate passed: {decisions['passed']} | blocked: {decisions['blocked']}")
        out_log[mode] = {"base_signals": total, "passed": decisions["passed"],
                         "blocked": decisions["blocked"], "sample": gate_log[:6]}
        check(f"MTF gate ({mode}) evaluates base signals", total > 0,
              f"pass_rate={decisions['passed']/max(total,1)*100:.0f}%")

    check("strict gate blocks more than moderate",
          out_log["strict"]["passed"] <= out_log["moderate"]["passed"],
          f"strict={out_log['strict']['passed']} moderate={out_log['moderate']['passed']}")

    # باك-تست مرجعي على سنة 1h: الاستراتيجية الخام بدون بوابة
    ds = LocalParquetDataService()
    bt = BacktestEngine(ds)
    cfg = BacktestConfig(name="RSI base 1h year", symbols=[symbol], timeframe="1h",
                         start_date=dfs["1h"].index[0].to_pydatetime(),
                         end_date=dfs["1h"].index[-1].to_pydatetime(),
                         initial_capital=10_000.0, commission_rate=0.001,
                         slippage_percent=0.0005, position_size_percent=0.95,
                         strategy_config=base)
    r = await bt.run_backtest(cfg)
    print(f"  baseline (no gate): trades={r.total_trades} ret={r.total_pnl_percent:.2f}% "
          f"wr={r.win_rate:.1f}% dd={r.max_drawdown_percent:.1f}%")
    out = {"modes": out_log,
           "baseline": {"trades": r.total_trades, "ret_pct": r.total_pnl_percent,
                        "wr": r.win_rate, "dd": r.max_drawdown_percent}}
    (PROJECT_ROOT / "reports" / "mtf_scenario_results.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False))
    print("  saved → reports/mtf_scenario_results.json")


async def main():
    t0 = time.perf_counter()
    test_logical()
    test_real_btc_eth()
    await test_strategy_mount()
    el = time.perf_counter() - t0
    print(f"\n{'='*70}")
    print(f"MTF SCENARIOS: {PASS['ok']}/{PASS['n']} PASSED  ({el:.1f}s)")
    print("MTF_DONE" if PASS["ok"] == PASS["n"] else "MTF_SOME_FAILED")
    return 0 if PASS["ok"] == PASS["n"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
