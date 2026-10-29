# app/services/indicator_state_service.py
import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Anchor the sqlite file to the backend root instead of the process CWD so the
# service behaves identically regardless of where uvicorn/celery is launched.
_DB_PATH = Path(__file__).resolve().parents[2] / "indicators_state.db"

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS indicator_states (
        symbol TEXT PRIMARY KEY,
        indicators_json TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
"""


class IndicatorStateService:

    # ==================== Sync sqlite helpers (run in a thread) ====================
    # Sync sqlite3 blocks the event loop, so every DB access is executed via
    # asyncio.to_thread() from the async methods below.

    def _load_all_active_monitoring_sync(self) -> list:
        """(sync, thread-only) Load all monitored symbols from SQLite."""
        conn = sqlite3.connect(_DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.execute(_CREATE_TABLE_SQL)
            cursor.execute("SELECT symbol, indicators_json FROM indicator_states")
            rows = cursor.fetchall()
        finally:
            conn.close()

        active_symbols = []
        for symbol, indicators_json in rows:
            try:
                indicators = json.loads(indicators_json) if indicators_json else []
            except (TypeError, ValueError) as e:
                logger.warning(f"Corrupt indicators JSON for '{symbol}': {e}")
                indicators = []
            active_symbols.append({
                "symbol": symbol,
                "indicators": indicators,
                "is_active": True
            })
        return active_symbols

    def _save_to_permanent_storage_sync(self, symbol: str, indicators: list) -> None:
        """(sync, thread-only) Persist one monitored symbol to SQLite."""
        conn = sqlite3.connect(_DB_PATH)
        try:
            cursor = conn.cursor()
            cursor.execute(_CREATE_TABLE_SQL)
            cursor.execute(
                """
                INSERT OR REPLACE INTO indicator_states
                (symbol, indicators_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (symbol, json.dumps(indicators), datetime.utcnow()),
            )
            conn.commit()
        finally:
            conn.close()

    # ==================== Async API ====================

    async def save_active_monitoring(self, symbol: str, indicators: list):
        """حفظ الرموز تحت المراقبة ومؤشراتها"""
        await asyncio.to_thread(self._save_to_permanent_storage_sync, symbol, list(indicators))

    async def load_all_active_monitoring(self):
        """تحميل جميع الرموز تحت المراقبة"""
        return await asyncio.to_thread(self._load_all_active_monitoring_sync)

    async def save_to_permanent_storage(self, symbol: str, data: dict):
        """حفظ دائم في SQLite (يحافظ على العقد القديم: dict فيه 'indicators')"""
        indicators = data.get("indicators", []) if isinstance(data, dict) else []
        await asyncio.to_thread(self._save_to_permanent_storage_sync, symbol, list(indicators))

    async def resume_monitoring_on_startup(self):
        """
        استئناف المراقبة عند إعادة تشغيل السيرفر.

        Safety contract (bugfix): this runs during startup, so it must NEVER
        raise — any failure is logged and startup continues.
        """
        try:
            active_symbols = await self.load_all_active_monitoring()
        except Exception as e:
            logger.exception(f"Failed to load persisted indicator states: {e}")
            return

        if not active_symbols:
            logger.info("No persisted indicator states to resume")
            return

        from app.providers.binance_indicators_stream import indicators_manager

        resumed = 0
        for symbol_data in active_symbols:
            symbol = symbol_data.get("symbol")
            if not symbol:
                continue
            try:
                add_monitoring = getattr(indicators_manager, "add_symbol_monitoring", None)
                if add_monitoring is None:
                    logger.warning(
                        "indicators_manager has no add_symbol_monitoring(); "
                        f"cannot resume monitoring for {symbol}"
                    )
                    continue
                # Contract (binance_indicators_stream): add_symbol_monitoring(
                #   symbol, timeframe="1m") / remove_symbol_monitoring(symbol)
                await add_monitoring(symbol, timeframe="1m")
                resumed += 1
                logger.info(f"Resumed monitoring for {symbol}")
            except Exception as e:
                # One bad symbol must never abort resuming the rest (or startup).
                logger.exception(f"Failed to resume monitoring for {symbol}: {e}")

        logger.info(f"Indicator monitoring resume finished: {resumed}/{len(active_symbols)} symbols")


# إنشاء النسخة الوحيدة
state_service = IndicatorStateService()
