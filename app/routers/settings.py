"""User settings router — watchlists, strategies, custom indicators,
filter settings, portfolios and exchange API keys.

Converted to 100% async SQLAlchemy 2.0 style (AsyncSession):

    result = await db.execute(select(Model).where(...))
    rows = result.scalars().all()
    await db.commit() / await db.refresh(obj) / await db.delete(obj)

No legacy sync-ORM query builders or un-awaited commits remain.

Security model
--------------
* Every endpoint requires ``AuthService.get_current_active_user_or_bypass``.
* ``user_id`` is ALWAYS taken from ``current_user`` — never from body/query.
* All list/detail/modify queries are scoped to ``current_user.id``.
  Strategies/indicators keep their original "mine OR public" read semantics;
  every write stays owner-scoped. Resources belonging to other users are
  reported as 404 (no existence leak).
* API-key secrets are never written back to the DB in masked form: responses
  are built as explicit DTOs with masked fields (masking is RESPONSE-ONLY).
* JSON columns are never mutated in place — whole lists/dicts are reassigned.
"""

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import (
    APIKey,
    FilterSettings,
    Portfolio,
    Position,
    Transaction,
    User,
    UserIndicator,
    UserStrategy,
    Watchlist,
)
from app.schemas.user import (
    APIKeyCreate,
    APIKeyResponse,
    FilterSettingsCreate,
    FilterSettingsResponse,
    FilterSettingsUpdate,
    IndicatorCreate,
    IndicatorResponse,
    IndicatorUpdate,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioUpdate,
    StrategyCreate,
    StrategyResponse,
    StrategyUpdate,
    WatchlistCreate,
    WatchlistResponse,
    WatchlistUpdate,
)
from app.services.auth import AuthService
from app.utils.security import SecurityUtils


logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])

#Caps for the honest (non-placeholder) test/run endpoints
MAX_FILTER_SYMBOLS = 20          # /filters/{id}/run processes at most 20 symbols
MIN_TEST_BARS = 20               # /indicators/{id}/test synthetic sample bounds
MAX_TEST_BARS = 500
KNOWN_EXCHANGES = {"binance", "alpaca", "kraken", "bybit", "coinbase", "kucoin"}
VALID_PERMISSIONS = {"read", "trade", "withdraw"}


# ============================================================================
# Internal helpers
# ============================================================================

def _utcnow() -> datetime:
    """Timezone-aware UTC now (safe for asyncpg timestamptz columns)."""
    return datetime.now(timezone.utc)


def _apply_update(obj: Any, update_data: Dict[str, Any]) -> None:
    """Apply an ``exclude_unset`` payload to an ORM instance.

    Lists/dicts are deep-copied and reassigned whole (JSON columns with
    mutable defaults are never mutated in place — SQLAlchemy must see a new
    object to detect the change).
    """
    for field, value in update_data.items():
        if isinstance(value, (dict, list)):
            value = copy.deepcopy(value)
        setattr(obj, field, value)


def _mask(value: Optional[str]) -> str:
    """Mask a secret for response serialization only (never for storage)."""
    if not value:
        return "***"
    return SecurityUtils.mask_sensitive_data(value)


def _api_key_dto(api_key: APIKey) -> Dict[str, Any]:
    """Build a JSON-safe response DTO for an API key.

    The raw ``api_key``/``api_secret`` values stay on the ORM instance; the
    DTO only ever carries masked copies. (Historically this endpoint mutated
    the ORM instance with masked strings, which would persist corrupted
    values on the next flush — that must never happen again.)
    """
    dto = APIKeyResponse.model_validate(api_key).model_dump(mode="json")
    dto["api_key"] = _mask(api_key.api_key)
    dto["api_secret"] = _mask(api_key.api_secret)
    return dto


def _finite_float(value: Any) -> Optional[float]:
    """Convert a numeric value to a JSON-safe finite float (or None)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _position_dict(position: Position) -> Dict[str, Any]:
    """Explicit serialization of a Position (no __dict__ leaks)."""
    return {
        "id": position.id,
        "portfolio_id": position.portfolio_id,
        "symbol": position.symbol,
        "market": position.market,
        "position_type": position.position_type,
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "quantity": position.quantity,
        "stop_loss": position.stop_loss,
        "take_profit": position.take_profit,
        "pnl": position.pnl,
        "pnl_percent": position.pnl_percent,
        "status": position.status,
        "opened_at": position.opened_at.isoformat() if position.opened_at else None,
        "closed_at": position.closed_at.isoformat() if position.closed_at else None,
    }


def _transaction_dict(transaction: Transaction) -> Dict[str, Any]:
    """Explicit serialization of a Transaction (no __dict__ leaks)."""
    return {
        "id": transaction.id,
        "portfolio_id": transaction.portfolio_id,
        "type": transaction.type,
        "symbol": transaction.symbol,
        "amount": transaction.amount,
        "price": transaction.price,
        "quantity": transaction.quantity,
        "fee": transaction.fee,
        "description": transaction.description,
        "status": transaction.status,
        "executed_at": transaction.executed_at.isoformat() if transaction.executed_at else None,
    }


def _portfolio_dict(
    portfolio: Portfolio,
    positions: Optional[List[Dict[str, Any]]] = None,
    transactions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Explicit portfolio response payload (no ``portfolio.__dict__`` leak)."""
    data = PortfolioResponse.model_validate(portfolio).model_dump(mode="json")
    data["positions"] = positions if positions is not None else []
    data["transactions"] = transactions if transactions is not None else []
    return data


# ============================================================================
# قوائم المراقبة — Watchlists
# ============================================================================

@router.get("/watchlists", response_model=List[WatchlistResponse])
async def get_watchlists(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    market: Optional[str] = None,
    is_default: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على قوائم مراقبة المستخدم الحالي (تتطلب مصادقة — scoped to owner).

    Security fix: this endpoint used to be public and accepted an arbitrary
    ``user_id`` query param (IDOR by design). user_id now comes only from
    the authenticated user and every query is scoped to ``current_user.id``.
    """
    try:
        stmt = select(Watchlist).where(Watchlist.user_id == current_user.id)

        if market:
            stmt = stmt.where(Watchlist.market == market)

        if is_default is not None:
            stmt = stmt.where(Watchlist.is_default == is_default)

        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Watchlist.name.ilike(like),
                    Watchlist.description.ilike(like),
                )
            )

        stmt = stmt.order_by(Watchlist.id).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to list watchlists for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/watchlists", response_model=WatchlistResponse)
async def create_watchlist(
    watchlist_data: WatchlistCreate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """إنشاء قائمة مراقبة جديدة"""
    try:
        # إذا كانت هذه القائمة الأولى، اجعلها الافتراضية
        count_result = await db.execute(
            select(func.count())
            .select_from(Watchlist)
            .where(Watchlist.user_id == current_user.id)
        )
        existing_count = count_result.scalar_one()
        is_default = True if existing_count == 0 else bool(watchlist_data.is_default)

        db_watchlist = Watchlist(
            user_id=current_user.id,
            name=watchlist_data.name,
            description=watchlist_data.description,
            symbols=list(watchlist_data.symbols or []),  # explicit fresh copy
            market=watchlist_data.market,
            is_default=is_default,
            color=watchlist_data.color,
        )

        db.add(db_watchlist)
        await db.commit()
        await db.refresh(db_watchlist)

        return db_watchlist

    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error creating watchlist for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to create watchlist for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/watchlists/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist_by_id(
    watchlist_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على قائمة مراقبة محددة (scoped to owner — 404 for foreign rows)"""
    try:
        result = await db.execute(
            select(Watchlist).where(
                Watchlist.id == watchlist_id,
                Watchlist.user_id == current_user.id,
            )
        )
        watchlist = result.scalar_one_or_none()
        if not watchlist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watchlist not found",
            )

        return watchlist

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to fetch watchlist id=%s", watchlist_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.put("/watchlists/{watchlist_id}", response_model=WatchlistResponse)
async def update_watchlist(
    watchlist_id: int,
    watchlist_data: WatchlistUpdate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """تحديث قائمة مراقبة"""
    try:
        result = await db.execute(
            select(Watchlist).where(
                Watchlist.id == watchlist_id,
                Watchlist.user_id == current_user.id,
            )
        )
        watchlist = result.scalar_one_or_none()
        if not watchlist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watchlist not found",
            )

        update_data = watchlist_data.model_dump(exclude_unset=True)

        # إذا تم تعيين is_default = True، إلغاء الافتراضية عن الآخرين
        if update_data.get("is_default") is True:
            await db.execute(
                sa_update(Watchlist)
                .where(
                    Watchlist.user_id == current_user.id,
                    Watchlist.is_default == True,  # noqa: E712
                )
                .values(is_default=False)
                .execution_options(synchronize_session=False)
            )

        _apply_update(watchlist, update_data)

        await db.commit()
        await db.refresh(watchlist)

        return watchlist

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error updating watchlist id=%s", watchlist_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to update watchlist id=%s", watchlist_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist(
    watchlist_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """حذف قائمة مراقبة"""
    try:
        result = await db.execute(
            select(Watchlist).where(
                Watchlist.id == watchlist_id,
                Watchlist.user_id == current_user.id,
            )
        )
        watchlist = result.scalar_one_or_none()
        if not watchlist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watchlist not found",
            )

        # إذا كانت القائمة الافتراضية، جعل قائمة أخرى افتراضية
        if watchlist.is_default:
            other_result = await db.execute(
                select(Watchlist)
                .where(
                    Watchlist.user_id == current_user.id,
                    Watchlist.id != watchlist_id,
                )
                .order_by(Watchlist.id)
                .limit(1)
            )
            other_watchlist = other_result.scalars().first()
            if other_watchlist:
                other_watchlist.is_default = True

        await db.delete(watchlist)
        await db.commit()

        return {"message": "Watchlist deleted successfully"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to delete watchlist id=%s", watchlist_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/watchlists/{watchlist_id}/symbols/{symbol}")
async def add_symbol_to_watchlist(
    watchlist_id: int,
    symbol: str,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """إضافة رمز إلى قائمة المراقبة"""
    try:
        result = await db.execute(
            select(Watchlist).where(
                Watchlist.id == watchlist_id,
                Watchlist.user_id == current_user.id,
            )
        )
        watchlist = result.scalar_one_or_none()
        if not watchlist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watchlist not found",
            )

        symbols = list(watchlist.symbols or [])
        if symbol in symbols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Symbol {symbol} already in watchlist",
            )

        # whole-list reassignment (never in-place mutation of the JSON column)
        watchlist.symbols = symbols + [symbol]
        await db.commit()

        return {"message": f"Symbol {symbol} added to watchlist"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to add symbol to watchlist id=%s", watchlist_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.delete("/watchlists/{watchlist_id}/symbols/{symbol}")
async def remove_symbol_from_watchlist(
    watchlist_id: int,
    symbol: str,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """إزالة رمز من قائمة المراقبة"""
    try:
        result = await db.execute(
            select(Watchlist).where(
                Watchlist.id == watchlist_id,
                Watchlist.user_id == current_user.id,
            )
        )
        watchlist = result.scalar_one_or_none()
        if not watchlist:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Watchlist not found",
            )

        symbols = list(watchlist.symbols or [])
        if symbol not in symbols:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Symbol {symbol} not in watchlist",
            )

        # whole-list reassignment (never in-place mutation of the JSON column)
        watchlist.symbols = [s for s in symbols if s != symbol]
        await db.commit()

        return {"message": f"Symbol {symbol} removed from watchlist"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to remove symbol from watchlist id=%s", watchlist_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


# ============================================================================
# استراتيجيات المستخدم — User strategies
# ============================================================================

@router.post("/strategies", response_model=StrategyResponse)
async def create_strategy(
    strategy_data: StrategyCreate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """إنشاء استراتيجية جديدة"""
    try:
        db_strategy = UserStrategy(
            user_id=current_user.id,
            name=strategy_data.name,
            description=strategy_data.description,
            strategy_config=copy.deepcopy(strategy_data.strategy_config),
            category=strategy_data.category,
            tags=list(strategy_data.tags or []),
            is_public=strategy_data.is_public,
            is_default=strategy_data.is_default,
        )

        db.add(db_strategy)
        await db.commit()
        await db.refresh(db_strategy)

        return db_strategy

    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error creating strategy for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to create strategy for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/strategies", response_model=List[StrategyResponse])
async def get_strategies(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = None,
    is_public: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على استراتيجيات المستخدم (خاصة به + الاستراتيجيات العامة)"""
    try:
        stmt = select(UserStrategy).where(
            or_(
                UserStrategy.user_id == current_user.id,
                UserStrategy.is_public == True,  # noqa: E712
            )
        )

        if category:
            stmt = stmt.where(UserStrategy.category == category)

        if is_public is not None:
            stmt = stmt.where(UserStrategy.is_public == is_public)

        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    UserStrategy.name.ilike(like),
                    UserStrategy.description.ilike(like),
                )
            )

        stmt = stmt.order_by(UserStrategy.id).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to list strategies for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy_by_id(
    strategy_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على استراتيجية محددة (خاصة أو عامة)"""
    try:
        result = await db.execute(
            select(UserStrategy).where(
                UserStrategy.id == strategy_id,
                or_(
                    UserStrategy.user_id == current_user.id,
                    UserStrategy.is_public == True,  # noqa: E712
                ),
            )
        )
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        return strategy

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to fetch strategy id=%s", strategy_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.put("/strategies/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    strategy_data: StrategyUpdate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """تحديث استراتيجية (owner-only)"""
    try:
        result = await db.execute(
            select(UserStrategy).where(
                UserStrategy.id == strategy_id,
                UserStrategy.user_id == current_user.id,
            )
        )
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        update_data = strategy_data.model_dump(exclude_unset=True)
        _apply_update(strategy, update_data)

        await db.commit()
        await db.refresh(strategy)

        return strategy

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error updating strategy id=%s", strategy_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to update strategy id=%s", strategy_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """حذف استراتيجية (owner-only)"""
    try:
        result = await db.execute(
            select(UserStrategy).where(
                UserStrategy.id == strategy_id,
                UserStrategy.user_id == current_user.id,
            )
        )
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        await db.delete(strategy)
        await db.commit()

        return {"message": "Strategy deleted successfully"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to delete strategy id=%s", strategy_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/strategies/{strategy_id}/duplicate", response_model=StrategyResponse)
async def duplicate_strategy(
    strategy_id: int,
    new_name: str,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """نسخ استراتيجية (يمكن نسخ الاستراتيجيات العامة — النسخة ملك للمستخدم الحالي)"""
    try:
        result = await db.execute(
            select(UserStrategy).where(
                UserStrategy.id == strategy_id,
                or_(
                    UserStrategy.user_id == current_user.id,
                    UserStrategy.is_public == True,  # noqa: E712
                ),
            )
        )
        original = result.scalar_one_or_none()
        if not original:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Strategy not found",
            )

        # إنشاء نسخة (JSON deep copies — never share mutable containers)
        new_strategy = UserStrategy(
            user_id=current_user.id,
            name=new_name,
            description=f"Copy of {original.name}",
            strategy_config=copy.deepcopy(original.strategy_config) or {},
            category=original.category,
            tags=list(original.tags or []),
            is_public=False,
            is_default=False,
        )

        db.add(new_strategy)
        await db.commit()
        await db.refresh(new_strategy)

        return new_strategy

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error duplicating strategy id=%s", strategy_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to duplicate strategy id=%s", strategy_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


# ============================================================================
# مؤشرات المستخدم — Custom indicators
# ============================================================================

@router.post("/indicators", response_model=IndicatorResponse)
async def create_indicator(
    indicator_data: IndicatorCreate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """إنشاء مؤشر مخصص"""
    try:
        # التحقق من صحة كود المؤشر
        if not indicator_data.indicator_code.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Indicator code cannot be empty",
            )

        db_indicator = UserIndicator(
            user_id=current_user.id,
            name=indicator_data.name,
            display_name=indicator_data.display_name,
            description=indicator_data.description,
            indicator_code=indicator_data.indicator_code,
            indicator_type=indicator_data.indicator_type,
            parameters=copy.deepcopy(indicator_data.parameters),
            category=indicator_data.category,
            is_public=indicator_data.is_public,
            is_active=indicator_data.is_active,
        )

        db.add(db_indicator)
        await db.commit()
        await db.refresh(db_indicator)

        return db_indicator

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error creating indicator for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to create indicator for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/indicators", response_model=List[IndicatorResponse])
async def get_indicators(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = None,
    indicator_type: Optional[str] = None,
    is_public: Optional[bool] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على مؤشرات المستخدم (خاصة به + المؤشرات العامة)"""
    try:
        stmt = select(UserIndicator).where(
            or_(
                UserIndicator.user_id == current_user.id,
                UserIndicator.is_public == True,  # noqa: E712
            )
        )

        if category:
            stmt = stmt.where(UserIndicator.category == category)

        if indicator_type:
            stmt = stmt.where(UserIndicator.indicator_type == indicator_type)

        if is_public is not None:
            stmt = stmt.where(UserIndicator.is_public == is_public)

        if is_active is not None:
            stmt = stmt.where(UserIndicator.is_active == is_active)

        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    UserIndicator.name.ilike(like),
                    UserIndicator.display_name.ilike(like),
                    UserIndicator.description.ilike(like),
                )
            )

        stmt = stmt.order_by(UserIndicator.id).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to list indicators for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/indicators/{indicator_id}", response_model=IndicatorResponse)
async def get_indicator_by_id(
    indicator_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على مؤشر محدد (خاص أو عام)"""
    try:
        result = await db.execute(
            select(UserIndicator).where(
                UserIndicator.id == indicator_id,
                or_(
                    UserIndicator.user_id == current_user.id,
                    UserIndicator.is_public == True,  # noqa: E712
                ),
            )
        )
        indicator = result.scalar_one_or_none()
        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indicator not found",
            )

        return indicator

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to fetch indicator id=%s", indicator_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.put("/indicators/{indicator_id}", response_model=IndicatorResponse)
async def update_indicator(
    indicator_id: int,
    indicator_data: IndicatorUpdate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """تحديث مؤشر (owner-only)"""
    try:
        result = await db.execute(
            select(UserIndicator).where(
                UserIndicator.id == indicator_id,
                UserIndicator.user_id == current_user.id,
            )
        )
        indicator = result.scalar_one_or_none()
        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indicator not found",
            )

        update_data = indicator_data.model_dump(exclude_unset=True)
        _apply_update(indicator, update_data)

        await db.commit()
        await db.refresh(indicator)

        return indicator

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error updating indicator id=%s", indicator_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to update indicator id=%s", indicator_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.delete("/indicators/{indicator_id}")
async def delete_indicator(
    indicator_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """حذف مؤشر (owner-only)"""
    try:
        result = await db.execute(
            select(UserIndicator).where(
                UserIndicator.id == indicator_id,
                UserIndicator.user_id == current_user.id,
            )
        )
        indicator = result.scalar_one_or_none()
        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indicator not found",
            )

        await db.delete(indicator)
        await db.commit()

        return {"message": "Indicator deleted successfully"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to delete indicator id=%s", indicator_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/indicators/{indicator_id}/test")
async def test_indicator(
    indicator_id: int,
    test_data: Optional[dict] = None,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """اختبار مؤشر مخصص — REAL computation against the indicator registry.

    No more fake "Simulated indicator output": if the stored indicator name
    maps to a registered indicator (app.services.indicators registry), we run
    an actual calculation over a deterministic synthetic OHLCV sample.
    Failures are reported honestly with status 502.
    """
    try:
        result = await db.execute(
            select(UserIndicator).where(
                UserIndicator.id == indicator_id,
                UserIndicator.user_id == current_user.id,
            )
        )
        indicator = result.scalar_one_or_none()
        if not indicator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Indicator not found",
            )

        # Lazy import keeps this router importable even if the indicator
        # package is being refactored by another agent.
        from app.services.indicators import IndicatorConfig, IndicatorRegistry, IndicatorType

        registry_name = (indicator.name or "").strip().lower()
        registered = IndicatorRegistry.get_indicator(registry_name)
        if registered is None:
            logger.info(
                "Indicator test skipped: '%s' (id=%s) is not registry-backed",
                indicator.name,
                indicator.id,
            )
            return {
                "status": "unsupported",
                "indicator_id": indicator.id,
                "indicator_name": indicator.name,
                "detail": (
                    f"Indicator '{indicator.name}' is not registered in the "
                    "app.services.indicators registry; only registry-backed "
                    "indicators can be executed (registered: rsi, ema, sma, "
                    "sma_fast, sma_slow, macd, bb, atr)."
                ),
            }

        # --- build parameters (stored params + optional body overrides) ----
        params: Dict[str, Any] = copy.deepcopy(indicator.parameters or {})
        n_bars = 120
        if isinstance(test_data, dict):
            override_params = test_data.get("params")
            if isinstance(override_params, dict):
                params.update(copy.deepcopy(override_params))
            try:
                n_bars = int(test_data.get("bars", n_bars))
            except (TypeError, ValueError):
                n_bars = 120
        n_bars = max(MIN_TEST_BARS, min(n_bars, MAX_TEST_BARS))

        # --- deterministic synthetic OHLCV sample (no network, no randomness)
        index = pd.date_range(end=_utcnow(), periods=n_bars, freq="15min")
        step = np.arange(n_bars, dtype=float)
        close = 100.0 + 10.0 * np.sin(step / 9.0) + 0.05 * step
        frame = pd.DataFrame(
            {
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1000.0 + 100.0 * np.cos(step / 5.0),
            },
            index=index,
        )

        # --- REAL computation through the registry -------------------------
        # (IndicatorConfig construction is inside the guard too: its param
        # validators reject out-of-range stored parameters with ValueError)
        try:
            config = IndicatorConfig(
                name=registry_name,
                type=IndicatorType.CUSTOM,
                params=params,
            )
            registry = IndicatorRegistry()
            series = registry.calculate_indicator(frame, config)
        except Exception as exc:
            logger.exception(
                "Indicator test failed for '%s' (id=%s)", indicator.name, indicator.id
            )
            return JSONResponse(
                status_code=502,
                content={
                    "status": "error",
                    "detail": f"Indicator computation failed: {exc}",
                },
            )

        valid = series.dropna()
        logger.info(
            "Indicator test executed: name=%s id=%s bars=%s points=%s valid=%s",
            indicator.name,
            indicator.id,
            n_bars,
            len(series),
            len(valid),
        )

        return {
            "status": "success",
            "indicator_id": indicator.id,
            "indicator_name": indicator.name,
            "registry_name": registry_name,
            "bars": n_bars,
            "points": len(series),
            "valid_points": int(series.notna().sum()),
            "first_value": _finite_float(valid.iloc[0]) if len(valid) else None,
            "last_value": _finite_float(valid.iloc[-1]) if len(valid) else None,
            "executed_at": _utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Unexpected failure testing indicator id=%s", indicator_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


# ============================================================================
# إعدادات الفلترة — Filter settings
# ============================================================================

@router.post("/filters", response_model=FilterSettingsResponse)
async def create_filter_settings(
    filter_data: FilterSettingsCreate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """إنشاء إعدادات فلترة جديدة"""
    try:
        # إذا كانت هذه الإعدادات الأولى، اجعلها الافتراضية
        count_result = await db.execute(
            select(func.count())
            .select_from(FilterSettings)
            .where(FilterSettings.user_id == current_user.id)
        )
        existing_count = count_result.scalar_one()
        is_default = True if existing_count == 0 else bool(filter_data.is_default)

        db_filter = FilterSettings(
            user_id=current_user.id,
            name=filter_data.name,
            description=filter_data.description,
            filter_criteria=copy.deepcopy(filter_data.filter_criteria),
            market=filter_data.market,
            is_default=is_default,
        )

        db.add(db_filter)
        await db.commit()
        await db.refresh(db_filter)

        return db_filter

    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error creating filter settings for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to create filter settings for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/filters", response_model=List[FilterSettingsResponse])
async def get_filter_settings(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    market: Optional[str] = None,
    is_default: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على إعدادات فلترة المستخدم"""
    try:
        stmt = select(FilterSettings).where(
            FilterSettings.user_id == current_user.id
        )

        if market:
            stmt = stmt.where(FilterSettings.market == market)

        if is_default is not None:
            stmt = stmt.where(FilterSettings.is_default == is_default)

        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    FilterSettings.name.ilike(like),
                    FilterSettings.description.ilike(like),
                )
            )

        stmt = stmt.order_by(FilterSettings.id).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to list filter settings for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/filters/{filter_id}", response_model=FilterSettingsResponse)
async def get_filter_settings_by_id(
    filter_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على إعدادات فلترة محددة (scoped to owner)"""
    try:
        result = await db.execute(
            select(FilterSettings).where(
                FilterSettings.id == filter_id,
                FilterSettings.user_id == current_user.id,
            )
        )
        filter_settings = result.scalar_one_or_none()
        if not filter_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Filter settings not found",
            )

        return filter_settings

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to fetch filter settings id=%s", filter_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.put("/filters/{filter_id}", response_model=FilterSettingsResponse)
async def update_filter_settings(
    filter_id: int,
    filter_data: FilterSettingsUpdate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """تحديث إعدادات الفلترة"""
    try:
        result = await db.execute(
            select(FilterSettings).where(
                FilterSettings.id == filter_id,
                FilterSettings.user_id == current_user.id,
            )
        )
        filter_settings = result.scalar_one_or_none()
        if not filter_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Filter settings not found",
            )

        update_data = filter_data.model_dump(exclude_unset=True)

        # إذا تم تعيين is_default = True، إلغاء الافتراضية عن الآخرين
        if update_data.get("is_default") is True:
            await db.execute(
                sa_update(FilterSettings)
                .where(
                    FilterSettings.user_id == current_user.id,
                    FilterSettings.is_default == True,  # noqa: E712
                )
                .values(is_default=False)
                .execution_options(synchronize_session=False)
            )

        _apply_update(filter_settings, update_data)

        await db.commit()
        await db.refresh(filter_settings)

        return filter_settings

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error updating filter settings id=%s", filter_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to update filter settings id=%s", filter_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.delete("/filters/{filter_id}")
async def delete_filter_settings(
    filter_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """حذف إعدادات الفلترة"""
    try:
        result = await db.execute(
            select(FilterSettings).where(
                FilterSettings.id == filter_id,
                FilterSettings.user_id == current_user.id,
            )
        )
        filter_settings = result.scalar_one_or_none()
        if not filter_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Filter settings not found",
            )

        # إذا كانت الإعدادات الافتراضية، جعل أخرى افتراضية
        if filter_settings.is_default:
            other_result = await db.execute(
                select(FilterSettings)
                .where(
                    FilterSettings.user_id == current_user.id,
                    FilterSettings.id != filter_id,
                )
                .order_by(FilterSettings.id)
                .limit(1)
            )
            other_filter = other_result.scalars().first()
            if other_filter:
                other_filter.is_default = True

        await db.delete(filter_settings)
        await db.commit()

        return {"message": "Filter settings deleted successfully"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to delete filter settings id=%s", filter_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/filters/{filter_id}/run")
async def run_filter(
    filter_id: int,
    market: str = "crypto",
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """تشغيل الفلترة — REAL FilteringEngine call on the stored criteria.

    No more random.sample() fake results: the stored ``filter_criteria`` JSON
    is validated into FilterCriteria and executed by the real FilteringEngine
    over the stored market, capped at 20 symbols. Failures return 502.
    """
    try:
        result = await db.execute(
            select(FilterSettings).where(
                FilterSettings.id == filter_id,
                FilterSettings.user_id == current_user.id,
            )
        )
        filter_settings = result.scalar_one_or_none()
        if not filter_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Filter settings not found",
            )

        # Lazy imports keep this router importable independent of the
        # filtering service lifecycle.
        from app.services.filtering import get_filtering_engine
        from app.services.filtering.schemas import FilterCriteria

        # stored market takes precedence, query param is the fallback
        effective_market = filter_settings.market or market

        criteria_raw = dict(filter_settings.filter_criteria or {})
        criteria_raw["market"] = effective_market

        # cap the number of symbols the run may return
        try:
            raw_limit = int(criteria_raw.get("limit") or MAX_FILTER_SYMBOLS)
        except (TypeError, ValueError):
            raw_limit = MAX_FILTER_SYMBOLS
        criteria_raw["limit"] = max(1, min(raw_limit, MAX_FILTER_SYMBOLS))

        try:
            criteria = FilterCriteria(**criteria_raw)
        except Exception as exc:
            logger.exception(
                "Stored filter criteria are invalid for filter id=%s", filter_id
            )
            return JSONResponse(
                status_code=502,
                content={
                    "status": "error",
                    "detail": f"Stored filter criteria are invalid: {exc}",
                },
            )

        engine = get_filtering_engine()
        try:
            filter_result = await engine.filter_symbols(
                effective_market, criteria, use_cache=False
            )
            symbols = list(filter_result.symbols)[:MAX_FILTER_SYMBOLS]
            summary = {
                "symbols": symbols,
                "count": len(symbols),
                "filtered_count": filter_result.filtered_count,
                "total_count": filter_result.total_count,
                "execution_time_ms": filter_result.execution_time_ms,
                "market": effective_market,
                "limit": criteria_raw["limit"],
            }
        except Exception as exc:
            logger.exception(
                "FilteringEngine execution failed for filter id=%s", filter_id
            )
            return JSONResponse(
                status_code=502,
                content={
                    "status": "error",
                    "detail": f"Filter execution failed: {exc}",
                },
            )

        logger.info(
            "Filter run executed: filter='%s' id=%s market=%s matched=%s",
            filter_settings.name,
            filter_settings.id,
            effective_market,
            len(symbols),
        )

        # تحديث وقت التشغيل الأخير والنتائج (whole-dict reassignment)
        filter_settings.last_run = _utcnow()
        filter_settings.last_results = summary

        await db.commit()

        return {
            "message": "Filter executed successfully",
            "results": summary,
            "filter_name": filter_settings.name,
        }

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Unexpected failure running filter id=%s", filter_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


# ============================================================================
# المحافظ — Portfolios
# ============================================================================

@router.post("/portfolios", response_model=PortfolioResponse)
async def create_portfolio(
    portfolio_data: PortfolioCreate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """إنشاء محفظة جديدة

    Bug fix: the old code splatted the whole pydantic payload while also
    passing ``current_capital`` — a guaranteed duplicate-kwarg TypeError on
    every call. Fields are now built explicitly, and ``current_capital``
    starts equal to ``initial_capital``.
    """
    try:
        db_portfolio = Portfolio(
            user_id=current_user.id,
            name=portfolio_data.name,
            description=portfolio_data.description,
            initial_capital=portfolio_data.initial_capital,
            current_capital=portfolio_data.initial_capital,
            currency=portfolio_data.currency,
            risk_level=portfolio_data.risk_level,
            strategy_allocation=dict(copy.deepcopy(portfolio_data.strategy_allocation or {})),
        )

        db.add(db_portfolio)
        await db.commit()
        await db.refresh(db_portfolio)

        return db_portfolio

    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error creating portfolio for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to create portfolio for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/portfolios", response_model=List[PortfolioResponse])
async def get_portfolios(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على محافظ المستخدم"""
    try:
        stmt = select(Portfolio).where(Portfolio.user_id == current_user.id)

        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Portfolio.name.ilike(like),
                    Portfolio.description.ilike(like),
                )
            )

        stmt = stmt.order_by(Portfolio.id).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to list portfolios for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/portfolios/{portfolio_id}")
async def get_portfolio_by_id(
    portfolio_id: int,
    include_positions: bool = Query(False),
    include_transactions: bool = Query(False),
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على محفظة محددة (explicit dict — no ``__dict__`` leak)

    Positions/transactions are loaded eagerly with ``selectinload`` (lazy
    loading is not safely available on AsyncSession) and only when requested.
    """
    try:
        stmt = select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )

        options = []
        if include_positions:
            options.append(selectinload(Portfolio.positions))
        if include_transactions:
            options.append(selectinload(Portfolio.transactions))
        if options:
            stmt = stmt.options(*options)

        result = await db.execute(stmt)
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found",
            )

        positions = (
            [_position_dict(p) for p in portfolio.positions]
            if include_positions
            else []
        )
        transactions = (
            [_transaction_dict(t) for t in portfolio.transactions]
            if include_transactions
            else []
        )

        return _portfolio_dict(portfolio, positions, transactions)

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to fetch portfolio id=%s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.put("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: int,
    portfolio_data: PortfolioUpdate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """تحديث محفظة"""
    try:
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == current_user.id,
            )
        )
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found",
            )

        update_data = portfolio_data.model_dump(exclude_unset=True)
        _apply_update(portfolio, update_data)

        await db.commit()
        await db.refresh(portfolio)

        return portfolio

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error updating portfolio id=%s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to update portfolio id=%s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.delete("/portfolios/{portfolio_id}")
async def delete_portfolio(
    portfolio_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """حذف محفظة (positions/transactions removed via ORM cascade)"""
    try:
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == current_user.id,
            )
        )
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found",
            )

        await db.delete(portfolio)
        await db.commit()

        return {"message": "Portfolio deleted successfully"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to delete portfolio id=%s", portfolio_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


# ============================================================================
# مفاتيح API — API keys
# ============================================================================

@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    api_key_data: APIKeyCreate,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """إنشاء مفتاح API جديد

    Secrets are stored verbatim (encryption at rest is a separate task) and
    never returned: the APIKeyResponse model excludes api_key/api_secret.
    """
    try:
        # التحقق من صحة مفاتيح API (format check at creation time only)
        if not SecurityUtils.validate_api_key_format(api_key_data.api_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid API key format",
            )

        db_api_key = APIKey(
            user_id=current_user.id,
            name=api_key_data.name,
            exchange=api_key_data.exchange,
            api_key=api_key_data.api_key,
            api_secret=api_key_data.api_secret,
            permissions=list(api_key_data.permissions or ["read"]),
            is_active=True,
        )

        db.add(db_api_key)
        await db.commit()
        await db.refresh(db_api_key)

        return db_api_key

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        logger.exception("Integrity error creating API key for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database constraint error",
        )
    except Exception:
        await db.rollback()
        logger.exception("Failed to create API key for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/api-keys")
async def get_api_keys(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    exchange: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على مفاتيح API الخاصة بالمستخدم (masked DTOs)

    SECURITY FIX: the old implementation assigned masked values onto the ORM
    instances (``api_key.api_key = mask(...)``), which would persist corrupted
    masked secrets on the next flush. Responses are now explicit DTOs with
    masked fields — the ORM objects are never touched.
    """
    try:
        stmt = select(APIKey).where(APIKey.user_id == current_user.id)

        if exchange:
            stmt = stmt.where(APIKey.exchange == exchange)

        if is_active is not None:
            stmt = stmt.where(APIKey.is_active == is_active)

        stmt = stmt.order_by(APIKey.id).offset(skip).limit(limit)
        result = await db.execute(stmt)
        api_keys = result.scalars().all()

        return [_api_key_dto(api_key) for api_key in api_keys]

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to list API keys for user_id=%s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.get("/api-keys/{api_key_id}")
async def get_api_key_by_id(
    api_key_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """الحصول على مفتاح API محدد (masked DTO, scoped to owner)"""
    try:
        result = await db.execute(
            select(APIKey).where(
                APIKey.id == api_key_id,
                APIKey.user_id == current_user.id,
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )

        return _api_key_dto(api_key)

    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to fetch API key id=%s", api_key_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.put("/api-keys/{api_key_id}")
async def update_api_key(
    api_key_id: int,
    name: Optional[str] = None,
    permissions: Optional[List[str]] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """تحديث مفتاح API (metadata only — secrets are never updatable here)"""
    try:
        result = await db.execute(
            select(APIKey).where(
                APIKey.id == api_key_id,
                APIKey.user_id == current_user.id,
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )

        if name is not None:
            api_key.name = name

        if permissions is not None:
            # whole-list reassignment (JSON column, never in-place mutation)
            api_key.permissions = list(permissions)

        if is_active is not None:
            api_key.is_active = is_active

        await db.commit()

        return {"message": "API key updated successfully"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to update API key id=%s", api_key_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.delete("/api-keys/{api_key_id}")
async def delete_api_key(
    api_key_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """حذف مفتاح API"""
    try:
        result = await db.execute(
            select(APIKey).where(
                APIKey.id == api_key_id,
                APIKey.user_id == current_user.id,
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )

        await db.delete(api_key)
        await db.commit()

        return {"message": "API key deleted successfully"}

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Failed to delete API key id=%s", api_key_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )


@router.post("/api-keys/{api_key_id}/test")
async def test_api_key(
    api_key_id: int,
    current_user: User = Depends(AuthService.get_current_active_user_or_bypass),
    db: AsyncSession = Depends(get_db),
):
    """اختبار مفتاح API — REAL lightweight (offline) validation.

    No more fake "Connection successful". We validate format/length/permission
    semantics locally and honestly report the key as ``unverified`` — a live
    connectivity check requires per-exchange provider integration.
    """
    try:
        result = await db.execute(
            select(APIKey).where(
                APIKey.id == api_key_id,
                APIKey.user_id == current_user.id,
            )
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )

        if not api_key.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key is not active",
            )

        key_value = api_key.api_key or ""
        secret_value = api_key.api_secret or ""
        permissions = list(api_key.permissions or [])

        checks = {
            "api_key_format_valid": bool(key_value)
            and SecurityUtils.validate_api_key_format(key_value),
            "api_key_length": len(key_value),
            "api_secret_present": bool(secret_value),
            "api_secret_min_length": len(secret_value) >= 20,
            "permissions_valid": all(p in VALID_PERMISSIONS for p in permissions),
            "exchange_known": (api_key.exchange or "").lower() in KNOWN_EXCHANGES,
        }

        passed = bool(
            checks["api_key_format_valid"]
            and checks["api_secret_present"]
            and checks["api_secret_min_length"]
            and checks["permissions_valid"]
        )

        logger.info(
            "API key lightweight test: id=%s exchange=%s passed=%s checks=%s",
            api_key.id,
            api_key.exchange,
            passed,
            {k: v for k, v in checks.items() if isinstance(v, bool)},
        )

        # record that the key was exercised (no fake success is implied)
        api_key.last_used = _utcnow()
        await db.commit()

        return {
            "status": "unverified" if passed else "invalid",
            "message": (
                "unverified — live check requires provider integration"
                if passed
                else "API key failed lightweight offline validation"
            ),
            "exchange": api_key.exchange,
            "permissions": permissions,
            "checks": checks,
            "live_check": "not_performed — provider integration required",
            "tested_at": _utcnow().isoformat(),
        }

    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        logger.exception("Unexpected failure testing API key id=%s", api_key_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        )
