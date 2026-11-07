#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROUND19 — تشخيص مرضي: لماذا يولّد زقزاقنا أطرافاً صغيرة لا تشبه TradingView؟
=====================================================================
يقيس على بيانات LAZIOUSDT · 1m (نفس فريم صورة المستخدم):
  [1] زقزاقنا الحالي (LuxAlgo length=100): عدد الأطراف + انعكاس كل ساق % —
      وعدّ الأطراف "الصغيرة" (انعكاس < 0.5%).
  [2] الطول القصير luxalgo (لإظهار حساسية الطول فقط).
  [3] مرجع MT4/TV نظيف (تنفيذ تجريبي مستقل داخل السكربت — depth=12, deviation, backstep=3)
      لقياس شكل الأطراف المفروض أن نطابقها.
السكربت تشخيص فقط — لا يعدل كود الإنتاج.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

PRO27 = "/home/z/my-project/backend-audit/pro27"
sys.path.insert(0, PRO27)
os.chdir(PRO27)
os.environ.setdefault(
    "SECRET_KEY",
    "r6fwc7Q8CGqI3RpKFaTDbJJ55EOR6LrADCPZv4_KK5LbI0fpzDn84KhemcV_TE0C",
)

import pandas as pd  # noqa: E402

from app.services.live_strategy_service import _fetch_window, _is_forming  # noqa: E402
from app.services.indicators.overlays import zigzag_fib  # noqa: E402


def iso_ms(ms):
    if isinstance(ms, (int, float)) and not isinstance(ms, bool):
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%m-%d %H:%M")
    return pd.Timestamp(ms).strftime("%m-%d %H:%M")


def legs_report(zzf, df, label, lo_bar=None):
    legs = zzf.get("legs", [])
    if lo_bar is not None:
        legs = [lg for lg in legs if int(lg.get("x2") or 0) >= lo_bar]
    pivots = []
    for lg in legs:
        pivots.append((int(lg["x1"]), float(lg["y1"]), "top" if lg["kind"] == "bottom" else "bottom"))
    if legs:
        pivots.append((int(legs[-1]["x2"]), float(legs[-1]["y2"]), str(legs[-1]["kind"])))
    # انعكاس كل ساق %
    moves = []
    for k in range(1, len(pivots)):
        b0, p0, k0 = pivots[k - 1]
        b1, p1, k1 = pivots[k]
        if p0 in (None, 0):
            continue
        moves.append(((p1 - p0) / p0 * 100.0, b0, p0, b1, p1, k1))
    n_small = sum(1 for m in moves if abs(m[0]) < 0.5)
    print(f"\n--- {label} ---")
    print(f"pivots={len(pivots)} legs={len(moves)} small(<0.5%)={n_small}")
    for m in moves[-14:]:
        sign = "+" if m[0] >= 0 else ""
        print(f"  leg {iso_ms(df.index[int(m[3])])} {str(m[5]):6s} @{m[4]:<10.6g} Δ={sign}{m[0]:.2f}%  "
              f"(from {m[2]:.6g} @ {iso_ms(df.index[int(m[1])])})")
    return pivots, moves


def zigzag_tv_proto(h, l, depth=12, dev_pct=5.0, backstep=3):
    """نموذج مرجعي داخل السكربت (MT4/TV كلاسيكي) للقياس قبل دمجه في المحرك."""
    N = len(h)
    dev = dev_pct / 1000.0  # وحدات TV: أعشار المئة (5 ⇒ 0.5%)
    tops, btms = [], []
    for i in range(depth - 1, N):
        seg = [x for x in h[i - depth + 1: i + 1] if x is not None]
        if h[i] is not None and seg and h[i] >= max(seg):
            tops.append((i, h[i]))
        segl = [x for x in l[i - depth + 1: i + 1] if x is not None]
        if l[i] is not None and segl and l[i] <= min(segl):
            btms.append((i, l[i]))

    def clean(cands, better):
        out = []
        for bar, px in cands:
            if out and bar - out[-1][0] < backstep:
                if better(px, out[-1][1]):
                    out[-1] = (bar, px)
            else:
                out.append((bar, px))
        return out

    tops = clean(tops, lambda a, b: a >= b)
    btms = clean(btms, lambda a, b: a <= b)
    ev = sorted([("top", b, p) for b, p in tops] + [("bottom", b, p) for b, p in btms],
                key=lambda x: (x[1], 0 if x[0] == "top" else 1))
    piv = []
    for kind, bar, px in ev:
        if not piv:
            piv.append([bar, px, kind])
            continue
        lb, lp, lk = piv[-1]
        if kind == lk:
            if (kind == "top" and px >= lp) or (kind == "bottom" and px <= lp):
                piv[-1] = [bar, px, kind]
        else:
            if kind == "bottom" and lp - px >= lp * dev:
                piv.append([bar, px, kind])
            elif kind == "top" and px - lp >= lp * dev:
                piv.append([bar, px, kind])
    return piv


def report_tv(piv, df, label):
    moves = []
    for k in range(1, len(piv)):
        b0, p0, k0 = piv[k - 1]
        b1, p1, k1 = piv[k]
        if not p0:
            continue
        moves.append(((p1 - p0) / p0 * 100.0, b0, p0, b1, p1, k1))
    n_small = sum(1 for m in moves if abs(m[0]) < 0.5)
    print(f"\n--- {label} ---")
    print(f"pivots={len(piv)} legs={len(moves)} small(<0.5%)={n_small}")
    for m in moves[-14:]:
        sign = "+" if m[0] >= 0 else ""
        print(f"  leg {iso_ms(df.index[int(m[3])])} {str(m[5]):6s} @{m[4]:<10.6g} Δ={sign}{m[0]:.2f}%  "
              f"(from {m[2]:.6g} @ {iso_ms(df.index[int(m[1])])})")


async def main():
    symbol, timeframe = "LAZIOUSDT", "1m"
    print(f"DIAGNOSIS — {symbol} · {timeframe} (نفس فريم صورة المستخدم)")
    df_raw, now = await _fetch_window(symbol, "crypto", timeframe)
    df = df_raw.copy().sort_index()
    if len(df) and _is_forming(df.index[-1].to_pydatetime(), timeframe, now):
        df = df.iloc[:-1]
    print(f"window: {len(df)} closed · {iso_ms(ms0 := int(pd.Timestamp(df.index[0]).timestamp()*1000))} → "
          f"{iso_ms(int(pd.Timestamp(df.index[-1]).timestamp()*1000))} UTC")

    # نافذة العرض في صورة المستخدم ≈ آخر 18 ساعة (1050 شمعة 1m)
    view = df.iloc[-1050:]
    lo_bar = len(df) - len(view)

    for length, label in [(100, "OUR ENGINE — LuxAlgo length=100 (الحالي)"),
                          (20, "LuxAlgo length=20 (للمقارنة فقط)")]:
        zzf = zigzag_fib(df, length=length)
        legs_report(zzf, df, label, lo_bar=lo_bar)

    h = [None if pd.isna(x) else float(x) for x in df["high"]]
    l = [None if pd.isna(x) else float(x) for x in df["low"]]
    for dev in (5.0, 10.0, 20.0, 30.0):
        piv = zigzag_tv_proto(h, l, depth=12, dev_pct=dev, backstep=3)
        piv_view = [p for p in piv if p[0] >= lo_bar]
        report_tv(piv_view, df, f"MT4/TV PROTO — depth=12 · deviation={dev:g} ({dev/10:g}%) · backstep=3")


if __name__ == "__main__":
    asyncio.run(main())
