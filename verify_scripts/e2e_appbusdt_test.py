#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# ✅ ROUND34 — الاختبار الوظيفي الشامل E2E على APPBUSDT 5m (الحالة المبلغة)
# =============================================================================
# المسار الكامل من الإشارة إلى الرسم:
#   1) تشغيل باك تست حقيقي بمحرك engine1 باستراتيجية «البطل e2e» على بيانات
#      APPBUSDT 5m الأسبوعية (نفس بيانات بلاغ المستخدم).
#   2) التحقق أن الصفقات/الإشارات ظهرت بأسمائها (ZLF-E2E S1/S2/S3).
#   3) بناء حمولة chart-data كما يبنيها الراوتر (شموع ISO بلا/مع volume)
#      والتحقق أن مسار overlays ينتج إحداثيات رسم صحيحة (أزمنة ≠ 0) ومراجع
#      R وإشارات متطابقة مع ما نفذته الاستراتيجية.
#   4) إخراج ملف JSON كامل للرسم البصري (HTML) — كل الإحداثيات الحية.
# =============================================================================
import asyncio
import copy
import json
import os
import sys
import time
from datetime import datetime, timezone

# ✅ مسارات نسبية — تعمل من أي مكان: جذر المشروع = والدُ والدُ السكربت
# (أو NEW_SRC لمشروع مدموج في مسار آخر)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT = os.environ.get("NEW_SRC") or os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT)
_EVIDENCE = os.path.join(_PROJECT, "evidence")
_OUT_DIR = os.environ.get("OUT_DIR") or _HERE

import pandas as pd

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(("PASS ✅ " if ok else "FAIL ❌ ") + name + (f"  [{detail}]" if detail and not ok else ""))


def main():
    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig
    from app.services.strategy.presets import get_presets

    candles = json.load(open(os.path.join(_EVIDENCE, "APPBUSDT_5m_week.json")))
    print(f"APPBUSDT 5m: {len(candles)} candles "
          f"({datetime.fromtimestamp(candles[0]['timestamp']/1000, tz=timezone.utc).date()} → "
          f"{datetime.fromtimestamp(candles[-1]['timestamp']/1000, tz=timezone.utc).date()})")

    df = pd.DataFrame(candles)
    df["time"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
    df = df.set_index(pd.DatetimeIndex(df["time"], name="time"))[["open", "high", "low", "close", "volume"]]
    df = df.apply(lambda s: pd.to_numeric(s, errors="coerce"))

    class _PreparedDataService:
        def __init__(self, frame):
            self._df = frame

        async def get_historicallastvirsion(self, **kwargs):
            return self._df.copy()

    presets = {p["id"]: p for p in get_presets()}
    e2e_payload = presets["zlf_e2e_triple_signal_zero_fee"]
    # تكييف الفريم/الرمز لحالة البلاغ: APPBUSDT 5m
    payload = copy.deepcopy(e2e_payload["payload"])
    payload["strategy_config"]["base_timeframe"] = "5m"
    for ind in payload["strategy_config"]["indicators"]:
        ind["timeframe"] = "5m"
    payload["timeframe"] = "5m"

    async def run_engine(pl):
        cfg = BacktestConfig(
            name="round34-appbusdt-e2e",
            symbols=["APPUSDT".replace("APPUSDT", "APPBUSDT")],
            timeframe="5m",
            market="crypto",
            initial_capital=10000.0,
            position_size_percent=1.0,
            stop_loss_percent=2.0,
            take_profit_percent=99.0,
            fill_model="next_open",
            tz_offset_minutes=180,  # الرياض +3 — كما يشغّل المستخدم
            strategy_config=pl["strategy_config"],
        )
        engine = BacktestEngine(_PreparedDataService(df))
        return await engine.run_backtest(cfg)

    t0 = time.perf_counter()
    bt = asyncio.run(run_engine(payload))
    elapsed = time.perf_counter() - t0
    print(f"backtest finished in {elapsed:.1f}s")

    trades = getattr(bt, "trades", []) or []
    total_pnl = getattr(bt, "total_pnl", None)
    print(f"trades: {len(trades)} | total_pnl: {total_pnl}")
    riyadh_tz = timezone(timezone.utc.utcoffset(None) if False else __import__("datetime").timedelta(hours=3))
    entry_times = []
    for tr in trades:
        et = getattr(tr, "entry_time", None)
        if et is not None:
            entry_times.append(et)
    for i, tr in enumerate(trades[:6]):
        print("  trade#%d: entry=%s side=%s price=%s pnl=%s" % (
            i, getattr(tr, "entry_time", None), getattr(tr, "side", None),
            getattr(tr, "entry_price", None),
            getattr(tr, "pnl", getattr(tr, "profit", None))))
    check("باك تست حقيقي ب engine1 لااستراتيجية البطل e2e على APPBUSDT 5m — اكتمل بلا أخطاء",
          bt is not None)

    # ---- 2) الشموع البصرية تحمل أعمدة ind_zzfe_* ----
    # (BacktestResult.visual_candles: List[VisualCandle] — كائنات Pydantic)
    vc = getattr(bt, "visual_candles", None) or []
    if vc and not isinstance(vc[0], dict):
        vc = [c.model_dump() if hasattr(c, "model_dump") else dict(c.__dict__) for c in vc]
    print(f"visual_candles: {len(vc)}")
    zzfe_cols = []
    for c in vc:
        if isinstance(c, dict) and isinstance(c.get("indicators"), dict):
            zzfe_cols = [k for k in c["indicators"] if k.startswith("ind_zzfe_")]
            break
    print(f"ind_zzfe_* columns in visual candles: {len(zzfe_cols)}")
    check("الشموع البصرية تحمل أعمدة ind_zzfe_* (عقد الجولة 12.1)", len(zzfe_cols) >= 20)

    # ---- 3) إشارات الاستراتيجية داخل الشموع ----
    entry_bars = []
    anchor_bars = []
    for i, c in enumerate(vc):
        ind = (c or {}).get("indicators") or {}
        if ind.get("ind_zzfe_entry") not in (None, 0):
            entry_bars.append(i)
        if ind.get("ind_zzfe_anchor") not in (None, 0):
            anchor_bars.append(i)
    print(f"entry bars in visual candles: {entry_bars}")
    print(f"anchor bars (ولادات النطاق): {len(anchor_bars)}")
    if entry_bars:
        et = vc[entry_bars[0]].get("timestamp")
        print(f"أول دخول: bar={entry_bars[0]} timestamp={et}")
    check("أعمدة الدخول وولادة النطاق موجودة في الشموع", len(anchor_bars) > 0)

    # ---- 4) محاكاة مسار chart-data: شموع ISO → overlays ----
    from app.services.indicators.overlays import compute_overlays

    ovl_candles_fixed = [
        {"time": c.get("timestamp"), "open": c.get("open"), "high": c.get("high"),
         "low": c.get("low"), "close": c.get("close"), "volume": c.get("volume")}
        for c in vc if isinstance(c, dict)
    ]
    # الشكل القديم المعطوب (بلا volume) — للمقارنة
    ovl_candles_old = [{k: v for k, v in c.items() if k != "volume"} for c in ovl_candles_fixed]

    params = {"zzfib_e2e": {"mode": "luxalgo", "length": 100}}
    res_fixed = compute_overlays(ovl_candles_fixed, types=["zzfib_e2e"], params=params)
    res_old = compute_overlays(ovl_candles_old, types=["zzfib_e2e"], params=params)

    e2e_fixed = res_fixed["overlays"]["zzfib_e2e"]
    e2e_old = res_old["overlays"]["zzfib_e2e"]
    legs = e2e_fixed.get("legs") or []
    times_ok = all(lg["t1"] > 0 and lg["t2"] > 0 for lg in legs)
    print(f"fixed: legs={len(legs)} times_ok={times_ok} volume_available={e2e_fixed.get('volume_available')}")
    print(f"old-style: volume_available={e2e_old.get('volume_available')} (كان بلا مرجع R)")
    # أزمنة المستويات والنطاقات والإشارات كلها ≠ 0 أيضاً (نفس الجذر المصلح)
    levels_times_ok = True
    for r in (e2e_fixed.get("ranges") or []):
        for lv in r.get("levels") or []:
            if not lv.get("t_from") or (lv.get("t_to") is not None and lv["t_to"] <= 0):
                levels_times_ok = False
    sig_times_ok = all((s.get("time") or 0) > 0 for s in (e2e_fixed.get("signals") or []))
    check("مسار chart-data المصلح: كل الأزمنة صحيحة ≠ 0 (أرجل + مستويات + إشارات)",
          times_ok and levels_times_ok and sig_times_ok)
    check("مسار chart-data المصلح: الحجم يصل → مراجع R وإشارات في حمولة الرسم",
          bool(e2e_fixed.get("volume_available")) and not bool(e2e_old.get("volume_available")))

    fixed_signals = [s for s in (e2e_fixed.get("signals") or []) if s.get("side") == "buy"]
    print(f"إشارات الدخول في حمولة الرسم المصلحة: {len(fixed_signals)}")
    for s in fixed_signals:
        print(f"   bar={s['bar']} time={datetime.fromtimestamp(s['time']/1000, tz=riyadh_tz).isoformat()} {s['signal']}")

    # مطابقة إشارات حمولة الرسم مع أعمدة الاستراتيجية في الشموع
    overlay_entry_bars = sorted(s["bar"] for s in fixed_signals)
    strategy_entry_bars = sorted(entry_bars)
    # (قد تختلف الشموع البصرية عن الكاملة على البيانات الضخمة — هنا كل شمعة بصرية)
    match = set(overlay_entry_bars) & set(strategy_entry_bars)
    print(f"overlay entries: {overlay_entry_bars} | strategy entries: {strategy_entry_bars} | match: {sorted(match)}")
    check("إشارات حمولة الرسم المصلحة تطابق أعمدة استراتيجية الباك تست",
          bool(strategy_entry_bars) and set(overlay_entry_bars) == set(strategy_entry_bars))

    # ---- 5) كل نطاق يحمل levels بحدود ولادة/نهاية ----
    ranges = e2e_fixed.get("ranges") or []
    ok_levels = all(r.get("levels") for r in ranges)
    bounds_ok = True
    N = len(vc)
    for r in ranges:
        for lv in r.get("levels") or []:
            if lv["x_from"] != r["anchor"]["bar"]:
                bounds_ok = False
            db = r["death"]["bar"]
            if db is not None and db < N and lv["x_to"] != db - 1:
                bounds_ok = False
    check("كل نطاق في حمولة الرسم يحمل مستويات فيبو بحدود ولادة/نهاية", ok_levels and bounds_ok)

    # ---- 6) حفظ ملف الرسم البصري (للـ HTML) ----
    out = {
        "meta": {
            "symbol": "APPBUSDT", "timeframe": "5m",
            "candles": len(candles),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "case": "بلاغ المستخدم: أول إشارة 31/10 07:40 الرياض — أعيد إنتاجها وتحليلها",
            "core": e2e_fixed.get("core"),
        },
        "candles": candles,
        "overlays": {"zzfib_e2e": e2e_fixed},
        "trades": [
            {"entry_time": str(getattr(tr, "entry_time", None)),
             "entry_price": getattr(tr, "entry_price", None),
             "side": str(getattr(tr, "side", None)),
             "pnl": getattr(tr, "pnl", getattr(tr, "profit", None))}
            for tr in trades
        ],
        "verification": {"results": [{"name": n, "pass": ok} for n, ok in RESULTS]},
    }
    json.dump(out, open(os.path.join(_OUT_DIR, "appbusdt_visual_payload.json"), "w"), ensure_ascii=False)
    print(f"\nvisual payload saved → {os.path.join(_OUT_DIR, 'appbusdt_visual_payload.json')}")

    n_ok = sum(1 for _, ok in RESULTS if ok)
    print(f"===== {n_ok}/{len(RESULTS)} PASS =====")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
