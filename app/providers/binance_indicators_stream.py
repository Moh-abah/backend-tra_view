# trading_backend/app/providers/binance_indicators_stream.py
"""
بث مؤشرات/شموع Binance عبر WebSocket مع كاش Redis.

العقد العام (يستخدمه راوتر /ws/indicators/{symbol}):
    await indicators_manager.add_symbol_monitoring(symbol, timeframe="1m")
    await indicators_manager.remove_symbol_monitoring(symbol)

- add_symbol_monitoring: idempotent — إضافة نفس الرمز مرتين عملية لا تُغيّر شيئاً.
- remove_symbol_monitoring: idempotent — إزالة رمز غير موجود عملية لا تُغيّر شيئاً.
- self.active_symbols = {symbol: {"timeframe": str, "clients": [websocket, ...]}}
"""

import asyncio
import json
import logging
from datetime import datetime

import redis.asyncio as aioredis
import websockets

from app.config import settings

logger = logging.getLogger(__name__)


class IndicatorWebSocketManager:
    def __init__(self):
        # {symbol: {"timeframe": str, "clients": [ws, ...]}}
        self.active_symbols: dict = {}
        # {symbol: asyncio.Task} مهمة اتصال Binance لكل رمز
        self.binance_connections: dict = {}
        # عميل Redis غير متزامن (يُنشأ كسولاً — لا يسد الـ event loop)
        self.redis_client = None

    # ------------------------------------------------------------------ #
    # Redis (async)
    # ------------------------------------------------------------------ #
    def _get_redis(self):
        if self.redis_client is None:
            self.redis_client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self.redis_client

    # ------------------------------------------------------------------ #
    # Public contract — used by routers
    # ------------------------------------------------------------------ #
    async def add_symbol_monitoring(self, symbol: str, timeframe: str = "1m"):
        """
        بدء مراقبة رمز على إطار زمني معيّن.

        Idempotent: إذا كان الرمز مراقباً بالفعل فلن يُنشأ اتصال ثانٍ.
        يبني/يحافظ على: self.active_symbols[symbol] = {"timeframe": ..., "clients": [...]}
        """
        if not symbol:
            return
        # حماية من نداءات قديمة تمرر إعدادات مؤشرات مكان الـ timeframe
        if not isinstance(timeframe, str) or not timeframe:
            timeframe = "1m"

        # نحافظ على الرمز كما مُرّر (نفس مفتاح active_symbols المتوقع في راوتر WebSocket)
        symbol = str(symbol).strip()

        existing = self.active_symbols.get(symbol)
        if existing:
            # موجود بالفعل — no-op (نضمن فقط وجود مفتاح clients كقائمة)
            if not isinstance(existing.get("clients"), list):
                existing["clients"] = []
            return

        self.active_symbols[symbol] = {"timeframe": timeframe, "clients": []}
        task = asyncio.create_task(self.connect_binance_stream(symbol, timeframe))
        self.binance_connections[symbol] = task
        logger.info("📡 Started monitoring %s (%s)", symbol, timeframe)

    async def remove_symbol_monitoring(self, symbol: str):
        """
        إيقاف مراقبة رمز.

        Idempotent: إزالة رمز غير مراقب لا تفعل شيئاً ولا ترفع خطأ.
        """
        if not symbol:
            return

        symbol = str(symbol).strip()

        removed = self.active_symbols.pop(symbol, None)
        task = self.binance_connections.pop(symbol, None)

        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Error while stopping monitoring task for %s", symbol)

        if removed is not None:
            logger.info("🛑 Stopped monitoring %s", symbol)

    # ------------------------------------------------------------------ #
    # Binance streaming
    # ------------------------------------------------------------------ #
    async def connect_binance_stream(self, symbol: str, timeframe: str = "1m"):
        """الاتصال بـ Binance WebSocket مع إعادة اتصال تلقائية، ويتوقف عند إزالة الرمز."""
        binance_ws_url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{timeframe}"

        while symbol in self.active_symbols:
            try:
                async with websockets.connect(binance_ws_url) as ws:
                    async for message in ws:
                        if symbol not in self.active_symbols:
                            return
                        try:
                            kline_data = json.loads(message)
                            await self.process_new_kline(symbol, kline_data)
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            logger.exception("Error processing kline for %s", symbol)
                            continue
            except asyncio.CancelledError:
                # إيقاف مقصود (remove_symbol_monitoring)
                raise
            except Exception as e:
                if symbol not in self.active_symbols:
                    return
                logger.warning("WebSocket error for %s: %s, reconnecting in 5s...", symbol, e)
                await asyncio.sleep(5)

    async def process_new_kline(self, symbol: str, kline_data: dict):
        """معالجة شمعة جديدة"""
        candle = {
            'timestamp': datetime.fromtimestamp(kline_data['k']['t'] / 1000),
            'open': float(kline_data['k']['o']),
            'high': float(kline_data['k']['h']),
            'low': float(kline_data['k']['l']),
            'close': float(kline_data['k']['c']),
            'volume': float(kline_data['k']['v']),
            'is_closed': kline_data['k']['x']
        }

        if candle['is_closed']:
            # تحديث الكاش (Redis async — لا يسد الـ loop؛ وفشل Redis لا يمنع الإشعار)
            try:
                redis = self._get_redis()
                cache_key = f"kline:{symbol}:1m"
                cached = await redis.get(cache_key)

                candles = json.loads(cached) if cached else []
                candles.append(candle)
                if len(candles) > 500:
                    candles.pop(0)

                await redis.setex(cache_key, 3600, json.dumps(candles, default=str))
            except Exception:
                logger.exception("Redis cache update failed for %s", symbol)

            # إعلام جميع المشتركين
            await self.notify_subscribers(symbol, candle)

    async def notify_subscribers(self, symbol: str, new_candle: dict):
        """إرسال تحديث للمشتركين"""
        entry = self.active_symbols.get(symbol)
        if not entry:
            return

        update_msg = json.dumps({
            "type": "new_candle",
            "symbol": symbol,
            "candle": new_candle,
            "timestamp": datetime.utcnow().isoformat()
        }, default=str)

        # المرور على نسخة حتى نتمكن من إزالة العملاء الفاشلين بأمان
        for client in list(entry.get("clients", [])):
            try:
                await client.send_text(update_msg)
            except Exception:
                try:
                    entry["clients"].remove(client)
                except ValueError:
                    pass


# إنشاء النسخة الوحيدة
indicators_manager = IndicatorWebSocketManager()
