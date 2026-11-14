#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بطارية اختبار PRO73 — «الترندية الماكدية» و«الملتهبة الماكدية» (باك اند فقط).

الأقسام:
  A) نواة الموشرات متعددة النسخ/الفريمات (mtf_oscillator_core):
     سجل الـ14 فريماً · مراسي التجميع (epoch/الاثنين/الشهر) · بلا نظرة مستقبلية
     · رياضيات RSI/MACD/Momentum (ببذرة SMA) · تطبيع النسخ والشروط.
  B) الهوية بت-بت: ترنديه ماكديه ≡ الترندية · ملتهبه ماكديه ≡ الملتهبة
     عند إيقاف بوابة الموشرات (مفتاح A/B — كل سلاسل المحرك الأصل بالمرآة).
  C) بوابة الشروط القابلة للتركيب: and/or/not · cross_above/cross_below ·
     price:* · فشل مغلق (fail-closed) للمرجع غير القابل للحل.
  D) عقد الأعمدة والتوصيل: ind_zzfetm_*/ind_zzfbm_* من compute_overlays
     وcolumns_for_configs (مسار محرك الاستراتيجيات) · القوالب (presets)
     تمر عبر StrategyConfig pydantic · السجل · خريطة عائلات الراوتر.
  E) 🔍 فلترة المناطق الهابطة (طلب المالك الصريح): على نافذة SOL 60 يوماً
     (2023-09-01 → 2023-11-07 — نافذة R69.2 نفسها) — هل تُفلتر الإشارات
     في المناطق الهابطة عند تفعيل بوابة الموشرات (RSI/MACD/Mom AND)؟
  F) التكامل الكامل: StrategyEngine (المسار الإنتاجي نفسه) — قوالب PRO73
     كاملة (10 RSI + 10 MACD + 5 Mom) → قرارات BUY/HOLD/خروج → صفقات فعلية
     عبر نموذج next_open — إثبات أن ind_zzfetm_*/ind_zzfbm_* تصل شروط الدخول.
"""

import asyncio
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

os.environ.setdefault("SECRET_KEY", "battery-only-secret-key-0123456789abcdef")
os.environ.setdefault("DEBUG", "true")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.indicators.mtf_oscillator_core import (  # noqa: E402
    TF_REGISTRY, TF_ORDER, TF_DURATIONS,
    compute_oscillator_matrix, evaluate_osc_conditions,
    normalize_osc_conditions, normalize_osc_instances,
    resample_ohlcv, infer_base_step_ms, _rsi_wilder, _ema_sma_seed,
)
from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy  # noqa: E402
from app.services.indicators.overlays_zlf_e2e_trendy_macd import zigzag_fib_e2e_trendy_macd  # noqa: E402
from app.services.indicators.overlays_zlf_e2e_blazing import zigzag_fib_e2e_blazing  # noqa: E402
from app.services.indicators.overlays_zlf_e2e_blazing_macd import zigzag_fib_e2e_blazing_macd  # noqa: E402
from app.services.indicators.overlays import compute_overlays, OVERLAY_TYPES  # noqa: E402
from app.services.indicators.overlay_columns import (  # noqa: E402
    columns_for_configs, config_to_overlay_params, columns_from_overlays_result,
)

PASS = 0
FAIL = 0
FAILURES = []
EVID = {"sections": {}}


def check(name: str, cond: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        FAILURES.append((name, detail))
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
    return cond


def section(title: str):
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# ---------------------------------------------------------------------------
# بيانات SOL — نافذة R69.2 نفسها (60 يوماً + تمديد 7 نوفمبر)
# ---------------------------------------------------------------------------
DATA_CANDIDATES = [
    "/home/z/my-project/r70-workspace/data/SOLUSDT_1m.npz",
    os.path.join(HERE, "..", "..", "..", "r70-workspace", "data", "SOLUSDT_1m.npz"),
]
DATA_PATH = next((p for p in DATA_CANDIDATES if os.path.isfile(p)), None)

W_FROM = int(_dt.datetime(2023, 9, 1, tzinfo=_dt.timezone.utc).timestamp() * 1000)
W_TO = int(_dt.datetime(2023, 11, 8, tzinfo=_dt.timezone.utc).timestamp() * 1000)  # حتى 7 نوفمبر نهايةً

# PRO73-R3: بوابة العملية الابنة لقسم F (ذاكرة) — نسخ المستند الـ67 تستهلك
# ~1.6GB ذروة؛ داخل نفس عملية الأقسام A-E تتجاوز 3GB → OOM. العملية الابنة
# تقفز مباشرة للتكامل وتخرج قبل أي قسم آخر.
if os.environ.get("PRO73_F_CHILD") == "1":
    from integration_lib import load_window_arrays, run_integration  # noqa: E402
    from app.services.strategy.presets import TRENDY_MACDIZED, BLAZING_MACDIZED  # noqa: E402
    _T, _O, _H, _L, _C, _V, _df = load_window_arrays(W_FROM, W_TO)
    print(f"  نافذة التكامل: {len(_df):,} شمعة 1m (نافذة الـ60 يوماً كاملة)")
    _r1 = run_integration(TRENDY_MACDIZED["strategy_config"], _T, _O, _H, _L, _C, _V, _df, "ترنديه ماكديه")
    _r2 = run_integration(BLAZING_MACDIZED["strategy_config"], _T, _O, _H, _L, _C, _V, _df, "ملتهبه ماكديه")
    _r1["trades_full"] = _r1["trades_full"][:40]
    _r2["trades_full"] = _r2["trades_full"][:40]
    _fp = os.path.join(HERE, "r73-evidence", "battery-r73-f.json")
    os.makedirs(os.path.dirname(_fp), exist_ok=True)
    with open(_fp, "w", encoding="utf-8") as fh:
        json.dump({"trendy_macdized": _r1, "blazing_macdized": _r2}, fh,
                  ensure_ascii=False, indent=2, default=str)
    print(f"F evidence → {_fp}")
    sys.exit(0)


def load_sol_window():
    z = np.load(DATA_PATH)
    t = z["time_ms"].astype(np.int64)
    m = (t >= W_FROM) & (t < W_TO)
    T = t[m]
    O = z["open"][m].astype(np.float64)
    H = z["high"][m].astype(np.float64)
    L = z["low"][m].astype(np.float64)
    C = z["close"][m].astype(np.float64)
    V = z["volume"][m].astype(np.float64)
    candles = [{"time": int(T[i]), "open": float(O[i]), "high": float(H[i]),
                "low": float(L[i]), "close": float(C[i]), "volume": float(V[i])}
               for i in range(len(T))]
    return int(T[0]), int(T[-1]), len(T), candles, T, O, H, L, C, V


# ===========================================================================
print("PRO73-R BATTERY — الترندية الماكدية / الملتهبة الماكدية")
print(f"src = {os.path.abspath(SRC)}")
print(f"data = {DATA_PATH}")
if DATA_PATH is None:
    print("⚠️ بيانات SOL غير موجودة — الأقسام E/F ستفشل")
    sys.exit(2)

T0_ALL = time.perf_counter()
W_START, W_END, NWIN, WIN_CANDLES, WT, WO, WH, WL, WC, WV = load_sol_window()
print(f"نافذة SOL: {NWIN:,} شمعة 1m | {W_START} → {W_END} "
      f"({_dt.datetime.utcfromtimestamp(W_START / 1000):%Y-%m-%d} → "
      f"{_dt.datetime.utcfromtimestamp(W_END / 1000):%Y-%m-%d})")

# ===========================================================================
section("A) نواة الموشرات — سجل الفريمات والمراسي والرياضيات")

# A1 — سجل الـ14 فريماً
check("A1 سجل 14 فريماً بالترتيب", TF_ORDER == ["1s", "5s", "30s", "1m", "5m", "15m",
                                                 "1h", "4h", "1d", "2d", "3d", "1w", "2w", "1M"],
      f"{'|'.join(TF_ORDER)}")
check("A1b خطوات صحيحة", TF_DURATIONS["1s"] == 1000 and TF_DURATIONS["5m"] == 300000
      and TF_DURATIONS["4h"] == 14400000 and TF_DURATIONS["2d"] == 2 * 86400000
      and TF_DURATIONS["3d"] == 3 * 86400000 and TF_DURATIONS["2w"] == 2 * 7 * 86400000)

# A2 — مراسي التجميع على نافذة SOL الحقيقية
week_bars = resample_ohlcv(WT, WO, WH, WL, WC, WV, "1w")
ok_anchor_1w = all((int(x) - 4 * 86400000) % (7 * 86400000) == 0 for x in week_bars["open_ms"][:5])
check("A2 مرساة 1w = الاثنين 00:00 UTC", ok_anchor_1w,
      f"أول شريط {_dt.datetime.utcfromtimestamp(week_bars['open_ms'][0] / 1000):%Y-%m-%d %H}")
biw = resample_ohlcv(WT, WO, WH, WL, WC, WV, "2w")
ok_2w = all((int(x) - 4 * 86400000) % (14 * 86400000) == 0 for x in biw["open_ms"][:5])
check("A2b مرساة 2w = أسبوعان بمرساة الاثنين", ok_2w)
mo = resample_ohlcv(WT, WO, WH, WL, WC, WV, "1M")
ok_1m = all(np.datetime64(int(x), "ms") == np.datetime64(int(x), "ms").astype("datetime64[M]").astype("datetime64[ms]")
            for x in mo["open_ms"][:3])
check("A2c مرساة 1M = بداية شهر تقويمي UTC", ok_1m,
      f"أول شريط {_dt.datetime.utcfromtimestamp(int(mo['open_ms'][0]) / 1000):%Y-%m-%d}")
d2 = resample_ohlcv(WT, WO, WH, WL, WC, WV, "2d")
d3 = resample_ohlcv(WT, WO, WH, WL, WC, WV, "3d")
check("A2d مراسي 2d/3d = epoch", int(d2["open_ms"][0]) % (2 * 86400000) == 0
      and int(d3["open_ms"][0]) % (3 * 86400000) == 0)

# A3 — بلا نظرة مستقبلية: قيمة 1h RSI عند شمعة الدقيقة التي إغلاقها == إغلاق شريط الساعة
hour_bars = resample_ohlcv(WT, WO, WH, WL, WC, WV, "1h")
h_rsi = _rsi_wilder(hour_bars["close"], 14)
res = compute_oscillator_matrix(WIN_CANDLES, [
    {"kind": "rsi", "id": "rsi1h", "timeframe": "1h", "period": 14}])
rsi_grid = res["series"]["rsi1h"]["value"]
k = 200
tc = int(hour_bars["close_ms"][k])
i = int(np.searchsorted(WT + 60000, tc, side="right") - 1)
ok_at = (rsi_grid[i] is not None) and abs(rsi_grid[i] - float(h_rsi[k])) < 1e-9
ok_before = (rsi_grid[i - 1] is not None) and abs(rsi_grid[i - 1] - float(h_rsi[k - 1])) < 1e-9
check("A3 لا-نظرة-مستقبلية (عند الإغلاق = الشريط الحالي، قبله = السابق)", ok_at and ok_before,
      f"at-close={ok_at} before-close={ok_before}")
# الشريط النامي لا يُرى إطلاقاً: شمعة الدقيقة التي إغلاقها قبل إغلاق شريط الساعة k
# ترى الشريط k−1 فقط — أي قيمة عن rsi_grid تساوي rsi[k-1] أو None (إحماء)
j = int(np.searchsorted(WT + 60000, tc, side="left") - 1)
ok_growing = (WT[j] + 60000 < tc) and (
    rsi_grid[j] is None or abs(rsi_grid[j] - float(h_rsi[k - 1])) < 1e-9)
check("A3b الشريط النامي غير مرئي", ok_growing)

# A4 — رياضيات المؤشرات (بذور SMA):
c_small = np.array([10.0, 10.5, 10.2, 10.8, 11.0, 10.6, 10.9, 11.2, 11.5, 11.1,
                    11.4, 11.8, 11.6, 12.0, 12.3, 12.1, 12.4, 12.6, 12.2, 12.8])
r_small = _rsi_wilder(c_small, 5)
d = np.diff(c_small)
g = np.where(d > 0, d, 0.0)
ls = np.where(d < 0, -d, 0.0)
sg = float(np.mean(g[:5]))
sl = float(np.mean(ls[:5]))
rsi_manual = 100 - 100 / (1 + (sg / sl if sl > 0 else float("inf")))
check("A4 RSI Wilder ببذرة SMA (مقارنة يدوية)", abs(float(r_small[5]) - rsi_manual) < 1e-9,
      f"محرك={float(r_small[5]):.6f} يدوي={rsi_manual:.6f}")
check("A4b RSI داخل [0,100]", np.nanmax(r_small) <= 100.0000001 and np.nanmin(r_small) >= -1e-9)
e_f = _ema_sma_seed(c_small, 5)
check("A4c EMA ببذرة SMA (NaN قبل البذرة)", np.isnan(e_f[:4]).all() and not np.isnan(e_f[4:]).any()
      and abs(float(e_f[4]) - float(np.mean(c_small[:5]))) < 1e-12)
mom_manual = c_small[5] - c_small[0]
# أزمنة epoch حقيقية (to_ms يفسّر الأرقام < 1e11 كثوانٍ — عقد الإنتاج)
EPOCH0 = 1693526400000
res_small = compute_oscillator_matrix(
    [{"time": EPOCH0 + 60000 * i, "open": x, "high": x + 0.1, "low": x - 0.1, "close": x, "volume": 1.0}
     for i, x in enumerate(c_small)],
    [{"kind": "mom", "id": "m1", "timeframe": "1m", "length": 5}])
check("A4d Momentum = close[i] − close[i−5]", abs((res_small["series"]["m1"]["line"][5] or 0) - mom_manual) < 1e-12,
      f"محرك={res_small['series']['m1']['line'][5]} يدوي={mom_manual} · base_tf={res_small['base_tf']}")

# A5 — تطبيع النسخ: مرادفات + فريم غير معروف + معرف مكرر + نسخة معطلة
insts, warns = normalize_osc_instances([
    {"kind": "momentum", "id": "M1", "timeframe": "H1", "period": 9},
    {"kind": "roc", "id": "m2", "timeframe": "15min", "length": 4},
    {"kind": "macd", "id": "x1", "timeframe": "7h"},
    {"kind": "rsi", "id": "M1", "timeframe": "1h", "period": 14},
])
check("A5 تطبيع المرادفات (momentum→mom, H1→1h, roc→mom, 15min→15m)",
      insts[0]["kind"] == "mom" and insts[0]["timeframe"] == "1h" and insts[0]["params"]["length"] == 9
      and insts[1]["timeframe"] == "15m")
check("A5b فريم مجهول يُهمل بتحذير (لا انهيار)", len(insts) == 3 and any("7h" in w for w in warns))
check("A5c المعرف المكرر يُرقّم", any(x["id"].startswith("m1_") for x in insts))
check("A5d النسخة المعطلة محفوظة disabled",
      any(x.get("available") is False for x in
          compute_oscillator_matrix(WIN_CANDLES[:50], [
              {"kind": "rsi", "id": "off1", "timeframe": "1h", "period": 14, "enabled": False}])["instances"]))

# A6 — فريم أدنى من شموع القاعدة → غير متاح + قيم None (لا انهيار)
res_low = compute_oscillator_matrix(WIN_CANDLES[:2000], [
    {"kind": "rsi", "id": "r1s", "timeframe": "30s", "period": 14},
    {"kind": "mom", "id": "m5s", "timeframe": "5s", "length": 3},
])
rep = {x["id"]: x for x in res_low["instances"]}
check("A6 فريم أدنى من القاعدة (30s/5s على 1m) غير متاح + قيم None",
      rep["r1s"]["available"] is False and rep["m5s"]["available"] is False
      and all(v is None for v in res_low["series"]["r1s"]["value"])
      and any("أدنى" in w for w in res_low["warnings"]))

EVID["sections"]["A_core"] = {"pass": PASS, "fail": FAIL}
_p = lambda: EVID["sections"]["A_core"]["pass"]  # noqa: E731
_f = lambda: EVID["sections"]["A_core"]["fail"]  # noqa: E731

# ===========================================================================
section("B) الهوية بت-بت — إيقاف البوابة = المحرك الأصل بالضبط")

tm_id = zigzag_fib_e2e_trendy_macd(WIN_CANDLES, osc_instances=None, osc_conditions=None)
ty_id = zigzag_fib_e2e_trendy(WIN_CANDLES)
mism = []
for k, vals in ty_id["series"].items():
    mk = "zzfetm_" + k[len("zzfet_"):]
    mv = tm_id["series"].get(mk)
    if mv is None:
        mism.append((k, "missing"))
    elif not k.startswith("zzfet_entry"):
        if list(vals or []) != list(mv or []):
            mism.append((k, "value"))
ok_identity_tm = not mism
for k in ("zzfet_entry", "zzfet_entry_s1", "zzfet_entry_s2", "zzfet_entry_s3",
          "zzfet_entry_raw", "zzfet_entry_blocked_s1"):
    mk = "zzfetm_" + k[len("zzfet_"):]
    if list(ty_id["series"].get(k) or []) != list(tm_id["series"].get(mk) or []):
        ok_identity_tm = False
        mism.append((k, "entry-layer"))
check("B1 ترنديه ماكديه ≡ الترندية بت-بت (بوابة مفتوحة — كل السلاسل)",
      ok_identity_tm, f"عدم تطابق: {mism[:4]} ({len(mism)})")
check("B1b حمولة الترندية كاملة داخل الماكدية",
      tm_id["legs"] == ty_id["legs"] and tm_id["ranges"] == ty_id["ranges"]
      and tm_id["trend"] == ty_id["trend"] and tm_id["pivots"] == ty_id["pivots"]
      and tm_id["current"] == ty_id["current"])
check("B1c counts الهوية", tm_id["osc"]["counts"]["final_entries"] == tm_id["osc"]["counts"]["trend_entries"]
      and tm_id["osc"]["gate_open"] is True)

bm_id = zigzag_fib_e2e_blazing_macd(WIN_CANDLES, osc_instances=None, osc_conditions=None)
bl_id = zigzag_fib_e2e_blazing(WIN_CANDLES)
mism2 = []
for k, vals in bl_id["series"].items():
    mk = "zzfbm_" + k[len("zzfb_"):]
    mv = bm_id["series"].get(mk)
    if mv is None:
        mism2.append((k, "missing"))
    elif not k.startswith("zzfb_entry"):
        if list(vals or []) != list(mv or []):
            mism2.append((k, "value"))
ok_identity_bm = not mism2
for k in ("zzfb_entry", "zzfb_entry_s1", "zzfb_entry_s2", "zzfb_entry_s3",
          "zzfb_entry_n5", "zzfb_entry_n6", "zzfb_entry_raw_n5"):
    mk = "zzfbm_" + k[len("zzfb_"):]
    if list(bl_id["series"].get(k) or []) != list(bm_id["series"].get(mk) or []):
        ok_identity_bm = False
        mism2.append((k, "entry-layer"))
check("B2 ملتهبه ماكديه ≡ الملتهبة بت-بت (بوابة مفتوحة — كل السلاسل)",
      ok_identity_bm, f"عدم تطابق: {mism2[:4]} ({len(mism2)})")
check("B2b حمولة الملتهبة كاملة داخل الماكدية",
      bm_id["legs"] == bl_id["legs"] and bm_id["ranges"] == bl_id["ranges"]
      and bm_id["trend"] == bl_id["trend"] and bm_id["pivots"] == bl_id["pivots"]
      and bm_id["current"] == bl_id["current"])

EVID["sections"]["B_identity"] = {"pass": PASS - _p(), "fail": FAIL - _f()}
_pB = lambda: _p() + EVID["sections"]["B_identity"]["pass"]  # noqa: E731
_fB = lambda: _f() + EVID["sections"]["B_identity"]["fail"]  # noqa: E731

# ===========================================================================
section("C) بوابة الشروط القابلة للتركيب")

# مصفوفة كاملة للشروط (rsi1h + macd1h) — تُحسب مرة وتُستعمل في C2-C5
res_full = compute_oscillator_matrix(WIN_CANDLES, [
    {"kind": "rsi", "id": "rsi1h", "timeframe": "1h", "period": 14},
    {"kind": "macd", "id": "macd1h", "timeframe": "1h", "fast": 12, "slow": 26, "signal": 9},
])
osc_np2 = {kk: {f: np.asarray([np.nan if x is None else x for x in (vals or [])]) for f, vals in dd.items()}
           for kk, dd in res_full["series"].items()}

t306 = {"logic": "and", "conditions": [
    {"left": "osc:rsi1h.value", "op": ">", "right": 50},
    {"logic": "or", "conditions": [
        {"left": "osc:macd1h.hist", "op": ">", "right": 0},
        {"left": "osc:rsi1h.value", "op": "cross_above", "right": 60},
    ]},
]}
norm_t, w_norm = normalize_osc_conditions(t306)
check("C1 تطبيع and/or متداخل", norm_t is not None and norm_t["logic"] == "and"
      and norm_t["conditions"][1]["logic"] == "or",
      f"تحذيرات: {w_norm}")
gate_c, _ = evaluate_osc_conditions(norm_t, osc_np2, WO, WH, WL, WC, NWIN)
check("C2 التقييم على نافذة SOL ينتج بوابة بجزء صحيح",
      0 < int(gate_c.sum()) < NWIN, f"صحيح={int(gate_c.sum()):,}/{NWIN:,}")

t_bad = {"logic": "and", "conditions": [
    {"left": "osc:rsi1h.value", "op": ">", "right": 50},
    {"left": "osc:ghost.line", "op": ">", "right": 0},
]}
norm_bad, _ = normalize_osc_conditions(t_bad)
gate_bad, w_bad = evaluate_osc_conditions(norm_bad, osc_np2, WO, WH, WL, WC, NWIN)
check("C3 فشل مغلق (fail-closed): مرجع مجهول = الشرط لا يتحقق أبداً",
      int(gate_bad.sum()) == 0 and any("فشل مغلق" in w for w in w_bad))
t_not = {"logic": "not", "conditions": [{"left": "osc:rsi1h.value", "op": "<=", "right": 50}]}
norm_not, _ = normalize_osc_conditions(t_not)
gate_not, _ = evaluate_osc_conditions(norm_not, osc_np2, WO, WH, WL, WC, NWIN)
check("C4 NOT منطقي يعمل", abs(int(gate_not.sum()) - int((~(osc_np2["rsi1h"]["value"] <= 50)).sum())) < 2)
t_cross = {"left": "osc:macd1h.line", "op": "cross_above", "right": "osc:macd1h.signal"}
norm_cross, _ = normalize_osc_conditions(t_cross)
gate_cross, _ = evaluate_osc_conditions(norm_cross, osc_np2, WO, WH, WL, WC, NWIN)
manual_above = osc_np2["macd1h"]["line"] > osc_np2["macd1h"]["signal"]
manual_known = np.concatenate(([False], np.isfinite(osc_np2["macd1h"]["line"][:-1])
                                & np.isfinite(osc_np2["macd1h"]["signal"][:-1])))
manual_prev = np.concatenate(([False], manual_above[:-1]))
check("C5 cross_above بين سلسلتين (خط فوق إشارة MACD — بتقاطع معلوم الحالة السابقة فقط)",
      int(gate_cross.sum()) == int((manual_above & ~manual_prev & manual_known).sum()),
      f"تقاطعات={int(gate_cross.sum())}")
gate_open, _ = evaluate_osc_conditions(None, {}, WO, WH, WL, WC, NWIN)
check("C6 غياب الشروط = بوابة مفتوحة دائماً", bool(gate_open.all()))

EVID["sections"]["C_conditions"] = {"pass": PASS - _pB(), "fail": FAIL - _fB()}
_pC = lambda: _pB() + EVID["sections"]["C_conditions"]["pass"]  # noqa: E731
_fC = lambda: _fB() + EVID["sections"]["C_conditions"]["fail"]  # noqa: E731

# ===========================================================================
section("D) عقد الأعمدة والتوصيل (مسارات الباك اند كلها)")

INSTS10 = [
    {"kind": "rsi", "id": f"rsi{i}", "timeframe": tf, "period": p} for i, (tf, p) in enumerate([
        ("5m", 14), ("15m", 14), ("1h", 14), ("4h", 14), ("1d", 14),
        ("1h", 7), ("4h", 21), ("15m", 28), ("1d", 10), ("1w", 14)], start=1)
] + [
    {"kind": "macd", "id": f"macd{i}", "timeframe": tf, "fast": f, "slow": s, "signal": g}
    for i, (tf, f, s, g) in enumerate([
        ("15m", 12, 26, 9), ("1h", 12, 26, 9), ("4h", 12, 26, 9), ("1d", 12, 26, 9),
        ("1h", 6, 13, 4), ("4h", 6, 13, 4), ("15m", 6, 13, 4), ("1d", 5, 34, 5),
        ("5m", 12, 26, 9), ("1w", 12, 26, 9)], start=1)
] + [
    {"kind": "mom", "id": f"mom{i}", "timeframe": tf, "length": L} for i, (tf, L) in enumerate([
        ("15m", 10), ("1h", 10), ("4h", 14), ("1d", 10), ("1h", 5)], start=1)
]
CONDS10 = {"logic": "and", "conditions": [
    {"left": "osc:rsi3.value", "op": ">", "right": 50},
    {"left": "osc:rsi4.value", "op": ">", "right": 50},
    {"left": "osc:macd2.hist", "op": ">", "right": 0},
    {"left": "osc:macd4.line", "op": ">", "right": 0},
    {"left": "osc:mom2.line", "op": ">", "right": 0},
]}

cfg_tm = {"name": "zigzag_fib_e2e_trendy_macd", "params": {
    "mode": "luxalgo", "length": 100,
    "trend_periods": [7, 15, 25], "trend_confirm": "majority",
    "trend_gate": ["s1", "s2", "s3"],
    "osc_instances": INSTS10, "osc_conditions": CONDS10}}
cfg_bm = {"name": "zigzag_fib_e2e_blazing_macd", "params": {
    "mode": "luxalgo", "length": 100,
    "trend_periods": [7, 15, 25], "trend_confirm": "majority",
    "trend_gate": ["s1", "s2", "s3", "n5", "n6"],
    "osc_instances": INSTS10, "osc_conditions": CONDS10}}

conv_tm = config_to_overlay_params(cfg_tm)
check("D1 config_to_overlay_params يمرر القالبين كاملين",
      conv_tm["zzfib_e2e_trendy_macd"]["osc_instances"] == INSTS10
      and conv_tm["zzfib_e2e_trendy_macd"]["osc_conditions"] == CONDS10)

ovl = compute_overlays(WIN_CANDLES, types=["zzfib_e2e_trendy_macd"],
                       params={"zzfib_e2e_trendy_macd": cfg_tm["params"]})
cols_tm = columns_from_overlays_result(ovl)
n_zzfetm = len([k for k in cols_tm if k.startswith("ind_zzfetm_")])
has_osc_cols = all(f"ind_zzfetm_osc_{iid}_{f}" in cols_tm for iid in ("rsi1", "macd2", "mom3")
                   for f in (("value", "ma") if iid.startswith("rsi") else
                             (("line", "signal", "hist") if iid.startswith("macd") else ("line", "pct"))))
check("D2 عقد ind_zzfetm_* كامل (المرآة + الشفافية الرباعية + سلاسل الموشرات)",
      n_zzfetm >= 59 and "ind_zzfetm_entry" in cols_tm and "ind_zzfetm_entry_iblocked_s1" in cols_tm
      and "ind_zzfetm_osc_gate" in cols_tm and has_osc_cols, f"أعمدة={n_zzfetm}")

ovl_b = compute_overlays(WIN_CANDLES, types=["zzfib_e2e_blazing_macd"],
                         params={"zzfib_e2e_blazing_macd": cfg_bm["params"]})
cols_bm = columns_from_overlays_result(ovl_b)
n_zzfbm = len([k for k in cols_bm if k.startswith("ind_zzfbm_")])
check("D3 عقد ind_zzfbm_* كامل (الأنواع الخمسة + الشفافية الرباعية + الموشرات)",
      n_zzfbm >= 69 and "ind_zzfbm_entry_n5" in cols_bm and "ind_zzfbm_entry_iblocked_n6" in cols_bm
      and "ind_zzfbm_osc_gate" in cols_bm, f"أعمدة={n_zzfbm}")

cols_engine = columns_for_configs(WIN_CANDLES, [cfg_tm])
check("D4 columns_for_configs (مسار المحرك) يحقن ind_zzfetm_*",
      "ind_zzfetm_entry_s1" in cols_engine and "ind_zzfetm_osc_macd2_hist" in cols_engine)

from app.services.strategy.presets import (  # noqa: E402
    TRENDY_MACDIZED, BLAZING_MACDIZED, get_presets, OSC_INSTANCES_TEMPLATE,
)
from app.services.strategy.schemas import StrategyConfig  # noqa: E402
try:
    sc_tm = StrategyConfig(**TRENDY_MACDIZED["strategy_config"])
    sc_bm = StrategyConfig(**BLAZING_MACDIZED["strategy_config"])
    ok_presets = True
except Exception as e:
    ok_presets = False
    print("    استثناء:", str(e)[:200])
check("D5 قالبا PRO73 يعبران StrategyConfig pydantic (القواعد والأوزان والمعاملات)",
      ok_presets and len(sc_tm.indicators[0].params["osc_instances"]) == len(OSC_INSTANCES_TEMPLATE)
      and len(sc_tm.indicators[0].params["osc_instances"]) == 67)
n_rsi = sum(1 for x in sc_tm.indicators[0].params["osc_instances"] if x["kind"] == "rsi")
n_macd = sum(1 for x in sc_tm.indicators[0].params["osc_instances"] if x["kind"] == "macd")
n_mom = sum(1 for x in sc_tm.indicators[0].params["osc_instances"] if x["kind"] == "mom")
check("D5b القالب الافتراضي (PRO73-R3 — نسخ المستند الكاملة): MACD×28 + RSI×16 + Mom×23 = 67",
      n_rsi == 16 and n_macd == 28 and n_mom == 23, f"rsi={n_rsi} macd={n_macd} mom={n_mom}")
ids_presets = [p["id"] for p in get_presets()]
check("D5c القالبان مسجلان في get_presets",
      "trendy_macdized_zero_fee" in ids_presets and "blazing_macdized_zero_fee" in ids_presets)

from app.services.indicators.registry import IndicatorRegistry  # noqa: E402
ok_reg = IndicatorRegistry.get_indicator_info("zigzag_fib_e2e_trendy_macd") is not None \
    and IndicatorRegistry.get_indicator_info("zigzag_fib_e2e_blazing_macd") is not None
check("D6 السجل: المحركان مسجلان (zigzag_fib_e2e_trendy_macd / blazing_macd)", ok_reg)

import ast  # noqa: E402
router_src = os.path.join(SRC, "app", "routers", "backtest.py")
fam_fn = None
with open(router_src, "r", encoding="utf-8") as fh:
    tree = ast.parse(fh.read())
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == "_strategy_family_overlays":
        mod = ast.Module(body=[node], type_ignores=[])
        ns = {"Any": object, "List": list}
        exec(compile(mod, router_src, "exec"), ns)
        fam_fn = ns["_strategy_family_overlays"]
check("D7 خريطة عائلات الراوتر: ind_zzfetm_* → trendy_macd · ind_zzfbm_* → blazing_macd",
      fam_fn is not None and "zzfib_e2e_trendy_macd" in fam_fn(["ind_zzfetm_entry_s1"])
      and "zzfib_e2e_blazing_macd" in fam_fn(["ind_zzfbm_entry_n5"])
      and "zzfib_e2e_blazing" in fam_fn(["ind_zzfb_entry_s1"])
      and fam_fn(["ind_zzfbm_entry_s1", "ind_zzfetm_entry_s1"]) == ["zzfib_e2e_blazing_macd", "zzfib_e2e_trendy_macd"])

ovl_all = compute_overlays(WIN_CANDLES[:5000])
check("D8 حارس الأداء: مسار «الكل» يتجاوز الماكدية بلا قالب ويبقي الباقي",
      "zzfib_e2e_trendy_macd" not in ovl_all["overlays"]
      and "zzfib_e2e_trendy" in ovl_all["overlays"] and "zzfib_e2e_blazing" in ovl_all["overlays"]
      and "zzfib" in ovl_all["overlays"])
ovl_exp = compute_overlays(WIN_CANDLES[:5000], types=["zzfib_e2e_trendy_macd"])
check("D8b الطلب الصريح بلا قالب = وضع الهوية (يُحسب)", "zzfib_e2e_trendy_macd" in ovl_exp["overlays"])

EVID["sections"]["D_contract"] = {"pass": PASS - _pC(), "fail": FAIL - _fC()}
_pD = lambda: _pC() + EVID["sections"]["D_contract"]["pass"]  # noqa: E731
_fD = lambda: _fC() + EVID["sections"]["D_contract"]["fail"]  # noqa: E731

# ===========================================================================
section("E) 🔍 فلترة المناطق الهابطة — هل تُفلتر الإشارات في الأماكن الهابطة؟")

h1 = resample_ohlcv(WT, WO, WH, WL, WC, WV, "1h")
h_close = h1["close"]
h_close_ms = h1["close_ms"]


def _roll_mean(x, w):
    out = np.full(len(x), np.nan)
    cs = np.concatenate(([0.0], np.cumsum(x)))
    out[w - 1:] = (cs[w:] - cs[:-w]) / w
    return out


sma200_1h = _roll_mean(h_close, 200)
sma50_1h = _roll_mean(h_close, 50)
eval_ms = (WT + 60000).astype(np.int64)
idx_h = np.searchsorted(h_close_ms, eval_ms, side="right") - 1
grid_sma200 = np.full(NWIN, np.nan)
grid_sma50 = np.full(NWIN, np.nan)
ok_mask = idx_h >= 0
grid_sma200[ok_mask] = sma200_1h[idx_h[ok_mask]]
grid_sma50[ok_mask] = sma50_1h[idx_h[ok_mask]]
with np.errstate(invalid="ignore"):
    is_down = (grid_sma200 < grid_sma50) | (WC < grid_sma200)   # موت تقاطع أو تحت SMA200
    is_up = (WC > grid_sma200) & (grid_sma200 >= grid_sma50)
n_down, n_up = int(is_down.sum()), int(is_up.sum())
check("E1 بيئات النافذة مصنفة (صاعدة/هابطة) بلا نظرة مستقبلية",
      n_down > 0 and n_up > 0, f"شموع هابطة={n_down:,} ({n_down / NWIN:.1%}) · صاعدة={n_up:,} ({n_up / NWIN:.1%})")

tm_gate = zigzag_fib_e2e_trendy_macd(WIN_CANDLES, osc_instances=INSTS10, osc_conditions=CONDS10)
bm_gate = zigzag_fib_e2e_blazing_macd(WIN_CANDLES, osc_instances=INSTS10, osc_conditions=CONDS10)
# إشارات الأصل (بعد بوابة الترند، قبل بوابة الموشرات) تُشتق من نتيجة الماكدية
# نفسها (final ∨ iblocked) — لا حاجة لتشغيل الترندية/الملتهبة مجدداً.


def _entry_cols(res_dict, prefix, kinds, iblocked=False):
    out = {}
    s = res_dict["series"]
    suffix = "_iblocked" if iblocked else ""
    for kind in kinds:
        col = s.get(f"{prefix}_entry{suffix}_{kind}") or []
        vals = [float(x) if x is not None else 0.0 for x in col]
        if len(vals) < NWIN:
            vals = vals + [0.0] * (NWIN - len(vals))
        out[kind] = vals
    return out


def _gated_from_macdized(res_dict, prefix, kinds):
    """إشارة الأصل المبوّبة (قبل بوابة الموشرات) = final ∨ iblocked لكل نوع."""
    fin = _entry_cols(res_dict, prefix, kinds)
    blk = _entry_cols(res_dict, prefix, kinds, iblocked=True)
    gated = {}
    for kind in kinds:
        gated[kind] = [1.0 if (fin[kind][i] >= 0.5 or blk[kind][i] >= 0.5) else 0.0
                       for i in range(NWIN)]
    return gated


tm_final = _entry_cols(tm_gate, "zzfetm", ("s1", "s2", "s3"))
tm_raw_trendy = _gated_from_macdized(tm_gate, "zzfetm", ("s1", "s2", "s3"))
bm_final = _entry_cols(bm_gate, "zzfbm", ("s1", "s2", "s3", "n5", "n6"))
bm_raw_blazing = _gated_from_macdized(bm_gate, "zzfbm", ("s1", "s2", "s3", "n5", "n6"))


def _stats(raw_cols, final_cols, mask):
    raw = kept = 0
    for kind in raw_cols:
        rc, fc = raw_cols[kind], final_cols[kind]
        for i in range(NWIN):
            if mask[i] and rc[i] >= 0.5:
                raw += 1
                if fc[i] >= 0.5:
                    kept += 1
    return raw, kept


raw_down_tm, kept_down_tm = _stats(tm_raw_trendy, tm_final, is_down)
raw_up_tm, kept_up_tm = _stats(tm_raw_trendy, tm_final, is_up)
raw_down_bm, kept_down_bm = _stats(bm_raw_blazing, bm_final, is_down)
raw_up_bm, kept_up_bm = _stats(bm_raw_blazing, bm_final, is_up)


def _pct(a, b):
    return round(a / b * 100, 2) if b else 0.0


surv_down_tm, surv_up_tm = _pct(kept_down_tm, raw_down_tm), _pct(kept_up_tm, raw_up_tm)
surv_down_bm, surv_up_bm = _pct(kept_down_bm, raw_down_bm), _pct(kept_up_bm, raw_up_bm)
check("E2 الترندية الماكدية: معدل بقاء الإشارات في المناطق الهابطة أقل بكثير من الصاعدة",
      surv_down_tm < surv_up_tm,
      f"هابطة: {kept_down_tm}/{raw_down_tm} = {surv_down_tm}% · صاعدة: {kept_up_tm}/{raw_up_tm} = {surv_up_tm}%")
check("E3 الملتهبة الماكدية: نفس السلوك — بقاء أقل في الهابطة",
      surv_down_bm < surv_up_bm,
      f"هابطة: {kept_down_bm}/{raw_down_bm} = {surv_down_bm}% · صاعدة: {kept_up_bm}/{raw_up_bm} = {surv_up_bm}%")
check("E4 الترندية الماكدية: فلترة قوية فعلاً في الهابط (بقاء ≤ 35%)",
      surv_down_tm <= 35.0, f"بقاء الهابط = {surv_down_tm}%")
check("E5 الملتهبة الماكدية: فلترة قوية فعلاً في الهابط (بقاء ≤ 35%)",
      surv_down_bm <= 35.0, f"بقاء الهابط = {surv_down_bm}%")
check("E6 البوابة تُفلتر (ليست هوية): إجمالي الماكدية < إجمالي الأصل",
      tm_gate["osc"]["counts"]["final_entries"] < tm_gate["osc"]["counts"]["trend_entries"]
      and bm_gate["osc"]["counts"]["final_entries"] < bm_gate["osc"]["counts"]["blazing_entries"],
      f"ترندية: {tm_gate['osc']['counts']['trend_entries']} → {tm_gate['osc']['counts']['final_entries']} · "
      f"ملتهبة: {bm_gate['osc']['counts']['blazing_entries']} → {bm_gate['osc']['counts']['final_entries']}")

EVID["sections"]["E_downtrend"] = {
    "pass": PASS - _pD(), "fail": FAIL - _fD(),
    "metrics": {
        "window": {"from": W_START, "to": W_END, "bars_1m": NWIN},
        "regimes": {"down_bars": n_down, "up_bars": n_up},
        "trendy_macdized": {
            "down": {"raw": raw_down_tm, "kept": kept_down_tm, "survival_pct": surv_down_tm},
            "up": {"raw": raw_up_tm, "kept": kept_up_tm, "survival_pct": surv_up_tm},
        },
        "blazing_macdized": {
            "down": {"raw": raw_down_bm, "kept": kept_down_bm, "survival_pct": surv_down_bm},
            "up": {"raw": raw_up_bm, "kept": kept_up_bm, "survival_pct": surv_up_bm},
        },
    },
}
_pE = lambda: _pD() + EVID["sections"]["E_downtrend"]["pass"]  # noqa: E731
_fE = lambda: _fD() + EVID["sections"]["E_downtrend"]["fail"]  # noqa: E731

# ===========================================================================
section("F) التكامل الكامل — محرك الاستراتيجيات (المسار الإنتاجي) → صفقات فعلية")

# PRO73-R3: قسم F يُشغّل في عملية ابنة معزولة (بوابة PRO73_F_CHILD أعلى الملف)
# — نفس المسار الإنتاجي بت-بت عبر مكتبة التكامل المشتركة integration_lib.
import subprocess  # noqa: E402

# حرّر ذاكرة الأقسام A-E قبل تشغيل الابنة (الابنة تحتاج ~1.6GB ذروة —
# بقاء كومة الأم عند ~1.4GB معها يتجاوز الـ4GB → OOM يقتل الأم أثناء الانتظار)
import ctypes  # noqa: E402
import gc as _gc  # noqa: E402
for _v in ("osc_np2", "res_full", "tm_gate", "bm_gate", "tm_final", "bm_final",
           "tm_raw_trendy", "bm_raw_blazing", "gated", "fin", "blk",
           "WIN_CANDLES", "WT", "WO", "WH", "WL", "WC", "WV"):
    globals().pop(_v, None)
_gc.collect()
try:
    ctypes.CDLL("libc.so.6").malloc_trim(0)
except Exception:
    pass

_F_EVID_PATH = os.path.join(HERE, "r73-evidence", "battery-r73-f.json")
_rproc = subprocess.run([sys.executable, os.path.abspath(__file__)],
                       env=dict(os.environ, PRO73_F_CHILD="1"), timeout=1200)
check("F0 عدّاء التكامل في عملية معزولة (ذاكرة) اكتمل بنجاح", _rproc.returncode == 0,
      f"rc={_rproc.returncode}")
with open(_F_EVID_PATH, "r", encoding="utf-8") as fh:
    _fdata = json.load(fh)
res_tmF = _fdata["trendy_macdized"]
res_bmF = _fdata["blazing_macdized"]

check("F1 ترنديه ماكديه عبر محرك الاستراتيجيات: أعمدة الماكدية حُقنت",
      res_tmF["osc_columns"] >= 59, f"أعمدة={res_tmF['osc_columns']}")
check("F2 قرارات BUY فعلية عبر شروط ind_zzfetm_entry_*", res_tmF["buys"] > 0 and res_tmF["trades"] > 0,
      f"BUY={res_tmF['buys']} صفقات={res_tmF['trades']} عوائد={res_tmF['total_return_pct']}%")
check("F3 أسماء القواعد في decision_reason تحمل هوية الماكدية",
      any("Trendy-MACD" in r for r in res_tmF["sample_reasons"]),
      f"أمثلة: {res_tmF['sample_reasons'][:2]}")
check("F4 ملتهبه ماكديه عبر محرك الاستراتيجيات: أعمدة ind_zzfbm_* حُقنت",
      res_bmF["osc_columns"] >= 69, f"أعمدة={res_bmF['osc_columns']}")
check("F5 قرارات BUY فعلية عبر شروط ind_zzfbm_entry_* (الخمسة)",
      res_bmF["buys"] > 0 and res_bmF["trades"] > 0,
      f"BUY={res_bmF['buys']} صفقات={res_bmF['trades']} عوائد={res_bmF['total_return_pct']}%")
check("F6 أسماء القواعد تحمل هوية الملتهبة الماكدية",
      any("Blazing-MACD" in r for r in res_bmF["sample_reasons"]),
      f"أمثلة: {res_bmF['sample_reasons'][:2]}")

EVID["sections"]["F_integration"] = {
    "pass": PASS - _pE(), "fail": FAIL - _fE(),
    "trendy_macdized": res_tmF,
    "blazing_macdized": res_bmF,
}

# ===========================================================================
ELAPSED = time.perf_counter() - T0_ALL
print(f"\n{'=' * 78}")
print(f"PRO73-R BATTERY: PASS={PASS} FAIL={FAIL} | زمن={ELAPSED:.1f}s")
if FAILURES:
    print("الفشل:")
    for n, d in FAILURES:
        print(f"  ❌ {n} — {d}")
EVID["summary"] = {"pass": PASS, "fail": FAIL, "elapsed_s": round(ELAPSED, 1),
                   "failures": [{"name": n, "detail": d} for n, d in FAILURES]}
os.makedirs(os.path.join(HERE, "r73-evidence"), exist_ok=True)
with open(os.path.join(HERE, "r73-evidence", "battery-r73.json"), "w", encoding="utf-8") as fh:
    json.dump(EVID, fh, ensure_ascii=False, indent=2, default=str)
print(f"الأدلة: {os.path.join(HERE, 'r73-evidence', 'battery-r73.json')}")
sys.exit(0 if FAIL == 0 else 1)
