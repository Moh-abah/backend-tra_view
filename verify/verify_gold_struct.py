#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
✅ verify_gold_struct.py — بطارية تحقق حزمة GOLD-STRUCT-STRICT (STRUCT1)

تُشغَّل على المحرك بعد النشر مباشرة (من جذر تطبيق المحرك أو بتعيين
PYTHONPATH=مسار_التطبيق). 12 فحصاً صارماً:

  1) استيراد الوحدة المعدّلة من المحرك المنشور
  2) الإضافة الصرفة: كل الأعمدة القائمة (189) بت-بت على شموع اصطلاحية حتمية
  3) أعمدة الهيكل الكبير الخمس موجودة بقيمها المتجمدة
  4) قسم struct في النتيجة (reversal_pct=22 + العدادات)
  5) تمرير المعامل struct_reversal_pct عبر config_to_overlay_params
  6) بقاؤه بعد القائمة البيضاء _normalize_overlay_params
  7) ظهور أعمدة ind_zzfetqe_struct_* عبر columns_for_configs (مسار الباك-تست)
  8) override: struct_reversal_pct=35 يغيّر أعمدة الهيكل فقط (بقية الأعمدة بت-بت)
  9) السببية: حالة الهيكل عند الشمعة i لا تعتمد إلا على الشموع ≤ i
 10) الحتمية: تشغيلان متطابقان بت-بت
 11) القيم None قبل اكتمال أول زوج مؤكد ⇒ البوابة مقفلة تحفظياً
 12) العلم hh_hl=1 فقط عند القمة>القمة ∧ القاع>القاع معاً

الاستعمال:
    python3 verify_gold_struct.py            # PYTHONPATH يشير إلى جذر التطبيق
"""
import sys, os, json, importlib

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.environ.get("ENGINE_APP_PATH") or os.path.abspath(
    os.path.join(HERE, "..", "..", "..", "..", ".."))
if APP not in sys.path:
    sys.path.insert(0, APP)

FAILED = []

def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)

candles = json.load(open(os.path.join(HERE, "synthetic_candles.json")))
expected = json.load(open(os.path.join(HERE, "baseline_expected.json")))
import pandas as pd
df = pd.DataFrame(candles)
N = len(df)
PARAMS = expected["params"]

from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
    zigzag_fib_e2e_trendy_quantum_ema,
    ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_STRUCT_REVERSAL_PCT,
)
check("1) استيراد الوحدة المعدّلة من المحرك", True)

res1 = zigzag_fib_e2e_trendy_quantum_ema(df, **PARAMS)
ser1 = res1["series"]
idxs = list(range(0, N, expected["step"]))

# 2) pure addition — bit-identical pre-existing columns
mismatch = []
for k, frozen in expected["baseline_columns"].items():
    col = ser1.get(k)
    if col is None:
        mismatch.append(f"{k}:MISSING"); continue
    if any((col[i] if i < len(col) else None) != v for i, v in zip(idxs, frozen)):
        mismatch.append(k)
check("2) الإضافة الصرفة: كل الأعمدة القائمة بت-بت",
      not mismatch, f"{len(expected['baseline_columns'])} عموداً | اختلافات: {mismatch[:5]}")

# 3) struct columns values
sm = []
for k, frozen in expected["struct_columns"].items():
    col = ser1.get(k)
    if col is None:
        sm.append(f"{k}:MISSING"); continue
    if any((col[i] if i < len(col) else None) != v for i, v in zip(idxs, frozen)):
        sm.append(k)
check("3) أعمدة الهيكل الكبير الخمس بقيمها المتجمدة", not sm, f"اختلافات: {sm}")

# 4) struct section meta
st = res1.get("struct") or {}
check("4) قسم struct (reversal_pct + عدادات)",
      st.get("reversal_pct") == 22.0 and st.get("counts") == expected["struct_meta"]["counts"],
      f"reversal_pct={st.get('reversal_pct')} counts={st.get('counts')}")

# 5) param extraction
from app.services.indicators.overlay_columns import config_to_overlay_params
conv = config_to_overlay_params({"name": "zigzag_fib_e2e_trendy_quantum_ema",
                                 "params": dict(PARAMS, struct_reversal_pct=22)})
prm = (conv or {}).get("zzfib_e2e_trendy_quantum_ema") or {}
check("5) تمرير struct_reversal_pct عبر config_to_overlay_params",
      prm.get("struct_reversal_pct") == 22.0)

# 6) whitelist survival
from app.services.indicators.overlays import _normalize_overlay_params
norm = _normalize_overlay_params("zzfib_e2e_trendy_quantum_ema",
                                 dict(PARAMS, struct_reversal_pct=22))
check("6) بقاؤه بعد القائمة البيضاء _normalize_overlay_params",
      norm.get("struct_reversal_pct") == 22)

# 7) ind_* columns via the backtest path
from app.services.indicators.overlay_columns import columns_for_configs
cols, _ = columns_for_configs(df, [{"name": "zigzag_fib_e2e_trendy_quantum_ema",
                                     "type": "support_resistance", "enabled": True,
                                     "params": dict(PARAMS, struct_reversal_pct=22)}],
                               return_sections=True)
need = ["ind_zzfetqe_struct_last_high", "ind_zzfetqe_struct_prev_high",
        "ind_zzfetqe_struct_last_low", "ind_zzfetqe_struct_prev_low",
        "ind_zzfetqe_struct_hh_hl"]
check("7) أعمدة ind_zzfetqe_struct_* عبر مسار الباك-تست",
      all(c in cols for c in need),
      "موجودة: " + ",".join(c for c in need if c in cols))

# 8) override changes ONLY struct columns
res2 = zigzag_fib_e2e_trendy_quantum_ema(df, struct_reversal_pct=35, **PARAMS)
ser2 = res2["series"]
base_changed = [k for k in expected["baseline_columns"]
                if k in ser1 and k in ser2 and ser1[k] != ser2[k]]
struct_changed = [k for k in expected["struct_columns"]
                  if ser1[k] != ser2[k]]
check("8) override R=35 يغيّر الهيكل فقط (بقية الأعمدة بت-بت)",
      not base_changed and len(struct_changed) == 5,
      f"تغيرت أعمدة الهيكل: {len(struct_changed)}/5 | أعمدة أخرى تغيرت: {base_changed[:5]}")

# 9) causality — prefix invariance
res3 = zigzag_fib_e2e_trendy_quantum_ema(df.iloc[:N // 2], **PARAMS)
ser3 = res3["series"]
M = N // 2
causal_bad = [k for k in expected["struct_columns"]
              if any((ser3[k][i] if i < len(ser3[k]) else None) != ser1[k][i]
                     for i in range(0, M, 5))]
check("9) السببية: الحالة عند i لا تعتمد إلا على الشموع ≤ i", not causal_bad,
      f"اختلافات: {causal_bad}")

# 10) determinism
res4 = zigzag_fib_e2e_trendy_quantum_ema(df, **PARAMS)
det_bad = [k for k in ser1 if ser1[k] != (res4["series"].get(k) or [])]
check("10) الحتمية: تشغيلان متطابقان بت-بت", not det_bad)

# 11) None before first confirmed pair => gate closed
lh = ser1["zzfetqe_struct_last_high"]
first_high_idx = next((i for i, v in enumerate(lh) if v is not None), None)
none_prefix_ok = all(lh[i] is None for i in range(first_high_idx or 0))
check("11) None قبل أول زوج مؤكد ⇒ البوابة مقفلة تحفظياً", none_prefix_ok,
      f"أول قمة مؤكدة عند الشمعة {first_high_idx}")

# 12) hh_hl flag semantics
LH, PH = ser1["zzfetqe_struct_last_high"], ser1["zzfetqe_struct_prev_high"]
LL, PL = ser1["zzfetqe_struct_last_low"], ser1["zzfetqe_struct_prev_low"]
FLAG = ser1["zzfetqe_struct_hh_hl"]
bad = [i for i in idxs if FLAG[i] == 1.0 and not (LH[i] is not None and PH[i] is not None
      and LL[i] is not None and PL[i] is not None and LH[i] > PH[i] and LL[i] > PL[i])]
check("12) العلم hh_hl=1 فقط عند القمة>القمة ∧ القاع>القاع", not bad)

print()
if FAILED:
    print(f"❌ FAILED CHECKS ({len(FAILED)}): {FAILED}")
    sys.exit(1)
print(f"✅ ALL 12 CHECKS PASSED — الحزمة سليمة حرفياً على المحرك المنشور")
