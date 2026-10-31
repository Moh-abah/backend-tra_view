"""US stock market endpoints (symbols, charts, analysis, company, market data).

Mounted at /api/v1/stocks (see app/main.py). All endpoints map provider
failures to 404/502 and unexpected errors to a generic 500 — internals are
never leaked to clients.
"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.services.data_service import DataService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stocks-analysis"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat()


def sanitize_json(obj: Any) -> Any:
    """Recursively remove NaN/Inf and normalize values for JSON output.

    Handles pandas Series/DataFrame, numpy scalars, dicts, lists/tuples and
    plain floats in a single module-level function (previously duplicated
    inside endpoints).
    """
    if obj is None:
        return None

    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [sanitize_json(item) for item in obj]

    if hasattr(obj, "to_dict"):  # pandas Series / DataFrame
        return sanitize_json(obj.to_dict())

    if hasattr(obj, "item"):  # numpy scalar
        try:
            obj = obj.item()
        except Exception:
            return str(obj)

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        if abs(obj) > 1e10:
            return round(obj, 4)
        return obj

    return obj


def _stock_provider(service: DataService):
    """Consistent provider lookup: registered as 'stocks' (legacy key 'stock')."""
    provider = service.providers.get("stocks") or service.providers.get("stock")
    if not provider:
        logger.error("Stock provider missing from DataService registry")
        raise HTTPException(status_code=502, detail="Stock data provider is unavailable")
    return provider


def _stock_provider_from_db(db: AsyncSession):
    """Build the DataService and resolve the stock provider (502 on failure)."""
    try:
        service = DataService(db)
    except Exception:
        logger.exception("Failed to initialize the stock provider stack")
        raise HTTPException(status_code=502, detail="Stock data provider is unavailable")
    return _stock_provider(service)


async def _provider_call(coro, not_found_detail: Optional[str] = None) -> Any:
    """Await a provider call: failures -> 502, empty results -> 404."""
    try:
        result = await coro
    except HTTPException:
        raise
    except Exception:
        logger.exception("Stock provider call failed")
        raise HTTPException(status_code=502, detail="Upstream stock provider failed")
    if not_found_detail and not result:
        raise HTTPException(status_code=404, detail=not_found_detail)
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/symbols")
async def get_stock_symbols(
    category: Optional[str] = Query(None, description="Category: technology, financial, healthcare, etc."),
    db: AsyncSession = Depends(get_db),
):
    """Stock symbols, optionally filtered by category."""
    try:
        provider = _stock_provider_from_db(db)
        symbols = await _provider_call(provider.get_symbols(category))
        symbols = symbols or []
        # ✅ الجولة 4: حالة السوق لكل رمز (نفس الجلسة لكل السوق الأمريكي — حساب واحد)
        try:
            from app.providers.us_stock_provider import get_market_status
            _ms = get_market_status()
        except Exception:  # noqa: BLE001
            _ms = None
        return {
            "category": category or "all",
            "symbols": symbols,
            "count": len(symbols),
            "market_status": _ms,
            "per_symbol_status": {s: _ms for s in symbols} if symbols else {},
            "timestamp": _utcnow_iso(),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Stock symbol lookup failed (category=%s)", category)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chart/{symbol}")
async def get_stock_chart(
    symbol: str,
    timeframe: str = Query("1d", description="Timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1M"),
    period: str = Query("1mo", description="Period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y, max"),
    indicators: Optional[str] = Query(None, description="Indicators in JSON format"),
    db: AsyncSession = Depends(get_db),
):
    """Full chart data (candles + indicators + analysis) for a stock."""
    try:
        provider = _stock_provider_from_db(db)

        indicators_list: List[Dict[str, Any]] = []
        if indicators:
            try:
                parsed = json.loads(indicators)
                if isinstance(parsed, list):
                    indicators_list = parsed
                else:
                    logger.warning("Ignored non-list indicators payload for %s", symbol)
            except json.JSONDecodeError:
                logger.warning("Failed to parse indicators JSON for %s", symbol)

        chart_data = await _provider_call(
            provider.get_chart_data(
                symbol=symbol.upper(),
                timeframe=timeframe,
                period=period,
                indicators=indicators_list,
            ),
        )

        if isinstance(chart_data, dict) and chart_data.get("error"):
            logger.error("Provider returned an error for %s chart: %s", symbol, chart_data.get("error"))
            raise HTTPException(status_code=502, detail="Upstream stock provider failed")

        if not chart_data:
            raise HTTPException(status_code=404, detail=f"No chart data found for {symbol}")

        cleaned_data = sanitize_json(chart_data)
        logger.debug("Cleaned chart data for %s (%d keys)", symbol, len(cleaned_data) if isinstance(cleaned_data, dict) else -1)
        return cleaned_data

    except HTTPException:
        raise
    except Exception:
        logger.exception("Chart data failed for %s", symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/analysis/{symbol}")
async def get_technical_analysis(
    symbol: str,
    timeframe: str = Query("1d", description="Timeframe: 1d, 1w, 1M"),
    period: str = Query("3mo", description="Period: 1mo, 3mo, 6mo, 1y"),
    db: AsyncSession = Depends(get_db),
):
    """Technical analysis (trend, momentum, volatility, volume) for a stock."""
    try:
        provider = _stock_provider_from_db(db)
        analysis = await _provider_call(
            provider.get_technical_analysis(symbol=symbol, timeframe=timeframe, period=period),
            not_found_detail=f"No analysis data found for {symbol}",
        )
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "period": period,
            "analysis": analysis,
            "timestamp": _utcnow_iso(),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Technical analysis failed for %s", symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/company/{symbol}")
async def get_company_profile(symbol: str, db: AsyncSession = Depends(get_db)):
    """Company profile, fundamentals and financial statements."""
    try:
        provider = _stock_provider_from_db(db)

        company_info = await _provider_call(
            provider.get_company_info(symbol),
            not_found_detail=f"No company data found for {symbol}",
        )
        fundamental_data = await _provider_call(provider.get_fundamental_data(symbol))
        financial_statements = await _provider_call(provider.get_financial_statements(symbol))

        return {
            "symbol": symbol,
            "company_info": company_info,
            "fundamental_data": fundamental_data,
            "financial_statements": financial_statements,
            "timestamp": _utcnow_iso(),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Company profile failed for %s", symbol)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/market/summary")
async def get_market_summary(db: AsyncSession = Depends(get_db)):
    """Overall US market summary."""
    try:
        provider = _stock_provider_from_db(db)
        summary = await _provider_call(
            provider.get_market_summary(),
            not_found_detail="Market summary is unavailable",
        )
        # ✅ الجولة 4: حالة السوق الحية في ملخص السوق
        _ms = None
        try:
            from app.providers.us_stock_provider import get_market_status
            _ms = get_market_status()
        except Exception:  # noqa: BLE001
            pass
        if isinstance(summary, dict):
            summary.setdefault("market_status", _ms)
        return {"market_summary": summary, "market_status": _ms, "timestamp": _utcnow_iso()}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Market summary failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/market/top-movers")
async def get_top_movers(db: AsyncSession = Depends(get_db)):
    """Biggest gainers and losers of the session."""
    try:
        provider = _stock_provider_from_db(db)
        movers = await _provider_call(
            provider.get_top_gainers_losers(),
            not_found_detail="Top movers are unavailable",
        )
        movers = movers or {}
        _ms = None
        try:
            from app.providers.us_stock_provider import get_market_status
            _ms = get_market_status()
        except Exception:  # noqa: BLE001
            pass
        return {
            "gainers": movers.get("gainers", []),
            "losers": movers.get("losers", []),
            "market_status": _ms,
            "timestamp": _utcnow_iso(),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Top movers lookup failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/search")
async def search_stocks(
    query: str = Query(..., description="Search query"),
    db: AsyncSession = Depends(get_db),
):
    """Search stocks by name or ticker."""
    try:
        provider = _stock_provider_from_db(db)
        results = await _provider_call(provider.search_stocks(query))
        results = results or []
        return {
            "query": query,
            "results": results,
            "count": len(results),
            "timestamp": _utcnow_iso(),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Stock search failed (query=%s)", query)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/sectors")
async def get_sector_analysis(db: AsyncSession = Depends(get_db)):
    """Sector-level performance analysis."""
    try:
        provider = _stock_provider_from_db(db)
        sectors = await _provider_call(
            provider.get_sector_analysis(),
            not_found_detail="Sector analysis is unavailable",
        )
        return {"sectors": sectors, "timestamp": _utcnow_iso()}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Sector analysis failed")
        raise HTTPException(status_code=500, detail="Internal server error")
