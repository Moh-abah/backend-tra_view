#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BNB-E2E-QEMA · جولة A/B نمط التريلينق (TRAILMODE1) — ترجمة سؤال المهندس
محمد الحرفي إلى قياس:

«احسب من سعر الشراء الى اعلى قمه، اذا نزل 15% من اجمالي هذا الارتفاع
فهذا يعتبر ستوب تريلينق» (rise_pct — النزول من إجمالي الارتفاع)
ضد سلوك النظام الحالي (peak_pct — النزول نسبة% من أعلى قمة سعرية نفسها).
«لانها تفرق بالنسبه المئويه فكيف بيتم احتسابها لاننا نريد الافضل».

نفس العقد المجمّد الحرفي لحملة mo2 (بلا أي تغيير):
  · zigzag_fib_e2e_trendy_quantum_ema · length=100 · رصة EMA الستة
    [21,50,100,200,350,500] · فريم 60 · trend 7/15/25 majority
  · trend_gate/zone_gate/ema_gate كاملة [s1,s2,s3] · الإشارات الثلاث
  · 15m · كامل التاريخ من الصدور (2017-11-06 → 2026-11-16)
  · 1000$ · صفر عمولة · max_positions=2 · compounding متعدد

البُعد الوحيد المتغير: نمط خط التريلينق (trailing_stop_mode) + في أذرع
الاستكشاف: نسبة تريلينق أوسع (25%) بنمط الارتفاع.
المحرك: trailmode1/post_tree (TP3-SLTRAIL1 + TRAILMODE1 — البطارية PASS).

الأذرع:
  B3-peak   : نفس حمولة mo2-B3 حرفيًا بلا نمط — برهان الهوية بت-بت مع
              نتيجة mo2 المؤرشفة (52.20% / +212.28%) على الشجرة الجديدة.
  B3-rise   : العقد الحرفي + rise_pct — سؤال المهندس مُجابًا بالقياس.
  B1-rise   : عزل التريلينق (بلا ستوب) بنمط الارتفاع (مقابل mo2-B1).
  E7-rise   : تريلينق-10 بنمط الارتفاع (مقابل mo2-E7 63.93%).
  E3-rise   : ذراع العائد الجيد (3.0@70+6.0@15) بنمط الارتفاع.
  E6-rise   : ذراع أفضل PF (ستوب-4) بنمط الارتفاع.
  F1-rise   : البطل (1.0@100) بنمط الارتفاع — التريلينق تجميلي هنا؟
  B3-rise25 : استكشاف — تريلينق-25 من الارتفاع (توسيع المقارنة).
"""
import asyncio
import io
import json
import sys
import time
import types
from pathlib import Path

BASE = Path("/home/z/my-project/trading-system")
POST_TREE = BASE / "trailmode1" / "post_tree"
DATA = BASE / "bnb-e2e-qema" / "data" / "BNBUSDT_15m.json"
PAYLOAD_BASE = BASE / "bnb-e2e-qema" / "payloads" / "payload_D3_h1651_BOTH.json"
OUT = BASE / "trailmode1" / "results"
OUT.mkdir(exist_ok=True, parents=True)

# (key, splits, sl, trail, mode) — mode=None يعني بلا بث (peak_pct التاريخي)
ARMS = [
    ("B3-peak",   [(4.7, 33.33), (7.4, 33.33)], 5, 15, None),
    ("B3-rise",   [(4.7, 33.33), (7.4, 33.33)], 5, 15, "rise_pct"),
    ("B1-rise",   [(4.7, 33.33), (7.4, 33.33)], None, 15, "rise_pct"),
    ("E7-rise",   [(3.0, 70), (6.0, 15)], 5, 10, "rise_pct"),
    ("E3-rise",   [(3.0, 70), (6.0, 15)], 5, 15, "rise_pct"),
    ("E6-rise",   [(3.0, 70), (6.0, 15)], 4, 15, "rise_pct"),
    ("F1-rise",   [(1.0, 100)], 5, 15, "rise_pct"),
    ("B3-rise25", [(4.7, 33.33), (7.4, 33.33)], 5, 25, "rise_pct"),
]

_ds_mod = types.ModuleType("app.services.data_service")


class _S:
    pass


_ds_mod.DataService = _S


def build_payload(key, splits, sl, trail, mode):
    p = json.load(io.open(PAYLOAD_BASE, encoding="utf-8"))
    # الشروط الإلزامية تُثبّت حرفيًا (نفس دفاع mo2_round.py — عقد مجمّد)
    ind = p["strategy_config"]["indicators"][0]
    ind["params"]["length"] = 100
    ind["params"]["ema_lengths"] = [21, 50, 100, 200, 350, 500]
    ind["params"]["trend_confirm"] = "majority"
    ind["params"]["trend_periods"] = [7, 15, 25]
    ind["params"]["trend_gate"] = ["s1", "s2", "s3"]
    ind["params"]["zone_gate"] = ["s1", "s2", "s3"]
    ind["params"]["ema_gate"] = ["s1", "s2", "s3"]
    ind["params"]["ema_resolution"] = "60"
    for r in p["strategy_config"]["entry_rules"]:
        r["enabled"] = True
    p["max_positions"] = 2
    p["multi_position_compounding"] = True
    p["take_profit_splits"] = [
        {"gain_percent": g, "size_percent": s,
         "name": "التصريف %d — جني عند +%g%%" % (i + 1, g)}
        for i, (g, s) in enumerate(splits)
    ]
    if sl is None:
        p.pop("stop_loss_percent", None)
    else:
        p["stop_loss_percent"] = float(sl)
    if trail is None:
        p.pop("trailing_stop_percent", None)
    else:
        p["trailing_stop_percent"] = float(trail)
    if mode is None:
        p.pop("trailing_stop_mode", None)
    else:
        p["trailing_stop_mode"] = mode
    p["name"] = (f"BNB-E2E-QEMA · 15m · trailAB {key} — العقد المجمّد mo2 "
                 f"· جني " + "/".join(f"{g}@{s}%" for g, s in splits)
                 + f" · ستوب {sl} · تريلينق {trail}"
                 + (f" ({mode})" if mode else " (peak_pct تاريخي)"))
    return p


def load_df():
    import pandas as pd
    candles = json.load(io.open(DATA, encoding="utf-8"))
    df = pd.DataFrame([{
        "open": float(c["open"]), "high": float(c["high"]),
        "low": float(c["low"]), "close": float(c["close"]),
        "volume": float(c["volume"]),
    } for c in candles])
    df.index = pd.DatetimeIndex(
        pd.to_datetime([c["time"] for c in candles], unit="ms", utc=True),
        name="time")
    return df


async def run_arm(key, splits, sl, trail, mode):
    sys.path.insert(0, str(POST_TREE))
    sys.modules["app.services.data_service"] = _ds_mod
    import app.backtest.engine1 as e1
    from app.backtest.schemas import BacktestConfig
    df = load_df()

    class StubDS:
        def __init__(self, df):
            self.dfs = {"15m": df}

        async def get_historicallastvirsion(self, symbol, timeframe, market,
                                            start_date, end_date, use_cache=True,
                                            tz_offset_minutes=0):
            return self.dfs.get(str(timeframe), self.dfs["15m"]).copy()

    payload = build_payload(key, splits, sl, trail, mode)
    cfg = BacktestConfig(**payload)
    eng = e1.BacktestEngine(data_service=StubDS(df))
    res = await eng.run_backtest(cfg)
    trades = getattr(res, "trades", None) or []
    reasons = {}
    for t in trades:
        r = str(t.exit_reason).split(" (")[0]
        reasons[r] = reasons.get(r, 0) + 1
    re_ = ((getattr(res, "math_audit", None) or {}).get("risk_echo") or {})
    d = {
        "key": key,
        "config": {
            "length": 100,
            "ema_lengths": [21, 50, 100, 200, 350, 500],
            "signals": "S1+S2+S3",
            "gates": "trend 7/15/25 majority + zone كاملة + ema كاملة",
            "splits": [{"gain_percent": g, "size_percent": s} for g, s in splits],
            "stop_loss_percent": sl,
            "trailing_stop_percent": trail,
            "trailing_stop_mode": mode or "(none ⇒ peak_pct)",
            "max_positions": 2,
            "multi_position_compounding": True,
            "engine": "TP3-SLTRAIL1 + TRAILMODE1 (trailmode1/post_tree)",
        },
        "final_capital": float(res.final_capital),
        "total_pnl_percent": float(res.total_pnl_percent),
        "total_trades": int(res.total_trades),
        "win_rate": float(res.win_rate),
        "max_drawdown_percent": float(getattr(res, "max_drawdown_percent", 0) or 0),
        "profit_factor": float(getattr(res, "profit_factor", 0) or 0),
        "sharpe_ratio": float(getattr(res, "sharpe_ratio", 0) or 0),
        "sortino_ratio": float(getattr(res, "sortino_ratio", 0) or 0),
        "calmar_ratio": float(getattr(res, "calmar_ratio", 0) or 0),
        "expectancy": float(getattr(res, "expectancy", 0) or 0),
        "winning_trades": int(getattr(res, "winning_trades", 0) or 0),
        "exit_reasons": reasons,
        "max_positions_requested": re_.get("max_positions_requested"),
        "max_concurrent_applied": re_.get("max_concurrent_applied"),
        "multi_position_compounding_echo": re_.get("multi_position_compounding"),
        "trailing_stop_mode_echo": re_.get("trailing_stop_mode"),
        "trailing_stop_semantics": re_.get("trailing_stop_semantics"),
        "sl_trailing_coexist": re_.get("sl_trailing_coexist"),
    }
    return d


def main():
    which = sys.argv[1:] or [a[0] for a in ARMS]
    if which and which[0] == "combine":
        combined = {}
        for (key, _s, _sl, _t, _m) in ARMS:
            fp = OUT / f"trailAB_{key}_15m.json"
            if fp.exists():
                combined[key] = json.load(io.open(fp, encoding="utf-8"))
        with io.open(OUT / "trailAB_summary.json", "w", encoding="utf-8") as f:
            json.dump(combined, f, ensure_ascii=False, indent=1, default=str)
        print(f"دمج {len(combined)} ذراعًا → trailAB_summary.json")
        return
    arms = {a[0]: a for a in ARMS}
    for key in which:
        if key not in arms:
            print(f"[{key}] ذراع مجهول — تجاهل", flush=True)
            continue
        _k, splits, sl, trail, mode = arms[key]
        t0 = time.time()
        print(f"[{key}] تشغيل — جني {splits} · ستوب {sl} · تريلينق {trail} "
              f"· نمط {mode or 'peak_pct'}", flush=True)
        try:
            d = asyncio.run(run_arm(key, splits, sl, trail, mode))
        except Exception as exc:
            d = {"key": key, "error": repr(exc)}
        d["elapsed_s"] = round(time.time() - t0, 1)
        with io.open(OUT / f"trailAB_{key}_15m.json", "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1, default=str)
        if "error" in d:
            print(f"[{key}] خطأ: {d['error'][:200]}", flush=True)
        else:
            print(f"[{key}] WR={d['win_rate']:.2f}% · PnL={d['total_pnl_percent']:.2f}% · "
                  f"صفقات={d['total_trades']} · ماكس-مطبق={d['max_concurrent_applied']} · "
                  f"نمط-صدى={d['trailing_stop_mode_echo']} · "
                  f"PF={d['profit_factor']:.2f} · MaxDD={d['max_drawdown_percent']:.1f}% · "
                  f"({d['elapsed_s']}s)", flush=True)


if __name__ == "__main__":
    main()
