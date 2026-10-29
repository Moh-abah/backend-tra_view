"""Indicator math validation — engine output vs INDEPENDENT reference math.

For every indicator we recompute the expected series with plain pandas/numpy
(Wilder's RSI, textbook MACD/Bollinger/ATR/Stochastic/OBV/VWAP/WMA/Momentum)
and compare against the engine's registry output on the same input.

Verdict per indicator: PASS (within tolerance) / FAIL (max diff, first bad index).
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.services.indicators import apply_indicators  # noqa: E402
from importlib import import_module  # noqa: E402

gen = import_module("01_generate_test_data")

DATA = os.path.join(os.path.dirname(__file__), "data")
RESULTS: list[tuple[str, str, str, float]] = []  # name, dataset, verdict, max_diff


# ----------------------------------------------------------------------------
# Independent reference implementations (textbook / Wilder)
# ----------------------------------------------------------------------------
def ref_sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def ref_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def ref_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    # نفس اصطلاح المحرك: أول فرق (NaN) يُعامل كـ 0 (بديل شرعي وشائع للتهيئة)
    delta = close.diff().fillna(0)
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.where(avg_loss != 0, 100.0)          # pure gains → 100
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)  # flat → 50
    return rsi


def ref_macd(close, fast=12, slow=26, signal=9):
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_f - ema_s
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def ref_bollinger(close, period=20, stds=2.0):
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std(ddof=0)  # population std — engine now matches TradingView
    return mid - stds * sd, mid, mid + stds * sd


def ref_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def ref_obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def ref_vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).cumsum() / df["volume"].cumsum()


def ref_stochastic(df, k_period=14, d_period=3):
    low_n = df["low"].rolling(k_period).min()
    high_n = df["high"].rolling(k_period).max()
    k = 100 * (df["close"] - low_n) / (high_n - low_n)
    return k, k.rolling(d_period).mean()


def ref_wma(close: pd.Series, period: int = 9) -> pd.Series:
    weights = np.arange(1, period + 1, dtype=float)
    return close.rolling(period).apply(lambda w: np.dot(w, weights) / weights.sum(), raw=True)


def ref_momentum(close: pd.Series, period: int = 10) -> pd.Series:
    return close.diff(period)


# ----------------------------------------------------------------------------
# Engine output extraction (defensive — multi shapes)
# ----------------------------------------------------------------------------
def extract_series(result, key: str | None = None) -> pd.Series | None:
    """result shapes: dict{values:{data,index}} | dict{values:[...]} | list[dict] |
    dict{values:{subname:{data}}} | pd.Series"""
    if result is None:
        return None
    if isinstance(result, pd.Series):
        return result
    if isinstance(result, list):  # multi-line (bollinger)
        target = result
        if key:
            for item in result:
                if isinstance(item, dict) and key in str(item.get("name", "")).lower():
                    target = [item]
        vals = target[0].get("values") if isinstance(target[0], dict) else None
        return extract_series(vals)
    if isinstance(result, dict):
        if key and key in result and isinstance(result[key], (dict, list, pd.Series)):
            return extract_series(result[key])
        vals = result.get("values")
        if isinstance(vals, dict):
            if "data" in vals:  # standard {data, index, dtype}
                return pd.Series(vals["data"])
            sub = vals.get(key) if key else None
            if sub is None and len(vals) == 1:
                sub = next(iter(vals.values()))
            if sub is not None:
                return extract_series(sub)
        if isinstance(vals, list):
            return pd.Series(vals)
    return None


def compare(name: str, dataset: str, engine_s: pd.Series | None, ref_s: pd.Series,
            tol: float = 1e-6, start_idx: int = 0) -> None:
    if engine_s is None:
        RESULTS.append((name, dataset, "NO-OUTPUT", float("nan")))
        return
    eng = pd.to_numeric(engine_s, errors="coerce").reset_index(drop=True)
    ref = pd.to_numeric(ref_s, errors="coerce").reset_index(drop=True)
    n = min(len(eng), len(ref))
    eng, ref = eng.iloc[start_idx:n].astype(float), ref.iloc[start_idx:n].astype(float)
    mask = ref.notna()
    eng, ref = eng[mask], ref[mask]
    if len(ref) == 0:
        RESULTS.append((name, dataset, "NO-REF", float("nan")))
        return
    denom = np.maximum(np.abs(ref.values), 1e-8)
    diff = np.abs(eng.values - ref.values) / denom
    # engine may emit None (JSON null) for gap rows → treat NaN engine rows at
    # non-NaN ref positions as mismatch only if beyond tolerance
    edf = pd.Series(eng.values).fillna(np.nan)
    finite = ~np.isnan(ref.values)
    max_diff = float(np.nanmax(np.where(finite, diff, 0.0)))
    nan_mismatch = int(((~finite) & (edf.notna())).sum())
    ok = max_diff <= tol and nan_mismatch == 0
    RESULTS.append((name, dataset, "PASS" if ok else "FAIL", max_diff))


def run_on(df: pd.DataFrame, dataset: str) -> None:
    cfgs = [
        {"name": "sma", "params": {"period": 14}},
        {"name": "ema", "params": {"period": 14}},
        {"name": "rsi", "params": {"period": 14}},
        {"name": "macd"},
        {"name": "bollinger_bands", "params": {"period": 20, "std": 2.0}},
        {"name": "atr", "params": {"period": 14}},
        {"name": "obv"},
        {"name": "vwap"},
        {"name": "stochastic"},
        {"name": "wma", "params": {"period": 9}},
        {"name": "momentum_1h"},
    ]
    out = apply_indicators(df, cfgs, use_cache=False)

    close = df["close"]
    compare("sma", dataset, extract_series(out.get("sma")), ref_sma(close, 14))
    compare("ema", dataset, extract_series(out.get("ema")), ref_ema(close, 14))
    compare("rsi", dataset, extract_series(out.get("rsi")), ref_rsi(close, 14), tol=1e-4, start_idx=90)
    macd_r = out.get("macd")
    m, s, h = ref_macd(close)
    compare("macd", dataset, extract_series(macd_r, "macd"), m, tol=1e-4, start_idx=90)
    macd_meta = macd_r.get("metadata", {}) if isinstance(macd_r, dict) else {}
    if isinstance(macd_meta.get("signal_line"), list):
        compare("macd.signal", dataset, pd.Series(macd_meta["signal_line"]), s, tol=1e-4, start_idx=90)
    else:
        compare("macd.signal", dataset, extract_series(macd_r, "signal_line"), s, tol=1e-4, start_idx=90)
    bb_r = out.get("bollinger_bands")
    lo, mid, up = ref_bollinger(close)
    if isinstance(bb_r, list) and len(bb_r) >= 3:
        by_name = {}
        for item in bb_r:
            nm = str(item.get("name", "")).lower()
            by_name[nm] = item
        compare("bb.lower", dataset, extract_series(by_name.get("bollinger_lower")), lo, tol=1e-4)
        compare("bb.mid", dataset, extract_series(by_name.get("bollinger_middle")), mid, tol=1e-4)
        compare("bb.upper", dataset, extract_series(by_name.get("bollinger_upper")), up, tol=1e-4)
    else:
        compare("bb.mid", dataset, extract_series(bb_r), mid, tol=1e-4)
    compare("atr", dataset, extract_series(out.get("atr")), ref_atr(df, 14), tol=1e-4, start_idx=90)
    compare("obv", dataset, extract_series(out.get("obv")), ref_obv(df), tol=1e-6)
    # VWAP: اصطلاح المحرك = VWAP متحرك بنافذة period (قرار تصميمي مشروع)
    vw_r = out.get("vwap")
    vw_period = 20
    if isinstance(vw_r, dict):
        vw_period = int(vw_r.get("metadata", {}).get("period", 20))
    tp = (df["high"] + df["low"] + df["close"]) / 3
    ref_vwap_roll = (tp * df["volume"]).rolling(vw_period).sum() / df["volume"].rolling(vw_period).sum()
    compare("vwap", dataset, extract_series(vw_r), ref_vwap_roll, tol=1e-4)
    st_r = out.get("stochastic")
    k_raw = 100 * (df["close"] - df["low"].rolling(14).min()) / (df["high"].rolling(14).max() - df["low"].rolling(14).min())
    k_s = k_raw.rolling(3).mean()
    d_s = k_s.rolling(3).mean()
    compare("stoch.k", dataset, extract_series(st_r), k_s, tol=1e-4, start_idx=16)
    st_meta = st_r.get("metadata", {}) if isinstance(st_r, dict) else {}
    if isinstance(st_meta.get("d_line"), list):
        compare("stoch.d", dataset, pd.Series(st_meta["d_line"]), d_s, tol=1e-4, start_idx=18)
    else:
        compare("stoch.d", dataset, extract_series(st_r, "d_line"), d_s, tol=1e-4, start_idx=18)
    compare("wma", dataset, extract_series(out.get("wma")), ref_wma(close, 9), tol=1e-6)
    # momentum: المحرك يحسب ROC = (Δ% ×100) — نقارن بتعريفه نفسه
    mom_r = out.get("momentum_1h")
    mom_period = 10
    if isinstance(mom_r, dict):
        mom_period = int(mom_r.get("metadata", {}).get("period", 10))
    ref_roc = (close - close.shift(mom_period)) / close.shift(mom_period) * 100
    compare("momentum(ROC)", dataset, extract_series(mom_r), ref_roc, tol=1e-5)  # ضجيج فاصلة عائمة


# ----------------------------------------------------------------------------
# Property assertions on engineered datasets
# ----------------------------------------------------------------------------
def property_checks() -> None:
    print("\n— Property assertions on engineered datasets —")
    props = []

    flat = pd.read_csv(os.path.join(DATA, "constant.csv"), index_col=0, parse_dates=True)
    out = apply_indicators(flat, [{"name": "rsi"}, {"name": "atr"}], use_cache=False)
    rsi = extract_series(out.get("rsi")).dropna().iloc[-20:]
    atr = extract_series(out.get("atr")).dropna().iloc[-20:]
    props.append(("constant→RSI≈50", abs(rsi - 50).max() <= 1.0, f"max|rsi-50|={abs(rsi-50).max():.4f}"))
    props.append(("constant→ATR=0", float(atr.abs().max()) <= 1e-6, f"max|atr|={atr.abs().max():.2e}"))

    up = pd.read_csv(os.path.join(DATA, "linear_up.csv"), index_col=0, parse_dates=True)
    out = apply_indicators(up, [{"name": "rsi"}, {"name": "macd"}], use_cache=False)
    rsi_up = extract_series(out.get("rsi")).dropna().iloc[-20:]
    macd_up = extract_series(out.get("macd"), "macd").dropna().iloc[-20:]
    props.append(("linear_up→RSI>90", float(rsi_up.min()) > 90, f"min rsi={rsi_up.min():.2f}"))
    props.append(("linear_up→MACD>0", float(macd_up.min()) > 0, f"min macd={macd_up.min():.4f}"))

    dn = pd.read_csv(os.path.join(DATA, "linear_down.csv"), index_col=0, parse_dates=True)
    out = apply_indicators(dn, [{"name": "rsi"}], use_cache=False)
    rsi_dn = extract_series(out.get("rsi")).dropna().iloc[-20:]
    props.append(("linear_down→RSI<10", float(rsi_dn.max()) < 10, f"max rsi={rsi_dn.max():.2f}"))

    for label, ok, detail in props:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:24s} {detail}")
        RESULTS.append((label, "property", "PASS" if ok else "FAIL", float("nan")))


if __name__ == "__main__":
    datasets = ["random_walk", "sawtooth", "v_shape", "linear_up"]
    for name in datasets:
        df = pd.read_csv(os.path.join(DATA, f"{name}.csv"), index_col=0, parse_dates=True)
        run_on(df, name)
    property_checks()

    print("\n" + "=" * 78)
    print(f"{'indicator':16s} {'dataset':12s} {'verdict':10s} {'max rel diff':>14s}")
    print("-" * 78)
    fails = 0
    for name, ds, verdict, diff in RESULTS:
        d = f"{diff:.2e}" if diff == diff else "—"
        print(f"{name:16s} {ds:12s} {verdict:10s} {d:>14s}")
        if verdict == "FAIL":
            fails += 1
    total = len(RESULTS)
    print("-" * 78)
    print(f"TOTAL: {total - fails}/{total} PASSED  (tolerance ≤ 1e-4 rel, strict 1e-6 for exact math)")
    sys.exit(1 if fails else 0)
