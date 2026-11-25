#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EBREAK1 فحص 6-11: وحدة الآلة (سيناريو اصطناعي حتمي) + السببية + الحتمية + الجسر + مسار الباك-تست."""
import sys, json
APP = "/home/z/my-project/trading-system/ebreak-reclaim/runtime_after"
sys.path.insert(0, APP)
import pandas as pd, numpy as np
from app.services.indicators.overlays_zlf_e2e_trendy_quantum_ema import (
    zigzag_fib_e2e_trendy_quantum_ema,
    _compute_ema_break_reclaim,
    ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_LENGTH as DLEN,
    ZLF_E2E_TRENDY_QUANTUM_EMA_DEFAULT_EMA_BREAK_DROP_PCT as DDROP,
)

FAILED = []
def check(name, cond, detail=""):
    s = "PASS" if cond else "FAIL"
    print(f"[{s}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILED.append(name)

# ── 6) اختبار الوحدة: سيناريو كسر → نزول 3% → استرداد (حتمي يدوي)
# ema ثابت 100.0 لتبسيط الكسر؛ الشموع:
# 0: close 105 ≥ 100 (فوق الخط)
# 1: close 99 < 100 → شمعة الكسر: high=101, close=99, low=98.5 (98.5 > 99*0.97=96.03 → غير مسلح)
# 2: close 98.8, low 96.0 → 96.0 ≤ 96.03 → تسليح (drop_ok=1)
# 3: close 97 (تحت الخط، لا استرداد)
# 4: close 102 > high(101) → استرداد → إشارة دخول ثانٍ
# 5: close 103 — الحلقة مغلقة: refs=None, drop_ok=0
ema = [None, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]
high = [106.0, 101.0, 99.5, 97.5, 103.0, 104.0]
low =  [104.0, 98.5, 96.0, 96.5, 99.0, 103.0]
close=[105.0, 99.0, 98.8, 97.0, 102.0, 103.0]
br, rh, rcl, dk, rc, ev = _compute_ema_break_reclaim(high, low, close, ema, 3.0)
check("6a) شمعة الكسر عند 1", br == [0, 1, 0, 0, 0, 0], f"br={br}")
check("6b) التسليح عند 2 (low 96.0 ≤ 96.03)", dk == [0, 0, 1, 1, 1, 0], f"dk={dk}")
check("6c) الاسترداد عند 4 (close 102 > high 101)", rc == [0, 0, 0, 0, 1, 0], f"rc={rc}")
check("6d) refs قيم عند 1-4 و None بعد الإغلاق",
      rh[1] == 101.0 and rh[4] == 101.0 and rh[5] is None and rcl[1] == 99.0,
      f"rh={rh} rcl={rcl}")
check("6e) أحداث: break@1 ثم reclaim@4",
      [e["kind"] for e in ev] == ["break", "reclaim"] and ev[0]["bar"] == 1 and ev[1]["bar"] == 4)

# 6f) مطرقة الاسترداد: تسليح وإطلاق بنفس الشمعة (ذيل 3% ثم إغلاق فوق القمة)
br2, _, _, dk2, rc2, _ = _compute_ema_break_reclaim(
    [106.0, 101.0], [104.0, 95.0], [105.0, 99.0],
    [None, 100.0, 100.0], 3.0)
check("6f) مطرقة: كسر@1 مسلح فوراً (low 95 ≤ 96.03) و الاسترداد لا يطلق بنفس الشمعة (close 99 < high 101)",
      br2 == [0, 1] and dk2 == [0, 1] and rc2 == [0, 0],
      f"br={br2} dk={dk2} rc={rc2}")

# 6g) إشارة واحدة لكل حلقة: بعد الاسترداد لا توجد إشارة ثانية بنفس الحلقة
br3, rh3, rcl3, dk3, rc3, _ = _compute_ema_break_reclaim(
    [106.0, 101.0, 100.0, 101.5, 103.0, 104.0, 105.0],
    [104.0, 96.0, 99.0, 96.5, 99.5, 103.5, 104.5],
    [105.0, 99.0, 99.5, 97.0, 102.0, 103.5, 104.5],
    [None] + [100.0] * 6, 3.0)
check("6g) إشارة واحدة فقط في الحلقة (عند 4) ثم لا شيء",
      rc3 == [0, 0, 0, 0, 1, 0, 0] and br3 == [0, 1, 0, 0, 0, 0, 0],
      f"rc={rc3}")

# 6h) كسر جديد يفتح حلقة جديدة بقيم شمعته (بعد استرداد فوق الخط ثم كسر جديد)
# 5: close 104.5 (فوق الخط) · 6: close 99.5 < 100 → كسر جديد high=104.8 low=99.0
br4, rh4, rcl4, dk4, rc4, ev4 = _compute_ema_break_reclaim(
    [106.0, 101.0, 100.0, 101.5, 103.0, 105.5, 104.8],
    [104.0, 96.0, 99.0, 96.5, 99.5, 105.0, 99.0],
    [105.0, 99.0, 99.5, 97.0, 102.0, 104.5, 99.5],
    [None] + [100.0] * 6, 3.0)
check("6h) كسر جديد@6 يفتح حلقة جديدة (ref_high=104.8, ref_close=99.5)",
      br4[6] == 1 and rh4[6] == 104.8 and rcl4[6] == 99.5 and
      [e["kind"] for e in ev4] == ["break", "reclaim", "break"],
      f"br={br4} rh={rh4}")

# 6i) بلا استرداد بلا نزول: كسر بلا نزول 3% ثم إغلاق فوق القمة → لا إشارة
br5, rh5, _, dk5, rc5, _ = _compute_ema_break_reclaim(
    [106.0, 101.0, 100.5, 101.5, 103.0],
    [104.0, 99.5, 100.0, 101.0, 102.5],
    [105.0, 99.5, 100.0, 101.5, 102.9],
    [None] + [100.0] * 4, 3.0)
check("6i) بلا نزول 3% ⇒ لا إشارة حتى لو أغلق فوق القمة (dk@4=0)",
      dk5 == [0, 0, 0, 0, 0] and rc5 == [0, 0, 0, 0, 0],
      f"dk={dk5} rc={rc5}")

# ── 7) السببية: بادئة ثابتة (لا يتغير الماضي عند تمديد المستقبل)
rng = np.random.RandomState(20260723)
N = 3000
closes = 100 + np.cumsum(rng.randn(N) * 0.4)
highs = closes + rng.rand(N) * 0.8
lows = closes - rng.rand(N) * 0.8
ts = [1500000000000 + i * 900000 for i in range(N)]
df = pd.DataFrame({"time": ts, "open": closes, "high": highs, "low": lows,
                   "close": closes, "volume": [1.0] * N})
P = dict(mode="luxalgo", length=226, trend_periods=[7, 15, 25],
         trend_confirm="majority", trend_gate=["s1", "s2", "s3"],
         zone_gate=["s1", "s2", "s3"], ema_lengths=[50, 100, 200, 350, 500],
         ema_resolution="60", ema_source="close", ema_offset=0,
         ema_gate=["s1", "s2", "s3"])
r_full = zigzag_fib_e2e_trendy_quantum_ema(df, **P)
for cut in (N // 3, 2 * N // 3):
    r_cut = zigzag_fib_e2e_trendy_quantum_ema(df.iloc[:cut].reset_index(drop=True), **P)
    ok = True
    for k in ("zzfetqe_ebreak_break", "zzfetqe_ebreak_ref_high",
              "zzfetqe_ebreak_drop_ok", "zzfetqe_ebreak_reclaim"):
        a, b = r_cut["series"][k], r_full["series"][k][:cut]
        for i, (x, y) in enumerate(zip(a, b)):
            xv = None if x is None else float(x)
            yv = None if y is None else float(y)
            if xv != yv and not (xv is None and yv is None):
                ok = False
                break
        if not ok:
            break
    check(f"7) السببية عند cut={cut}", ok)

# ── 8) الحتمية: تشغيلان متطابقان
r2 = zigzag_fib_e2e_trendy_quantum_ema(df, **P)
ok = all(r_full["series"][k] == r2["series"][k]
         for k in r_full["series"] if k.startswith("zzfetqe_ebreak"))
check("8) الحتمية: تشغيلان متطابقان بت-بت (أعمدة ebreak)", ok)

# ── 9) الجسر والقائمة البيضاء
from app.services.indicators.overlay_columns import config_to_overlay_params
cfg = {"name": "zigzag_fib_e2e_trendy_quantum_ema", "type": "support_resistance",
       "params": {"mode": "luxalgo", "length": 226,
                  "ema_break_length": 100, "ema_break_drop_pct": 3.0,
                  "struct_reversal_pct": 22}}
conv = config_to_overlay_params(cfg)
pp = conv.get("zzfib_e2e_trendy_quantum_ema") or {}
check("9a) config_to_overlay_params يمرر ema_break_length/drop_pct",
      pp.get("ema_break_length") == 100 and pp.get("ema_break_drop_pct") == 3.0,
      f"pp={pp}")
from app.services.indicators.overlays import _normalize_overlay_params
norm = _normalize_overlay_params("zzfib_e2e_trendy_quantum_ema", pp)
check("9b) القائمة البيضاء تحافظ عليهما",
      norm.get("ema_break_length") == 100 and norm.get("ema_break_drop_pct") == 3.0,
      f"norm={norm}")

# ── 10) مسار الباك-تست: columns_for_configs → ind_zzfetqe_ebreak_*
from app.services.indicators.overlay_columns import columns_for_configs
cols = columns_for_configs(df, [cfg])
need = ["ind_zzfetqe_ebreak_break", "ind_zzfetqe_ebreak_ref_high",
        "ind_zzfetqe_ebreak_ref_close", "ind_zzfetqe_ebreak_drop_ok",
        "ind_zzfetqe_ebreak_reclaim"]
have = [c for c in need if c in cols]
check("10) مسار الباك-تست يعرض الأعمدة الخمسة ind_zzfetqe_ebreak_*",
      len(have) == 5, f"have={have}")

# ── 11) الافتراضيات دون تمرير: 100/3.0 + صدى
r_d = zigzag_fib_e2e_trendy_quantum_ema(df, **{k: v for k, v in P.items()})
pe = r_d.get("params") or {}
check("11) الصدى: ema_break_length=100 و ema_break_drop_pct=3.0 بالافتراضي",
      pe.get("ema_break_length") == DLEN and pe.get("ema_break_drop_pct") == DDROP
      and DLEN == 100 and DDROP == 3.0,
      f"echo={pe.get('ema_break_length')}/{pe.get('ema_break_drop_pct')}")

print()
print("RESULT:", "ALL PASS" if not FAILED else f"FAILED: {FAILED}")
sys.exit(1 if FAILED else 0)
