def fetch_klines(*args, **kwargs):
    pass

def klines_to_df(*args, **kwargs):
    class MockDataFrame:
        def iterrows(self):
            from datetime import datetime
            yield (datetime(2023, 1, 1), {"open": 100, "high": 105, "low": 95, "close": 100, "volume": 1000})
    return (MockDataFrame(), None)

TF_MS = {
    "1m": 60000,
    "5m": 300000
}