# test_dataservice.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.services.data_service import DataService

DATABASE_URL: str = "postgresql+asyncpg://neondb_owner:npg_SmQ5UA8CGgOo@ep-dry-moon-a4gvc6kp-pooler.us-east-1.aws.neon.tech/neondb?ssl=require"    

async def test_get_symbols():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with async_session() as session:
        service = DataService(session)
        symbols = await service.get_symbols("crypto")
        print(f"Retrieved {len(symbols)} symbols: {symbols[:10]}")  # عرض أول 10 فقط

asyncio.run(test_get_symbols())
