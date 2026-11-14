# =============================================================================
# ✅ PRO73-R1 — نواة الموشرات متعدد النسخ والفريمات (Multi-Timeframe Oscillators)
# =============================================================================
# أمر صاحب القرار (2026-11-13): «استمر وتعلم واختبر وادمج مع الثلاث موشرات
#   (RSI / MACD / Momentum) … نسخ متعددة على فريمات متعددة على نفس الشارت
#   (RSI×10 و MACD×10 و Momentum نسخ متعددة، لكل نسخة فريمها الخاص وسرعتها
#   وبطيئتها) … 14 فريماً (1s·5s·30s·1m·5m·15m·1h·4h·1d·2d·3d·1w·2w·1M) …
#   والشروط قابلة للتركيب (مثلاً S1 AND مع انطباق كل شروط الماكد والمومنتم
#   والآر إس آي)».
#
# هذه النواة = المصدر الوحيد لحساب عائلة الموشرات الثلاث (rsi/macd/mom)
# بأي عدد نسخ، وكل نسخة:
#   · فريمها الخاص من الـ14 (يُجمَّع من شموع القاعدة صعوداً — بلا نظر مستقبلية:
#     القيمة «المتاحة» عند إغلاق شمعة القاعدة = آخر شريط للفريم الأعلى أُغلق
#     عند لحظة ≤ إغلاق شمعة القاعدة فقط — الشريط النامي لا يُرى إطلاقاً).
#   · معاملاتها الخاصة (period لRSI + ماي EMA / fast·slow·signal لMACD /
#     length للمومنتم) — كلها قالبية من التكوين بلا أي أرقام داخل الكود.
#
# مراسي الفريمات (مطابقة لمزود الإنتاج + بايننس/TradingView):
#   · الثواني/الدقائق/الساعات/اليوم: epoch 00:00:00 UTC (قسمة أرضية على الخطوة).
#   · 2d/3d: epoch (نفس resample_map المزود).
#   · 1w: مرساة الاثنين (epoch خميس → off = 4 أيام).
#   · 2w: أسبوعان بمرساة الاثنين نفسها.
#   · 1M: بداية شهر التقويم UTC (datetime64[M]).
#
# الرياضيات (نمط TradingView ببذرة SMA — إحماء NaN → الشرط=False):
#   · EMA     : بذرة SMA(length) ثم lfilter (سرعة C).
#   · RSI     : Wilder (alpha=1/length) ببذرة SMA — ta.rsi.
#   · MACD    : line = EMA(fast) − EMA(slow) · signal = EMA(line, sig)
#               · hist = line − signal.
#   · Momentum: line = close[i] − close[i−length] · pct = النسبة المئوية.
#
# مُقيِّم الشروط القابل للتركيب (osc_conditions):
#   شجرة JSON:  {"logic": "and"|"or", "conditions": [ ... ]}
#   ورقة:       {"left": "<مرجع>", "op": "<معامل>", "right": "<مرجع أو رقم>",
#                "skip_unavailable": true|false (اختياري — PRO73-R3)}
#   المرجع:     "osc:<id>.<field>"  (نسخة موشر، مثل osc:macd1.hist)
#               "price:open|high|low|close" (شمعة القاعدة نفسها)
#               رقم ثابت.
#   المعاملات:  > >= < <= == != cross_above cross_below
#   (cross_above: يسار > يمين الآن ولم يكن كذلك في الشمعة السابقة، والحالة
#    السابقة معروفة (ليست إحماء NaN ولا بداية البيانات) — لا تقاطع وهمياً).
#   NaN في أي طرف → False (فترات الإحماء تحجب — سببية كاملة بلا استشراف).
#   skip_unavailable=true (PRO73-R3): إذا كان طرف الورقة يُشير إلى نسخة
#   مُصرّحة في التكوين لكنها **غير متاحة** على بيانات القاعدة (فريم أدنى من
#   القاعدة/نسخة معطّلة) → الورقة تُعدّ مُحققة (تُتجاوز) بدل False — هكذا
#   تعمل حالة «جميع الفريمات ايجابية» على أي عمق بيانات، بينما المرجع
#   المجهول تماماً (خطأ إملائي) يبقى فشلاً مغلقاً أبدياً.
#   الشجرة الفارغة/الغائبة → البوابة مفتوحة دائماً (تمرير — هوية المحرك الأصل).
# =============================================================================

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:  # scipy اختياري — عند غيابه نسقط إلى تنفيذ بايثوني نقي (نفس النتائج)
    from scipy.signal import lfilter as _lfilter
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover — بيئة بلا scipy
    _lfilter = None
    _HAVE_SCIPY = False

# ---------------------------------------------------------------------------
# عقد التطبيع — من نواة الزقزاق الموحد (مصدر حقيقة واحد للشموع)
# ---------------------------------------------------------------------------
from app.services.indicators.zigzag_fib_core import norm_candles


__all__ = [
    "MTF_OSC_CORE_SPEC",
    "MTF_OSC_CORE_VERSION",
    "TF_REGISTRY",
    "TF_ORDER",
    "TF_DURATIONS",
    "normalize_osc_instances",
    "normalize_osc_conditions",
    "resample_ohlcv",
    "infer_base_step_ms",
    "compute_oscillator_matrix",
    "evaluate_osc_conditions",
    "macdized_layer",
    "OSC_KIND_FIELDS",
]

MTF_OSC_CORE_SPEC = "PRO73-mtf-osc-core"
MTF_OSC_CORE_VERSION = "1.1.0"

# ---------------------------------------------------------------------------
# سجل الفريمات — 14 فريماً (1s → 1M) بخطواتها ومراسيها
# ---------------------------------------------------------------------------
# (الاسم، خطوة ms، نوع المرساة، إزاحة المرساة ms)
#   anchor_type: "epoch" (قسمة أرضية) | "monday" (مرساة الاثنين) | "month"
_M_S = 1_000
_M_H = 60 * _M_S
_DAY = 86_400_000
_WEEK = 7 * _DAY

TF_REGISTRY: Dict[str, Dict[str, Any]] = {
    "1s":  {"ms": 1 * _M_S,  "anchor": "epoch"},
    "5s":  {"ms": 5 * _M_S,  "anchor": "epoch"},
    "30s": {"ms": 30 * _M_S, "anchor": "epoch"},
    "1m":  {"ms": 1 * _M_H,  "anchor": "epoch"},
    "5m":  {"ms": 5 * _M_H,  "anchor": "epoch"},
    "15m": {"ms": 15 * _M_H, "anchor": "epoch"},
    "1h":  {"ms": 60 * _M_H, "anchor": "epoch"},
    "4h":  {"ms": 4 * 60 * _M_H, "anchor": "epoch"},
    "1d":  {"ms": _DAY,      "anchor": "epoch"},
    "2d":  {"ms": 2 * _DAY,  "anchor": "epoch"},
    "3d":  {"ms": 3 * _DAY,  "anchor": "epoch"},
    "1w":  {"ms": _WEEK,     "anchor": "monday", "offset": 4 * _DAY},
    "2w":  {"ms": 2 * _WEEK, "anchor": "monday", "offset": 4 * _DAY},
    "1M":  {"ms": 0,         "anchor": "month"},  # الخطوة تقومية (شهر تقويمي)
}

# ترتيب الفريمات من الأدنى إلى الأعلى (لمقارنة قابلية التجميع من شموع القاعدة)
TF_ORDER: List[str] = ["1s", "5s", "30s", "1m", "5m", "15m", "1h", "4h",
                       "1d", "2d", "3d", "1w", "2w", "1M"]

TF_DURATIONS: Dict[str, int] = {k: int(v["ms"]) for k, v in TF_REGISTRY.items()}


def _tf_rank(tf: str) -> int:
    try:
        return TF_ORDER.index(tf)
    except ValueError:
        return -1


# ---------------------------------------------------------------------------
# تطبيع نسخ الموشرات (osc_instances) — كل شيء قالبي قابل للتعديل
# ---------------------------------------------------------------------------
# المدخل: قائمة dict، الواحدة:
#   {"kind": "rsi"|"macd"|"mom" (aliases: rsi/macd/momentum/roc),
#    "id":   معرف فريد (افتراضي f"{kind}{n}"),
#    "timeframe": من الـ14 (aliases: tf/frame/interval),
#    ...معاملات النوع:
#      rsi: period (aliases: length/len), ma_length (0 = بلا ماي),
#           bb_std (0 = بلا بولينجر — افتراضي 2.0 من مستند المالك — PRO73-R3),
#           overbought/oversold (معلوماتية فقط — للعتبات تستخدم الشروط),
#      macd: fast/slow/signal,
#      mom:  length (aliases: period)}
OSC_KIND_FIELDS: Dict[str, Tuple[str, ...]] = {
    "rsi":  ("value", "ma", "bb_upper", "bb_lower"),
    "macd": ("line", "signal", "hist"),
    "mom":  ("line", "pct"),
}
_KIND_ALIASES = {
    "rsi": "rsi", "relative_strength_index": "rsi", "rsiwilder": "rsi",
    "macd": "macd", "moving_average_convergence_divergence": "macd",
    "mom": "mom", "momentum": "mom", "roc": "mom", "rate_of_change": "mom",
}
_ID_SANITIZE_BAD = set(" !@#$%^&*()+[]{};:'\"\\|,.<>/?`~=-")

def _sanitize_id(raw: Any, fallback: str) -> str:
    s = "".join(
        (ch.lower() if (ch.isalnum() or ch == "_") else "_")
        for ch in str(raw or "")
    ).strip("_")
    s = s.translate({ord(k): "_" for k in _ID_SANITIZE_BAD if len(k) == 1})
    out = "".join(ch for ch in s if ch.isalnum() or ch == "_") or fallback
    return out[:48]


def normalize_osc_instances(raw: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """تطبيع تكوين النسخ → (نسخ نظيفة، تحذيرات).

    كل نسخة: {"id","kind","timeframe","params":{...},"index"} — بلا أي أرقام
    داخل المنطق؛ فريم مجهول → تحذير وتجاهل النسخة (بلا انهيار).
    """
    warnings: List[str] = []
    if raw is None:
        return [], []
    if isinstance(raw, dict):
        # شكل {id: {...}} مقبول أيضاً — نحوّله لقائمة
        raw = [dict(v or {}, id=str(k)) for k, v in raw.items()]
    if not isinstance(raw, (list, tuple)):
        warnings.append("osc_instances غير قابل للتفسير (ليست قائمة ولا قاموس) — أُهملت")
        return [], warnings

    out: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}
    counters: Dict[str, int] = {}
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            warnings.append(f"النسخة #{i + 1} ليست قاموساً — أُهملت")
            continue
        kind_raw = str(item.get("kind") or item.get("type") or item.get("name") or "").strip().lower()
        kind = _KIND_ALIASES.get(kind_raw)
        if kind is None:
            warnings.append(f"النسخة #{i + 1}: نوع مجهول '{kind_raw}' (المعروف: rsi/macd/mom) — أُهملت")
            continue
        counters[kind] = counters.get(kind, 0) + 1
        ident = _sanitize_id(item.get("id"), f"{kind}{counters[kind]}")
        # تفرد المعرف — عند التكرار نُرقّمه
        if ident in seen_ids:
            n = 2
            while f"{ident}_{n}" in seen_ids:
                n += 1
            ident = f"{ident}_{n}"
            warnings.append(f"النسخة #{i + 1}: معرف مكرر — أُعيدت التسمية إلى '{ident}'")
        seen_ids[ident] = i

        tf_raw = str(item.get("timeframe") or item.get("tf") or item.get("frame") or item.get("interval") or "").strip()
        tf = tf_raw.lower() if tf_raw else ""
        # مرادفات شائعة
        tf_map = {"m1": "1m", "m5": "5m", "m15": "15m", "m30": "30m",
                  "h1": "1h", "h4": "4h", "d1": "1d", "w1": "1w", "mn1": "1M",
                  "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
                  "1hour": "1h", "4hour": "4h", "1day": "1d", "2day": "2d",
                  "3day": "3d", "1week": "1w", "2week": "2w", "2weeks": "2w",
                  "1month": "1M", "1mo": "1M", "M": "1M"}
        tf = tf_map.get(tf, tf)
        if tf not in TF_REGISTRY:
            warnings.append(f"النسخة '{ident}': فريم غير معروف '{tf_raw}' (المعروف: {', '.join(TF_ORDER)}) — أُهملت النسخة")
            continue

        p = item.get("params") if isinstance(item.get("params"), dict) else {}
        merged = dict(p)
        for k, v in item.items():  # معاملات مسطحة على مستوى النسخة تفوز
            if k not in ("kind", "type", "name", "id", "timeframe", "tf", "frame", "interval", "params", "enabled"):
                merged.setdefault(k, v)

        def _pos_int(keys: Sequence[str], default: int, minimum: int = 1) -> int:
            for k in keys:
                if k in merged:
                    try:
                        return max(minimum, int(float(merged[k])))
                    except (TypeError, ValueError):
                        continue
            return default

        inst: Dict[str, Any] = {"id": ident, "kind": kind, "timeframe": tf, "index": i}
        if kind == "rsi":
            def _pos_float(keys: Sequence[str], default: float, minimum: float = 0.0) -> float:
                for k in keys:
                    if k in merged:
                        try:
                            return max(minimum, float(merged[k]))
                        except (TypeError, ValueError):
                            continue
                return default
            inst["params"] = {
                "period": _pos_int(("period", "length", "len"), 14),
                "ma_length": max(0, _pos_int(("ma_length", "ma", "ma_len"), 0, 0)),
                "bb_std": _pos_float(("bb_std", "bb", "bbdev", "bb_stddev", "stddev"), 2.0),
            }
        elif kind == "macd":
            inst["params"] = {
                "fast": _pos_int(("fast", "fast_period", "fast_len"), 12),
                "slow": _pos_int(("slow", "slow_period", "slow_len"), 26),
                "signal": _pos_int(("signal", "signal_period", "sig", "signal_len"), 9),
            }
        else:  # mom
            inst["params"] = {"length": _pos_int(("length", "period", "len"), 10)}
        # enabled=false → نسخة محسوبة الشكل لكن معطلة (لا تُحسب)
        inst["enabled"] = bool(item.get("enabled", merged.get("enabled", True)))
        out.append(inst)
    return out, warnings


# ---------------------------------------------------------------------------
# تطبيع شجرة الشروط (osc_conditions) — قابلة للتركيب بلا حدود
# ---------------------------------------------------------------------------
_OPS = {">", ">=", "<", "<=", "==", "!=", "cross_above", "cross_below"}


def normalize_osc_conditions(raw: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """تطبيع شجرة الشروط → (شجرة نظيفة | None للتمرير الكامل، تحذيرات).

    العقد: {"logic": "and"|"or"|"not", "conditions": [...]}
    الأوراق: {"left": <مرجع|رقم>, "op": <معامل>, "right": <مرجع|رقم>}
    المرجع: "osc:<id>.<field>" | "price:open|high|low|close" | رقم.
    """
    warnings: List[str] = []
    if raw is None:
        return None, warnings

    def _ref_norm(v: Any) -> Any:
        if isinstance(v, bool):
            warnings.append("قيمة بولية في طرف شرط — غير مدعومة (استخدم مقارنة صريحة)")
            return None
        if isinstance(v, (int, float)):
            try:
                f = float(v)
                return f if (math.isfinite(f)) else None
            except (TypeError, ValueError):
                return None
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                f = float(s)
                if math.isfinite(f):
                    return f
            except ValueError:
                pass
            low = s.lower()
            if low.startswith("osc:"):
                rest = s[4:]
                if "." not in rest:
                    warnings.append(f"مرجع osc ناقص الحقل: '{s}' — الصيحة osc:<id>.<field>")
                    return None
                return low
            if low.startswith("price:"):
                col = low.split(":", 1)[1].strip()
                if col in ("open", "high", "low", "close", "volume"):
                    return f"price:{col}"
                warnings.append(f"مرجع سعر غير معروف: '{s}' (المعروف: open/high/low/close/volume)")
                return None
            warnings.append(f"مرجع غير معروف: '{s}' (الصيغ: osc:<id>.<field> أو price:<عمود> أو رقم)")
            return None
        warnings.append(f"طرف شرط من نوع غير معروف: {type(v).__name__}")
        return None

    def _walk(node: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
        if depth > 16:
            warnings.append("شجرة الشروط أعمق من 16 مستوى — قُطعت")
            return None
        if not isinstance(node, dict):
            warnings.append("عقدة شرط ليست قاموساً — أُهملت")
            return None
        if "logic" in node or "type" in node and str(node.get("type", "")).strip().lower() in ("and", "or", "not", "logical_and", "logical_or"):
            logic_raw = str(node.get("logic") or node.get("type") or "").strip().lower()
            logic = {"and": "and", "logical_and": "and", "all": "and",
                     "or": "or", "logical_or": "or", "any": "or",
                     "not": "not", "logical_not": "not"}.get(logic_raw)
            if logic is None:
                warnings.append(f"منطق مركّب غير معروف: '{logic_raw}' (and/or/not) — العقدة أُهملت")
                return None
            subs_raw = node.get("conditions") or node.get("args") or []
            if not isinstance(subs_raw, (list, tuple)) or not subs_raw:
                warnings.append("عقدة منطقية بلا شروط فرعية — أُهملت")
                return None
            subs: List[Dict[str, Any]] = []
            for sub in subs_raw:
                got = _walk(sub, depth + 1)
                if got is not None:
                    subs.append(got)
            if not subs:
                return None
            if logic == "not" and len(subs) != 1:
                warnings.append("منطق not يقبل شرطاً واحداً بالضبط — استُخدم الأول")
                subs = subs[:1]
            return {"logic": logic, "conditions": subs}

        left = _ref_norm(node.get("left", node.get("ref", node.get("value"))))
        op_raw = str(node.get("op") or node.get("operator") or node.get("comparison") or "").strip()
        op = op_raw if op_raw in _OPS else {">": ">", "gt": ">", "greater": ">",
                                            ">=": ">=", "ge": ">=", "gte": ">=",
                                            "<": "<", "lt": "<", "less": "<",
                                            "<=": "<=", "le": "<=", "lte": "<=",
                                            "==": "==", "eq": "==", "equals": "==",
                                            "!=": "!=", "ne": "!=", "not_equal": "!=",
                                            "cross": "cross_above", "crossup": "cross_above",
                                            "cross_up": "cross_above", "crossover": "cross_above",
                                            "crossabove": "cross_above",
                                            "crossdown": "cross_below", "cross_dn": "cross_below",
                                            "crossunder": "cross_below", "crossbelow": "cross_below",
                                            }.get(op_raw.lower())
        right = _ref_norm(node.get("right", node.get("level", node.get("threshold"))))
        if left is None or op is None:
            warnings.append(f"ورقة شرط غير قابلة للتفسير: {str(node)[:120]} — أُهملت")
            return None
        if right is None and op not in ("==", "!="):
            # right غائب: نسمح به كـ 0 (مثل {"left": "osc:macd1.hist", "op": ">"})
            right = 0.0
        return {"left": left, "op": op, "right": right,
                "skip_unavailable": bool(node.get("skip_unavailable", False))}

    if isinstance(raw, str):
        import json as _json
        try:
            raw = _json.loads(raw)
        except Exception:
            warnings.append("osc_conditions نص غير JSON — البوابة تُفتح (تمرير)")
            return None, warnings
    tree = _walk(raw)
    return tree, warnings


# ---------------------------------------------------------------------------
# رياضيات المؤشرات (نمط TradingView: بذرة SMA ثم تصفية أسّية)
# ---------------------------------------------------------------------------
def _ema_sma_seed(x: np.ndarray, length: int) -> np.ndarray:
    """EMA ببذرة SMA لطول length — NaN قبل البذرة.

    PRO73-R3: إذا كان رأس السلسلة NaN (فترة إحماء مؤشر أدنى — مثل خط RSI
    قبل بذرته)، تُبذَّر EMA من أول نافذة متصلة كاملة بعد الرأس — نفس ما
    يفعله تردينغ فيو عند تطبيق EMA فوق مؤشر له إحماء. السلاسل الخالية من
    NaN (الإغلاقات/شرائح خط الماكد) سلوكها بت-بت كما كان حرفياً.
    """
    n = len(x)
    out = np.full(n, np.nan)
    if length < 1 or n < length:
        return out
    alpha = 2.0 / (length + 1.0)
    finite = np.isfinite(x)
    if not finite.any():
        return out
    # أول نافذة بطول length خالية تماماً من NaN (رأس إحماء متصل → تُتخطى)
    bad = (~finite).astype(np.int64)
    csum = np.concatenate(([0], np.cumsum(bad)))
    counts = csum[length:] - csum[:len(x) - length + 1]
    idxs = np.nonzero(counts == 0)[0]
    if len(idxs) == 0:
        return out
    s = int(idxs[0])
    seed = float(np.mean(x[s:s + length]))
    if not math.isfinite(seed):
        return out
    out[s + length - 1] = seed
    tail_start = s + length
    if n > tail_start:
        y = np.empty(n - tail_start)
        if _HAVE_SCIPY:
            b = [alpha]
            a = [1.0, -(1.0 - alpha)]
            y, _ = _lfilter(b, a, x[tail_start:], zi=[(1.0 - alpha) * seed])
        else:  # تنفيذ نقي مكافئ
            prev = seed
            for j, xv in enumerate(x[tail_start:]):
                if math.isfinite(float(xv)) and math.isfinite(prev):
                    prev = alpha * float(xv) + (1.0 - alpha) * prev
                    y[j] = prev
                else:
                    y[j] = np.nan
                    prev = np.nan
        out[tail_start:] = y
    return out


def _rsi_wilder(c: np.ndarray, length: int) -> np.ndarray:
    """RSI Wilder ببذرة SMA (ta.rsi) — NaN قبل البذرة. al=0 → 100 صعود خالص."""
    n = len(c)
    out = np.full(n, np.nan)
    if length < 1 or n < length + 1:
        return out
    d = np.diff(c)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    a = 1.0 / length
    sg = float(np.mean(gain[:length]))
    sl = float(np.mean(loss[:length]))

    def _rsi_from(g: float, l: float) -> float:
        if l <= 0:
            return 100.0 if g > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[length] = _rsi_from(sg, sl)
    if n > length + 1:
        yg = np.empty(n - length - 1)
        yl = np.empty(n - length - 1)
        if _HAVE_SCIPY:
            b = [a]
            A = [1.0, -(1.0 - a)]
            yg, _ = _lfilter(b, A, gain[length:], zi=[(1.0 - a) * sg])
            yl, _ = _lfilter(b, A, loss[length:], zi=[(1.0 - a) * sl])
        else:
            pg, pl = sg, sl
            for j in range(length, n - 1):
                dg = float(gain[j])
                dl = float(loss[j])
                pg = a * dg + (1 - a) * pg if math.isfinite(dg) and math.isfinite(pg) else np.nan
                pl = a * dl + (1 - a) * pl if math.isfinite(dl) and math.isfinite(pl) else np.nan
                yg[j - length] = pg
                yl[j - length] = pl
        with np.errstate(divide="ignore", invalid="ignore"):
            l_pos = yl > 0
            rs = np.where(l_pos, yg / np.where(l_pos, yl, 1.0), np.inf)
            out[length + 1:] = np.where(
                l_pos, 100.0 - 100.0 / (1.0 + rs),
                np.where(yg > 0, 100.0, 50.0),
            )
    return out


def _macd(c: np.ndarray, fast: int, slow: int, sig: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    line = _ema_sma_seed(c, fast) - _ema_sma_seed(c, slow)
    n = len(c)
    sigl = np.full(n, np.nan)
    start = slow - 1
    if n >= start + sig:
        sigl[start:] = _ema_sma_seed(line[start:], sig)
    hist = line - sigl
    return line, sigl, hist


def _rolling_std(x: np.ndarray, length: int) -> np.ndarray:
    """الانحراف المعياري السكّي (population — نمط stdev بتريدينغ فيو).

    NaN قبل البذرة أو حيث تحوي النافذة أي NaN (فترات الإحماء تحجب).
    PRO73-R3 — لحساب بولينجر حول خط RSI (bb_std من مستند المالك = 2).
    """
    n = len(x)
    out = np.full(n, np.nan)
    if length < 2 or n < length:
        return out
    w = np.lib.stride_tricks.sliding_window_view(x, length)
    bad = np.isnan(w).any(axis=1)
    with np.errstate(invalid="ignore"):
        sd = w.std(axis=1)
    out[length - 1:] = np.where(bad, np.nan, sd)
    return out


def _momentum(c: np.ndarray, length: int) -> Tuple[np.ndarray, np.ndarray]:
    n = len(c)
    line = np.full(n, np.nan)
    pct = np.full(n, np.nan)
    if length >= 1 and n > length:
        prev = c[:-length].astype(np.float64)
        with np.errstate(divide="ignore", invalid="ignore"):
            line[length:] = c[length:] - prev
            pct[length:] = np.where(prev != 0, (c[length:] - prev) / np.where(prev != 0, prev, 1.0) * 100.0, np.nan)
    return line, pct


# ---------------------------------------------------------------------------
# التجميع — من شموع القاعدة إلى أي فريم أعلى (مراسي الإنتاج)
# ---------------------------------------------------------------------------
def resample_ohlcv(t: np.ndarray, o: np.ndarray, h: np.ndarray, l: np.ndarray,
                    c: np.ndarray, v: Optional[np.ndarray], tf: str) -> Dict[str, np.ndarray]:
    """تجميع OHLCV من الشبكة الأدنى إلى فريم tf — بلا أي نظر مستقبلية.

    يعيد: open_ms (زمن فتح الشريط) · close_ms (زمن إغلاقه) · OHLCV.
    مراسي: epoch للثابتة · الاثنين ل1w/2w · بداية الشهر ل1M.
    """
    spec = TF_REGISTRY[tf]
    anchor = spec["anchor"]
    n = len(t)
    if anchor == "month":
        months = t.astype("datetime64[ms]").astype("datetime64[M]")
        keys = months.astype(np.int64)
    elif anchor == "monday":
        off = int(spec.get("offset", 0))
        step = int(spec["ms"])
        keys = (t - off) // step
    else:
        step = int(spec["ms"])
        keys = t // step
    if n == 0:
        empty_i = np.zeros(0, dtype=np.int64)
        empty_f = np.zeros(0, dtype=np.float64)
        return {"open_ms": empty_i, "close_ms": empty_i,
                "open": empty_f, "high": empty_f, "low": empty_f,
                "close": empty_f, "volume": empty_f}
    starts = np.concatenate(([0], np.nonzero(np.diff(keys))[0] + 1))
    ends = np.concatenate((starts[1:], [n]))
    if anchor == "month":
        open_ms = (months[starts].astype("datetime64[ms]").astype(np.int64))
        # نهاية الشهر = بداية الشهر التالي
        nxt = (months[starts].astype("datetime64[M]") + np.timedelta64(1, "M")).astype("datetime64[ms]").astype(np.int64)
        close_ms = nxt
    elif anchor == "monday":
        off = int(spec.get("offset", 0))
        step = int(spec["ms"])
        open_ms = keys[starts] * step + off
        close_ms = open_ms + step
    else:
        step = int(spec["ms"])
        open_ms = keys[starts] * step
        close_ms = open_ms + step
    vol = v if v is not None else np.zeros(n, dtype=np.float64)
    return {
        "open_ms": open_ms.astype(np.int64),
        "close_ms": close_ms.astype(np.int64),
        "open": o[starts],
        "high": np.maximum.reduceat(h, starts),
        "low": np.minimum.reduceat(l, starts),
        "close": c[ends - 1],
        "volume": np.add.reduceat(vol, starts),
    }


def infer_base_step_ms(t: np.ndarray) -> int:
    """استنتاج خطوة شموع القاعدة (ms) من الفروق الوسيطية (متين ضد الفجوات)."""
    if len(t) < 2:
        return 60_000
    d = np.diff(t)
    d = d[d > 0]
    if not len(d):
        return 60_000
    step = int(np.median(d))
    return step if step > 0 else 60_000


# ---------------------------------------------------------------------------
# حساب المصفوفة — النسخ كلها على شبكة شموع القاعدة (بلا نظر مستقبلية)
# ---------------------------------------------------------------------------
def compute_oscillator_matrix(
    candles: Any,
    instances: Any,
    base_tf: Optional[str] = None,
) -> Dict[str, Any]:
    """شموع القاعدة + تكوين النسخ → المصفوفة الكاملة على شبكة القاعدة.

    المخرجات (كلها على طول شموع القاعدة N — قيم None حيث NaN):
      {
        "base_step_ms", "base_tf", "bars": N,
        "instances": [تقرير كل نسخة: id/kind/timeframe/params/available/why],
        "series": {"<id>": {"<field>": [Optional[float]]*N}},
        "warnings": [...]
      }
    نسخة بفريم أدنى من خطوة القاعدة → غير متاحة (قيم None) + تحذير (لا انهيار).
    نسخة بفريم == القاعدة → تُحسب على شموع القاعدة مباشرة (بلا تجميع).
    """
    t, o, h, l, c = norm_candles(candles)
    N = len(c)
    t_i = np.asarray([int(x) for x in t], dtype=np.int64) if N else np.zeros(0, dtype=np.int64)
    o_f = np.asarray([float(x) if x is not None else np.nan for x in o], dtype=np.float64) if N else np.zeros(0)
    h_f = np.asarray([float(x) if x is not None else np.nan for x in h], dtype=np.float64) if N else np.zeros(0)
    l_f = np.asarray([float(x) if x is not None else np.nan for x in l], dtype=np.float64) if N else np.zeros(0)
    c_f = np.asarray([float(x) if x is not None else np.nan for x in c], dtype=np.float64) if N else np.zeros(0)
    # الحجم من الشموع إن وُجد (للتجميع فقط — الموشرات الثلاثة لا تستخدمه)
    try:
        from app.services.indicators.zigzag_fib_core import norm_volume
        vols = norm_volume(candles)
        v_f = np.asarray([float(x) if x is not None else 0.0 for x in vols], dtype=np.float64) if N else np.zeros(0)
    except Exception:
        v_f = np.zeros(0 if not N else N, dtype=np.float64)
    if N and len(v_f) != N:
        v_f = np.zeros(N, dtype=np.float64)

    base_step = infer_base_step_ms(t_i) if N else 60_000
    if base_tf is None:
        base_tf = next((k for k, d in TF_DURATIONS.items() if int(d) == base_step), f"{base_step}ms")
    eval_ms = (t_i + base_step).astype(np.int64) if N else np.zeros(0, dtype=np.int64)  # لحظة إغلاق شمعة القاعدة

    insts, warnings = normalize_osc_instances(instances)
    series: Dict[str, Dict[str, List[Optional[float]]]] = {}
    reports: List[Dict[str, Any]] = []
    tf_cache: Dict[str, Dict[str, np.ndarray]] = {}

    def _tf_bars(tf: str) -> Dict[str, np.ndarray]:
        if tf not in tf_cache:
            tf_cache[tf] = resample_ohlcv(t_i, o_f, h_f, l_f, c_f, v_f if N else None, tf)
        return tf_cache[tf]

    def _map_to_base(vals: np.ndarray, close_ms: np.ndarray) -> np.ndarray:
        """آخر شريط مغلق فقط — searchsorted right على أوقات الإغلاق."""
        if N == 0 or len(vals) == 0:
            return np.full(N, np.nan)
        idx = np.searchsorted(close_ms, eval_ms, side="right") - 1
        out = np.full(N, np.nan)
        ok = idx >= 0
        out[ok] = vals[idx[ok]]
        return out

    for inst in insts:
        if not inst.get("enabled", True):
            reports.append({**inst, "available": False, "why": "disabled"})
            continue
        tf = inst["timeframe"]
        tf_ms = int(TF_DURATIONS[tf])
        p = inst["params"]
        rid = inst["id"]
        if tf_ms and tf_ms < base_step:
            # فريم أدنى من شموع القاعدة — لا يمكن تجميعه من الأسفل
            warnings.append(
                f"النسخة '{rid}' ({inst['kind']} {tf}): الفريم أدنى من فريم شموع القاعدة "
                f"({base_tf}) — لا يمكن بناؤه من بيانات أسمك؛ القيم None (مرر شموعاً أدق لبنائه)")
            fields = OSC_KIND_FIELDS[inst["kind"]]
            series[rid] = {f: [None] * N for f in fields}
            reports.append({**inst, "available": False, "why": "tf_below_base"})
            continue

        if tf_ms and tf_ms == base_step:
            bars_close = c_f  # نفس شموع القاعدة
            close_ms = eval_ms  # شريط i يُغلق عند إغلاق شمعة القاعدة i
        else:
            bars = _tf_bars(tf)
            bars_close = bars["close"]
            close_ms = bars["close_ms"]

        if inst["kind"] == "rsi":
            vals = _rsi_wilder(bars_close, int(p["period"]))
            ma_len = int(p["ma_length"])
            k_std = float(p.get("bb_std", 2.0) or 0.0)
            ma = _ema_sma_seed(vals, ma_len) if ma_len > 0 else np.full(len(vals), np.nan)
            have_bb = (ma_len > 1) and (k_std > 0)
            if have_bb:
                sd = _rolling_std(vals, ma_len)
                bb_up = ma + k_std * sd
                bb_dn = ma - k_std * sd
            else:
                bb_up = np.full(len(vals), np.nan)
                bb_dn = np.full(len(vals), np.nan)
            series[rid] = {
                "value": _to_jsonable(_map_to_base(vals, close_ms)),
                "ma": _to_jsonable(_map_to_base(ma, close_ms)) if ma_len > 0 else [None] * N,
                "bb_upper": _to_jsonable(_map_to_base(bb_up, close_ms)) if have_bb else [None] * N,
                "bb_lower": _to_jsonable(_map_to_base(bb_dn, close_ms)) if have_bb else [None] * N,
            }
        elif inst["kind"] == "macd":
            line, sig, hist = _macd(bars_close, int(p["fast"]), int(p["slow"]), int(p["signal"]))
            series[rid] = {
                "line": _to_jsonable(_map_to_base(line, close_ms)),
                "signal": _to_jsonable(_map_to_base(sig, close_ms)),
                "hist": _to_jsonable(_map_to_base(hist, close_ms)),
            }
        else:  # mom
            line, pct = _momentum(bars_close, int(p["length"]))
            series[rid] = {
                "line": _to_jsonable(_map_to_base(line, close_ms)),
                "pct": _to_jsonable(_map_to_base(pct, close_ms)),
            }
        reports.append({**inst, "available": True, "why": None})

    return {
        "spec": MTF_OSC_CORE_SPEC,
        "version": MTF_OSC_CORE_VERSION,
        "base_step_ms": int(base_step),
        "base_tf": base_tf,
        "bars": int(N),
        "instances": reports,
        "series": series,
        "warnings": warnings,
    }


def _to_jsonable(arr: np.ndarray) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for v in np.asarray(arr, dtype=np.float64):
        fv = float(v)
        out.append(fv if math.isfinite(fv) else None)
    return out


# ---------------------------------------------------------------------------
# مُقيِّم الشروط على شبكة القاعدة — المرجع: osc:<id>.<field> | price:* | رقم
# ---------------------------------------------------------------------------
def _resolve_grid_arg(arg: Any, osc_series: Dict[str, Dict[str, np.ndarray]],
                      price: Dict[str, np.ndarray], N: int) -> Optional[np.ndarray]:
    if isinstance(arg, (int, float)):
        return np.full(N, float(arg))
    if not isinstance(arg, str):
        return None
    low = arg.lower()
    if low.startswith("osc:"):
        rest = low[4:]
        if "." not in rest:
            return None
        iid, field = rest.split(".", 1)
        rec = osc_series.get(iid)
        if rec is None or field not in rec:
            return None
        return rec[field]
    if low.startswith("price:"):
        col = low.split(":", 1)[1].strip()
        return price.get(col)
    return None


def evaluate_osc_conditions(
    tree: Optional[Dict[str, Any]],
    osc_series: Dict[str, Dict[str, np.ndarray]],
    o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray,
    N: int,
    osc_available: Optional[Dict[str, bool]] = None,
) -> Tuple[np.ndarray, List[str]]:
    """تقييم الشجرة على كل شمعة → (بوابة bool[N], تحذيرات).

    الشجرة الفارغة/None → كل True (بوابة مفتوحة — هوية المحرك الأصل).
    NaN في أي طرف ورقة → False لتلك الورقة عند تلك الشمعة (فترات الإحماء تحجب).

    PRO73-R3 — skip_unavailable: تُمرّر خريطة توفر النسخ (osc_available):
    {id: available}. الورقة التي تحمل skip_unavailable=true ويُشير أحد طرفيها
    إلى نسخة **غير متاحة** (فريم أدنى من القاعدة/معطّلة) تُعدّ مُحققة على كل
    الشموع (تُتجاوز) — هكذا تعمل حالة «جميع الفريمات ايجابية» على أي عمق
    بيانات. المرجع المجهول تماماً (خطأ إملائي) يبقى فشلاً مغلقاً (False).
    """
    warns: List[str] = []
    if N == 0:
        return np.zeros(0, dtype=bool), warns
    if tree is None:
        return np.ones(N, dtype=bool), warns
    price = {"open": o, "high": h, "low": l, "close": c, "volume": None}

    def _ref_unavailable(arg: Any) -> bool:
        if not isinstance(arg, str) or osc_available is None:
            return False
        low = arg.lower()
        if not low.startswith("osc:") or "." not in low[4:]:
            return False
        iid = low[4:].split(".", 1)[0]
        return osc_available.get(iid) is False

    def _leaf_ok(node: Dict[str, Any]) -> Optional[np.ndarray]:
        if node.get("skip_unavailable") and (
                _ref_unavailable(node["left"]) or _ref_unavailable(node["right"])):
            return np.ones(N, dtype=bool)
        a = _resolve_grid_arg(node["left"], osc_series, price, N)
        b = _resolve_grid_arg(node["right"], osc_series, price, N)
        if a is None or b is None:
            # فشل مغلق (fail-closed): ورقة غير قابلة للحل (مرجع مجهول/نسخة غير
            # متاحة) = الشرط لا يتحقق أبداً — لا تُفتح البوابة بصمت أبداً.
            warns.append(f"مرجع غير قابل للحل في شرط (فشل مغلق): {str(node)[:100]}")
            return np.zeros(N, dtype=bool)
        op = node["op"]
        if op == "cross_above" or op == "cross_below":
            with np.errstate(invalid="ignore"):
                above = np.where(np.isnan(a) | np.isnan(b), False, a > b)
                below = np.where(np.isnan(a) | np.isnan(b), False, a < b)
                # PRO73-R3: التقاطع يتطلب حالة سابقة **معروفة** — لا تقاطع وهمياً
                # عند بداية البيانات أو فور انتهاء إحماء NaN (لا نعرف أنه لم يكن فوق).
                known_prev = np.concatenate(
                    ([False], np.isfinite(a[:-1]) & np.isfinite(b[:-1])))
            prev_above = np.concatenate(([False], above[:-1]))
            prev_below = np.concatenate(([False], below[:-1]))
            if op == "cross_above":
                return above & ~prev_above & known_prev
            return below & ~prev_below & known_prev
        with np.errstate(invalid="ignore"):
            if op == ">":
                m = a > b
            elif op == ">=":
                m = a >= b
            elif op == "<":
                m = a < b
            elif op == "<=":
                m = a <= b
            elif op == "==":
                m = a == b
            elif op == "!=":
                m = a != b
            else:
                warns.append(f"معامل مجهول '{op}'")
                return None
            return np.where(np.isnan(a) | np.isnan(b), False, m)

    def _walk(node: Dict[str, Any]) -> Optional[np.ndarray]:
        if "logic" in node:
            subs: List[np.ndarray] = []
            for sub in node["conditions"]:
                got = _walk(sub)
                if got is None:
                    return None
                subs.append(got)
            logic = node["logic"]
            if logic == "and":
                out = subs[0].copy()
                for s in subs[1:]:
                    out = out & s
                return out
            if logic == "or":
                out = subs[0].copy()
                for s in subs[1:]:
                    out = out | s
                return out
            if logic == "not":
                return ~subs[0]
            return None
        return _leaf_ok(node)

    gate = _walk(tree)
    if gate is None:
        return np.ones(N, dtype=bool), warns + ["شجرة الشروط غير قابلة للتقييم — البوابة مفتوحة"]
    return gate.astype(bool), warns


def _np_from_jsonable(vals: List[Optional[float]], N: int) -> np.ndarray:
    arr = np.asarray([np.nan if v is None else float(v) for v in (vals or [])], dtype=np.float64)
    if len(arr) < N:
        arr = np.concatenate((arr, np.full(N - len(arr), np.nan)))
    return arr[:N]


# ---------------------------------------------------------------------------
# ✅ PRO73-R2 — طبقة الدمج المشتركة لمحركي «الماكدية» (ترنديه ماكديه /
#    ملتهبه ماكديه): مصفوفة الموشرات + بوابة الشروط + المصفوفات الجاهزة.
# ---------------------------------------------------------------------------
def macdized_layer(
    candles: Any,
    osc_instances: Any,
    osc_conditions: Any,
) -> Dict[str, Any]:
    """الطبقة المشتركة: يحسبها كلا محركي الماكدية فوق محركه الأصل.

    يعيد:
      {
        "N", "o_np","h_np","l_np","c_np"       (مصفوفات OHLC القاعدة),
        "osc"        (نتيجة compute_oscillator_matrix كاملة),
        "osc_json"   (سلاسل JSONable للنسخ),
        "osc_np"     ({id: {field: ndarray}}),
        "tree"       (شجرة الشروط المطبَّعة | None),
        "gate"       (ndarray bool[N] — True = الشروط منطبقة),
        "gate_list"  (قائمة 0/1 للسلاسل),
        "warnings"   (مجمع: النسخ + الشجرة + التقييم),
      }
    """
    t, o, h, l, c = norm_candles(candles)
    N = len(c)
    osc = compute_oscillator_matrix(candles, osc_instances)
    osc_json = osc.get("series") or {}
    osc_np: Dict[str, Dict[str, np.ndarray]] = {}
    for iid, fields in osc_json.items():
        osc_np[iid] = {}
        for f, vals in fields.items():
            osc_np[iid][f] = _np_from_jsonable(vals, N)

    tree, tree_warns = normalize_osc_conditions(osc_conditions)
    o_np = np.asarray([float(x) if x is not None else np.nan for x in o], dtype=np.float64) if N else np.zeros(0)
    h_np = np.asarray([float(x) if x is not None else np.nan for x in h], dtype=np.float64) if N else np.zeros(0)
    l_np = np.asarray([float(x) if x is not None else np.nan for x in l], dtype=np.float64) if N else np.zeros(0)
    c_np = np.asarray([float(x) if x is not None else np.nan for x in c], dtype=np.float64) if N else np.zeros(0)
    # PRO73-R3 — خريطة توفر النسخ (الفريم الأدنى من القاعدة/المعطّلة → skip_unavailable)
    osc_available: Dict[str, bool] = {}
    for rep in (osc.get("instances") or []):
        try:
            osc_available[str(rep.get("id"))] = bool(rep.get("available", True))
        except Exception:
            continue
    gate, gate_warns = evaluate_osc_conditions(
        tree, osc_np, o_np, h_np, l_np, c_np, N, osc_available=osc_available)
    warnings = list(osc.get("warnings") or []) + list(tree_warns) + list(gate_warns)
    gate_list: List[float] = [1.0 if bool(g) else 0.0 for g in gate] if N else []
    return {
        "N": N,
        "o_np": o_np, "h_np": h_np, "l_np": l_np, "c_np": c_np,
        "osc": osc, "osc_json": osc_json, "osc_np": osc_np,
        "tree": tree, "gate": gate, "gate_list": gate_list,
        "warnings": warnings,
    }
