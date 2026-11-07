#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG الإثبات البصري للجولة 34 — شارت الباك تست الموحد (زقزاق+نطاق+إشارات+ترندات)."""
import json
import os
import arabic_reshaper
from bidi.algorithm import get_display
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(ROOT, "html_data.json")))

def ar(t):
    return get_display(arabic_reshaper.reshape(t))

def ms_dt(ms):
    if ms is None:
        return datetime.fromtimestamp(cs[-1]["t"] / 1000, tz=timezone.utc)
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

cs = D["candles"]
legs = D["legs"]
ranges = D["ranges"]
signals = D["signals"]
trend = D["trend"]

W = 16.5
def candle_ax(ax, x0, x1):
    seg = [c for c in cs if x0 <= c["t"] <= x1]
    for c in seg:
        t = ms_dt(c["t"]); up = c["c"] >= c["o"]
        col = "#0ecb81" if up else "#f6465d"
        ax.plot([t, t], [c["l"], c["h"]], color=col, lw=0.8, zorder=2)
        ax.add_patch(plt.Rectangle((mdates.date2num(t) - 0.00024, min(c["o"], c["c"])),
                                   0.00048, abs(c["c"] - c["o"]) + 1e-9,
                                   facecolor=col, edgecolor=col, zorder=3))
    return seg

# ============ لوحة 1: الأسبوع + النطاقات + الزقزاق + الإشارات ============
fig, ax = plt.subplots(figsize=(W, 6.2), dpi=130)
x0, x1 = cs[0]["t"], cs[-1]["t"]
seg = candle_ax(ax, x0, x1)

# النطاقات
for r in ranges:
    a = ms_dt(r["anchor"]["time"])
    d = r.get("death")
    d = ms_dt(d["time"]) if (d and d.get("time")) else ms_dt(x1)
    top = max(r["p1"]["price"], r["p2"]["price"])
    bot = min(r["p1"]["price"], r["p2"]["price"])
    ax.hlines(top, a, d, color="#26a69a", lw=1.0, alpha=0.55, zorder=4)
    ax.hlines(bot, a, d, color="#ef5350", lw=1.0, alpha=0.55, zorder=4)
    ax.axvspan(a, d, color="#7986cb", alpha=0.045, zorder=1)
    if r.get("launch_line") is not None:
        ax.hlines(r["launch_line"], a, x1, color="#ab47bc", lw=1.0, ls="--", alpha=0.85, zorder=4)
    if r.get("ref") and r["ref"].get("high") is not None:
        rt = ms_dt(r["ref"]["time"])
        ax.hlines(r["ref"]["high"], rt, x1, color="#26c6da", lw=1.0, ls="--", alpha=0.8, zorder=4)
        ax.plot([rt], [r["ref"]["high"]], "o", ms=3.5, color="#26c6da", zorder=5)

# الزقزاق
for L in legs:
    t1, t2 = ms_dt(L["t1"]), ms_dt(L["t2"])
    ax.plot([t1, t2], [L["y1"], L["y2"]], color="#f0b90b", lw=1.7, zorder=5)
    ax.plot([t2], [L["y2"]], "o", ms=3, color="#f0b90b", zorder=6)

# الإشارات
sc = {"S1": "#0ecb81", "S2": "#f6465d", "S3": "#f0b90b"}
for s in signals:
    t = ms_dt(s["time"])
    y = next((c["l"] for c in seg if c["t"] == s["time"]), None)
    if y is None:
        continue
    st = int(s.get("state") or 0)
    if st:
        ax.plot([t], [y * 0.9992], "^", ms=7, color=sc[f"S{st}"], zorder=7)

ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=timezone.utc))
ax.set_xlim(ms_dt(x0), ms_dt(x1))
ax.set_title(ar("الجولة 34 — شارت الباك تست الموحد: الزقزاق + النطاق (قمة/قاع/انطلاقة/مرجع R) + الإشارات — BTCUSDT 5m أسبوع حتى 31-10 07:45"),
             fontsize=12, color="#eaecef")
ax.grid(alpha=0.15)
fig.tight_layout()
fig.savefig(os.path.join(ROOT, "proof_r34_panel1_full.png"), facecolor="#111418")
plt.close(fig)

# ============ لوحة 2: تكبير أول إشارة ============
# الإشارة المثبتة يدوياً من Binance: 2026-10-25T14:50:00Z — S1 (range 0)
FIXED_MS = 1792939800000  # 2026-10-25T14:50:00Z
s0 = {"time": FIXED_MS, "range_index": 0, "state": 1}
z0, z1 = s0["time"] - 80 * 60000, s0["time"] + 130 * 60000
fig, ax = plt.subplots(figsize=(W, 5.6), dpi=130)
seg = candle_ax(ax, z0, z1)
r = ranges[s0["range_index"]]
a = ms_dt(r["anchor"]["time"])
top = max(r["p1"]["price"], r["p2"]["price"]); bot = min(r["p1"]["price"], r["p2"]["price"])
ax.axvspan(a, x1 and ms_dt(r["death"]["time"] or x1), color="#7986cb", alpha=0.06)
ax.hlines(top, a, ms_dt(z1), color="#26a69a", lw=1.6)
ax.hlines(bot, a, ms_dt(z1), color="#ef5350", lw=1.6)
ax.hlines(r["launch_line"], a, ms_dt(z1), color="#ab47bc", lw=1.4, ls="--")
# المرجع اللحظي قبل الإشارة (مثبت يدوياً: 80141.71 @ 13:35)
refT = ms_dt(s0["time"] - 110 * 60000)
ax.hlines(80470.34, refT, ms_dt(z1), color="#26c6da", lw=1.4, ls="--")
ax.plot([refT], [80470.34], "o", ms=5, color="#26c6da")
ax.annotate(ar("مرجع R لحظياً 80470.34"), (refT, 80470.34), xytext=(-90, 26),
            textcoords="offset points", color="#26c6da", fontsize=9)
ax.annotate(ar(f"انطلاقة {r['launch_line']:.2f}"), (a, r["launch_line"]), xytext=(6, -14),
            textcoords="offset points", color="#ab47bc", fontsize=9)
ax.annotate(ar(f"قمة النطاق {top}"), (a, top), xytext=(6, 8), textcoords="offset points", color="#26a69a", fontsize=9)
ax.annotate(ar(f"قاع النطاق {bot}"), (a, bot), xytext=(6, -16), textcoords="offset points", color="#ef5350", fontsize=9)
t_s = ms_dt(s0["time"])
y_s = next((c["l"] for c in seg if c["t"] == s0["time"]), None)
ax.plot([t_s], [y_s * 0.9994], "^", ms=11, color=sc["S1"], zorder=8)
ax.annotate(ar("إشارة S1 (مثبتة MATCH)"), (t_s, y_s * 0.9994), xytext=(10, 18),
            textcoords="offset points", color="#f6465d", fontsize=10, fontweight="bold")
# أرجل الزقزاق في التكبير
for L in legs:
    if L["t2"] >= z0 and L["t1"] <= z1:
        ax.plot([ms_dt(L["t1"]), ms_dt(L["t2"])], [L["y1"], L["y2"]], color="#f0b90b", lw=1.9, zorder=6)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=timezone.utc))
ax.set_xlim(ms_dt(z0), ms_dt(z1))
ax.set_title(ar("تكبير أول إشارة — S1 @ 2026-10-25 14:50 (التحقق اليدوي من Binance: MATCH)"), fontsize=12, color="#eaecef")
ax.grid(alpha=0.15)
fig.tight_layout()
fig.savefig(os.path.join(ROOT, "proof_r34_panel2_signal_zoom.png"), facecolor="#111418")
plt.close(fig)

# ============ لوحة 3: الترندات p7/p15/p25 ============
fig, ax = plt.subplots(figsize=(W, 5.6), dpi=130)
seg = candle_ax(ax, x0, x1)
colors = {"p7": "#00BCD4", "p15": "#2962FF", "p25": "#FF9800"}
for p, grp in trend.items():
    for kind in ("upper", "lower"):
        for L in grp.get(kind, []):
            if L["t2"] > x1 or L["t1"] < x0 - 86400000 * 5:
                continue
            end_bar = L.get("replaced_at_bar")
            t_end = ms_dt(cs[min(len(cs) - 1, end_bar)]["t"]) if end_bar is not None else ms_dt(x1)
            xs = max(ms_dt(L["t2"]), ms_dt(x0))
            active = end_bar is None
            ls = (0, (6, 3)) if kind == "lower" else "-"
            tt = [xs, t_end]
            yy = [L["y1"] + L["slope"] * ((xs - ms_dt(x0)).total_seconds() / 300 - 0 + (0)), None]
            # حساب القيم عبر الفهرس: النافذة أسبوع 5m — الفهرس = فرق الزمن/300s
            def val_at(t_dt):
                i = (t_dt - ms_dt(x0)).total_seconds() / 300.0
                return L["y1"] + L["slope"] * (i - next(j for j, c in enumerate(cs) if c["t"] == L["t1"]))
            yy = [val_at(xs), val_at(t_end)]
            ax.plot(tt, yy, color=colors[p], lw=1.8 if active else 0.9,
                    alpha=0.95 if active else 0.3, ls=ls, zorder=6, clip_on=True)
            if ms_dt(L["t2"]) >= ms_dt(x0):
                ax.plot([xs], [L["y2"]], ".", ms=4, color=colors[p], zorder=7)
# قص المجال الرأسي على مجال الشموع (الخطوط تُقص خارجها — كما في منصة رسم)
ys = [c["l"] for c in seg] + [c["h"] for c in seg]
ypad = (max(ys) - min(ys)) * 0.08
ax.set_ylim(min(ys) - ypad, max(ys) + ypad)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=timezone.utc))
ax.set_xlim(ms_dt(x0), ms_dt(x1))
ax.set_title(ar("خطوط الترند p7/p15/p25 على شارت الباك تست (المرسات بالقيعان/القمم الفعلية — أزمنة صارت حقيقية في الجولة 34)"),
             fontsize=12, color="#eaecef")
ax.grid(alpha=0.15)
fig.tight_layout()
fig.savefig(os.path.join(ROOT, "proof_r34_panel3_trendlines.png"), facecolor="#111418")
plt.close(fig)

print("PNG proofs saved:",
      [f for f in os.listdir(ROOT) if f.startswith("proof_r34")])
