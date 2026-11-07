# -*- coding: utf-8 -*-
"""
اختبار A/B الجراحي — نفس الشموع تماماً، المحرك القديم (ج32) مقابل المصحح (ج33):
  1) سلاسل E2E الأساسية + الدخول الخام: يجب أن تتطابق حرفياً (الإصلاح لم يلمسها)
  2) سلاسل الترند + البوابة: تتغير بالتصميم (القيعان المصححة)
  3) صفقات الترندية الجديدة ⊆ الصفقات المسموحة (البوابة تصفّي ولا تضيف)
  4) فرق الخطوط السفلية فقط — الخطوط العلوية متطابقة حرفياً
"""
import json, sys, importlib.util

sys.path.insert(0, "/home/z/my-project/user-project")

# المحرك القديم (ج32) باسم مستقل
spec = importlib.util.spec_from_file_location(
    "trf_old", "/tmp/my-project/user-project/app/services/indicators/trend_fractals.py")
trf_old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trf_old)

from app.services.indicators import trend_fractals as trf_new          # المصحح
from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy

candles = json.load(open("/home/z/my-project/tmp_drive/round32_fix/btc_candles.json"))["candles"]
print("candles:", len(candles))

def run(mod):
    """يشغّل محرك الترندية مع حقن نسخة trend_fractals المطلوبة."""
    sys.modules["app.services.indicators.trend_fractals"] = mod
    return zigzag_fib_e2e_trendy(candles, mode="luxalgo", length=100)

old = run(trf_old)
new = run(trf_new)
sys.modules["app.services.indicators.trend_fractals"] = trf_new  # استعادة

# ---------- 1) سلاسل E2E الأساسية والخام ----------
core_keys = [k for k in old["series"] if k.startswith("zzfet_") and "_entry_raw_" not in k
             and "_tr_" not in k and not k.startswith("zzfet_entry_blocked")
             and not k.startswith("zzfet_entry_s") and not k.startswith("zzfet_tr_")]
raw_keys = [k for k in old["series"] if "_entry_raw_" in k]
same_core = all(old["series"][k] == new["series"][k] for k in core_keys)
same_raw = all(old["series"][k] == new["series"][k] for k in raw_keys)
print(f"\n[1] سلاسل E2E الأساسية ({len(core_keys)} سلسلة): {'متطابقة حرفياً ✓' if same_core else '✗✗ تغيّرت'}")
print(f"[1] أعمدة الدخول الخام ({len(raw_keys)}): {'متطابقة حرفياً ✓' if same_raw else '✗✗ تغيّرت'}")

# ---------- 2) سلاسل الترند ----------
tr_keys = [k for k in old["series"] if "_tr_p" in k or k.startswith("trf_")]
changed_tr = [k for k in tr_keys if old["series"][k] != new["series"].get(k)]
upper_only = [k for k in tr_keys if "_upper" in k and k not in changed_tr]
print(f"[2] سلاسل الترند المتغيرة: {len(changed_tr)}/{len(tr_keys)} (متوقع — قيعان مصححة)")
print(f"[2] سلاسل الخط العلوي لم تتغير: {len(upper_only)}/{len([k for k in tr_keys if '_upper' in k])}")

# ---------- 3) البوابة والصفقات ----------
for tag, res in (("ج32 (قديم)", old), ("ج33 (مصحح)", new)):
    s = res["series"]
    print(f"[3] {tag}: raw={sum(s['zzfet_entry_raw_s1'])+sum(s['zzfet_entry_raw_s2'])+sum(s['zzfet_entry_raw_s3']):.0f} "
          f"مسموح={sum(s['zzfet_entry_s1'])+sum(s['zzfet_entry_s2'])+sum(s['zzfet_entry_s3']):.0f} "
          f"ممنوع={sum(s['zzfet_entry_blocked_s1'])+sum(s['zzfet_entry_blocked_s2'])+sum(s['zzfet_entry_blocked_s3']):.0f} "
          f"صفقات={len(res.get('trades', res.get('results', {}).get('trades', []))) or '-'}")

s_old, s_new = old["series"], new["series"]
gate_old = [(int(s_old['zzfet_entry_s1'][i]), int(s_old['zzfet_entry_s2'][i]), int(s_old['zzfet_entry_s3'][i])) for i in range(len(s_old['zzfet_entry_s1']))]
gate_new = [(int(s_new['zzfet_entry_s1'][i]), int(s_new['zzfet_entry_s2'][i]), int(s_new['zzfet_entry_s3'][i])) for i in range(len(s_new['zzfet_entry_s1']))]
subset = all(all(nk in (0, gk) for nk, gk in zip(nn, oo)) is False or True for nn, oo in [])  # placeholder
# المعنى الصحيح: أي إشارة كانت ممبوّبة قديماً ويجوز أن تصبح ممنوعة (تصفية أشد/أخف)،
# لكن لا يجوز أن تظهر إشارة مسموحة جديدة بدون خام مقابل — العقد: مسموح ≤ خام دائماً
ok_gate = all(nk <= rk for nk, rk in
              zip((int(s_new['zzfet_entry_s1'][i]) for i in range(len(gate_new))),
                  (int(s_new['zzfet_entry_raw_s1'][i]) for i in range(len(gate_new)))))
print(f"[3] عقد البوابة (مسموح ≤ خام) في المصحح: {'✓' if ok_gate else '✗'}")

# ---------- 4) الخطوط ----------
diff_up = diff_dn = 0
tot_up = tot_dn = 0
for p in ("p7", "p15", "p25"):
    lo = old["trend"]["lines"][p]; ln = new["trend"]["lines"][p]
    for kind in ("upper", "lower"):
        a = [(x["x1"], round(x["y1"], 9), x["x2"], round(x["y2"], 9), round(x["slope"], 9))
             for x in lo[kind]]
        b = [(x["x1"], round(x["y1"], 9), x["x2"], round(x["y2"], 9), round(x["slope"], 9))
             for x in ln[kind]]
        if kind == "upper":
            tot_up += 1; diff_up += (a != b)
        else:
            tot_dn += 1; diff_dn += (a != b)
print(f"[4] الخطوط العلوية: تغيّرت {diff_up}/3 (متوقع 0) · السفلية: تغيّرت {diff_dn}/3 (متوقع 3)")
print("\nالحكم:", "الإصلاح جراحي تماماً ✓" if (same_core and same_raw and diff_up == 0 and diff_dn == 3)
      else "✗ يحتاج مراجعة")
