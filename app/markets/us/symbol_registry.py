# app/markets/us/symbol_registry.py

import pandas as pd
from typing import List, Dict

class USSymbolRegistry:
    """
    Registry رسمي لرموز السوق الأمريكي
    مصدره: NASDAQ Official Listings
    """

    def __init__(self):
        self._symbols: Dict[str, Dict] = {}

    def load_from_files(
        self,
        nasdaq_file: str,
        other_file: str = None  # أصبح اختياري
    ) -> None:
        symbols = {}

        # NASDAQ
        df_nasdaq = pd.read_csv(nasdaq_file)  # بدون sep="|"
        for _, row in df_nasdaq.iterrows():
            symbol = row["Symbol"]
            symbols[symbol] = {
                "symbol": symbol,
                "name": row.get("Security Name", row.get("Company Name", "")),
                "exchange": "NASDAQ",
                "market": "us_stocks",
                "type": "stock"
            }

        # NYSE / AMEX إذا تم تمرير الملف
        if other_file:
            df_other = pd.read_csv(other_file)
            for _, row in df_other.iterrows():
                symbol = row["Symbol"]
                symbols[symbol] = {
                    "symbol": symbol,
                    "name": row.get("Security Name", row.get("Company Name", "")),
                    "exchange": row.get("Exchange", "UNKNOWN"),
                    "market": "us_stocks",
                    "type": "stock"
                }

        self._symbols = symbols

    def all(self) -> List[Dict]:
        return list(self._symbols.values())

    def symbols_only(self) -> List[str]:
        return list(self._symbols.keys())

    def exists(self, symbol: str) -> bool:
        return symbol in self._symbols

    def get(self, symbol: str) -> Dict:
        return self._symbols.get(symbol)
