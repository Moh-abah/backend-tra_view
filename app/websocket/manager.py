from fastapi import WebSocket, WebSocketDisconnect
from typing import Any, Dict, Set, Optional
import json
from datetime import datetime

from .stream_handler import RealTimeStreamHandler
from app.services.data_service import DataService
from app.services.filtering import FilteringEngine

class WebSocketManager:
    """مدير اتصالات WebSocket المحدث"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.stream_handler: Optional[RealTimeStreamHandler] = None
        
    def initialize(self, data_service: DataService, filtering_engine: FilteringEngine):
        """تهيئة معالج البث"""
        self.stream_handler = RealTimeStreamHandler(data_service, filtering_engine)
    
    async def connect(self, websocket: WebSocket, channel: str):
        """قبول اتصال WebSocket جديد"""
        await websocket.accept()
        
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        
        self.active_connections[channel].add(websocket)
    
    def disconnect(self, websocket: WebSocket, channel: str):
        """قطع اتصال WebSocket"""
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)
        
        # إلغاء الاشتراك من جميع البثوث
        if self.stream_handler:
            for stream_id in self.stream_handler.subscribers:
                if websocket in self.stream_handler.subscribers[stream_id]:
                    self.stream_handler.subscribers[stream_id].discard(websocket)
    
    async def handle_stream_connection(
        self,
        websocket: WebSocket,
        symbol: str,
        timeframe: str,
        market: str = "crypto",
        indicators_config: Optional[str] = None,
        strategy_config: Optional[str] = None
    ):
        """معالجة اتصال بث لحظي"""
        if not self.stream_handler:
            await websocket.close(code=1000, reason="Stream handler not initialized")
            return
        
        # تحويل البيانات من JSON
        try:
            indicators = json.loads(indicators_config) if indicators_config else []
            strategy = json.loads(strategy_config) if strategy_config else None
        except json.JSONDecodeError as e:
            await websocket.close(code=1003, reason=f"Invalid JSON: {str(e)}")
            return
        
        # بدء البث
        stream_id = await self.stream_handler.start_stream(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            indicators_config=indicators,
            strategy_config=strategy
        )
        
        # اشتراك العميل في البث
        await self.stream_handler.subscribe(stream_id, websocket)
        
        channel = f"stream:{stream_id}"
        await self.connect(websocket, channel)
        
        try:
            # الاستماع للأوامر من العميل
            while True:
                data = await websocket.receive_text()
                
                try:
                    command = json.loads(data)
                    await self._handle_client_command(websocket, stream_id, command)
                except json.JSONDecodeError:
                    pass
                    
        except WebSocketDisconnect:
            print(f"Client disconnected from stream {stream_id}")
            self.disconnect(websocket, channel)
            await self.stream_handler.unsubscribe(stream_id, websocket)
            
            # إذا لم يكن هناك مشتركون، إيقاف البث
            if stream_id in self.stream_handler.subscribers and not self.stream_handler.subscribers[stream_id]:
                await self.stream_handler.stop_stream(stream_id)
                
        except Exception as e:
            print(f"Error in stream connection: {e}")
            self.disconnect(websocket, channel)
            await self.stream_handler.unsubscribe(stream_id, websocket)
    
    async def _handle_client_command(
        self,
        websocket: WebSocket,
        stream_id: str,
        command: Dict[str, Any]
    ):
        """معالجة أوامر من العميل"""
        cmd_type = command.get("type")
        
        if not self.stream_handler:
            return
        
        if cmd_type == "update_indicators":
            # تحديث المؤشرات
            indicators = command.get("indicators", [])
            stream_info = self.stream_handler.active_streams.get(stream_id)
            if stream_info:
                stream_info["indicators_config"] = indicators
            
        elif cmd_type == "update_strategy":
            # تحديث الإستراتيجية
            strategy = command.get("strategy_config")
            stream_info = self.stream_handler.active_streams.get(stream_id)
            if stream_info:
                stream_info["strategy_config"] = strategy
            
        elif cmd_type == "pause_stream":
            # إيقاف البث مؤقتاً
            stream_info = self.stream_handler.active_streams.get(stream_id)
            if stream_info:
                stream_info["status"] = "paused"
            
        elif cmd_type == "resume_stream":
            # استئناف البث
            stream_info = self.stream_handler.active_streams.get(stream_id)
            if stream_info:
                stream_info["status"] = "running"
            
        elif cmd_type == "get_stream_info":
            # الحصول على معلومات البث
            info = self.stream_handler.get_stream_info(stream_id)
            await websocket.send_json({
                "type": "stream_info",
                "data": info,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        elif cmd_type == "ping":
            # الرد على ping
            await websocket.send_json({
                "type": "pong",
                "timestamp": datetime.utcnow().isoformat()
            })

manager = WebSocketManager()