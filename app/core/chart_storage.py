# \app\core\chart_storage.py
import sqlite3
import json
from typing import Dict, List

# ✅ الجولة 6: مسار عبر طبقة التجهيز الذاتي — كان مساراً نسبياً مباشراً
# (قنبلة "readonly database" كامنة لو استُخدمت الوحدة في الإنتاج).
from app.core.storage_health import ensure_sqlite_ready

DB_FILE = ensure_sqlite_ready("chart_state.db", label="chart_state_legacy")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

def init_db():
    conn = _connect()
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
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO chart_indicators (symbol, timeframe, indicator_name, config)
        VALUES (?, ?, ?, ?)
    """, (symbol, timeframe, indicator_name, json.dumps(config)))
    conn.commit()
    conn.close()

def load_indicators(symbol: str, timeframe: str) -> List[Dict]:
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT config FROM chart_indicators
        WHERE symbol = ? AND timeframe = ?
    """, (symbol, timeframe))
    rows = cursor.fetchall()
    conn.close()
    return [json.loads(row[0]) for row in rows]
