"""Indicator endpoints: apply, pine transpile, signals and registry metadata.

Mounted at /api/v1/indicators (see app/main.py).
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.signals import SignalRequest
from app.services.data_service import DataService
from app.services.indicators import (
    IndicatorRegistry,
    IndicatorType,
    create_indicator_from_pine,
    get_available_indicators,
    transpile_pine_script,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["indicators"])


class IndicatorSpec(BaseModel):
    """One indicator configuration (flat dict, e.g. {"name": "rsi", "period": 14}).

    Extra keys (id/label/params/...) are preserved so the calculator receives
    the exact configuration shape clients already send.
    """

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., min_length=1, description="Registered indicator name, e.g. rsi, macd, bb")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get(
    "/available",
    summary="قائمة المؤشرات الحية (54+) بالفئات — اكتشفها ديناميكياً",
)
async def list_available_indicators(
    category: Optional[str] = Query(None, description="Filter by category, e.g. momentum, trend, volatility"),
):
    """List all registered indicators with defaults and required columns."""
    try:
        category_enum = None
        if category:
            try:
                category_enum = IndicatorType(category)
            except ValueError:
                raise HTTPException(status_code=400, detail="Unknown indicator category")
        indicators = jsonable_encoder(get_available_indicators(category_enum))
        return {"count": len(indicators), "indicators": indicators}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to list available indicators")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
    "/apply",
    summary="حساب مؤشرات على بيانات رمز وإرجاع القيم جاهزة للرسم",
)
async def apply_indicators_to_data(
    symbol: str,
    timeframe: str,
    market: str = "crypto",
    indicators: List[IndicatorSpec] = Body(..., description="List of indicator configurations"),
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Apply indicators to market data and return the series alongside the candles.

    - **symbol**: stock or crypto symbol
    - **timeframe**: candle interval (1m, 5m, 1h, ...)
    - **market**: market type (crypto, stocks)
    - **body**: list of indicator configurations
    - **days**: historical lookback in days
    """
    indicators_config = [spec.model_dump(exclude_none=True) for spec in indicators]
    try:
        data_service = DataService(db)
        result = await data_service.get_data_with_indicators(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            indicators_config=indicators_config,
            days=days,
        )
        return result
    except HTTPException:
        raise
    except ValueError:
        logger.warning("Indicator apply rejected for %s/%s (market=%s)", symbol, timeframe, market)
        raise HTTPException(status_code=400, detail="Invalid symbol, market or timeframe")
    except Exception:
        logger.exception("Failed to apply indicators for %s", symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/pine/transpile")
async def transpile_pine_code(
    pine_code: str = Body(..., embed=True),
    execute: bool = False,
):
    """Transpile Pine Script code to Python.

    - **pine_code**: full Pine Script source
    - **execute**: optionally build the indicator class from the code
    """
    try:
        python_code = transpile_pine_script(pine_code)
    except Exception:
        logger.exception("Pine Script transpilation failed")
        raise HTTPException(status_code=400, detail="Could not transpile the provided Pine Script")

    result: Dict[str, Any] = {
        "success": True,
        "python_code": python_code,
        "message": "تم التحويل بنجاح",
    }

    if execute:
        try:
            indicator_class = create_indicator_from_pine(pine_code)
            result["indicator_created"] = True
            result["indicator_name"] = indicator_class.__name__
        except Exception:
            logger.warning("Indicator creation from Pine failed", exc_info=True)
            result["indicator_created"] = False
            result["error"] = "Could not build an indicator from the provided code"

    return result


@router.post("/signals")
async def get_trading_signals(request: SignalRequest, db: AsyncSession = Depends(get_db)):
    """Trading signals derived from indicator configurations.

    - **symbol**: stock or crypto symbol
    - **timeframe**: candle interval
    - **market**: market type
    - **indicators**: list of indicator configurations
    - **days**: historical lookback in days
    """
    try:
        data_service = DataService(db)
        signals = await data_service.get_trading_signals(
            symbol=request.symbol,
            timeframe=request.timeframe,
            market=request.market,
            indicators_config=request.indicators,
            days=request.days,
        )
        return signals
    except HTTPException:
        raise
    except ValueError:
        logger.warning("Signal request rejected for %s", request.symbol)
        raise HTTPException(status_code=400, detail="Invalid symbol, market or timeframe")
    except Exception:
        logger.exception("Failed to compute trading signals for %s", request.symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/{indicator_name}/params",
    summary="الإعدادات الافتراضية لمؤشر (rsi, macd, bb...) — لبناء لوحة الإعدادات",
)
async def get_indicator_parameters(indicator_name: str):
    """Default parameters for a registered indicator (e.g. rsi, macd, bb)."""
    info = IndicatorRegistry.get_indicator_info(indicator_name)

    if not info:
        raise HTTPException(status_code=404, detail="Indicator not found")

    return {
        "name": indicator_name,
        "display_name": info.display_name,
        "description": info.description,
        "category": info.category.value,
        "default_params": info.default_params,
        "required_columns": info.required_columns,
    }
