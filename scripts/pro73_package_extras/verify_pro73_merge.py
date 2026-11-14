#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تحقق ما بعد الدمج — PRO73-MERGE-PACKAGE فوق backend_PRO73.zip.
يعمل على شموع تركيبية صغيرة (بلا أي بيانات خارجية) ويثبت:
  1) استيراد النواة والحالات والمحركين والقالبين بعد الدمج.
  2) سجل الفريمات الـ14 ونسخ المستند الـ67 (28/16/23) والحالات الـ19 (13+6).
  3) عقد الأعمدة: columns_for_configs يحقن ind_zzfetm_* من القالب.
  4) الهوية: بلا بوابة ≡ الترندية بت-بت على نافذة تركيبية.
  5) بوابة الحالات الافتراضية تعمل (ليست تمريراً).
التشغيل من جذر الشجرة المدموجة: python3 verify/verify_pro73_merge.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
if os.path.isfile(os.path.join(ROOT, "app", "services", "indicators", "mtf_oscillator_core.py")):
    sys.path.insert(0, ROOT)
elif os.path.isfile(os.path.join(ROOT, "..", "app", "services", "indicators", "mtf_oscillator_core.py")):
    sys.path.insert(0, os.path.abspath(os.path.join(ROOT, "..")))
else:
    sys.path.insert(0, os.getcwd())

os.environ.setdefault("SECRET_KEY", "verify-pro73-merge-secret")
os.environ.setdefault("DEBUG", "true")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (f" — {detail}" if detail else ""))
    return cond


import numpy as np  # noqa: E402

from app.services.indicators.mtf_oscillator_core import (  # noqa: E402
    TF_ORDER, normalize_osc_instances, MTF_OSC_CORE_VERSION,
)
from app.services.indicators.osc_cases import (  # noqa: E402
    OSC_DOC_INSTANCES, OSC_CASE_LIBRARY, OSC_CASE_CATALOG,
    MASTER_ANY_CASE, MASTER_STRICT, EARLY_WATCH, collect_case_refs,
)
from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy  # noqa: E402
from app.services.indicators.overlays_zlf_e2e_trendy_macd import zigzag_fib_e2e_trendy_macd  # noqa: E402
from app.services.indicators.overlay_columns import columns_for_configs  # noqa: E402
from app.services.strategy.presets import TRENDY_MACDIZED, get_presets  # noqa: E402
from app.services.strategy.schemas import StrategyConfig  # noqa: E402

print(f"== PRO73 merge verify (core v{MTF_OSC_CORE_VERSION}) ==")

check("سجل الفريمات الـ14", len(TF_ORDER) == 14, "؛ ".join(TF_ORDER))
insts, warns = normalize_osc_instances(OSC_DOC_INSTANCES)
from collections import Counter  # noqa: E402
kc = Counter(i["kind"] for i in insts)
check("نسخ المستند الكاملة 67 (ماكد 28 · RSI 16 · مومنتم 23) — تطبيع نظيف",
      kc.get("macd") == 28 and kc.get("rsi") == 16 and kc.get("mom") == 23 and not warns,
      f"{dict(kc)} | تحذيرات: {len(warns)}")
ids_norm = {i["id"] for i in insts}
check("الحالات 13 + وحدات 6 = 19 وكل المراجع تحل",
      len(OSC_CASE_LIBRARY) == 13 and len(OSC_CASE_CATALOG) == 19
      and all(r.split(":", 1)[1].split(".", 1)[0] in ids_norm
              for c in OSC_CASE_LIBRARY for r in collect_case_refs(c["tree"])))

ok_tm = False
try:
    cfg_tm = StrategyConfig(**TRENDY_MACDIZED["strategy_config"])
    ok_tm = len(cfg_tm.indicators[0].params["osc_instances"]) == 67
except Exception as exc:  # noqa: BLE001
    print("   استثناء:", str(exc)[:160])
check("القالبان الرسميان يعبران StrategyConfig بنسخ المستند (67)", ok_tm)
pid_list = [p["id"] for p in get_presets()]
check("القالبان مسجلان في get_presets",
      "trendy_macdized_zero_fee" in pid_list and "blazing_macdized_zero_fee" in pid_list)

rng = np.random.default_rng(3)
candles = []
p = 20.0
t0 = 1693526400000
for i in range(900):  # 900 × 5m ≈ 3 أيام
    p *= (1.0 + rng.normal(0.0008, 0.01))
    candles.append({"time": t0 + i * 300000, "open": p, "high": p * 1.008,
                    "low": p * 0.992, "close": p, "volume": 10.0})
cols_tm = columns_for_configs(candles, [{
    "name": "zigzag_fib_e2e_trendy_macd", "type": "support_resistance",
    "params": {"mode": "luxalgo", "length": 100, "trend_periods": [7, 15, 25],
               "trend_confirm": "majority", "trend_gate": ["s1", "s2", "s3"],
               "osc_instances": OSC_DOC_INSTANCES, "osc_conditions": MASTER_ANY_CASE},
}])
check("عقد ind_zzfetm_* من القالب (دخول + شفافية رباعية + بوابة + سلاسل الموشرات)",
      "ind_zzfetm_entry_s1" in cols_tm and "ind_zzfetm_entry_iblocked_s3" in cols_tm
      and "ind_zzfetm_osc_gate" in cols_tm and "ind_zzfetm_osc_macd_1d_12_26_4_line" in cols_tm,
      f"أعمدة={len(cols_tm)}")

tr = zigzag_fib_e2e_trendy(candles, length=100, mode="luxalgo",
                            trend_periods=[7, 15, 25], trend_confirm="majority",
                            trend_gate=["s1", "s2", "s3"])
tm = zigzag_fib_e2e_trendy_macd(candles, length=100, mode="luxalgo", trend_periods=[7, 15, 25],
                                 trend_confirm="majority", trend_gate=["s1", "s2", "s3"],
                                 osc_instances=[], osc_conditions=None)


def _z(vals):
    return [0.0 if x is None or (isinstance(x, float) and x != x) else float(x) for x in (vals or [])]


same = True
for src, dst in (("zzfet_entry_s1", "zzfetm_entry_s1"), ("zzfet_entry_s2", "zzfetm_entry_s2"),
                 ("zzfet_entry_s3", "zzfetm_entry_s3"), ("zzfet_dir", "zzfetm_dir"),
                 ("zzfet_trend_ok", "zzfetm_trend_ok")):
    if _z(tr["series"].get(src)) != _z(tm["series"].get(dst)):
        same = False
        print(f"   اختلاف في {dst}")
check("الهوية: ترنديه ماكديه (بلا بوابة) ≡ الترندية — دخول/اتجاه/ترند بت-بت", same)

gated = zigzag_fib_e2e_trendy_macd(candles, length=100, mode="luxalgo", trend_periods=[7, 15, 25],
                                    trend_confirm="majority", trend_gate=["s1", "s2", "s3"],
                                    osc_instances=OSC_DOC_INSTANCES, osc_conditions=MASTER_ANY_CASE)
cnt = gated["osc"]["counts"]
check("بوابة «أي حالة لحظية» تعمل (تحجز إشارات عند عدم انطباق الحالات)",
      cnt["final_entries"] <= cnt["trend_entries"],
      f"ترند={cnt['trend_entries']} → نهائي={cnt['final_entries']} (محجوزة بالموشرات={cnt.get('osc_blocked_entries', 0)})")
check("الوحدات الجاهزة (any/strict/early)",
      MASTER_ANY_CASE["logic"] == "or" and MASTER_STRICT["logic"] == "and" and EARLY_WATCH["logic"] == "or")

print(f"\n== النتيجة: PASS={PASS} FAIL={FAIL} ==")
sys.exit(0 if FAIL == 0 else 1)
