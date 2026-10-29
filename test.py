import asyncio
from app.services.data_service import DataService
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

async def test():
    # استدعاء get_db للحصول على جلسة
    async for db in get_db():
        service = DataService(db)
        symbols = await service.get_symbols("crypto")
        print(symbols)

asyncio.run(test())
