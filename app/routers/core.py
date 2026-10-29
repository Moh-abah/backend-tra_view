from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.data_service import DataService

router = APIRouter(tags=["core"])

@router.get("/symbols")
async def get_available_symbols(market: str = "crypto", db: AsyncSession = Depends(get_db)):
    print("🔥 core router hit with market:", market, flush=True)
    service = DataService(db)
    try:
        symbols = await service.get_symbols(market)
        return {
            "market": market,
            "symbols": symbols,
            "count": len(symbols),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    