# =============================================================================
# EQUIV-TIMEFRAME.py — إثبات تكافؤ الكود القديم/الجديد على نافذة مثبتة التواريخ
# =============================================================================
# الاستخدام: python3 EQUIV-TIMEFRAME.py <output.json>
# يشغّل حمولة البطل المرجعي (CHAMPION_ZIGZAG_HL_V2) بنافذة مثبتة داخل الذيل
# المتصل بالكاش (/tmp/tf_cache/BTCUSDT_1h.parquet — 1800 شمعة متصلة) → صفر
# شبكة → نتيجة حتمية. يفرغ كل الصفقات (زمن/سعر/وحدات/pnl) + الملخص في JSON.
# =============================================================================
import asyncio
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

import pandas as pd

from app.backtest.engine1 import BacktestEngine
from app.backtest.schemas import BacktestConfig
from app.services.data_service import DataService
from app.services.strategy.presets import CHAMPION_ZIGZAG_HL_V2

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/equiv_result.json"
PARQUET = "/tmp/tf_cache/BTCUSDT_1h.parquet"
START = datetime(2026, 8, 20, 0, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 11, 1, 14, 12, 0, tzinfo=timezone.utc)


def expected_candles() -> int:
    df = pd.read_parquet(PARQUET).sort_values("time").reset_index(drop=True)
    end_ms = int((END - pd.Timedelta(hours=1)).timestamp() * 1000)  # آخر شمعة مغلقة
    start_ms = int(START.timestamp() * 1000)
    sel = df[(df.time >= start_ms) & (df.time <= end_ms)]
    return len(sel)


async def main():
    payload = dict(CHAMPION_ZIGZAG_HL_V2)
    payload["name"] = "EQUIV-TIMEFRAME champion pinned"
    payload["start_date"] = START.isoformat()
    payload["end_date"] = END.isoformat()
    payload.pop("days", None)

    exp = expected_candles()
    print(f"pinned window: {START.isoformat()} → {END.isoformat()} | expected candles={exp}")

    config = BacktestConfig(**payload)
    ds = DataService(None)
    engine = BacktestEngine(ds)
    result = await engine.run_backtest(config)

    trades = [
        {
            "entry_time": str(t.entry_time),
            "exit_time": str(t.exit_time),
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "position_size": t.position_size,
            "pnl": t.pnl,
            "price_delta_pct": getattr(t, "price_delta_pct", None),
            "result_pct": getattr(t, "result_pct", None),
            "exit_reason": getattr(t, "exit_reason", None),
        }
        for t in result.trades
    ]
    out = {
        "total_trades": result.total_trades,
        "total_pnl_percent": result.total_pnl_percent,
        "final_capital": result.final_capital,
        "fees_applied": getattr(result, "fees_applied", 0.0),
        "fill_model": str(getattr(result, "fill_model", "next_open")),
        "math_audit": getattr(result, "math_audit", {}),
        "n_visual_candles": len(result.visual_candles),
        "expected_candles": exp,
        "candles_match_cache": len(result.visual_candles) == exp,
        "trades": trades,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print(f"trades={out['total_trades']} · pnl%={out['total_pnl_percent']} · "
          f"visual={out['n_visual_candles']} (expected {exp}) → {OUT}")
    assert out["candles_match_cache"], "نافذة غير مغطاة بالكاش — النتيجة غير حتمية!"


asyncio.run(main())
