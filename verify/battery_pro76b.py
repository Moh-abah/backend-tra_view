# -*- coding: utf-8 -*-
"""
بطارية تحقق PRO76b — تشغيل ضد شجرة محددة (src-latest أو src-patched)
الاستخدام: python3 battery.py <tree> [test_id ...]
كل اختبار يطبع سطر نتيجة واحد قابل للمقارنة قبل/بعد.
"""
import sys, os, io, json, time, traceback, datetime, contextlib

TREE = sys.argv[1] if len(sys.argv) > 1 else "src-patched"
ONLY = set(sys.argv[2:]) or {"T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"}
sys.path.insert(0, os.path.abspath(TREE))

import numpy as np
import pandas as pd

BASE_MS = 900_000
T0 = 1_630_000_000_000
RESULTS = {}


def iso(ms):
    return datetime.datetime.utcfromtimestamp(ms / 1000.0).isoformat() + "Z"


def make_view_candles(n_total, bad_closes=0, bad_times=0):
    out = []
    for i in range(n_total):
        ts = T0 + i * BASE_MS
        close = 100.0 + (i % 37) * 0.5
        if i >= n_total - bad_closes:
            close = None
        s = iso(ts)
        if i >= n_total - bad_times:
            s = "—"
        out.append({"time": s, "open": close, "high": (close or 100) + 1.0,
                    "low": (close or 100) - 1.0, "close": close, "volume": 10.0})
    return out


def patch_hero(module, n, entry_idx):
    def fake_hero(candles, **kw):
        nn = len(candles)
        s = {"zzfet_dir": [1.0] * nn, "zzfet_entry": [None] * nn,
             "zzfet_entry_s1": [None] * nn, "zzfet_entry_s2": [None] * nn,
             "zzfet_entry_s3": [None] * nn, "zzfet_entry_raw": [None] * nn}
        for k in ("zzfet_entry", "zzfet_entry_s1"):
            s[k][entry_idx] = 1.0
        return {"engine": "F", "spec": "F", "series": s,
                "window": {"bars": nn, "time_from": T0, "time_to": T0 + nn * BASE_MS}}
    module.zigzag_fib_e2e_trendy = fake_hero


def osc_params(view_times, impossible=False, with_base=None):
    cond = {"logic": "and", "conditions": [
        {"left": "osc:rsi_14_15m.value", "op": ">", "right": (999999 if impossible else 0)},
    ]}
    p = {
        "mode": "luxalgo", "length": 100,
        "trend_periods": [7, 15, 25], "trend_confirm": "majority",
        "trend_gate": ["s1", "s2", "s3"],
        "osc_instances": [
            {"id": "rsi_14_15m", "kind": "rsi", "timeframe": "15m", "params": {"period": 14}},
        ],
        "osc_conditions": cond,
        "osc_base_timeframe": "15m",
        "view_times": view_times,
    }
    if with_base is not None:
        p["osc_base"] = with_base
        p["osc_series"] = "view"
    return p


def run_engine_case(candles, p):
    """compute_overlays عبر المسار الحقيقي — يعيد (نتيجة أو استثناء)."""
    from app.services.indicators.overlays import compute_overlays
    try:
        res = compute_overlays(candles, types=["zzfib_e2e_trendy_macd"],
                               params={"zzfib_e2e_trendy_macd": p})
        return res, None
    except Exception as e:
        tb = traceback.format_exc().splitlines()
        loc = [l.strip() for l in tb if "overlays_zlf_e2e_trendy_macd.py" in l]
        return None, (type(e).__name__, loc[-1] if loc else "?")


# --------------------------------------------------------------- T1: الانهيار
def t1():
    """مشهد 4d976421 بالضبط: fallback + 20 صف «—» + إشارة عند 9650."""
    import app.services.indicators.overlays_zlf_e2e_trendy_macd as tm
    patch_hero(tm, 9660, 9650)
    candles = make_view_candles(9660, bad_closes=12, bad_times=20)
    p = osc_params([c["time"] for c in candles])
    res, err = run_engine_case(candles, p)
    if err:
        RESULTS["T1"] = f"💥 {err[0]} @ {err[1]}"
        return
    ovl = res["overlays"].get("zzfib_e2e_trendy_macd") or {}
    ser = ovl.get("series") or {}
    osc = ovl.get("osc") or {}
    n_series = len(ser.get("zzfetm_entry") or [])
    gate_len = len(ser.get("zzfetm_osc_gate") or [])
    final = [i for i, x in enumerate(ser.get("zzfetm_entry") or []) if x is not None]
    iblk = [i for i, x in enumerate(ser.get("zzfetm_entry_iblocked") or []) if x is not None]
    codes = osc.get("warning_codes") or []
    RESULTS["T1"] = (f"✅ 200-مسار: سلسلة={n_series} بوابة={gate_len} نهائي@{final} "
                     f"ممنوع@{iblk} أكواد={codes} view_gaps={osc.get('view_gaps')} "
                     f"realigned={'gate_realigned' in codes}")


# ------------------------------------------------------- T2: العرض السليم
def t2():
    """عرض سليم بلا صفوف مشوّهة — نفس سلوك الصباح الناجح (بلا انحدار)."""
    import app.services.indicators.overlays_zlf_e2e_trendy_macd as tm
    patch_hero(tm, 3000, 1500)
    candles = make_view_candles(3000)
    p = osc_params([c["time"] for c in candles])
    res, err = run_engine_case(candles, p)
    if err:
        RESULTS["T2"] = f"💥 {err[0]} @ {err[1]}"
        return
    ovl = res["overlays"]["zzfib_e2e_trendy_macd"]
    ser = ovl.get("series") or {}
    osc = ovl.get("osc") or {}
    final = [i for i, x in enumerate(ser.get("zzfetm_entry") or []) if x is not None]
    RESULTS["T2"] = (f"✅ سلسلة={len(ser.get('zzfetm_entry') or [])} "
                     f"بوابة={len(ser.get('zzfetm_osc_gate') or [])} نهائي@{final} "
                     f"عدادات={osc.get('counts')} حياد={osc.get('warmup_neutral_bars')}")


# --------------------------------------- T3: القاعدة الكاملة + انقطاعات عرض
def t3():
    """مسار hit (مثل dd82d09d) + view_times فيها أعمدة لا تطابق القاعدة."""
    import app.services.indicators.overlays_zlf_e2e_trendy_macd as tm
    n_view = 3000
    patch_hero(tm, n_view, 2950)
    candles = make_view_candles(n_view)
    base = {"time_ms": [T0 + i * BASE_MS for i in range(20000)],
            "close": [100.0 + (i % 53) * 0.5 for i in range(20000)],
            "tf": "15m", "bars": 20000}
    # أزمنة عرض «غريبة» (30 عموداً منتصف النافذة بطوابع غير موجودة في القاعدة)
    vt = [c["time"] for c in candles]
    for k in range(1500, 1530):
        vt[k] = iso(T0 + k * BASE_MS + 432_000)  # +7.2 دقيقة — لا تطابق
    p = osc_params(vt, with_base=base)
    res, err = run_engine_case(candles, p)
    if err:
        RESULTS["T3"] = f"💥 {err[0]} @ {err[1]}"
        return
    ovl = res["overlays"]["zzfib_e2e_trendy_macd"]
    ser = ovl.get("series") or {}
    osc = ovl.get("osc") or {}
    n_series = len(ser.get("zzfetm_entry") or [])
    gate_len = len(ser.get("zzfetm_osc_gate") or [])
    final = [i for i, x in enumerate(ser.get("zzfetm_entry") or []) if x is not None]
    rsi_col = ser.get("zzfetm_osc_rsi_14_15m_value") or []
    rsi_gaps = sum(1 for k in range(1500, 1530) if rsi_col[k] is None)
    RESULTS["T3"] = (f"✅ سلسلة={n_series} بوابة={gate_len} نهائي@{final} "
                     f"قيمNone_بالانقطاع={rsi_gaps}/30 view_gaps={osc.get('view_gaps')} "
                     f"full_bars={osc.get('full_bars')}")


# ------------------------------- T4: الشجرة المستحيلة فوق حارس الذاكرة (50k)
def t4():
    """قرار البوابة فوق الحارس: نهائي=0 والخام=2 — القرار لا يتغير."""
    import app.services.indicators.overlays_zlf_e2e_trendy_macd as tm
    n = 60000
    patch_hero(tm, n, 1000)
    candles = make_view_candles(n)
    p = osc_params(None, impossible=True)
    p.pop("view_times")
    from app.services.indicators.overlay_columns import columns_for_configs
    df = pd.DataFrame({
        "time": [datetime.datetime.utcfromtimestamp((T0 + i * BASE_MS) / 1000.0) for i in range(n)],
        "open": np.linspace(100, 120, n), "high": np.linspace(101, 121, n),
        "low": np.linspace(99, 119, n), "close": np.linspace(100, 120, n),
    })
    cfgs = [{"name": "zzfib_e2e_trendy_macd", "enabled": True, "params": p}]
    cols = columns_for_configs(df, cfgs)
    ent = cols.get("ind_zzfetm_entry") or []
    raw = cols.get("ind_zzfetm_entry_raw") or []
    gate = cols.get("ind_zzfetm_osc_gate") or []
    RESULTS["T4"] = (f"✅ أعمدة={len(cols)} نهائي={sum(1 for x in ent if x is not None)} "
                     f"خام={sum(1 for x in raw if x is not None)} بوابة_قيم={sum(1 for x in gate if x is not None)} "
                     f"طول_بوابة={len(gate)}/{n}")


# ------------------------------------------- T5: حياد الإحماء (P2 — R74)
def t5():
    """شجرة rsi>0: أول قيمة rsi عند 14 — البوابة حيادة قبلها (مفتوحة)."""
    from app.services.indicators.mtf_oscillator_core import build_osc_section
    n = 200
    candles = make_view_candles(n)
    built = build_osc_section(
        candles, base_timeframe="15m",
        osc_instances=[{"id": "rsi_14_15m", "kind": "rsi", "timeframe": "15m",
                        "params": {"period": 14}}],
        osc_conditions={"logic": "and", "conditions": [
            {"left": "osc:rsi_14_15m.value", "op": ">", "right": 999999}]},  # مستحيلة
        osc_series="none",
    )
    gate = built["gate"]
    sec = built["section"]
    wu = sec.get("warmup_neutral_bars", 0) if "warmup_neutral_bars" in sec else None
    open_before = sum(1 for g in gate[:14] if g)
    closed_after = sum(1 for g in gate[20:80] if g)
    RESULTS["T5"] = (f"✅ أفق_الحياد={wu} مفتوحة_قبل_الأفق={open_before}/14 "
                     f"مغلقة_بعده={closed_after}/60 "
                     f"(شجرة مستحيلة: القاعدة = حياد كامل قبل الجاهزية ثم حجب كامل)")


# ------------------------------------------- T6: عزل المحركات (HF-B)
def t6():
    """محرك يفجر نفسه → البقية تُخدم + failed_engines — لا استثناء يخرج."""
    import app.services.indicators.overlays_zlf_e2e_trendy_macd as tm
    real_engine = tm.zigzag_fib_e2e_trendy_macd

    def bomb(candles, **kw):
        raise RuntimeError("انفجار مصطنع — كما انفجرت الماكدية في الإنتاج")
    tm.zigzag_fib_e2e_trendy_macd = bomb
    from app.services.indicators.overlays import compute_overlays
    candles = make_view_candles(500)
    p = osc_params(None)
    p.pop("view_times")
    try:
        res = compute_overlays(candles,
                               types=["zigzag", "zzfib_e2e_trendy", "zzfib_e2e_trendy_macd"],
                               params={})
        ok_engines = sorted(res["overlays"].keys())
        failed = res.get("failed_engines")
        RESULTS["T6"] = f"✅ بلا استثناء ✤ محركات_حية={ok_engines} متعثرة={failed}"
    except Exception as e:
        RESULTS["T6"] = f"💥 الاستثناء فجر النداء كله: {type(e).__name__}"
    finally:
        tm.zigzag_fib_e2e_trendy_macd = real_engine


# ------------------------------------------- T7: عقد الأطوال الشامل
def t7():
    """كل سلاسل المحرك = n بالضبط حتى مع 40 صفاً مشوّهاً في العرض."""
    import app.services.indicators.overlays_zlf_e2e_trendy_macd as tm
    patch_hero(tm, 9660, 9650)
    candles = make_view_candles(9660, bad_closes=25, bad_times=15)
    p = osc_params([c["time"] for c in candles])
    res, err = run_engine_case(candles, p)
    if err:
        RESULTS["T7"] = f"💥 {err[0]} @ {err[1]}"
        return
    ovl = res["overlays"]["zzfib_e2e_trendy_macd"]
    ser = ovl.get("series") or {}
    bad = {k: len(v) for k, v in ser.items() if len(v) != 9660}
    RESULTS["T7"] = (f"✅ سلاسل={len(ser)} مخالفات_الطول={len(bad)} "
                     f"{'⚠ ' + str(bad) if bad else 'كل السلاسل = 9660'}")


# ------------------------------------------- T8: الحارس/الذاكرة فوق 400k
def t8():
    """حارس SIGKILL سليم فوق 400k: نمط none — بوابة+عدادات بلا سلاسل كاملة."""
    import resource, time as _t
    import app.services.indicators.overlays_zlf_e2e_trendy_macd as tm
    n = 420_000
    patch_hero(tm, n, 300000)
    p = osc_params(None)
    p.pop("view_times")
    p.pop("osc_base_timeframe", None)
    candles = [{"time": T0 + i * 60_000, "open": 100.0, "high": 101.0,
                "low": 99.0, "close": 100.0 + (i % 37) * 0.5, "volume": 10.0}
               for i in range(n)]
    from app.services.indicators.overlays import compute_overlays
    t0 = _t.time()
    res, err = run_engine_case(candles, p)
    dt = _t.time() - t0
    if err:
        RESULTS["T8"] = f"💥 {err[0]}"
        return
    ovl = res["overlays"]["zzfib_e2e_trendy_macd"]
    ser = ovl.get("series") or {}
    osc = ovl.get("osc") or {}
    gate_len = len(ser.get("zzfetm_osc_gate") or [])
    counts = osc.get("counts")
    mode = osc.get("mode")
    full_series = [k for k, v in ser.items() if len(v) == n and k != "zzfetm_osc_gate"]
    RESULTS["T8"] = (f"✅ mode={mode} زمن={dt:.1f}s بوابة={gate_len}/{n} "
                     f"سلاسل_كاملة_مخزنة={len(full_series)} (0 = الحارس صامد) "
                     f"عدادات={counts}")


# ------------------------------------------- T9: ذاكرة 665k + مستند 67 نسخة
def t9():
    """حارس SIGKILL عند مقياس البطل: 665k شمعة 1m + مستند 67 نسخة (none) —
    القمة الرام يجب أن تبقى منخفضة (لا 5-7GB كعلة 10000312-14)."""
    try:
        import psutil
    except ImportError:
        psutil = None
    import os as _os
    import time as _t
    import app.services.indicators.overlays_zlf_e2e_trendy_macd as tm
    n = 665_099
    patch_hero(tm, n, 300000)

    def _mem_mb():
        if psutil is not None:
            return psutil.Process().memory_info().rss / (1024 * 1024)
        try:
            with open("/proc/self/status") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        return float(line.split()[1]) / 1024.0
        except Exception:
            return -1.0
        return -1.0

    m0 = _mem_mb()
    # شموع 1m + شجرة تشير لنسخة واحدة — المستند الكامل 67 يُمرَّر كما هو
    t0ms = T0
    candles = [{"time": t0ms + i * 60_000, "open": 100.0, "high": 101.0,
                "low": 99.0, "close": 100.0 + (i % 37) * 0.5, "volume": 10.0}
               for i in range(n)]
    m_candles = _mem_mb()
    p = {"mode": "luxalgo", "length": 100,
         "trend_periods": [7, 15, 25], "trend_confirm": "majority",
         "trend_gate": ["s1", "s2", "s3"],
         "osc_instances": None,          # ← None = المستند الكامل 67 نسخة
         "osc_conditions": {"logic": "and", "conditions": [
             {"left": "osc:rsi_14_1m.value", "op": ">", "right": 0}]},
         }
    from app.services.indicators.overlays import compute_overlays
    t0 = _t.time()
    res, err = run_engine_case(candles, p)
    dt = _t.time() - t0
    m_peak = _mem_mb()
    if err:
        RESULTS["T9"] = f"💥 {err[0]}"
        return
    ovl = res["overlays"]["zzfib_e2e_trendy_macd"]
    ser = ovl.get("series") or {}
    osc = ovl.get("osc") or {}
    osc_series = [k for k in ser if k.startswith("zzfetm_osc_")]
    RESULTS["T9"] = (f"✅ mode={osc.get('mode')} زمن={dt:.1f}s "
                     f"ذاكرة: شموع=+{m_candles-m0:.0f}MB قمة=+{m_peak-m_candles:.0f}MB "
                     f"(بلا انفجار 5-7GB) سلاسل_موشرات_مخزنة={len(osc_series)} "
                     f"بوابة={len(ser.get('zzfetm_osc_gate') or [])}/{n}")


# ------------------------------------------- T10: الملتهبة الماكدية — نفس المشهد
def t10():
    """نفس مشهد 4d976421 لكن على zzfib_e2e_blazing_macd (درس العائلة الثانية)."""
    import app.services.indicators.overlays_zlf_e2e_blazing_macd as bm
    n = 9660

    def fake_blazing(candles, **kw):
        nn = len(candles)
        s = {"zzfb_dir": [1.0] * nn, "zzfb_entry": [None] * nn,
             "zzfb_entry_s1": [None] * nn, "zzfb_entry_s2": [None] * nn,
             "zzfb_entry_s3": [None] * nn, "zzfb_entry_n5": [None] * nn,
             "zzfb_entry_n6": [None] * nn}
        s["zzfb_entry"][9650] = 1.0
        s["zzfb_entry_s1"][9650] = 1.0
        return {"engine": "F", "spec": "F", "series": s,
                "window": {"bars": nn, "time_from": T0, "time_to": 1}}
    bm.zigzag_fib_e2e_blazing = fake_blazing
    candles = make_view_candles(n, bad_closes=12, bad_times=20)
    p = osc_params([c["time"] for c in candles])
    from app.services.indicators.overlays import compute_overlays
    try:
        res = compute_overlays(candles, types=["zzfib_e2e_blazing_macd"],
                               params={"zzfib_e2e_blazing_macd": p})
        ovl = res["overlays"].get("zzfib_e2e_blazing_macd") or {}
        ser = ovl.get("series") or {}
        osc = ovl.get("osc") or {}
        n_series = len(ser.get("zzfbm_entry") or [])
        gate_len = len(ser.get("zzfbm_osc_gate") or [])
        final = [i for i, x in enumerate(ser.get("zzfbm_entry") or []) if x is not None]
        RESULTS["T10"] = (f"✅ سلسلة={n_series} بوابة={gate_len} نهائي@{final} "
                          f"أكواد={osc.get('warning_codes')}")
    except IndexError as e:
        RESULTS["T10"] = f"💥 IndexError: {e}"
    except Exception as e:
        RESULTS["T10"] = f"💥 {type(e).__name__}: {e}"


if __name__ == "__main__":
    print(f"البطارية ضد: {TREE}")
    print("=" * 74)
    runners = {"T1": t1, "T2": t2, "T3": t3, "T4": t4,
               "T5": t5, "T6": t6, "T7": t7, "T8": t8, "T9": t9, "T10": t10}
    for tid in ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]:
        if tid not in ONLY:
            continue
        try:
            runners[tid]()
        except Exception:
            RESULTS[tid] = "💥 " + traceback.format_exc(limit=1).splitlines()[-1]
        print(f"{tid}: {RESULTS.get(tid)}")
