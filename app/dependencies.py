"""Shared FastAPI dependencies (thin re-exports).

The real implementations live in :mod:`app.services.auth`; this module
exposes them plus ``get_db`` under stable names so routers can depend on a
single import point.
"""

from typing import Any, Dict

from app.database import get_db  # noqa: F401  (re-export)
from app.services.auth import AuthService

# Auth dependencies (async; use these directly in Depends(...)).
get_current_user = AuthService.get_current_user
get_current_active_user = AuthService.get_current_active_user
get_current_superuser = AuthService.get_current_superuser


async def get_user_settings(current_user=Depends(get_current_active_user)):
    """Hook for user-scoped settings resolution (returns the user today)."""
    return current_user


async def get_user_portfolio(
    portfolio_id: int,
    current_user=Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Hook for portfolio-scoped resolution (returns a reference today)."""
    return {"portfolio_id": portfolio_id, "user": current_user}


__all__ = [
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "get_current_superuser",
    "get_user_settings",
    "get_user_portfolio",
]
