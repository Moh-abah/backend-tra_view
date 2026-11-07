# app/routers/live_strategy.py
"""
الجولة 16 — نقطة الإشارة الحية للاستراتيجية
============================================

GET /api/v1/live/strategy/signal
    ?symbol=ZECUSDT&market=crypto&timeframe=5m&strategy=zigzag_fib

عقد الفرونت (ROUND16): إشارة دخول واحدة فقط (الأحدث) —
label (S1/S2/S3 بنفس ترقيم محرك الباك تست حرفياً) · side · price ·
candle_time (فتح شمعة الدخول بالمللي ثانية) · state (active/waiting/invalidated).

كل الحسابات هنا (في الباك اند) — الفرونت يرسم فقط. لا تاريخ ولا مصفوفات
ولا بيانات استراتيجية كاملة في الجواب.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.live_strategy_service import (
    LiveStrategyError,
    LiveStrategyTransientError,
    evaluate_live_signal,
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live-strategy"])

# ✅ ROUND21 — المعاملات المبيّحة لتجاوز إعدادات zigzag_fib في نقطة الحية
# (الافتراضي: قالب البطل دون أي تغيير — التوافق الخلفي كامل)
# ✅ ROUND32 — مفاتيح قوالب الترند للترندية (تُقبل فقط عند strategy=zigzag_fib_e2e_trendy)
_OVERRIDE_QP = {
    "liq_lookback", "liq_arm_bars", "liq_signals", "liq_sfp_signals",
    "zz_mode", "zz_depth", "zz_deviation", "zz_backstep", "touch_level",
    "trend_periods", "trend_confirm", "trend_gate",
}
# مفاتيح شائعة لإبطال الكاش تُقبل بصمت حتى لا نكسر عملاء يضيفونها
_CACHEBUSTERS_QP = {"_", "t", "ts", "v", "cb", "cache", "nocache", "nonce"}


@router.get("/strategy/signal")
async def live_strategy_signal(
    request: Request,
    symbol: str = Query(..., min_length=1, description="رمز التداول (مثل ZECUSDT)"),
    market: str = Query("crypto", description="السوق — افتراضي crypto"),
    timeframe: str = Query(..., min_length=1, description="الفريم — أحد فريمات عقد الفريمات المدعومة"),
    strategy: str = Query("zigzag_fib", description="الاستراتيجية — افتراضي zigzag_fib (البطل)"),
    # ✅ ROUND21 — تجاوزات معاملات zigzag_fib (اختيارية كلها — بلاها يعمل القالب الافتراضي)
    liq_lookback: Optional[int] = Query(None, ge=5, le=2000,
        description="نافذة شموع سيولة R — الافتراضي 20؛ لفريم الدقيقة يوصى 240 (PRESET_NOTES)"),
    liq_arm_bars: Optional[int] = Query(None, ge=1, le=2000,
        description="نافذة انتهاء الخطة البديلة FIFO"),
    liq_signals: Optional[bool] = Query(None, description="تشغيل/تعطيل إشارات السيولة"),
    liq_sfp_signals: Optional[bool] = Query(None, description="إشارة SFP الاختيارية (مطفأة افتراضياً)"),
    zz_mode: Optional[str] = Query(None, pattern="^(tradingview|luxalgo)$",
        description="وضع الزقزاق — الافتراضي tradingview"),
    zz_depth: Optional[int] = Query(None, ge=2, le=500, description="عمق زقزاق TV"),
    zz_deviation: Optional[float] = Query(None, ge=0.0, le=1000.0,
        description="انحراف زقزاق TV بوحدات أعشار المئة (20 = 2.0%)"),
    zz_backstep: Optional[int] = Query(None, ge=1, le=100, description="backstep زقزاق TV"),
    touch_level: Optional[float] = Query(None, ge=0.0, le=1.0, description="مستوى لمس الفيبو"),
    # ✅ ROUND32 — قوالب الترند للترندية (strategy=zigzag_fib_e2e_trendy) — كلها قالبية:
    # إضافة ترند رابع 30 = تمرير «7,15,25,30» من الواجهة بلا أي كود.
    trend_periods: Optional[str] = Query(None,
        description="فترات الترند مفصولة بفواصل — مثل 7,15,25 (أو أضف رابعاً: 7,15,25,30) — للترندية فقط"),
    trend_confirm: Optional[str] = Query(None,
        description="صيغة إجماع الفترات: majority | all | any | رقم صريح — للترندية فقط"),
    trend_gate: Optional[str] = Query(None,
        description="الإشارات المبوّبة بالترند: s1,s2,s3 أو none للتعطيل — للترندية فقط"),
):
    """الإشارة الحية الأخيرة فقط — طبقة تقييم فوق محرك الباك تست دون المساس به.

    ✅ ROUND21: أي معامل من قائمة التجاوزات الممرّر يُطبّق فوق قالب البطل بنسخة
    عميقة ويُعلن في الجواب ضمن meta.params_applied — نداء (20) لا يعيد أبداً
    جواب نداء (240) (توقيع التجاوزات داخل مفتاح الكاش).
    """
    # حماية ضد الخطأ الصامت: معامل غير معروف (خطأ إملائي مثل liq_lookbak) → 400
    # بدل تجاهله وتشغيل نافذة مكفّئة دون علم المستخدم. (مفاتيح إبطال الكاش تُقبل)
    qp_keys = set(request.query_params.keys())
    unknown = sorted(qp_keys - {"symbol", "market", "timeframe", "strategy"}
                     - _OVERRIDE_QP - _CACHEBUSTERS_QP)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(f"Unknown query param(s): {unknown} — allowed overrides: "
                    f"{sorted(_OVERRIDE_QP)} (لا تطبيق صامت — صحّح الاسم أو احذفه)")
        )
    overrides: Dict[str, Any] = {
        k: v for k, v in {
            "liq_lookback": liq_lookback, "liq_arm_bars": liq_arm_bars,
            "liq_signals": liq_signals, "liq_sfp_signals": liq_sfp_signals,
            "zz_mode": zz_mode, "zz_depth": zz_depth, "zz_deviation": zz_deviation,
            "zz_backstep": zz_backstep, "touch_level": touch_level,
            # ✅ ROUND32: قوالب الترند — تُمرَّر نصاً ويطبّعها/يتحقق منها محرك الخدمة
            "trend_periods": trend_periods, "trend_confirm": trend_confirm,
            "trend_gate": trend_gate,
        }.items() if v is not None
    }
    try:
        data = await evaluate_live_signal(
            symbol=symbol.strip(),
            market=market.strip(),
            timeframe=timeframe.strip(),
            strategy=strategy.strip(),
            param_overrides=overrides or None,
        )
    except LiveStrategyError as e:
        # رفض عقد صريح — رسالة موحدة 400
        raise HTTPException(status_code=400, detail=str(e))
    except LiveStrategyTransientError as e:
        # فشل مؤقت للمزود (حظر/تهدئة 418/429 أو نافذة غير مكتملة) —
        # 503 قابل لإعادة المحاولة: الفرونت يعيد البولينج بعد ثوانٍ ويعود
        # الجواب طبيعياً بمجرد انتهاء التهدئة وامتلاء فجوات الكاش.
        logger.warning("live strategy transient for %s %s %s: %s", symbol, market, timeframe, e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        # رفض المزود للفريم/الرمز = مخالفة عقد → 400 وليس 503
        if "Unsupported timeframe" in msg or "Unsupported" in msg:
            raise HTTPException(status_code=400, detail=msg)
        # خطأ تشغيلي — 503 مع الرسالة (الجلب/المزود/المحرك)
        logger.exception("live strategy evaluation failed for %s %s %s", symbol, market, timeframe)
        raise HTTPException(status_code=503, detail=f"live strategy evaluation failed: {e}")
    return {"success": True, "data": data}
