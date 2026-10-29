"""Core API router: symbol listing and real system health/status checks.

Mounted at /api/v1 (see app/main.py). The canonical /market-overview
WebSocket lives in app/routers/websocket.py — it is intentionally NOT
duplicated here.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.redis_client import redis_client
from app.database.session import AsyncSessionLocal, get_db
from app.services.data_service import DataService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["core"])


# ---------------------------------------------------------------------------
# Shared real health-check helpers (mirrored in market_data.py)
# ---------------------------------------------------------------------------
async def _check_database() -> Dict[str, Any]:
    """Probe the PostgreSQL connection with a real `SELECT 1`. Never raises."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "up", "detail": "SELECT 1 OK"}
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return {"status": "down", "detail": "Database connection failed"}


async def _check_redis() -> Dict[str, Any]:
    """Probe Redis with a real PING. Never raises."""
    try:
        if await redis_client.ping():
            return {"status": "up", "detail": "PING OK"}
        return {"status": "down", "detail": "PING returned False"}
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"status": "down", "detail": "PING failed"}


async def _system_status_payload() -> Dict[str, Any]:
    """Build the status payload from real probes; degrades, never raises."""
    try:
        services = {
            "database": await _check_database(),
            "redis": await _check_redis(),
        }
        overall = "ok" if all(s["status"] == "up" for s in services.values()) else "degraded"
        return {
            "status": overall,
            "services": services,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception:
        logger.exception("Status payload construction failed")
        return {
            "status": "degraded",
            "services": {
                "database": {"status": "down", "detail": "Check crashed"},
                "redis": {"status": "down", "detail": "Check crashed"},
            },
            "timestamp": datetime.utcnow().isoformat(),
        }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/symbols")
async def get_available_symbols(
    market: str = "crypto",
    db: AsyncSession = Depends(get_db),
):
    """List available symbols for a market (crypto, stocks)."""
    try:
        service = DataService(db)
        symbols = await service.get_symbols(market)
        logger.info("Served %d symbols for market=%s", len(symbols), market)
        return {
            "market": market,
            "symbols": symbols,
            "count": len(symbols),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        # DataService raises well-formed HTTPExceptions (400 unknown market,
        # 500 provider failure) — pass them through untouched.
        raise
    except Exception:
        logger.exception("Failed to list symbols for market=%s", market)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status")
async def system_status():
    """Real system status: probes the database and Redis, degrades if any is down."""
    return await _system_status_payload()


@router.get("/health")
async def health_check():
    """Liveness alias returning the same payload as /status."""
    return await _system_status_payload()
