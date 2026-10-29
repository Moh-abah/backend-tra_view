import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pydantic import ValidationError
import pandas.testing as pdt

from app.services.indicators.base import (
    IndicatorResult,
    IndicatorConfig,
    IndicatorType,
    Timeframe,
    BaseIndicator,
)


def make_timeseries(n=5, start=None):
    if start is None:
        start = pd.Timestamp("2025-01-01")
    idx = pd.date_range(start=start, periods=n, freq="min")
    return idx


def test_indicatorresult_accepts_list_and_converts_to_series():
    vals = [1, 2, 3, 4]
    res = IndicatorResult(name="test", values=vals)
    assert isinstance(res.values, pd.Series)
    assert res.values.tolist() == vals
    assert res.name == "test"


def test_indicatorresult_to_dict_and_from_dict_with_index_and_signals():
    idx = make_timeseries(4)
    values = pd.Series([10, 20, 30, 40], index=idx)
    signals = pd.Series([0, 1, 0, -1], index=idx)
    meta = {"foo": "bar"}

    res = IndicatorResult(name="ind", values=values, signals=signals, metadata=meta)
    d = res.to_dict()

    # basic shape checks
    assert d["name"] == "ind"
    assert "values" in d and isinstance(d["values"], dict)
    assert d["values"]["data"] == [10, 20, 30, 40]
    assert len(d["values"]["index"]) == 4
    assert d["signals"]["data"] == [0, 1, 0, -1]
    assert d["metadata"] == meta

    # reconstruct
    res2 = IndicatorResult.from_dict(d)
    pdt.assert_series_equal(res.values.reset_index(drop=True), res2.values.reset_index(drop=True))
    pdt.assert_series_equal(res.signals.reset_index(drop=True), res2.signals.reset_index(drop=True))
    assert res2.name == res.name
    assert res2.metadata == res.metadata


def test_indicatorresult_to_json_and_from_json():
    idx = make_timeseries(3)
    values = pd.Series([1.5, 2.5, 3.5], index=idx)
    res = IndicatorResult(name="jtest", values=values, metadata={"a": 1})
    j = res.to_json()
    assert isinstance(j, str)

    res2 = IndicatorResult.from_json(j)
    # indexes may deserialize to datetime index; compare values and name/metadata
    pdt.assert_series_equal(res.values.reset_index(drop=True), res2.values.reset_index(drop=True))
    assert res2.name == res.name
    assert res2.metadata == res.metadata


def test_indicatorresult_to_dict_empty_series():
    empty = pd.Series(dtype=float)
    res = IndicatorResult(name="empty", values=empty)
    d = res.to_dict()
    assert d["values"]["data"] == []
    assert d["values"]["index"] == []
    assert d["values"]["dtype"] == "float64"


def test_indicatorconfig_validator_accepts_valid_and_rejects_invalid():
    # valid params for rsi (period between 5 and 100)
    cfg = IndicatorConfig(name="rsi", type=IndicatorType.MOMENTUM, params={"period": 14})
    assert cfg.name == "rsi"
    assert cfg.params["period"] == 14

    # invalid period should raise a ValidationError on model creation
    with pytest.raises(ValidationError):
        IndicatorConfig(name="rsi", type=IndicatorType.MOMENTUM, params={"period": 3})


class DummyIndicator(BaseIndicator):
    """مؤشر بسيط للاختبارات"""
    @classmethod
    def get_required_columns(cls):
        # نطلب open و close للاختبار
        return ["open", "close"]

    def calculate(self, data: pd.DataFrame) -> IndicatorResult:
        # تأكد من صحة البيانات ثم ارجع متوسط متحرك بسيط كقيم
        self.validate_data(data)
        period = int(self.params.get("period", 1))
        values = data["close"].rolling(period, min_periods=1).mean()
        signals = self.generate_signals(values, data)
        return IndicatorResult(name=self.name, values=values, signals=signals, metadata={"period": period})


def test_baseindicator_validate_data_empty_and_missing_columns():
    cfg = IndicatorConfig(name="dummy", type=IndicatorType.CUSTOM, params={"period": 2})
    ind = DummyIndicator(cfg)

    # empty dataframe -> raises
    empty_df = pd.DataFrame()
    with pytest.raises(ValueError):
        ind.validate_data(empty_df)

    # missing required cols -> raises
    df_missing = pd.DataFrame({"open": [1, 2, 3]})
    with pytest.raises(ValueError) as exc:
        ind.validate_data(df_missing)
    assert "Missing required columns" in str(exc.value)
    assert "dummy" in str(exc.value)

    # valid dataframe -> returns True
    idx = make_timeseries(3)
    df_ok = pd.DataFrame({"open": [1, 2, 3], "close": [1.0, 2.0, 3.0]}, index=idx)
    assert ind.validate_data(df_ok) is True


def test_generate_signals_default_returns_zero_series_and_preserves_index():
    cfg = IndicatorConfig(name="dummy2", type=IndicatorType.CUSTOM)
    ind = DummyIndicator(cfg)
    idx = make_timeseries(4)
    values = pd.Series([5, 6, 7, 8], index=idx)
    sigs = ind.generate_signals(values)
    assert isinstance(sigs, pd.Series)
    assert list(sigs) == [0, 0, 0, 0]
    assert all(sigs.index == values.index)


def test_calculate_and_cache_sets_last_result():
    cfg = IndicatorConfig(name="cache_test", type=IndicatorType.CUSTOM, params={"period": 2})
    ind = DummyIndicator(cfg)
    idx = make_timeseries(4)
    df = pd.DataFrame({"open": [1, 2, 3, 4], "close": [10, 20, 30, 40]}, index=idx)

    res = ind.calculate_and_cache(df)
    # result is IndicatorResult
    assert isinstance(res, IndicatorResult)
    # last result stored
    last = ind.get_last_result()
    assert last is res
    # values length matches input
    assert len(res.values) == len(df)





