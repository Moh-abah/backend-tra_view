#!/usr/bin/env python3
"""R76 — بطارية التحقق المحلية لنواة PRO76-mtf-osc-core v2.0.0.

الأدلة المرجعية مقيسة من الإنتاج الحي (161.97.73.254:8000) بتاريخ 2026-11-15:
  · /tmp/live_osc_probe.json — 400 شمعة 1m اصطناعية (seed=42) + سلاسل الماكد/RSI/MOM الحية.
  · عقد 1.1.0: 67 نسخة · warnings عربية حرفية · fields_per_kind · counts.

الفحوص:
  T1  تطابق صيغ PRO73/74 بت-بت: MACD line (talib-EMA) · RSI Wilder · ma · BB · MOM line/pct.
  T2  B-4: الإشارة = SMA(line, signal) الآن (تختلف عن الحي EMA عمداً) · hist = line − signal.
  T3  B-1: شموع 1s → نسخ 5s/15s/30s متاحة وقيمها = محسوبة من التجميع الصاعد.
  T4  B-1: عند قاعدة 1m تبقى نسخ الثواني tf_below_base بتحذير + كود.
  T5  B-3: 3 نسخ ممررة → 9 سلاسل فقط (لا مستند 67).
  T6  B-2: view_times على نافذة 1s → mode=view · bars = أعمدة العرض · full_bars = الدقة الكاملة.
  T7  B-7: crosses [{index, up}] بمقاييس العرض في نمط view.
  T8  B-5: warning_codes + warnings_v2 موجودة لكل تحذير.
  T9  بوابة osc_conditions (شجرة and/or/not) عند الشمعة المغلقة — بلا استشراف.
  T10 عقد العدادات: trend_entries/final/blocked من entry_series الخام.
  T11 الأداء/الذاكرة: 665K شمعة × مستند 67 كامل بنمط none — زمن معقول وذاكرة محكمة
      (لا قوائم Python بطول كامل في الرد).
  T12 المحركان: trendy_macd/blazing_macd — إعادة تسمية السلاسل + بوابة الدخول + iblocked.
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/z/my-project/r67-workspace/src")
from app.services.indicators.mtf_oscillator_core import (  # noqa: E402
    TF_MS, DEFAULT_OSC_INSTANCES, build_osc_section, resolve_instances,
    evaluate_conditions, normalize_timeframe,
)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗ فشل'} {name}" + (f" — {detail}" if detail else ""))


def nl(title: str):
    print(f"\n=== {title} ===")


def main() -> int:
    probe = json.load(open("/tmp/live_osc_probe.json"))
    cl = np.array(probe["closes"])
    live = probe["series"]
    n = len(cl)
    candles = [{"time": 1777593540000 + i * 60_000, "close": float(cl[i])} for i in range(n)]

    nl("T1 — تطابق صيغ PRO73/74 بت-بت (أدلة حية)")
    r = build_osc_section(
        candles, base_timeframe="1m", prefix="zzfetm",
        osc_instances=[
            {"kind": "macd", "id": "macd_1m_6_13_4", "timeframe": "1m", "fast": 6, "slow": 13, "signal": 4},
            {"kind": "rsi", "id": "rsi_1m_14_14", "timeframe": "1m", "period": 14, "ma_length": 14, "bb_std": 2},
            {"kind": "mom", "id": "mom_1m_10", "timeframe": "1m", "length": 10},
        ],
    )
    line = np.array([np.nan if x is None else x for x in r["series"]["zzfetm_osc_macd_1m_6_13_4_line"]])
    lv = np.array([np.nan if x is None else x for x in live["zzfetm_osc_macd_1m_6_13_4_line"]])
    d = np.nanmax(np.abs(line - lv))
    check("MACD line == الحي بت-بت (talib-EMA)", d == 0.0, f"maxdiff={d:.2e}")

    val = np.array([np.nan if x is None else x for x in r["series"]["zzfetm_osc_rsi_1m_14_14_value"]])
    lvr = np.array([np.nan if x is None else x for x in live["zzfetm_osc_rsi_1m_14_14_value"]])
    d = np.nanmax(np.abs(val - lvr))
    check("RSI value == الحي (Wilder-talib)", d < 1e-10, f"maxdiff={d:.2e}")

    ma = np.array([np.nan if x is None else x for x in r["series"]["zzfetm_osc_rsi_1m_14_14_ma"]])
    lvm = np.array([np.nan if x is None else x for x in live["zzfetm_osc_rsi_1m_14_14_ma"]])
    d = np.nanmax(np.abs(ma - lvm))
    check("RSI ma == الحي (EMA-talib)", d < 1e-10, f"maxdiff={d:.2e}")

    bu = np.array([np.nan if x is None else x for x in r["series"]["zzfetm_osc_rsi_1m_14_14_bb_upper"]])
    lvb = np.array([np.nan if x is None else x for x in live["zzfetm_osc_rsi_1m_14_14_bb_upper"]])
    d = np.nanmax(np.abs(bu - lvb))
    check("RSI bb_upper == الحي (ma + 2·std سكّاني)", d < 1e-10, f"maxdiff={d:.2e}")

    mo = np.array([np.nan if x is None else x for x in r["series"]["zzfetm_osc_mom_1m_10_line"]])
    lvo = np.array([np.nan if x is None else x for x in live["zzfetm_osc_mom_1m_10_line"]])
    d = np.nanmax(np.abs(mo - lvo))
    check("MOM line == الحي (c − c10)", d == 0.0, f"maxdiff={d:.2e}")
    pc = np.array([np.nan if x is None else x for x in r["series"]["zzfetm_osc_mom_1m_10_pct"]])
    lvp = np.array([np.nan if x is None else x for x in live["zzfetm_osc_mom_1m_10_pct"]])
    d = np.nanmax(np.abs(pc - lvp))
    check("MOM pct == الحي", d < 1e-10, f"maxdiff={d:.2e}")

    nl("T2 — B-4: إشارة MACD = SMA حرفياً كما Pine")
    sig = np.array([np.nan if x is None else x for x in r["series"]["zzfetm_osc_macd_1m_6_13_4_signal"]])
    sma_mine = pd.Series(line).rolling(4).mean().to_numpy()
    m = ~np.isnan(sma_mine) & ~np.isnan(sig)
    d = np.nanmax(np.abs(sig[m] - sma_mine[m]))
    check("signal == SMA(line, 4)", d < 1e-12, f"maxdiff={d:.2e}")
    lvs = np.array([np.nan if x is None else x for x in live["zzfetm_osc_macd_1m_6_13_4_signal"]])
    dl = np.nanmax(np.abs(sig[m] - lvs[m]))
    check("signal تختلف عن الحي EMA (تغيير B-4 مقصود)", dl > 1e-3, f"maxdiff={dl:.2e}")
    hist = np.array([np.nan if x is None else x for x in r["series"]["zzfetm_osc_macd_1m_6_13_4_hist"]])
    d = np.nanmax(np.abs((line - sig)[~np.isnan(hist)] - hist[~np.isnan(hist)]))
    check("hist == line − signal", d < 1e-12, f"maxdiff={d:.2e}")

    nl("T3 — B-1: الثواني تعمل (تجميع صاعد من شموع 1s)")
    rng = np.random.default_rng(11)
    ns = 9000  # 2.5 ساعة من الثواني
    t0 = 1777593540000
    cl1s = 100 + np.cumsum(rng.normal(0, 0.01, ns))
    candles_1s = [{"time": t0 + i * 1000, "close": float(cl1s[i])} for i in range(ns)]
    r1s = build_osc_section(
        candles_1s, base_timeframe="1s", prefix="zzfetm",
        osc_instances=[
            {"kind": "macd", "id": "macd_5s_6_13_4", "timeframe": "5s", "fast": 6, "slow": 13, "signal": 4},
            {"kind": "macd", "id": "macd_15s_6_13_4", "timeframe": "15s", "fast": 6, "slow": 13, "signal": 4},
            {"kind": "macd", "id": "macd_30s_6_13_4", "timeframe": "30s", "fast": 6, "slow": 13, "signal": 4},
            {"kind": "rsi", "id": "rsi_5s_14_14", "timeframe": "5s", "period": 14, "ma_length": 14, "bb_std": 2},
            {"kind": "mom", "id": "mom_1s_10", "timeframe": "1s", "length": 10},
        ],
    )
    avail = {i["id"]: i["available"] for i in r1s["section"]["instances"]}
    check("macd_5s/15s/30s متاحة فوق قاعدة 1s", all(avail[f"macd_{tf}_6_13_4"] for tf in ("5s", "15s", "30s")))
    check("rsi_5s متاحة", avail["rsi_5s_14_14"])
    check("mom_1s متاحة (نفس القاعدة)", avail["mom_1s_10"])
    check("base_tf = 1s (مكتشفة من التباعد)", r1s["section"]["base_tf"] == "1s")
    # التحقق الرياضي: تجميع 5s = متوسط... لا: إغلاق آخر شمعة في الدلو
    cl5 = cl1s.reshape(-1, 5)[:, -1]
    ln5 = np.array([np.nan if x is None else x for x in r1s["series"]["zzfetm_osc_macd_5s_6_13_4_line"]])
    # أول قيمة صالحة عند slow-1=12 على شبكة 5s → الشريط 12 مكتمل عند نهاية دلو 12
    # القيمة عند شمعة 1s رقم i تأتي من الشريط B(i)-1
    b = (np.arange(ns))  # دلاء 5s
    bi = np.arange(ns) // 5
    usable = bi - 1
    i_probe = 5 * 13 + 4  # آخر شمعة الدلو 13 → الشريط 12 مكتمل
    # EMA-talib على cl5
    def ema_t(x, p):
        o = np.full(len(x), np.nan); o[p-1] = np.mean(x[:p]); a = 2.0/(p+1)
        for i in range(p, len(x)):
            o[i] = a*x[i] + (1-a)*o[i-1]
        return o
    ln5_mine = ema_t(cl5, 6) - ema_t(cl5, 13)
    check("macd_5s line عند آخر شمعة دلو == قيمة الشريط المكتمل 12",
          abs(ln5[i_probe] - ln5_mine[12]) < 1e-9,
          f"{ln5[i_probe]:.6f} vs {ln5_mine[12]:.6f}")
    # وقيمة الشريط 13 غير معتمدة قبل اكتمال دلو 13 (لا استشراف)
    i_mid = 5 * 13 + 2
    check("بلا استشراف: منتصف الدلو يرى الشريط السابق فقط",
          ln5[i_mid] == ln5[i_probe] or abs(ln5[i_mid] - ln5_mine[12]) < 1e-9)

    nl("T4 — B-1: قاعدة 1m → نسخ الثواني tf_below_base + كود")
    rm = build_osc_section(candles, base_timeframe="1m",
                           osc_instances=[{"kind": "macd", "id": "macd_1s_6_13_4", "timeframe": "1s",
                                           "fast": 6, "slow": 13, "signal": 4}])
    im = rm["section"]["instances"][0]
    check("available=False", im["available"] is False)
    check("why=tf_below_base", im["why"] == "tf_below_base")
    check("code=tf_below_base (B-5)", im.get("code") == "tf_below_base")
    check("warning_codes فيها tf_below_base", "tf_below_base" in rm["section"]["warning_codes"])
    check("warnings_v2[0].code", rm["section"]["warnings_v2"][0]["code"] == "tf_below_base")
    check("نص التحذير عربي كما كان", "الفريم أدنى" in rm["section"]["warnings"][0])

    nl("T5 — B-3: النسخ الممررة تُحترم (3 → 9 سلاسل)")
    osc_series_count = len([k for k in r["series"] if "_osc_" in k and k != "zzfetm_osc_gate"])
    check("9 سلاسل (3 macd/rsi/mom × حقولها)", osc_series_count == 3 + 4 + 2,
          f"got {osc_series_count}")
    check("عدد النسخ في القسم = 3", len(r["section"]["instances"]) == 3)

    nl("T6 — B-2: نمط view (حساب كامل الدقة + تخزين عند أعمدة العرض)")
    view_times = [t0 + i * 1000 for i in range(0, ns, 3)]  # كل 3 ثوانٍ = 3000 عمود
    rv = build_osc_section(candles_1s, base_timeframe="1s", prefix="zzfetm",
                           osc_instances=[{"kind": "macd", "id": "macd_5s_6_13_4", "timeframe": "5s",
                                           "fast": 6, "slow": 13, "signal": 4}],
                           view_times=view_times, osc_series="view")
    sec = rv["section"]
    check("view_sampled=True", sec["view_sampled"] is True)
    check("bars = أعمدة العرض (B-8)", sec["bars"] == len(view_times), f"{sec['bars']} vs {len(view_times)}")
    check("full_bars = الدقة الكاملة", sec.get("full_bars") == ns)
    check("view_times مرفقة (B-6)", sec.get("view_times") == view_times)
    ln_v = r1s["series"]["zzfetm_osc_macd_5s_6_13_4_line"]
    lv_v = rv["series"]["zzfetm_osc_macd_5s_6_13_4_line"]
    # العينة عند i=3j تساوي القيمة الكاملة عند 3j
    same = all((lv_v[j] is None and ln_v[3*j] is None) or
               (lv_v[j] is not None and ln_v[3*j] is not None and abs(lv_v[j] - ln_v[3*j]) < 1e-12)
               for j in range(len(view_times)))
    check("عينات view == القيم الكاملة عند نفس الفهرس", same)

    nl("T7 — B-7: التقاطعات بمقاييس العرض")
    cr = sec.get("crosses", {}).get("macd_5s_6_13_4")
    check("crosses موجودة وقائمة", isinstance(cr, list))
    if cr:
        check("كل عنصر {index, up} ومقاسه ضمن العرض",
              all(isinstance(x.get("index"), int) and isinstance(x.get("up"), bool)
                  and 0 <= x["index"] < len(view_times) for x in cr))
        # تحقق رياضي عند أول تقاطع
        x0 = cr[0]
        full_idx = view_times[x0["index"]]  # زمن → فهرس كامل
        fi = (full_idx - t0) // 1000
        line_f = ln_v[fi]; sig_f = r1s["series"]["zzfetm_osc_macd_5s_6_13_4_signal"][fi]
        check("التقاطع يطابق إشارة line×signal",
              (line_f is not None and sig_f is not None and
               (x0["up"] == (line_f > sig_f))))

    nl("T8 — B-5 + عقد القسم العام")
    check("engine=PRO76-mtf-osc-core", sec_ := r["section"]["engine"] == "PRO76-mtf-osc-core")
    check("version=2.0.0", r["section"]["version"] == "2.0.0")
    check("fields_per_kind مطابق للحي", r["section"]["fields_per_kind"] ==
          {"rsi": ["value", "ma", "bb_upper", "bb_lower"], "macd": ["line", "signal", "hist"],
           "mom": ["line", "pct"]})
    check("base_tf_ms رقم صريح (B-2)", r["section"].get("base_tf_ms") == 60_000)
    d67 = build_osc_section(candles)  # بلا نسخ ⇒ 67 افتراضياً
    check("None ⇒ المستند الافتراضي 67 (توافق 1.1.0)",
          len(d67["section"]["instances"]) == 67)
    check("التحذيرات الحية 12 نسخة ثواني تحت 1m",
          len(d67["section"]["warnings"]) == 12, f"got {len(d67['section']['warnings'])}")

    nl("T9 — بوابة الشروط (شجرة and/or/not) بلا استشراف")
    lookup = {"osc:a.value": np.array([np.nan, 10.0, 10.0, 10.0, 5.0]),
              "osc:b.value": np.array([np.nan, 20.0, 5.0, 20.0, 5.0])}
    tree = {"logic": "or", "conditions": [
        {"left": "osc:a.value", "op": ">", "right": 7},
        {"logic": "and", "conditions": [
            {"left": "osc:b.value", "op": "<", "right": 6},
            {"logic": "not", "conditions": [
                {"left": "osc:a.value", "op": "<", "right": "osc:b.value"}]},
        ]},
    ]}
    got = [evaluate_conditions(tree, lookup, i) for i in range(5)]
    # i=0: a مفقود→False؛ b مفقود→False → or(False,False)=False
    # i=1: a=10>7 → True
    # i=2: a>7 True → True
    # i=3: True
    # i=4: a=5>7 False؛ b=5<6 True و not(a<b)=not(5<5)=True → and=True → or True
    check("التقييم المتوقع [F,T,T,T,T]", got == [False, True, True, True, True], str(got))
    sk = {"left": "osc:a.value", "op": ">", "right": 7, "skip_unavailable": True}
    check("skip_unavailable=True عند القيمة المفقودة",
          evaluate_conditions(sk, lookup, 0) is True)

    nl("T10 — عدادات الدخول من entry_series الخام")
    ent = [False] * 10
    ent[2] = True; ent[5] = True; ent[8] = True
    gate_arr = [True] * 10; gate_arr[5] = False
    rc = build_osc_section(candles[:10], osc_instances=[{"kind": "mom", "id": "mom_1m_5",
                                                         "timeframe": "1m", "length": 5}],
                           entry_series=ent, osc_conditions={"left": "osc:mom_1m_5.line", "op": ">", "right": -1e18})
    # الشجرة تفتح البوابة حيث mom له قيمة (من index 5) — القيم قبلها مفقودة → False
    cnt = rc["section"]["counts"]
    check("trend_entries=3", cnt["trend_entries"] == 3, str(cnt))
    check("counts keys", set(cnt) == {"trend_entries", "final_entries", "osc_blocked_entries"})
    check("gate_open منطقي", isinstance(rc["section"]["gate_open"], bool))

    nl("T11 — الأداء/الذاكرة: 665K شمعة × مستند 67 بنمط none (علة SIGKILL)")
    big_n = 665_099
    tb = np.arange(big_n, dtype=np.int64) * 60_000 + 1697414400000
    cb = 100.0 + np.cumsum(np.random.default_rng(3).normal(0, 0.05, big_n))
    big_candles = pd.DataFrame({"time": tb, "close": cb})
    t0 = time.perf_counter()
    rn = build_osc_section(big_candles, base_timeframe="1m", osc_series="none",
                           entry_series=[False] * big_n)
    el = time.perf_counter() - t0
    n_series = len(rn["series"])
    check("لا سلاسل مخزنة في نمط none", n_series == 0, f"series={n_series}")
    check("البوابة بطول الدقة الكاملة", len(rn["gate"]) == big_n)
    check("الزمن معقول (<90s)", el < 90.0, f"{el:.1f}s")
    check("كل النسخ الأعلى متاحة (55/67)", sum(1 for i in rn["section"]["instances"] if i["available"]) == 55)
    print(f"    (665K × 67 نسخة بواجهة none: {el:.1f}s، الذاكرة = numpy فقط)")
    del big_candles, rn

    nl("T12 — المحركان: التسمية + البوابة + iblocked")
    from app.services.indicators.overlays_zlf_e2e_trendy_macd import zigzag_fib_e2e_trendy_macd
    from app.services.indicators.overlays_zlf_e2e_blazing_macd import zigzag_fib_e2e_blazing_macd
    # شموع 1m حقيقية الشكل (OHLCV)
    rng = np.random.default_rng(7)
    nc = 600
    price = 100.0
    full_candles = []
    for i in range(nc):
        o = price
        c = o + rng.normal(0.05, 0.3)
        h = max(o, c) + abs(rng.normal(0, 0.1))
        lo = min(o, c) - abs(rng.normal(0, 0.1))
        full_candles.append({"time": 1777593540000 + i * 60_000, "open": o, "high": h,
                             "low": lo, "close": c, "volume": float(rng.uniform(50, 300))})
        price = c
    res_t = zigzag_fib_e2e_trendy_macd(
        full_candles, length=40,
        osc_instances=[{"kind": "macd", "id": "macd_1m_6_13_4", "timeframe": "1m",
                        "fast": 6, "slow": 13, "signal": 4}],
        osc_conditions={"left": "osc:macd_1m_6_13_4.hist", "op": ">", "right": -1e9},
    )
    srs = res_t["series"]
    check("سلاسل zzfetm_* (إعادة التسمية)", any(k.startswith("zzfetm_dir") for k in srs))
    check("سلاسل الموشرات zzfetm_osc_*", "zzfetm_osc_macd_1m_6_13_4_line" in srs)
    check("osc_gate موجودة", "zzfetm_osc_gate" in srs)
    check("entry_iblocked موجودة", "zzfetm_entry_iblocked" in srs)
    # خام بوابة الترند (ما بعد الترند وقبل بوابة الموشرات) = نهائي أو ممنوع
    # لكل إشارة مبوّبة — عقد الشفافية الرباعية (raw_s قبل الترند ليس مرجع
    # العدادات: counts.trend_entries عدّاد ما بعد الترند كما في PRO73).
    fin = [bool(x) for x in srs["zzfetm_entry"]]
    ib = [bool(x) for x in srs["zzfetm_entry_iblocked"]]
    post = [False] * len(fin)
    for n_sig in (1, 2, 3):
        fs = srs.get(f"zzfetm_entry_s{n_sig}") or []
        bs = srs.get(f"zzfetm_entry_iblocked_s{n_sig}") or []
        for i in range(min(len(fs), len(bs), len(post))):
            if fs[i] or bs[i]:
                post[i] = True
    check("final = post-trend ∧ gate (كل خام إما نهائي أو ممنوع)",
          all((not p_) or (f_ != b_) for p_, f_, b_ in zip(post, fin, ib)))
    cnt = res_t["osc"]["counts"]
    check("counts.trend_entries", cnt.get("trend_entries") == sum(post))
    check("counts.final+blocked = trend", cnt.get("final_entries", 0) + cnt.get("osc_blocked_entries", 0) == cnt.get("trend_entries", 0))
    check("قسم osc.version=2.0.0", res_t["osc"].get("version") == "2.0.0")
    check("base_engine.name = محرك الترندية", (res_t.get("base_engine") or {}).get("name") == "ZLF-End-To-End-Trendy")
    res_b = zigzag_fib_e2e_blazing_macd(
        full_candles, length=40,
        osc_instances=[{"kind": "rsi", "id": "rsi_1m_14_14", "timeframe": "1m",
                        "period": 14, "ma_length": 14, "bb_std": 2}],
    )
    srs_b = res_b["series"]
    check("blazing: سلاسل zzfbm_*", any(k.startswith("zzfbm_dir") for k in srs_b))
    check("blazing: n5/n6 موجودة", "zzfbm_entry_n5" in srs_b and "zzfbm_entry_n6" in srs_b)
    check("blazing: counts.blazing_entries", "blazing_entries" in res_b["osc"]["counts"])
    check("blazing: بلا شروط ⇒ gate_open=True", res_b["osc"]["gate_open"] is True)

    print(f"\n{'='*60}\nالنتيجة: {len(PASS)} ناجح · {len(FAIL)} فاشل")
    if FAIL:
        print("الفاشلة:", FAIL)
    return 2 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
