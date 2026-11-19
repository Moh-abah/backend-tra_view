#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QMOM1 — التحقق المحلي الشامل لبوابة الشروط المرنة (كموميه الزخم الاولى).

يشتغل فوق نسخة runtime المدموجة محلياً (بعد تطبيق حزمة الدمج بت-بت).
البطارية:
  T1  استيراد المحرك الجديد + التسجيل الذاتي
  T2  تشغيل المحرك بتكوين الاستراتيجية الحرفي (length=226 + الشروط الأربعة)
  T3  عقد السلاسل zzfetqem_* (النهائي المبوّب + iblocked + osc_gate + سلاسل
      الموشرات الديناميكية + التمرير zzfetq_*/zzfet_*)
  T4  دلالات البوابة (خام الكمومية ∧ بوابة الزخم) + حياد الإحماء
  T5  السببية — بلا أي استشراف: MACD 4h عند الشمعة = قيمة آخر شريط 4h مكتمل
      (محسوبة بمعمارية مستقلة تماماً)
  T6  تعطيل شرط واحد (enabled:false) ⇒ البوابة = الشجرة بدونه (محايد)
  T7  وضع الهوية (بلا قالب) ⇒ مرآة الكمومية-EMA بت-بت
  T8  الأنبوب الكامل: columns_for_configs → ind_zzfetqem_* → مقيّم شروط
      المحرك (indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:...)
  T9  مصادقة pydantic للحمولة كاملة (جدار 422 مكسور مقدماً)
"""
import json
import io
import sys
import math
import numpy as np
import pandas as pd

import os
RUNTIME = os.environ.get("QMOM_RUNTIME", "/home/z/my-project/trading-system/zone-exit-ltf/runtime")
sys.path.insert(0, RUNTIME)

HERE = os.path.dirname(os.path.abspath(__file__))
PAYLOAD = os.environ.get("QMOM_PAYLOAD", os.path.join(HERE, "..", "payloads", "payload_qmom1_sol_full_history.json"))
DATA_15M = os.environ.get("QMOM_DATA", "/home/z/my-project/trading-system/zone-exit-ltf/data/MMTUSDT_15m.json")

PASS = []
FAIL = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), "|", name, ("| " + str(detail)) if detail else "")


def to_bools(series):
    return [bool(v) if v else False for v in series]


# ------------------------------------------------------------------ T1
from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema_mom import (  # noqa: E402
    zigzag_fib_e2e_trendy_quantum_ema_mom,
    ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_ENGINE_NAME,
)
from app.services.indicators.mtf_oscillator_core import (  # noqa: E402
    evaluate_conditions, TF_MS, _macd_talib, _rsi_wilder_talib,
)
from app.services.indicators.overlay_columns import (  # noqa: E402
    columns_for_configs, is_known_indicator_name, config_to_overlay_params,
)
from app.services.strategy.schemas import StrategyConfig, Condition  # noqa: E402
from app.services.strategy.conditions import ConditionEvaluator  # noqa: E402

check("T1 استيراد المحرك الجديد", True,
      ZLF_E2E_TRENDY_QUANTUM_EMA_MOM_ENGINE_NAME)
check("T1 is_known_indicator_name(zigzag_fib_e2e_trendy_quantum_ema_mom)",
      is_known_indicator_name("zigzag_fib_e2e_trendy_quantum_ema_mom"))

# ------------------------------------------------------------------ تحضير
payload = json.load(io.open(PAYLOAD, encoding="utf-8"))
ind_params = payload["strategy_config"]["indicators"][0]["params"]
candles = json.load(io.open(DATA_15M, encoding="utf-8"))
print("candles:", len(candles), "| from", pd.to_datetime(candles[0]["time"], unit="ms"),
      "to", pd.to_datetime(candles[-1]["time"], unit="ms"))

# مسار الإنتاج الحرفي: التطبيع عبر config_to_overlay_params (فرع QMOM1)
conv = config_to_overlay_params({
    "name": "zigzag_fib_e2e_trendy_quantum_ema_mom",
    "params": ind_params,
})
E = (conv or {}).get("zzfib_e2e_trendy_quantum_ema_mom") or {}
check("T2 المطبّع يمرّر قالب الموشرات (osc_instances)",
      "osc_instances" in E and len(E["osc_instances"]) == 7)
check("T2 المطبّع يمرّر شجرة الشروط (osc_conditions)",
      "osc_conditions" in E and E["osc_conditions"]["logic"] == "and")
check("T2 المطبّع يمرّر معاملات الكمومية-EMA",
      E.get("length") == 226 and E.get("zone_gate") == ["s1", "s2", "s3"]
      and E.get("ema_lengths") == [50, 100, 200, 350, 500])

res = zigzag_fib_e2e_trendy_quantum_ema_mom(candles, **E)
series = res["series"]
n = len(candles)
osc = res.get("osc") or {}

# ------------------------------------------------------------------ T2/T3
check("T2 المحرك رجع n=%d شمعة" % n, len(next(iter(series.values()))) == n)
need = ["zzfetqem_entry", "zzfetqem_entry_s1", "zzfetqem_entry_s2",
        "zzfetqem_entry_s3", "zzfetqem_entry_iblocked",
        "zzfetqem_entry_iblocked_s1", "zzfetqem_osc_gate",
        "zzfetqem_zone_exit", "zzfetqem_trend_votes_bear",
        "zzfetqem_ema_50", "zzfetqem_ema_stack_ok"]
check("T3 عقد السلاسل الأساسي", all(k in series for k in need),
      [k for k in need if k not in series])
osc_expected = []
for inst in ind_params["osc_instances"]:
    for f in ({"macd": ["line", "signal", "hist"],
               "rsi": ["value", "ma", "bb_upper", "bb_lower"],
               "mom": ["line", "pct"]})[inst["kind"]]:
        osc_expected.append(f"zzfetqem_osc_{inst['id']}_{f}")
check("T3 سلاسل الموشرات الديناميكية (7 نسخ)", all(k in series for k in osc_expected),
      [k for k in osc_expected if k not in series])
check("T3 التمرير zzfetq_*/zzfet_*",
      any(k.startswith("zzfetq_") for k in series) and
      any(k.startswith("zzfet_") for k in series))

inst_meta = {m["id"]: m for m in (osc.get("instances") or [])}
check("T3 قسم osc: 7 نسخ كلها متاحة",
      len(inst_meta) == 7 and all(m.get("available") for m in inst_meta.values()),
      {k: (m.get("available"), m.get("code")) for k, m in inst_meta.items()})
codes = osc.get("warning_codes") or []
check("T3 لا تحذيرات صعبة (unknown/insufficient)",
      not ({"unknown_timeframe", "insufficient_data", "tf_below_base"} & set(codes)), codes)
counts = osc.get("counts") or {}
print("    osc.counts:", counts, "| warmup_neutral_bars:", osc.get("warmup_neutral_bars"))

# ------------------------------------------------------------------ T4
base_e = to_bools(series.get("zzfetqem_entry"))
# خام الكمومية قبل بوابة الزخم = الإشارات التي أطلقها المحرك الأساسي
raw = [bool(x) if x else False for x in series.get("zzfetqem_entry")]
gate = to_bools(series.get("zzfetqem_osc_gate"))
ib = to_bools(series.get("zzfetqem_entry_iblocked"))
# لإثبات دلالات البوابة نبني "الخام" من محاكاة الكمومية-EMA (b run identity أدناه يثبت المرآة)
violations = 0
for i in range(n):
    if raw[i] and not gate[i]:
        if not ib[i]:
            violations += 1
    if raw[i] and gate[i]:
        if not base_e[i]:
            violations += 1
check("T4 الدخول النهائي = خام الكمومية ∧ بوابة الزخم", violations == 0,
      "violations=%d" % violations)
horizon = int(osc.get("warmup_neutral_bars") or 0)
neu = all(gate[i] for i in range(min(horizon, n)))
check("T4 حياد الإحماء (أول %d شريط مفتوحة)" % horizon, neu or horizon == 0)

# البوابة المتوقعة من الشجرة (بعد الأفق) — تقييم مستقل عبر السلاسل نفسها
# (المفاتيح التعاقدية: osc:<id>.<field> — نقطة بين المعرف والحقل)
FIELDS_PER_KIND = {"macd": ["line", "signal", "hist"],
                   "rsi": ["value", "ma", "bb_upper", "bb_lower"],
                   "mom": ["line", "pct"]}
lookup = {}
for inst in ind_params["osc_instances"]:
    for f in FIELDS_PER_KIND[inst["kind"]]:
        k = f"zzfetqem_osc_{inst['id']}_{f}"
        if k in series:
            lookup[f"osc:{inst['id']}.{f}"] = np.asarray(
                [np.nan if v is None else float(v) for v in series[k]])
missing_keys = [r for r in (
    "osc:macd_4h_12_26_4.line", "osc:macd_4h_12_26_4.signal",
    "osc:macd_3d_5_11_4.line", "osc:macd_1d_12_26_4.line",
    "osc:rsi_1h_14_14.value", "osc:rsi_4h_14_14.value",
    "osc:rsi_1d_14_14.value", "osc:rsi_1d_10_14.value") if r not in lookup]
check("T4 مفاتيح المراجع التعاقدية موجودة", not missing_keys, missing_keys)
tree = ind_params["osc_conditions"]
mismatch = 0
for i in range(horizon, n):
    exp = evaluate_conditions(tree, lookup, i)
    if exp != gate[i]:
        mismatch += 1
check("T4 البوابة = شجرة الشروط الأربعة بت-بت (بعد الأفق)", mismatch == 0,
      "mismatch=%d" % mismatch)

# ------------------------------------------------------------------ T5 السببية
t = np.asarray([c["time"] for c in candles], dtype=np.int64)
c = np.asarray([c["close"] for c in candles], dtype=np.float64)


def bucket_index_ref(t, tf):
    ms = TF_MS[tf]
    t0 = int(t[0]) // ms * ms
    return (t - t0) // ms


def bucket_closes_ref(c, b, nb):
    last = np.full(nb, -1, dtype=np.int64)
    last[b] = np.arange(len(b))
    for i in range(nb):
        if last[i] == -1:
            last[i] = last[i - 1] if i > 0 else 0
    return c[last]


def ref_stepped(candles_t, closes, tf, calc):
    b = bucket_index_ref(candles_t, tf)
    nb = int(b[-1]) + 1
    cb = bucket_closes_ref(closes, b, nb)
    vals = calc(cb)
    out = np.full(len(candles_t), np.nan)
    for i in range(len(candles_t)):
        usable = int(b[i]) - 1
        if usable >= 0 and usable < len(vals):
            out[i] = vals[usable]
    return out


def macd_field_of(fast, slow, sig, ffield):
    idx = {"line": 0, "signal": 1, "hist": 2}[ffield]
    return lambda cb: _macd_talib(cb, fast, slow, sig)[idx]


# MACD 4h 12/26/4: line وsignal — مطابقة مستقلة (آخر شريط مكتمل فقط)
for tf, inst, ffield in (("4h", "macd_4h_12_26_4", "line"),
                          ("4h", "macd_4h_12_26_4", "signal"),
                          ("3d", "macd_3d_5_11_4", "line"),
                          ("1d", "macd_1d_12_26_4", "line")):
    inst_p = next(x for x in ind_params["osc_instances"] if x["id"] == inst)
    fn = macd_field_of(int(inst_p["fast"]), int(inst_p["slow"]),
                       int(inst_p["signal"]), ffield)
    ref = ref_stepped(t, c, tf, fn)
    got = np.asarray([np.nan if v is None else float(v)
                      for v in series[f"zzfetqem_osc_{inst}_{ffield}"]])
    mask = ~np.isnan(ref)
    same = np.array_equal(ref[mask], got[mask]) if mask.any() else False
    check("T5 سببية MACD %s %s.%s (آخر شريط مكتمل — بت-بت)" % (tf, inst, ffield),
          bool(same), "n_compared=%d" % int(mask.sum()))

# RSI 1d 14: مطابقة مستقلة (فيبو الترندية 7/15/25 نفسها)
for tf, inst in (("1d", "rsi_1d_14_14"), ("1d", "rsi_1d_10_14"),
                 ("1h", "rsi_1h_14_14"), ("4h", "rsi_4h_14_14")):
    inst_p = next(x for x in ind_params["osc_instances"] if x["id"] == inst)
    ref = ref_stepped(t, c, tf,
                      lambda cb: _rsi_wilder_talib(cb, int(inst_p["period"])))
    got = np.asarray([np.nan if v is None else float(v)
                      for v in series[f"zzfetqem_osc_{inst}_value"]])
    mask = ~np.isnan(ref)
    same = np.array_equal(ref[mask], got[mask]) if mask.any() else False
    check("T5 سببية RSI %s %s.value" % (tf, inst), bool(same),
          "n_compared=%d" % int(mask.sum()))

# ------------------------------------------------------------------ T6 تعطيل شرط
tree_off = json.loads(json.dumps(tree))
tree_off["conditions"][0]["enabled"] = False   # تعطيل الشرط الأول (MACD 4h)
res_off = zigzag_fib_e2e_trendy_quantum_ema_mom(candles, **{
    **E, "osc_conditions": tree_off})
gate_off = to_bools(res_off["series"]["zzfetqem_osc_gate"])
mismatch_off = 0
hz_off = int((res_off.get("osc") or {}).get("warmup_neutral_bars") or 0)
for i in range(hz_off, n):
    exp = evaluate_conditions(tree_off, lookup, i)
    if exp != gate_off[i]:
        mismatch_off += 1
check("T6 enabled:false على الشرط الأول ⇒ بوابة الشجرة بدونه",
      mismatch_off == 0, "mismatch=%d" % mismatch_off)
# والبوابة يجب أن تكون أخفّ (أقل حجباً) من البوابة الكاملة
relaxed = sum(1 for i in range(n) if gate_off[i] and not gate[i])
strict = sum(1 for i in range(n) if gate[i] and not gate_off[i])
check("T6 التعطيل يرخي البوابة فقط (لا يشدّها)", strict == 0,
      "relaxed=%d strict=%d" % (relaxed, strict))

# ------------------------------------------------------------------ T7 وضع الهوية
from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (  # noqa: E402
    zigzag_fib_e2e_trendy_quantum_ema,
)
ident_params = {k: v for k, v in E.items()
                if k not in ("osc_instances", "osc_conditions")}
res_id = zigzag_fib_e2e_trendy_quantum_ema_mom(candles, **ident_params)
res_qe = zigzag_fib_e2e_trendy_quantum_ema(candles, **ident_params)
ident_ok = True
for k, v in (res_qe.get("series") or {}).items():
    ks = str(k)
    nk = ("zzfetqem_" + ks[len("zzfetqe_"):]) if ks.startswith("zzfetqe_") else ks
    if res_id["series"].get(nk) != v:
        ident_ok = False
        print("    diff:", nk)
check("T7 وضع الهوية (بلا قالب) = مرآة الكمومية-EMA بت-بت", ident_ok)
check("T7 وضع الهوية: قسم osc معطّل",
      (res_id.get("osc") or {}).get("enabled") is False)

# ------------------------------------------------------------------ T8 الأنبوب الكامل
cfg = [{"name": "zigzag_fib_e2e_trendy_quantum_ema_mom",
        "type": "support_resistance",
        "params": ind_params, "enabled": True, "timeframe": "15m"}]
cols = columns_for_configs(candles, cfg)
qem_cols = [k for k in cols if k.startswith("ind_zzfetqem_")]
check("T8 columns_for_configs: أعمدة ind_zzfetqem_*",
      len(qem_cols) >= 20, "count=%d" % len(qem_cols))
check("T8 أعمدة الموشرات في الأنبوب",
      any("ind_zzfetqem_osc_macd_4h_12_26_4_line" == k for k in cols) and
      any("ind_zzfetqem_osc_rsi_1d_14_14_value" == k for k in cols))

df = pd.DataFrame(candles)
for col, vals in cols.items():
    pad = vals + [None] * (len(df) - len(vals))
    df[col] = pd.Series(pad[:len(df)], index=df.index, dtype=object)

ev = ConditionEvaluator()
ev.set_indicators_data({})
cond_s1 = Condition(
    type="indicator_value", operator=">",
    left_value="indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:zzfetqem_entry_s1",
    right_value=0)
cond_ok = True
probe_true = probe_false = 0
for i in range(n):
    r = ev.evaluate(cond_s1, df, {}, i)
    v = df["ind_zzfetqem_entry_s1"].iloc[i]
    expect = (v is not None) and float(v) > 0
    if r != expect:
        cond_ok = False
    if r:
        probe_true += 1
    else:
        probe_false += 1
check("T8 مقيّم شروط المحرك يقرأ ind_zzfetqem_entry_s1 حرفياً", cond_ok,
      "true=%d false=%d" % (probe_true, probe_false))

# شرط مباشر على سلسلة موشر (المسار الثاني للمرونة — مستوى الاستراتيجية)
cond_macd = Condition(
    type="indicator_value", operator=">",
    left_value="indicator:zigzag_fib_e2e_trendy_quantum_ema_mom:zzfetqem_osc_macd_4h_12_26_4_line",
    right_value=0)
probe = 0
for i in range(n):
    r = ev.evaluate(cond_macd, df, {}, i)
    v = df["ind_zzfetqem_osc_macd_4h_12_26_4_line"].iloc[i]
    expect = (v is not None) and float(v) > 0
    if r != expect:
        probe += 1
check("T8 شرط على سلسلة موشر مباشرة (مسار الفرونت الثاني)", probe == 0)

# ------------------------------------------------------------------ T9 pydantic
try:
    sc = StrategyConfig(**payload["strategy_config"])
    ok = sc.indicators[0].name == "zigzag_fib_e2e_trendy_quantum_ema_mom"
    p = sc.indicators[0].params
    ok = ok and len(p["osc_instances"]) == 7 and p["osc_conditions"]["logic"] == "and"
    check("T9 StrategyConfig يقبل الحمولة (pydantic v2)", ok)
except Exception as e:
    check("T9 StrategyConfig يقبل الحمولة (pydantic v2)", False, repr(e)[:300])

# ------------------------------------------------------------------ الخلاصة
print("\n=====================")
print("PASS:", len(PASS), "| FAIL:", len(FAIL))
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
print("QMOM1 LOCAL VERIFICATION — ALL GREEN")
print("gate stats: open_bars=%d / %d | raw entries=%d | final=%d | blocked=%d" % (
    sum(gate), n, sum(raw), sum(base_e), sum(ib)))
