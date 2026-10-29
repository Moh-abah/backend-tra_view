import pytest
import pandas as pd
import numpy as np
import pandas.testing as pdt

from app.services.indicators.indicators import (
    SMAIndicator,
    EMAIndicator,
    WMAIndicator,
    RSIIndicator,
    MACDIndicator,
    VWAPIndicator,
    OBVIndicator,
)

from app.services.indicators.base import IndicatorConfig, IndicatorType


def make_df(close, high=None, low=None, open_=None, volume=None, start="2025-01-01", freq="min"):
    n = len(close)
    idx = pd.date_range(start=start, periods=n, freq=freq)
    df = pd.DataFrame(index=idx)
    df["close"] = pd.Series(close, index=idx)
    df["high"] = pd.Series(high if high is not None else close, index=idx)
    df["low"] = pd.Series(low if low is not None else close, index=idx)
    df["open"] = pd.Series(open_ if open_ is not None else close, index=idx)
    df["volume"] = pd.Series(volume if volume is not None else [0]*n, index=idx)
    return df


def test_sma_basic():
    # close = 1..5, period=3 -> SMA at indexes 0,1 = NaN, idx2=2.0, idx3=3.0, idx4=4.0
    df = make_df([1, 2, 3, 4, 5])
    cfg = IndicatorConfig(name="sma", type=IndicatorType.TREND, params={"period": 3})
    ind = SMAIndicator(cfg)
    res = ind.calculate(df)
    vals = res.values
    assert len(vals) == len(df)
    # check expected non-nan values
    assert pytest.approx(vals.iloc[2]) == 2.0
    assert pytest.approx(vals.iloc[3]) == 3.0
    assert pytest.approx(vals.iloc[4]) == 4.0
    # first two are NaN
    assert pd.isna(vals.iloc[0])
    assert pd.isna(vals.iloc[1])


def test_ema_matches_pandas_ewm():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    df = make_df(data)
    period = 3
    cfg = IndicatorConfig(name="ema", type=IndicatorType.TREND, params={"period": period})
    ind = EMAIndicator(cfg)
    res = ind.calculate(df)
    expected = df["close"].ewm(span=period, adjust=False).mean()
    pdt.assert_series_equal(res.values, expected)


def test_wma_basic():
    # test WMA implementation against manual calculation for small series
    data = [1.0, 2.0, 3.0, 4.0]
    df = make_df(data)
    period = 3
    cfg = IndicatorConfig(name="wma", type=IndicatorType.TREND, params={"period": period})
    ind = WMAIndicator(cfg)
    res = ind.calculate(df)
    # For index 2 (third element), WMA of [1,2,3] weights [1,2,3] => (1*1+2*2+3*3)/6 = 14/6
    assert pytest.approx(res.values.iloc[2], rel=1e-6) == 14.0 / 6.0
    # index 3 (last): WMA of [2,3,4] => (2*1 + 3*2 + 4*3)/6 = (2+6+12)/6 = 20/6
    assert pytest.approx(res.values.iloc[3], rel=1e-6) == 20.0 / 6.0


def test_rsi_signals_and_range():
    # build strictly increasing close -> RSI should trend to high values and produce -1 signals when > overbought
    data = list(range(1, 31))  # 1..30
    df = make_df(data)
    cfg = IndicatorConfig(name="rsi", type=IndicatorType.MOMENTUM, params={"period": 14, "overbought": 70, "oversold": 30})
    ind = RSIIndicator(cfg)
    res = ind.calculate(df)
    vals = res.values
    sigs = res.signals
    assert len(vals) == len(df)
    # values should be within [0,100] or NaN
    finite = vals.dropna()
    assert finite.min() >= 0 - 1e-8
    assert finite.max() <= 100 + 1e-8
    # because data is strictly increasing, last values should be high => expect at least one -1 signal
    assert (sigs == -1).any()


def test_macd_signal_presence():
    # create data that produces a clear upward trend so MACD crosses above signal
    data = [1]*5 + list(np.linspace(1, 5, 20)) + [6, 7, 8]
    df = make_df(data)
    cfg = IndicatorConfig(name="macd", type=IndicatorType.MOMENTUM, params={"fast": 12, "slow": 26, "signal": 9})
    ind = MACDIndicator(cfg)
    res = ind.calculate(df)
    macd_vals = res.values
    sigs = res.signals
    assert len(macd_vals) == len(df)
    # signals must be in {-1,0,1}
    assert set(np.unique(sigs.values)).issubset({-1, 0, 1})
    # because trend goes up, expect at least one buy signal (1)
    assert (sigs == 1).any()


def test_vwap_obv_basic_behaviour():
    # VWAP: if close > typical_price often, expect signals -1; OBV: check monotonic increase when close increases and volumes positive
    close = [10, 11, 12, 13, 14]
    high = [10, 11, 12, 13, 14]
    low = [9, 10, 11, 12, 13]
    volume = [100, 100, 100, 100, 100]
    df = make_df(close=close, high=high, low=low, volume=volume)
    cfg_vwap = IndicatorConfig(name="vwap", type=IndicatorType.VOLUME, params={"period": 3})
    vwap_ind = VWAPIndicator(cfg_vwap)
    vres = vwap_ind.calculate(df)
    # values length match
    assert len(vres.values) == len(df)
    # signals only -1/0/1
    assert set(np.unique(vres.signals.values)).issubset({-1, 0, 1})

    cfg_obv = IndicatorConfig(name="obv", type=IndicatorType.VOLUME, params={})
    obv_ind = OBVIndicator(cfg_obv)
    ores = obv_ind.calculate(df)
    # OBV should be non-decreasing because close strictly increases and volumes positive
    obv_vals = ores.values
    # drop first element and ensure each next >= previous (non-strict)
    non_decreasing = all(obv_vals.iloc[i] >= obv_vals.iloc[i-1] - 1e-8 for i in range(1, len(obv_vals)))
    assert non_decreasing
