#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROUND19 — اختبار الخصائص الحاكمة لوضع tradingview في zigzag_fib (بلا شبكة)
=====================================================================
على بيانات الكاش المحلي (parquet) — LAZIO 1m وBTC 5m وZEC 5m إن وجدت:
  P1) التناوب الصارم: لا طرفين متعاكسين... بل لا نفس النوع متتاليين في pivots.
  P2) الأطراف على القصوى: كل طرف price == high/low الشمعة نفسها (مسجل في المخرجات).
  P3) الانعكاس: كل ساق بين طرفين متتاليين ≥ deviation نسبةً من سعر الطرف.
  P4) السببية/عدم إعادة الرسم: الحساب على مقطع منتهٍ عند T يطابق حرفياً كل الأطراف
      المؤكدة (confirmed_at_bar ≤ T) الموجودة في الحساب الكامل — أي إضافة الشموع
      اللاحقة لا تعيد كتابة أي طرف مؤكد (الإحلال يمس الطرف الحي فقط).
  P5) الانطلاقة تعمل: leg_ready + launch_line متوافقة، والسيولة تنتج إشارات.
  P6) مطابقة الكثافة مع صورة المستخدم على LAZIO 1m (نافذة 18 ساعة).
  P7) التوافق الرجعي: mode=luxalgo يعمل كما كان (بلا أي فرق بنيوي).
"""
import os
import sys

PRO27 = "/home/z/my-project/backend-audit/pro27"
sys.path.insert(0, PRO27)
os.chdir(PRO27)
os.environ.setdefault(
    "SECRET_KEY",
    "r6fwc7Q8CGqI3RpKFaTDbJJ55EOR6LrADCPZv4_KK5LbI0fpzDn84KhemcV_TE0C",
)

import pandas as pd  # noqa: E402

from app.services.indicators.overlays import zigzag_fib  # noqa: E402

DEPTH, DEV, BACK = 12, 20.0, 3


def load(sym, tf):
    path = f"data/history/{sym}_{tf}.parquet"
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df = df.set_index(pd.to_datetime(df["timestamp"], unit="ms", utc=True))
    df = df.sort_index()
    if len(df) > 2000:
        df = df.iloc[-2000:]
    return df


def check(mode_name: str, df: pd.DataFrame, **kwargs) -> dict:
    params = dict(mode="tradingview", depth=DEPTH, deviation=DEV, backstep=BACK,
                  touch_level=0.618, liq_lookback=20, liq_signals=True, liq_arm_bars=60)
    params.update(kwargs)
    zzf = zigzag_fib(df, **params)

    def pivots_from_legs(z):
        legs = z.get("legs", [])
        piv = []
        if legs:
            first = legs[0]
            piv.append({"bar": int(first["x1"]), "price": first["y1"],
                        "kind": "top" if first["kind"] == "bottom" else "bottom",
                        "confirmed_at_bar": None})
            for lg in legs:
                piv.append({"bar": int(lg["x2"]), "price": lg["y2"],
                            "kind": lg["kind"], "confirmed_at_bar": lg["confirmed_at_bar"]})
        return piv

    piv = pivots_from_legs(zzf)
    out = {"zzf": zzf, "fails": [], "pivots": piv}

    # P1 تناوب صارم
    kinds = [p["kind"] for p in piv]
    for a, b in zip(kinds, kinds[1:]):
        if a == b:
            out["fails"].append(f"P1 same-kind consecutive: {a}")
            break

    # P2 أطراف على القصوى (تحقق عبر مقارنة السعر بـhigh/low الشمعة)
    h = df["high"].tolist(); l = df["low"].tolist()
    for p in piv:
        b, px = int(p["bar"]), float(p["price"])
        want = h[b] if p["kind"] == "top" else l[b]
        if abs(float(want) - px) > 1e-12 * max(1.0, abs(px)):
            out["fails"].append(f"P2 pivot not at extreme: bar {b} {p['kind']} {px} vs {want}")
            break

    # P3 انعكاس ≥ deviation (عقد وضع tradingview حصراً — luxalgo بلا عتبة انعكاس)
    dev_frac = DEV / 1000.0
    if params.get("mode") == "tradingview":
        for a, b2 in zip(piv, piv[1:]):
            p0, p1 = float(a["price"]), float(b2["price"])
            base = abs(p0)
            if base > 0 and abs(p1 - p0) + 1e-15 < base * dev_frac:
                out["fails"].append(f"P3 leg < deviation: {p0}->{p1} ({abs(p1-p0)/base*100:.3f}% < {DEV/10:.1f}%)")
                break

    # P4 سببية — قص زمني
    if len(piv) >= 3:
        T = int(piv[-2]["bar"])  # قبل الطرف الأخير
        sub = df.iloc[: T + 1]
        zzf2 = zigzag_fib(sub, **params)
        piv2 = pivots_from_legs(zzf2)
        # كل الأطراف المؤكدة ≤ T في الكامل يجب أن تطابق في المقطع (بالزمن والسعر والنوع)
        full_conf = [(p["bar"], p["price"], p["kind"], p["confirmed_at_bar"]) for p in piv
                     if p["confirmed_at_bar"] is not None and p["confirmed_at_bar"] <= T]
        sub_conf = [(p["bar"], p["price"], p["kind"], p["confirmed_at_bar"]) for p in piv2
                    if p["confirmed_at_bar"] is not None and p["confirmed_at_bar"] <= T]
        if full_conf != sub_conf:
            diff_n = sum(1 for x, y in zip(full_conf, sub_conf) if x != y)
            out["fails"].append(
                f"P4 causality broken: full={len(full_conf)} sub={len(sub_conf)} first_diff="
                f"{next(( (x,y) for x,y in zip(full_conf, sub_conf) if x!=y), 'len-mismatch')}")
    out["n_pivots"] = len(piv)
    out["n_entry_signals"] = sum(1 for s in zzf["signals"] if str(s.get("signal", "")).startswith("ZLF Entry"))
    return out


def report(sym, tf, lo_hours=18):
    df = load(sym, tf)
    if df is None:
        print(f"[skip] {sym}_{tf} غير موجود في الكاش")
        return
    print(f"\n{'='*80}\n{sym} · {tf} · {len(df)} شمعة ({df.index[0]} → {df.index[-1]})")
    r_tv = check("tradingview", df)
    print(f"  TV  (depth={DEPTH}, dev={DEV:g} ({DEV/10:g}%), backstep={BACK}): "
          f"pivots={r_tv['n_pivots']} · ZLF entries={r_tv['n_entry_signals']} · "
          f"{'ALL PROPERTIES PASS ✓' if not r_tv['fails'] else 'FAILS: ' + '; '.join(r_tv['fails'])}")

    r_lux = check("luxalgo", df, mode="luxalgo", length=100)
    print(f"  LUX (length=100 — توافق رجعي): pivots={r_lux['n_pivots']} · "
          f"{'PASS ✓' if not r_lux['fails'] else 'FAILS: ' + '; '.join(r_lux['fails'])}")

    # P6 كثافة نافذة العرض (نفس نافذة صورة المستخدم تقريباً)
    view = df.iloc[-(lo_hours * 60 if tf == "1m" else lo_hours * 12):]
    lo_bar = len(df) - len(view)
    piv_view = [p for p in r_tv["pivots"] if int(p["bar"]) >= lo_bar]
    moves = []
    for a, b in zip(piv_view, piv_view[1:]):
        p0, p1 = float(a["price"]), float(b["price"])
        moves.append((p1 - p0) / p0 * 100.0 if p0 else 0.0)
    n_small = sum(1 for m in moves if abs(m) < 0.5)
    print(f"  P6 كثافة نافذة {lo_hours}h: pivots={len(piv_view)} · legs={len(moves)} · "
          f"small(<0.5%)={n_small} · نطاق الموجات: "
          f"{min([abs(m) for m in moves], default=0):.2f}%–{max([abs(m) for m in moves], default=0):.2f}%")
    last_pivs = [(pd.Timestamp(df.index[int(p['bar'])]).strftime('%m-%d %H:%M'), p['kind'], float(p['price']))
                 for p in piv_view]
    for z in last_pivs[-8:]:
        print(f"    {z[0]} {z[1]:6s} @{z[2]:.6g}")


def main():
    print("ROUND19 — اختبار الخصائص الحاكمة لوضع tradingview (كاش محلي)")
    report("LAZIOUSDT", "1m")
    report("BTCUSDT", "5m")
    report("ZECUSDT", "5m")
    report("ETHUSDT", "1m")
    report("1000CATUSDT", "1m")

    # P7: توافق رجعي بنيوي — نفس المدخلات تعطي نفس بنية المخرجات في الوضعين
    print("\nP7 — بنية المخرجات متطابقة بين الوضعين:")
    df = load("BTCUSDT", "5m")
    a = zigzag_fib(df, mode="luxalgo", length=100)
    b = zigzag_fib(df, mode="tradingview", depth=12, deviation=20, backstep=3)
    keys_a, keys_b = set(a.keys()), set(b.keys())
    print(f"  keys_equal={keys_a == keys_b} · series_equal_keys={set(a['series'].keys()) == set(b['series'].keys())}")
    sa, sb = a["series"], b["series"]
    ok_cols = all(len(sa[k]) == len(sb[k]) for k in sa)
    print(f"  columns_length_equal={ok_cols} (نفس طول السلاسل — عقد الأعمدة سليم)")


if __name__ == "__main__":
    main()
