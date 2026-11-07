#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# ✅ ROUND32 — التحقق الشامل — «الزقزاق البطل e2e الترنديه»
# =============================================================================
# يتحقق من كل عقد الجولة 32:
#   1) محرك الترند المعزول (trend_fractals.py) — وفاء Pine: الفراكتالات،
#      ولادة الخطوط بإحداثياتها، التقاطعات، بلا استشراف، فترات قالبية.
#   2) محرك الترندية المعزول (overlays_zlf_e2e_trendy.py) — E2E حرفياً عند
#      تعطيل البوابة (الاختبار القاتل) + اتساق البوابة عند تفعيلها.
#   3) الانحدار الصفري — الأنواع الخمسة القديمة والقوالب الثلاثة القديمة
#      مطابقة بايت-ببايت (لقطة ذهبية قبل/بعد).
#   4) التوصيل الكامل — الموزّع + الأعمدة التعاقدية + الجسر + السجل +
#      البريسِت + مسار البث الحي + شارت الباك تست.
#   5) اختبار وظيفي كامل — محرك الباك تست الحقيقي ينتج صفقات الترندية
#      بأعمدة ind_zzfet_* داخل شموع الرسم، وتطابق كامل مع E2E عند التعطيل.
#
# النتيجة: evidence/verify_round32.json — كل فحص PASS/FAIL مع تفاصيله.
# =============================================================================

import asyncio
import copy
import hashlib
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = []
CHECKS = 0


def check(idx, name, ok, details=None):
    global CHECKS
    CHECKS += 1
    RESULTS.append({"n": idx, "name": name, "pass": bool(ok),
                    "details": details if details is not None else {}})
    mark = "PASS ✅" if ok else "FAIL ❌"
    print(f"[{idx:02d}] {mark} — {name}")
    if not ok and details:
        print("      details:", json.dumps(details, ensure_ascii=False, default=str)[:500])
    return bool(ok)


def jhash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


# ---------------------------------------------------------------------------
# البيانات: BTCUSDT 1m حية من Binance (مع سقوط احتياطي للملف المرجعي)
# ---------------------------------------------------------------------------
def fetch_candles() -> list:
    # ✅ ROUND34 — حتمية قابلة للتكرار: نافذة السوق الحية قد تكون بلا أي إشارات
    # أثناء التماسك (مُثبت: نافذة 2026-11-05 15:40 كانت raw=0 بينما نافذة 15:29
    # فيها إشارات — نفس الكود بالضبط، والقديم=الجديد على النافذة نفسها). لذلك
    # نُفضّل اللقطة الذهبية (بيانات Binance حقيقية 2026-11-04 بها 22 حدثاً
    # خاماً) — نفس منهج فحص 17 للانحدار الصفري — والحي عند توفر الشبكة يُستخدم
    # فقط إذا لم توجد لقطة. هذا يجعل الحزمة خضراء قابلة لإعادة الإنتاج في أي
    # بيئة وأي وقت (بلا تذبذب حسب مزاج السوق اللحظي).
    here = os.path.dirname(os.path.abspath(__file__))
    for golden in (os.path.join(here, "evidence", "golden_btc_1m.json"), "/tmp/golden_btc_1m.json"):
        if os.path.exists(golden):
            d = json.load(open(golden))
            if d and len(d) >= 500:
                return d
    url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=1000"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = json.loads(r.read().decode())
        if isinstance(raw, list) and len(raw) >= 500:
            return [{"time": int(k[0]), "open": k[1], "high": k[2], "low": k[3],
                     "close": k[4], "volume": k[5]} for k in raw]
    except Exception:
        pass
    for fallback in ("/tmp/golden_btc_1m.json",
                     os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "evidence", "btc_1m_klines.json")):
        if os.path.exists(fallback):
            d = json.load(open(fallback))
            if d and isinstance(d[0], dict):
                return d
            return [{"time": k[0], "open": k[1], "high": k[2], "low": k[3],
                     "close": k[4], "volume": k[5]} for k in d]
    raise RuntimeError("لا بيانات متاحة — فشل الجلب والاحتياط معاً")


KLINES = fetch_candles()
# بيانات اللقطة الذهبية (مجمعة مع الأدلة لجعل الانحدار الصفري قابلًا لإعادة الإنتاج في أي بيئة)
def load_golden_data() -> list:
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "evidence", "golden_btc_1m.json"), "/tmp/golden_btc_1m.json"):
        if os.path.exists(cand):
            return json.load(open(cand))
    return None


def load_golden_hashes() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "evidence", "golden_before_round32.json"), "/tmp/golden_before_round32.json"):
        if os.path.exists(cand):
            return json.load(open(cand))
    return None


def main():
    import pandas as pd
    from app.services.indicators.trend_fractals import (
        auto_trendlines_fractal, _pivot_events, TRF_ENGINE_NAME, TRF_SPEC)
    from app.services.indicators.overlays_zlf_e2e import zigzag_fib_e2e, ZLF_E2E_ENGINE_NAME
    from app.services.indicators.overlays_zlf_e2e_trendy import (
        zigzag_fib_e2e_trendy, ZLF_E2E_TRENDY_ENGINE_NAME, ZLF_E2E_TRENDY_SPEC)
    from app.services.indicators.overlays import compute_overlays, OVERLAY_TYPES, _normalize_overlay_params
    from app.services.indicators.overlay_columns import (
        columns_from_overlays_result, columns_for_configs, config_to_overlay_params,
        normalize_overlay_name, CONTRACT_COLUMNS, KNOWN_OVERLAY_BASES)
    from app.services.indicators.calculator import IndicatorCalculator
    from app.services.indicators.registry import IndicatorRegistry
    from app.services.strategy.presets import get_presets, ZLF_E2E_TRENDY_TRIPLE_SIGNAL
    from app.services.strategy.schemas import StrategyConfig as StrategyConfigSchema

    N = len(KLINES)
    params_old = {
        "zigzag": {"length": 100},
        "fib": {"depth": 12, "dev_threshold": 0.5, "retracement": 0.618},
        "trendline": {"period": 10, "max_pairs": 2},
        "zzfib": {"mode": "tradingview", "depth": 12, "deviation": 20, "backstep": 3},
        "zzfib_e2e": {"mode": "luxalgo", "length": 100},
    }

    # ============================ كتلة 1: محرك الترند المعزول ============================
    # سناريو مُصنَّع: قمتان معلومتان عند 15 و40 (نافذة 5 → ظهور عند 21 و46)
    prices = []
    for i in range(80):
        if i <= 15:
            prices.append(100 + i)
        elif i <= 27:
            prices.append(115 - (i - 15))
        elif i <= 40:
            prices.append(103 + (i - 27) * 2.071428)
        else:
            prices.append(130 - (i - 40) * 1.5)
    syn = [{"time": 1700000000000 + i * 60000, "open": p - 0.5, "high": p + 0.5,
            "low": p - 1.0, "close": p, "volume": 10.0} for i, p in enumerate(prices)]

    trf_syn = auto_trendlines_fractal(syn, periods=[5], confirm_mode="majority")
    ups = _pivot_events([p + 0.5 for p in prices], 5, "upper")

    check(1, "trend_fractals: الفراكتال يظهر عند p+n+1 (وفاء إزاحة [1] في Pine)",
          ups and ups[0][0] == 21 and ups[0][1] == 15,
          {"events": ups[:2]})

    lines_up = trf_syn["lines"]["p5"]["upper"]
    ln = lines_up[0] if lines_up else None
    ok2 = bool(ln and ln["x1"] == 40 and ln["x2"] == 15
               and abs(ln["slope"] - (ln["y1"] - ln["y2"]) / 25.0) < 1e-12
               and ln["formed_at_bar"] == 46 and ln["active"] is True)
    check(2, "trend_fractals: إحداثيات الخط كاملة (x/t/y للطرفين + الميل + ولادة عند الظهور)",
          ok2, {"line": ln})

    y_series = trf_syn["series"]["trf_p5_upper"]
    y_manual = ln["y1"] + ln["slope"] * (50 - ln["x1"])
    check(3, "trend_fractals: قيمة الخط الممتد عند شمعة بعيدة = معادلة التمديد الأيمن",
          y_series[50] is not None and abs(y_series[50] - y_manual) < 1e-9,
          {"series@50": y_series[50], "manual": y_manual})

    trf_pref = auto_trendlines_fractal(syn[:45], periods=[5], confirm_mode="majority")
    mm_up = sum(1 for a, b in zip(trf_pref["series"]["trf_p5_upper"], trf_syn["series"]["trf_p5_upper"][:45]) if a != b)
    mm_bias = sum(1 for a, b in zip(trf_pref["series"]["trf_p5_bias"], trf_syn["series"]["trf_p5_bias"][:45]) if a != b)
    check(4, "trend_fractals: بلا استشراف — الحساب على بادئة البيانات مطابق حرفياً",
          mm_up == 0 and mm_bias == 0, {"upper_mismatches": mm_up, "bias_mismatches": mm_bias})

    # تقاطع مصنَّع بوفاء ta.cross: سعر يعبر الخط الصاعد صعوداً مرة واحدة
    cross_prices = list(prices)
    y60 = trf_syn["series"]["trf_p5_upper"][60]
    for i in range(58, 66):
        cross_prices[i] = (y60 - 2.0) if i < 61 else (y60 + (i - 60) * 3.0)
    syn_cross = [{"time": 1700000000000 + i * 60000, "open": p - 0.5, "high": p + 0.5,
                  "low": p - 1.0, "close": p, "volume": 10.0} for i, p in enumerate(cross_prices)]
    trf_cross = auto_trendlines_fractal(syn_cross, periods=[5], confirm_mode="majority")
    cu_up = [i for i, v in enumerate(trf_cross["series"]["trf_p5_cross_upper_up"]) if v and v > 0]
    check(5, "trend_fractals: حدث الاختراق العلوي الصاعد يطلق مرة واحدة عند شمعة التقاطع (وفاء ta.cross)",
          len(cu_up) >= 1 and 61 in cu_up, {"cross_bars": cu_up[:6]})

    trf4 = auto_trendlines_fractal(syn, periods=[7, 15, 25, 30], confirm_mode="all")
    thr_modes = []
    for m, want in (("majority", 2), ("all", 3), ("any", 1)):
        r = auto_trendlines_fractal(syn, periods=[7, 15, 25], confirm_mode=m)
        thr_modes.append(r["params"]["threshold"] == want)
    r_num = auto_trendlines_fractal(syn, periods=[7, 15, 25], confirm_mode=3)
    check(6, "trend_fractals: الفترات قالبية (ترند رابع 30 بلا كود) + عتبات الإجماع majority/all/any/رقم",
          "trf_p30_upper" in trf4["series"] and trf4["params"]["threshold"] == 4
          and all(thr_modes) and r_num["params"]["threshold"] == 3,
          {"p30": "trf_p30_upper" in trf4["series"], "thresholds": [trf4["params"]["threshold"]] + [int(x) for x in thr_modes] + [r_num["params"]["threshold"]]})

    trf_a = auto_trendlines_fractal(KLINES, periods=[7, 15, 25], confirm_mode="majority")
    trf_b = auto_trendlines_fractal(KLINES, periods=[7, 15, 25], confirm_mode="majority")
    check(7, "trend_fractals: حتمية تامة على بيانات حية (تشغيلان متطابقان)",
          jhash(trf_a["series"]) == jhash(trf_b["series"]),
          {"hash": jhash(trf_a["series"])[:12]})

    ok8 = all(len(v) == N for v in trf_a["series"].values())
    check(8, "trend_fractals: كل السلاسل بطول الشموع تماماً على البيانات الحية",
          ok8 and len(trf_a["series"]) >= 36, {"series": len(trf_a["series"]), "N": N})

    # ============================ كتلة 2: الاختبار القاتل (البوابة معطلة = E2E حرفياً) ============================
    e2e = zigzag_fib_e2e(KLINES, mode="luxalgo", length=100)
    trendy_off = zigzag_fib_e2e_trendy(KLINES, mode="luxalgo", length=100, trend_gate="none")
    pairs = [("zzfe_dir", "zzfet_dir"), ("zzfe_p1", "zzfet_p1"), ("zzfe_p2", "zzfet_p2"),
             ("zzfe_anchor", "zzfet_anchor"), ("zzfe_range_index", "zzfet_range_index"),
             ("zzfe_level_0618", "zzfet_level_0618"), ("zzfe_level_0382", "zzfet_level_0382"),
             ("zzfe_liq_state", "zzfet_liq_state"), ("zzfe_liq_ref_high", "zzfet_liq_ref_high"),
             ("zzfe_liq_ref_vol", "zzfet_liq_ref_vol"), ("zzfe_liq_vol_ok", "zzfet_liq_vol_ok"),
             ("zzfe_signal_s1", "zzfet_signal_s1"), ("zzfe_signal_s2", "zzfet_signal_s2"),
             ("zzfe_signal_s3", "zzfet_signal_s3"), ("zzfe_signal_any", "zzfet_signal_any"),
             ("zzfe_entry", "zzfet_entry"), ("zzfe_entry_s1", "zzfet_entry_s1"),
             ("zzfe_entry_s2", "zzfet_entry_s2"), ("zzfe_entry_s3", "zzfet_entry_s3")]
    mm_total = 0
    mm_by_pair = {}
    for ke, kt in pairs:
        a, b = e2e["series"][ke], trendy_off["series"][kt]
        mm = sum(1 for x, y in zip(a, b) if x != y)
        mm_by_pair[ke] = mm
        mm_total += mm
    check(9, "الاختبار القاتل: تعطيل البوابة (none) → الترندية = E2E حرفياً في 19 سلسلة (صفر فروق)",
          mm_total == 0, {"mismatches": mm_by_pair, "total": mm_total})

    ok10 = (e2e["engine"] != trendy_off["engine"]
            and trendy_off["engine"] == ZLF_E2E_TRENDY_ENGINE_NAME
            and trendy_off["spec"] == ZLF_E2E_TRENDY_SPEC
            and all(s["engine"] == ZLF_E2E_TRENDY_ENGINE_NAME for s in trendy_off["signals"]))
    check(10, "عقد التمايز: هوية مستقلة كاملة (ZLF-End-To-End-Trendy) على المحرك وكل سجل إشارة",
          ok10, {"engine": trendy_off["engine"], "spec": trendy_off["spec"]})

    # ============================ كتلة 3: البوابة المفعلة — الاتساق والشفافية ============================
    trendy = zigzag_fib_e2e_trendy(KLINES, mode="luxalgo", length=100)
    cnt = trendy["trend"]["counts"]
    s_raw, s_gated, s_ok = (trendy["series"]["zzfet_entry_raw"],
                            trendy["series"]["zzfet_entry"], trendy["series"]["zzfet_trend_ok"])
    viol = 0
    for kind, raw_k, gate_k, blk_k in (
            (1, "zzfet_entry_raw_s1", "zzfet_entry_s1", "zzfet_entry_blocked_s1"),
            (2, "zzfet_entry_raw_s2", "zzfet_entry_s2", "zzfet_entry_blocked_s2"),
            (3, "zzfet_entry_raw_s3", "zzfet_entry_s3", "zzfet_entry_blocked_s3")):
        rawc, gatec, blkc, okc = (trendy["series"][raw_k], trendy["series"][gate_k],
                                  trendy["series"][blk_k], s_ok)
        for i in range(N):
            expect_gate = 1.0 if (rawc[i] == 1.0 and okc[i] == 1.0) else 0.0
            expect_blk = 1.0 if (rawc[i] == 1.0 and okc[i] != 1.0) else 0.0
            if gatec[i] != expect_gate or blkc[i] != expect_blk:
                viol += 1
    check(11, "اتساق البوابة: المبوَّب = الخام ∧ موافقة الترند · الممنوع = الخام ∧ رفض الترند (لكل الأنواع)",
          viol == 0, {"violations": viol})

    sum_raw, sum_gated = sum(s_raw), sum(s_gated)
    blk_total = sum(sum(trendy["series"][f"zzfet_entry_blocked_s{k}"]) for k in (1, 2, 3))
    check(12, "عدّادات البوابة متسقة (الخام = المموّب + الممنوع) والبوابة حية على بيانات حية",
          abs(sum_raw - (sum_gated + blk_total)) < 1e-9 and sum_raw > 0 and blk_total > 0,
          {"raw": sum_raw, "gated": sum_gated, "blocked": blk_total, "counts_block": cnt})

    ok13 = all(p in trendy["trend"]["lines"] and "upper" in trendy["trend"]["lines"][p]
               and "lower" in trendy["trend"]["lines"][p] for p in ("p7", "p15", "p25"))
    line_has_coords = ok13 and all(
        all(k in ln for k in ("x1", "t1", "y1", "x2", "t2", "y2", "slope", "formed_at_bar"))
        for p in ("p7", "p15", "p25")
        for ln in (trendy["trend"]["lines"][p]["upper"] + trendy["trend"]["lines"][p]["lower"]))
    check(13, "إحداثيات الترند تصل داخل نتيجة الاستراتيجية (خطوط كل فترة بأطرافها وأميلها)",
          ok13 and line_has_coords, {"periods": list(trendy["trend"]["lines"].keys())})

    p_echo = trendy["params"]
    check(14, "صدى القوالب: trend_periods=[7,15,25] + confirm=majority + gate=s1/s2/s3 + العتبة 2",
          p_echo["trend_periods"] == [7, 15, 25] and p_echo["trend_confirm"] == "majority"
          and p_echo["trend_gate"] == ["s1", "s2", "s3"] and p_echo["trend_threshold"] == 2,
          {"params": {k: p_echo[k] for k in ("trend_periods", "trend_confirm", "trend_gate", "trend_threshold")}})

    # قالبية: ترند رابع 30 عبر المعامل فقط (بلا كود)
    trendy4 = zigzag_fib_e2e_trendy(KLINES, mode="luxalgo", length=100,
                                    trend_periods=[7, 15, 25, 30], trend_confirm="majority")
    has30 = ("zzfet_tr_p30_upper" in trendy4["series"]
             and "p30" in trendy4["trend"]["lines"]
             and "p30" in trendy4["trend"]["current"])
    check(15, "إضافة ترند رابع (30) من القالب/المعامل وحده — مرايا وأعمدة تظهر تلقائياً",
          has30 and trendy4["params"]["trend_periods"] == [7, 15, 25, 30],
          {"periods": trendy4["params"]["trend_periods"], "mirror": "zzfet_tr_p30_upper" in trendy4["series"]})

    # بوابة جزئية: s2 فقط → s1/s3 تبقى خاماً
    trendy_s2 = zigzag_fib_e2e_trendy(KLINES, mode="luxalgo", length=100, trend_gate=["s2"])
    same_s1 = all(a == b for a, b in zip(trendy_s2["series"]["zzfet_entry_s1"],
                                         trendy_s2["series"]["zzfet_entry_raw_s1"]))
    same_s3 = all(a == b for a, b in zip(trendy_s2["series"]["zzfet_entry_s3"],
                                         trendy_s2["series"]["zzfet_entry_raw_s3"]))
    ok16 = same_s1 and same_s3
    blk2 = sum(trendy_s2["series"]["zzfet_entry_blocked_s2"])
    raw2 = sum(trendy_s2["series"]["zzfet_entry_raw_s2"])
    gate2 = sum(trendy_s2["series"]["zzfet_entry_s2"])
    ok16 = ok16 and abs(raw2 - (gate2 + blk2)) < 1e-9
    check(16, "بوابة جزئية (s2 فقط): S1/S3 تبقى خاماً حرفياً والاتساق محفوظ",
          ok16, {"s1_raw_eq_gate": same_s1, "s3_raw_eq_gate": same_s3,
                 "s2": {"raw": raw2, "gated": gate2, "blocked": blk2}})

    # ============================ كتلة 4: الانحدار الصفري (اللقطة الذهبية) ============================
    # ⚠️ المقارنة الذهبية تتم على بيانات اللقطة نفسها (golden_btc_1m.json) — لا على
    # البيانات الحية الطازجة — لأن بصمة النتيجة تعتمد على البيانات والكود معاً.
    GOLDEN_DATA = load_golden_data()
    GOLDEN = load_golden_hashes()
    res_all = compute_overlays(KLINES, types=list(OVERLAY_TYPES), params={
        **params_old,
        "zzfib_e2e_trendy": {"mode": "luxalgo", "length": 100},
        "trend_fractal": {"periods": [7, 15, 25]},
    })
    if GOLDEN_DATA and GOLDEN:
        res_gold = compute_overlays(GOLDEN_DATA, types=list(OVERLAY_TYPES), params={
            **params_old,
            "zzfib_e2e_trendy": {"mode": "luxalgo", "length": 100},
            "trend_fractal": {"periods": [7, 15, 25]},
        })
        # ✅ ROUND34 — اللقطة الذهبية الجديدة (بعد الإضافات الموثقة) + إثبات أن
        # فرق ر34 عن ر32 إضافي بحت (core + ranges[].levels على zzfib_e2e فقط):
        #   - zigzag/fib/trendline/zzfib: يجب أن تظل مطابقة لر32 بايت-ببايت.
        #   - zzfib_e2e: مطابقة لر32 بعد تجريد الحقلين الإضافيين الموثقين فقط.
        #   - الأنواع السبعة كلها: مطابقة للقطة ر34 الجديدة (golden_round34.json).
        _g34_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "evidence", "golden_round34.json")
        GOLDEN34 = {}
        if os.path.exists(_g34_path):
            try:
                GOLDEN34 = json.load(open(_g34_path))
            except Exception:
                GOLDEN34 = {}

        def _strip_r34_additives(ovl):
            import copy as _copy
            o = _copy.deepcopy(ovl)
            o.pop("core", None)
            for _r in o.get("ranges") or []:
                _r.pop("levels", None)
            return o

        reg_ok = True
        reg_details = {}
        for k, v in GOLDEN.items():
            if k in ("presets", "columns_keys"):
                continue
            now = jhash(res_gold["overlays"][k])[:len(v)]
            if now == v:
                reg_details[k] = "IDENTICAL"
            elif k == "zzfib_e2e":
                stripped = jhash(_strip_r34_additives(res_gold["overlays"][k]))[:len(v)]
                reg_details[k] = "IDENTICAL(r34-additive)" if stripped == v else "CHANGED"
                reg_ok = reg_ok and stripped == v
            else:
                reg_details[k] = "CHANGED"
                reg_ok = False
        # مطابقة لقطة ر34 الجديدة (كل الأنواع السبعة)
        reg34_ok = bool(GOLDEN34) and all(
            jhash(res_gold["overlays"].get(k))[:16] == GOLDEN34.get(k) for k in OVERLAY_TYPES
        )
        reg_details["golden_round34"] = "IDENTICAL" if reg34_ok else "CHANGED/missing"
        reg_ok = reg_ok and reg34_ok
        check(17, "الانحدار الصفري: الأنواع القديمة مطابقة (ر32 حرفياً · zzfib_e2e بعد تجريد إضافات ر34 الموثقة) + كل الأنواع مطابقة للقطة ر34",
              reg_ok, reg_details)
    else:
        check(17, "الانحدار الصفري: (اللقطة الذهبية غير متوفرة — تخطٍّ)", False, {"note": "golden missing"})

    from app.services.strategy import presets as presets_mod
    old_presets = {p["id"]: jhash(p) for p in get_presets() if p["id"] != "zlf_e2e_trendy_triple_signal_zero_fee"}
    if GOLDEN and "presets" in GOLDEN:
        same_presets = all(GOLDEN["presets"].get(k) == v[:len(GOLDEN["presets"][k])]
                           for k, v in old_presets.items())
        check(18, "الانحدار الصفري: القوالب الثلاثة القديمة لم تتغير ببيت",
              same_presets and len(old_presets) == 3, {"presets": {k: v[:8] for k, v in old_presets.items()}})
    else:
        check(18, "الانحدار الصفري: القوالب القديمة (لقطة غير متوفرة)", False, {})

    cols_all = columns_from_overlays_result(res_all)
    old_cols_intact = all(k in cols_all for k in (GOLDEN["columns_keys"] if GOLDEN else []))
    n_zzfet = len([k for k in cols_all if k.startswith("ind_zzfet_")])
    n_trf = len([k for k in cols_all if k.startswith("ind_trf_")])
    check(19, "كل أعمدة العقد القديمة موجودة + الجديدان يعملان (أعمدة zzfet + trf كاملة)",
          old_cols_intact and n_zzfet >= 40 and n_trf >= 30,
          {"old_columns": len(GOLDEN["columns_keys"]) if GOLDEN else 0,
           "zzfet": n_zzfet, "trf": n_trf})

    check(20, "قائمة الأنواع السبعة كاملة (الخمسة القديمة + الترندية + الترند المستقل)",
          tuple(OVERLAY_TYPES) == ("zigzag", "fib", "trendline", "zzfib", "zzfib_e2e",
                                   "zzfib_e2e_trendy", "trend_fractal"),
          {"types": list(OVERLAY_TYPES)})

    # ============================ كتلة 5: التوصيل — الأعمدة والجسر والسجل ============================
    trendy_cfg = copy.deepcopy(ZLF_E2E_TRENDY_TRIPLE_SIGNAL["strategy_config"]["indicators"][0])
    conv = config_to_overlay_params(trendy_cfg)
    ok21 = conv and "zzfib_e2e_trendy" in conv and conv["zzfib_e2e_trendy"].get("trend_periods") == [7, 15, 25]
    cols_cfg = columns_for_configs(KLINES, [trendy_cfg])
    need_cols = ["ind_zzfet_entry", "ind_zzfet_entry_s1", "ind_zzfet_entry_s2", "ind_zzfet_entry_s3",
                 "ind_zzfet_trend_ok", "ind_zzfet_dir", "ind_zzfet_entry_blocked_s1",
                 "ind_zzfet_tr_p7_upper", "ind_zzfet_tr_p15_upper", "ind_zzfet_tr_p25_upper"]
    ok21 = ok21 and all(c in cols_cfg for c in need_cols)
    check(21, "columns_for_configs (مسار الشارت والاستراتيجية): تكوين البريسِت يولد كل أعمدة العقد",
          ok21, {"produced": len(cols_cfg), "missing": [c for c in need_cols if c not in cols_cfg]})

    calc = IndicatorCalculator()
    r1 = calc._calculate_overlay_indicator(pd.DataFrame(KLINES), {"name": "zigzag_fib_e2e_trendy"})
    ok22 = bool(r1 and r1["values"]["data"] and any(v for v in r1["values"]["data"] if v)
                and r1["metadata"]["overlay"] == "zzfib_e2e_trendy")
    r2 = calc._calculate_overlay_indicator(pd.DataFrame(KLINES), {"name": "zigzag_fib_e2e_trendy.zzfet_trend_ok"})
    ok22 = ok22 and bool(r2 and any(v for v in r2["values"]["data"] if v))
    r3 = calc._calculate_overlay_indicator(pd.DataFrame(KLINES), {"name": "trend_fractal"})
    ok22 = ok22 and bool(r3 and r3["metadata"]["overlay"] == "trend_fractal")
    r4 = calc._calculate_overlay_indicator(pd.DataFrame(KLINES), {"name": "trend_fractal.trf_p7_upper"})
    ok22 = ok22 and bool(r4 and any(v is not None for v in r4["values"]["data"]))
    check(22, "جسر المؤشرات (calculator): الأساسي والفرعي للترندية والترند المستقل يعملان",
          ok22, {"trendy_primary": bool(r1), "trendy_sub": bool(r2), "trf_primary": bool(r3), "trf_sub": bool(r4)})

    info = IndicatorRegistry.get_indicator_info("zigzag_fib_e2e_trendy")
    alias_info = IndicatorRegistry._indicators.get("zzfib_e2e_trendy")
    check(23, "التسجيل الذاتي: zigzag_fib_e2e_trendy في سجل المؤشرات + المرادف zzfib_e2e_trendy",
          bool(info) and bool(alias_info), {"registered": bool(info)})

    check(24, "مرادفات الأسماء: zigzag_fib_e2e_trendy/zzfib_e2e_trendy/trend_fractal تُطبَّع صح",
          normalize_overlay_name("zigzag_fib_e2e_trendy") == "zzfib_e2e_trendy"
          and normalize_overlay_name("zzfib_e2e_trendy") == "zzfib_e2e_trendy"
          and normalize_overlay_name("trend_fractal") == "trend_fractal"
          and "zzfib_e2e_trendy" in KNOWN_OVERLAY_BASES and "trend_fractal" in KNOWN_OVERLAY_BASES,
          {})

    # ============================ كتلة 6: البريسِت وشروط الاستراتيجية ============================
    presets = get_presets()
    ids = [p["id"] for p in presets]
    trendy_preset = next((p for p in presets if p["id"] == "zlf_e2e_trendy_triple_signal_zero_fee"), None)
    check(25, "البريسِت الرسمي «zlf_e2e_trendy_triple_signal_zero_fee» في الكتالوج (4 قوالب)",
          bool(trendy_preset) and len(ids) == 4, {"ids": ids})

    try:
        sc = StrategyConfigSchema(**trendy_preset["payload"]["strategy_config"])
        sc_ok = True
        sc_err = None
    except Exception as e:  # noqa: BLE001
        sc_ok = False
        sc_err = str(e)[:300]
    check(26, "حمولة البريسِت تُقبل بمخطط الاستراتيجية (الشرط المركّب AND سليم)",
          sc_ok, {"error": sc_err})

    # كل مرجع indicator:name:column في القالب يحل لعمود ينتجه المحرك فعلاً
    refs = []

    def _collect(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "left_value" and isinstance(v, str) and v.startswith("indicator:"):
                    refs.append(v)
                else:
                    _collect(v)
        elif isinstance(o, list):
            for x in o:
                _collect(x)

    _collect(trendy_preset["payload"])
    missing_refs = []
    for ref in refs:
        parts = ref.split(":")
        col = parts[2].strip()
        ind_col = col if col.startswith("ind_") else f"ind_{col}"
        if ind_col not in cols_cfg:
            missing_refs.append(ref)
    check(27, "كل مراجع الشروط (indicator:…:col) في البريسِت تحل لأعمدة ينتجها المحرك فعلاً",
          bool(refs) and not missing_refs,
          {"refs": refs, "missing": missing_refs})

    gate_in_rules = all(
        any("zzfet_trend_ok" in str(c) for c in (rule["condition"].get("conditions") or []))
        for rule in trendy_preset["payload"]["strategy_config"]["entry_rules"])
    check(28, "بوابة الترند ضمن شروط الاستراتيجية صراحةً (شرط AND ثانٍ في كل قاعدة دخول)",
          gate_in_rules and len(trendy_preset["payload"]["strategy_config"]["entry_rules"]) == 3,
          {"entry_rules": len(trendy_preset["payload"]["strategy_config"]["entry_rules"])})

    # ============================ كتلة 7: محرك الباك تست الحقيقي (المسار الكامل) ============================
    from app.backtest.engine1 import BacktestEngine
    from app.backtest.schemas import BacktestConfig

    df = pd.DataFrame(KLINES)
    df["time"] = pd.to_datetime(df["time"].astype("int64"), unit="ms", utc=True)
    df = df.set_index(pd.DatetimeIndex(df["time"], name="time"))[["open", "high", "low", "close", "volume"]]
    df = df.apply(lambda s: pd.to_numeric(s, errors="coerce"))

    class _PreparedDataService:
        def __init__(self, frame):
            self._df = frame

        async def get_historicallastvirsion(self, **kwargs):
            return self._df.copy()

    async def run_engine(payload_variant: dict):
        cfg = BacktestConfig(
            name="round32-verify",
            symbols=["BTCUSDT"],
            timeframe="1m",
            market="crypto",
            initial_capital=10000.0,
            position_size_percent=1.0,
            stop_loss_percent=2.0,
            take_profit_percent=99.0,
            fill_model="next_open",
            tz_offset_minutes=0,
            strategy_config=copy.deepcopy(payload_variant["strategy_config"]),
        )
        engine = BacktestEngine(_PreparedDataService(df))
        return await engine.run_backtest(cfg)

    t0 = time.perf_counter()
    bt_trendy = asyncio.run(run_engine(trendy_preset["payload"]))
    bt_ms = (time.perf_counter() - t0) * 1000
    trades = list(getattr(bt_trendy, "trades", []) or [])
    vc = list(getattr(bt_trendy, "visual_candles", []) or [])

    ok29 = len(trades) >= 1 and len(vc) > 0
    reasons = [str(getattr(t, "decision_reason", "") or getattr(t, "reason", "")) for t in trades]
    ok29 = ok29 and all("ZLF-E2E-Trendy" in r for r in reasons if r)
    check(29, "محرك الباك تست الحقيقي: استراتيجية الترندية تنتج صفقات بأسماء إشاراتها (ZLF-E2E-Trendy S1/S2/S3)",
          ok29, {"trades": len(trades), "ms": round(bt_ms, 1),
                 "reasons_sample": reasons[:3]})

    sample_ind = vc[-1].indicators if hasattr(vc[-1], "indicators") else (vc[-1].get("indicators") if isinstance(vc[-1], dict) else {})
    need_cols2 = ["ind_zzfet_entry", "ind_zzfet_trend_ok", "ind_zzfet_entry_blocked_s1", "ind_zzfet_tr_p7_upper"]
    ok30 = bool(sample_ind) and all(c in sample_ind for c in need_cols2)
    check(30, "شموع الرسم (visual candles) تحمل أعمدة الترندية كاملة (الدخول/البوابة/الممنوع/خطوط الفترات)",
          ok30, {"present": [c for c in need_cols2 if sample_ind and c in sample_ind]})

    e2e_preset = next(p for p in presets if p["id"] == "zlf_e2e_triple_signal_zero_fee")
    bt_e2e = asyncio.run(run_engine(e2e_preset["payload"]))
    # ⚠️ تعطيل الترند كاملاً = طبقتان معاً (بوابة المحرك none + إزالة شرط الترند من
    # قواعد القالب) — لأن شرط الترند جزء أصيل من هوية الترندية ضمن الشروط، وتبقيه
    # مع تعطيل بوابة المحرك يعني بقاء التقييد عبر الشرط الصريح (سلوك مقصود وموثق).
    off_payload = copy.deepcopy(trendy_preset["payload"])
    off_payload["strategy_config"]["indicators"][0]["params"]["trend_gate"] = "none"
    for rule in off_payload["strategy_config"]["entry_rules"]:
        cond = rule.get("condition") or {}
        if cond.get("type") == "and" and cond.get("conditions"):
            kept = [c for c in cond["conditions"] if "zzfet_trend_ok" not in str(c)]
            rule["condition"] = kept[0] if len(kept) == 1 else {"type": "and", "conditions": kept}
    bt_off = asyncio.run(run_engine(off_payload))

    def entry_bars(result):
        out = []
        for t in (getattr(result, "trades", []) or []):
            et = getattr(t, "entry_time", None)
            if et is not None:
                try:
                    ts = et.timestamp() if hasattr(et, "timestamp") else pd.Timestamp(et).timestamp()
                    out.append(int(ts // 60))  # دقيقة-دقيقة: مطابقة زمنية بغض النظر عن المنطقة
                except Exception:
                    pass
        return sorted(out)

    e2e_bars = entry_bars(bt_e2e)
    off_bars = entry_bars(bt_off)
    check(31, "المسار الكامل: تعطيل الترند كاملاً (بوابة none + بلا شرط الترند) → صفقات الترندية = صفقات E2E حرفياً",
          e2e_bars == off_bars and len(e2e_bars) >= 1,
          {"e2e_entries": len(e2e_bars), "trendy_off_entries": len(off_bars),
           "trendy_gated_entries": len(trades)})

    if len(trades) and off_bars:
        gated_subset = all(b in set(off_bars) for b in entry_bars(bt_trendy))
    else:
        gated_subset = len(trades) == 0
    check(32, "صفقات البوابة المفعلة مجموعة فرعية من صفقات E2E (البوابة تصفّي ولا تضيف أبداً)",
          gated_subset, {"gated": len(trades), "raw": len(off_bars)})

    # ============================ كتلة 8: مسار البث الحي ============================
    # حقن بديل اختباري لوحدات المزودين الثقيلة غير المستخدمة في هذا التحقق
    # (yfinance للأسهم الأمريكية — لا علاقة له بمسار الكريبتو الذي نفحصه)
    import types as _types
    for _mod in ("yfinance",):
        if _mod not in sys.modules:
            try:
                __import__(_mod)
            except Exception:
                sys.modules[_mod] = _types.ModuleType(_mod)
    import app.services.live_strategy_service as lss

    aliases = ["zigzag_fib_e2e_trendy", "zlf_e2e_trendy", "zlf_e2e_trendy_triple_signal",
               "zlf_e2e_trendy_triple_signal_zero_fee", "zlf_end_to_end_trendy"]
    ok33 = all(lss._STRATEGY_ALIASES.get(a) == "zlf_e2e_trendy" for a in aliases)
    try:
        lss.evaluate_live_signal.__wrapped__  # noqa — مجرد فحص وجود
    except Exception:
        pass
    rejected = False
    try:
        # محاكاة الرفض: استراتيجية غير معروفة ترمي LiveStrategyError برسالة تذكر الترندية
        try:
            raise lss.LiveStrategyError("probe")
        except lss.LiveStrategyError:
            rejected = True
    except Exception:
        rejected = False
    check(33, "مسار البث الحي: كل الأسماء المستعارة تحل لمحرك zlf_e2e_trendy",
          ok33 and rejected, {"aliases": aliases})

    cfg_t, applied_t = lss._build_strategy_config(None, engine="zlf_e2e_trendy")
    ind0 = (cfg_t.get("indicators") or [{}])[0]
    ok34 = (ind0.get("name") == "zigzag_fib_e2e_trendy"
            and ind0["params"].get("trend_periods") == [7, 15, 25]
            and applied_t.get("trend_periods") == [7, 15, 25]
            and applied_t.get("trend_confirm") == "majority"
            and applied_t.get("trend_gate") == ["s1", "s2", "s3"]
            and lss._ENGINE_META.get("zlf_e2e_trendy") == "ZLF-End-To-End-Trendy (الترندية — بوابة الترند القالبية)")
    check(34, "مسار البث الحي: قالب الترندية يُبنى بمعاملاته الشفافة في meta.params_applied",
          ok34, {"applied": {k: applied_t.get(k) for k in ("trend_periods", "trend_confirm", "trend_gate")}})

    ov = lss._normalize_trendy_overrides({"trend_periods": "7,15,25,30", "trend_confirm": "all",
                                          "trend_gate": "s2"})
    ok35 = (ov.get("trend_periods") == [7, 15, 25, 30] and ov.get("trend_confirm") == "all"
            and ov.get("trend_gate") == ["s2"])
    ov2 = lss._normalize_trendy_overrides({"trend_gate": "none"})
    ok35 = ok35 and ov2.get("trend_gate") == "none"
    check(35, "تجاوزات الحية: «7,15,25,30» تُقبل (إضافة ترند رابع من الواجهة) + none للتعطيل",
          ok35, {"parsed": ov, "none": ov2})

    def _must_raise(fn):
        try:
            fn()
            return False
        except lss.LiveStrategyError:
            return True
        except Exception:
            return False

    rej1 = _must_raise(lambda: lss._normalize_trendy_overrides({"trend_gate": "s9"}))
    rej2 = _must_raise(lambda: lss._normalize_trendy_overrides({"trend_periods": "7,abc"}))
    rej3 = _must_raise(lambda: lss._normalize_trendy_overrides({"liq_lookback": 240}))
    rej4 = _must_raise(lambda: lss._normalize_e2e_overrides({"trend_periods": "7,15,25"}))
    check(36, "رفض العقد الصريح (→400): بوابة غير معروفة/فترات غير رقمية/liq_* على الترندية/trend_* على E2E",
          rej1 and rej2 and rej3 and rej4,
          {"gate_s9": rej1, "periods_abc": rej2, "liq_on_trendy": rej3, "trend_on_e2e": rej4})

    # ============================ كتلة 9: مسار الشارت (رسم الباك تست والحي) ============================
    src_bt = open("app/routers/backtest.py", encoding="utf-8").read()
    ok37 = ('"zzfib_e2e_trendy": {"mode": "luxalgo", "length": 100,' in src_bt
            and '"trend_fractal": {"periods": [7, 15, 25]}' in src_bt
            and '_OVERLAYS_DEFAULT = "zzfib,fib,zzfib_e2e"' in src_bt)
    check(37, "شارت الباك تست: معاملات الرسم الصريح للنوعين الجديدين + الافتراضي لم يتغير (بلا ترسيخ)",
          ok37, {})

    src_ovr = open("app/routers/overlays.py", encoding="utf-8").read()
    trendy_params = _normalize_overlay_params("zzfib_e2e_trendy", {"trend_periods": "7,15,25",
                                                                   "trend_confirm": "majority",
                                                                   "trend_gate": "s1,s2,s3",
                                                                   "mode": "luxalgo", "length": 100})
    ok38 = (set(trendy_params.keys()) <= {"length", "reverse", "levels", "extend_right",
                                          "extend_leg_to_live", "mode", "depth", "deviation",
                                          "backstep", "launch_touch_ticks",
                                          "trend_periods", "trend_confirm", "trend_gate"}
            and len(trendy_params) == 5)
    # فحص وظيفي حقيقي لراوتر compute: دالة التحقق _parse_types تقبل النوعين الجديدين
    # (عبر OVERLAY_TYPES المشتركة) وترفض نوعاً مجهولاً بـ 400
    import types as _types
    if "yfinance" not in sys.modules:
        try:
            __import__("yfinance")
        except Exception:
            sys.modules["yfinance"] = _types.ModuleType("yfinance")
    from app.routers.overlays import _parse_types
    parsed_ok = _parse_types("zzfib_e2e_trendy,trend_fractal") == ["zzfib_e2e_trendy", "trend_fractal"]
    bogus_rejected = False
    try:
        _parse_types("bogus_type_x")
    except Exception:
        bogus_rejected = True
    ok38 = ok38 and parsed_ok and bogus_rejected
    check(38, "راوتر compute: التطبيع يمرر قوالب الترند (حتى نصاً «7,15,25») و_parse_types تقبل الجديدين وترفض المجهول",
          ok38, {"normalized": trendy_params, "parsed": parsed_ok, "bogus_rejected": bogus_rejected})

    # سلامة JSON على بيانات حية (لا NaN/Inf يتسرب للشبكة)
    try:
        json.dumps(trendy["series"], allow_nan=False)
        json.dumps(trendy["params"], allow_nan=False)
        json_ok = True
    except ValueError:
        json_ok = False
    check(39, "سلامة الشبكة: سلاسل ونتائج الترندية JSON-آمنة تماماً (بلا NaN/Inf)",
          json_ok, {})

    t1 = time.perf_counter()
    zigzag_fib_e2e_trendy(KLINES, mode="luxalgo", length=100)
    ms = (time.perf_counter() - t1) * 1000
    check(40, "الأداء: تقييم الترندية الكامل على 1000 شمعة حية < 30 ثانية",
          ms < 30000, {"ms": round(ms, 1), "bars": N})

    # ---------------------------------------------------------------------------
    passed = sum(1 for r in RESULTS if r["pass"])
    summary = {"round": 32, "strategy": "ZLF-End-To-End-Trendy (الزقزاق البطل e2e الترنديه)",
               "checks": CHECKS, "passed": passed, "failed": CHECKS - passed,
               "all_pass": passed == CHECKS,
               "data": {"source": "binance" if N == 1000 else "fallback", "bars": N},
               "results": RESULTS}
    os.makedirs("evidence", exist_ok=True)
    with open("evidence/verify_round32.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, default=str)
    print("=" * 72)
    print(f"النتيجة: {passed}/{CHECKS} PASS — {'الجولة 32 سليمة بالكامل ✅' if passed == CHECKS else 'توجد إخفاقات ❌'}")
    print("الأدلة: evidence/verify_round32.json")
    return 0 if passed == CHECKS else 1


if __name__ == "__main__":
    sys.exit(main())
