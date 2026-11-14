#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A/B — الترندية (بطل +1651.25% · 63 صفقة) مقابل «الترندية الماكدية»
على نافذة البطل الكاملة (665,099 شمعة · SOLUSDT 1m · 2023-10-16 → 2025-01-19T20:58Z).

أمر صاحب القرار (2026-11-14): «اختبر الماكديه مع الترنديه اللي كانت جايبه 1651
و63 صفقه — جرب الحين مع الماكديه وشوف كم ستقل الصفقات ومتوسط مده الصفقه
والنسبه كم ستصبح وكم ستتقلص عدد الصفقات».

التصميم (عزل الذاكرة — جهاز 4GB): كل مرحلة بعملية مستقلة عبر argv:
  validate   — تحقق بت-بت: البوابة السريعة (numpy مباشرة) مقابل مسار الإنتاج
               macdized_layer كاملاً (بجولة JSON) على آخر 20k شمعة.
  gate       — البوابة السريعة على النافذة كاملة → /tmp/ab-pro73/gate.npy
  base-hero  — إشارات الترندية الحالية (حمولة البطل الحرفية) على النافذة كاملة
               (columns_for_configs — نفس مرحلة التحقق التاريخية) → sig.npy + s1s2s3.npy
  base-preset— الإشارة الداخلية لمحرك الماكدية (zigzag_fib_e2e_trendy بمعاملات
               القالب حرفياً — نفس النداء الذي ي executeه المحرك الماكدي) → sig_preset.npy
  sim        — المحاكي الحرفي (TP 4.7% · SL 49% · N=1 · next_open — نسخة مطابقة
               حرفياً من مختبر R67) على: snapshot / current / current∧gate /
               snapshot∧gate + إحصاءات كاملة → r73-evidence/ab-macdized-fullwindow.json

لماذا «البوابة السريعة»؟ مسار الإنتاج (macdized_layer) يبني كل الحقول الـ235
كقوائم Python (~4.3GB على النافذة الكاملة — خارج قدرة الجهاز). البوابة السريعة
تستدعي نفس الدوال الحرفية (resample_ohlcv/_macd/_rsi_wilder/_momentum/
evaluate_osc_conditions) لكن تحتفظ بالمصفوفات numpy فقط للحقول التي تشير
إليها الشجرة (macd.line · rsi.value · mom.line) — وتتحقق بت-بت في مرحلة
validate ضد مسار الإنتاج نفسه.
"""
import copy
import gc as _gc
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [os.path.join(HERE, ".."), os.path.join(HERE, "..", "src"), HERE]
SRC = next((p for p in CANDIDATES
            if os.path.isfile(os.path.join(p, "app", "services", "indicators", "mtf_oscillator_core.py"))),
           CANDIDATES[0])
sys.path.insert(0, os.path.abspath(SRC))
sys.path.insert(0, HERE)

os.environ.setdefault("SECRET_KEY", "ab-macdized-secret-key-0123456789")
os.environ.setdefault("DEBUG", "true")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DATA_R70 = "/home/z/my-project/r70-workspace/data/SOLUSDT_1m.npz"
SIG_REF = "/home/z/my-project/r67-workspace/data/sig_SOL_bull.npz"
CHAMP_TO = 1737320280000            # 2025-01-19T20:58:00Z — آخر شمعة في نافذة البطل
OUT_DIR = "/tmp/ab-pro73"
REF_PNL_SNAPSHOT = 1651.2531087256748
REF_TRADES = 63
REF_PNL_CURRENT = 1560.1369220073775  # إشارات الكود الحالي (المرحلة H3 التاريخية)

os.makedirs(OUT_DIR, exist_ok=True)


def _trim():
    _gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def _mem(tag):
    with open("/proc/meminfo") as fh:
        mi = {ln.split(":")[0]: int(ln.split()[1]) for ln in fh if ":" in ln}
    print(f"    [mem:{tag}] MemAvailable={mi['MemAvailable']/1024:.0f}MB")


def load_window(from_ms=None, to_ms=CHAMP_TO):
    z = np.load(DATA_R70)
    t_all = z["time_ms"].astype(np.int64)
    if from_ms is None:
        z_ref = np.load(SIG_REF)
        from_ms = int(z_ref["time_ms"][0])
        del z_ref
    m = (t_all >= from_ms) & (t_all <= to_ms)
    T = t_all[m]
    O = z["open"][m].astype(np.float64)
    H = z["high"][m].astype(np.float64)
    L = z["low"][m].astype(np.float64)
    C = z["close"][m].astype(np.float64)
    V = z["volume"][m].astype(np.float64)
    del z, t_all, m
    _trim()
    return T, O, H, L, C, V


def make_df(T, O, H, L, C, V):
    return pd.DataFrame({"open": O, "high": H, "low": L, "close": C, "volume": V},
                        index=pd.DatetimeIndex(pd.to_datetime(T, unit="ms", utc=True), name="time"))


# ===========================================================================
# المحاكي الحرفي — نسخة مطابقة حرفياً من مختبر R67 (lab/sim.py)
# (المُصادَق على 7 مراجع إنتاجية حية بفرق 0.00e+00 — لا يُعدَّل حرف واحد)
# ===========================================================================
def simulate(o, h, l, c, sig, *, initial=100.0, tp_pct=4.7, sl_pct=49.0,
             trail_pct=None, max_positions=1, multi_compounding=True,
             collect_trades=False):
    o = np.ascontiguousarray(o, dtype=np.float64)
    h = np.ascontiguousarray(h, dtype=np.float64)
    l = np.ascontiguousarray(l, dtype=np.float64)
    c = np.ascontiguousarray(c, dtype=np.float64)
    sig = np.ascontiguousarray(sig, dtype=bool)
    n = len(o)

    tp_active = tp_pct is not None and float(tp_pct) > 0.0
    sl_active = sl_pct is not None and 0.0 < float(sl_pct) < 100.0
    trail_active = trail_pct is not None and float(trail_pct) > 0.0
    if trail_active:
        sl_active = False
        tp_active = False
    tp_frac = (float(tp_pct) / 100.0) if tp_active else None
    sl_frac = (float(sl_pct) / 100.0) if sl_active else None
    trail_frac = (float(trail_pct) / 100.0) if trail_active else None

    if multi_compounding:
        N = int(max_positions) if max_positions else 1
        if N < 1:
            N = 1
        if N > 10:
            N = 10
        frac = 1.0 / float(N)
    else:
        N = 1
        frac = 1.0

    balance = float(initial)
    trades = []
    pos = None
    extras = []
    pending = False

    def _close(p, price, i, reason):
        nonlocal balance
        if p["dir"] == "long":
            pnl = (price - p["entry"]) * p["size"]
        else:
            pnl = (p["entry"] - price) * p["size"]
        inv = p["entry"] * p["size"]
        pct = (pnl / inv) * 100.0 if inv else 0.0
        balance += pnl
        if collect_trades:
            trades.append({
                "entry_time": int(p["t_in"]), "exit_idx": i, "dir": p["dir"],
                "entry": float(p["entry"]), "exit": float(price), "size": float(p["size"]),
                "pnl": float(pnl), "pnl_pct": float(pct), "reason": reason,
                "extra": p.get("extra", False),
            })
        return pnl

    def _mkpos(price, i, extra):
        size = balance * frac / price if price else 0.0
        if sl_active and sl_frac is not None:
            off = price * sl_frac
            sl = price - off
        else:
            sl = 0.0
        if tp_active and tp_frac is not None:
            off = price * tp_frac
            tp = price + off
        else:
            tp = 0.0
        return {"dir": "long", "entry": price, "size": size, "sl": sl, "tp": tp,
                "t_in": i, "trail_peak": price, "extra": extra}

    for i in range(n):
        entering = False
        if pending and pos is None and balance > 0:
            pos = _mkpos(o[i], i, extra=False)
            entering = True
        elif (pending and pos is not None and N > 1 and not entering
              and (1 + len(extras)) < N and balance > 0):
            extras.append(_mkpos(o[i], i, extra=True))
        pending = False

        if pos is not None:
            exit_price = None
            reason = None
            if trail_active and trail_frac is not None:
                if h[i] > pos["trail_peak"]:
                    pos["trail_peak"] = h[i]
                if c[i] <= pos["trail_peak"] * (1.0 - trail_frac):
                    exit_price = c[i]
                    reason = "Trailing Stop"
            if exit_price is None and sl_active and l[i] <= pos["sl"]:
                exit_price = pos["sl"]
                reason = "Stop Loss Hit"
            elif exit_price is None and tp_active and h[i] >= pos["tp"]:
                exit_price = pos["tp"]
                reason = "Take Profit Hit"
            if exit_price is not None:
                _close(pos, exit_price, i, reason)
                pos = None

        if extras:
            still = []
            for x in extras:
                exit_price = None
                reason = None
                if trail_active and trail_frac is not None:
                    if h[i] > x["trail_peak"]:
                        x["trail_peak"] = h[i]
                    if c[i] <= x["trail_peak"] * (1.0 - trail_frac):
                        exit_price = c[i]
                        reason = "Trailing Stop (additional position)"
                if exit_price is None and sl_active and l[i] <= x["sl"]:
                    exit_price = x["sl"]
                    reason = "Stop Loss Hit (additional position)"
                elif exit_price is None and tp_active and h[i] >= x["tp"]:
                    exit_price = x["tp"]
                    reason = "Take Profit Hit (additional position)"
                if exit_price is not None:
                    _close(x, exit_price, i, reason)
                else:
                    still.append(x)
            extras = still

        pending = bool(sig[i])

    if pos is not None:
        _close(pos, c[n - 1], n - 1, "End of Data")
        pos = None
    for x in extras:
        _close(x, c[n - 1], n - 1, "End of Data")
    extras = []
    if balance < 0:
        balance = 0.0

    return {
        "final_capital": balance,
        "total_pnl_percent": (balance / float(initial) - 1.0) * 100.0,
        "n_trades": len(trades),
        "trades": trades,
    }


# ===========================================================================
# البوابة السريعة — نفس دوال mtf_oscillator_core حرفياً لكن بلا جولة قوائم JSON
# (الحقول المحسوبة: macd.line · rsi.value · mom.line — كل ما تشير إليه الشجرة)
# ===========================================================================
def fast_gate(df, instances, conditions):
    from app.services.indicators.zigzag_fib_core import norm_candles, norm_volume
    from app.services.indicators.mtf_oscillator_core import (
        TF_DURATIONS, normalize_osc_instances, normalize_osc_conditions,
        evaluate_osc_conditions, resample_ohlcv, infer_base_step_ms,
        _rsi_wilder, _macd, _momentum,
    )

    t, o, h, l, c = norm_candles(df)
    N = len(c)
    t_i = np.asarray([int(x) for x in t], dtype=np.int64) if N else np.zeros(0, dtype=np.int64)
    o_f = np.asarray([float(x) if x is not None else np.nan for x in o], dtype=np.float64) if N else np.zeros(0)
    h_f = np.asarray([float(x) if x is not None else np.nan for x in h], dtype=np.float64) if N else np.zeros(0)
    l_f = np.asarray([float(x) if x is not None else np.nan for x in l], dtype=np.float64) if N else np.zeros(0)
    c_f = np.asarray([float(x) if x is not None else np.nan for x in c], dtype=np.float64) if N else np.zeros(0)
    del t, o, h, l, c
    try:
        vols = norm_volume(df)
        v_f = np.asarray([float(x) if x is not None else 0.0 for x in vols], dtype=np.float64) if N else np.zeros(0)
    except Exception:
        v_f = np.zeros(0 if not N else N, dtype=np.float64)
    if N and len(v_f) != N:
        v_f = np.zeros(N, dtype=np.float64)

    base_step = infer_base_step_ms(t_i) if N else 60_000
    eval_ms = (t_i + base_step).astype(np.int64) if N else np.zeros(0, dtype=np.int64)
    insts, warnings = normalize_osc_instances(instances)

    tf_cache = {}

    def _tf_bars(tf):
        if tf not in tf_cache:
            tf_cache[tf] = resample_ohlcv(t_i, o_f, h_f, l_f, c_f, v_f if N else None, tf)
        return tf_cache[tf]

    def _map_to_base(vals, close_ms):
        if N == 0 or len(vals) == 0:
            return np.full(N, np.nan)
        idx = np.searchsorted(close_ms, eval_ms, side="right") - 1
        out = np.full(N, np.nan)
        ok = idx >= 0
        out[ok] = vals[idx[ok]]
        return out

    osc_np = {}
    osc_available = {}
    for k, inst in enumerate(insts):
        rid = inst["id"]
        kind = inst["kind"]
        if not inst.get("enabled", True):
            osc_available[rid] = False
            osc_np[rid] = {"line": np.full(N, np.nan) if kind != "rsi" else np.full(N, np.nan)}
            continue
        tf = inst["timeframe"]
        tf_ms = int(TF_DURATIONS[tf])
        p = inst["params"]
        if tf_ms and tf_ms < base_step:
            osc_available[rid] = False
            field = "value" if kind == "rsi" else "line"
            osc_np[rid] = {field: np.full(N, np.nan)}
            continue
        if tf_ms and tf_ms == base_step:
            bars_close = c_f
            close_ms = eval_ms
        else:
            bars = _tf_bars(tf)
            bars_close = bars["close"]
            close_ms = bars["close_ms"]
        if kind == "macd":
            line, _sig, _hist = _macd(bars_close, int(p["fast"]), int(p["slow"]), int(p["signal"]))
            osc_np[rid] = {"line": _map_to_base(line, close_ms)}
        elif kind == "rsi":
            vals = _rsi_wilder(bars_close, int(p["period"]))
            osc_np[rid] = {"value": _map_to_base(vals, close_ms)}
        else:
            line, _pct = _momentum(bars_close, int(p["length"]))
            osc_np[rid] = {"line": _map_to_base(line, close_ms)}
        osc_available[rid] = True
        if (k + 1) % 10 == 0:
            print(f"    ... نسخة {k+1}/{len(insts)} ({rid})")
            _trim()

    tree, tree_warns = normalize_osc_conditions(conditions)
    gate, gate_warns = evaluate_osc_conditions(
        tree, osc_np, o_f, h_f, l_f, c_f, N, osc_available=osc_available)
    all_warns = list(warnings) + list(tree_warns) + list(gate_warns)
    return gate.astype(bool), all_warns


# ===========================================================================
PHASE = sys.argv[1] if len(sys.argv) > 1 else "sim"

if PHASE == "validate":
    # ------------------------------------------------------------------
    print("=== VALIDATE: البوابة السريعة بت-بت مقابل macdized_layer (آخر 20k شمعة) ===")
    from app.services.indicators.mtf_oscillator_core import macdized_layer
    from app.services.indicators.osc_cases import OSC_DOC_INSTANCES, MASTER_ANY_CASE

    T, O, H, L, C, V = load_window(CHAMP_TO - 20_000 * 60_000, CHAMP_TO)
    df = make_df(T, O, H, L, C, V)
    print(f"  نافذة التحقق: {len(df):,} شمعة")
    _mem("قبل الإنتاج")
    t0 = time.perf_counter()
    layer = macdized_layer(df, OSC_DOC_INSTANCES, MASTER_ANY_CASE)
    prod_gate = layer["gate"]
    print(f"  مسار الإنتاج: {time.perf_counter()-t0:.1f}s · gate True={int(prod_gate.sum()):,}")
    prod_warns = list(layer["warnings"])
    _trim()
    _mem("بعد الإنتاج")
    t0 = time.perf_counter()
    fast, fast_warns = fast_gate(df, OSC_DOC_INSTANCES, MASTER_ANY_CASE)
    print(f"  البوابة السريعة: {time.perf_counter()-t0:.1f}s · gate True={int(fast.sum()):,}")
    same = bool((prod_gate == fast).all())
    print(f"  بت-بت مطابقة: {same} (فروق={int((prod_gate != fast).sum())})")
    print(f"  تحذيرات الإنتاج={len(prod_warns)} · السريعة={len(fast_warns)}")
    for w in fast_warns:
        if "غير قابل للحل" in w:
            print(f"  ⚠️ {w}")
    sys.exit(0 if same else 1)

elif PHASE == "gate":
    # ------------------------------------------------------------------
    print("=== GATE: البوابة على نافذة البطل كاملة (665,099 شمعة) ===")
    from app.services.indicators.osc_cases import OSC_DOC_INSTANCES, MASTER_ANY_CASE

    T, O, H, L, C, V = load_window()
    print(f"  النافذة: {len(T):,} شمعة")
    _mem("قبل البوابة")
    t0 = time.perf_counter()
    gate, warns = fast_gate(make_df(T, O, H, L, C, V), OSC_DOC_INSTANCES, MASTER_ANY_CASE)
    print(f"  زمن البوابة: {time.perf_counter()-t0:.1f}s · gate True={int(gate.sum()):,}/{len(gate):,}"
          f" ({gate.sum()/len(gate)*100:.2f}%)")
    np.save(os.path.join(OUT_DIR, "gate.npy"), gate)
    with open(os.path.join(OUT_DIR, "gate-warnings.json"), "w") as fh:
        json.dump(warns, fh, ensure_ascii=False, indent=1)
    bad = [w for w in warns if "غير قابل للحل" in w]
    print(f"  تحذيرات: {len(warns)} (غير قابلة للحل: {len(bad)})")
    for w in bad[:5]:
        print(f"    ⚠️ {w}")
    _trim()
    _mem("بعد البوابة")
    sys.exit(0 if not bad else 1)

elif PHASE in ("base-hero", "base-preset"):
    # ------------------------------------------------------------------
    if PHASE == "base-hero":
        print("=== BASE-HERO: إشارات الترندية الحالية — حمولة البطل (columns_for_configs) ===")
        HERO_CFG = {
            "name": "zigzag_fib_e2e_trendy",
            "type": "support_resistance",
            "params": {
                "mode": "luxalgo",
                "length": 100,
                "touch_level": 0.618,
                "trend_periods": "7,15,25",
                "trend_confirm": "majority",
                "trend_gate": "s1,s2,s3",
            },
            "enabled": True,
            "timeframe": "1m",
        }
        from app.services.indicators.overlay_columns import columns_for_configs
        T, O, H, L, C, V = load_window()
        print(f"  النافذة: {len(T):,} شمعة")
        _mem("قبل الحساب")
        df = make_df(T, O, H, L, C, V)
        t0 = time.perf_counter()
        cols = columns_for_configs(df, [HERO_CFG])
        print(f"  زمن الأعمدة: {time.perf_counter()-t0:.1f}s · أعمدة={len(cols)}")

        def _col_np(name, n=len(T)):
            v = cols.get(name) or []
            arr = np.asarray([0.0 if x is None else float(x) for x in v], dtype=np.float64)
            if len(arr) < n:
                arr = np.concatenate((arr, np.zeros(n - len(arr))))
            return arr[:n]

        s1 = _col_np("ind_zzfet_entry_s1") >= 0.5
        s2 = _col_np("ind_zzfet_entry_s2") >= 0.5
        s3 = _col_np("ind_zzfet_entry_s3") >= 0.5
        sig = s1 | s2 | s3
        np.save(os.path.join(OUT_DIR, "sig_hero.npy"), sig)
        np.save(os.path.join(OUT_DIR, "s123_hero.npy"), np.stack([s1, s2, s3]))
        print(f"  إشارات: {int(sig.sum()):,} (S1={int(s1.sum())} · S2={int(s2.sum())} · S3={int(s3.sum())})")
        del cols, df
        _trim()
        _mem("بعد الحساب")
    else:
        print("=== BASE-PRESET: الإشارة الداخلية للمحرك الماكدي (zigzag_fib_e2e_trendy بمعاملات القالب) ===")
        from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy
        T, O, H, L, C, V = load_window()
        print(f"  النافذة: {len(T):,} شمعة")
        _mem("قبل الحساب")
        df = make_df(T, O, H, L, C, V)
        t0 = time.perf_counter()
        res = zigzag_fib_e2e_trendy(
            df, length=100, mode="luxalgo",
            trend_periods=[7, 15, 25], trend_confirm="majority", trend_gate=["s1", "s2", "s3"])
        print(f"  زمن المحرك: {time.perf_counter()-t0:.1f}s")
        ser = res.get("series") or {}
        N = len(T)

        def _col(name):
            v = ser.get(name) or []
            arr = np.asarray([0.0 if x is None else float(x) for x in v], dtype=np.float64)
            if len(arr) < N:
                arr = np.concatenate((arr, np.zeros(N - len(arr))))
            return arr[:N] >= 0.5

        s1 = _col("zzfet_entry_s1")
        s2 = _col("zzfet_entry_s2")
        s3 = _col("zzfet_entry_s3")
        sig = s1 | s2 | s3
        np.save(os.path.join(OUT_DIR, "sig_preset.npy"), sig)
        np.save(os.path.join(OUT_DIR, "s123_preset.npy"), np.stack([s1, s2, s3]))
        print(f"  إشارات: {int(sig.sum()):,} (S1={int(s1.sum())} · S2={int(s2.sum())} · S3={int(s3.sum())})")
        del res, ser, df
        _trim()
        _mem("بعد الحساب")
    sys.exit(0)

elif PHASE == "sim":
    # ------------------------------------------------------------------
    print("=== SIM: المحاكي الحرفي — A/B كامل على نافذة البطل ===")
    T, O, H, L, C, V = load_window()
    gate = np.load(os.path.join(OUT_DIR, "gate.npy"))
    sig_hero = np.load(os.path.join(OUT_DIR, "sig_hero.npy"))
    sig_preset = np.load(os.path.join(OUT_DIR, "sig_preset.npy"))
    s123_hero = np.load(os.path.join(OUT_DIR, "s123_hero.npy"))
    z_ref = np.load(SIG_REF)
    sig_snap = ((np.nan_to_num(z_ref["ind_zzfet_entry_s1"].astype(np.float64), nan=0.0) > 0)
                | (np.nan_to_num(z_ref["ind_zzfet_entry_s2"].astype(np.float64), nan=0.0) > 0)
                | (np.nan_to_num(z_ref["ind_zzfet_entry_s3"].astype(np.float64), nan=0.0) > 0))
    print(f"  النافذة: {len(T):,} · بوابة الماكد مفتوحة {int(gate.sum()):,} ({gate.sum()/len(gate)*100:.2f}%)")
    print(f"  hero==preset بت-بت: {bool((sig_hero == sig_preset).all())}"
          f" (فروق={int((sig_hero != sig_preset).sum())})")

    def stats(r, label, base=None):
        tr = r["trades"]
        n = len(tr)
        wins = sum(1 for x in tr if x["pnl"] > 0)
        durs_bars = [x["exit_idx"] - x["entry_time"] for x in tr]
        durs_min = [d * 1.0 for d in durs_bars]  # 1m candles
        reasons = {}
        for x in tr:
            reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1
        out = {
            "label": label,
            "total_pnl_percent": r["total_pnl_percent"],
            "final_capital": r["final_capital"],
            "n_trades": n,
            "wins": wins,
            "win_rate_pct": round(wins / n * 100, 2) if n else None,
            "avg_trade_pnl_pct": round(sum(x["pnl_pct"] for x in tr) / n, 4) if n else None,
            "avg_duration_min": round(sum(durs_min) / n, 1) if n else None,
            "median_duration_min": round(float(np.median(durs_min)), 1) if n else None,
            "min_duration_min": round(min(durs_min), 1) if n else None,
            "max_duration_min": round(max(durs_min), 1) if n else None,
            "exit_reasons": reasons,
        }
        if n:
            buckets = {"<1h": 0, "1-6h": 0, "6-24h": 0, "1-3d": 0, ">3d": 0}
            for d in durs_min:
                if d < 60:
                    buckets["<1h"] += 1
                elif d < 360:
                    buckets["1-6h"] += 1
                elif d < 1440:
                    buckets["6-24h"] += 1
                elif d < 4320:
                    buckets["1-3d"] += 1
                else:
                    buckets[">3d"] += 1
            out["duration_buckets"] = buckets
        print(f"\n  [{label}]")
        print(f"    العائد: +{r['total_pnl_percent']:.4f}% · رأس المال: {r['final_capital']:.4f}")
        print(f"    الصفقات: {n} · رابحة: {wins} · نسبة الربح: {out['win_rate_pct']}%")
        print(f"    متوسط الصفقة: {out['avg_trade_pnl_pct']}% · متوسط المدة: "
              f"{(out['avg_duration_min'] or 0)/60:.1f}h · وسيطها: {(out['median_duration_min'] or 0)/60:.1f}h")
        if out.get("duration_buckets"):
            print(f"    توزيع المدة: {out['duration_buckets']}")
        print(f"    أسباب الخروج: {reasons}")
        return out

    results = {}

    r = simulate(O, H, L, C, sig_snap, initial=100.0, tp_pct=4.7, sl_pct=49.0,
                 max_positions=1, multi_compounding=True, collect_trades=True)
    ok_snap = abs(r["total_pnl_percent"] - REF_PNL_SNAPSHOT) < 1e-9 and r["n_trades"] == REF_TRADES
    print(f"\n  مرساة 1 (snapshot): {r['total_pnl_percent']!r} / {r['n_trades']} — مطابقة للمرجع: {ok_snap}")
    results["A_snapshot_trendy"] = stats(r, "A · الترندية (لقطة البطل المصادَقة)")

    r = simulate(O, H, L, C, sig_hero, initial=100.0, tp_pct=4.7, sl_pct=49.0,
                 max_positions=1, multi_compounding=True, collect_trades=True)
    ok_cur = r["n_trades"] == REF_TRADES and abs(r["total_pnl_percent"] - REF_PNL_CURRENT) < 1e-6
    print(f"\n  مرساة 2 (current): {r['total_pnl_percent']!r} / {r['n_trades']} — مطابقة للمرجع: {ok_cur}")
    results["B_current_trendy"] = stats(r, "B · الترندية (كود حالي — خط الأساس)")

    sig_gated = sig_hero & gate
    r = simulate(O, H, L, C, sig_gated, initial=100.0, tp_pct=4.7, sl_pct=49.0,
                 max_positions=1, multi_compounding=True, collect_trades=True)
    results["C_current_macdized"] = stats(r, "C · الترندية الماكدية (كود حالي + بوابة الماكد)")

    sig_gated_snap = sig_snap & gate
    r = simulate(O, H, L, C, sig_gated_snap, initial=100.0, tp_pct=4.7, sl_pct=49.0,
                 max_positions=1, multi_compounding=True, collect_trades=True)
    results["D_snapshot_macdized"] = stats(r, "D · الترندية الماكدية (لقطة البطل + بوابة الماكد)")

    # كم من صفقات البطل الـ63 مرّ شريط إشارتها عبر البوابة؟
    rB = simulate(O, H, L, C, sig_hero, initial=100.0, tp_pct=4.7, sl_pct=49.0,
                  max_positions=1, multi_compounding=True, collect_trades=True)
    passed = sum(1 for x in rB["trades"] if gate[x["entry_time"]])
    results["hero_trades_gate_pass"] = {"trades": len(rB["trades"]), "gate_passed": passed}
    print(f"\n  من صفقات خط الأساس: {passed}/{len(rB['trades'])} شريط إشارتها مرّ عبر بوابة الماكد")

    results["signals"] = {
        "snapshot_signals": int(sig_snap.sum()),
        "current_signals": int(sig_hero.sum()),
        "current_gated_signals": int((sig_hero & gate).sum()),
        "signal_reduction_pct": round((1 - (sig_hero & gate).sum() / max(1, sig_hero.sum())) * 100, 2),
        "gate_open_pct": round(gate.sum() / len(gate) * 100, 2),
    }
    results["anchors_ok"] = {"snapshot": bool(ok_snap), "current": bool(ok_cur)}

    out_path = os.path.join(HERE, "r73-evidence", "ab-macdized-fullwindow.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\n  الأدلة: {out_path}")
    sys.exit(0 if (ok_snap and ok_cur) else 1)

else:
    print(f"مرحلة مجهولة: {PHASE}")
    sys.exit(2)
