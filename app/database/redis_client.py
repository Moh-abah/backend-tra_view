"""Fail-safe async Redis client.

Every public method degrades gracefully: on any error (missing REDIS_URL,
connection failure, timeout, serialization problem) it logs a warning and
returns ``None``/``False`` instead of raising, so a dead Redis never takes
down request handling. The connection is created lazily on first use.
"""

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Lazy, never-raising wrapper around redis.asyncio."""

    def __init__(self) -> None:
        self.redis: Optional[redis.Redis] = None
        self._connect_failed_logged = False

    async def connect(self) -> bool:
        """Establish the connection lazily. Returns True on success."""
        try:
            if self.redis is not None:
                return True
            if not settings.REDIS_URL:
                if not self._connect_failed_logged:
                    logger.warning("REDIS_URL is not configured — cache disabled")
                    self._connect_failed_logged = True
                return False
            self.redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
            await self.redis.ping()
            self._connect_failed_logged = False
            return True
        except Exception as exc:  # noqa: BLE001 — must never raise
            self.redis = None
            if not self._connect_failed_logged:
                logger.warning("Redis connect failed (cache disabled): %s", exc)
                self._connect_failed_logged = True
            return False

    async def disconnect(self) -> None:
        """Close the connection if open; never raises."""
        try:
            if self.redis is not None:
                await self.redis.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis disconnect error: %s", exc)
        finally:
            self.redis = None

    async def ping(self) -> bool:
        """Return True if Redis is reachable, False otherwise. Never raises."""
        try:
            if self.redis is None and not await self.connect():
                return False
            return bool(await self.redis.ping())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis ping failed: %s", exc)
            self.redis = None
            return False

    async def get_cached(self, key: str) -> Optional[Any]:
        """Fetch a JSON-serialized value; None on miss or any failure."""
        try:
            if self.redis is None and not await self.connect():
                return None
            data = await self.redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis get_cached('%s') failed: %s", key, exc)
            self.redis = None
            return None

    async def set_cached(self, key: str, value, expire: int = 300) -> bool:
        """Store a value as JSON with TTL; returns True on success."""
        try:
            if self.redis is None and not await self.connect():
                return False
            await self.redis.setex(key, expire, json.dumps(value))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis set_cached('%s') failed: %s", key, exc)
            self.redis = None
            return False

    async def delete_cached(self, key: str) -> bool:
        """Delete a key; returns True if it existed, False otherwise/failure."""
        try:
            if self.redis is None and not await self.connect():
                return False
            return bool(await self.redis.delete(key))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis delete_cached('%s') failed: %s", key, exc)
            self.redis = None
            return False


redis_client = RedisClient()
