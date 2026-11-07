#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROUND19 — التحقق الحي النهائي لوضع tradingview في مسار الإشارة
==============================================================
[1] المقارنة الحية: luxalgo-100 (القديم) مقابل tradingview(12,20,3) (الجديد)
    على نفس النافذة — آخر ساق، خط الانطلاقة، إشارات الدخول.
[2] إثبات عدم إعادة الرسم على الوضع الجديد: قص زمني (B/B+1/B+50) + صفقة المحرك
    (entry_time/entry_price/label) على المقطع المنتهي عند شمعة الإشارة.
[3] الإشارة الحية عبر evaluate_live_signal — البريسِت الجديد (ZLF_TRIPLE_SIGNAL
    يمرر mode=tradingview).
"""
import asyncio
import json
import os
import sys

PRO27 = "/home/z/my-project/backend-audit/pro27"
sys.path.insert(0, PRO27)
os.chdir(PRO27)
os.environ.setdefault(
    "SECRET_KEY",
    "r6fwc7Q8CGqI3RpKFaTDbJJ55EOR6LrADCPZv4_KK5LbI0fpzDn84KhemcV_TE0C",
)

import pandas as pd  # noqa: E402

from app.backtest.engine1 import BacktestEngine  # noqa: E402
from app.backtest.schemas import BacktestConfig  # noqa: E402
from app.services.live_strategy_service import (  # noqa: E402
    evaluate_live_signal, _fetch_window, _is_forming, WINDOW_CANDLES,
    _PreparedDataService, CHAMPION_SL_PERCENT, CHAMPION_TP_PERCENT,
)
from app.services.indicators.overlays import zigzag_fib  # noqa: E402
from app.services.strategy.presets import ZLF_TRIPLE_SIGNAL  # noqa: E402

TF_MIN = 5
TV_PARAMS = dict(mode="tradingview", depth=12, deviation=20, backstep=3)
LUX_PARAMS = dict(mode="luxalgo", length=100)
COMMON = dict(touch_level=0.618, liq_lookback=20, liq_signals=True, liq_arm_bars=60)

FIELDS = ("signal", "bar", "price", "ref_high", "ref_vol", "launch_line", "fallback")


def iso(ts) -> str:
    try:
        return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return str(ts)


def fmt(x) -> str:
    return f"{float(x):.10g}"


def last_leg_of(zzf):
    cur = zzf.get("current") or {}
    if not cur:
        return None
    return {"p1": cur.get("p1"), "p2": cur.get("p2"), "dir": cur.get("dir"),
            "i1": cur.get("i1"), "i2": cur.get("i2")}


def entries_of(zzf):
    return [dict({k: s.get(k) for k in FIELDS}, time=s.get("time"))
            for s in zzf.get("signals", []) if str(s.get("signal", "")).startswith("ZLF Entry")]


def diff_entry(a: dict, b: dict) -> list:
    bad = []
    for k in FIELDS:
        va, vb = a.get(k), b.get(k)
        if k == "signal":
            if str(va) != str(vb):
                bad.append((k, va, vb))
            continue
        if (va is None) != (vb is None):
            bad.append((k, va, vb))
        elif va is not None and abs(float(va) - float(vb)) > 1e-12 * max(1.0, abs(float(va))):
            bad.append((k, va, vb))
    return bad


async def engine_entry(dfin: pd.DataFrame, df_full: pd.DataFrame, symbol: str, timeframe: str):
    last_ts = dfin.index[-1].to_pydatetime()
    nxt = last_ts + pd.Timedelta(minutes=TF_MIN)
    open_px = float(df_full.loc[nxt, "open"]) if nxt in df_full.index else float(dfin["close"].iloc[-1])
    fill = pd.DataFrame(
        {"open": [open_px], "high": [open_px], "low": [open_px], "close": [open_px], "volume": [0.0]},
        index=pd.DatetimeIndex([nxt], name=dfin.index.name or "time"),
    )
    dfp = pd.concat([dfin, fill])
    dfp = dfp[~dfp.index.duplicated(keep="last")]
    config = BacktestConfig(
        name="round19-no-repaint-probe", symbols=[symbol], timeframe=timeframe, market="crypto",
        start_date=dfin.index[0].to_pydatetime(), end_date=nxt,
        initial_capital=10000.0, position_size_percent=1.0,
        stop_loss_percent=CHAMPION_SL_PERCENT, take_profit_percent=CHAMPION_TP_PERCENT,
        fill_model="next_open", tz_offset_minutes=0,
        strategy_config=ZLF_TRIPLE_SIGNAL["strategy_config"],
    )
    result = await BacktestEngine(_PreparedDataService(dfp)).run_backtest(config)
    trades = list(getattr(result, "trades", []) or [])
    points = [tp for tp in (getattr(result, "trade_points", []) or [])
              if isinstance(tp, dict) and tp.get("type") == "entry"]
    out = []
    for t in trades:
        ep = next((p for p in points if p.get("trade_id") == getattr(t, "id", None)), None)
        out.append({"entry_time": str(getattr(t, "entry_time")),
                    "entry_price": float(getattr(t, "entry_price")),
                    "label": (ep or {}).get("decision_reason")})
    return out


async def run(symbol: str, timeframe: str) -> None:
    print("=" * 96)
    print(f"ROUND19 LIVE PROOF — {symbol} · {timeframe} · crypto")
    print("=" * 96)

    df_raw, now = await _fetch_window(symbol, "crypto", timeframe)
    df = df_raw.copy().sort_index()
    if len(df) and _is_forming(df.index[-1].to_pydatetime(), timeframe, now):
        df = df.iloc[:-1]
    if len(df) > WINDOW_CANDLES:
        df = df.iloc[-WINDOW_CANDLES:]
    print(f"WINDOW: {len(df)} closed · {iso(df.index[0])} → {iso(df.index[-1])} · fetched {iso(now)}")

    # ---------- [1] المقارنة الحية: القديم مقابل الجديد ----------
    z_lux = zigzag_fib(df, **LUX_PARAMS, **COMMON)
    z_tv = zigzag_fib(df, **TV_PARAMS, **COMMON)
    for label, z in [("OLD luxalgo-100", z_lux), ("NEW tradingview(12,20,3)", z_tv)]:
        piv = len(z.get("legs", [])) + 1 if z.get("legs") else 0
        leg = last_leg_of(z)
        ents = entries_of(z)
        ent = ents[-1] if ents else None
        print(f"\n  [{label}]")
        print(f"    pivots≈{piv} · ZLF entries in window={len(ents)}")
        if leg:
            print(f"    last leg: p1={fmt(leg['p1'])} @bar {leg['i1']} → p2={fmt(leg['p2'])} @bar {leg['i2']} "
                  f"(dir={leg['dir']:+.0f})")
        if ent:
            print(f"    last entry: {ent['signal']} @bar {ent['bar']} ({iso(df.index[int(ent['bar'])])}) · "
                  f"price={fmt(ent['price'])} · launch={fmt(ent['launch_line'])} · fallback={ent['fallback']}")

    # ---------- [2] عدم إعادة الرسم على الوضع الجديد ----------
    ents = entries_of(z_tv)
    if ents:
        last = ents[-1]
        B = int(last["bar"])
        print(f"\n[2] NO-REPAINT (tradingview) — آخر دخول @bar {B} ({iso(df.index[B])}):")
        for cut in (B, min(B + 1, len(df) - 1), min(B + 50, len(df) - 1)):
            sub = df.iloc[: cut + 1]
            sub_zzf = zigzag_fib(sub, **TV_PARAMS, **COMMON)
            sub_ents = entries_of(sub_zzf)
            match = next((e for e in reversed(sub_ents) if int(e["bar"]) == B), None)
            if match is None:
                print(f"  cut@{cut}: ✗ حدث bar {B} غير موجود!")
                continue
            bad = diff_entry(last, match)
            print(f"  cut@{cut} (حتى {iso(df.index[cut])}): {match['signal']} @bar {match['bar']} — "
                  f"{'IDENTICAL ✓' if not bad else 'MISMATCH ' + str(bad)}")

        tr_full = await engine_entry(df, df, symbol, timeframe)
        tr_cut = await engine_entry(df.iloc[: B + 1], df, symbol, timeframe)
        cut_open = str(df.index[min(B + 1, len(df) - 1)])[:16]
        f_m = [t for t in tr_full if t["entry_time"][:16] == cut_open]
        c_m = [t for t in tr_cut if t["entry_time"][:16] == cut_open]
        if f_m and c_m:
            same = f_m[-1] == c_m[-1]
            print(f"    engine full  : {f_m[-1]}")
            print(f"    engine cut@B : {c_m[-1]}")
            print(f"    ⇒ صفقة الدخول {'IDENTICAL ✓ (entry_time/price/label حرفياً)' if same else 'MISMATCH ✗'}")
        else:
            print(f"    (لا صفقة عند فتح {cut_open} — full={len(f_m)} cut={len(c_m)})")

    # ---------- [3] الإشارة الحية (البريسِت الجديد) ----------
    print("\n[3] LIVE SIGNAL (بريسِت ROUND19 — mode=tradingview):")
    try:
        payload = await evaluate_live_signal(symbol, "crypto", timeframe, "zigzag_fib")
        slim = {"state": payload.get("state"), "has_signal": payload.get("has_signal"),
                "signal": payload.get("signal"),
                "meta.window": (payload.get("meta") or {}).get("window")}
        print(json.dumps(slim, ensure_ascii=False, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001
        print(f"    (unavailable: {type(exc).__name__}: {exc})")


async def main():
    for sym, tf in [("ZECUSDT", "5m"), ("LAZIOUSDT", "5m")]:
        try:
            await run(sym, tf)
        except Exception as exc:  # noqa: BLE001
            print(f"\n!! {sym}: {type(exc).__name__}: {exc}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
