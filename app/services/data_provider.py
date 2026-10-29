from abc import ABC, abstractmethod
from typing import Dict, List, Optional, AsyncGenerator
from datetime import datetime, timedelta
import pandas as pd

class MarketDataProvider(ABC):
    """واجهة مجردة لجميع مزودي البيانات"""
    
    @abstractmethod
    async def get_live_price(self, symbol: str) -> Dict:
        pass
    
    @abstractmethod
    async def get_historical(
        self, 
        symbol: str, 
        timeframe: str,
        start_date: datetime,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        pass
    
    @abstractmethod
    async def stream_live(
        self,
        symbol: str,
        timeframe: str
    ) -> AsyncGenerator[Dict, None]:
        pass
    
    @abstractmethod
    async def get_symbols(self) -> List[str]:
        pass