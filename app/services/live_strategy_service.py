# app/services/live_strategy_service.py
"""
الجولة 16 — محرك الإشارة الحية للاستراتيجية (Live Strategy Signal)
====================================================================

عقد الفرونت: GET /api/v1/live/strategy/signal?symbol=&market=&timeframe=&strategy=
يُقيّم استراتيجية البطل zigzag_fib (ZLF v13.2) على أحدث البيانات الحية
بنفس مصدر شموع الباك تست، ويُرجع إشارة الدخول الأخيرة فقط.

## القرارات التعاقدية الموثقة (كما طلب العقد — «وثّق قرارك»):

1) **التقييم بمحرك الباك تست نفسه — لا منطق مكرر**:
   نُشغّل `BacktestEngine.run_backtest` حرفياً على نافذة الشموع المغلقة،
   فالترقيم (S1/S2/S3) والخروج (انقلاب الساق + SL) ونموذج التنفيذ
   (next_open) كلها موروثة من نفس الكود الذي يدير الباك تست — صفر تفسير
   من الفرونت وصفر إعادة تنفيذ هنا.

2) **SL/TP البطل = حقول عليا لا risk_management**:
   PRESET_NOTES تنص أن `strategy_config.risk_management` توثيقي والمحرك
   لا يقرأه — الحاكم الفعلي = حقول BacktestConfig العليا. لذا نمرر
   stop_loss_percent=2.0 و take_profit_percent=99.0 (SL 2.0 / TP 99.0
   كما في العقد) كحقول عليا.

3) **شمعة الملء الاصطناعية (جوهر دقة «الإشارة الحية»)**:
   المحرك ينفذ next_open — قرار شمعة مغلقة T ينفذ عند فتح T+1. في الحي،
   T+1 هو الشمعة الحية المتكوِّنة الآن. نضيف بعد آخر شمعة مغلقة شمعة
   اصطناعية: open = الافتتاح الحقيقي للشمعة الحية (من المزود) و
   high=low=close=open (مسطحة — لا تُنتج إشارات زائفة) و volume=0.
   النتيجة: إشارة على آخر شمعة مغلقة تُملأ فعلاً عند فتح الشمعة الحية،
   فيصبح candle_time = وقت فتح الشمعة الحية — تماماً كما يرسمها الفرونت.
   - سلامة عدم الرسم: مؤشرات v13.2 غير مرسِّمة (قيم الشمعة T لا تتغير
     بإضافة شموع بعدها) — لهذا إلحاق شمعة اصطناعية لا يفسد قرارات
     الشموع المغلقة السابقة.
   - فحص SL داخل شمعة اصطناعية مسطحة مستحيل رياضياً (low == open > SL).
   - قرار خروج على آخر شمعة مغلقة يُملأ عند فتح الشمعة الحية — الخروج
     الحي يُحتسب لحظياً مثله مثل الباك تست.

4) **دورة الحياة من نتيجة المحاكاة نفسها**:
   - الموضع المفتوح عند نهاية النافذة يُغلق إجبارياً بسبب "End of Data"
     — نعتبره **active** (مفتوح حياً الآن).
   - أي خروج حقيقي (Stop Loss Hit / Exit Signal: انقلاب الساق / …)
     يجعل آخر إشارة **invalidated** (signal=null — الفرونت يزيل العلامة).
   - لا صفقات في النافذة → **waiting**.
   - إشارة أحدث تستبدل الأقدم تلقائياً لأننا نُرجع «آخر صفقة» فقط.

5) **النافذة**: آخر WINDOW_CANDLES شمعة مغلقة (2000) — كافية لأعمار
   المؤشر (length=100 / liq_arm=60) مع هامش واسع، ورخيصة حسابياً
   (~200ms). نافذة أطول لا تغير إشارة النهاية بفضل عدم الرسم.

6) **seq**: ترتيب حدث الدخول بين أحداث الدخول في النافذة (1، 2، …).
   للتعرف على «إشارة أحدث» استخدم candle_time — seq إرشادي.

7) **side**: الاستراتيجية long-only (position_side=long) — القيمة
   دائماً "long" حالياً؛ الحقل محفوظ لتوسيع مستقبلي.

8) **الأداء — حماية ميزانية المزود (إصلاح 2026-11-02 طبقة 5)**:
   - كاش النجاح TTL = 10 ثوانٍ لكل (symbol, market, timeframe, strategy):
     الجواب لا يتغير إلا بإغلاق شمعة (5m/1m/…) — استطلاع كل 2-3s لا يغيّر
     شيئاً، فيحوّل حرق الميزانية من «طلب شبكي لكل استطلاع» إلى «طلب لكل
     عُشر الدقيقة تقريباً» (تخفيض ~10x).
   - كاش سلبي للفشل المؤقت: عند فشل مؤقت (تهدئة 418/429 أو مهلة) يُخزَّن
     بصمة المفتاح لمدة 20-28 ثانية (جيتر عشوائي لتفادي تزامن انتهاء
     القطيع) — أي استطلاع أثناءها يجيب 503 فوراً **بدون أي طلب شبكي**.
     هذا يمنع «القطيع الرعدي» من إعادة إشعال عقوبة Binance فور انتهائها
     ويوزّع القبول بعد التهدئة.
   - دمج الطلبات المتزامنة (single-flight): من يصل أثناء حساب جارٍ ينتظر
     نتيجته بانتظار **غير حاجب** (لا يجمّد حلقة الأحداث) — وإن فشل
     المنتَج يرث الكاش السلبي بدل إطلاق طلب شبكي مكرر.
   - تراجع أُسّي للكاش السلبي: كل فشل متتابع لنفس المفتاح يضاعف كتمه
     (20-28s → 40-56s → … → 300s) — يخرج المطرودون فرادى بدل ضربة
     جماعية تعيد إشعال عقوبة المزود.
   - تدهور لطيف (stale-while-revalidate): فشل مؤقت لتحديث رمز لديه إشارة
     محسوبة سابقاً يخدم الإشارة القديمة موسومة (meta.stale=true +
     meta.stale_age_s، حتى 60s) بدل 503 — فشل جلب 11 شمعة لا يلغي
     إشارة حُسبت من 2000 شمعة.

9) **بنية الحلقات (إصلاح 2026-11-02 — «bound to a different event loop»)**:
   النمط القديم كان يشغّل *كل* التقييم (بما فيه الجلب الشبكي عبر
   data_service → المزود) داخل asyncio.run في خيط عامل — حلقة مؤقتة
   جديدة لكل طلب. الـasyncio primitives المشتركة في المزود
   (Semaphore/أقفال التاريخ) تُربط بأول حلقة تتنافس عليها وترفض البقية
   → عاصفة 503 متسلسلة عند المسح المتوازي. الآن:
   - المرحلة ١ (الجلب الشبكي): على حلقة الـAPI الرئيسية حصراً — الـprimitives
     المشتركة تُربط بحلقة واحدة دائمة لا تموت أبداً.
   - المرحلة ٢ (الحساب الثقيل): خيط عامل بحلقة خاصة تعمل على
     _PreparedDataService فقط (نسخة محلية — صفر primitives مشتركة) —
     نفس نمط الباك تست الداخلي (الجولة 14.1) المثبت في الإنتاج.
"""
import asyncio
import copy
import json
import logging
import os
import random
import re
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.backtest.engine1 import BacktestEngine
from app.backtest.schemas import BacktestConfig
from app.services.data_service import DataService
from app.services.strategy.presets import (
    ZLF_TRIPLE_SIGNAL,
    ZLF_E2E_TRIPLE_SIGNAL,
    ZLF_E2E_TRENDY_TRIPLE_SIGNAL,
    ZLF_E2E_BLAZING_QUINT_SIGNAL,
    TRENDY_MACDIZED,
    BLAZING_MACDIZED,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ثوابت العقد
# ---------------------------------------------------------------------------
# عقد البطل: SL 2.0 / TP 99.0 — تمرَّر كحقول عليا (risk_management توثيقي فقط)
CHAMPION_SL_PERCENT: float = 2.0
CHAMPION_TP_PERCENT: float = 99.0

# اسم الاستراتيجية البطلة + المرادفات المقبولة في strategy=
CHAMPION_KEY = "zigzag_fib"
_STRATEGY_ALIASES = {
    "zigzag_fib": "zlf",
    "zlf": "zlf",
    "zlf_triple_signal": "zlf",
    "zlf_triple_signal_zero_fee": "zlf",
    # ✅ ROUND22: ZLF-End-To-End — الاستراتيجية المنفصلة الجديدة (محرك منفصل باسم مختلف)
    "zigzag_fib_e2e": "zlf_e2e",
    "zlf_e2e": "zlf_e2e",
    "zlf_end_to_end": "zlf_e2e",
    # ✅ ROUND32: «الزقزاق البطل e2e الترنديه» — الاستنساخ المعزول ببوابة الترند
    "zigzag_fib_e2e_trendy": "zlf_e2e_trendy",
    "zlf_e2e_trendy": "zlf_e2e_trendy",
    "zlf_e2e_trendy_triple_signal": "zlf_e2e_trendy",
    "zlf_e2e_trendy_triple_signal_zero_fee": "zlf_e2e_trendy",
    "zlf_end_to_end_trendy": "zlf_e2e_trendy",
    # 🔥 R69: «الترندية الملتهبة» — الترندية بت-بت + N5/N6 (محرك معزول جديد كلياً)
    "zigzag_fib_e2e_blazing": "zlf_e2e_blazing",
    "zlf_e2e_blazing": "zlf_e2e_blazing",
    "blazing": "zlf_e2e_blazing",
    "zlf_e2e_blazing_quint_signal": "zlf_e2e_blazing",
    "zlf_e2e_blazing_quint_signal_zero_fee": "zlf_e2e_blazing",
    "zlf_end_to_end_blazing": "zlf_e2e_blazing",
    # ✅ PRO73: «الترندية الماكدية» — الترندية + بوابة الموشرات (نسخ المستند 67)
    "zigzag_fib_e2e_trendy_macd": "zlf_e2e_trendy_macd",
    "zlf_e2e_trendy_macd": "zlf_e2e_trendy_macd",
    "trendy_macdized": "zlf_e2e_trendy_macd",
    "trendy_macdized_zero_fee": "zlf_e2e_trendy_macd",
    # 🔥 PRO73: «الملتهبة الماكدية» — الملتهبة + بوابة الموشرات (نسخ المستند 67)
    "zigzag_fib_e2e_blazing_macd": "zlf_e2e_blazing_macd",
    "zlf_e2e_blazing_macd": "zlf_e2e_blazing_macd",
    "blazing_macdized": "zlf_e2e_blazing_macd",
    "blazing_macdized_zero_fee": "zlf_e2e_blazing_macd",
}

# هوية المحركين (تُعلن في meta.engine في كل جواب)
_ENGINE_META = {
    "zlf": "ZLF (zigzag_fib — المحرك الحالي كما هو)",
    "zlf_e2e": "ZLF-End-To-End",
    # ✅ ROUND32
    "zlf_e2e_trendy": "ZLF-End-To-End-Trendy (الترندية — بوابة الترند القالبية)",
    # 🔥 R69
    "zlf_e2e_blazing": "ZLF-End-To-End-Blazing (الترندية الملتهبة — S1/S2/S3 + N5/N6)",
    # ✅ PRO73
    "zlf_e2e_trendy_macd": "PRO73-Trendy-MACDized (الترندية الماكدية — بوابة الموشرات: 67 نسخة + الحالات)",
    "zlf_e2e_blazing_macd": "PRO73-Blazing-MACDized (الملتهبة الماكدية — بوابة الموشرات: 67 نسخة + الحالات)",
}

WINDOW_CANDLES = 2000          # شموع مغلقة للتقييم
MIN_CANDLES_FOR_ENGINE = 50    # حد المحرك الأدنى (نفس شرط المحرك)

# ---------------------------------------------------------------------------
# ✅ ROUND21-v2 (2026-11-03) — تجاوزات معاملات zigzag_fib لنقطة الإشارة الحية
# ---------------------------------------------------------------------------
# الفحص الجنائي المشترك (باكند + فرونت، أدلة حية على RUNEUSDT·1m): نقطة الحية
# كانت تعمل بقيم القالب المثبتة (liq_lookback=20 = نافذة 20 دقيقة على فريم
# الدقيقة) مهما كانت إعدادات المستخدم — فتولّد «اختراقات» شكلية على قمم حمراء
# محلية عمرها دقيقتان بدل القمم الحقيقية (مثال مثبت: S2 @ 0.585 على 13:16
# ضد ref_high=0.583، بينما بالنافذة 240 لا إشارة إطلاقاً لأن ref_high=0.599).
#
# ROUND21-v2: القالب البطل نفسه صُحّح في presets.py (liq_lookback 20 → 240
# = نافذة المستخدم 4 ساعات) — أي أن نقطة الحية الآن تستخدم 240 **افتراضياً**
# حتى بدون أي معاملات استعلام، والمعاملات الاستعلامية تبقى للتجاوز الاختياري
# (A/B والفريمات الأخرى). meta.params_applied في كل جواب يعلن المعاملات
# الفعلية المطبّقة كاملة — تحقق ذاتي فوري بلا تخمين.
# نفس فلسفة البيت: أي مفتاح غير معروف يُرفض برسالة واضحة — لا تطبيق صامت.
ZLF_PARAM_OVERRIDABLE: Dict[str, Dict[str, Any]] = {
    "zz_mode":         {"type": "enum", "values": ("tradingview", "luxalgo")},
    "zz_depth":        {"type": "int", "min": 2,    "max": 500},
    "zz_deviation":    {"type": "num", "min": 0.0,  "max": 1000.0},
    "zz_backstep":     {"type": "int", "min": 1,    "max": 100},
    "length":          {"type": "int", "min": 2,    "max": 2000},
    "touch_level":     {"type": "num", "min": 0.0,  "max": 1.0},
    "liq_lookback":    {"type": "int", "min": 5,    "max": 2000},
    "liq_signals":     {"type": "bool"},
    "liq_arm_bars":    {"type": "int", "min": 1,    "max": 2000},
    "liq_sfp_signals": {"type": "bool"},
}

# ✅ ROUND21-v2 (إصلاح جسر الأسماء): المحرك (calculator.py → فرع zzfib) يقرأ
# المفاتيح الأصلية mode/depth/deviation/backstep — بينما واجهة الاستعلام تعرض
# zz_mode/zz_depth/zz_deviation/zz_backstep. بدون هذه الخريطة كانت التجاوزات
# zz_* تُكتب بمفاتيح لا يعرفها المحرك فتُهمَل **بصمت** (نفس العطب الذي جاءنا
# لإصلاحه!). الآن: كل تجاوز zz_* يُكتب بمفتاحه الأصلي فعلاً — بلا استثناء.
ZLF_PARAM_ALIAS_TO_NATIVE: Dict[str, str] = {
    "zz_mode":      "mode",
    "zz_depth":     "depth",
    "zz_deviation": "deviation",
    "zz_backstep":  "backstep",
}


def normalize_zlf_overrides(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """تصفية وتحقق التجاوزات — يرفع LiveStrategyError (→400) على أي مفتاح/قيمة غير مشروعة.

    - int: يقبل عدداً صحيحاً (أو عدداً عائماً متكافئاً) ويرفض bool صراحة
      (لأن isinstance(True, int) صحيح في بايثون — فخ كلاسيكي).
    - num: يقبل int/float غير منطقي.
    - bool: يقبل منطقياً حقيقياً فقط (وليس 0/1 نصياً).
    """
    if not raw:
        return {}
    unknown = sorted(k for k in raw if k not in ZLF_PARAM_OVERRIDABLE)
    if unknown:
        raise LiveStrategyError(
            f"Unsupported zigzag_fib param(s): {unknown} — overridable: {sorted(ZLF_PARAM_OVERRIDABLE)}"
        )
    clean: Dict[str, Any] = {}
    for key, val in raw.items():
        if val is None:
            continue
        spec = ZLF_PARAM_OVERRIDABLE[key]
        kind = spec["type"]
        if kind == "bool":
            if not isinstance(val, bool):
                raise LiveStrategyError(f"param {key!r} must be boolean (true/false), got {val!r}")
            clean[key] = val
            continue
        if isinstance(val, bool):
            raise LiveStrategyError(f"param {key!r} must be numeric, got boolean {val!r}")
        if kind == "enum":
            if not isinstance(val, str) or val not in spec["values"]:
                raise LiveStrategyError(
                    f"param {key!r} must be one of {list(spec['values'])}, got {val!r}"
                )
            clean[key] = val
            continue
        if kind == "int":
            if isinstance(val, float) and not float(val).is_integer():
                raise LiveStrategyError(f"param {key!r} must be an integer, got {val!r}")
            if not isinstance(val, (int, float)):
                raise LiveStrategyError(f"param {key!r} must be an integer, got {val!r}")
            ival = int(val)
            if not (spec["min"] <= ival <= spec["max"]):
                raise LiveStrategyError(f"param {key!r}={ival} out of range [{spec['min']}, {spec['max']}]")
            clean[key] = ival
            continue
        # num
        if not isinstance(val, (int, float)):
            raise LiveStrategyError(f"param {key!r} must be numeric, got {val!r}")
        fval = float(val)
        if not (spec["min"] <= fval <= spec["max"]):
            raise LiveStrategyError(f"param {key!r}={fval} out of range [{spec['min']}, {spec['max']}]")
        clean[key] = fval
    return clean


def _normalize_e2e_overrides(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """✅ ROUND22 — تحقق التجاوزات لمحرك ZLF-End-To-End (منفصل).

    المبيّح: معاملات الزقزاق فقط (zz_mode/zz_depth/zz_deviation/zz_backstep/length).
    معاملات liq_* غير منطبقة على هذا المحرك — النطاق يعتمد لحظة ظهور الزقزاق
    ونافذة الحساب = عمر النطاق (لا نافذة منزلقة بعدد شموع في التعريف) —
    يُرفض إمرارها برسالة واضحة (لا تطبيق صامت — نفس فلسفة البيت).
    """
    if not raw:
        return {}
    e2e_keys = ("zz_mode", "zz_depth", "zz_deviation", "zz_backstep", "length")
    unknown = sorted(k for k in raw if k not in e2e_keys)
    if unknown:
        non_appl = [k for k in unknown if k in ZLF_PARAM_OVERRIDABLE]
        hint = (" — معاملات السيولة liq_* غير منطبقة على ZLF-End-To-End "
                "(النطاق يعتمد لحظة ظهور الزقزاق ونافذة الحساب = عمر النطاق)" if non_appl else "")
        raise LiveStrategyError(
            f"Unsupported ZLF-End-To-End param(s): {unknown}{hint} — overridable: {list(e2e_keys)}"
        )
    return normalize_zlf_overrides({k: raw[k] for k in raw if k in ZLF_PARAM_OVERRIDABLE})


# ✅ ROUND32 — مفاتيح قوالب الترند المبيّحة للتجاوز في نقطة الحية (الترندية فقط).
# الفترات قالبية: نص مفصول بفواصل («7,15,25») أو قائمة أرقام — إضافة ترند رابع
# 30 = تمرير «7,15,25,30» من الواجهة بلا أي كود.
TRENDY_TREND_KEYS = ("trend_periods", "trend_confirm", "trend_gate")


def _parse_int_list(raw: Any, lo: int, hi: int, key: str) -> List[int]:
    """تطبيق قائمة أعداد صحيحة من قائمة/نص مفصول بفواصل — رفض صريح خارج المدى."""
    if isinstance(raw, str):
        parts = [x for x in raw.replace(";", ",").split(",") if str(x).strip()]
    elif isinstance(raw, (list, tuple)):
        parts = list(raw)
    else:
        parts = [raw]
    out: List[int] = []
    for x in parts:
        if isinstance(x, bool):
            raise LiveStrategyError(f"param {key!r} must contain integers, got boolean {x!r}")
        try:
            v = int(float(x))
        except (TypeError, ValueError):
            raise LiveStrategyError(f"param {key!r} must contain integers, got {x!r}")
        if not (lo <= v <= hi):
            raise LiveStrategyError(f"param {key!r} value {v} out of range [{lo}, {hi}]")
        out.append(v)
    if not out:
        raise LiveStrategyError(f"param {key!r} must contain at least one value")
    if len(out) > 12:
        raise LiveStrategyError(f"param {key!r} accepts at most 12 trends, got {len(out)}")
    return out


def _normalize_trendy_overrides(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """✅ ROUND32 — تحقق التجاوزات لمحرك ZLF-End-To-End-Trendy (منفصل).

    المبيّح: معاملات الزقزاق نفسها المبيّحة لـ E2E فقط
    (zz_mode/zz_depth/zz_deviation/zz_backstep/length) + قوالب الترند الثلاثة:
      trend_periods:  «7,15,25» أو قائمة — أعداد 2..500 (حتى 12 ترنداً)
      trend_confirm:  majority|all|any أو رقم صريح 1..500
      trend_gate:     s1/s2/s3 (بأي صيغة) أو none للتعطيل
    معاملات liq_* غير منطبقة على الترندية (كما في E2E — النطاق يعتمد لحظة ظهور
    الزقزاق ونافذة الحساب = عمر النطاق) — تُرفض برسالة واضحة (لا تطبيق صامت).
    """
    if not raw:
        return {}
    trendy_zlf_keys = ("zz_mode", "zz_depth", "zz_deviation", "zz_backstep", "length")
    allowed = set(trendy_zlf_keys) | set(TRENDY_TREND_KEYS)
    unknown = sorted(k for k in raw if k not in allowed)
    if unknown:
        non_appl = [k for k in unknown if k in ZLF_PARAM_OVERRIDABLE]
        hint = (" — معاملات السيولة liq_* غير منطبقة على الترندية (النطاق يعتمد لحظة ظهور الزقزاق)" if non_appl else "")
        raise LiveStrategyError(
            f"Unsupported ZLF-End-To-End-Trendy param(s): {unknown}{hint} — "
            f"overridable: {sorted(allowed)}"
        )
    clean = normalize_zlf_overrides({k: raw[k] for k in raw if k in trendy_zlf_keys})
    if "trend_periods" in raw and raw["trend_periods"] is not None:
        clean["trend_periods"] = _parse_int_list(raw["trend_periods"], 2, 500, "trend_periods")
    if "trend_confirm" in raw and raw["trend_confirm"] is not None:
        v = raw["trend_confirm"]
        if isinstance(v, str) and v.strip().lower() in ("majority", "all", "any"):
            clean["trend_confirm"] = v.strip().lower()
        else:
            try:
                iv = int(float(v))
            except (TypeError, ValueError):
                raise LiveStrategyError(
                    f"param 'trend_confirm' must be majority|all|any or an integer, got {v!r}"
                )
            if not (1 <= iv <= 500):
                raise LiveStrategyError(f"param 'trend_confirm'={iv} out of range [1, 500]")
            clean["trend_confirm"] = iv
    if "trend_gate" in raw and raw["trend_gate"] is not None:
        v = raw["trend_gate"]
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("none", "off", "false", "0", ""):
                clean["trend_gate"] = "none"
            else:
                parts = [x.strip().lower() for x in v.replace(";", ",").split(",") if x.strip()]
                bad = [x for x in parts if x not in ("s1", "s2", "s3", "1", "2", "3")]
                if bad:
                    raise LiveStrategyError(
                        f"param 'trend_gate' accepts s1/s2/s3 (or none), got {bad}"
                    )
                clean["trend_gate"] = parts
        elif isinstance(v, (list, tuple)):
            parts = [str(x).strip().lower() for x in v]
            bad = [x for x in parts if x not in ("s1", "s2", "s3", "1", "2", "3")]
            if bad:
                raise LiveStrategyError(
                    f"param 'trend_gate' accepts s1/s2/s3 (or none), got {bad}"
                )
            clean["trend_gate"] = parts or "none"
        else:
            raise LiveStrategyError(f"param 'trend_gate' must be a list or comma string, got {v!r}")
    return clean


def _normalize_blazing_overrides(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """🔥 R69 — تحقق التجاوزات لمحرك ZLF-End-To-End-Blazing «الترندية الملتهبة».

    المبيّح: معاملات الزقزاق نفسها المبيّحة للترندية
    (zz_mode/zz_depth/zz_deviation/zz_backstep/length) + قوالب الترند الثلاثة:
      trend_periods:  «7,15,25» أو قائمة — أعداد 2..500 (حتى 12 ترنداً)
      trend_confirm:  majority|all|any أو رقم صريح 1..500
      trend_gate:     s1/s2/s3/n5/n6 (بأي صيغة) أو none للتعطيل — الملتهبة
                      تبوّب خمسة أنواع (إشارتا R68 الجديدتان ن5/ن6 مع العائلة).
    معاملات liq_* غير منطبقة (كما في الترندية — النطاق يعتمد لحظة ظهور
    الزقزاق ونافذة الحساب = عمر النطاق) — تُرفض برسالة واضحة (لا تطبيق صامت).
    """
    if not raw:
        return {}
    blazing_zlf_keys = ("zz_mode", "zz_depth", "zz_deviation", "zz_backstep", "length")
    allowed = set(blazing_zlf_keys) | set(TRENDY_TREND_KEYS)
    unknown = sorted(k for k in raw if k not in allowed)
    if unknown:
        non_appl = [k for k in unknown if k in ZLF_PARAM_OVERRIDABLE]
        hint = (" — معاملات السيولة liq_* غير منطبقة على الملتهبة (النطاق يعتمد لحظة ظهور الزقزاق)" if non_appl else "")
        raise LiveStrategyError(
            f"Unsupported ZLF-End-To-End-Blazing param(s): {unknown}{hint} — "
            f"overridable: {sorted(allowed)}"
        )
    clean = normalize_zlf_overrides({k: raw[k] for k in raw if k in blazing_zlf_keys})
    if "trend_periods" in raw and raw["trend_periods"] is not None:
        clean["trend_periods"] = _parse_int_list(raw["trend_periods"], 2, 500, "trend_periods")
    if "trend_confirm" in raw and raw["trend_confirm"] is not None:
        v = raw["trend_confirm"]
        if isinstance(v, str) and v.strip().lower() in ("majority", "all", "any"):
            clean["trend_confirm"] = v.strip().lower()
        else:
            try:
                iv = int(float(v))
            except (TypeError, ValueError):
                raise LiveStrategyError(
                    f"param 'trend_confirm' must be majority|all|any or an integer, got {v!r}"
                )
            if not (1 <= iv <= 500):
                raise LiveStrategyError(f"param 'trend_confirm'={iv} out of range [1, 500]")
            clean["trend_confirm"] = iv
    if "trend_gate" in raw and raw["trend_gate"] is not None:
        v = raw["trend_gate"]
        ok_tokens = ("s1", "s2", "s3", "n5", "n6", "1", "2", "3", "5", "6")
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("none", "off", "false", "0", ""):
                clean["trend_gate"] = "none"
            else:
                parts = [x.strip().lower() for x in v.replace(";", ",").split(",") if x.strip()]
                bad = [x for x in parts if x not in ok_tokens]
                if bad:
                    raise LiveStrategyError(
                        f"param 'trend_gate' accepts s1/s2/s3/n5/n6 (or none), got {bad}"
                    )
                clean["trend_gate"] = parts
        elif isinstance(v, (list, tuple)):
            parts = [str(x).strip().lower() for x in v]
            bad = [x for x in parts if x not in ok_tokens]
            if bad:
                raise LiveStrategyError(
                    f"param 'trend_gate' accepts s1/s2/s3/n5/n6 (or none), got {bad}"
                )
            clean["trend_gate"] = parts or "none"
        else:
            raise LiveStrategyError(f"param 'trend_gate' must be a list or comma string, got {v!r}")
    return clean


def _build_strategy_config(
    param_overrides: Optional[Dict[str, Any]] = None,
    engine: str = "zlf",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """نسخة عميقة من قالب البطل + تطبيق التجاوزات المبيّحة على معاملات zigzag_fib.

    ✅ يصلح أيضاً خللاً كامناً قديماً: كان القالب المعياري (dict على مستوى
    الموديول) يُمرَّر للمحرك مباشرة — أي تطبيع/تعديل داخلي في المحرك كان سيُلوّث
    القالب لكل الطلبات اللاحقة. الآن كل تقييم يعمل على نسخته الخاصة.

    ✅ ROUND21-v2: `applied` يحمل الآن **المعاملات الفعلية كاملة** (القالب بعد
    التجاوزات) وليس التجاوزات فقط — meta.params_applied تصبح إعلاناً كاملاً
    عن النافذة المستخدمة فعلاً في كل جواب (شفافية بلا استثناء).

    يعيد (config, applied): applied = المعاملات المطبّقة فعلاً (للشفافية في meta).
    """
    # ✅ ROUND22: اختيار قالب المحرك — الافتراضي zlf (المحرك الحالي حرفياً)؛
    # zlf_e2e = قالب ZLF-End-To-End المنفصل (zigzag_fib_e2e) بلا أي مساس بالأصل؛
    # ✅ ROUND32: zlf_e2e_trendy = قالب «الترندية» المعزول (zigzag_fib_e2e_trendy
    # + قوالب الترند القالبية [7,15,25] — الأرقام في القالب لا في الكود).
    if engine == "zlf_e2e_trendy":
        template = ZLF_E2E_TRENDY_TRIPLE_SIGNAL
    elif engine == "zlf_e2e_blazing":
        # 🔥 R69: قالب «الترندية الملتهبة» (zigzag_fib_e2e_blazing — S1/S2/S3 بت-بت
        # + N5/N6) — محرك معزول جديد كلياً، لا مساس بأي قالب قائم.
        template = ZLF_E2E_BLAZING_QUINT_SIGNAL
    elif engine == "zlf_e2e":
        template = ZLF_E2E_TRIPLE_SIGNAL
    elif engine == "zlf_e2e_trendy_macd":
        # ✅ PRO73: «الترندية الماكدية» — الترندية + بوابة الموشرات (67 نسخة + الحالات)
        template = TRENDY_MACDIZED
    elif engine == "zlf_e2e_blazing_macd":
        # 🔥 PRO73: «الملتهبة الماكدية» — الملتهبة + بوابة الموشرات (67 نسخة + الحالات)
        template = BLAZING_MACDIZED
    else:
        template = ZLF_TRIPLE_SIGNAL
    cfg = copy.deepcopy(template["strategy_config"])
    applied: Dict[str, Any] = {}
    inds = cfg.get("indicators") or []
    if inds:
        params = inds[0].setdefault("params", {})
        # لقطة المعاملات الفعلية (القالب) — تُعلن دائماً حتى بلا تجاوزات.
        # تُقرأ من المفتاح الأصلي وتُبلَّغ باسم واجهة الاستعلام (zz_* / liq_*).
        for key in ZLF_PARAM_OVERRIDABLE:
            native = ZLF_PARAM_ALIAS_TO_NATIVE.get(key, key)
            if native in params:
                applied[key] = params[native]
        if param_overrides:
            for key, val in param_overrides.items():
                native = ZLF_PARAM_ALIAS_TO_NATIVE.get(key, key)
                params[native] = val
                applied[key] = val
        # ✅ ROUND32: لقطة قوالب الترند الفعلية + تطبيق تجاوزاتها — شفافية كاملة
        # (meta.params_applied تعلن دائماً الفترات/الإجماع/الأنواع المبوّبة المستخدمة)
        if engine == "zlf_e2e_trendy":
            for tk in TRENDY_TREND_KEYS:
                if tk in params:
                    applied[tk] = params[tk]
        # 🔥 R69: نفس شفافية قوالب الترند للملتهبة (الفترات/الإجماع/بوابة الخمسة)
        if engine == "zlf_e2e_blazing":
            for tk in TRENDY_TREND_KEYS:
                if tk in params:
                    applied[tk] = params[tk]
    return cfg, applied


# كاش النجاح: الجواب يتغير فقط عند إغلاق شمعة — 10s تخفض حرق ميزانية المزود
# ~10x مع أقصى تأخير لظهور إشارة جديدة = 10 ثوانٍ (مقبول لفريمات الدقائق).
# قابل للضبط تشغيلياً عبر LIVE_SIGNAL_CACHE_TTL (يُخفض إلى 1 للمحليات إن لزم).
CACHE_TTL_SECONDS = float(os.environ.get("LIVE_SIGNAL_CACHE_TTL", "10"))
EVALUATION_TIMEOUT_SECONDS = 45  # سقف صارم لعملية التقييم الواحدة

# الكاش السلبي للفشل المؤقت مع تراجع أُسّي: البداية 20-28 ثانية (جيتر)،
# وكل فشل جديد لنفس المفتاح يضاعف المدة حتى سقف 300s = مدة عقوبة المزود.
# الجيتر العشوائي يكسر تزامن «القطيع» فيخرج المطرودون من الكاش فرادى
# بدل ضربة جماعية تعيد إشعال عقوبة Binance فور انتهائها (thundering herd).
NEGATIVE_CACHE_TTL_BASE = 20.0
NEGATIVE_CACHE_TTL_JITTER = 8.0
NEGATIVE_CACHE_TTL_MAX = 300.0

# تدهور لطيف (stale-while-revalidate): عند فشل مؤقت لتحديث رمز لديه إشارة
# سابقة محسوبة، نخدم الإشارة القديمة موسومة بدل 503 — فشل جلب 11 شمعة
# لا يلغي إشارة حُسبت من 2000 شمعة سليمة. بعد STALE_MAX يصبح 503 صادقاً.
# الآمن إشاراتياً: الجواب لا يتغير إلا بإغلاق شمعة، و60s < شمعة 5m كاملة.
# الوسم في الجواب: meta.stale=true + meta.stale_age_s — الفرونت يقرر.
STALE_MAX_SECONDS = float(os.environ.get("LIVE_SIGNAL_STALE_MAX", "60"))

_LABEL_RE = re.compile(r"\b([SN])([12356])\b")

# مدة الفريم للأغراض الهيورستيكية فقط (اكتشاف الشمعة الحية + طابع شمعة الملء).
# الفريمات الشبكية غير الثابتة تُعالج حالات خاصة، والفريم غير المدعوم يرفضه
# المزود نفسه برسالته الموحدة (مصدر حقيقة واحد لعقد الفريمات).
_FIXED_TF = {
    "1m": timedelta(minutes=1), "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5), "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30), "45m": timedelta(minutes=45),
    "90m": timedelta(minutes=90), "1h": timedelta(hours=1),
    "2h": timedelta(hours=2), "4h": timedelta(hours=4),
    "6h": timedelta(hours=6), "8h": timedelta(hours=8),
    "12h": timedelta(hours=12), "1d": timedelta(days=1),
    "2d": timedelta(days=2), "3d": timedelta(days=3),
    "1w": timedelta(days=7), "2w": timedelta(days=14),
}


class LiveStrategyError(ValueError):
    """رفض عقد صريح → 400 برسالة موحدة."""


class LiveStrategyTransientError(RuntimeError):
    """فشل مؤقت للمزود (حظر/تهدئة 418/429 أو نافذة غير مكتملة) → 503.

    عقد واضح للفرونت: 503 = أعد المحاولة بعد ثوانٍ (كاش المزود يملا الفجوات
    بعد انتهاء التهدئة) — عكس 400 = خلل دائم لا تُعيد المحاولة.
    لا إشارة تُخدم أبداً من نافذة غير مكتملة (صحة > توفر).
    """


# ---------------------------------------------------------------------------
# الكاش ودمج الطلبات المتزامنة (thread-safe — حلقات أحداث متعددة آمنة)
# ---------------------------------------------------------------------------
_cache: Dict[Tuple[str, str, str, str], Tuple[float, Dict[str, Any]]] = {}
# الكاش السلبي: key -> (expiry_monotonic, رسالة الخطأ المؤقت، عدد المحاولات) —
# إجابة 503 فورية بلا شبكة، والمدة تتضاعف أُسّياً مع كل فشل متتابع
_neg_cache: Dict[Tuple[str, str, str, str], Tuple[float, str, int]] = {}
_lock = threading.Lock()
_inflight: Dict[Tuple[str, str, str, str], threading.Event] = {}

_shared_data_service = DataService()


def invalidate_cache(symbol: Optional[str] = None) -> None:
    """إفراغ الكاش (اختياري للاختبار/الصيانة)."""
    with _lock:
        if symbol is None:
            _cache.clear()
            _neg_cache.clear()
        else:
            sym = symbol.strip().upper()
            for k in [k for k in _cache if k[0] == sym]:
                _cache.pop(k, None)
            for k in [k for k in _neg_cache if k[0] == sym]:
                _neg_cache.pop(k, None)


def _neg_put(key: Tuple[str, str, str, str], message: str) -> float:
    """يخزّن إدخالاً سلبياً بتراجع أُسّي ويعيد الـTTL الفعلي.

    كل فشل مؤقت متتابع لنفس المفتاح يضاعف المدة (20-28 → 40-56 → … → 300s سقف
    = مدة عقوبة المزود) — يكسر تزامن القطيع ويجعل محاولات الشفاء فردية متناثرة.
    تنظيف عرضي للإدخالات المنتهية عند تجاوز الحد — لا تسريب ولا تضخم.
    """
    now = _time.monotonic()
    with _lock:
        prev = _neg_cache.get(key)
        attempts = (prev[2] + 1) if prev else 1
        base = min(NEGATIVE_CACHE_TTL_BASE * (2 ** (attempts - 1)), NEGATIVE_CACHE_TTL_MAX)
        ttl = base + random.uniform(0.0, NEGATIVE_CACHE_TTL_JITTER)
        _neg_cache[key] = (now + ttl, message, attempts)
        if len(_neg_cache) > 512:
            for k in [k for k, v in _neg_cache.items() if v[0] <= now]:
                _neg_cache.pop(k, None)
    return ttl


def _stale_payload(hit: Tuple[float, Dict[str, Any]]) -> Dict[str, Any]:
    """نسخة الجواب القديم موسومة (stale) — البنية التعاقدية كما هي حرفياً."""
    payload = dict(hit[1])
    meta = dict(payload.get("meta") or {})
    meta["stale"] = True
    meta["stale_age_s"] = round(_time.monotonic() - hit[0], 1)
    meta["stale_max_s"] = STALE_MAX_SECONDS
    payload["meta"] = meta
    return payload


def _cache_key(symbol: str, market: str, timeframe: str, strategy: str) -> Tuple[str, str, str, str]:
    return (symbol.strip().upper(), market.strip().lower(), timeframe.strip(), strategy.strip().lower())


def _next_candle_open(last_open: datetime, timeframe: str) -> datetime:
    """وقت فتح الشمعة التالية (الشمعة الحية) — يدعم '1M' الشهرية تقويمياً."""
    tf = str(timeframe).strip()
    if tf == "1M":
        if last_open.month == 12:
            return last_open.replace(year=last_open.year + 1, month=1, day=1,
                                     hour=0, minute=0, second=0, microsecond=0)
        return last_open.replace(month=last_open.month + 1, day=1,
                                 hour=0, minute=0, second=0, microsecond=0)
    delta = _FIXED_TF.get(tf)
    if delta is None:
        # فريم عريض غير قياسي — بعد آمن بعد آخر شمعة مغلقة
        return last_open + timedelta(hours=1)
    return last_open + delta


def _is_forming(last_open: datetime, timeframe: str, now: datetime) -> bool:
    """هل آخر شمعة من المزود هي الشمعة الحية (غير المغلقة)؟"""
    tf = str(timeframe).strip()
    if tf == "1M":
        return (last_open.year == now.year and last_open.month == now.month)
    delta = _FIXED_TF.get(tf)
    if delta is None:
        return False  # لا نحذف شيئاً نجهله — المزود هو مصدر الحقيقة
    return (last_open + delta) > now


def _window_start(timeframe: str, now: datetime) -> datetime:
    """بداية النافذة المطلوبة هيوريستيكياً — الاقتصّ النهائي يتم بعد الجلب."""
    tf = str(timeframe).strip()
    if tf == "1M":
        return now - timedelta(days=3650)
    delta = _FIXED_TF.get(tf)
    if delta is None:
        return now - timedelta(days=3650)
    return now - delta * (WINDOW_CANDLES + 10)


# ---------------------------------------------------------------------------
# التقييم
# ---------------------------------------------------------------------------
class _PreparedDataService:
    """محوّل بيانات: يُغذّي المحرك بنافذة مُجهزة (مغلقة + شمعة ملء اصطناعية).

    المحرك يستدعي get_historicallastvirsion فقط (فحص: usage واحد في engine1)
    — لذا هذا الغلاف يعطينا تحكماً كاملاً بالبيانات دون لمس المحرك.
    """

    def __init__(self, df: pd.DataFrame):
        self._df = df

    async def get_historicallastvirsion(self, **kwargs) -> pd.DataFrame:  # noqa: D401
        return self._df.copy()


def _parse_label(decision_reason: Optional[str]) -> str:
    """S1/S2/S3/N5/N6 من decision_reason — نفس اسم القاعدة في الباك تست حرفياً.

    🔥 R69: الملتهبة تحمل N5/N6 في أسماء قواعدها — المُطابقة تشمل العائلتين.
    (عقد توافر خلفي: أسماء الترندية لا تحوي N5/N6 فلا يتغير سلوكها إطلاقاً.)
    """
    if decision_reason:
        m = _LABEL_RE.search(str(decision_reason))
        if m:
            return f"{m.group(1)}{m.group(2)}"
    # احتياط صريح — لا تخصيص صامت: العلامة مجهولة الاسم تُعرض كما هي
    return "S?"


def _to_ms(ts: datetime) -> int:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return int(ts.timestamp() * 1000)


async def _fetch_window(symbol: str, market: str, timeframe: str) -> Tuple[Optional[pd.DataFrame], datetime]:
    """المرحلة ١ — الجلب الشبكي على حلقة الأحداث الرئيسية حصراً.

    data_service → المزود (كل I/O الشبكي وأقفاله المشتركة) يعيش على حلقة
    الـAPI الدائمة — لا حلقات مؤقتة تلمسه من هذه الخدمة إطلاقاً.
    """
    now = datetime.now(timezone.utc)
    start = _window_start(timeframe, now)
    df = await _shared_data_service.get_historical_last_version(
        symbol=symbol,
        timeframe=timeframe,
        market=market,
        start_date=start,
        end_date=now,
        use_cache=True,
        tz_offset_minutes=0,  # الطوابع تبقى UTC — الفرونت يثبّت على openTime مباشرة
    )

    # تمييز الفشل المؤقت عن الخلل الدائم — عقد الاستجابة:
    # نافذة فارغة أو غير مكتملة بسبب حظر/تهدئة المزود → LiveStrategyTransientError (503)
    # فارغ بلا علامة مؤقتة (رمز غير مدرج/بلا تاريخ فعل) → LiveStrategyError (400)
    if df is None or df.empty:
        incomplete = bool((getattr(df, "attrs", None) or {}).get("fetch_incomplete"))
        rate_limited = False
        try:
            provider = _shared_data_service.providers.get(market)
            rate_limited = bool(provider and hasattr(provider, "is_rate_limited") and provider.is_rate_limited())
        except Exception:  # noqa: BLE001 — فحص تحسيني لا يعطل المسار
            rate_limited = False
        if incomplete or rate_limited:
            raise LiveStrategyTransientError(
                f"data provider temporarily rate-limited (418/429 cooldown) for {symbol} {timeframe} — retry shortly"
            )
        raise LiveStrategyError(f"No data available for {symbol} {timeframe} ({market})")

    # نافذة جزئية (بعض الدفعات فشلت والبقية نجحت) → رفض تقييم صارم:
    # زجزاج/فيبو على شموع ناقصة يولّد إشارات مغلوطة — الصحة قبل التوفر.
    if bool((getattr(df, "attrs", None) or {}).get("fetch_incomplete")):
        raise LiveStrategyTransientError(
            f"incomplete candle window for {symbol} {timeframe} (provider cooldown) — retry shortly"
        )

    return df, now


def _evaluate_compute(
    df_raw: Optional[pd.DataFrame],
    symbol: str,
    market: str,
    timeframe: str,
    strategy_key: str,
    now: datetime,
    param_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """المرحلة ٢ — الحساب الثقيل في خيط عامل بحلقة خاصة **معزولة**.

    asyncio.run هنا آمن بنيوياً لأن كل ما تلمسه هذه الحلقة محلي:
    المحرك يستدعي get_historicallastvirsion فقط (فحص: usage واحد في
    engine1) والغلاف _PreparedDataService يعيد نسخة محلية — صفر primitives
    asyncio مشتركة مع المزود/الخدمات (نفس نمط الباك تست الداخلي 14.1).
    """
    async def _run() -> Dict[str, Any]:
        df = df_raw.copy() if df_raw is not None else None  # الخيط يملك نسخته الخاصة
        if df is None or df.empty:
            raise LiveStrategyError(f"No data available for {symbol} {timeframe} ({market})")

        df = df.sort_index()

        # 2) حذف الشمعة الحية (غير المغلقة) إن وجدت — التقييم على المغلقة فقط (بلا repaint)
        forming_open: Optional[float] = None
        if len(df) > 0 and _is_forming(df.index[-1].to_pydatetime(), timeframe, now):
            forming_open = float(df["open"].iloc[-1])
            df = df.iloc[:-1]

        if len(df) < MIN_CANDLES_FOR_ENGINE:
            return _waiting_payload(symbol, market, timeframe, strategy_key,
                                    note=f"insufficient history: {len(df)} closed candles")

        # اقتصاص النافذة إلى آخر WINDOW_CANDLES شمعة مغلقة
        if len(df) > WINDOW_CANDLES:
            df = df.iloc[-WINDOW_CANDLES:]

        # 3) شمعة الملء الاصطناعية (open حقيقي للشمعة الحية، مسطحة، حجم صفر)
        last_open_ts = df.index[-1].to_pydatetime()
        live_open = forming_open if forming_open is not None else float(df["close"].iloc[-1])
        live_open_ts = _next_candle_open(last_open_ts, timeframe)
        if live_open_ts <= last_open_ts:  # حارس ترتيب صارم
            live_open_ts = last_open_ts + timedelta(minutes=1)
        fill_row = pd.DataFrame(
            {"open": [live_open], "high": [live_open], "low": [live_open],
             "close": [live_open], "volume": [0.0]},
            index=pd.DatetimeIndex([live_open_ts], name=df.index.name or "time"),
        )
        df_prepared = pd.concat([df, fill_row])
        df_prepared = df_prepared[~df_prepared.index.duplicated(keep="last")]

        # 4) تشغيل محرك الباك تست نفسه على النافذة — بطل العقد: SL 2.0 / TP 99.0
        # ✅ ROUND21: نسخة عميقة + تجاوزات المعاملات المبيّحة (لا تلويث للقالب المعياري)
        # ✅ ROUND22: اختيار القالب حسب المحرك (zlf = الحالي كما هو · zlf_e2e = المنفصل)
        strategy_cfg, params_applied = _build_strategy_config(param_overrides, engine=strategy_key)
        config = BacktestConfig(
            name=f"live-signal:{symbol}:{timeframe}",
            symbols=[symbol],
            timeframe=timeframe,
            market=market,
            start_date=df.index[0].to_pydatetime(),
            end_date=live_open_ts,
            initial_capital=10000.0,
            position_size_percent=100.0,     # ✅ R58 — رأس مال كامل (نسبة مئوية حقيقية في وضع percentage)
            stop_loss_percent=CHAMPION_SL_PERCENT,
            take_profit_percent=CHAMPION_TP_PERCENT,
            fill_model="next_open",
            tz_offset_minutes=0,
            strategy_config=strategy_cfg,
        )

        engine = BacktestEngine(_PreparedDataService(df_prepared))
        result = await engine.run_backtest(config)

        # 5) دورة الحياة من نتيجة المحاكاة نفسها
        trades = list(getattr(result, "trades", []) or [])
        trade_points = list(getattr(result, "trade_points", []) or [])
        entries = [tp for tp in trade_points if isinstance(tp, dict) and tp.get("type") == "entry"]

        updated_at = _to_ms(datetime.now(timezone.utc))
        base_meta = {
            "window": {
                "closed_candles": int(len(df)),
                "first_open": _to_ms(df.index[0].to_pydatetime()),
                "last_closed_open": _to_ms(df.index[-1].to_pydatetime()),
                "live_candle_open": _to_ms(live_open_ts),
                "live_candle_open_price": live_open,
            },
            "fill_model": "next_open",
            "risk": {"stop_loss_percent": CHAMPION_SL_PERCENT, "take_profit_percent": CHAMPION_TP_PERCENT},
            # ✅ ROUND22: هوية المحرك صراحةً في كل جواب (zlf أو ZLF-End-To-End)
            "engine": _ENGINE_META.get(strategy_key, strategy_key),
        }
        # ✅ ROUND21: الشفافية — الجواب يعلن المعاملات التي طبّقها هذا التقييم
        # (يظهر فقط عند تمرير تجاوزات — الأوفّلود الافتراضي بلا تغيير في شكل الجواب)
        if params_applied:
            base_meta["params_applied"] = dict(params_applied)

        if not trades:
            return _waiting_payload(symbol, market, timeframe, strategy_key, meta=base_meta, updated_at=updated_at)

        last = trades[-1]
        exit_reason = str(getattr(last, "exit_reason", "") or "")

        if exit_reason == "End of Data":
            # الموضع ما يزال مفتوحاً حياً → الإشارة نشطة
            ep = next((tp for tp in entries if tp.get("trade_id") == getattr(last, "id", None)), None)
            label = _parse_label((ep or {}).get("decision_reason"))
            seq = (entries.index(ep) + 1) if ep in entries else len(entries)
            # side: حقل direction النصي ("long"/"short") — والاحتياط من enum position_type
            side_val = str(getattr(last, "direction", None) or "").strip().lower()
            if side_val not in ("long", "short"):
                side_val = str(getattr(last, "position_type", "long")).split(".")[-1].strip().lower()
            signal = {
                "label": label,
                "seq": int(seq),
                "side": side_val,
                "price": float(getattr(last, "entry_price")),
                "candle_time": _to_ms(getattr(last, "entry_time")),
                "emitted_at": updated_at,
                "sl": float(getattr(last, "stop_loss") or 0.0) or None,
                "tp": float(getattr(last, "take_profit") or 0.0) or None,
                "decision_reason": (ep or {}).get("decision_reason"),
            }
            return {
                "symbol": symbol, "market": market, "timeframe": timeframe,
                "strategy": strategy_key,
                "has_signal": True, "state": "active",
                "signal": signal, "updated_at": updated_at, "meta": base_meta,
            }

        # خروج حقيقي (SL / انقلاب الساق / خروج إشارة) → آخر إشارة أُلغيت
        return {
            "symbol": symbol, "market": market, "timeframe": timeframe,
            "strategy": strategy_key,
            "has_signal": False, "state": "invalidated",
            "signal": None,
            "invalidated_by": exit_reason,
            "updated_at": updated_at, "meta": base_meta,
        }

    return asyncio.run(_run())


def _waiting_payload(symbol, market, timeframe, strategy_key, meta=None, updated_at=None, note=None):
    payload = {
        "symbol": symbol, "market": market, "timeframe": timeframe,
        "strategy": strategy_key,
        "has_signal": False, "state": "waiting", "signal": None,
        "updated_at": updated_at or _to_ms(datetime.now(timezone.utc)),
    }
    if meta:
        payload["meta"] = meta
    if note:
        payload["note"] = note
    return payload


async def _evaluate_full(
    symbol: str, market: str, timeframe: str, strategy_key: str,
    param_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """خط الأنابيب الكامل: جلب على الحلقة الرئيسية + حساب في خيط معزول."""
    df_raw, now = await _fetch_window(symbol, market, timeframe)
    return await asyncio.to_thread(
        _evaluate_compute, df_raw, symbol, market, timeframe, strategy_key, now, param_overrides,
    )


async def evaluate_live_signal(
    symbol: str, market: str, timeframe: str, strategy: str,
    param_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """نقطة الدخول العامة — كاش نجاح 10s + كاش سلبي للفشل المؤقت + دمج
    الطلبات المتزامنة بانتظار غير حاجب + سقف زمني صارم.

    ✅ ROUND21: param_overrides = تجاوزات معاملات zigzag_fib (اختيارية، مبيّحة).
    توقيع التجاوزات جزء من مفتاح الكاش — نداء (20) لا يعيد أبداً جواب نداء (240).

    تسلسل الأسبقية (الأرخص أولاً):
      1. كاش سلبي صالح → 503 فوري، صفر شبكة (يحمي ميزانية المزود من القطيع).
      2. كاش نجاح طازج → الجواب فوراً، صفر شبكة.
      3. حساب جارٍ لنفس المفتاح → انتظر نتيجته (غير حاجب) وارث كاشه.
      4. حساب كامل — وعند الفشل المؤقت يُخزَّن الكاش السلبي للجميع.
    """
    key_strategy = strategy.strip().lower()
    if key_strategy not in _STRATEGY_ALIASES:
        raise LiveStrategyError(
            f"Unsupported strategy: {strategy!r} — supported: 'zigzag_fib' "
            "(ZLF — المحرك الحالي) و 'zigzag_fib_e2e' "
            "(ZLF-End-To-End — المحرك المنفصل — ROUND22) و 'zigzag_fib_e2e_trendy' "
            "(ZLF-End-To-End-Trendy — الزقزاق البطل e2e الترنديه — ROUND32) و "
            "'zigzag_fib_e2e_blazing' "
            "(ZLF-End-To-End-Blazing — الترندية الملتهبة S1/S2/S3+N5/N6 — R69) و "
            "'zigzag_fib_e2e_trendy_macd' "
            "(PRO73 — الترندية الماكدية: بوابة الموشرات 67 نسخة + الحالات) و "
            "'zigzag_fib_e2e_blazing_macd' "
            "(PRO73 — الملتهبة الماكدية: بوابة الموشرات 67 نسخة + الحالات)"
        )
    strategy_key = _STRATEGY_ALIASES[key_strategy]
    # ✅ ROUND21: تحقق التجاوزات قبل أي شيء (خطأ عقد → 400) + توقيعها في مفتاح الكاش
    # ✅ ROUND22: تحقق حسب المحرك — للمحرك المنفصل معاملاته الخاصة فقط
    # ✅ ROUND32: للترندية معاملاتها الخاصة (الزقزاق + قوالب الترند الثلاثة)
    # 🔥 R69: للملتهبة معاملاتها (الزقزاق + قوالب الترند — البوابة تقبل ن5/ن6)
    # ✅ PRO73: للماكديين نفس معاملات أصليهما (الزقزاق + قوالب الترند) —
    #           طبقة الموشرات قالبية داخل القالب (تُدار عبر خدمة التحكم لا query)
    if strategy_key in ("zlf_e2e_blazing", "zlf_e2e_blazing_macd"):
        applied = _normalize_blazing_overrides(param_overrides)
    elif strategy_key in ("zlf_e2e_trendy", "zlf_e2e_trendy_macd"):
        applied = _normalize_trendy_overrides(param_overrides)
    elif strategy_key == "zlf_e2e":
        applied = _normalize_e2e_overrides(param_overrides)
    else:
        applied = normalize_zlf_overrides(param_overrides)
    override_sig = json.dumps(applied, sort_keys=True, separators=(",", ":")) if applied else ""
    key = _cache_key(symbol, market, timeframe, strategy_key) + (override_sig,)

    # 1) كاش طازج؟ ثم (كاش سلبي + تدهور لطيف للنجاح القديم)؟
    now_mono = _time.monotonic()
    with _lock:
        neg = _neg_cache.get(key)          # (expiry, msg, attempts) أو None
        neg_active = bool(neg and now_mono < neg[0])
        hit = _cache.get(key)
        hit_age = (now_mono - hit[0]) if hit else None
        fresh = bool(hit and hit_age < CACHE_TTL_SECONDS)
        stale_ok = bool(hit and hit_age < STALE_MAX_SECONDS)
        if fresh:
            return hit[1]
        if neg_active:
            if stale_ok:
                # فشل تحديث لرمز لديه إشارة سابقة سليمة → نخدم القديم موسوماً
                # (فشل جلب 11 شمعة لا يلغي إشارة حُسبت من 2000 شمعة)
                return _stale_payload(hit)
            raise LiveStrategyTransientError(neg[1])
        event = _inflight.get(key)

    if event is not None:
        # طلب آخر يحسب نفس المفتاح — انتظر نتيجته بدون تجميد حلقة الأحداث
        # (event.wait الحاجب كان يجمّد الحلقة كلها حتى 45 ثانية!)
        if await asyncio.to_thread(event.wait, EVALUATION_TIMEOUT_SECONDS):
            with _lock:
                now_mono = _time.monotonic()
                neg = _neg_cache.get(key)
                neg_active = bool(neg and now_mono < neg[0])
                hit = _cache.get(key)
                hit_age = (now_mono - hit[0]) if hit else None
                if hit and hit_age < CACHE_TTL_SECONDS:
                    return hit[1]
                if neg_active:
                    if hit and hit_age < STALE_MAX_SECONDS:
                        return _stale_payload(hit)
                    # المنتَج فشل مؤقتاً — ورّث الكاش السلبي بدل طلب شبكي مكرر
                    raise LiveStrategyTransientError(neg[1])
                if hit:
                    return hit[1]
        # انتهى الانتظار بلا نتيجة → تابع حساباً خاصاً (أمان قبل الأداء)

    # 2) سجّل نفسك كحاسب حالي
    my_event = threading.Event()
    with _lock:
        _inflight[key] = my_event

    try:
        started = _time.perf_counter()
        try:
            payload = await asyncio.wait_for(
                _evaluate_full(key[0], key[1], key[2], strategy_key, applied or None),
                timeout=EVALUATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # تجاوز السقف = فشل مؤقت بإجماع العقد (503) + كاش سلبي للقطيع
            msg = f"evaluation timed out after {EVALUATION_TIMEOUT_SECONDS}s for {key[0]} {key[2]} — retry shortly"
            _neg_put(key, msg)
            raise LiveStrategyTransientError(msg) from None
        except LiveStrategyTransientError as e:
            # فشل مؤقت (تهدئة 418/429 أو نافذة غير مكتملة) — اكتم القطيع 20-28s
            ttl = _neg_put(key, str(e))
            logger.debug(
                "negative cache: %s %s %s → 503 لمدة %.1fs (بدون شبكة)",
                key[0], key[1], key[2], ttl,
            )
            raise
        payload.setdefault("meta", {})["evaluation_ms"] = round((_time.perf_counter() - started) * 1000, 1)
        with _lock:
            _cache[key] = (_time.monotonic(), payload)
            _neg_cache.pop(key, None)  # نجاح = صفّار التراجع الأسي وفتح الطريق
        return payload
    finally:
        with _lock:
            # تحقق الهوية: طالب خاص انطلق بعد انتهاء انتظاره لا يمسح event غيره
            if _inflight.get(key) is my_event:
                _inflight.pop(key, None)
        my_event.set()
