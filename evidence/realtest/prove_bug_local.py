# -*- coding: utf-8 -*-
"""
(أ) تحقق: المحرك المحلي (قبل الإصلاح) على شموع الخادم = مخرجات الخادم الحي
(ب) تحقق: المرجع المستقل (ta.pivotlow الصحيح) ≠ مخرجات الخادم للخطوط السفلية
(ج) تحقق: المرجع المستقل = مخرجات الخادم للخطوط العلوية
"""
import json, sys

BASE = "/home/z/my-project/tmp_drive/round32_fix"
sys.path.insert(0, "/home/z/my-project/user-project/app/services/indicators")
import trend_fractals as tf  # قبل الإصلاح

# ---------- المدخلات ----------
candles = json.load(open(f"{BASE}/btc_candles.json"))["candles"]
print("candles:", len(candles))
srv = json.load(open(f"{BASE}/btc_tf.json"))["overlays"]["trend_fractal"]

# ---------- (أ) المحرك المحلي قبل الإصلاح ----------
out = tf.auto_trendlines_fractal(candles, periods=[7, 15, 25], confirm_mode="majority")

def compare_lines(a_list, b_list, name):
    """مطابقة قائمة خطوط (تُقارن حتى نهاية أقصر تاريخ مشترك عبر t1)."""
    if not b_list:
        return not a_list, 0, 0
    # الحد الزمني: آخر خط في القائمة الأقدم زمنياً (الخادم سبق المحلي ببضعة شموع)
    cut = max(x["formed_at_time"] for x in b_list)
    a_cut = [x for x in a_list if x["formed_at_time"] <= cut]
    b_cut = [x for x in b_list if x["formed_at_time"] <= cut]
    if len(a_cut) != len(b_cut):
        return False, len(a_cut), len(b_cut)
    for a, b in zip(a_cut, b_cut):
        for k in ("kind", "x1", "t1", "y1", "x2", "t2", "y2", "slope",
                  "formed_at_bar", "formed_at_time", "active", "replaced_at_bar"):
            av, bv = a.get(k), b.get(k)
            if isinstance(av, float) and isinstance(bv, float):
                if abs(av - bv) > 1e-9:
                    return False, len(a_cut), len(b_cut)
            elif av != bv:
                return False, len(a_cut), len(b_cut)
    return True, len(a_cut), len(b_cut)

print("\n=== (أ) محلي (قبل الإصلاح) مقابل الخادم الحي ===")
all_match = True
for p in [7, 15, 25]:
    tag = f"p{p}"
    for kind in ("upper", "lower"):
        ok, na, nb = compare_lines(out["lines"][tag][kind], srv["lines"][tag][kind], f"{tag}.{kind}")
        all_match = all_match and ok
        print(f"{tag}.{kind:5s}: محلي={na:3d} خادم={nb:3d} → {'مطابق ✓' if ok else 'مختلف ✗'}")
print("الأحكام:", "المحرك المحلي يعيد إنتاج الخادم حرفياً ✓" if all_match else "✗ عدم تطابق — تدخل زمني؟")

# ---------- (ب/ج) المرجع المستقل ----------
N = len(candles)
H = [c["high"] for c in candles]
L = [c["low"] for c in candles]

def ref_pivot_events(vals, n, mode):
    Nn = len(vals)
    out = []
    for p in range(n, Nn - n):
        v = vals[p]
        lw = vals[p - n:p]
        rw = vals[p + 1:p + 1 + n]
        if v is None or any(x is None for x in lw + rw):
            continue
        if mode == "high" and v > max(lw) and v > max(rw):
            out.append((p + n + 1, p, v))
        elif mode == "low" and v < min(lw) and v < min(rw):
            out.append((p + n + 1, p, v))
    out.sort(key=lambda x: (x[0], x[1]))
    return out

def ref_fill(events, Nn):
    lines, prev, last, ei = [], None, None, 0
    for i in range(Nn):
        while ei < len(events) and events[ei][0] <= i:
            _cf, pb, px = events[ei]; ei += 1
            if last is None:
                last, prev = (pb, px), None
                continue
            prev, last = last, (pb, px)
            x2, y2 = prev; x1, y1 = last
            m = 0.0 if x1 == x2 else (y1 - y2) / float(x1 - x2)
            if lines:
                lines[-1]["active"] = False
                lines[-1]["replaced_at_bar"] = int(i)
            lines.append(dict(kind=None, x1=int(x1), t1=None, y1=float(y1), x2=int(x2),
                              t2=None, y2=float(y2), slope=float(m), formed_at_bar=int(i),
                              formed_at_time=None, active=True, replaced_at_bar=None))
        if last is not None and prev is not None:
            pass
    return lines

def local_key(ln):
    return (ln["x1"], round(ln["y1"], 9), ln["x2"], round(ln["y2"], 9),
            round(ln["slope"], 9), ln["formed_at_bar"])

print("\n=== (ب/ج) المرجع المستقل مقابل المحرك المحلي (قبل الإصلاح) ===")
for p in [7, 15, 25]:
    tag = f"p{p}"
    for kind, arr, mode in [("upper", H, "high"), ("lower", L, "low")]:
        ev = ref_pivot_events(arr, p, mode)
        ref = ref_fill(ev, N)
        eng = out["lines"][tag][kind]
        rk = [local_key(x) for x in ref]
        ek = [local_key(x) for x in eng]
        same = rk == ek
        print(f"{tag}.{kind:5s}: محرك={len(ek):3d} مرجع={len(rk):3d} → "
              f"{'مطابق ✓' if same else 'مختلف ✗'}")
        if not same:
            for a, b in zip(ek, rk):
                if a != b:
                    print(f"    أول اختلاف — محرك={a}\n              مرجع={b}")
                    break
