#!/usr/bin/env python3
"""R76 — بطارية التحقق الموسعة لمسار chart-data في راوتر الباك-تست (B-2/B-3/B-6/B-7).

تختبر الرقعة الكبرى كما تُشغّل فعلاً: مساعدات الراوتر تُستخلص من مصدره
المرقّع نفسه (لا نسخ يدوية — ما يُختبر هو حرفياً ما يُنشَر) وتُشغَّل بمحاكاة
الكاش/المزوّد، ثم تُختبر النواة والمحركات بالعقد الجديد، ثم رقع B-1 في
market_data/dataframe_utils/Timeframe/overlays. لا celery ولا fastapi
مطلوبة — المساعدات نقية والاستيرادات الداخلية تُحقن.

الفحوص (37):
  C1-C6   (B-3) قالب strategy_config.indicators: العائلات/التعطيل/التشوّه/الاحترام بالمحرك.
  C7-C12  (B-2) _get_or_build_osc_base: ميتاداتا ناقصة/حارس 2M/مسار سليم/كاش/فشل الجلب/نافذة فاسدة.
  C13-C19 (B-2/B-6/B-7/B-8) نمط view: base_tf صادق (خطوة 34 دقيقة!) · bars/full_bars · view_times مضمّنة ·
          crosses للماكد فقط بمقاييس العرض · العينات == الدقة الكاملة.
  C20-C24 (B-1) مسار الثواني: 1s → 5s/15s/30s متاحة وقيمها من التجميع الصاعد · base_tf=1s.
  C25-C30 (B-1) market_data/_tf_span_ms/_tf_to_minutes/align_time_ms/تعداد Timeframe.
  C31-C34 (B-1) ريجكسات REST الخمسة تقبل الثواني · _SECONDS_DAYS_CAP وسلوك القصّ.
  C35-C37 (B-4/B-5/حارس الذاكرة) إشارة MACD=SMA 100/100 · أكواد التحذيرات · حارس 50K في الخدمة.
"""
from __future__ import annotations

import asyncio
import re
import sys
import types
import json
import inspect
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

R76 = "/home/z/my-project/r76-workspace/files/app"
sys.path.insert(0, "/home/z/my-project/r67-workspace/src")

from app.services.indicators.mtf_oscillator_core import (  # noqa: E402
    TF_MS, build_osc_section,
)
from app.services.indicators.overlays_zlf_e2e_trendy_macd import (  # noqa: E402
    zigzag_fib_e2e_trendy_macd,
)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗ فشل'} {name}" + (f" — {detail}" if detail else ""))


def nl(title: str):
    print(f"\n=== {title} ===")


# ─── استخلاص مساعدات الراوتر من المصدر المرقّع نفسه ────────────────────────
BACKTEST_SRC = open(f"{R76}/routers/backtest.py", encoding="utf-8").read()


def extract_def(src: str, name: str) -> str:
    """يستخرج نص دالة top-level (مع تعليقاتها الخلفية) من مصدر الراوتر."""
    lines = src.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines)
                  if ln.startswith(f"def {name}(") or ln.startswith(f"async def {name}(")), None)
    if start is None:
        raise AssertionError(f"المساعد {name} غير موجود في المصدر")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j]
        if s.startswith("def ") or s.startswith("async def ") or s.startswith("@router") or s.startswith("class "):
            end = j
            break
    return "".join(lines[start:end])


class _Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass


_cache_store: Dict[str, Any] = {}
_ns_base = {"Dict": Dict, "Any": Any, "Optional": Optional, "List": List,
            "logger": _Log(), "asyncio": asyncio, "re": re, "json": json,
            "_bt_cache_get": _cache_store.get,
            "_bt_cache_put": lambda k, v: _cache_store.__setitem__(k, v)}

exec(compile(extract_def(BACKTEST_SRC, "_strategy_osc_params"), "<r76>", "exec"), _ns_base)
_strategy_osc_params = _ns_base["_strategy_osc_params"]

_R76_OSC_BASE_MAX_BARS = int(re.search(
    r"_R76_OSC_BASE_MAX_BARS = ([\d_]+)", BACKTEST_SRC).group(1).replace("_", ""))
_R76_FAMILY_OF_INDICATOR = eval(re.search(
    r"_R76_FAMILY_OF_INDICATOR = (\{[^}]*\})", BACKTEST_SRC, re.S).group(1))
_ns_base.update(_R76_OSC_BASE_MAX_BARS=_R76_OSC_BASE_MAX_BARS,
                _R76_FAMILY_OF_INDICATOR=_R76_FAMILY_OF_INDICATOR,
                AsyncSession=None)  # توقيع الراوتر — يُحاكى بلا fastapi
exec(compile(extract_def(BACKTEST_SRC, "_get_or_build_osc_base"), "<r76>", "exec"), _ns_base)
_get_or_build_osc_base = _ns_base["_get_or_build_osc_base"]

_fetch_calls = {"n": 0}


class _FakeDataServiceOk:
    def __init__(self, *_a, **_k): pass

    async def get_historical_last_version(self, **_k):
        _fetch_calls["n"] += 1
        n = 500
        t = pd.Series(np.arange(n, dtype=np.int64) * 60_000 + 1_700_000_000_000)
        return pd.DataFrame({"time": t, "close": 100.0 + np.cumsum(
            np.random.default_rng(1).normal(0, 0.1, n))})


class _FakeDataServiceFail:
    def __init__(self, *_a, **_k): pass

    async def get_historical_last_version(self, **_k):
        _fetch_calls["n"] += 1
        raise RuntimeError("provider down")


def _install_ds(cls):
    mod = types.ModuleType("app.services.data_service")
    mod.DataService = cls
    sys.modules["app.services.data_service"] = mod


_MD = {"symbol": "SOLUSDT", "timeframe": "1m",
       "start_date": "2026-06-01T00:00:00+00:00", "end_date": "2026-06-01T08:20:00+00:00"}
_FC = {"market": "crypto", "strategy_config": {"indicators": [
    {"name": "zigzag_fib_e2e_trendy_macd", "enabled": True,
     "params": {"length": 40, "osc_instances": [
         {"kind": "macd", "id": "m1", "timeframe": "1m", "fast": 6, "slow": 13, "signal": 4}]}}
]}}


def main() -> int:
    nl("C1-C6 — B-3: قالب strategy_config.indicators (_strategy_osc_params)")
    check("C1 بلا قالب ⇒ قيم فارغة", _strategy_osc_params(None) == {}
          and _strategy_osc_params({}) == {} and _strategy_osc_params({"strategy_config": {}}) == {})
    tpl = _strategy_osc_params(_FC)
    check("C2 عائلة الترندية الماكدية تُستخرج بحرفية قالبها",
          tpl == {"zzfib_e2e_trendy_macd": _FC["strategy_config"]["indicators"][0]["params"]})
    fc_b = {"strategy_config": {"indicators": [
        {"name": "zigzag_fib_e2e_blazing_macd", "enabled": True,
         "params": {"osc_instances": [{"kind": "rsi", "id": "r1", "timeframe": "1m", "period": 14}]}}]}}
    check("C3 عائلة الملتهبة الماكدية كذلك",
          set(_strategy_osc_params(fc_b)) == {"zzfib_e2e_blazing_macd"})
    fc_dis = {"strategy_config": {"indicators": [
        {"name": "zigzag_fib_e2e_trendy_macd", "enabled": False, "params": {"length": 9}}]}}
    check("C4 المؤشر المعطَّل يُتجاهل (لم يُحسب أصلاً)", _strategy_osc_params(fc_dis) == {})
    check("C5 قالب مشوّه لا يفجّر المسار (بلا استثناء)", _strategy_osc_params(
        {"strategy_config": {"indicators": "ليس قائمة"}}) == {} and _strategy_osc_params(
        {"strategy_config": {"indicators": [{"params": 5}]}}) == {})
    # احترام المحرك للقالب: 6 نسخ مخلوطة ⇒ 14 سلسلة (3 ماكد + 2 رسي + 1 مو = 9+8+2 … )
    mixed6 = [
        {"kind": "macd", "id": "m1", "timeframe": "1m", "fast": 6, "slow": 13, "signal": 4},
        {"kind": "macd", "id": "m2", "timeframe": "1m", "fast": 12, "slow": 26, "signal": 9},
        {"kind": "macd", "id": "m3", "timeframe": "1m", "fast": 8, "slow": 21, "signal": 5},
        {"kind": "rsi", "id": "r1", "timeframe": "1m", "period": 14, "ma_length": 14, "bb_std": 2},
        {"kind": "rsi", "id": "r2", "timeframe": "1m", "period": 7, "ma_length": 7, "bb_std": 2},
        {"kind": "mom", "id": "o1", "timeframe": "1m", "length": 10},
    ]
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
    res6 = zigzag_fib_e2e_trendy_macd(full_candles, length=40, osc_instances=mixed6)
    n_series6 = len([k for k in res6["series"] if "_osc_" in k and not k.endswith("_osc_gate")])
    check("C6 المحرك يحترم القالب: 6 نسخ ⇒ 19 سلسلة موشرات (لا 67)",
          n_series6 == 3 * 3 + 2 * 4 + 1 * 2 and len(res6["osc"]["instances"]) == 6,
          f"series={n_series6} instances={len(res6['osc']['instances'])}")

    nl("C7-C12 — B-2: _get_or_build_osc_base (حارس/كاش/سقوط آمن)")
    _cache_store.clear(); _fetch_calls["n"] = 0
    _install_ds(_FakeDataServiceOk)
    r = asyncio.run(_get_or_build_osc_base(None, "bt1", {"symbol": "SOLUSDT"}, {}))
    check("C7 ميتاداتا ناقصة ⇒ None بلا جلب", r is None and _fetch_calls["n"] == 0)
    md_huge = dict(_MD, start_date="1700-01-01T00:00:00+00:00")
    r = asyncio.run(_get_or_build_osc_base(None, "bt2", md_huge, _FC))
    check("C8 حارس 2M شمعة ⇒ تخطٍ صريح بلا جلب", r is None and _fetch_calls["n"] == 0)
    r = asyncio.run(_get_or_build_osc_base(None, "bt3", _MD, _FC))
    check("C9 مسار سليم ⇒ بنية مضغوطة {time_ms, close, tf, bars}",
          isinstance(r, dict) and isinstance(r.get("time_ms"), list) and isinstance(r.get("close"), list)
          and r["tf"] == "1m" and r["bars"] == 500 and len(r["time_ms"]) == 500)
    r2 = asyncio.run(_get_or_build_osc_base(None, "bt3", _MD, _FC))
    check("C10 كاش لكل backtest_id — الجلب الثاني دون مزوّد",
          r2 is not None and _fetch_calls["n"] == 1)
    _cache_store.clear(); _fetch_calls["n"] = 0
    _install_ds(_FakeDataServiceFail)
    r = asyncio.run(_get_or_build_osc_base(None, "bt4", _MD, _FC))
    check("C11 فشل المزوّد ⇒ None (fallback فوق العرض المخزن — لا فشل مسار)",
          r is None and _fetch_calls["n"] == 1)
    md_bad = dict(_MD, start_date="ليس تاريخاً", end_date="كذلك")
    r = asyncio.run(_get_or_build_osc_base(None, "bt5", md_bad, _FC))
    check("C12 نافذة غير قابلة للتحليل ⇒ None", r is None)
    _install_ds(_FakeDataServiceOk)

    nl("C13-C19 — B-2/B-6/B-7/B-8: نمط view بصدق الدقة الكاملة")
    # العرض المضغوط: خطوة 34 دقيقة — كانت النواة القديمة تكتشف 2040000ms
    # زوراً كقاعدة؛ الآن osc_base بالدقة الكاملة 1m ⇒ base_tf=1m الصادق.
    n_full = len(full_candles)  # 600 شمعة 1m كاملة الدقة
    t0 = 1777593540000
    osc_base = {"time_ms": [c["time"] for c in full_candles],
                "close": [float(c["close"]) for c in full_candles],
                "tf": "1m", "bars": n_full}
    view_times = [full_candles[i * 34]["time"] for i in range(n_full // 34)]  # خطوة 34 دقيقة
    view_candles = [full_candles[i * 34] for i in range(len(view_times))]  # شموع العرض (كما flat_candles)
    res_v = zigzag_fib_e2e_trendy_macd(
        view_candles, length=40,
        osc_instances=[{"kind": "macd", "id": "m1", "timeframe": "1m", "fast": 6, "slow": 13, "signal": 4}],
        osc_base=osc_base, view_times=view_times, osc_series="view",
    )
    sec = res_v["osc"]
    check("C13 base_tf = 1m الصادق من الدقة الكاملة (لا 2040000ms من خطوة 34د)",
          sec["base_tf"] == "1m" and sec.get("base_tf_ms") == 60_000,
          f"base_tf={sec['base_tf']} ms={sec.get('base_tf_ms')}")
    check("C14 bars = أعمدة العرض فقط (B-8)", sec["bars"] == len(view_times),
          f"{sec['bars']} vs {len(view_times)}")
    check("C15 full_bars = الدقة الكاملة", sec.get("full_bars") == n_full)
    check("C16 view_times مضمّنة داخل القسم (B-6)", sec.get("view_times") == view_times)
    check("C17 view_sampled=True", sec.get("view_sampled") is True)
    crs = sec.get("crosses", {}).get("m1")
    check("C18 crosses للماكد فقط [{index, up}] بمقاييس العرض (B-7)",
          isinstance(crs, list) and all(isinstance(x.get("index"), int) and isinstance(x.get("up"), bool)
                                       and 0 <= x["index"] < len(view_times) for x in crs)
          and set(sec.get("crosses", {})) == {"m1"}, f"count={len(crs) if isinstance(crs, list) else '∅'}")
    # العينات عند أعمدة العرض == قيم الدقة الكاملة عند نفس الفهرس
    full = build_osc_section(osc_base, base_timeframe="1m", prefix="zzfetm",
                             osc_instances=[{"kind": "macd", "id": "m1", "timeframe": "1m",
                                             "fast": 6, "slow": 13, "signal": 4}])
    lv = res_v["series"]["zzfetm_osc_m1_line"]
    lf = full["series"]["zzfetm_osc_m1_line"]
    ok = True
    for j, vt in enumerate(view_times):
        fi = (vt - t0) // 60_000  # فهرس الدقة الكاملة من الزمن
        a, b = lv[j], lf[fi]
        if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-12):
            ok = False
            break
    check("C19 عينات view == قيم الدقة الكاملة عند نفس العمود", ok)

    nl("C20-C24 — B-1: مسار الثواني (تجميع صاعد من 1s)")
    rng11 = np.random.default_rng(11)
    ns = 9000
    cl1s = 100 + np.cumsum(rng11.normal(0, 0.01, ns))
    candles_1s = [{"time": t0 + i * 1000, "close": float(cl1s[i])} for i in range(ns)]
    r1s = build_osc_section(candles_1s, base_timeframe="1s", prefix="zzfetm",
                            osc_instances=[
                                {"kind": "macd", "id": "m5", "timeframe": "5s", "fast": 6, "slow": 13, "signal": 4},
                                {"kind": "macd", "id": "m15", "timeframe": "15s", "fast": 6, "slow": 13, "signal": 4},
                                {"kind": "macd", "id": "m30", "timeframe": "30s", "fast": 6, "slow": 13, "signal": 4},
                            ])
    avail = {i["id"]: i["available"] for i in r1s["section"]["instances"]}
    check("C20 macd_5s متاحة فوق قاعدة 1s", avail["m5"] is True)
    check("C21 macd_15s متاحة", avail["m15"] is True)
    check("C22 macd_30s متاحة", avail["m30"] is True)
    check("C23 base_tf = 1s المكتشفة من التباعد (لا 1m الافتراضية)",
          r1s["section"]["base_tf"] == "1s" and r1s["section"]["base_tf_ms"] == 1_000)
    cl5 = cl1s.reshape(-1, 5)[:, -1]

    def ema_t(x, p):
        o = np.full(len(x), np.nan); o[p - 1] = np.mean(x[:p]); a = 2.0 / (p + 1)
        for i in range(p, len(x)):
            o[i] = a * x[i] + (1 - a) * o[i - 1]
        return o
    ln5 = np.array([np.nan if x is None else x for x in r1s["series"]["zzfetm_osc_m5_line"]])
    i_probe = 5 * 13 + 4
    ln5_mine = ema_t(cl5, 6) - ema_t(cl5, 13)
    check("C24 قيم 5s = محسوبة من التجميع الصاعد (إغلاق آخر شمعة الدلو)",
          abs(ln5[i_probe] - ln5_mine[12]) < 1e-9, f"{ln5[i_probe]:.8f} vs {ln5_mine[12]:.8f}")

    nl("C25-C30 — B-1: رقع market_data/dataframe_utils/Timeframe")
    MD_SRC = open(f"{R76}/routers/market_data.py", encoding="utf-8").read()
    _ns_md = {}
    exec(compile(extract_def(MD_SRC, "_tf_span_ms"), "<md>", "exec"), _ns_md)
    span = _ns_md["_tf_span_ms"]
    check("C25 _tf_span_ms للثواني: 1s/5s/15s/30s ⇒ 1000/5000/15000/30000",
          (span("1s"), span("5s"), span("15s"), span("30s")) == (1_000, 5_000, 15_000, 30_000))
    check("C26 _tf_span_ms للدقائق/الساعات بلا انحدار",
          (span("1m"), span("1h"), span("4h"), span("1d")) == (60_000, 3_600_000, 14_400_000, 86_400_000))
    exec(compile(extract_def(MD_SRC, "_tf_to_minutes"), "<md>", "exec"), _ns_md)
    t2m = _ns_md["_tf_to_minutes"]
    check("C27 _tf_to_minutes(1s)=1 لا 60 (العلة القديمة)", t2m("1s") == 1 and t2m("30s") == 1)
    # تحميل مباشر من ملفات R76 (حزمة app المحمّلة مسبقاً من شجرة الاختبار
    # لا تُعيد التوجيه — لذا importlib باسم مستقل هو الطريق الصادق للملف المرقّع).
    import importlib.util
    _spec_d = importlib.util.spec_from_file_location("r76_dfu", f"{R76}/utils/dataframe_utils.py")
    _mod_d = importlib.util.module_from_spec(_spec_d)
    _spec_d.loader.exec_module(_mod_d)
    align_time_ms = _mod_d.align_time_ms
    check("C28 align_time_ms للثواني على شبكة الإبوك",
          (align_time_ms(1777593540123, "1s"), align_time_ms(1777593540123, "5s"),
           align_time_ms(1777593540123, "15s"), align_time_ms(1777593540123, "30s"))
          == (1777593540000, 1777593540000, 1777593540000, 1777593540000)
          and align_time_ms(1777593540123, "5s") == 1777593540000
          and align_time_ms(1777593567234, "15s") == 1777593555000)  # الشبكة: 3540000+15000
    _spec_s = importlib.util.spec_from_file_location("r76_sch", f"{R76}/schemas/indicators.py")
    _mod_s = importlib.util.module_from_spec(_spec_s)
    _spec_s.loader.exec_module(_mod_s)
    vals = {t.value for t in _mod_s.Timeframe}
    check("C29 تعداد Timeframe يضم 1s/5s/15s/30s",
          {"1s", "5s", "15s", "30s"} <= vals)
    check("C30 ريجكسات REST الخمسة تقبل الثواني (market_data×2 · overlays · agent_report · backtest-create إن وُجد)",
          all(re.search(r'pattern="\^\(1s\|5s\|15s\|30s\|1m', x) for x in [
              MD_SRC, open(f"{R76}/routers/overlays.py", encoding="utf-8").read(),
              open(f"{R76}/routers/agent_report.py", encoding="utf-8").read()])
          and MD_SRC.count('1s|5s|15s|30s|1m') >= 2)

    nl("C31-C34 — B-1: سقوف أيام الثواني في راوتر overlays")
    OVL_SRC = open(f"{R76}/routers/overlays.py", encoding="utf-8").read()
    m = re.search(r"_SECONDS_DAYS_CAP: Dict\[str, int\] = \{([^}]*)\}", OVL_SRC)
    cap = json.loads("{" + m.group(1).replace('"', '"') + "}") if m else {}
    cap = eval("{" + m.group(1) + "}") if m else {}
    check("C31 _SECONDS_DAYS_CAP: 1s→1 · 5s→3 · 15s→8 · 30s→15",
          cap == {"1s": 1, "5s": 3, "15s": 8, "30s": 15}, str(cap))
    _ns_ovl = {"Dict": Dict, "Optional": Optional, "int": int, "str": str, "cap": None,
               "_SECONDS_DAYS_CAP": cap}
    body = extract_def(OVL_SRC, "_cap_days_for_timeframe")
    exec(compile(body, "<ovl>", "exec"), _ns_ovl)
    capf = _ns_ovl["_cap_days_for_timeframe"]
    d1, c1 = capf("1s", 365)
    d2, c2 = capf("5s", 3)
    d3, c3 = capf("1m", 365)
    check("C32 1s×365يوم ⇒ مقصوصة ليوم واحد (معلنة)", (d1, c1) == (1, True))
    check("C33 5s×3 أيام ⇒ ضمن السقف بلا قصّ", (d2, c2) == (3, False))
    check("C34 فريم الدقائق لا يُمس (365 ⇒ 365 بلا قصّ)", (d3, c3) == (365, False))

    nl("C35-C37 — B-4/B-5/حارس الذاكرة")
    probe = json.load(open("/tmp/live_osc_probe.json"))
    cl_live = np.array(probe["closes"])
    live_candles = [{"time": 1777593540000 + i * 60_000, "close": float(cl_live[i])}
                    for i in range(len(cl_live))]
    r_sig = build_osc_section(live_candles, base_timeframe="1m", prefix="zzfetm",
                              osc_instances=[{"kind": "macd", "id": "macd_1m_6_13_4", "timeframe": "1m",
                                              "fast": 6, "slow": 13, "signal": 4}])
    line = np.array([np.nan if x is None else x for x in r_sig["series"]["zzfetm_osc_macd_1m_6_13_4_line"]])
    sig = np.array([np.nan if x is None else x for x in r_sig["series"]["zzfetm_osc_macd_1m_6_13_4_signal"]])
    sma = pd.Series(line).rolling(4).mean().to_numpy()
    m_ = ~np.isnan(sma) & ~np.isnan(sig)
    n_pts = int(m_.sum())
    n_eq = int(np.sum(np.abs(sig[m_] - sma[m_]) < 1e-12))
    check("C35 B-4: إشارة MACD = SMA(line, 4) في كل النقاط الصالحة",
          n_pts > 0 and n_eq == n_pts,
          f"{n_eq}/{n_pts} نقطة")
    rm = build_osc_section(live_candles, base_timeframe="1m",
                           osc_instances=[{"kind": "macd", "id": "macd_1s_6_13_4", "timeframe": "1s",
                                           "fast": 6, "slow": 13, "signal": 4}])
    check("C36 B-5: warning_codes + warnings_v2 لكل تحذير (كود قابل للقراءة آلياً)",
          "tf_below_base" in rm["section"]["warning_codes"]
          and rm["section"]["warnings_v2"][0]["code"] == "tf_below_base"
          and len(rm["section"]["warnings"]) == len(rm["section"]["warnings_v2"]))
    SVC_SRC = open(f"{R76}/services/indicators/overlays.py", encoding="utf-8").read()
    guard_ok = ("_OSC_ENGINE_MEMORY_BARS = 50_000" in SVC_SRC
                and SVC_SRC.count('tmacd_params["osc_series"] = "none"') == 1
                and SVC_SRC.count('bmacd_params["osc_series"] = "none"') == 1)
    check("C37 حارس 50K شمعة ⇒ نمط none للمحركين (علاج SIGKILL الثلاثي)",
          guard_ok)

    print(f"\n{'='*60}\nالنتيجة: {len(PASS)} ناجح · {len(FAIL)} فاشل")
    if FAIL:
        print("الفاشلة:", FAIL)
    return 2 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
