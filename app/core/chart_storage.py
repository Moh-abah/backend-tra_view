# \app\core\chart_storage.py
import sqlite3
import json
from typing import Dict, List

DB_FILE = "chart_state.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chart_indicators (
            symbol TEXT,
            timeframe TEXT,
            indicator_name TEXT,
            config TEXT,
            PRIMARY KEY(symbol, timeframe, indicator_name)
        )
    """)
    conn.commit()
    conn.close()

def save_indicator(symbol: str, timeframe: str, indicator_name: str, config: Dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO chart_indicators (symbol, timeframe, indicator_name, config)
        VALUES (?, ?, ?, ?)
    """, (symbol, timeframe, indicator_name, json.dumps(config)))
    conn.commit()
    conn.close()

def load_indicators(symbol: str, timeframe: str) -> List[Dict]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT config FROM chart_indicators
        WHERE symbol = ? AND timeframe = ?
    """, (symbol, timeframe))
    rows = cursor.fetchall()
    conn.close()
    return [json.loads(row[0]) for row in rows]
