# =============================================================================
# ✅ ZONE-EXIT-TF1 — فريم هيكل الخروج (CHoCH على أي فريم نريده)
# =============================================================================
# مواصفة صاحب القرار: «اتاحة تعديل هيكل الخروج ليتم حسابه على أي فريم نريده —
# هذا بخصوص الـ CHoCH. هو يحسب الدخول والمنطقة المسموحة على نفس الفريم الذي
# يعمل عليه حالياً بدون كسر؛ فقط نريد حساب الخروج ليُحتسب على الفريم الذي
# نريده».
#
# الخروج المقصود = حدث إغلاق المنطقة الكمومية zone_exit (LL+LH — انعكاس
# بنية السوق «Change of Character») — الباب الوحيد للخروج في استراتيجية
# الجبّارة ALMIGHTY. حالياً يُحسب على فريم الشارت نفسه (15m) مع الدخول
# والمنطقة المسموحة. هذه الوحدة تجعله قابلاً للحساب على أي فريم أعلى
# (60/240/1D/1W/1M...) مع بقاء الدخول والمنطقة المسموحة حيث هما بلا أي كسر.
#
# البنية (نفس أنماط MTFEMA1 المثبتة — بلا أي استشراف):
#   1) تُبنى شموع HTF من شموع القاعدة (_build_htf_bars — نفس النواة التي
#      تحسب رصة EMA على فريم الساعة).
#   2) يُحسب محرك الزقزاق الترندي zigzag_fib_e2e_trendy على شموع HTF بنفس
#      معاملات الزقزاق (length/mode/depth/...) → محاور مؤكدة (pivots) على
#      مستوى HTF.
#   3) تُشغَّل آلة المنطقة الكمومية نفسها حرفياً (مقارنة المحاور: قمة/قمة
#      سابقة وقاع/قاع سابقة → HH/HL/LH/LL → HH+HL يفتح · LL+LH يغلق) على
#      محاور HTF → أحداث enter/exit على مستوى HTF.
#   4) الإسقاط السببي على شموع القاعدة: حدث HTF يُعلَم فقط عند إغلاق شمعة
#      HTF التي أكدته (closes[j]) — أول شمعة قاعدة إغلاقها ≥ ذلك الحدث
#      تحمل العلم (مرة واحدة — حدث وليس حالة). حالة المنطقة HTF تُسقط
#      استمرائياً للشفافية والرسم.
#
# العقد (أعمدة جديدة — لا تداخل مع أي عقد قائم):
#   zzfetqe_zone_exit         : حدث الخروج (LL+LH) محسوباً على فريم HTF
#                                المطلوب ومسقوطاً سببياً — هذا هو الباب الذي
#                                تقرأه قاعدة الخروج (يحل محل النسخة الأساس).
#   zzfetqe_zone_exit_base    : النسخة الأصلية على فريم الشارت (شفافية/A-B).
#   zzfetqe_zone_exit_htf_enter: أحداث فتح منطقة HTF مسقطة (شفافية/رسم).
#   zzfetqe_zone_exit_htf_on  : حالة منطقة HTF مسقطة استمرائياً (رسم).
#   (نفس الأسماء ببادئة zzfetq_ لمحرك الكمومية غير الأسية.)
#
# التعطيل الآمن: zone_exit_resolution فارغة/«none»/«base»/«chart» = السلوك
# التاريخي بت-بت (لا أي تغيير في أي عمود). فريم أعلى يُبنى من شموع الشارت
# (نفس نمط رصة EMA). ✅ ZONE-EXIT-LTF1: فريم أدق من الشارت («5m» والشارت
# 15m) يستخدم شموع الفريم الأدق الحقيقية من السياق الذي يُسجّله محرك
# الباك-تست من طبقة البيانات (set_zone_exit_ltf_context) — غياب السياق
# ⇒ التقييد الدفاعي إلى فريم الشارت مع تحذير (نفس نمط MTFEMA1).
# =============================================================================

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# نواة MTF (بناء شموع HTF + تحليل الفريم — نفس نواة رصة EMA المثبتة)
from app.services.indicators.overlays_mtf_ema import (
    _build_htf_bars,
    _norm_candles_arrays,
    _parse_resolution,
)
# المحرك الترندي (مصدر المحاور المؤكدة — نفس المحرك الذي تستخدمه الكمومية)
from app.services.indicators.overlays_zlf_e2e_trendy import zigzag_fib_e2e_trendy
from app.services.indicators.zigzag_fib_core import clean_float

logger = logging.getLogger(__name__)

__all__ = [
    "norm_zone_exit_resolution",
    "compute_zone_exit_mtf",
    "ZONE_EXIT_TF_SPEC",
    "set_zone_exit_ltf_context",
    "clear_zone_exit_ltf_context",
]

ZONE_EXIT_TF_SPEC = "ZONE-EXIT-TF1-choch-exit-timeframe"

# ✅ ZONE-EXIT-LTF1 — سياق بيانات الفريم الأدق الحقيقية (طلب صاحب القرار:
# «نجرب نفعل الخروج ع فريم 5 دقائق» — الشارت 15m). فريم أدق لا يمكن
# اشتقاقه من شموع الشارت؛ يجلبه محرك الباك-تست من طبقة البيانات ويسجّله
# هنا قبل حساب المؤشرات ثم يمسحه بعده (try/finally). غياب السياق ⇒
# التقييد الدفاعي التاريخي (فريم الشارت) بت-بت — لا كسر أبداً في أي مسار.
_LTF_EXIT_CONTEXT: Dict[str, Any] = {}


def set_zone_exit_ltf_context(candles: Any, resolution: str) -> None:
    """تسجيل شموع فريم أدق حقيقية لهيكل الخروج (يستدعيه محرك الباك-تست).

    resolution = التسمية القانونية من _parse_resolution (مثال: «5m»).
    """
    _LTF_EXIT_CONTEXT[str(resolution)] = candles


def clear_zone_exit_ltf_context() -> None:
    """إفراغ السياق — يستدعيه محرك الباك-تست في finally دائماً."""
    _LTF_EXIT_CONTEXT.clear()


def _ltf_context_for(label: str) -> Optional[Any]:
    return _LTF_EXIT_CONTEXT.get(str(label))

# القيم المفسَّرة كـ «معطَّل» (السلوك التاريخي بت-بت على فريم الشارت)
_DISABLED_TOKENS = {"", "none", "off", "false", "0", "no", "base", "chart", "current", "same"}


def norm_zone_exit_resolution(raw: Any) -> Optional[str]:
    """تطبيع فريم هيكل الخروج — يرجع None عند التعطيل (السلوك التاريخي).

    يقبل كل صيغ فريمات Pine/الواجهة («60»/«1h»/«240»/«4h»/«1D»/«1W»/«1M»...)
    عبر _parse_resolution نفسها التي تستخدمها رصة EMA. القيم الفارغة
    والمرادفات الصريحة للتعطيل («none»/«off»/«base»/«chart»...) ترجع None.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        # قيمة منطقية ليست فريماً — التعطيل الآمن (السلوك التاريخي)
        return None
    s = str(raw).strip()
    if s.lower() in _DISABLED_TOKENS:
        return None
    return s


def _zone_machine_on_pivots(
    pivots: List[Dict[str, Any]],
    n_bars: int,
) -> Tuple[List[float], List[float], List[float], List[Dict[str, Any]]]:
    """آلة المنطقة الكمومية على محاور مؤكدة — نسخة حرفية من منطق الكمومية.

    (z_enter, z_exit, zone_on, events) بأطوال n_bars — نفس الترتيب الحرفي:
    كل محور يُعالج عند شمعة تأكيده confirmed_at_bar، والمقارنة بسابقه من
    نفس النوع، والبنية المجمعة HH+HL تفتح / LL+LH يغلق (عند شمعة المحور
    المكمِّل للزوج).
    """
    z_enter = [0.0] * n_bars
    z_exit = [0.0] * n_bars
    zone_on_series = [0.0] * n_bars
    events: List[Dict[str, Any]] = []

    last_high: Optional[float] = None
    last_low: Optional[float] = None
    prev_high: Optional[float] = None
    prev_low: Optional[float] = None
    high_state: Optional[float] = None
    low_state: Optional[float] = None
    zone_on = False

    pi = 0
    for j in range(n_bars):
        while pi < len(pivots) and int(pivots[pi]["confirmed_at_bar"]) <= j:
            p = pivots[pi]
            pi += 1
            price = clean_float(p.get("price"))
            kind = str(p.get("kind") or "")
            if price is None:
                continue
            if kind in ("top", "high"):
                prev_high = last_high
                last_high = price
                if prev_high is not None:
                    high_state = 1.0 if price > prev_high else -1.0
            else:
                prev_low = last_low
                last_low = price
                if prev_low is not None:
                    low_state = 1.0 if price > prev_low else -1.0
            # البنية المجمعة + آلة المنطقة (عند شمعة المحور نفسها — حرفي)
            both_up = high_state == 1.0 and low_state == 1.0
            both_down = high_state == -1.0 and low_state == -1.0
            if both_up and not zone_on:
                zone_on = True
                z_enter[j] = 1.0
                events.append({
                    "kind": "enter", "htf_bar": int(j),
                    "last_high": clean_float(last_high),
                    "prev_high": clean_float(prev_high),
                    "last_low": clean_float(last_low),
                    "prev_low": clean_float(prev_low),
                })
            elif both_down and zone_on:
                zone_on = False
                z_exit[j] = 1.0
                events.append({
                    "kind": "exit", "htf_bar": int(j),
                    "last_high": clean_float(last_high),
                    "prev_high": clean_float(prev_high),
                    "last_low": clean_float(last_low),
                    "prev_low": clean_float(prev_low),
                })
        zone_on_series[j] = 1.0 if zone_on else 0.0

    return z_enter, z_exit, zone_on_series, events


def compute_zone_exit_mtf(
    candles: Any,
    resolution: Any,
    length: int,
    reverse: bool = False,
    levels: Optional[Any] = None,
    extend_right: bool = True,
    extend_leg_to_live: bool = True,
    mode: str = "luxalgo",
    depth: int = 12,
    deviation: float = 20.0,
    backstep: int = 3,
    launch_touch_ticks: float = 1.0,
) -> Optional[Dict[str, Any]]:
    """هيكل الخروج (CHoCH: LL+LH) محسوباً على فريم مستقل ومسقوطاً سببياً.

    يرجع قاموساً بأطوال شموع القاعدة:
      zone_exit  : أعلام حدث الخروج HTF على شموع القاعدة (الباب الجديد)
      zone_enter : أعلام حدث فتح منطقة HTF (شفافية)
      zone_on    : حالة منطقة HTF مسقطة استمرائياً (رسم)
      events     : أحداث HTF مع مواقعها (htf_bar/base_bar/الأزمنة)
      meta       : {resolution, length, htf_bars, htf_step_ms, base_step_ms,
                    clamped, counts...}

    يرجع None عند: التعطيل (resolution معطلة) أو بلا شموع أو فشل دفاعي
    (السلوك التاريخي يسود — لا كسر أبداً).
    """
    res_raw = norm_zone_exit_resolution(resolution)
    if res_raw is None:
        return None

    try:
        t, o, h, l, c = _norm_candles_arrays(candles)
    except Exception:
        logger.exception("ZONE-EXIT-TF: فشل تطبيع الشموع — تعطيل هيكل الخروج المTF")
        return None
    N = int(t.size)
    if N == 0:
        return None

    # خطوة شمعة القاعدة (نفس عقد MTFEMA1 — متين أمام فجوات البيانات)
    if N > 1:
        diffs = np.diff(t)
        pos = diffs[diffs > 0]
        base_step = int(pos.min()) if pos.size else 60_000
    else:
        base_step = 60_000

    res_info = _parse_resolution(res_raw)

    # HTF لا يمكن أن يكون أدنى من فريم الشارت — تقييد دفاعي (متسق رياضياً:
    # يصبح الحساب على فريم الشارت نفسه) مع تحذير في meta — نفس نمط MTFEMA1.
    # ✅ ZONE-EXIT-LTF1 — استثناء الفريم الأدق: عند طلب فريم أدق من فريم
    # الشارت («5m» والشارت 15m) تُستخدم شموع الفريم الأدق الحقيقية من
    # السياق (جلبها محرك الباك-تست من طبقة البيانات). غياب السياق ⇒
    # التقييد التاريخي بت-بت (لا أي سلوك جديد في أي مسار آخر).
    htf_step = res_info.get("step_ms")
    clamped = False
    ltf_ctx: Optional[Any] = None
    if res_info["kind"] == "fixed" and htf_step is not None and htf_step < base_step:
        ltf_ctx = _ltf_context_for(res_info["label"])
        if ltf_ctx is None:
            logger.warning(
                "ZONE-EXIT-TF: resolution '%s' (%d ms) أدنى من فريم الشارت (%d ms) "
                "ولا سياق بيانات أدق مسجل (ZONE-EXIT-LTF1) — استُخدم فريم الشارت نفسه",
                res_info["label"], htf_step, base_step)
            htf_step = base_step
            res_info = dict(res_info, step_ms=base_step)
            clamped = True

    # 1) شموع الفريم المستقل:
    #    أ) HTF (أعلى من الشارت) تُبنى من شموع القاعدة (نفس نواة رصة EMA —
    #       بلا تلفيق) — كما كان بت-بت.
    #    ب) ✅ ZONE-EXIT-LTF1: فريم أدق من الشارت — شموع الفريم الأدق
    #       الحقيقية من السياق مباشرة (زقزاق أدق بأمانة كاملة — لا تلفيق).
    if ltf_ctx is not None:
        try:
            lt, lo, lh, llo, lc = _norm_candles_arrays(ltf_ctx)
        except Exception:
            logger.exception("ZONE-EXIT-LTF: فشل تطبيع شموع الفريم الأدق — "
                             "تعطيل هيكل الخروج (السلوك التاريخي)")
            return None
        M = int(lt.size)
        if M == 0:
            return None
        if M > 1:
            ld = np.diff(lt)
            lp = ld[ld > 0]
            ltf_step_real = int(lp.min()) if lp.size else int(htf_step)
        else:
            ltf_step_real = int(htf_step)
        starts = lt
        # وقت إغلاق كل شمعة أدق = بدايتها + خطوتها الاسمية (معلوم عند الإغلاق)
        closes = lt + ltf_step_real
        b_o, b_h, b_l, b_c = lo, lh, llo, lc
    else:
        try:
            starts, closes, b_o, b_h, b_l, b_c = _build_htf_bars(t, o, h, l, c, res_info)
        except Exception:
            logger.exception("ZONE-EXIT-TF: فشل بناء شموع HTF — تعطيل هيكل الخروج")
            return None
        M = int(starts.size)
        if M == 0:
            return None

    # 2) محرك الزقزاق الترندي على شموع HTF — بنفس معاملات الزقزاق
    #    (المحاور فقط هي المطلوبة — البوابات لا تمس المحاور).
    htf_candles = [
        {
            "time": int(starts[j]),
            "open": float(b_o[j]),
            "high": float(b_h[j]),
            "low": float(b_l[j]),
            "close": float(b_c[j]),
        }
        for j in range(M)
    ]
    try:
        trendy = zigzag_fib_e2e_trendy(
            htf_candles,
            length=length,
            reverse=reverse,
            levels=levels,
            extend_right=extend_right,
            extend_leg_to_live=extend_leg_to_live,
            mode=mode,
            depth=depth,
            deviation=deviation,
            backstep=backstep,
            launch_touch_ticks=launch_touch_ticks,
        )
    except Exception:
        logger.exception("ZONE-EXIT-TF: فشل محرك الزقزاق على HTF — تعطيل هيكل الخروج")
        return None
    pivots = trendy.get("pivots") or []

    # 3) آلة المنطقة على محاور HTF (نسخة حرفية من منطق الكمومية)
    z_enter_htf, z_exit_htf, zone_on_htf, events = _zone_machine_on_pivots(pivots, M)

    # 4) الإسقاط السببي على شموع القاعدة:
    #    حدث HTF عند الشمعة j يُعلَم عند إغلاقها closes[j]؛ أول شمعة قاعدة
    #    إغلاقها ≥ closes[j] (t[i] + base_step ≥ closes[j]) تحمل العلم مرة
    #    واحدة. الشريط النامي لا يُرى إطلاقاً (نفس عقد MTFEMA1).
    z_exit_base = [0.0] * N
    z_enter_base = [0.0] * N
    mapped_events: List[Dict[str, Any]] = []
    for j in range(M):
        if z_exit_htf[j] or z_enter_htf[j]:
            # أول i بحيث t[i] >= closes[j] - base_step
            i0 = int(np.searchsorted(t, closes[j] - base_step, side="left"))
            if i0 >= N:
                # الشمعة HTF لم تُغلق بعد ضمن نافذة البيانات (الشريط النامي
                # الأخير) — الحدث لم يقع بعد: لا يُرى. (سببية كاملة.)
                continue
            kind = "exit" if z_exit_htf[j] else "enter"
            if kind == "exit":
                z_exit_base[i0] = 1.0
            else:
                z_enter_base[i0] = 1.0
            mapped_events.append({
                "kind": kind,
                "htf_bar": int(j),
                "htf_close_time": int(closes[j]),
                "base_bar": int(i0),
                "base_time": int(t[i0]),
            })

    # حالة منطقة HTF مسقطة استمرائياً: لكل شمعة قاعدة آخر شمعة HTF مغلقة
    # عند لحظة ≤ إغلاقها (نفس محاذاة رصة EMA بت-بت).
    cutoff = t + base_step
    jlast = np.searchsorted(closes, cutoff, side="right") - 1
    zone_on_base = [0.0] * N
    for i in range(N):
        jj = int(jlast[i])
        if jj >= 0:
            zone_on_base[i] = zone_on_htf[jj]

    n_exit_htf = int(sum(z_exit_htf))
    n_enter_htf = int(sum(z_enter_htf))
    meta: Dict[str, Any] = {
        "resolution": res_info["label"],
        "htf_kind": res_info["kind"],
        "length": int(length),
        "htf_bars": M,
        "htf_step_ms": int(htf_step) if htf_step is not None else None,
        "base_step_ms": int(base_step),
        "resolution_clamped_to_chart_tf": clamped,
        # ✅ ZONE-EXIT-LTF1 — توثيق وضع الفريم الأدق الحقيقي
        "ltf_real_context": bool(ltf_ctx is not None),
        "counts": {
            "htf_zone_enters": n_enter_htf,
            "htf_zone_exits": n_exit_htf,
            "mapped_enters": int(sum(z_enter_base)),
            "mapped_exits": int(sum(z_exit_base)),
        },
    }
    if ltf_ctx is not None:
        meta["rule"] = (
            "هيكل الخروج محسوب على شموع الفريم الأدق الحقيقية "
            f"({res_info['label']} · {M:,} شمعة أدق من طبقة البيانات) "
            "— زقزاق length={int(length)} على شموع أدق ومسقط سببياً: "
            "الحدث يُعلَم عند إغلاق شمعة الفريم الأدق التي أكدته. "
            "الدخول والمنطقة المسموحة على فريم الشارت بلا أي تغيير."
        )
    return {
        "spec": ZONE_EXIT_TF_SPEC,
        "zone_exit": z_exit_base,
        "zone_enter": z_enter_base,
        "zone_on": zone_on_base,
        "events": mapped_events,
        "meta": meta,
    }
