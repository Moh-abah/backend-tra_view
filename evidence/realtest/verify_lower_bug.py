# -*- coding: utf-8 -*-
"""
تأكيد تجريبي مستقل لخلل الخطوط السفلية (الجولة 32 — محرك الترند)
- مرجع مستقل O(n²) بسيط: pivot high/low بمنطق ta.pivothigh/pivotlow(n,n)[1]
- مقارنة: خطوط الخادم (المديلة) مقابل المرجع — علوي وسفلي لكل فترة
"""
import json, urllib.request

BASE = "/home/z/my-project/tmp_drive/round32_fix"

# ---------- 1) شموع Binance لنفس النافذة ----------
req = urllib.request.Request(
    "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=1500",
    headers={"User-Agent": "Mozilla/5.0"})
klines = json.loads(urllib.request.urlopen(req, timeout=20).read())
candles = [dict(t=int(k[0]), h=float(k[2]), l=float(k[3])) for k in klines]
NC = len(candles)
t2idx = {c["t"]: i for i, c in enumerate(candles)}
print(f"candles: {NC} (آخرها {candles[-1]['t']})")

# ---------- 2) بيانات الخادم ----------
srv = json.load(open(f"{BASE}/btc_tf.json"))["overlays"]["trend_fractal"]

# إزاحة فهارس الخادم → بنانس عبر t1 لخط معروف
probe = srv["lines"]["p7"]["upper"][-1]
OFF = t2idx[probe["t1"]] - probe["x1"]
print(f"offset خادم→بنانس = {OFF}")

# ---------- 3) المرجع المستقل (بلا deque — قوة غبية صريحة) ----------
H = [c["h"] for c in candles]
L = [c["l"] for c in candles]

def ref_pivot_events(vals, n, mode):
    """pivot bar p يُعرف عند p+n+1 (وفاء [1]). strict على الجانبين."""
    N = len(vals)
    out = []
    for p in range(n, N - n):
        v = vals[p]
        lw = vals[p - n:p]
        rw = vals[p + 1:p + 1 + n]
        if any(x is None for x in lw + rw) or v is None:
            continue
        if mode == "high" and v > max(lw) and v > max(rw):
            out.append((p + n + 1, p, v))
        elif mode == "low" and v < min(lw) and v < min(rw):
            out.append((p + n + 1, p, v))
    out.sort(key=lambda x: (x[0], x[1]))
    return out

def ref_fill_lines(events, N):
    """وصل آخر فراكتالَين + امتداد أيمن — نفس منطق العقد."""
    lines = []
    prev = last = None
    ei = 0
    for i in range(N):
        while ei < len(events) and events[ei][0] <= i:
            _cf, pb, px = events[ei]
            ei += 1
            if last is None:
                last, prev = (pb, px), None
                continue
            prev, last = last, (pb, px)
            x2, y2 = prev
            x1, y1 = last
            m = 0.0 if x1 == x2 else (y1 - y2) / float(x1 - x2)
            if lines:
                lines[-1]["active"] = False
                lines[-1]["replaced_at_bar"] = int(i)
            lines.append(dict(x1=x1, y1=y1, x2=x2, y2=y2, slope=m,
                              formed_at_bar=i, active=True, replaced_at_bar=None))
        if last is not None and prev is not None:
            pass
    return lines

# ---------- 4) المقارنة لكل فترة ----------
def line_key(ln, off):
    return (ln["x1"] + off, round(ln["y1"], 6), ln["x2"] + off, round(ln["y2"], 6),
            round(ln["slope"], 9), ln["formed_at_bar"] + off)

print("\n=== المقارنة: خطوط الخادم مقابل المرجع المستقل ===")
all_ok_up, all_ok_dn = True, True
for p in [7, 15, 25]:
    tag = f"p{p}"
    for kind, mode, okflag in [("upper", "high", "up"), ("lower", "low", "dn")]:
        ev = ref_pivot_events(H if kind == "upper" else L, p, mode)
        ref = ref_fill_lines(ev, NC)
        ref_keys = [line_key(x, 0) for x in ref]
        srv_lines = srv["lines"][tag][kind]
        srv_keys = [line_key(x, OFF) for x in srv_lines]
        same = ref_keys == srv_keys
        if kind == "upper":
            all_ok_up = all_ok_up and same
        else:
            all_ok_dn = all_ok_dn and same
        print(f"{tag}.{kind:5s}: خادم={len(srv_keys):3d} مرجع={len(ref_keys):3d} "
              f"→ {'متطابقان ✓' if same else 'مختلفان ✗'}")
        if not same and kind == "lower" and p == 7:
            # عينة أول اختلاف
            for a, b in zip(srv_keys, ref_keys):
                if a != b:
                    print(f"   أول اختلاف: خادم={a}\n               مرجع={b}")
                    break

print("\n=== الحكم ===")
print("العلوي مطابق للمرجع:", "نعم ✓" if all_ok_up else "لا ✗")
print("السفلي مطابق للمرجع:", "نعم ✓" if all_ok_dn else "لا ✗")

# ---------- 5) فحص مكان الخط السفلي الحي: هل يحتضن القيعان؟ ----------
print("\n=== فحص موضع الخط السفلي الحي (آخر 60 شمعة) ===")
for p in [7, 15, 25]:
    cur = srv["current"][f"p{p}"]["lower"]
    if not cur or not cur.get("active"):
        continue
    x1, y1, m = cur["x1"] + OFF, cur["y1"], cur["slope"]
    bad, tot = 0, 0
    for i in range(max(0, NC - 60), NC):
        yv = y1 + m * (i - x1)
        tot += 1
        if candles[i]["l"] < yv:   # قاع شمعة تحت «الخط السفلي» → الخط ليس سفلياً
            bad += 1
    print(f"p{p}: خط سفلي حي — القيعان تحته في {bad}/{tot} من آخر 60 شمعة "
          f"{'✗✗ الخط ليس سفلياً فعلاً' if bad > tot // 2 else 'مقبول'}")
    if p == 7:
        print(f"   مرساته: ({x1},{y1}) ← قاع الشمعة هناك = {L[x1]} "
              f"(فرق {round(y1 - L[x1], 2)})")
