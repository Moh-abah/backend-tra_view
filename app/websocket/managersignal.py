# from typing import Dict, List
# from fastapi import WebSocket
# import json
# import asyncio

# class ConnectionManager:
#     def __init__(self):
#         self.active_connections: Dict[str, List[WebSocket]] = {
#             "signals": [],
#             "alerts": [],
#             "prices": []
#         }
    
#     async def connect(self, websocket: WebSocket):
#         await websocket.accept()
#         # إضافة إلى القناة الافتراضية
#         self.active_connections["signals"].append(websocket)
    
#     def disconnect(self, websocket: WebSocket):
#         for channel in self.active_connections.values():
#             if websocket in channel:
#                 channel.remove(websocket)
    
#     async def subscribe(self, websocket: WebSocket, channel: str):
#         if channel in self.active_connections:
#             if websocket not in self.active_connections[channel]:
#                 self.active_connections[channel].append(websocket)
    
#     async def unsubscribe(self, websocket: WebSocket, channel: str):
#         if channel in self.active_connections:
#             if websocket in self.active_connections[channel]:
#                 self.active_connections[channel].remove(websocket)
    
#     async def broadcast_signal(self, signal: dict):
#         """بث إشارة جديدة لجميع المشتركين"""
#         message = {
#             "type": "signal_update",
#             "data": signal,
#             "timestamp": datetime.utcnow().isoformat()
#         }
        
#         await self._broadcast_to_channel("signals", message)
    
#     async def broadcast_price_update(self, symbol: str, price: float):
#         """بث تحديث سعر"""
#         message = {
#             "type": "price_update",
#             "symbol": symbol,
#             "price": price,
#             "timestamp": datetime.utcnow().isoformat()
#         }
        
#         await self._broadcast_to_channel("prices", message)
    
#     async def _broadcast_to_channel(self, channel: str, message: dict):
#         if channel in self.active_connections:
#             disconnected = []
            
#             for connection in self.active_connections[channel]:
#                 try:
#                     await connection.send_json(message)
#                 except Exception:
#                     disconnected.append(connection)
            
#             # إزالة الاتصالات المقطوعة
#             for connection in disconnected:
#                 self.active_connections[channel].remove(connection)