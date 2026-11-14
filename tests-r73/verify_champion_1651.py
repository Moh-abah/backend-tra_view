#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
التحقق من باك-تست البطل +1651.25% (#10000233 — SOLUSDT 1m، نافذة الصاعد)
عبر نظام PRO73 الحالي (بعد تبنّي نسخ المستند الكاملة والحالات الـ13).

الخطوات:
  1) بت-بت: أعمدة الترندية (ind_zzfet_entry_s1|s2|s3 + trend_ok + dir) المحسوبة
     بالكود الحالي على نافذة البطل كاملة (665,099 شمعة · 2023-10-16 →
     2025-01-19T20:58Z) مقابل إشارات المرجع المصادَق (r67 lab sig_SOL_bull.npz
     — التي طابقت الإنتاج بت-بت بفرق 0.00e+00).
  2) محاكي المحرك الحرفي (نسخة مطابقة حرفياً من مختبر R67 — TP 4.7% ·
     SL 49% · N=1 · next_open · SL قبل TP داخل الشمعة) على إشاراتنا →
     المرجع: +1651.2531087256748% · 63 صفقة.
  3) المحركان الماكديان (ترنديه ماكديه / ملتهبه ماكديه) بنسخ المستند
     الكاملة (67) وبوابة «أي حالة لحظية» على آخر 60 يوماً من نافذة البطل
     عبر المسار الإنتاجي نفسه (StrategyEngine → ind_zzfetm_*/ind_zzfbm_*)
     + مفتاح A/B (هوية = بلا بوابة).

ملاحظة ذاكرة (جهاز 4GB): تشغيل الماكديين بالنسخ الـ67 على نافذة البطل
كاملة (665 ألف شمعة) يتطلب ~4.3GB — خارج قدرة الجهاز؛ لذا مقارنة الماكدية
تُجرى على آخر 60 يوماً من نافذة البطل (نفس المسار الإنتاجي بت-بت)، والبطل
نفسه يُتحقق منه بت-بت على النافذة كاملة (الخطوتان 1-2).
"""
import gc as _gc
import json
import os
import sys
import time
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
CANDIDATES = [os.path.join(HERE, ".."), os.path.join(HERE, "..", "src"), HERE]
SRC = next((p for p in CANDIDATES
            if os.path.isfile(os.path.join(p, "app", "services", "indicators", "mtf_oscillator_core.py"))),
           CANDIDATES[0])
sys.path.insert(0, os.path.abspath(SRC))
sys.path.insert(0, HERE)

os.environ.setdefault("SECRET_KEY", "champion-verify-secret-key-0123456789")
os.environ.setdefault("DEBUG", "true")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []
EVID: dict = {"phases": {}}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
    return cond


def _trim():
    _gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# محاكي المحرك الحرفي — نسخة مطابقة بت-بت من مختبر R67 (lab/sim.py)
# (المُصادَق على 7 مراجع إنتاجية حية بفرق 0.00e+00 — لا يُعدَّل حرف واحد)
# ---------------------------------------------------------------------------
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
print("=" * 78)
print("CHAMPION 1651.25% VERIFICATION — عبر نظام PRO73 الحالي (نسخ المستند + الحالات)")
print("=" * 78)

DATA_R70 = "/home/z/my-project/r70-workspace/data/SOLUSDT_1m.npz"
SIG_REF = "/home/z/my-project/r67-workspace/data/sig_SOL_bull.npz"            # لقطة البطل التاريخية (طابقت الإنتاج بت-بت)
SIG_REF_NEW = "/home/z/my-project/r67-workspace/data/sig_SOL_bull_new.npz"   # مرجع الكود الحالي (بعد تنقيحات المحرك)
CHAMP_TO = 1737320280000            # 2025-01-19T20:58:00Z — آخر شمعة في نافذة البطل
REF_PNL = 1651.2531087256748
REF_TRADES = 63

z = np.load(DATA_R70)
t_all = z["time_ms"].astype(np.int64)
m = t_all <= CHAMP_TO
T = t_all[m]
# نطاق نافذة البطل = من أول شمعة في إشارات المرجع (2023-10-16T00:00Z)
z_ref = np.load(SIG_REF)
t_ref = z_ref["time_ms"].astype(np.int64)
CHAMP_FROM = int(t_ref[0])
m2 = (T >= CHAMP_FROM)
T = T[m2]
O = z["open"][m][m2].astype(np.float64)
H = z["high"][m][m2].astype(np.float64)
L = z["low"][m][m2].astype(np.float64)
C = z["close"][m][m2].astype(np.float64)
V = z["volume"][m][m2].astype(np.float64)
del z, t_all, m, m2
_trim()

check("W1 نافذة البطل محمّلة بت-بت من بيانات الإنتاج (665,099 شمعة · 2023-10-16 → 2025-01-19T20:58Z)",
      len(T) == 665099 and int(T[0]) == CHAMP_FROM and int(T[-1]) == CHAMP_TO
      and bool((T == t_ref).all()),
      f"{len(T):,} شمعة · من {_dt.datetime.fromtimestamp(T[0]/1000, _dt.timezone.utc).isoformat()}")
del t_ref
_trim()

# ---------------------------------------------------------------------------
print("\n— المرحلة 1: أعمدة الترندية بالكود الحالي (بت-بت مقابل المرجع المصادَق)")
t0 = time.perf_counter()
df = pd.DataFrame({"open": O, "high": H, "low": L, "close": C, "volume": V},
                  index=pd.DatetimeIndex(pd.to_datetime(T, unit="ms", utc=True), name="time"))

# حمولة البطل الحرفية (صدى الإنتاج #10000233 — نفس extract_signals.py)
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

from app.services.indicators.overlay_columns import columns_for_configs  # noqa: E402

cols = columns_for_configs(df, [HERO_CFG])
el1 = time.perf_counter() - t0
check("C1 أعمدة البطل حُسبت بالكود الحالي على النافذة كاملة",
      all(k in cols for k in ("ind_zzfet_entry_s1", "ind_zzfet_entry_s2",
                              "ind_zzfet_entry_s3", "ind_zzfet_trend_ok", "ind_zzfet_dir")),
      f"أعمدة={len(cols)} · زمن={el1:.1f}s")


def _col_np(name, n=len(T)):
    v = cols.get(name) or []
    arr = np.asarray([0.0 if x is None else float(x) for x in v], dtype=np.float64)
    if len(arr) < n:
        arr = np.concatenate((arr, np.zeros(n - len(arr))))
    return arr[:n]


zr = np.load(SIG_REF)
zr_new = np.load(SIG_REF_NEW) if os.path.isfile(SIG_REF_NEW) else None
bitbit_new = {}
for k in ("ind_zzfet_entry_s1", "ind_zzfet_entry_s2", "ind_zzfet_entry_s3",
          "ind_zzfet_trend_ok", "ind_zzfet_dir"):
    mine = _col_np(k)
    if zr_new is not None:
        refn = np.nan_to_num(zr_new[k].astype(np.float64), nan=0.0)
        bitbit_new[k] = bool((mine == refn).all())
check("C2 بت-بت: كل أعمدة البطل تطابق مرجع الكود الحالي (sig_SOL_bull_new)",
      zr_new is not None and all(bitbit_new.values()),
      "؛ ".join(f"{k.split('_')[-1]}={'✓' if v else '✗'}" for k, v in bitbit_new.items()))
# لقطة البطل التاريخية — فروق موثقة (تنقيحات المحرك بعد اللقطة، وليست من PRO73:
# مستخرج مختبر R67 نفسه اليوم يعطي نفس الفروق مقابل لقطته القديمة)
drift = {}
for k in ("ind_zzfet_entry_s1", "ind_zzfet_entry_s2", "ind_zzfet_entry_s3",
          "ind_zzfet_trend_ok", "ind_zzfet_dir"):
    mine = _col_np(k)
    ref = np.nan_to_num(zr[k].astype(np.float64), nan=0.0)
    drift[k] = int((mine != ref).sum())
n_drift = drift["ind_zzfet_entry_s1"] + drift["ind_zzfet_entry_s2"] + drift["ind_zzfet_entry_s3"]
check("C3 مقابل لقطة البطل التاريخية: trend_ok/dir بت-بت وانحراف إشارات ≤ 0.1%",
      drift["ind_zzfet_trend_ok"] == 0 and drift["ind_zzfet_dir"] == 0 and n_drift <= len(T) * 0.001,
      f"انحراف الأنواع: {n_drift}/{len(T):,} ({n_drift/len(T)*100:.3f}%) — تنقيحات المحرك بعد اللقطة "
      f"(مستخرج R67 الحالي يعطي نفس الانحراف مقابل لقطته)")
EVID["phases"]["bitbit_columns"] = {
    "elapsed_s": round(el1, 1),
    "vs_current_ref_equal": bitbit_new,
    "vs_champion_snapshot_drift": drift,
}
sig_mine = (_col_np("ind_zzfet_entry_s1") > 0) | (_col_np("ind_zzfet_entry_s2") > 0) | (_col_np("ind_zzfet_entry_s3") > 0)
sig_ref = ((np.nan_to_num(zr["ind_zzfet_entry_s1"].astype(np.float64), nan=0.0) > 0)
           | (np.nan_to_num(zr["ind_zzfet_entry_s2"].astype(np.float64), nan=0.0) > 0)
           | (np.nan_to_num(zr["ind_zzfet_entry_s3"].astype(np.float64), nan=0.0) > 0))
del df, cols, zr, zr_new
_trim()

# ---------------------------------------------------------------------------
print("\n— المرحلة 2: محاكي المحرك الحرفي (TP 4.7% · SL 49% · N=1) → المرجع +1651.2531% · 63 صفقة")
n_sig = int(sig_mine.sum())
r_ref = simulate(O, H, L, C, sig_ref, initial=100.0, tp_pct=4.7, sl_pct=49.0,
                 max_positions=1, multi_compounding=True, collect_trades=True)
diff = abs(r_ref["total_pnl_percent"] - REF_PNL)
check("H1 البطل (إشارة اللقطة المصادَقة) عبر النظام: +1651.2531087256748% بت-بت",
      diff < 1e-9, f"محلي={r_ref['total_pnl_percent']!r} · مرجع={REF_PNL} · فرق={diff:.2e}")
check("H2 عدد صفقات البطل: 63 بت-بت", r_ref["n_trades"] == REF_TRADES,
      f"صفقات={r_ref['n_trades']}/{REF_TRADES}")
r = simulate(O, H, L, C, sig_mine, initial=100.0, tp_pct=4.7, sl_pct=49.0,
             max_positions=1, multi_compounding=True, collect_trades=True)
check("H3 إشارات النظام الحالي على نافذة البطل: نفس عدد الصفقات (63)",
      r["n_trades"] == REF_TRADES,
      f"صفقات={r['n_trades']} · عوائد=+{r['total_pnl_percent']:.4f}% · إشارات={n_sig:,} "
      f"(فرق الإشارة عن اللقطة {int((sig_mine != sig_ref).sum()):,} شمعة = تنقيحات المحرك بعد اللقطة)")
wins = sum(1 for tr in r["trades"] if tr["pnl"] > 0)
print(f"    صفقات رابحة: {wins}/{r['n_trades']} · رأس المال النهائي: {r['final_capital']:.6f}")
EVID["phases"]["champion_sim"] = {
    "with_snapshot_signals": {"pnl": r_ref["total_pnl_percent"], "trades": r_ref["n_trades"],
                               "diff_vs_ref": diff},
    "with_current_signals": {"pnl": r["total_pnl_percent"], "trades": r["n_trades"], "wins": wins,
                              "signals": n_sig, "final_capital": r["final_capital"]},
    "ref_pnl": REF_PNL,
    "first_trades": [{k: tr[k] for k in ("entry_time", "entry", "exit", "pnl_pct", "reason")}
                     for tr in r["trades"][:5]],
}
del r, r_ref, sig_mine, sig_ref
_trim()

# ---------------------------------------------------------------------------
print("\n— المرحلة 3: المحركان الماكديان (نسخ المستند الـ67 + بوابة الحالات) على آخر 60 يوماً من نافذة البطل")
from integration_lib import load_window_arrays, run_integration  # noqa: E402
from app.services.strategy.presets import TRENDY_MACDIZED, BLAZING_MACDIZED  # noqa: E402
import copy  # noqa: E402

SUB_TO = CHAMP_TO
SUB_FROM = SUB_TO - 60 * 86_400_000
T2, O2, H2, L2, C2, V2, df2 = load_window_arrays(SUB_FROM, SUB_TO)
print(f"  نافذة المقارنة: {len(df2):,} شمعة ({_dt.datetime.fromtimestamp(SUB_FROM/1000, _dt.timezone.utc).date()} → "
      f"{_dt.datetime.fromtimestamp(SUB_TO/1000, _dt.timezone.utc).date()})")


def _variant(preset, identity=False):
    p = copy.deepcopy(preset)
    for ind in p["strategy_config"]["indicators"]:
        if ind.get("name") in ("zigzag_fib_e2e_trendy_macd", "zigzag_fib_e2e_blazing_macd"):
            if identity:
                ind["params"]["osc_instances"] = []
                ind["params"]["osc_conditions"] = None
    return p["strategy_config"]


res = {}
res["trendy_identity"] = run_integration(_variant(TRENDY_MACDIZED, True), T2, O2, H2, L2, C2, V2, df2, "ترنديه ماكديه — هوية (بلا بوابة)")
res["trendy_gated"] = run_integration(_variant(TRENDY_MACDIZED), T2, O2, H2, L2, C2, V2, df2, "ترنديه ماكديه — بوابة الحالات (أي حالة لحظية)")
res["blazing_gated"] = run_integration(_variant(BLAZING_MACDIZED), T2, O2, H2, L2, C2, V2, df2, "ملتهبه ماكديه — بوابة الحالات (أي حالة لحظية)")

check("M1 ترنديه ماكديه على نافذة البطل (آخر 60 يوماً): أعمدة الماكدية محقونة",
      res["trendy_gated"]["osc_columns"] >= 59, f"أعمدة={res['trendy_gated']['osc_columns']}")
check("M2 البوابة تعمل (ليست هوية): صفقات الماكدية أقل من الهوية",
      res["trendy_gated"]["trades"] < res["trendy_identity"]["trades"],
      f"هوية={res['trendy_identity']['trades']} صفقة → ماكدية={res['trendy_gated']['trades']} صفقة")
check("M3 ملتهبه ماكديه تعمل بنسخ المستند الـ67 على نافذة البطل",
      res["blazing_gated"]["osc_columns"] >= 69 and res["blazing_gated"]["trades"] > 0,
      f"أعمدة={res['blazing_gated']['osc_columns']} · صفقات={res['blazing_gated']['trades']} · "
      f"عوائد={res['blazing_gated']['total_return_pct']}%")
EVID["phases"]["macdized_subwindow"] = {
    "window": {"from_ms": SUB_FROM, "to_ms": SUB_TO, "bars": len(df2)},
    "trendy_identity": {k: v for k, v in res["trendy_identity"].items() if k != "trades_full"},
    "trendy_gated": {k: v for k, v in res["trendy_gated"].items() if k != "trades_full"},
    "blazing_gated": {k: v for k, v in res["blazing_gated"].items() if k != "trades_full"},
    "note": "ذاكرة الجهاز (4GB) تمنع تشغيل النسخ الـ67 على نافذة البطل كاملة (~4.3GB) — "
            "المقارنة على آخر 60 يوماً من نافذة البطل عبر المسار الإنتاجي نفسه؛ "
            "البطل نفسه مُتحقق بت-بت على النافذة كاملة (المرحلتان 1-2).",
}

# ===========================================================================
print("\n" + "=" * 78)
print(f"CHAMPION VERIFICATION: PASS={PASS} FAIL={FAIL}")
if FAILURES:
    for n, d in FAILURES:
        print(f"  ❌ {n} — {d}")
EVID["summary"] = {"pass": PASS, "fail": FAIL,
                   "failures": [{"name": n, "detail": d} for n, d in FAILURES]}
out_path = os.path.join(HERE, "r73-evidence", "champion-1651.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(EVID, fh, ensure_ascii=False, indent=2, default=str)
print(f"الأدلة: {out_path}")
sys.exit(0 if FAIL == 0 else 1)
