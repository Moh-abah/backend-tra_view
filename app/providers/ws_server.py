# trading_backend/app/providers/ws_server.py
import asyncio
import websockets
from app.services.chart_manager import ChartManager

chart_manager = ChartManager()

async def ws_handler(websocket, path):
    queue = chart_manager.subscribe()
    try:
        while True:
            message = await queue.get()
            await websocket.send(json.dumps(message))
    except websockets.ConnectionClosed:
        print("Client disconnected")

async def start_ws_server():
    server = await websockets.serve(ws_handler, "0.0.0.0", 8765)
    await server.wait_closed()
