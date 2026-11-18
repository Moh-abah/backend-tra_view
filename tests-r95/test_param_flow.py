#!/usr/bin/env python3
"""test_param_flow.py — اختبار مسار المعامل عبر طبقة الاستراتيجية كاملاً.

يتحقق أن zone_exit_resolution يمر عبر:
  strategy_config JSON → config_to_overlay_params (overlay_columns)
  → columns_for_configs → compute_overlays → المحرك → أعمدة ind_*

وهذا هو نفس المسار الذي يسلكه _prepare_indicators في strategy_engine1
أثناء الباك تست الحقيقي — أي أن وضعه في params المؤشر يكفي، بلا أي
تغيير في قواعد الخروج (نفس left_value: zzfetqe_zone_exit).
"""
import sys
from pathlib import Path

NEW_ROOT = Path("/home/z/drive-download/backend_PRO95_extracted")
sys.path.insert(0, str(NEW_ROOT))

import pandas as pd  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def load_df(n=6000):
    df = pd.read_parquet(NEW_ROOT / "data/history/SOLUSDT_15m.parquet").head(n)
    idx = pd.to_datetime(df["time"], unit="ms", utc=True)
    out = df.drop(columns=["time"]).copy()
    out.index = pd.DatetimeIndex(idx, name="time")
    return out


def main():
    from app.services.indicators.overlay_columns import (
        columns_for_configs, config_to_overlay_params, is_known_indicator_name)

    base_ind = {
        "name": "zigzag_fib_e2e_trendy_quantum_ema",
        "type": "support_resistance",
        "params": {
            "mode": "luxalgo", "length": 226,
            "trend_periods": [7, 15, 25], "trend_confirm": "majority",
            "trend_gate": ["s1", "s2", "s3"], "zone_gate": ["s1"],
            "ema_lengths": [50, 100, 200, 350, 500], "ema_resolution": "60",
            "ema_source": "close", "ema_offset": 0, "ema_gate": ["s1", "s2", "s3"],
        },
        "enabled": True, "timeframe": "15m",
    }

    df = load_df()

    print("— 1) التطبيع: config_to_overlay_params")
    conv = config_to_overlay_params({**base_ind, "params": {**base_ind["params"],
                                       "zone_exit_resolution": "240"}})
    qe = conv.get("zzfib_e2e_trendy_quantum_ema") or {}
    check("1a: zone_exit_resolution عبر التطبيع", qe.get("zone_exit_resolution") == "240")
    conv2 = config_to_overlay_params({**base_ind, "params": {**base_ind["params"],
                                        "zone_exit_resolution": "240", "zone_exit_length": 50}})
    qe2 = conv2.get("zzfib_e2e_trendy_quantum_ema") or {}
    check("1b: zone_exit_length عبر التطبيع", qe2.get("zone_exit_length") == 50)
    conv3 = config_to_overlay_params({**base_ind, "params": {**base_ind["params"],
                                        "exit_resolution": "1D"}})
    qe3 = conv3.get("zzfib_e2e_trendy_quantum_ema") or {}
    check("1c: المرادف exit_resolution يعمل", qe3.get("zone_exit_resolution") == "1D")
    conv4 = config_to_overlay_params(base_ind)
    qe4 = conv4.get("zzfib_e2e_trendy_quantum_ema") or {}
    check("1d: بلا المعامل = لا يظهر في التطبيع", "zone_exit_resolution" not in qe4)
    check("1e: المحرك معروف بالاسم", is_known_indicator_name("zigzag_fib_e2e_trendy_quantum_ema"))

    print("— 2) المسار الكامل: columns_for_configs (نفس مسار الباك تست)")
    cols_none = columns_for_configs(df, [base_ind])
    check("2a: بلا المعامل — لا عمود htf_on", "ind_zzfetqe_zone_exit_htf_on" not in cols_none)
    check("2b: بلا المعامل — عمود الخروج موجود",
          "ind_zzfetqe_zone_exit" in cols_none and len(cols_none["ind_zzfetqe_zone_exit"]) == len(df))

    ind240 = {**base_ind, "params": {**base_ind["params"], "zone_exit_resolution": "240"}}
    cols240 = columns_for_configs(df, [ind240])
    check("2c: مع 240 — عمود htf_on ظهر",
          "ind_zzfetqe_zone_exit_htf_on" in cols240)
    check("2d: مع 240 — عمود zone_exit_base ظهر",
          "ind_zzfetqe_zone_exit_base" in cols240)
    check("2e: أطوال الأعمدة = عدد الشموع",
          all(len(cols240[k]) == len(df) for k in (
              "ind_zzfetqe_zone_exit", "ind_zzfetqe_zone_exit_base",
              "ind_zzfetqe_zone_exit_htf_on", "ind_zzfetqe_zone_exit_htf_enter")))
    check("2f: خروج 240 مختلف عن الأساس",
          cols240["ind_zzfetqe_zone_exit"] != cols_none["ind_zzfetqe_zone_exit"])
    check("2g: zone_exit_base == خروج الأساس",
          cols240["ind_zzfetqe_zone_exit_base"] == cols_none["ind_zzfetqe_zone_exit"])
    # الدخول لم يتغير عبر المسار الكامل
    check("2h: الدخول s1 عبر المسار لم يتغير",
          cols240.get("ind_zzfetqe_entry_s1") == cols_none.get("ind_zzfetqe_entry_s1"))

    print("— 3) محرك الكمومية غير الأسية (zone_exit على zzfetq_)")
    base_q = {
        "name": "zigzag_fib_e2e_trendy_quantum",
        "type": "support_resistance",
        "params": {"mode": "luxalgo", "length": 100,
                   "trend_periods": [7, 15, 25], "trend_confirm": "majority",
                   "trend_gate": ["s1", "s2", "s3"], "zone_gate": ["s1", "s2", "s3"]},
        "enabled": True, "timeframe": "15m",
    }
    colsq0 = columns_for_configs(df, [base_q])
    colsq1 = columns_for_configs(df, [{**base_q, "params": {
        **base_q["params"], "zone_exit_resolution": "60"}}])
    check("3a: zzfetq_zone_exit تغيّر مع 60",
          colsq1["ind_zzfetq_zone_exit"] != colsq0["ind_zzfetq_zone_exit"])
    check("3b: أعمدة الشفافية zzfetq ظهرت",
          "ind_zzfetq_zone_exit_base" in colsq1 and "ind_zzfetq_zone_exit_htf_on" in colsq1)
    check("3c: الدخول zzfetq_entry_s1 لم يتغير",
          colsq1.get("ind_zzfetq_entry_s1") == colsq0.get("ind_zzfetq_entry_s1"))

    print(f"\nالنتيجة: ✅ {PASS} · ❌ {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
