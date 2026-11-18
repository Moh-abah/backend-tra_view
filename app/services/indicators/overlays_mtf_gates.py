# =============================================================================
# ✅ MTF-GATES1 — بوابة الدخول متعددة الفريمات (MACD 4h + RSI متعدد الفريمات)
# =============================================================================
# مواصفة صاحب القرار (حرفياً): «نفس الاستراتيجية ولكن مع اضافة الماكد لفريم
# 4 ساعات يكون فوق الصفر (12/26/4) + يكون ايجابيا (خط السريع يكون متجاوز
# الخط البطيء لأعلى). والشرط الثاني: rsi فريم ساعه و 4 ساعات فوق الفريم
# اليومي وتكون اعداداتهم 14/14/2».
#
# البوابة (شرطان يُجمعان AND على كل شمعة شارت):
#   1) MACD على فريم مستقل (افتراضياً 4 ساعات — 12/26/4):
#        line > 0  (الماكد فوق الصفر)
#        line > signal  (الخط السريع متجاوز الخط البطيء/الإشارة لأعلى)
#   2) RSI (period/ma_length/bb_std = 14/14/2) على عدة فريمات مستقلة
#      (افتراضياً 1h و 4h) كلها فوق RSI الفريم المرجعي (افتراضياً اليومي 1D).
#
# الهندسة (نفس الأنماط المثبتة في الإنتاج — بلا أي ابتكار مجهول):
#   • شموع الفريم الأعلى تُبنى من شموع الشارت بنواة _build_htf_bars نفسها
#     التي تحسب رصة EMA الستة على فريم الساعة في استراتيجية البطل (MTFEMA1).
#   • الإسقاط السببي: قيمة كل مؤشر عند شمعة الشارت i = قيمة آخر شمعة فريم
#     أعلى مغلقة عند لحظة ≤ إغلاقها (cutoff = t[i] + base_step — عقد MTFEMA1
#     بت-بت). الشريط النامي لا يُرى إطلاقاً — صفر استشراف.
#   • MACD: line = EMA(fast) − EMA(slow) على إغلاقات الفريم الأعلى،
#     signal = EMA(signal) للخط، hist = line − signal (توصيلات TradingView
#     القياسية — EMA بذرّ SMA لأول n قيمة).
#   • RSI: Wilder القياسي (period) + EMA(ma_length) للخط + بولنجر
#     bb_std حوله (شفافية الرسم فقط — البوابة تستخدم قيمة RSI نفسها).
#   • حياد الإحماء (عقد R74 المستعاد): قبل جاهزية كل القيم المطلوبة تبقى
#     البوابة مفتوحة (gate=1) — نفس عقد نواة الموشحات في النظام. قابل
#     للإطفاء بـ warmup_neutral=false (حجب حتى الجاهزية).
#
# العقد (أعمدة ind_* تُحقن تلقائياً في مسار الاستراتيجية):
#   ind_mtg_gate                  : البوابة (0/1) — هذا ما تقرأه قاعدة الدخول
#   ind_mtg_macd_ok / rsi_ok      : البوابتان الفرعيتان (شفافية)
#   ind_mtg_macd_line/signal/hist : MACD الفريم الأعلى مسقطاً سببياً (رسم)
#   ind_mtg_rsi_{tf}_value/ma/bb_upper/bb_lower : RSI لكل فريم (رسم)
#
# التعطيل الآمن: macd_timeframe="none" يسقط شرط الماكد ·
# rsi_reference_timeframe="none" يسقط شرط RSI · كلاهما معطل ⇒ هوية (gate=1)
# مع تحذير. أي فشل دفاعي ⇒ بوابة مفتوحة (لا تُحجب الصفقات أبداً بسبب خلل
# في هذه الوحدة) مع تحذير واضح في meta.
# =============================================================================

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.services.indicators.overlays_mtf_ema import (
    _build_htf_bars,
    _norm_candles_arrays,
    _parse_resolution,
)

logger = logging.getLogger(__name__)

__all__ = ["mtf_gates_engine", "MTF_GATES_SPEC", "MTF_GATES_ENGINE_NAME"]

MTF_GATES_SPEC = "MTF-GATES1-macd-rsi-multi-timeframe-gate"
MTF_GATES_ENGINE_NAME = "ZLF-MTF-Gates (MACD+RSI multi-timeframe entry gate)"

_DISABLED_TOKENS = {"", "none", "off", "false", "0", "no", "disabled"}

_SOURCES = ("open", "high", "low", "close", "hl2", "hlc3", "ohlc4")


def _norm_enabled(raw: Any) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() not in _DISABLED_TOKENS


def _safe_label(label: Any) -> str:
    s = re.sub(r"[^0-9a-zA-Z_]", "", str(label or ""))
    return s or "tf"


def _ema_seeded(values: List[float], n: int) -> List[Optional[float]]:
    """EMA قياسي بذرّ SMA لأول n قيمة — أول قيمة عند الفهرس n-1 (عقد Pine)."""
    out: List[Optional[float]] = [None] * len(values)
    if n < 1 or len(values) < n:
        return out
    sma = math.fsum(values[:n]) / n
    out[n - 1] = sma
    alpha = 2.0 / (n + 1.0)
    prev = sma
    for i in range(n, len(values)):
        prev = values[i] * alpha + prev * (1.0 - alpha)
        out[i] = prev
    return out


def _rsi_wilder(closes: List[float], period: int) -> List[Optional[float]]:
    """RSI بتنعيم Wilder — أول قيمة عند الفهرس period (العقد القياسي)."""
    out: List[Optional[float]] = [None] * len(closes)
    n = len(closes)
    if period < 1 or n <= period:
        return out
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        ch = closes[i] - closes[i - 1]
        if ch > 0:
            gains[i] = ch
        elif ch < 0:
            losses[i] = -ch
    avg_g = math.fsum(gains[1:period + 1]) / period
    avg_l = math.fsum(losses[1:period + 1]) / period

    def _val(g: float, l: float) -> float:
        if l <= 0.0:
            return 100.0 if g > 0.0 else 50.0
        rs = g / l
        return 100.0 - 100.0 / (1.0 + rs)

    out[period] = _val(avg_g, avg_l)
    for i in range(period + 1, n):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
        out[i] = _val(avg_g, avg_l)
    return out


def _rolling_std(values: List[Optional[float]], n: int) -> List[Optional[float]]:
    """انحراف معياري متدرج على آخر n قيمة غير معدومة (بولنجر الشفافية)."""
    out: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i + 1 < n:
            continue
        window = [v for v in values[i + 1 - n:i + 1] if v is not None]
        if len(window) < n:
            continue
        m = math.fsum(window) / n
        var = math.fsum((x - m) ** 2 for x in window) / n
        out[i] = math.sqrt(var)
    return out


def _build_htf_source(
    t: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray,
    res_info: Dict[str, Any], source: str,
) -> Optional[Tuple[np.ndarray, np.ndarray, int]]:
    """يبني شموع الفريم الأعلى ويرجع (close_times, source_values, n_bars)."""
    try:
        starts, closes, b_o, b_h, b_l, b_c = _build_htf_bars(t, o, h, l, c, res_info)
    except Exception:
        logger.exception("MTF-GATES: فشل بناء شموع الفريم الأعلى %s", res_info.get("label"))
        return None
    M = int(starts.size)
    if M == 0:
        return None
    if source == "open":
        vals = b_o
    elif source == "high":
        vals = b_h
    elif source == "low":
        vals = b_l
    elif source == "hl2":
        vals = (b_h + b_l) / 2.0
    elif source == "hlc3":
        vals = (b_h + b_l + b_c) / 3.0
    elif source == "ohlc4":
        vals = (b_o + b_h + b_l + b_c) / 4.0
    else:
        vals = b_c
    return closes.astype(np.int64), [float(x) for x in vals], M


def _project_series(
    t: np.ndarray, base_step: int, htf_closes: np.ndarray,
    htf_series: List[Optional[float]],
) -> List[Optional[float]]:
    """إسقاط سببي: قيمة الشمعة i = قيمة آخر شمعة فريم أعلى مغلقة ≤ إغلاقها."""
    N = int(t.size)
    cutoff = t + base_step
    jlast = np.searchsorted(htf_closes, cutoff, side="right") - 1
    out: List[Optional[float]] = [None] * N
    for i in range(N):
        j = int(jlast[i])
        if j >= 0:
            out[i] = htf_series[j]
    return out


def mtf_gates_engine(
    candles: Any,
    macd_timeframe: Any = "240",
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 4,
    rsi_timeframes: Any = ("60", "240"),
    rsi_reference_timeframe: Any = "1D",
    rsi_period: int = 14,
    rsi_ma_length: int = 14,
    rsi_bb_std: float = 2.0,
    source: str = "close",
    warmup_neutral: bool = True,
) -> Dict[str, Any]:
    """بوابة الدخول متعددة الفريمات — راجع ترويسة الوحدة للعقد الكامل."""
    # ------------------------------------------------------------------ تطبيع
    try:
        t, o, h, l, c = _norm_candles_arrays(candles)
    except Exception:
        logger.exception("MTF-GATES: فشل تطبيع الشموع — بوابة مفتوحة (هوية)")
        return _identity_result("فشل تطبيع الشموع")
    N = int(t.size)
    if N == 0:
        return _identity_result("لا شموع")

    if N > 1:
        diffs = np.diff(t)
        pos = diffs[diffs > 0]
        base_step = int(pos.min()) if pos.size else 60_000
    else:
        base_step = 60_000

    src = str(source or "close").strip().lower()
    if src not in _SOURCES:
        src = "close"

    try:
        macd_fast = max(1, int(macd_fast))
        macd_slow = max(1, int(macd_slow))
        macd_signal = max(1, int(macd_signal))
        rsi_period = max(1, int(rsi_period))
        rsi_ma_length = max(1, int(rsi_ma_length))
        rsi_bb_std = abs(float(rsi_bb_std))
    except (TypeError, ValueError):
        logger.warning("MTF-GATES: معاملات غير رقمية — استُخدمت الافتراضيات 12/26/4 و14/14/2")
        macd_fast, macd_slow, macd_signal = 12, 26, 4
        rsi_period, rsi_ma_length, rsi_bb_std = 14, 14, 2.0
    warmup_neutral = bool(warmup_neutral)

    # ------------------------------------------------- تفكيك فريمات RSI
    rsi_tfs_raw: List[str] = []
    if isinstance(rsi_timeframes, (list, tuple, set)):
        rsi_tfs_raw = [str(x) for x in rsi_timeframes if _norm_enabled(x)]
    elif isinstance(rsi_timeframes, str):
        rsi_tfs_raw = [s.strip() for s in re.split(r"[,;|]+", rsi_timeframes) if _norm_enabled(s.strip())]
    rsi_ref_raw = str(rsi_reference_timeframe).strip() if _norm_enabled(rsi_reference_timeframe) else None

    # إزالة التكرار بالخطوة الزمنية (60 و1h و60m فريم واحد)
    def _dedup_by_step(labels: List[str]) -> List[Tuple[str, Dict[str, Any]]]:
        seen: Dict[int, Dict[str, Any]] = {}
        for raw in labels:
            try:
                info = _parse_resolution(raw)
            except Exception:
                continue
            if info.get("kind") != "fixed" or not info.get("step_ms"):
                continue
            step = int(info["step_ms"])
            if step not in seen:
                seen[step] = info
        return [(str(info["label"]), info) for step, info in sorted(seen.items())]

    rsi_instances = _dedup_by_step(rsi_tfs_raw)
    rsi_ref_info: Optional[Dict[str, Any]] = None
    if rsi_ref_raw:
        try:
            info = _parse_resolution(rsi_ref_raw)
            if info.get("kind") == "fixed" and info.get("step_ms"):
                rsi_ref_info = info
        except Exception:
            rsi_ref_info = None

    macd_enabled = _norm_enabled(macd_timeframe)
    macd_info: Optional[Dict[str, Any]] = None
    if macd_enabled:
        try:
            info = _parse_resolution(str(macd_timeframe))
            if info.get("kind") == "fixed" and info.get("step_ms"):
                macd_info = info
        except Exception:
            macd_info = None
        if macd_info is None:
            logger.warning("MTF-GATES: macd_timeframe '%s' غير مفهوم — سقط شرط الماكد", macd_timeframe)

    rsi_active = bool(rsi_instances) and rsi_ref_info is not None
    series: Dict[str, List[Optional[float]]] = {}
    warnings: List[str] = []

    # حماية: لا يقارَن فريم مع نفسه (المرجع ضمن النسخ ⇒ يُستبعد مع تحذير)
    if rsi_ref_info is not None:
        ref_step = int(rsi_ref_info["step_ms"])
        _kept = [(lb, inf) for lb, inf in rsi_instances if int(inf["step_ms"]) != ref_step]
        if len(_kept) != len(rsi_instances):
            warnings.append(
                "فريم RSI مطابق للمرجع استُبعد من المقارنة (مقارنة الذات بالذات مستحيلة)")
            rsi_instances = _kept
            rsi_active = bool(rsi_instances) and rsi_ref_info is not None
    if rsi_tfs_raw and not rsi_instances:
        logger.warning("MTF-GATES: rsi_timeframes غير مفهومة — سقط شرط RSI")
    if _norm_enabled(rsi_reference_timeframe) and rsi_ref_info is None:
        logger.warning("MTF-GATES: rsi_reference_timeframe '%s' غير مفهوم — سقط شرط RSI", rsi_reference_timeframe)
    # حالة جزء RSI (نفس دلالات الماكد)
    rsi_state = "enabled" if rsi_active else "disabled"

    # ------------------------------------------------------------- MACD
    macd_line_p: List[Optional[float]] = [None] * N
    macd_signal_p: List[Optional[float]] = [None] * N
    macd_hist_p: List[Optional[float]] = [None] * N
    macd_meta: Dict[str, Any] = {"enabled": False}
    # حالة الجزء: enabled (شغّال — يُقيّم قيمه) · disabled (معطّل بالتكوين —
    # يتخطى) · failed (فشل بناء — يُغلق بصوت عالٍ: 0 صفقات مرئية فوراً
    # بدل حماية صامتة معدومة)
    macd_state = "disabled"
    if macd_info is not None:
        built = _build_htf_source(t, o, h, l, c, macd_info, src)
        if built is None:
            warnings.append(f"فشل بناء شموع فريم الماكد {macd_info.get('label')} — شرط الماكد مغلق (fail-closed)")
            macd_state = "failed"
        else:
            closes_htf, vals, M = built
            ema_f = _ema_seeded(vals, macd_fast)
            ema_s = _ema_seeded(vals, macd_slow)
            line: List[Optional[float]] = [
                (ema_f[i] - ema_s[i]) if (ema_f[i] is not None and ema_s[i] is not None) else None
                for i in range(M)
            ]
            first_val = next((i for i, v in enumerate(line) if v is not None), None)
            sig: List[Optional[float]] = [None] * M
            if first_val is not None:
                sub = _ema_seeded([float(v) for v in line[first_val:]], macd_signal)
                for i, v in enumerate(sub):
                    sig[first_val + i] = v
            hist: List[Optional[float]] = [
                (line[i] - sig[i]) if (line[i] is not None and sig[i] is not None) else None
                for i in range(M)
            ]
            macd_line_p = _project_series(t, base_step, closes_htf, line)
            macd_signal_p = _project_series(t, base_step, closes_htf, sig)
            macd_hist_p = _project_series(t, base_step, closes_htf, hist)
            macd_meta = {
                "enabled": True,
                "resolution": macd_info.get("label"),
                "step_ms": int(macd_info["step_ms"]),
                "htf_bars": M,
                "fast": macd_fast, "slow": macd_slow, "signal": macd_signal,
                "source": src,
                "conditions": ["line > 0", "line > signal"],
            }
            macd_state = "enabled"
    series["mtg_macd_line"] = macd_line_p
    series["mtg_macd_signal"] = macd_signal_p
    series["mtg_macd_hist"] = macd_hist_p

    # -------------------------------------------------------------- RSI
    rsi_values_p: Dict[str, List[Optional[float]]] = {}
    rsi_meta: Dict[str, Any] = {"enabled": False}
    all_rsi_infos: List[Tuple[str, Dict[str, Any]]] = list(rsi_instances)
    if rsi_ref_info is not None:
        all_rsi_infos = _dedup_by_step(
            [str(x) for x, _ in rsi_instances] + [str(rsi_ref_info.get("label"))])
    for label, info in all_rsi_infos:
        safe = _safe_label(label)
        built = _build_htf_source(t, o, h, l, c, info, src)
        if built is None:
            warnings.append(f"فشل بناء شموع فريم RSI {label} — عموده فارغ")
            rsi_values_p[safe] = [None] * N
            series[f"mtg_rsi_{safe}_value"] = [None] * N
            series[f"mtg_rsi_{safe}_ma"] = [None] * N
            series[f"mtg_rsi_{safe}_bb_upper"] = [None] * N
            series[f"mtg_rsi_{safe}_bb_lower"] = [None] * N
            continue
        closes_htf, vals, M = built
        rsi = _rsi_wilder(vals, rsi_period)
        first_val = next((i for i, v in enumerate(rsi) if v is not None), None)
        ma: List[Optional[float]] = [None] * M
        if first_val is not None:
            sub = _ema_seeded([float(v) for v in rsi[first_val:]], rsi_ma_length)
            for i, v in enumerate(sub):
                ma[first_val + i] = v
        std = _rolling_std(rsi, rsi_ma_length)
        bb_u: List[Optional[float]] = [
            (ma[i] + rsi_bb_std * std[i]) if (ma[i] is not None and std[i] is not None) else None
            for i in range(M)
        ]
        bb_l: List[Optional[float]] = [
            (ma[i] - rsi_bb_std * std[i]) if (ma[i] is not None and std[i] is not None) else None
            for i in range(M)
        ]
        series[f"mtg_rsi_{safe}_value"] = _project_series(t, base_step, closes_htf, rsi)
        series[f"mtg_rsi_{safe}_ma"] = _project_series(t, base_step, closes_htf, ma)
        series[f"mtg_rsi_{safe}_bb_upper"] = _project_series(t, base_step, closes_htf, bb_u)
        series[f"mtg_rsi_{safe}_bb_lower"] = _project_series(t, base_step, closes_htf, bb_l)
        rsi_values_p[safe] = series[f"mtg_rsi_{safe}_value"]
    if rsi_active:
        rsi_meta = {
            "enabled": True,
            "instances": [str(lb) for lb, _ in rsi_instances],
            "reference": str(rsi_ref_info.get("label")),
            "reference_step_ms": int(rsi_ref_info["step_ms"]),
            "period": rsi_period, "ma_length": rsi_ma_length, "bb_std": rsi_bb_std,
            "source": src,
            "conditions": [f"rsi({lb}) > rsi({rsi_ref_info.get('label')})" for lb, _ in rsi_instances],
        }

    # ------------------------------------------------------------- البوابة
    gate: List[float] = [1.0] * N
    macd_ok: List[float] = [1.0] * N
    rsi_ok: List[float] = [1.0] * N
    warmup_bars = 0
    ref_safe = _safe_label(rsi_ref_info.get("label")) if rsi_ref_info is not None else None

    def _valid(v: Optional[float]) -> bool:
        return v is not None and math.isfinite(float(v))

    for i in range(N):
        # جمع القيم المطلوبة لهذه الشمعة (الأجزاء الشغالة فقط)
        needed: List[Optional[float]] = []
        if macd_state == "enabled":
            needed.append(macd_line_p[i])
            needed.append(macd_signal_p[i])
        if rsi_state == "enabled":
            needed.append(rsi_values_p.get(ref_safe, [None] * N)[i])
            for lb, _info in rsi_instances:
                needed.append(rsi_values_p.get(_safe_label(lb), [None] * N)[i])
        if needed and any(not _valid(v) for v in needed):
            # إحماء (أو نقص بيانات) — حياد عقد R74: البوابة مفتوحة ما لم يُطلب الحجب
            if warmup_neutral:
                gate[i] = 1.0
                macd_ok[i] = 1.0
                rsi_ok[i] = 1.0
            else:
                gate[i] = 0.0
                macd_ok[i] = 0.0
                rsi_ok[i] = 0.0
            warmup_bars += 1
            continue
        ok_m = 1.0
        if macd_state == "enabled":
            lv = float(macd_line_p[i])
            sv = float(macd_signal_p[i])
            ok_m = 1.0 if (lv > 0.0 and lv > sv) else 0.0
        elif macd_state == "failed":
            ok_m = 0.0
        ok_r = 1.0
        if rsi_state == "enabled":
            ref_v = float(rsi_values_p[ref_safe][i])
            ok_r = 1.0
            for lb, _info in rsi_instances:
                v = float(rsi_values_p[_safe_label(lb)][i])
                if not (v > ref_v):
                    ok_r = 0.0
                    break
        elif rsi_state == "failed":
            ok_r = 0.0
        macd_ok[i] = ok_m
        rsi_ok[i] = ok_r
        gate[i] = 1.0 if (ok_m > 0.5 and ok_r > 0.5) else 0.0

    series["mtg_gate"] = gate
    series["mtg_macd_ok"] = macd_ok
    series["mtg_rsi_ok"] = rsi_ok

    if macd_state == "disabled" and rsi_state == "disabled":
        warnings.append("كل شروط البوابة معطلة/غير مفهومة — البوابة هوية (gate=1 دائماً)")

    gate_on = int(sum(1.0 for g in gate if g > 0.5))
    return {
        "name": "MTF Gates (MACD + RSI multi-timeframe entry gate)",
        "engine": MTF_GATES_ENGINE_NAME,
        "spec": MTF_GATES_SPEC,
        "params": {
            "macd_timeframe": macd_meta.get("resolution") if macd_meta.get("enabled") else None,
            "macd_fast": macd_fast, "macd_slow": macd_slow, "macd_signal": macd_signal,
            "rsi_timeframes": [str(lb) for lb, _ in rsi_instances] if rsi_instances else [],
            "rsi_reference_timeframe": str(rsi_ref_info.get("label")) if rsi_ref_info else None,
            "rsi_period": rsi_period, "rsi_ma_length": rsi_ma_length,
            "rsi_bb_std": rsi_bb_std, "source": src,
            "warmup_neutral": warmup_neutral,
        },
        "series": series,
        "mtf_gates": {
            "spec": MTF_GATES_SPEC,
            "macd": macd_meta,
            "rsi": rsi_meta,
            "base_step_ms": int(base_step),
            "warmup_neutral": warmup_neutral,
            "warmup_bars": warmup_bars,
            "gate_on_bars": gate_on,
            "gate_off_bars": N - gate_on,
            "warnings": warnings,
            "rule": (
                "بوابة دخول متعددة الفريمات: "
                + ("MACD {res} (f/s/sig={f}/{s}/{g}) فوق الصفر والخط فوق الإشارة".format(
                    res=macd_meta.get("resolution"), f=macd_fast, s=macd_slow, g=macd_signal)
                    if macd_meta.get("enabled") else "بلا شرط MACD")
                + " ∧ "
                + ("RSI({tfs}) {p}/{m}/{b} كلها فوق RSI({ref})".format(
                    tfs=",".join(str(lb) for lb, _ in rsi_instances),
                    p=rsi_period, m=rsi_ma_length, b=rsi_bb_std,
                    ref=rsi_ref_info.get("label")) if rsi_active else "بلا شرط RSI")
                + " — كلها محسوبة على فريمات مستقلة مبنية من شموع الشارت وإسقاط سببي"
                  " (آخر شمعة فريم مغلقة فقط — عقد MTFEMA1)."
            ),
        },
        "signals": [],
    }


def _identity_result(reason: str) -> Dict[str, Any]:
    logger.warning("MTF-GATES: %s — البوابة هوية (gate=1)", reason)
    return {
        "name": "MTF Gates (MACD + RSI multi-timeframe entry gate)",
        "engine": MTF_GATES_ENGINE_NAME,
        "spec": MTF_GATES_SPEC,
        "params": {},
        "series": {"mtg_gate": [], "mtg_macd_ok": [], "mtg_rsi_ok": []},
        "mtf_gates": {
            "spec": MTF_GATES_SPEC,
            "identity": True,
            "warnings": [reason],
        },
        "signals": [],
    }
