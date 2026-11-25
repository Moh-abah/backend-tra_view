#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
✅ verify_ebreak_reclaim.py — بطارية تحقق حزمة GOLD-EBREAK-RECLAIM (EBREAK1)

تُشغَّل على المحرك بعد النشر مباشرة (من جذر تطبيق المحرك أو بتعيين
ENGINE_APP_PATH=<مسار جذر التطبيق>). 12 فحصاً صارماً:

  1) استيراد الوحدة المعدّلة من المحرك المنشور
  2) الإضافة الصرفة: كل الأعمدة القائمة (194) بت-بت على شموع اصطناعية حتمية
  3) أعمدة آلة الدخول الثاني الخمسة موجودة بقيمها المتجمدة
  4) قسم ema_break في النتيجة (break_length=100 · drop_pct=3 + العدادات)
  5) تمرير ema_break_length/ema_break_drop_pct عبر config_to_overlay_params
  6) بقاؤهما بعد القائمة البيضاء _normalize_overlay_params
  7) ظهور أعمدة ind_zzfetqe_ebreak_* عبر columns_for_configs (مسار الباك-تست)
  8) override: ema_break_drop_pct=5 يغيّر أعمدة ebreak فقط (البقية بت-بت)
  9) السببية: أعمدة ebreak عند الشمعة i لا تعتمد إلا على الشموع ≤ i
 10) الحتمية: تشغيلان متطابقان بت-بت
 11) دلالة الآلة: الاسترداد فقط بعد تسليح (نزول 3%) وإغلاق فوق قمة الشمعة
     الكاسرة — وحدة الآلة نفسها على متتاليات يدوية
 12) الصدى: ema_break_length=100 و ema_break_drop_pct=3.0 بالافتراضي

الاستعمال:
    python3 verify_ebreak_reclaim.py            # PYTHONPATH يشير إلى جذر التطبيق
"""
import sys, os, json

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
    _compute_ema_break_reclaim,
    ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_LENGTH,
    ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_DROP_PCT,
)
check("1) استيراد الوحدة المعدّلة من المحرك", True)

res1 = zigzag_fib_e2e_trendy_quantum_ema(df, **PARAMS)
ser1 = res1["series"]

# 2) pure addition — bit-identical pre-existing columns
mismatch = []
for k, frozen in expected["baseline_columns"].items():
    mine = ser1.get(k)
    if mine is None:
        mismatch.append(f"{k}: MISSING")
        continue
    for i, (a, b) in enumerate(zip(frozen, mine)):
        av = None if a is None else float(a)
        bv = None if b is None else float(b)
        if av is None and bv is None:
            continue
        if av is None or bv is None or (av != bv and abs(av - bv) > 0):
            mismatch.append(f"{k}@{i}: {av} != {bv}")
            break
check("2) الإضافة الصرفة: 194 عموداً قائماً بت-بت", not mismatch,
      "; ".join(mismatch[:3]) if mismatch else f"({len(expected['baseline_columns'])} عموداً × {N} شمعة)")

# 3) the five new columns with frozen values
NEW = ["zzfetqe_ebreak_break", "zzfetqe_ebreak_ref_high",
       "zzfetqe_ebreak_ref_close", "zzfetqe_ebreak_drop_ok",
       "zzfetqe_ebreak_reclaim"]
mm3 = []
for k in NEW:
    frozen = expected["ebreak_columns"].get(k)
    mine = ser1.get(k)
    if mine is None:
        mm3.append(f"{k}: MISSING"); continue
    for i, (a, b) in enumerate(zip(frozen, mine)):
        av = None if a is None else float(a)
        bv = None if b is None else float(b)
        if av is None and bv is None:
            continue
        if av is None or bv is None or (av != bv and abs(av - bv) > 0):
            mm3.append(f"{k}@{i}: {av} != {bv}")
            break
check("3) أعمدة الآلة الخمسة بقيمها المتجمدة", not mm3,
      "; ".join(mm3[:3]) if mm3 else "")

# 4) ema_break section
eb = res1.get("ema_break") or {}
counts = eb.get("counts") or {}
ok4 = (eb.get("enabled") is True and eb.get("break_length") == 100
       and eb.get("drop_pct") == 3.0 and counts == expected.get("ebreak_counts"))
check("4) قسم ema_break (100/3.0 + العدادات المتجمدة)", ok4,
      f"counts={counts}")

# 5) bridge
from app.services.indicators.overlay_columns import config_to_overlay_params
cfg = {"name": "zigzag_fib_e2e_trendy_quantum_ema", "type": "support_resistance",
       "params": {"mode": "luxalgo", "length": 226,
                  "ema_break_length": 100, "ema_break_drop_pct": 3.0}}
conv = config_to_overlay_params(cfg)
pp = conv.get("zzfib_e2e_trendy_quantum_ema") or {}
check("5) config_to_overlay_params يمرر المعاملين",
      pp.get("ema_break_length") == 100 and pp.get("ema_break_drop_pct") == 3.0)

# 6) whitelist
from app.services.indicators.overlays import _normalize_overlay_params
norm = _normalize_overlay_params("zzfib_e2e_trendy_quantum_ema", pp)
check("6) القائمة البيضاء تحافظ عليهما",
      norm.get("ema_break_length") == 100 and norm.get("ema_break_drop_pct") == 3.0)

# 7) backtest path
from app.services.indicators.overlay_columns import columns_for_configs
cols = columns_for_configs(df, [cfg])
need = ["ind_zzfetqe_ebreak_" + s for s in
        ("break", "ref_high", "ref_close", "drop_ok", "reclaim")]
check("7) مسار الباك-تست يعرض ind_zzfetqe_ebreak_* الخمسة",
      all(c in cols for c in need), f"missing={[c for c in need if c not in cols]}")

# 8) override changes ebreak only (عتبة 90% مستحيلة ⇒ صفر استردادات مؤكد)
res2 = zigzag_fib_e2e_trendy_quantum_ema(df, **dict(PARAMS, ema_break_drop_pct=90.0))
ser2 = res2["series"]
diff_other = [k for k in expected["baseline_columns"]
              if any((a is None) != (b is None) or
                     (a is not None and b is not None and float(a) != float(b))
                     for a, b in zip(expected["baseline_columns"][k], ser2.get(k) or []))]
reclaim2 = ser2.get("zzfetqe_ebreak_reclaim") or []
n_rc2 = sum(1 for v in reclaim2 if v and float(v) > 0)
check("8) override drop_pct=90: يغيّر ebreak فقط (صفر استرداد والبقية بت-بت)",
      not diff_other and n_rc2 == 0,
      f"غير المصرح={diff_other[:3]} · استردادات عند 90%={n_rc2}")

# 9) causality — prefix stability
ok9 = True
for cut in (N // 3, 2 * N // 3):
    rc = zigzag_fib_e2e_trendy_quantum_ema(df.iloc[:cut].reset_index(drop=True), **PARAMS)
    for k in NEW:
        a, b = rc["series"][k], ser1[k][:cut]
        for i, (x, y) in enumerate(zip(a, b)):
            xv = None if x is None else float(x)
            yv = None if y is None else float(y)
            if xv != yv and not (xv is None and yv is None):
                ok9 = False
                break
        if not ok9:
            break
    if not ok9:
        break
check("9) السببية (بادئة ثابتة عند قطعين)", ok9)

# 10) determinism
res3 = zigzag_fib_e2e_trendy_quantum_ema(df, **PARAMS)
ok10 = all(res3["series"][k] == ser1[k] for k in NEW)
check("10) الحتمية: تشغيلان متطابقان", ok10)

# 11) state machine semantics — hand-built sequences
# (ملاحظة الحساب: كسر@1 بإغلاق 99 و low 96.0 ≤ 99×0.97=96.03 ⇒ مسلّح فور الكسر)
br, rh, rcl, dk, rc, ev = _compute_ema_break_reclaim(
    [106.0, 101.0, 100.0, 101.5, 103.0],
    [104.0, 96.0, 99.0, 96.5, 99.5],
    [105.0, 99.0, 99.5, 97.0, 102.0],
    [None, 100.0, 100.0, 100.0, 100.0], 3.0)
ok11 = (br == [0, 1, 0, 0, 0] and dk == [0, 1, 1, 1, 1]
        and rc == [0, 0, 0, 0, 1] and rh[4] == 101.0 and rh[4] == ev[0]["ref_high"])
check("11) دلالة الآلة (كسر→تسليح→استرداد) على متتالية يدوية", ok11,
      f"br={br} dk={dk} rc={rc}")

# 12) defaults echo
pe = res1.get("params") or {}
check("12) الصدى الافتراضي: ema_break_length=100 · ema_break_drop_pct=3.0",
      pe.get("ema_break_length") == 100 and pe.get("ema_break_drop_pct") == 3.0
      and ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_LENGTH == 100
      and ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_DROP_PCT == 3.0)

print()
if FAILED:
    print(f"النتيجة: فشل {len(FAILED)} فحصاً: {FAILED}")
    sys.exit(1)
print("النتيجة: 12/12 فحصاً ناجحاً — الحزمة سليمة للنشر")
sys.exit(0)
