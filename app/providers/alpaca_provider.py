# import alpaca_trade_api as tradeapi
# import pandas as pd
# from datetime import datetime, timedelta
# from typing import Dict, List
# from app.config import settings
# from ..services.data_provider import MarketDataProvider
# import httpx
# class AlpacaProvider(MarketDataProvider):
#     def __init__(self):
#         self.api = tradeapi.REST(
#             key_id=settings.ALPACA_API_KEY,
#             secret_key=settings.ALPACA_SECRET_KEY,
#             base_url='https://paper-api.alpaca.markets'  # للتجربة
#         )
#         self.symbols_cache = None
    
#     async def get_live_price(self, symbol: str) -> Dict:
#         """الحصول على آخر سعر للأسهم"""
#         try:
#             quote = self.api.get_latest_quote(symbol)
#             return {
#                 "symbol": symbol,
#                 "bid": quote.bidprice,
#                 "ask": quote.askprice,
#                 "last": quote.lastprice,
#                 "timestamp": quote.timestamp,
#                 "source": "alpaca"
#             }
#         except Exception as e:
#             # Fallback إلى Polygon.io إذا كان متاحاً
#             if settings.POLYGON_API_KEY:
#                 return await self._fallback_to_polygon(symbol)
#             raise e
    
#     async def get_historical(
#         self, 
#         symbol: str, 
#         timeframe: str,
#         start_date: datetime,
#         end_date: datetime = None
#     ) -> pd.DataFrame:
#         """الحصول على بيانات تاريخية"""
#         # تحويل timeframe إلى صيغة Alpaca
#         timeframe_map = {
#             "1m": "1Min", "5m": "5Min", "15m": "15Min",
#             "1h": "1Hour", "4h": "4Hour", "1d": "1Day"
#         }
        
#         timeframe_str = timeframe_map.get(timeframe, "1Hour")
#         end_date = end_date or datetime.utcnow()
        
#         # الحصول على البيانات
#         bars = self.api.get_bars(
#             symbol,
#             timeframe_str,
#             start=start_date.isoformat(),
#             end=end_date.isoformat()
#         ).df
        
#         return bars
    
#     async def stream_live(self, symbol: str, timeframe: str = "1m"):
#         """بث بيانات حية (WebSocket)"""
#         async def handler(bar):
#             yield {
#                 "symbol": bar.symbol,
#                 "open": bar.open,
#                 "high": bar.high,
#                 "low": bar.low,
#                 "close": bar.close,
#                 "volume": bar.volume,
#                 "timestamp": bar.timestamp,
#                 "source": "alpaca"
#             }
        
#         # اشتراك في البيانات الحية
#         conn = tradeapi.StreamConn()
        
#         @conn.on(r'^AM\.{symbol}$')
#         async def on_bar(conn, channel, data):
#             async for item in handler(data):
#                 yield item
        
#         await conn.subscribe([f'AM.{symbol}'])
#         await conn.run()
    
#     async def get_symbols(self) -> List[str]:
#         """الحصول على الرموز المتاحة"""
#         if self.symbols_cache:
#             return self.symbols_cache
        
#         assets = self.api.list_assets(status='active')
#         symbols = [asset.symbol for asset in assets if asset.tradable]
        
#         self.symbols_cache = symbols
#         return symbols
    
#     # async def _fallback_to_polygon(self, symbol: str) -> Dict:
#     #     """استخدام Polygon.io كنسخة احتياطية"""
    
        
#     #     url = f"https://api.polygon.io/v2/last/tick/{symbol}"
#     #     params = {"apiKey": settings.POLYGON_API_KEY}
        
#     #     async with aiohttp.ClientSession() as session:
#     #         async with session.get(url, params=params) as response:
#     #             data = await response.json()
                
#     #             return {
#     #                 "symbol": symbol,
#     #                 "last": data['results']['p'],
#     #                 "timestamp": datetime.fromtimestamp(data['results']['t'] / 1000),
#     #                 "source": "polygon"
#     #             }

#     async def _fallback_to_polygon(self, symbol: str) -> dict:
#         """استخدام Polygon.io كنسخة احتياطية"""
        
#         url = f"https://api.polygon.io/v2/last/tick/{symbol}"
#         params = {"apiKey": settings.POLYGON_API_KEY}
        
#         async with httpx.AsyncClient() as client:
#             response = await client.get(url, params=params)
#             data = response.json()  # httpx يجيب JSON مباشرة

#             return {
#                 "symbol": symbol,
#                 "last": data['results']['p'],
#                 "timestamp": datetime.fromtimestamp(data['results']['t'] / 1000),
#                 "source": "polygon"
#             }    