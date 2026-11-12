# ساندبوكس إثبات R45 — نفس دوال المحرك الموحد المستخدمة من backtest1
from typing import Any, Dict, List


def _df_to_candles(df) -> List[Dict[str, Any]]:
    """نفس دور المحرك: DataFrame ⇦ قواميس شموع (time بالثواني هنا)."""
    out: List[Dict[str, Any]] = []
    for rec in df.to_dict("records"):
        t = rec.get("time") or rec.get("timestamp")
        if t is None:
            continue
        t = float(t)
        if t > 1e11:
            t = t / 1000.0
        out.append(
            {
                "time": int(t),
                "open": float(rec.get("open", 0.0)),
                "high": float(rec.get("high", 0.0)),
                "low": float(rec.get("low", 0.0)),
                "close": float(rec.get("close", 0.0)),
                "volume": float(rec.get("volume", 0.0)),
            }
        )
    return out
