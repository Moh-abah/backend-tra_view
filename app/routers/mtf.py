#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
routers/mtf.py — نقطة API لتحليل التداخل متعدد الأطر الزمنية (MTF)
====================================================================
POST /api/mtf/analyze
    body: {
        "symbol": "BTCUSDT",
        "timeframes": ["15m", "1h", "4h"],
        "days": 120,                        # عمق الجلب لكل فريم
        "indicators": [
            {"name": "rsi", "weight": 1.0},
            {"name": "ema_cross", "params": {"fast": 21, "slow": 50}},
            {"name": "sma_cross", "params": {"fast": 50, "slow": 200}, "weight": 1.5},
            {"name": "macd"},
            {"name": "stochastic", "weight": 0.5},
            {"name": "bollinger", "weight": 0.5},
            {"name": "liquidity", "params": {"min_ratio": 1.0}},
            {"name": "trend_filter", "params": {"period": 200}}
        ],
        "require_liquidity": false,
        "require_heavy_alignment": false,
        "min_confidence": 0.0,
        "market": "crypto"
    }
    → تحليل كامل + تفصيل لكل (فريم × مؤشر) بأوزان الخفيف/الثقيل.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.services.mtf_analyzer import (
    MountedIndicator, MultiTimeframeAnalyzer, TimeframeSpec,
)
from app.services.data_service import DataService
from app.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mtf"])


class MountIn(BaseModel):
    name: str = Field(..., description="rsi|macd|ema_cross|sma_cross|stochastic|bollinger|trend_filter|liquidity")
    params: Optional[Dict[str, Any]] = None
    weight: float = Field(1.0, gt=0)
    enabled: bool = True


class MTFAnalyzeIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    timeframes: List[str] = Field(..., min_length=1, max_length=6)
    days: int = Field(120, ge=5, le=730)
    indicators: List[MountIn] = Field(..., min_length=1)
    require_liquidity: bool = False
    require_heavy_alignment: bool = False
    min_confidence: float = Field(0.0, ge=0.0, le=1.0)
    market: str = "crypto"


def _sig_to_dict(s) -> Dict[str, Any]:
    val = s.value
    if isinstance(val, float):
        val = round(val, 6)
    return {
        "timeframe": s.timeframe,
        "indicator": s.indicator,
        "direction": s.direction,
        "weight": s.weight,
        "value": val,
        "detail": s.detail,
        "gate": s.gate,
    }


@router.post("/analyze")
async def analyze_mtf(payload: MTFAnalyzeIn, db=Depends(get_db)):
    """تحليل متعدد الفريمات: تصويت موزون (خفيف/متوسط/ثقيل) عبر المؤشرات المركبة."""
    try:
        data_service = DataService(db=db)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=payload.days)

        dataframes: Dict[str, pd.DataFrame] = {}
        for tf in payload.timeframes:
            try:
                df = await data_service.get_historical_last_version(
                    symbol=payload.symbol.upper(), timeframe=tf,
                    market=payload.market, start_date=start, end_date=end,
                    use_cache=True)
            except Exception as e:
                logger.warning(f"MTF fetch {payload.symbol} {tf} failed: {e}")
                df = pd.DataFrame()
            if df is None or df.empty:
                continue
            if "time" in df.columns:
                df = df.set_index("time")
            dataframes[tf] = df

        if not dataframes:
            raise HTTPException(status_code=503,
                                detail=f"No data for {payload.symbol} on {payload.timeframes}")

        analyzer = MultiTimeframeAnalyzer(
            timeframes=[TimeframeSpec(tf) for tf in payload.timeframes],
            require_liquidity=payload.require_liquidity,
            require_heavy_alignment=payload.require_heavy_alignment,
            min_confidence=payload.min_confidence,
        )
        for m in payload.indicators:
            try:
                analyzer.mount(MountedIndicator(name=m.name, params=m.params or {},
                                                weight=m.weight, enabled=m.enabled))
            except ValueError as ve:
                # ✅ Bugfix: مؤشر غير مدعوم كان ينفجر 500 داخل
                # logger.exception — يجب 400 برسالة واضحة تُذكر فيها
                # المؤشرات المدعومة.
                raise HTTPException(status_code=400, detail=str(ve))

        analysis = analyzer.analyze(dataframes, symbol=payload.symbol.upper())

        return {
            "symbol": analysis.symbol,
            "as_of": str(analysis.as_of),
            "action": analysis.action,
            "confidence": round(analysis.confidence, 4),
            "long_score": analysis.long_score,
            "short_score": analysis.short_score,
            "max_score": analysis.max_score,
            "liquidity_ok": analysis.liquidity_ok,
            "heavy_aligned": analysis.heavy_aligned,
            "veto_reasons": analysis.veto_reasons,
            "timeframes": payload.timeframes,
            "signals": [_sig_to_dict(s) for s in analysis.signals],
            "breakdown": analysis.breakdown_table(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("MTF analyze failed")
        raise HTTPException(status_code=500, detail=f"MTF analysis failed: {e}")
