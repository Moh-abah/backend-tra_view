# app/providers/stock_websocket.py
import asyncio
import json
import logging
from typing import Dict, List, Set, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed
from fastapi import WebSocket, WebSocketDisconnect

from .yahoo_client import YahooFinanceClient
from .us_stock_provider import USStockProvider

logger = logging.getLogger(__name__)


class StockWebSocketManager:
    """مدير WebSocket للأسهم الأمريكية - يدعم تعدد المستخدمين والرموز"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        self.subscription_data: Dict[WebSocket, Set[str]] = defaultdict(set)
        self.yahoo_client = YahooFinanceClient()
        self.us_provider = USStockProvider()
        
        # بيانات في الذاكرة للكاش السريع
        self.price_cache: Dict[str, Dict] = {}
        self.cache_timestamps: Dict[str, datetime] = {}
        
        # إحصائيات
        self.stats = {
            "total_connections": 0,
            "active_symbols": set(),
            "messages_sent": 0,
            "start_time": datetime.utcnow()
        }
        
        logger.info("✅ StockWebSocketManager initialized")
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """اتصال عميل جديد"""
        await websocket.accept()
        self.active_connections[client_id].add(websocket)
        self.stats["total_connections"] += 1
        
        logger.info(f"📡 Client connected: {client_id}")
        
        # إرسال رسالة ترحيب
        await self.send_personal_message({
            "type": "system",
            "event": "connected",
            "client_id": client_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Connected to Stock WebSocket server"
        }, websocket)
    
    def disconnect(self, websocket: WebSocket, client_id: str):
        """فصل عميل"""
        if websocket in self.active_connections[client_id]:
            self.active_connections[client_id].remove(websocket)
            
            # تنظيف الاشتراكات
            if websocket in self.subscription_data:
                subscribed_symbols = self.subscription_data.pop(websocket)
                for symbol in subscribed_symbols:
                    self._cleanup_symbol(symbol)
        
        if not self.active_connections[client_id]:
            del self.active_connections[client_id]
        
        logger.info(f"📡 Client disconnected: {client_id}")
    
    async def send_personal_message(self, message: Dict, websocket: WebSocket):
        """إرسال رسالة لعميل محدد"""
        try:
            await websocket.send_json(message)
            self.stats["messages_sent"] += 1
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def broadcast_to_symbol(self, symbol: str, message: Dict):
        """بث رسالة لجميع المشتركين في رمز معين"""
        connections_to_send = set()
        
        # البحث عن جميع الاتصالات المشتركة في هذا الرمز
        for websocket, symbols in self.subscription_data.items():
            if symbol in symbols:
                connections_to_send.add(websocket)
        
        # إرسال الرسالة لجميع الاتصالات
        for websocket in connections_to_send:
            await self.send_personal_message(message, websocket)
    
    async def handle_message(self, websocket: WebSocket, client_id: str, data: Dict):
        """معالجة الرسالة الواردة من العميل"""
        message_type = data.get("type")
        
        try:
            if message_type == "subscribe":
                await self.handle_subscribe(websocket, client_id, data)
            
            elif message_type == "unsubscribe":
                await self.handle_unsubscribe(websocket, client_id, data)
            
            elif message_type == "ping":
                await self.send_personal_message({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat()
                }, websocket)
            
            elif message_type == "get_historical":
                await self.handle_get_historical(websocket, client_id, data)
            
            elif message_type == "get_indicators":
                await self.handle_get_indicators(websocket, client_id, data)
            
            elif message_type == "get_candles":
                await self.handle_get_candles(websocket, client_id, data)
            
            elif message_type == "search":
                await self.handle_search(websocket, client_id, data)
            
            else:
                await self.send_personal_message({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}"
                }, websocket)
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self.send_personal_message({
                "type": "error",
                "message": str(e)
            }, websocket)
    
    async def handle_subscribe(self, websocket: WebSocket, client_id: str, data: Dict):
        """معالجة طلب الاشتراك في رمز"""
        symbol = data.get("symbol", "").upper()
        timeframe = data.get("timeframe", "1m")
        
        if not symbol:
            await self.send_personal_message({
                "type": "error",
                "message": "Symbol is required for subscription"
            }, websocket)
            return
        
        # إضافة الاشتراك
        self.subscription_data[websocket].add(symbol)
        self.stats["active_symbols"].add(symbol)
        
        logger.info(f"📊 Client {client_id} subscribed to {symbol} ({timeframe})")
        
        # إرسال تأكيد الاشتراك
        await self.send_personal_message({
            "type": "subscription",
            "event": "subscribed",
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
        
        # إرسال بيانات أولية
        await self.send_initial_data(websocket, symbol, timeframe)
    
    async def handle_unsubscribe(self, websocket: WebSocket, client_id: str, data: Dict):
        """معالجة طلب إلغاء الاشتراك"""
        symbol = data.get("symbol", "").upper()
        
        if symbol and websocket in self.subscription_data:
            if symbol in self.subscription_data[websocket]:
                self.subscription_data[websocket].remove(symbol)
                self._cleanup_symbol(symbol)
        
        await self.send_personal_message({
            "type": "subscription",
            "event": "unsubscribed",
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
    
    async def handle_get_historical(self, websocket: WebSocket, client_id: str, data: Dict):
        """الحصول على البيانات التاريخية"""
        symbol = data.get("symbol", "").upper()
        timeframe = data.get("timeframe", "1d")
        limit = data.get("limit", 100)
        
        if not symbol:
            await self.send_personal_message({
                "type": "error",
                "message": "Symbol is required"
            }, websocket)
            return
        
        try:
            # الحصول على البيانات التاريخية
            df = await self.yahoo_client.get_historical_data(
                symbol=symbol,
                interval=timeframe,
                period=f"{limit}d" if limit <= 365 else "max"
            )
            
            if df.empty:
                await self.send_personal_message({
                    "type": "historical_data",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "data": [],
                    "message": "No data available"
                }, websocket)
                return
            
            # تحويل DataFrame إلى قائمة
            candles = []
            for idx, row in df.iterrows():
                candles.append({
                    "time": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                    "open": float(row['open']),
                    "high": float(row['high']),
                    "low": float(row['low']),
                    "close": float(row['close']),
                    "volume": int(row['volume'])
                })
            
            # إرسال البيانات
            await self.send_personal_message({
                "type": "historical_data",
                "symbol": symbol,
                "timeframe": timeframe,
                "data": candles[-limit:],  # آخر 'limit' شمعة
                "count": len(candles[-limit:]),
                "timestamp": datetime.utcnow().isoformat()
            }, websocket)
            
        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            await self.send_personal_message({
                "type": "error",
                "message": f"Failed to get historical data: {str(e)}"
            }, websocket)
    
    async def handle_get_indicators(self, websocket: WebSocket, client_id: str, data: Dict):
        """الحصول على المؤشرات الفنية"""
        symbol = data.get("symbol", "").upper()
        timeframe = data.get("timeframe", "1d")
        indicators = data.get("indicators", [
            {"name": "sma", "params": {"period": 20}},
            {"name": "rsi", "params": {"period": 14}}
        ])
        
        if not symbol:
            await self.send_personal_message({
                "type": "error",
                "message": "Symbol is required"
            }, websocket)
            return
        
        try:
            # الحصول على البيانات
            df = await self.yahoo_client.get_historical_data(
                symbol=symbol,
                interval=timeframe,
                period="3mo"
            )
            
            if df.empty:
                await self.send_personal_message({
                    "type": "indicators",
                    "symbol": symbol,
                    "indicators": {},
                    "message": "No data available"
                }, websocket)
                return
            
            # حساب المؤشرات
            indicator_results = await self.yahoo_client.calculate_indicators(df, indicators)
            
            # تحويل النتائج
            processed_results = {}
            for name, result in indicator_results.items():
                if isinstance(result, dict):
                    processed_results[name] = {}
                    for key, series in result.items():
                        processed_results[name][key] = series.dropna().to_dict()
                elif hasattr(result, 'to_dict'):
                    processed_results[name] = result.dropna().to_dict()
                else:
                    processed_results[name] = result
            
            await self.send_personal_message({
                "type": "indicators",
                "symbol": symbol,
                "timeframe": timeframe,
                "indicators": processed_results,
                "timestamp": datetime.utcnow().isoformat()
            }, websocket)
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            await self.send_personal_message({
                "type": "error",
                "message": f"Failed to calculate indicators: {str(e)}"
            }, websocket)
    
    async def handle_get_candles(self, websocket: WebSocket, client_id: str, data: Dict):
        """الحصول على الشموع مع المؤشرات"""
        symbol = data.get("symbol", "").upper()
        timeframe = data.get("timeframe", "1d")
        limit = data.get("limit", 100)
        
        if not symbol:
            await self.send_personal_message({
                "type": "error",
                "message": "Symbol is required"
            }, websocket)
            return
        
        try:
            # الحصول على البيانات من مزود الأسهم
            chart_data = await self.us_provider.get_chart_data(
                symbol=symbol,
                timeframe=timeframe,
                period=f"{limit}d"
            )
            
            await self.send_personal_message({
                "type": "candles",
                "symbol": symbol,
                "timeframe": timeframe,
                **chart_data
            }, websocket)
            
        except Exception as e:
            logger.error(f"Error getting candles: {e}")
            await self.send_personal_message({
                "type": "error",
                "message": f"Failed to get candles: {str(e)}"
            }, websocket)
    
    async def handle_search(self, websocket: WebSocket, client_id: str, data: Dict):
        """البحث عن الأسهم"""
        query = data.get("query", "")
        
        if not query or len(query) < 2:
            await self.send_personal_message({
                "type": "search_results",
                "results": [],
                "message": "Query too short"
            }, websocket)
            return
        
        try:
            results = await self.us_provider.search_stocks(query)
            
            await self.send_personal_message({
                "type": "search_results",
                "query": query,
                "results": results[:20],  # أول 20 نتيجة
                "count": len(results),
                "timestamp": datetime.utcnow().isoformat()
            }, websocket)
            
        except Exception as e:
            logger.error(f"Error searching stocks: {e}")
            await self.send_personal_message({
                "type": "error",
                "message": f"Search failed: {str(e)}"
            }, websocket)
    
    async def send_initial_data(self, websocket: WebSocket, symbol: str, timeframe: str):
        """إرسال البيانات الأولية عند الاشتراك"""
        try:
            # الحصول على الاقتباس الحي
            quote = await self.yahoo_client.get_live_quote(symbol)
            
            # الحصول على آخر 50 شمعة
            df = await self.yahoo_client.get_historical_data(
                symbol=symbol,
                interval=timeframe,
                period="7d" if timeframe in ["1m", "5m", "15m", "30m", "1h"] else "1mo"
            )
            
            candles = []
            if not df.empty:
                for idx, row in df.iterrows():
                    candles.append({
                        "time": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                        "open": float(row['open']),
                        "high": float(row['high']),
                        "low": float(row['low']),
                        "close": float(row['close']),
                        "volume": int(row['volume'])
                    })
            
            await self.send_personal_message({
                "type": "initial_data",
                "symbol": symbol,
                "timeframe": timeframe,
                "quote": quote,
                "candles": candles[-50:],  # آخر 50 شمعة
                "timestamp": datetime.utcnow().isoformat()
            }, websocket)
            
        except Exception as e:
            logger.error(f"Error sending initial data: {e}")
    
    def _cleanup_symbol(self, symbol: str):
        """تنظيف الرمز إذا لم يعد له مشتركون"""
        has_subscribers = False
        
        for symbols in self.subscription_data.values():
            if symbol in symbols:
                has_subscribers = True
                break
        
        if not has_subscribers:
            self.stats["active_symbols"].discard(symbol)
            if symbol in self.price_cache:
                del self.price_cache[symbol]
            if symbol in self.cache_timestamps:
                del self.cache_timestamps[symbol]
    
    async def update_price(self, symbol: str):
        """تحديث سعر رمز معين وإرساله للمشتركين"""
        try:
            # الحصول على السعر الحي
            quote = await self.yahoo_client.get_live_quote(symbol)
            
            # تحديث الكاش
            self.price_cache[symbol] = quote
            self.cache_timestamps[symbol] = datetime.utcnow()
            
            # إعداد رسالة تحديث السعر
            message = {
                "type": "price_update",
                "symbol": symbol,
                "price": quote.get("price", 0),
                "change": quote.get("change", 0),
                "change_percent": quote.get("change_percent", 0),
                "volume": quote.get("volume", 0),
                "timestamp": quote.get("timestamp", datetime.utcnow().isoformat()),
                "bid": quote.get("bid", 0),
                "ask": quote.get("ask", 0),
                "open": quote.get("open", 0),
                "high": quote.get("high", 0),
                "low": quote.get("low", 0)
            }
            
            # بث التحديث لجميع المشتركين
            await self.broadcast_to_symbol(symbol, message)
            
            # إرسال تحديث الشمعة كل فترة (محاكاة)
            if symbol in self.stats["active_symbols"]:
                await self._send_candle_update(symbol)
            
        except Exception as e:
            logger.error(f"Error updating price for {symbol}: {e}")
    
    async def _send_candle_update(self, symbol: str):
        """إرسال تحديث للشمعة (محاكاة لتكوين شمعة جديدة)"""
        # هذه محاكاة، في النظام الحقيقي ستأتي البيانات من مصدر حي
        if symbol in self.price_cache:
            quote = self.price_cache[symbol]
            
            candle_update = {
                "type": "candle_update",
                "symbol": symbol,
                "price": quote.get("price", 0),
                "volume": quote.get("volume", 0),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self.broadcast_to_symbol(symbol, candle_update)
    
    async def get_stats(self) -> Dict:
        """الحصول على إحصائيات النظام"""
        return {
            "active_connections": sum(len(conns) for conns in self.active_connections.values()),
            "active_symbols": list(self.stats["active_symbols"]),
            "total_symbols_subscribed": len(self.stats["active_symbols"]),
            "messages_sent": self.stats["messages_sent"],
            "uptime": str(datetime.utcnow() - self.stats["start_time"]),
            "cache_size": len(self.price_cache),
            "clients": list(self.active_connections.keys())
        }
    
    async def broadcast_system_message(self, message: str, event_type: str = "info"):
        """بث رسالة نظام لجميع المتصلين"""
        system_message = {
            "type": "system",
            "event": event_type,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for connections in self.active_connections.values():
            for websocket in connections:
                try:
                    await self.send_personal_message(system_message, websocket)
                except:
                    pass


# ==================== WebSocket Background Task ====================

class StockWebSocketTask:
    """مهمة خلفية لإدارة تحديثات WebSocket"""
    
    def __init__(self, manager: StockWebSocketManager):
        self.manager = manager
        self.update_interval = 5  # تحديث كل 5 ثواني
        self.is_running = False
        self.task = None
        
    async def start(self):
        """بدء مهمة التحديث"""
        if self.is_running:
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._update_loop())
        logger.info("✅ StockWebSocketTask started")
    
    async def stop(self):
        """إيقاف مهمة التحديث"""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 StockWebSocketTask stopped")
    
    async def _update_loop(self):
        """حلقة التحديث الرئيسية"""
        while self.is_running:
            try:
                # تحديث الأسعار للرموز النشطة
                active_symbols = list(self.manager.stats["active_symbols"])
                
                for symbol in active_symbols:
                    await self.manager.update_price(symbol)
                
                # انتظار الفترة المحددة
                await asyncio.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Error in update loop: {e}")
                await asyncio.sleep(1)
    
    def set_update_interval(self, interval: int):
        """تحديث الفترة الزمنية للتحديث"""
        self.update_interval = interval
        logger.info(f"🔄 Update interval changed to {interval} seconds")


# ==================== FastAPI WebSocket Endpoint ====================


# ==================== التصدير (Exports) ====================

# هذه المتغيرات ستكون متاحة للاستيراد
__all__ = [
    "StockWebSocketManager",
    "StockWebSocketTask",
    "stock_websocket_manager",  # أضف هذا
    "stock_websocket_task",     # أضف هذا
    "stock_websocket_endpoint", # أضف هذا
    "start_stock_websocket_task", # أضف هذا
    "stop_stock_websocket_task",  # أضف هذا
    "get_stock_websocket_manager", # أضف هذا
    "get_stock_websocket_task"     # أضف هذا
]


# إنشاء نسخة عامة من Manager
stock_websocket_manager = StockWebSocketManager()
stock_websocket_task = StockWebSocketTask(stock_websocket_manager)


async def stock_websocket_endpoint(websocket: WebSocket, client_id: str = "anonymous"):
    """
    نقطة نهاية WebSocket للأسهم الأمريكية
    """
    await stock_websocket_manager.connect(websocket, client_id)
    
    try:
        while True:
            # استقبال البيانات من العميل
            data = await websocket.receive_json()
            
            # معالجة الرسالة
            await stock_websocket_manager.handle_message(websocket, client_id, data)
            
    except WebSocketDisconnect:
        stock_websocket_manager.disconnect(websocket, client_id)
    
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        stock_websocket_manager.disconnect(websocket, client_id)


# ==================== وظائف مساعدة ====================

async def start_stock_websocket_task():
    """بدء مهمة WebSocket عند بدء التطبيق"""
    await stock_websocket_task.start()

async def stop_stock_websocket_task():
    """إيقاف مهمة WebSocket عند إيقاف التطبيق"""
    await stock_websocket_task.stop()

def get_stock_websocket_manager() -> StockWebSocketManager:
    """الحصول على مدير WebSocket"""
    return stock_websocket_manager

def get_stock_websocket_task() -> StockWebSocketTask:
    """الحصول على مهمة WebSocket"""
    return stock_websocket_task