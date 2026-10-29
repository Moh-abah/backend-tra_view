# app/markets/us/market_config.py

US_MARKET_CONFIG = {
    "id": "us_stocks",
    "name": "US Stock Market",
    "currency": "USD",
    "timezone": "America/New_York",
    "exchanges": ["NASDAQ", "NYSE", "AMEX"],
    "asset_types": ["stock"],
    "data_delay": "15m",
    "provider": "yahoo_finance"
}
