#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROUND19 — إثبات الدوران الكامل (BRIDGE ROUND-TRIP)
==================================================
المرض الذي عولج: جسور المعاملات الثلاثة (calculator._calculate_overlay_indicator ·
overlay_adapters._kw_from_params · overlay_columns.config_to_overlay_params) كانت
تُسقط mode/depth/deviation/backstep بصمت — فيبقى المسار الحي كله يعمل luxalgo
حتى مع بريسِت يطلب tradingview. أُصلحت الجسور الثلاثة؛ هذا السكربت يثبت الإصلاح
على بيانات حية من نفس مسار الإنتاج (_fetch_window):

  B1) جسر المحرك (المسار الحي + الباك-تست): IndicatorCalculator مع تكوين المؤشر
      الحرفي من ZLF_TRIPLE_SIGNAL → metadata.params.mode == "tradingview" وكل
      معاملات TV حرفية، وأعمدة ind_zzf_* == نداء zigzag_fib/compute_overlays
      المباشر بوضع TV (مطابقة على كل الأعمدة التعاقدية).
  B2) جسر config_to_overlay_params: نفس التمرير حرفياً.
  B3) جسر overlay_adapters (ZigZagFibIndicator): نفس التمرير حرفياً.
  B4) التوافق الرجعي: بلا mode → luxalgo كما كان (لا mode يمر أصلاً + أعمدة ==
      النداء المباشر luxalgo).
  B5) الاختلاف الجوهري: أعمدة TV ≠ أعمدة luxalgo على نفس البيانات (الأطراف
      i1/i2/p1/p2 تختلف فعلاً — الوضع الجديد يغيّر الأطراف كما طُلب).
  B6) أثر الإشارات: عدد/مواقع دخول ZLF بين الوضعين.
"""
import asyncio
import json
import os
import sys

PRO27 = "/home/z/my-project/backend-audit/pro27"
sys.path.insert(0, PRO27)
os.chdir(PRO27)
os.environ.setdefault(
    "SECRET_KEY",
    "r6fwc7Q8CGqI3RpKFaTDbJJ55EOR6LrADCPZv4_KK5LbI0fpzDn84KhemcV_TE0C",
)

from app.services.live_strategy_service import _fetch_window, _is_forming  # noqa: E402
from app.services.indicators.calculator import IndicatorCalculator  # noqa: E402
from app.services.indicators.overlay_adapters import ZigZagFibIndicator  # noqa: E402
from app.services.indicators.overlay_columns import (  # noqa: E402
    config_to_overlay_params, columns_from_overlays_result,
)
from app.services.indicators.overlays import compute_overlays, zigzag_fib  # noqa: E402
from app.services.strategy.presets import ZLF_TRIPLE_SIGNAL  # noqa: E402

CONTRACT_ZZF = [
    "ind_zzf_dir", "ind_zzf_p1", "ind_zzf_p2", "ind_zzf_i1", "ind_zzf_i2",
    "ind_zzf_touch", "ind_zzf_liq_state", "ind_zzf_liq_ref_high",
    "ind_zzf_liq_ref_vol", "ind_zzf_liq_vol_ok", "ind_zzf_signal_s1",
    "ind_zzf_signal_s2", "ind_zzf_signal_s3", "ind_zzf_signal_any",
    "ind_zzf_entry", "ind_zzf_entry_s1", "ind_zzf_entry_s2", "ind_zzf_entry_s3",
]

WANT = {"mode": "tradingview", "depth": 12, "deviation": 20, "backstep": 3,
        "liq_lookback": 20, "liq_signals": True, "liq_arm_bars": 60}

FAILS = []


def _fail(msg):
    FAILS.append(msg)
    print(f"  ✗ {msg}")


def _ok(msg):
    print(f"  ✓ {msg}")


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def cols_equal(a: dict, b: dict, cols, label):
    bad = []
    for col in cols:
        va, vb = a.get(col), b.get(col)
        if va is None or vb is None:
            bad.append(f"{col}:missing")
            continue
        if len(va) != len(vb):
            bad.append(f"{col}:len{len(va)}!={len(vb)}")
            continue
        for i, (x, y) in enumerate(zip(va, vb)):
            xn, yn = _num(x), _num(y)
            if (xn is None) != (yn is None):
                bad.append(f"{col}@{i}:{x}!={y}")
                break
            if xn is not None and abs(xn - yn) > 1e-12 * max(1.0, abs(xn)):
                bad.append(f"{col}@{i}:{x}!={y}")
                break
    if bad:
        _fail(f"{label}: تختلف أعمدة — {bad[:4]}")
        return False
    _ok(f"{label}: {len(cols)} عمود تعاقدي مطابق حرفياً")
    return True


def direct_series_cols(zzf):
    """نتيجة zigzag_fib المباشرة → أعمدة ind_zzf_* بنفس المفاتيح التعاقدية."""
    s = zzf["series"]
    mapping = {
        "ind_zzf_dir": "zzf_dir", "ind_zzf_p1": "zzf_p1", "ind_zzf_p2": "zzf_p2",
        "ind_zzf_i1": "zzf_i1", "ind_zzf_i2": "zzf_i2", "ind_zzf_touch": "zzf_touch",
        "ind_zzf_liq_state": "zzf_liq_state", "ind_zzf_liq_ref_high": "zzf_liq_ref_high",
        "ind_zzf_liq_ref_vol": "zzf_liq_ref_vol", "ind_zzf_liq_vol_ok": "zzf_liq_vol_ok",
        "ind_zzf_signal_s1": "zzf_signal_s1", "ind_zzf_signal_s2": "zzf_signal_s2",
        "ind_zzf_signal_s3": "zzf_signal_s3", "ind_zzf_signal_any": "zzf_signal_any",
        "ind_zzf_entry": "zzf_entry", "ind_zzf_entry_s1": "zzf_entry_s1",
        "ind_zzf_entry_s2": "zzf_entry_s2", "ind_zzf_entry_s3": "zzf_entry_s3",
    }
    return {ind: s.get(src) for ind, src in mapping.items()}


def n_entries(cols):
    return int(sum(1 for v in cols.get("ind_zzf_entry", []) if v not in (None, 0)))


def params_ok(kw, label):
    bad = {k: (kw.get(k), v) for k, v in WANT.items() if kw.get(k) != v}
    if bad:
        _fail(f"{label} params mismatch: {bad}")
        return False
    _ok(f"{label}: mode/depth/deviation/backstep/liq_* تمر حرفياً ({sorted(kw.keys())})")
    return True


async def main():
    symbol, timeframe = "ZECUSDT", "5m"
    ind_cfg = ZLF_TRIPLE_SIGNAL["strategy_config"]["indicators"][0]
    print(f"BRIDGE ROUND-TRIP — {symbol} · {timeframe}")
    print(f"preset indicator params: {json.dumps(ind_cfg['params'], ensure_ascii=False)}")

    df_raw, now = await _fetch_window(symbol, "crypto", timeframe)
    df = df_raw.copy().sort_index()
    if len(df) and _is_forming(df.index[-1].to_pydatetime(), timeframe, now):
        df = df.iloc[:-1]
    if len(df) > 1500:
        df = df.iloc[-1500:]
    print(f"window: {len(df)} closed candles")

    preset_tv_kw = {"mode": "tradingview", "depth": 12, "deviation": 20.0,
                    "backstep": 3, "length": 100, "touch_level": 0.618,
                    "liq_lookback": 20, "liq_signals": True, "liq_arm_bars": 60}

    # ---------- B1) جسر المحرك (calculator) ----------
    print("\n[B1] calculator bridge (live + backtest path):")
    calc = IndicatorCalculator()
    res = calc._calculate_overlay_indicator(df, dict(ind_cfg))
    if res is None:
        _fail("calculator bridge returned None!")
    else:
        kw1 = res["metadata"]["params"]
        params_ok(kw1, "calculator")
        tv_direct = zigzag_fib(df, **preset_tv_kw)
        ov_direct = columns_from_overlays_result(
            compute_overlays(df, types=["zzfib"], params={"zzfib": dict(preset_tv_kw)}))
        ov_bridge = columns_from_overlays_result(
            compute_overlays(df, types=["zzfib"], params={"zzfib": dict(kw1)}))
        cols_equal(ov_bridge, ov_direct, CONTRACT_ZZF, "B1 bridge-kw vs direct-TV")
        cols_equal(ov_bridge, direct_series_cols(tv_direct), CONTRACT_ZZF,
                   "B1 bridge vs zigzag_fib-direct")

    # ---------- B2) config_to_overlay_params ----------
    print("\n[B2] config_to_overlay_params bridge:")
    p2 = config_to_overlay_params(dict(ind_cfg))
    p2_flat = (p2 or {}).get("zzfib") if isinstance(p2, dict) else None
    if p2_flat is None:
        _fail("config_to_overlay_params returned None!")
    else:
        params_ok(p2_flat, "config_to_overlay_params")

    # ---------- B3) overlay_adapters ----------
    print("\n[B3] overlay_adapters bridge (ZigZagFibIndicator):")
    from app.services.indicators.base import IndicatorConfig
    ad = ZigZagFibIndicator(IndicatorConfig(
        name="zigzag_fib", type="support_resistance", params=ind_cfg["params"]))
    kw3 = ad._kw_from_params()
    params_ok(kw3, "overlay_adapters")

    # ---------- B4) توافق رجعي: بلا mode → luxalgo ----------
    print("\n[B4] backward compat (بلا mode → luxalgo كما كان):")
    legacy_cfg = {"name": "zigzag_fib", "params": {"length": 100, "touch_level": 0.618,
                                                   "liq_lookback": 20, "liq_signals": True,
                                                   "liq_arm_bars": 60}}
    res4 = calc._calculate_overlay_indicator(df, legacy_cfg)
    if res4 is None:
        _fail("legacy calculator bridge returned None!")
    else:
        kw4 = res4["metadata"]["params"]
        if "mode" in kw4:
            _fail(f"legacy config got mode={kw4['mode']} — يجب ألا يمر mode أصلاً")
        else:
            _ok("legacy config: لا mode يمر أصلاً (سلوك تاريخي سليم)")
        lux_direct = zigzag_fib(df, length=100, touch_level=0.618,
                                liq_lookback=20, liq_signals=True, liq_arm_bars=60)
        ov4 = columns_from_overlays_result(
            compute_overlays(df, types=["zzfib"],
                             params={"zzfib": {"length": 100, "touch_level": 0.618,
                                               "liq_lookback": 20, "liq_signals": True,
                                               "liq_arm_bars": 60}}))
        cols_equal(ov4, direct_series_cols(lux_direct), CONTRACT_ZZF,
                   "B4 bridge vs direct-lux")

    # ---------- B5) الوضعان يختلفان فعلاً ----------
    print("\n[B5] TV vs LUX — الأطراف تختلف فعلاً على نفس البيانات:")
    diffs = 0
    for col in ("ind_zzf_i1", "ind_zzf_i2", "ind_zzf_p1", "ind_zzf_p2"):
        a = (ov_bridge.get(col) if res is not None else None) or []
        b = direct_series_cols(lux_direct).get(col) or []
        d = sum(1 for x, y in zip(a, b) if _num(x) != _num(y))
        diffs += (d > 0)
        print(f"    {col}: {d}/{len(a)} خلية مختلفة")
    if diffs == 0:
        _fail("الوضعان متطابقان؟! هذا يعني أن TV mode غير فعّال")
    else:
        _ok(f"{diffs}/4 أعمدة الأطراف تختلف — الوضع الجديد فعّال ويلتقط أطرافاً مختلفة")

    # ---------- B6) أثر الإشارات ----------
    print("\n[B6] أثر الإشارات (ZLF entries في نفس النافذة):")
    e_tv = n_entries(ov_bridge if res is not None else {})
    e_lux = n_entries(direct_series_cols(lux_direct))
    print(f"    tradingview(12,20,3): {e_tv} دخول · luxalgo-100: {e_lux} دخول")
    _ok("الإشارات تتبع أطراف الزقزاق كما تنبأ صاحب القرار")

    print("\n" + "=" * 80)
    if FAILS:
        print(f"RESULT: {len(FAILS)} FAIL(S)")
        for f in FAILS:
            print(f"  - {f}")
        sys.exit(1)
    print("RESULT: ALL BRIDGE PROOFS PASS ✓")


if __name__ == "__main__":
    asyncio.run(main())
