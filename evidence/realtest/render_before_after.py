# -*- coding: utf-8 -*-
"""
الرسم الإثباتي قبل/بعد — على نفس شموع لقطة المستخدم (BTCUSDT 1m)
- قبل: إحداثيات الخادم الحي (ج32 — الخط السفلي معكوس: يصل أعلى القيعان)
- بعد: الكود المصحح (ج33 — الخط السفلي يصل القيعان الحقيقية)
- نفس قانون الرسم المُسلَّم للفرونت: من المرساة الأقدم x2 → عبر x1 → امتداد أيمن
"""
import json, sys, datetime
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import arabic_reshaper
from bidi.algorithm import get_display
from matplotlib.patches import Rectangle

def ar(t):
    return get_display(arabic_reshaper.reshape(t))

BASE = "/home/z/my-project/tmp_drive/round32_fix"

# ---------- الشموع (نفس نافذة لقطة النظام) ----------
candles = json.load(open(f"{BASE}/btc_candles.json"))["candles"]
N = len(candles)
t2idx = {c["time"]: i for i, c in enumerate(candles)}
L = [c["low"] for c in candles]

# تحديد نافذة اللقطة: القاع العميق ~80300 في 08:00-08:15 UTC
import datetime as _dt
cand = [i for i, c in enumerate(candles)
        if _dt.datetime.fromtimestamp(c["time"]/1000).day == 5
        and 7 <= _dt.datetime.fromtimestamp(c["time"]/1000).hour <= 8]
deep_i = min(cand, key=lambda i: candles[i]["low"])
W0, W1 = max(0, deep_i - 95), min(N - 1, deep_i + 30)
print(f"نافذة اللقطة: الشمعة {W0}→{W1} "
      f"({datetime.datetime.fromtimestamp(candles[W0]['time']/1000)} → "
      f"{datetime.datetime.fromtimestamp(candles[W1]['time']/1000)} UTC)")
print(f"القاع العميق عند شمعة {deep_i}: low={candles[deep_i]['low']}")

# ---------- قبل: إحداثيات الخادم (ج32) عبر مطابقة زمنية ----------
srv = json.load(open(f"{BASE}/btc_tf.json"))["overlays"]["trend_fractal"]
# بعد: الكود المصحح (ج33) على نفس الشموع
sys.path.insert(0, "/home/z/my-project/user-project/app/services/indicators")
import trend_fractals as tf_new
fixed = tf_new.auto_trendlines_fractal(candles, periods=[7, 15, 25], confirm_mode="majority")

COLORS = {"p7": "#00BCD4", "p15": "#2962FF", "p25": "#FF9800"}

def render(ax, data, title):
    """يرسم الشموع + الخطوط وفق قانون العقد — data: dict بخطوط لكل فترة."""
    for i in range(W0, W1 + 1):
        c = candles[i]
        up = c["close"] >= c["open"]
        col = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [c["low"], c["high"]], color=col, linewidth=0.8, zorder=2)
        lo, hi = min(c["open"], c["close"]), max(c["open"], c["close"])
        ax.add_patch(Rectangle((i - 0.31, lo), 0.62, max(hi - lo, 1e-9),
                               facecolor=col, edgecolor=col, linewidth=0.4, zorder=3))
    for period in ["p7", "p15", "p25"]:
        col = COLORS[period]
        for kind in ["upper", "lower"]:
            for ln in data[period][kind]:
                t1, x1s, y1, m = ln["t1"], ln["x1"], ln["y1"], ln["slope"]
                if t1 not in t2idx:
                    continue
                x1 = t2idx[t1]                       # موضع المرساة الأحدث في نافذتنا
                if ln.get("t2") in t2idx:
                    x_start = t2idx[ln["t2"]]        # المرساة الأقدم — بداية الرسم
                else:
                    x_start = x1
                if ln.get("replaced_at_time") in t2idx:
                    x_end = t2idx[ln["replaced_at_time"]]
                elif ln.get("replaced_at_bar") is not None:
                    off = x1 - x1s
                    x_end = ln["replaced_at_bar"] + off
                else:
                    x_end = W1 + 6                   # امتداد أيمن لما بعد آخر شمعة
                x_end = max(x_end, x_start + 1)
                # y(i) = y1 + slope × (i − x1) — قانون العقد حرفياً
                xs = [x_start, x_end]
                ys = [y1 + m * (x_start - x1s), y1 + m * (x_end - x1s)]
                act = ln.get("active")
                lw = 2.0 if act else 0.8
                alpha = 0.95 if act else 0.4
                ls = "-" if kind == "upper" else (0, (6, 3))
                ax.plot(xs, ys, color=col, linewidth=lw, alpha=alpha,
                        linestyle=ls, zorder=6 if act else 4)
    vis = candles[W0:W1 + 1]
    ymin = min(c["low"] for c in vis); ymax = max(c["high"] for c in vis)
    pad = (ymax - ymin) * 0.28
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_xlim(W0 - 1, W1 + 8)
    step = max(1, (W1 - W0) // 8)
    ticks = list(range(W0, W1 + 1, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([datetime.datetime.fromtimestamp(candles[i]["time"]/1000).strftime("%H:%M")
                        for i in ticks], fontsize=8)
    ax.set_title(ar(title), fontsize=11)
    ax.grid(alpha=0.18, linewidth=0.5)

def server_lines():
    """خادم ج32: أعد تنظيم السطور حسب الفترة مع حقن replaced_at_time."""
    out = {}
    for p in ["p7", "p15", "p25"]:
        out[p] = {}
        for kind in ["upper", "lower"]:
            out[p][kind] = []
            for ln in srv["lines"][p][kind]:
                d = dict(ln)
                if d.get("replaced_at_bar") is not None:
                    off = d["x1"] - (d["x1"])
                    # لحظة الاستبدال بالزمن: replaced_at_bar بعيد عن formed_at_bar بعدد شموع؛
                    # نستنتج الزمن: نستخدم formed_at_time للخط التالي إن توفر — أبسط: نحسب من t1
                    d.setdefault("replaced_at_time", None)
                out[p][kind].append(d)
    # حقن replaced_at_time: الخط replaced_at_bar=i يعني استُبدل عند ولادة الخط التالي
    for p in ["p7", "p15", "p25"]:
        for kind in ["upper", "lower"]:
            arr = out[p][kind]
            for j in range(len(arr) - 1):
                if arr[j].get("replaced_at_bar") is not None:
                    arr[j]["replaced_at_time"] = arr[j + 1].get("formed_at_time")
    return out

def fixed_lines():
    out = {}
    for p in ["p7", "p15", "p25"]:
        out[p] = {}
        for kind in ["upper", "lower"]:
            arr = fixed["lines"][p][kind]
            for j in range(len(arr) - 1):
                if arr[j].get("replaced_at_bar") is not None:
                    arr[j]["replaced_at_time"] = arr[j + 1].get("formed_at_time")
            out[p][kind] = arr
    return out

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(17, 12.5), dpi=110)
render(ax1, server_lines(),
       "قبل — الخادم الحي ج32: «الخط السفلي» معكوس (يوصل أعلى القيعان) — نفس ما يظهر في لقطة نظامك\n"
       "لاحظ الخطوط المنقّطة تعبر وسط الشموع ولا تحتضن القيعان")
render(ax2, fixed_lines(),
       "بعد — ج33 المصحح: الخط السفلي يصل آخر فراكتالَي قاع حقيقيين ويحتضن القيعان من الأسفل\n"
       "نفس منطق القمم تماماً (ta.pivotlow بدل أعلى القيعان) — العلوي لم يتغير")
fig.suptitle(ar("BTCUSDT · 1m — إصلاح الخطوط السفلية للترندات p7/p15/p25 — نفس الشموع، نفس قانون الرسم"), fontsize=13, y=0.995)
fig.tight_layout(rect=[0, 0, 1, 0.96])
out = f"{BASE}/before_after_lower_lines.png"
fig.savefig(out, facecolor="white")
print("SAVED:", out)

# كذلك نسخة للحزمة
import shutil
shutil.copy(out, "/home/z/my-project/download/ROUND33-LOWER-PIVOT-FIX/evidence/realtest/before_after_lower_lines.png")
print("copied to package")
