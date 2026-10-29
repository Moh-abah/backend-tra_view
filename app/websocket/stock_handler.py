# app/websocket/stock_handler.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Optional, Dict
import uuid
import logging
from datetime import datetime

from app.providers.stock_websocket import (
    stock_websocket_endpoint,
    stock_websocket_manager,
    start_stock_websocket_task,
    stop_stock_websocket_task
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/stocks/{client_id}")
async def stocks_websocket(
    websocket: WebSocket,
    client_id: str
):
    """
    WebSocket endpoint للأسهم الأمريكية
    
    تنسيق الرسائل:
    
    1. الاشتراك:
        {
            "type": "subscribe",
            "symbol": "AAPL",
            "timeframe": "1m"
        }
    
    2. إلغاء الاشتراك:
        {
            "type": "unsubscribe", 
            "symbol": "AAPL"
        }
    
    3. الحصول على بيانات تاريخية:
        {
            "type": "get_historical",
            "symbol": "AAPL",
            "timeframe": "1d",
            "limit": 100
        }
    
    4. الحصول على مؤشرات:
        {
            "type": "get_indicators",
            "symbol": "AAPL",
            "timeframe": "1d",
            "indicators": [
                {"name": "sma", "params": {"period": 20}},
                {"name": "rsi", "params": {"period": 14}}
            ]
        }
    
    5. البحث:
        {
            "type": "search",
            "query": "apple"
        }
    
    6. ping/pong:
        {"type": "ping"}
    """
    await stock_websocket_endpoint(websocket, client_id)


@router.get("/ws/stats")
async def get_websocket_stats():
    """الحصول على إحصائيات WebSocket"""
    stats = await stock_websocket_manager.get_stats()
    
    return {
        "status": "active",
        "stats": stats,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/ws/start-task")
async def start_background_task():
    """بدء مهمة تحديث WebSocket (للتشغيل اليدوي)"""
    await start_stock_websocket_task()
    
    return {
        "status": "started",
        "message": "WebSocket background task started",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/ws/stop-task")
async def stop_background_task():
    """إيقاف مهمة تحديث WebSocket"""
    await stop_stock_websocket_task()
    
    return {
        "status": "stopped",
        "message": "WebSocket background task stopped",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/ws/broadcast-system")
async def broadcast_system_message(message: str):
    """بث رسالة نظام لجميع المتصلين"""
    await stock_websocket_manager.broadcast_system_message(message)
    
    return {
        "status": "broadcasted",
        "message": f"System message broadcasted: {message}",
        "timestamp": datetime.utcnow().isoformat()
    }