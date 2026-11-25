# =============================================================================
# B9 — «MACD Buy Strategy 9B» — بوابات MACD متعددة الفريمات (محرك معزول)
# =============================================================================
# أمر صاحب القرار (2026-11-22): «الان لدينا استراتيجيه جديده مبنيه باستخدام
#   بين سكربت اريد منك ان تحولها وتدمجها في النظام» — سكربت Pine
#   «MACD Buy Strategy 9B» (شراء فقط · MACD متعدد الفريمات).
#
# هذا الملف = محرك معزول جديد كلياً (إضافة تسجيل فقط — لا مساس بأي محرك
# قائم):
#   · indicator: b9_macd_gates   (مرادفات: b9 · b9_macd)
#     overlay:   b9_macd_gates
#   · سلاسل b9g_* → أعمدة ind_b9g_* قابلة للاستخدام مباشرة في شروط JSON
#     بصيغة indicator:b9_macd_gates:b9g_buy (وأي سلسلة أخرى).
#
# شروط الشراء الأربعة (حرفياً من سكربت Pine):
#   condW_pos      : MACD الأسبوعي الثلاثة فوق إشاراتها
#                    (1W A 6/13/4 · 1W B 12/26/4 · 1W C 18/39/4)
#   condD_pos      : MACD اليومي B/C فوق إشارتيهما
#                    (1D B 12/26/6 · 1D C 18/39/4)
#   cond4H_core    : MACD 4H B (12/26/6) فوق إشارته وفوق الصفر (confirmed)
#   condAnyAbove4H : أي ماكد أعلى (1D A/B/C أو 1W A/B/C) فوق إشارته وفوق
#                    قيمة ماكد 4H B نفسها (مقارنة قيم عابرة للفريمات)
#   buyCond        = condW_pos ∧ condD_pos ∧ cond4H_core ∧ condAnyAbove4H
#
# وفاء Pine (قرارات معمارية موثقة):
#   1) MACD حرفياً كـ ta.macd: line = EMA(fast) − EMA(slow) ·
#      signal = EMA(line, signal) · hist = line − signal — كلها EMA بنمط
#      TradingView (بذرة SMA عند أول length قيمة صالحة ثم alpha=2/(len+1)
#      تكرارياً — نفس _ema_talib بنواة R76 ونفس عقد mtf_gates/MTFEMA).
#      ⚠️ هذا يختلف عمداً عن نواة mtf_oscillator_core (signal=SMA بنمط
#      CM_MacD_Ult_MTF) — B9 يستخدم ta.macd القياسي (signal=EMA).
#   2) دلاء الفريم الأعلى: 4H/1D على مرسى epoch UTC (00:00 · 04:00 ...)
#      و1W على مرسى الاثنين (نفس TradingView) — عبر _build_htf_bars من
#      overlays_mtf_ema (MTFEMA1).
#   3) الإسقاط — وضعان عبر htf_mode (v4 · LIVE1):
#      · "confirmed" (الافتراضي — سلوك v2/v3 بلا أي تغيير): قيمة HTF عند
#        أي شمعة = آخر شريط HTF مكتمل فقط — الشريط النامي لا يُرى. هذا
#        وضع «confirmed» الذي اختاره مؤلف السكربت (useEarlyHTF=false —
#        «4h B (confirmed on 4h close)») وهو ما يعرضه TradingView على
#        الشموع التاريخية وفي الستراتيجي-تستر.
#      · "live" (الجديد): الشريط النامي مرئي — قيمة الدلو الجاري محدثة
#        بإغلاق الشمعة الحالية (خطوة EMA واحدة من بذرة آخر دلو مكتمل).
#        هذا بالضبط ما يعرضه TradingView على الحافة الحية (request.security
#        بلا إزاحة يعيد قيمة الشريط النامي في الوقت الحي) — وهو ما يراه
#        صاحب القرار على شارت TV: إشارات تشتعل داخل الأسبوع قبل إغلاقه
#        (مناطق ما قبل الصعود). سببي 100%: لا أي معلومات مستقبلية (يستخدم
#        إغلاق الشمعة الحالية فقط) — لكن القيمة قد تُرسم مجدداً لاحقاً إذا
#        اكتمل الدلو مختلفاً — نفس سلوك TV الحي حرفياً. أما lookahead_on
#        (useEarlyHTF=true التاريخي = رؤية إغلاق الأسبوع من أوله = استشراف
#        صريح للمستقبل) فمحظور عمداً: لا نبيع وهم استشراف.
#   4) فشل-الإغلاق عند الإحماء (fail-closed): أي ورقة بقيمة مفقودة
#      (إحماء EMA الأسبوعي 18/39/4 ≈ 42 أسبوعاً) ⇒ الشرط False — البوابة
#      مغلقة حتى جاهزية كل النسخ (عكس «حياد الإحماء» في QMOM1 — هنا
#      condW_pos شرط دخول جوهري لا يُحايد).
#   5) نافذة التفعيل active_start/active_end: بوابات b9g_buy على نافذة
#      التداول المستهدفة فقط — يسمح بتشغيل الباك-تست على بيانات ممتدة
#      قبل النافذة (إحماء MACD الأسبوعي وتقارب EMA كما في TradingView
#      الذي يرى التاريخ كاملاً) مع حصر الصفقات داخل النافذة نفسها
#      («نختبرها على الفترات حقها الي استخدمناها سابقاً» حرفياً).
#
# المخرجات (JSON-آمنة — لا NaN/Inf):
#   series:
#     b9g_buy                  — شرط الشراء النهائي 0/1 (الشجرة ∧ نافذة التفعيل)
#     b9g_cond                 — الشجرة وحدها 0/1 (شفافية — بلا نافذة)
#     b9g_sub_w_pos            — condW_pos 0/1        ┐
#     b9g_sub_d_pos            — condD_pos 0/1        │ شفافية الفروع الأربعة
#     b9g_sub_4h_core          — cond4H_core 0/1      │ (sub_labels قالبية)
#     b9g_sub_any_above_4h     — condAnyAbove4H 0/1   ┘
#     b9g_osc_<id>_line/signal/hist — قيم MACD المسقطة لكل نسخة (للرسم
#                                    والتحقق والشروط المباشرة)
#   meta: صدى النسخ (htf_bars/first_valid_*) + نافذة التفعيل + العدادات.
#
# الدمج مع ترند 100 (المهمة): بوابة الدخول «فوق ترند 100» وشرط الخروج
# «استجد ترند 100 في رسم جديد» يعيشان في مؤشر trend_fractal المستقل
# (فترات قالبية — periods:[100]) — يُضاف لقائمة المؤشرات في الاستراتيجية:
#     دخول: indicator:b9_macd_gates:b9g_buy > 0  ∧  indicator:trend_fractal:trf_p100_bias > 0
#     خروج: indicator:trend_fractal:trf_p100_new_upper > 0  ∨  ..._new_lower > 0
# (لا يحتاج هذا الملف أي معرفة بالترند — فصل كامل للمسؤوليات).
# =============================================================================

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.services.indicators.zigzag_fib_core import norm_candles as _norm_candles
from app.services.indicators.overlays_mtf_ema import (
    _build_htf_bars,
    _parse_resolution,
)
from app.services.indicators.mtf_oscillator_core import (
    evaluate_conditions,
)

_LOG = logging.getLogger(__name__)

__all__ = [
    "b9_macd_gates",
    "B9_MACD_GATES_ENGINE_NAME",
    "B9_MACD_GATES_SPEC",
    "B9_DEFAULT_INSTANCES",
    "B9_DEFAULT_CONDITIONS",
    "B9_DEFAULT_SUB_LABELS",
]

B9_MACD_GATES_ENGINE_NAME = "B9-MACD-Gates"
B9_MACD_GATES_SPEC = "B9-macd-mtf-gates"
B9_STRATEGY_AR_NAME = "ماكد 9B — بوابات MACD متعددة الفريمات"

# ---------------------------------------------------------------------------
# القالب الافتراضي — نسخ MACD السبع المستخدمة في شروط الشراء حرفياً
# (النسخ المرسومة فقط في Pine — 5m/15m/1h/4hA/3D/1WD — لا تدخل الشروط،
#  ولم تُحسب هنا عمداً: المحرك استراتيجي لا لوحة رسم).
# ---------------------------------------------------------------------------
B9_DEFAULT_INSTANCES: List[Dict[str, Any]] = [
    {"id": "macd_4h_12_26_6", "timeframe": "240", "fast": 12, "slow": 26, "signal": 6,
     "doc": "4H B (12/26/6) — نواة الشرط المؤكدة (confirmed on 4h close)"},
    {"id": "macd_1d_6_13_4", "timeframe": "1D", "fast": 6, "slow": 13, "signal": 4,
     "doc": "1D A (6/13/4)"},
    {"id": "macd_1d_12_26_6", "timeframe": "1D", "fast": 12, "slow": 26, "signal": 6,
     "doc": "1D B (12/26/6)"},
    {"id": "macd_1d_18_39_4", "timeframe": "1D", "fast": 18, "slow": 39, "signal": 4,
     "doc": "1D C (18/39/4)"},
    {"id": "macd_1w_6_13_4", "timeframe": "1W", "fast": 6, "slow": 13, "signal": 4,
     "doc": "1W A (6/13/4)"},
    {"id": "macd_1w_12_26_4", "timeframe": "1W", "fast": 12, "slow": 26, "signal": 4,
     "doc": "1W B (12/26/4)"},
    {"id": "macd_1w_18_39_4", "timeframe": "1W", "fast": 18, "slow": 39, "signal": 4,
     "doc": "1W C (18/39/4)"},
]

# تسميات الفروع الأربعة للشجرة الافتراضية (سلاسل الشفافية b9g_sub_*)
B9_DEFAULT_SUB_LABELS: List[str] = ["w_pos", "d_pos", "4h_core", "any_above_4h"]


def _above_leaf(inst_id: str) -> Dict[str, Any]:
    """فرع condAnyAbove4H لنسخة واحدة: فوق إشارتها ∧ فوق خط 4H B."""
    return {
        "logic": "and",
        "conditions": [
            {"left": f"osc:{inst_id}.line", "op": ">", "right": f"osc:{inst_id}.signal"},
            {"left": f"osc:{inst_id}.line", "op": ">", "right": "osc:macd_4h_12_26_6.line"},
        ],
    }


#: الشجرة الافتراضية — buyCond حرفياً من السكربت
#: (condW_pos ∧ condD_pos ∧ cond4H_core ∧ condAnyAbove4H)
B9_DEFAULT_CONDITIONS: Dict[str, Any] = {
    "logic": "and",
    "conditions": [
        {
            "name": "condW_pos — الماكد الأسبوعي الثلاثة فوق إشاراتها (1W A/B/C)",
            "logic": "and",
            "conditions": [
                {"left": "osc:macd_1w_6_13_4.line", "op": ">",
                 "right": "osc:macd_1w_6_13_4.signal"},
                {"left": "osc:macd_1w_12_26_4.line", "op": ">",
                 "right": "osc:macd_1w_12_26_4.signal"},
                {"left": "osc:macd_1w_18_39_4.line", "op": ">",
                 "right": "osc:macd_1w_18_39_4.signal"},
            ],
        },
        {
            "name": "condD_pos — الماكد اليومي B/C فوق إشارتيهما",
            "logic": "and",
            "conditions": [
                {"left": "osc:macd_1d_12_26_6.line", "op": ">",
                 "right": "osc:macd_1d_12_26_6.signal"},
                {"left": "osc:macd_1d_18_39_4.line", "op": ">",
                 "right": "osc:macd_1d_18_39_4.signal"},
            ],
        },
        {
            "name": "cond4H_core — 4H B فوق إشارته وفوق الصفر (مؤكد)",
            "logic": "and",
            "conditions": [
                {"left": "osc:macd_4h_12_26_6.line", "op": ">",
                 "right": "osc:macd_4h_12_26_6.signal"},
                {"left": "osc:macd_4h_12_26_6.line", "op": ">", "right": 0},
            ],
        },
        {
            "name": "condAnyAbove4H — أي ماكد أعلى (1D A/B/C · 1W A/B/C) فوق إشارته وفوق خط 4H B",
            "logic": "or",
            "conditions": [
                _above_leaf("macd_1d_6_13_4"),
                _above_leaf("macd_1d_12_26_6"),
                _above_leaf("macd_1d_18_39_4"),
                _above_leaf("macd_1w_6_13_4"),
                _above_leaf("macd_1w_12_26_4"),
                _above_leaf("macd_1w_18_39_4"),
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# تطبيع المساعدات
# ---------------------------------------------------------------------------
def _norm_tf(raw: Any) -> Dict[str, Any]:
    """فريم النسخة → معلومات الدلو (_parse_resolution + مرادفات Pine المجردة).

    يقبل: "240"/"4h"/"4H" · "1D"/"1d"/"D"/"day" · "1W"/"1w"/"W"/"week" ·
    "3D"/"3d" · "60"/"1h" ... — ويرجع {label, step_ms, kind, n}.
    """
    s = str(raw if raw is not None else "").strip()
    if s in ("D", "d"):
        s = "1D"
    return _parse_resolution(s)


def _to_ms_bound(raw: Any) -> Optional[int]:
    """حد نافذة التفعيل (ISO أو ms) → مللي ثانية، أو None."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        if math.isfinite(v) and v > 0:
            return int(v * 1000.0) if v < 1e11 else int(v)
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("none", "null", "off", "false"):
        return None
    try:
        f = float(s)
        return int(f * 1000.0) if f < 1e11 else int(f)
    except ValueError:
        pass
    try:
        from datetime import datetime, timezone
        s2 = s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        _LOG.warning("B9: active bound غير مفهوم '%s' — يُتجاهل", s)
        return None


def _jsonable(v: Any) -> Optional[float]:
    """قيمة → JSON-آمنة (None بدل NaN/Inf)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _ema_seeded(x: np.ndarray, period: int) -> np.ndarray:
    """EMA بنمط TradingView/ta.ema — واعٍ لبادئة NaN (محلي معزول).

    بذرة SMA عند القيمة الصالحة رقم (period) ثم alpha=2/(period+1) تكرارياً.
    بادئة NaN (إحماء EMA الأبطأ في line = fast−slow) تُتخطى — البذرة من
    أول period قيم صالحة، وأي NaN لاحقة نادرة تحمل آخر قيمة (لا تنشر NaN
    للأبد كما في _ema_talib البسيطة). على سلسلة بلا NaN تطابق _ema_talib
    بت-بت (بذرة عند الفهرس period−1 ثم نفس العودية).
    """
    n = x.size
    out = np.full(n, np.nan, dtype=float)
    if period < 1 or n < 1:
        return out
    nn = np.where(~np.isnan(x))[0]
    if nn.size < period:
        return out
    seed_i = int(nn[period - 1])
    out[seed_i] = float(np.mean(x[nn[:period]]))
    a = 2.0 / (period + 1.0)
    last = out[seed_i]
    for i in range(seed_i + 1, n):
        if np.isnan(x[i]):
            out[i] = last
        else:
            last = a * float(x[i]) + (1.0 - a) * last
            out[i] = last
    return out


# ---------------------------------------------------------------------------
# المحرك — B9 MACD Gates
# ---------------------------------------------------------------------------
def b9_macd_gates(
    candles: Any,
    *,
    instances: Optional[Sequence[Any]] = None,
    conditions: Optional[Dict[str, Any]] = None,
    sub_labels: Optional[Sequence[str]] = None,
    active_start: Any = None,
    active_end: Any = None,
    htf_mode: Any = "confirmed",
    **_extra,
) -> Dict[str, Any]:
    """«ماكد 9B» — بوابات MACD متعددة الفريمات (شراء B9 حرفياً من Pine).

    المعاملات:
      instances    : قائمة نسخ MACD — [{id, timeframe, fast, slow, signal,
                     enabled?, doc?}] بأي عدد (الافتراضي: نسخ B9 السبع
                     المستخدمة في الشروط).
      conditions   : شجرة الشروط {logic: and|or|not, conditions: [...]}
                     بأي عمق — الورقة {left, op, right} حيث المرجع
                     "osc:<id>.line|signal|hist" أو "price:<col>" أو رقم،
                     وop من > >= < <= == != (نفس مقيّم نواة R76).
                     (الافتراضي: buyCond الحرفي للسكربت).
      sub_labels   : تسميات الفروع العلوية للشجرة (سلاسل شفافية
                     b9g_sub_<label>) — الافتراضي التسميات الأربع للشجرة
                     الأصلية. None/[] = بلا سلاسل فرعية.
      active_start : بداية نافذة تفعيل b9g_buy (ISO أو ms) — قبلها
                     b9g_buy=0 (القيم تُحسب دائماً — إحماء ثم حصر
                     الصفقات داخل النافذة المستهدفة).
      active_end   : نهاية نافذة التفعيل (حصرية) — بعدها b9g_buy=0.
      htf_mode     : وضع إسقاط الفريم الأعلى (v4 · LIVE1):
                     · "confirmed" (الافتراضي) — آخر شريط HTF مكتمل فقط
                       (سلوك v2/v3 بلا تغيير — مثل TV التاريخي).
                     · "live" — الشريط النامي مرئي بقيمة محدّثة بإغلاق
                       الشمعة الحالية (مثل TV الحي حرفياً — إشارات داخل
                       الأسبوع في مناطق ما قبل الصعود). سببي بلا استشراف.

    الورقة بقيمة مفقودة (إحماء HTF) ⇒ False — فشل-الإغلاق (البوابة
    مغلقة حتى جاهزية كل النسخ المعنية).
    """
    t_l, o_l, h_l, l_l, c_l = _norm_candles(candles)
    N = len(t_l)
    t = np.asarray(t_l, dtype=np.int64)
    o = np.asarray(o_l, dtype=float)
    h = np.asarray(h_l, dtype=float)
    low = np.asarray(l_l, dtype=float)
    c = np.asarray(c_l, dtype=float)

    # خطوة شمعة القاعدة (أصغر فرق زمني موجب — متين أمام فجوات البيانات)
    if N > 1:
        diffs = np.diff(t)
        pos = diffs[diffs > 0]
        base_step = int(pos.min()) if pos.size else 60_000
    else:
        base_step = 60_000

    inst_list: List[Dict[str, Any]] = []
    for raw in (instances if instances is not None else B9_DEFAULT_INSTANCES):
        if raw is None:
            continue
        if not isinstance(raw, dict):
            raw = dict(raw)
        if raw.get("enabled") is False:
            continue
        try:
            fast = max(1, int(raw.get("fast", 12)))
            slow = max(1, int(raw.get("slow", 26)))
            sig = max(1, int(raw.get("signal", raw.get("sig", 6))))
        except (TypeError, ValueError):
            continue
        iid = str(raw.get("id") or raw.get("name") or
                  f"macd_{fast}_{slow}_{sig}").strip().lower()
        inst_list.append({
            "id": iid, "timeframe": raw.get("timeframe", "240"),
            "fast": fast, "slow": slow, "signal": sig,
            "doc": raw.get("doc"),
        })

    tree = conditions if conditions is not None else B9_DEFAULT_CONDITIONS
    labels: List[str] = []
    if sub_labels is None:
        labels = list(B9_DEFAULT_SUB_LABELS)
    else:
        labels = [str(x) for x in sub_labels if str(x).strip()]

    start_ms = _to_ms_bound(active_start)
    end_ms = _to_ms_bound(active_end)

    # ✅ v4 (LIVE1) — وضع إسقاط HTF: confirmed (افتراضي · v2/v3) | live
    htf_mode_n = str(htf_mode or "confirmed").strip().lower()
    if htf_mode_n not in ("confirmed", "live"):
        _LOG.warning("B9: htf_mode غير مفهوم '%s' — يُرجع confirmed", htf_mode)
        htf_mode_n = "confirmed"
    live_mode = (htf_mode_n == "live")

    series: Dict[str, Any] = {}
    meta_instances: List[Dict[str, Any]] = []
    lookup: Dict[str, np.ndarray] = {
        "price:open": o, "price:high": h,
        "price:low": low, "price:close": c,
    }

    for inst in inst_list:
        iid = inst["id"]
        res = _norm_tf(inst["timeframe"])
        starts, closes, _bo, _bh, _bl, bc = _build_htf_bars(
            t, o, h, low, c, res)
        M = int(starts.size)
        line = sig = hist = np.full(M, np.nan, dtype=float)
        ef = es = np.full(M, np.nan, dtype=float)
        if M:
            ef = _ema_seeded(bc, inst["fast"])
            es = _ema_seeded(bc, inst["slow"])
            line = ef - es
            sig = _ema_seeded(line, inst["signal"])
            hist = line - sig

        # الإسقاط السببي: آخر شريط HTF مكتمل فقط عند كل شمعة قاعدة
        cutoff = t + base_step
        if M:
            j = np.searchsorted(closes, cutoff, side="right") - 1
            valid = j >= 0
            j_safe = np.clip(j, 0, M - 1)
            v_line = np.where(valid, line[j_safe], np.nan)
            v_sig = np.where(valid, sig[j_safe], np.nan)
            v_hist = np.where(valid, hist[j_safe], np.nan)

            if live_mode:
                # ✅ v4 (LIVE1): الشريط النامي مرئي — قيمة الدلو الجاري
                # محدّثة بإغلاق الشمعة الحالية (خطوة EMA واحدة من بذرة
                # آخر دلو مكتمل) — نفس ما يعرضه TradingView على الحافة
                # الحية. سببي 100% (لا مستقبل) لكنه يعيد الرسم كـ TV.
                a_f = 2.0 / (inst["fast"] + 1.0)
                a_s = 2.0 / (inst["slow"] + 1.0)
                a_g = 2.0 / (inst["signal"] + 1.0)
                k_dev = np.searchsorted(starts, t, side="right") - 1
                kd_safe = np.clip(k_dev, 0, M - 1)
                developing = (k_dev >= 0) & (closes[kd_safe] > cutoff)
                prev_ok = developing & (k_dev >= 1)
                kp = np.clip(np.where(prev_ok, k_dev - 1, 0), 0, M - 1)
                seed_f = np.where(prev_ok, ef[kp], np.nan)
                seed_s = np.where(prev_ok, es[kp], np.nan)
                seed_g = np.where(prev_ok, sig[kp], np.nan)
                line_dev = (a_f * c + (1.0 - a_f) * seed_f) \
                    - (a_s * c + (1.0 - a_s) * seed_s)
                sig_dev = a_g * line_dev + (1.0 - a_g) * seed_g
                ok_dev = (developing & ~np.isnan(line_dev)
                          & ~np.isnan(sig_dev))
                v_line = np.where(ok_dev, line_dev, v_line)
                v_sig = np.where(ok_dev, sig_dev, v_sig)
                v_hist = np.where(ok_dev, line_dev - sig_dev, v_hist)
        else:
            v_line = v_sig = v_hist = np.full(N, np.nan, dtype=float)

        arr_line = np.where(np.isnan(v_line), np.nan, v_line)
        lookup[f"osc:{iid}.line"] = arr_line
        lookup[f"osc:{iid}.signal"] = np.where(np.isnan(v_sig), np.nan, v_sig)
        lookup[f"osc:{iid}.hist"] = np.where(np.isnan(v_hist), np.nan, v_hist)
        series[f"b9g_osc_{iid}_line"] = [_jsonable(x) for x in arr_line.tolist()]
        series[f"b9g_osc_{iid}_signal"] = [
            _jsonable(x) for x in lookup[f"osc:{iid}.signal"].tolist()]
        series[f"b9g_osc_{iid}_hist"] = [
            _jsonable(x) for x in lookup[f"osc:{iid}.hist"].tolist()]

        fv = next((int(i) for i, x in enumerate(series[f"b9g_osc_{iid}_line"])
                   if x is not None), None)
        meta_instances.append({
            "id": iid, "timeframe": res["label"], "kind": res["kind"],
            "fast": inst["fast"], "slow": inst["slow"], "signal": inst["signal"],
            "htf_bars": M, "first_valid_index": fv,
            "first_valid_time": (int(t[fv]) if fv is not None and fv < N else None),
            "doc": inst.get("doc"),
        })

    # تقييم الشجرة عند كل شمعة مغلقة (فشل-الإغلاق عند الإحماء — قيمة
    # مفقودة ⇒ الورقة False — مقيّم نواة R76 حرفياً).
    s_buy: List[float] = [0.0] * N
    s_cond: List[float] = [0.0] * N
    top_branches = None
    if (isinstance(tree, dict) and labels
            and str(tree.get("logic", "and")).lower() == "and"
            and isinstance(tree.get("conditions"), list)):
        branches = [b for b in tree["conditions"]
                    if not (isinstance(b, dict) and b.get("enabled") is False)]
        if len(branches) == len(labels):
            top_branches = branches

    buy_count = 0
    cond_count = 0
    for i in range(N):
        ok = evaluate_conditions(tree, lookup, i)
        if ok:
            cond_count += 1
            s_cond[i] = 1.0
            in_window = True
            if start_ms is not None and int(t[i]) < start_ms:
                in_window = False
            if in_window and end_ms is not None and int(t[i]) >= end_ms:
                in_window = False
            if in_window:
                s_buy[i] = 1.0
                buy_count += 1
        # فروع الشفافية
        if top_branches is not None:
            for bi, br in enumerate(top_branches):
                if evaluate_conditions(br, lookup, i):
                    series.setdefault(f"b9g_sub_{labels[bi]}", [0.0] * N)[i] = 1.0

    # ضمان وجود سلاسل الفروع حتى لو لم تتحقق أبداً
    if top_branches is not None:
        for lb in labels:
            series.setdefault(f"b9g_sub_{lb}", [0.0] * N)

    series["b9g_buy"] = s_buy
    series["b9g_cond"] = s_cond

    first_buy = next((int(i) for i, x in enumerate(s_buy) if x), None)
    return {
        "name": "B9 MACD Gates («MACD Buy Strategy 9B» — multi-timeframe MACD gates)",
        "engine": B9_MACD_GATES_ENGINE_NAME,
        "spec": B9_MACD_GATES_SPEC,
        "strategy_ar_name": B9_STRATEGY_AR_NAME,
        "bars": N,
        "time_from": int(t[0]) if N else None,
        "time_to": int(t[-1]) if N else None,
        "series": series,
        "signals": [],
        "meta": {
            "engine": B9_MACD_GATES_ENGINE_NAME,
            "spec": B9_MACD_GATES_SPEC,
            "instances": meta_instances,
            "active_start_ms": start_ms,
            "active_end_ms": end_ms,
            "base_step_ms": base_step,
            "buy_bars": buy_count,
            "cond_bars": cond_count,
            "first_buy_index": first_buy,
            "first_buy_time": (int(t[first_buy]) if first_buy is not None
                               and first_buy < N else None),
            "warmup_policy": "fail-closed — أي قيمة مفقودة (إحماء HTF) ⇒ الورقة False",
            "projection": (
                "live — الشريط النامي مرئي (قيمة الدلو الجاري بإغلاق الشمعة "
                "الحالية — مثل TV الحي · سببي بلا استشراف لكن يعيد الرسم)"
                if live_mode else
                "causal — آخر شريط HTF مكتمل فقط (confirmed · بلا استشراف)"),
            "htf_mode": htf_mode_n,
            "macd_formula": "ta.macd — line=EMA(fast)−EMA(slow) · signal=EMA(line) · بذرة SMA",
            "sub_labels": labels if top_branches is not None else [],
        },
        "notes": "B9 (ماكد 9B) — محرك معزول: بوابات MACD متعددة الفريمات "
                 "(4H/1D/1W بمرساة TradingView — الأسبوع من الاثنين) بشجرة شروط "
                 "قابلة للتركيب (مقارنات قيم عابرة للفريمات مدعومة). الإسقاط "
                 "حسب htf_mode: confirmed (الافتراضي — آخر شريط مكتمل فقط، "
                 "مثل TV التاريخي) أو live (الشريط النامي مرئي — مثل TV "
                 "الحي: إشارات داخل الأسبوع في مناطق ما قبل الصعود؛ سببي بلا "
                 "استشراف). الإحماء فشل-إغلاق. نافذة التفعيل "
                 "active_start/active_end تحصر b9g_buy داخل نافذة التداول "
                 "المستهدفة بينما تُحسب القيم على كامل البيانات الممتدة "
                 "(إحماء MACD الأسبوعي كما يراه TradingView بالتاريخ الكامل). "
                 "العمود الأساسي: ind_b9g_buy · الشفافية ind_b9g_cond و "
                 "ind_b9g_sub_* · قيم النسخ ind_b9g_osc_<id>_line|signal|hist.",
    }


# ---------------------------------------------------------------------------
# التسجيل الذاتي كمؤشر منفصل — b9_macd_gates
# يُستورد مرة واحدة من app/services/indicators/__init__.py
# ---------------------------------------------------------------------------
def _register_b9_macd_gates_indicator() -> None:
    try:
        from .base import BaseIndicator, IndicatorResult, IndicatorType
        from .registry import IndicatorRegistry
        import pandas as pd

        class B9MacdGatesIndicator(BaseIndicator):
            """«ماكد 9B» — بوابات MACD متعددة الفريمات (شراء B9)."""

            @classmethod
            def get_required_columns(cls):
                return ["open", "high", "low", "close"]

            @classmethod
            def get_default_params(cls):
                return {
                    "instances": B9_DEFAULT_INSTANCES,
                    "conditions": B9_DEFAULT_CONDITIONS,
                    "sub_labels": B9_DEFAULT_SUB_LABELS,
                    "active_start": None,
                    "active_end": None,
                }

            def calculate(self, data: pd.DataFrame) -> IndicatorResult:
                from .overlay_columns import config_to_overlay_params
                conv = config_to_overlay_params({
                    "name": "b9_macd_gates",
                    "params": dict(self.params or {}),
                }) or {"b9_macd_gates": {}}
                params = conv.get("b9_macd_gates") or {}
                res = b9_macd_gates(data, **params)
                values = res["series"].get("b9g_buy") or [0.0] * len(data)
                series = pd.Series(values, index=data.index, dtype=object)
                return IndicatorResult(
                    name=self.name,
                    values=series,
                    signals=None,
                    metadata={
                        "engine": B9_MACD_GATES_ENGINE_NAME,
                        "overlay": "b9_macd_gates",
                        "primary_column": "ind_b9g_buy",
                        "available_columns": sorted(res["series"].keys()),
                    },
                )

        IndicatorRegistry.register(
            "b9_macd_gates",
            display_name="B9 MACD Gates — ماكد 9B (بوابات MACD متعددة الفريمات)",
            description="«MACD Buy Strategy 9B» محوّلاً حرفياً: MACD(12/26/6) "
                        "على 4H فوق إشارته وفوق الصفر + MACD اليومي B(12/26/6) "
                        "وC(18/39/4) فوق إشارتيهما + MACD الأسبوعي A(6/13/4) "
                        "وB(12/26/4) وC(18/39/4) فوق إشاراتها + أي ماكد أعلى "
                        "(1D A/B/C · 1W A/B/C) فوق إشارته وفوق خط 4H. الإسقاط "
                        "سببي (آخر شريط HTF مكتمل — confirmed) والإحماء "
                        "فشل-إغلاق ونافذة تفعيل active_start/active_end تحصر "
                        "الإشارات داخل نافذة التداول. العمود الأساسي: "
                        "ind_b9g_buy · الشفافية ind_b9g_cond/ind_b9g_sub_* · "
                        "قيم النسخ ind_b9g_osc_<id>_line|signal|hist.",
            category=IndicatorType.MOMENTUM,
        )(B9MacdGatesIndicator)

        # مرادفات قصيرة — نفس الفئة (نمط العائلة)
        info = IndicatorRegistry._indicators.get("b9_macd_gates")
        if info is not None:
            IndicatorRegistry._indicators.setdefault("b9", info)
            IndicatorRegistry._indicators.setdefault("b9_macd", info)
    except Exception:  # pragma: no cover — التسجيل لا يعطل المحرك أبداً
        logging.getLogger(__name__).exception(
            "B9 MACD Gates indicator registration failed")


_register_b9_macd_gates_indicator()
