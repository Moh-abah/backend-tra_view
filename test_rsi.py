import asyncio
from app.database import get_db
from app.services.data_service import DataService
from app.services.indicators.base import IndicatorConfig, IndicatorType, Timeframe
from app.services.indicators.registry import IndicatorRegistry
from app.services.indicators.registry import IndicatorRegistry
print(IndicatorRegistry.list_indicators())


async def test_rsi():
    db = await get_db().__anext__()
    data_service = DataService(db)

    df = await data_service.get_latest_candles(
        symbol="BTCUSDT",
        timeframe="1m",
        market="crypto",
        limit=100
    )

    config = IndicatorConfig(
        name="rsi",
        type=IndicatorType.MOMENTUM,
        params={"period": 14, "overbought": 70, "oversold": 30},
        timeframe=Timeframe.MIN1
    )

    registry = IndicatorRegistry()
    rsi_result = registry.calculate_indicator(df, config)  # هذا مؤشر واحد

    # الآن نحصل على القيم الصحيحة من Attribute
    if hasattr(rsi_result, "values"):
        rsi_values = rsi_result.values
    elif hasattr(rsi_result, "series"):
        rsi_values = rsi_result.series
    else:
        raise TypeError("IndicatorResult does not have 'values' or 'series'")

    print(rsi_values.tail(10))  # آخر 10 قيم
