#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""✅ PRO74 — A/B نافذة هابطة ببيانات دافئة (lookback حقيقي).

تصحيح علمي مهم: نتائج A/B الأنظمة في تسليم PRO73 السابق (انقلاب الدب
−10.75% → +15.38%) كانت **أثر إحماء زائفًا**: البوابات حُسبت على شرائح
باردة (من بداية النافذة) فحجبت أسابيع النافذة الأولى زورًا. هذا الاختبار
يقيس القيمة الحقيقية للبوابات ببيانات دافئة (حساب المصفوفة من 2024-07
قبل نافذة الدب 2025-01-20 → 2025-04-20 ثم تقطيع البوابة إلى النافذة).

النتيجة الموثقة (SOLUSDT · الترندية · TP4.7/SL49 · next_open):
  الهوية:              7 صفقات · −49.95% · MDD 56.4%
  + بوابة RSI (دافئة): 5 صفقات · −50.42% · MDD 56.8% (حجبت رابحين!)
  + بوابة MACD (دافئة): 7 صفقات · −49.95% (صفر حجب)
الخلاصة الصادقة: البوابات الكلية (any-case) لا تحمي في هذا الدب —
قيمتها المثبتة الوحيدة حتى الآن = حياد الإحماء (PRO74) الذي يمنع
الحجب الزورف دون ادعاء حماية غير موجودة.
"""
import datetime as _dt
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
os.environ.setdefault("SECRET_KEY", "r74-bear-warm-0123456789")
os.environ.setdefault("DEBUG", "true")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

DATA_CANDIDATES = [
    "/home/z/my-project/r70-workspace/data/SOLUSDT_1m.npz",
    os.path.join(HERE, "..", "..", "..", "r70-workspace", "data", "SOLUSDT_1m.npz"),
]
DATA_PATH = next((p for p in DATA_CANDIDATES if os.path.isfile(p)), None)


def _ts(y, mo, d, h=0, mi=0):
    return int(_dt.datetime(y, mo, d, h, mi, tzinfo=_dt.timezone.utc).timestamp() * 1000)


def simulate(o, h, l, c, sig, initial=100.0, tp=4.7, sl=49.0):
    """المحاكي الحرفي (TP/SL فقط — نفس مختبر R67)."""
    n = len(o)
    tp_f, sl_f = tp / 100.0, sl / 100.0
    bal = float(initial)
    pos = None
    pending = False
    trades = []
    for i in range(n):
        if pending and pos is None and bal > 0:
            size = bal / o[i] if o[i] else 0.0
            pos = {"e": o[i], "s": size, "sl": o[i] * (1 - sl_f), "tp": o[i] * (1 + tp_f)}
        pending = False
        if pos is not None:
            ep = None
            if l[i] <= pos["sl"]:
                ep = pos["sl"]
            elif h[i] >= pos["tp"]:
                ep = pos["tp"]
            if ep is not None:
                pnl = (ep - pos["e"]) * pos["s"]
                bal += pnl
                trades.append({"pnl": pnl, "pct": pnl / (pos["e"] * pos["s"]) * 100 if pos["e"] * pos["s"] else 0})
                pos = None
        pending = bool(sig[i])
    if pos is not None:
        pnl = (c[n - 1] - pos["e"]) * pos["s"]
        bal += pnl
        trades.append({"pnl": pnl, "pct": pnl / (pos["e"] * pos["s"]) * 100})
    return {"pnl": (bal / initial - 1) * 100, "trades": trades}


def drawdown(steps):
    peak, mdd = -1e18, 0.0
    for v in steps:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak * 100)
    return mdd


def main():
    print("=" * 78)
    print("PRO74 — A/B الدب ببيانات دافئة (تصحيح أثر الإحماء)")
    print("=" * 78)
    if DATA_PATH is None:
        print("⚠️ بيانات SOL غير موجودة — يُتخطى (النتيجة موثقة في التسليم)")
        return 0
    from app.services.indicators.mtf_oscillator_core import macdized_layer
    from app.services.indicators.osc_cases import OSC_DOC_INSTANCES, RSI_ANY, MACD_ANY
    from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy

    z = np.load(DATA_PATH)
    T_all = z["time_ms"].astype(np.int64)
    m = (T_all >= _ts(2024, 7, 1)) & (T_all <= _ts(2025, 4, 20, 23, 59))
    Te = T_all[m]
    Oe = z["open"][m].astype(np.float64)
    He = z["high"][m].astype(np.float64)
    Le = z["low"][m].astype(np.float64)
    Ce = z["close"][m].astype(np.float64)
    Ve = z["volume"][m].astype(np.float64)
    df_ext = pd.DataFrame({"open": Oe, "high": He, "low": Le, "close": Ce, "volume": Ve},
                          index=pd.DatetimeIndex(pd.to_datetime(Te, unit="ms", utc=True), name="time"))
    mb = Te >= _ts(2025, 1, 20)
    Tb, Ob, Hb, Lb, Cb = Te[mb], Oe[mb], He[mb], Le[mb], Ce[mb]
    print(f"نافذة الدب: {len(Tb):,} شمعة · السعر {Cb[0]:.1f} → {Cb[-1]:.1f}")

    df_bear = pd.DataFrame({"open": Ob, "high": Hb, "low": Lb, "close": Cb, "volume": Ve[mb]},
                           index=pd.DatetimeIndex(pd.to_datetime(Tb, unit="ms", utc=True), name="time"))
    res = zigzag_fib_e2e_trendy(df_bear, length=100, mode="luxalgo",
                                trend_periods=[7, 15, 25], trend_confirm="majority",
                                trend_gate=["s1", "s2", "s3"])
    ser = res.get("series") or {}
    N = len(Tb)

    def _col(name):
        v = ser.get(name) or []
        a = np.asarray([0.0 if x is None else float(x) for x in v])
        if len(a) < N:
            a = np.concatenate((a, np.zeros(N - len(a))))
        return a[:N] >= 0.5

    sig = _col("zzfet_entry_s1") | _col("zzfet_entry_s2") | _col("zzfet_entry_s3")

    def _refs(tree, acc=None):
        if acc is None:
            acc = set()
        if isinstance(tree, dict):
            for k in ("left", "right"):
                v = tree.get(k)
                if isinstance(v, str) and v.startswith("osc:"):
                    acc.add(v.split(":")[1].split(".")[0])
            for c in (tree.get("conditions") or []):
                _refs(c, acc)
        return acc

    def warm_gate(tree):
        need = _refs(tree)
        insts = [i for i in OSC_DOC_INSTANCES if i["id"] in need]
        layer = macdized_layer(df_ext, insts, tree)
        return np.asarray(layer["gate"], dtype=bool)[mb]

    def run(sig_arr):
        r = simulate(Ob, Hb, Lb, Cb, sig_arr)
        eq = [100.0]
        for tr in r["trades"]:
            eq.append(eq[-1] * (1 + tr["pct"] / 100))
        return r, drawdown(eq)

    rA, ddA = run(sig)
    rB, ddB = run(sig & warm_gate(RSI_ANY))
    rC, ddC = run(sig & warm_gate(MACD_ANY))
    print(f"الهوية:              صفقات={len(rA['trades'])} · {rA['pnl']:+.2f}% · MDD {ddA:.1f}%")
    print(f"+ بوابة RSI (دافئة):  صفقات={len(rB['trades'])} · {rB['pnl']:+.2f}% · MDD {ddB:.1f}%")
    print(f"+ بوابة MACD (دافئة): صفقات={len(rC['trades'])} · {rC['pnl']:+.2f}% · MDD {ddC:.1f}%")

    out = {"identity": {"trades": len(rA["trades"]), "pnl": round(rA["pnl"], 2), "mdd": round(ddA, 1)},
           "rsi_gate_warm": {"trades": len(rB["trades"]), "pnl": round(rB["pnl"], 2), "mdd": round(ddB, 1)},
           "macd_gate_warm": {"trades": len(rC["trades"]), "pnl": round(rC["pnl"], 2), "mdd": round(ddC, 1)}}
    os.makedirs(os.path.join(HERE, "r73-evidence"), exist_ok=True)
    with open(os.path.join(HERE, "r73-evidence", "r74-bear-warm-ab.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print("saved → r73-evidence/r74-bear-warm-ab.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
