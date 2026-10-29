"""Market screening endpoints (filter symbols by criteria).

Mounted at /api/v1/filtering (see app/main.py).
"""

import asyncio
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Body, HTTPException, Query

from app.services.filtering import FilterCriteria, get_filtering_engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["filtering"])


@router.post("/symbols")
async def filter_symbols(
    market: str = Query("crypto"),
    criteria: FilterCriteria = Body(...),
    use_cache: bool = Query(True),
):
    """Filter symbols by multiple criteria (pattern, price, volume, indicators, ...).

    - **market**: crypto, stocks
    - **criteria**: FilterCriteria body
    - **use_cache**: use the engine result cache
    """
    filtering_engine = get_filtering_engine()
    try:
        result = await filtering_engine.filter_symbols(
            market=market, criteria=criteria, use_cache=use_cache
        )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Symbol filtering failed (market=%s)", market)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/markets")
async def get_available_markets():
    """Markets available for screening."""
    return {
        "markets": [
            {"id": "crypto", "name": "Cryptocurrency", "description": "العملات الرقمية"},
            {"id": "stocks", "name": "US Stocks", "description": "الأسهم الأمريكية"},
            {"id": "forex", "name": "Forex", "description": "سوق العملات", "coming_soon": True},
        ]
    }


@router.get("/criteria/examples")
async def get_filter_criteria_examples():
    """Example FilterCriteria payloads for common screens."""
    return {
        "basic_crypto": {
            "name": "فلترة العملات الأساسية",
            "description": "فلترة العملات الرقمية ذات الحجم العالي",
            "criteria": {
                "market": "crypto",
                "symbol_pattern": "*USDT",
                "min_volume_24h": 10000000,
                "limit": 20,
            },
        },
        "rsi_oversold": {
            "name": "فلترة RSI التشبع بالبيع",
            "description": "فلترة الرموز ذات RSI أقل من 30 (تشبع بالبيع)",
            "criteria": {
                "market": "crypto",
                "required_indicators": ["rsi"],
                "indicator_filters": {"rsi": {"max": 30}},
                "limit": 10,
            },
        },
        "trending_stocks": {
            "name": "الأسهم المتصاعدة",
            "description": "فلترة الأسهم ذات الاتجاه الصاعد",
            "criteria": {
                "market": "stocks",
                "min_price": 50,
                "sort_by": "price",
                "sort_order": "desc",
                "limit": 15,
            },
        },
    }


@router.get("/stats")
async def get_filtering_stats():
    """Engine statistics (filters run, cache hits/misses, cache size)."""
    filtering_engine = get_filtering_engine()
    try:
        engine_stats = filtering_engine.get_stats()
    except Exception:
        logger.exception("Failed to collect filtering stats")
        engine_stats = {}
    return {
        "engine_stats": engine_stats,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/bulk")
async def bulk_filter_symbols(
    markets: List[str] = Body(default=["crypto"]),
    criteria_list: List[FilterCriteria] = Body(...),
    parallel: bool = Query(True),
):
    """Filter symbols across several markets / criteria sets in one call.

    - **markets**: list of markets
    - **criteria_list**: list of FilterCriteria bodies
    - **parallel**: run all combinations concurrently (asyncio.gather)
    """
    filtering_engine = get_filtering_engine()
    pairs = [(market, criteria) for market in markets for criteria in criteria_list]
    if not pairs:
        return {"total_results": 0, "results": {}}

    async def _run_one(market: str, criteria: FilterCriteria) -> dict:
        result = await filtering_engine.filter_symbols(market=market, criteria=criteria)
        return {"symbols": result.symbols, "count": len(result.symbols)}

    try:
        if parallel:
            outcomes = await asyncio.gather(
                *[_run_one(market, criteria) for market, criteria in pairs],
                return_exceptions=True,
            )
        else:
            outcomes: list = []
            for market, criteria in pairs:
                try:
                    outcomes.append(await _run_one(market, criteria))
                except Exception as exc:  # keep going item by item
                    outcomes.append(exc)
    except Exception:
        logger.exception("Bulk filtering failed to schedule tasks")
        raise HTTPException(status_code=500, detail="Internal server error")

    results = {}
    for index, ((market, criteria), outcome) in enumerate(zip(pairs, outcomes)):
        key = f"{market}_{index}_{criteria.model_dump_json()[:40]}"
        if isinstance(outcome, BaseException):
            logger.error(
                "Bulk filter item failed (market=%s, index=%d): %r", market, index, outcome
            )
            results[key] = {"error": "Filtering failed for this market/criteria combination"}
        else:
            results[key] = outcome

    return {"total_results": len(results), "results": results}
