# test_symbols_endpoint_async.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from app.services.data_service import DataService
from app.config import settings

DATABASE_URL = settings.DATABASE_URL  # تأكد أن هذا موجود في config

async def test_symbols_endpoint():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with async_session() as session:
        service = DataService(session)
        try:
            symbols = await service.get_symbols("crypto")
            print(f"Retrieved {len(symbols)} symbols: {symbols[:10]}")
        except HTTPException as he:
            print("HTTPException:", he.detail)
        except Exception as e:
            print("Exception during get_symbols:")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_symbols_endpoint())
