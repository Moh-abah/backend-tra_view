#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""التحقق المستقل من صحة إشارات E2E — بشرط-بشرط من شموع Binance الخام.

عقد الإثبات (نفس منهجية ج34):
- المرجع R اللحظي = أكبر شمعة حمراء (close<open) **حجماً** داخل عمر النطاق الحي
  (من anchor حتى شمعة الإشارة) — قبل الإشارة فقط (سببية).
- G خضراء ∧ low_G ≥ launch_line ∧ هيمنة الخضراء (لا خضراء بين R وG بحجم ≥ V_G).
- S1 = اختراق (H>ref_high) ∧ (V>V_R) · S2 = اختراق ∧ حجم أقل/مساوٍ · S3 = رفض ∧ حجم أكبر.
ملاحظة: المرجع المرفق في قسم ranges هو النهائي عند موت النطاق؛ الصحيح سببياً هو
الأعمدة ind_zzfe_liq_ref_high/ref_vol عند شمعة الإشارة — والمقارنة هنا تحقق ذلك.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

BINANCE = "https://api.binance.com/api/v3/klines"
TF_MS = 5 * 60 * 1000


def klines(start_ms, end_ms, symbol="BTCUSDT", interval="5m"):
    url = f"{BINANCE}?symbol={symbol}&interval={interval}&startTime={start_ms}&endTime={end_ms}&limit=1000"
    return json.load(urllib.request.urlopen(url, timeout=30))


def verify(chart_json_path, sig_index=0):
    cd = json.load(open(chart_json_path))
    vc = cd["visual_candles"]
    e2 = cd["overlays"]["overlays"]["zzfib_e2e"]
    sig = [s for s in e2["signals"] if (s.get("state") or 0) > 0][sig_index]
    bar_ms = sig["time"]
    ridx = int(sig["range_index"])
    r = e2["ranges"][ridx]
    launch = r["launch_line"]
    anchor_ms = r["anchor"]["time"]

    kl = klines(bar_ms - 999 * TF_MS, bar_ms + 1000)
    idx = {k[0]: i for i, k in enumerate(kl)}
    i = idx[bar_ms]
    ai = idx[anchor_ms]
    O, H, L, C, V = (float(kl[i][j]) for j in (1, 2, 3, 4, 5))

    # المرجع اللحظي: أكبر حمراء في [anchor .. i-1]
    best = None
    for j in range(ai, i):
        kj = kl[j]
        Oj, Cj, Vj = float(kj[1]), float(kj[4]), float(kj[5])
        if Cj < Oj and (best is None or Vj >= best[0]):
            best = (Vj, float(kj[2]), kj[0])
    ref_vol, ref_high, ref_t = best

    # مطابقة الأعمدة السببية (المصدر اللحظي الحقيقي)
    candle = next(x for x in vc if x["timestamp"] ==
                  datetime.fromtimestamp(bar_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z"))
    col_match = (abs(ref_vol - candle["ind_zzfe_liq_ref_vol"]) < 1e-6
                 and abs(ref_high - candle["ind_zzfe_liq_ref_high"]) < 1e-6)

    # الشروط
    green = C > O
    breakout = H > ref_high
    vol_dom = V > ref_vol
    launch_ok = L >= launch - 1e-9
    dominance = True
    for j in range(idx[ref_t] + 1, i):
        kj = kl[j]
        Oj, Cj, Vj = float(kj[1]), float(kj[4]), float(kj[5])
        if Cj > Oj and Vj >= V:
            dominance = False
            break
    expected = "S1" if (green and breakout and vol_dom) else (
        "S2" if (green and breakout and not vol_dom) else (
            "S3" if (green and not breakout and vol_dom) else "NONE"))
    actual = sig["signal"].split()[-1]

    out = {
        "signal": sig["signal"],
        "time": datetime.fromtimestamp(bar_ms / 1000, tz=timezone.utc).isoformat(),
        "range_index": ridx,
        "range_anchor": datetime.fromtimestamp(anchor_ms / 1000, tz=timezone.utc).isoformat(),
        "launch_line": launch,
        "ref_instantaneous": {"vol": ref_vol, "high": ref_high, "time": datetime.fromtimestamp(ref_t / 1000, tz=timezone.utc).isoformat()},
        "columns_match_binance": col_match,
        "conditions": {"green": green, "breakout": breakout, "vol_dom": vol_dom,
                       "launch_ok": launch_ok, "green_dominance": dominance},
        "expected": expected, "actual": actual,
        "MATCH": expected == actual,
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "week_full.json"
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    out = verify(path, idx)
    sys.exit(0 if out["MATCH"] and out["columns_match_binance"] else 1)
