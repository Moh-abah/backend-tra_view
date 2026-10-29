# app/api/indicators_ws.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()

@router.websocket("/ws/indicators/{symbol}")
async def indicators_websocket(websocket: WebSocket, symbol: str):
    await websocket.accept()
    
    try:
        # 1. استقبال إعدادات المؤشرات من العميل
        data = await websocket.receive_json()
        indicators_config = data.get('indicators', [])
        
        # 2. إضافة الرمز للمراقبة (إذا لم يكن مضافاً)
        from app.providers.binance_indicators_stream import indicators_manager
        await indicators_manager.add_symbol_monitoring(symbol, indicators_config)
        
        # 3. إضافة العميل لقائمة المشتركين
        indicators_manager.active_symbols[symbol]['clients'].append(websocket)
        
        # 4. إرسال البيانات التاريخية أولاً
        from app.services.data_service import DataService
        data_service = DataService()
        
        historical_data = await data_service.get_data_with_indicators(
            symbol=symbol,
            timeframe=data.get('timeframe', '1m'),
            market="crypto",
            indicators_config=indicators_config,
            days=data.get('days', 1)
        )
        
        await websocket.send_json({
            "type": "historical_data",
            "data": historical_data
        })
        
        # 5. الانتظار للاتصال المستمر
        while True:
            # مجرد الانتظار - التحديثات تأتي من indicators_manager
            await websocket.receive_text()  # أو يمكن استخدام ping/pong
            
    except WebSocketDisconnect:
        print(f"Client disconnected for {symbol}")
    except Exception as e:
        print(f"Error in WebSocket: {e}")