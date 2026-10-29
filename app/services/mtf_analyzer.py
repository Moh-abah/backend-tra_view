#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mtf_analyzer.py — محلل التداخل متعدد الأطر الزمنية (Multi-Timeframe Confluence)
================================================================================
يركّب المؤشرات على الاستراتيجية عبر عدة فريمات في آنٍ واحد:

  • RSI على 3 فريمات (مثلاً 15m/1h/4h) بأوزان الخفيف/المتوسط/الثقيل
  • المتوسطات (EMA سريع/بطيء، SMA 50/200 — الذهبية/الموتية) خفيف وثقيل
  • MACD (Histogram + تقاطع الخط) على فريمات متعددة
  • Stochastic، Bollinger، فلتر الاتجاه (سعر مقابل SMA200 الثقيل)
  • بوابة السيولة (Liquidity Gate): الحجم مقابل متوسطه المتحرك

النتيجة: تصويت موزون (Light=1, Medium=2, Heavy=3) → LONG/SHORT/NEUTRAL
مع ثقة موحدة [0..1] وتفصيل كامل لكل (فريم × مؤشر) + بوابات رفض (Veto):
  - require_liquidity: السيولة ضعيفة → خفض الثقة أو رفض الإشارة
  - require_heavy_alignment: الفريم الثقيل يعارض → رفض الإشارة

كل الحسابات تمر عبر نفس خط مؤشرات التطبيق (apply_indicators) المستخدم في
الرسوم والباك-تست — اتساق كامل بين الشارت والاستراتيجية والتحليل.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.indicators import apply_indicators

logger = logging.getLogger(__name__)


# ============================================================================
# النماذج (Dataclasses)
# ============================================================================
LIGHT, MEDIUM, HEAVY = 1.0, 2.0, 3.0

TF_WEIGHT_PRESETS = {
    "1m": LIGHT, "5m": LIGHT, "15m": LIGHT,
    "30m": MEDIUM, "1h": MEDIUM, "2h": MEDIUM,
    "4h": HEAVY, "1d": HEAVY, "1w": HEAVY,
}


@dataclass
class TimeframeSpec:
    """فريم مع وزنه (الخفيف/الثقيل)"""
    timeframe: str
    weight: float = None  # None → من الـ preset

    def __post_init__(self):
        if self.weight is None:
            self.weight = TF_WEIGHT_PRESETS.get(self.timeframe, MEDIUM)


@dataclass
class MountedIndicator:
    """مؤشر مركّب على الفريمات"""
    name: str                       # rsi | macd | ema_cross | sma_cross | stochastic | bollinger | trend_filter | liquidity
    params: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0             # وزن المؤشر نفسه (يتضاعف بوزن الفريم)
    enabled: bool = True

    # معاملات القواعد الافتراضية لكل مؤشر
    DEFAULTS = {
        "rsi": {"period": 14, "buy_below": 30.0, "sell_above": 70.0},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "ema_cross": {"fast": 21, "slow": 50},
        "sma_cross": {"fast": 50, "slow": 200},
        "stochastic": {"k_period": 14, "d_period": 3, "buy_below": 20.0, "sell_above": 80.0},
        "bollinger": {"period": 20, "std": 2.0},
        "trend_filter": {"period": 200},
        "liquidity": {"period": 20, "min_ratio": 1.0},
    }

    def effective_params(self) -> Dict[str, Any]:
        base = dict(self.DEFAULTS.get(self.name, {}))
        base.update(self.params or {})
        return base


@dataclass
class MTFSignal:
    """نتيجة مؤشر واحد على فريم واحد"""
    timeframe: str
    indicator: str
    direction: int                  # +1 صاعد / -1 هابط / 0 محايد
    weight: float                   # وزن الفريم × وزن المؤشر
    value: Any                      # القيمة الحالية للمؤشر
    detail: str = ""
    gate: Optional[bool] = None     # للبوابات (سيولة/اتجاه)


@dataclass
class MTFAnalysis:
    """تحليل متعدد الفريمات كامل"""
    symbol: str
    as_of: Any
    signals: List[MTFSignal] = field(default_factory=list)
    long_score: float = 0.0
    short_score: float = 0.0
    max_score: float = 0.0
    confidence: float = 0.0         # 0..1
    action: str = "NEUTRAL"         # LONG | SHORT | NEUTRAL
    liquidity_ok: bool = True
    heavy_aligned: Optional[int] = None  # +1/-1/None
    veto_reasons: List[str] = field(default_factory=list)

    def breakdown_table(self) -> str:
        lines = [f"{'TF':>4} | {'Indicator':<14} | {'Dir':>4} | {'W':>4} | Value/Detail"]
        for s in self.signals:
            d = {1: "LONG", -1: "SHORT", 0: "—"}.get(s.direction, str(s.direction))
            val = s.value if not isinstance(s.value, float) else round(s.value, 5)
            lines.append(f"{s.timeframe:>4} | {s.indicator:<14} | {d:>4} | {s.weight:>4.1f} | {val} {s.detail}")
        return "\n".join(lines)


# ============================================================================
# المحلل
# ============================================================================
class MultiTimeframeAnalyzer:
    """
    يركّب مؤشرات على عدة فريمات ويصوّت بأوزان الخفيف/الثقيل.

    Usage:
        analyzer = MultiTimeframeAnalyzer(timeframes=[
            TimeframeSpec("15m"), TimeframeSpec("1h"), TimeframeSpec("4h"),
        ])
        analyzer.mount(MountedIndicator("rsi"))
        analyzer.mount(MountedIndicator("ema_cross"))
        analyzer.mount(MountedIndicator("macd"))
        analyzer.mount(MountedIndicator("liquidity"))
        result = analyzer.analyze(dataframes={"15m": df15, "1h": df1h, "4h": df4h}, symbol="BTCUSDT")
    """

    SUPPORTED = set(MountedIndicator.DEFAULTS.keys())

    def __init__(self, timeframes: List[TimeframeSpec],
                 require_liquidity: bool = False,
                 liquidity_confidence_penalty: float = 0.5,
                 require_heavy_alignment: bool = False,
                 min_confidence: float = 0.0):
        self.timeframes = list(timeframes)
        self.require_liquidity = require_liquidity
        self.liquidity_confidence_penalty = liquidity_confidence_penalty
        self.require_heavy_alignment = require_heavy_alignment
        self.min_confidence = min_confidence
        self.mounted: List[MountedIndicator] = []

    # ------------------------------------------------------------------
    def mount(self, indicator: MountedIndicator) -> "MultiTimeframeAnalyzer":
        if indicator.name not in self.SUPPORTED:
            raise ValueError(f"Unsupported MTF indicator: {indicator.name}. Supported: {sorted(self.SUPPORTED)}")
        self.mounted.append(indicator)
        return self

    # ------------------------------------------------------------------
    def analyze(self, dataframes: Dict[str, pd.DataFrame],
                symbol: str = "", as_of: Any = None,
                indicators_config_override: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> MTFAnalysis:
        """
        dataframes: {timeframe: OHLCV DataFrame} — يجب أن تغطي كل الفريمات المطلوبة.
        as_of: ختم زمني لقطع التحليل عند نقطة معينة (backtest) — None = آخر شمعة.
        indicators_config_override: يسمح بحقن أعمدة مؤشرات محسوبة مسبقاً لكل فريم
            (لتسريع باك-تست MTF: احسب مرة واحدة على كامل التاريخ).
        """
        analysis = MTFAnalysis(symbol=symbol, as_of=as_of)
        heavy_tf = self.timeframes[-1]  # افتراض: آخر فريم هو الأثقل

        for tf_spec in self.timeframes:
            tf = tf_spec.timeframe
            df = dataframes.get(tf)
            if df is None or df.empty:
                analysis.veto_reasons.append(f"missing data for {tf}")
                continue

            # قطع عند as_of (بدون تسريب مستقبلي — Look-Ahead Safe)
            work = df
            if as_of is not None:
                ts = pd.Timestamp(as_of)
                if ts.tzinfo is None and work.index.tz is not None:
                    ts = ts.tz_localize(work.index.tz)
                work = df[df.index <= ts]
                if work.empty:
                    analysis.veto_reasons.append(f"no bars at/before as_of for {tf}")
                    continue

            # حساب المؤشرات المطلوبة لهذا الفريم
            needed_cfg = self._indicators_config_for_tf(indicator_names=None)
            if indicators_config_override and tf in indicators_config_override:
                needed_cfg = indicators_config_override[tf]
            results = apply_indicators(work, needed_cfg, use_cache=False, return_raw=True)

            last_i = len(work) - 1
            close = float(work["close"].iloc[last_i])

            for mount in self.mounted:
                if not mount.enabled:
                    continue
                sig = self._evaluate_mount(mount, tf, tf_spec.weight, work, results, last_i, close)
                if sig is not None:
                    analysis.signals.append(sig)
                    if sig.gate is None:
                        analysis.max_score += tf_spec.weight * mount.weight
                        if sig.direction > 0:
                            analysis.long_score += tf_spec.weight * mount.weight
                        elif sig.direction < 0:
                            analysis.short_score += tf_spec.weight * mount.weight
                    elif sig.gate is False:
                        if mount.name == "liquidity":
                            analysis.liquidity_ok = False
                        if mount.name == "trend_filter":
                            pass

        # الحكم النهائي
        net = analysis.long_score - analysis.short_score
        analysis.confidence = (abs(net) / analysis.max_score) if analysis.max_score > 0 else 0.0

        # بوابة السيولة
        if not analysis.liquidity_ok and self.require_liquidity:
            analysis.veto_reasons.append("liquidity gate failed")
            analysis.confidence *= self.liquidity_confidence_penalty
        elif not analysis.liquidity_ok:
            analysis.confidence *= self.liquidity_confidence_penalty

        # توافق الفريم الثقيل
        heavy_signals = [s for s in analysis.signals
                         if s.timeframe == heavy_tf.timeframe and s.gate is None and s.direction != 0]
        if heavy_signals:
            dirs = {s.direction for s in heavy_signals}
            analysis.heavy_aligned = dirs.pop() if len(dirs) == 1 else 0
            if (self.require_heavy_alignment and net > 0 and analysis.heavy_aligned < 0):
                analysis.veto_reasons.append("heavy timeframe opposes LONG")
            elif (self.require_heavy_alignment and net < 0 and analysis.heavy_aligned > 0):
                analysis.veto_reasons.append("heavy timeframe opposes SHORT")

        if analysis.veto_reasons:
            analysis.action = "NEUTRAL"
            analysis.confidence = 0.0 if self.require_liquidity or self.require_heavy_alignment else analysis.confidence
        elif net >= 0 and analysis.confidence >= max(self.min_confidence, 1e-9):
            analysis.action = "LONG" if net > 0 else "NEUTRAL"
        elif net < 0 and analysis.confidence >= max(self.min_confidence, 1e-9):
            analysis.action = "SHORT"
        else:
            analysis.action = "NEUTRAL"

        return analysis

    # ------------------------------------------------------------------
    def _indicators_config_for_tf(self, indicator_names=None) -> List[Dict[str, Any]]:
        """
        فقط المؤشرات التي تمر عبر apply_indicators.
        ملاحظة: نفس الاسم مع باراميترات مختلفة يتصادم في مفتاح الناتج
        (ema21+ema50 → مفتاح واحد 'ema' يفوز فيه الأخير) — لذلك المتوسطات
        (ema_cross/sma_cross/trend_filter/liquidity) تُحسب محلياً بـ pandas.
        """
        cfgs = []
        for m in self.mounted:
            if not m.enabled:
                continue
            p = m.effective_params()
            if m.name == "rsi":
                cfgs.append({"name": "rsi", "type": "momentum", "params": {"period": int(p["period"])}})
            elif m.name == "macd":
                cfgs.append({"name": "macd", "type": "momentum",
                             "params": {"fast_period": int(p["fast"]), "slow_period": int(p["slow"]),
                                        "signal_period": int(p["signal"])}})
            elif m.name == "stochastic":
                cfgs.append({"name": "stochastic", "type": "momentum",
                             "params": {"k_period": int(p["k_period"]), "d_period": int(p["d_period"])}})
            elif m.name == "bollinger":
                cfgs.append({"name": "bollinger_bands", "type": "volatility",
                             "params": {"period": int(p["period"]), "std": float(p["std"])}})
            # ema_cross / sma_cross / trend_filter / liquidity → محلية
        return cfgs

    # ------------------------------------------------------------------
    @staticmethod
    def _ema(series: pd.Series, period: int) -> np.ndarray:
        return series.ewm(span=period, adjust=False).mean().to_numpy(dtype=np.float64)

    @staticmethod
    def _sma(series: pd.Series, period: int) -> np.ndarray:
        return series.rolling(period).mean().to_numpy(dtype=np.float64)

    # ------------------------------------------------------------------
    def _extract_series(self, results: Dict[str, Any], base_name: str,
                        params: Dict[str, Any], index_len: int) -> Optional[np.ndarray]:
        """يستخرج مصفوفة القيم من ناتج apply_indicators (raw) بمرونة عالية."""
        def _to_arr(vals):
            if vals is None:
                return None
            if isinstance(vals, np.ndarray):
                return vals.astype(np.float64)
            if isinstance(vals, (list, tuple)):
                try:
                    return np.asarray(vals, dtype=np.float64)
                except (TypeError, ValueError):
                    return None
            if isinstance(vals, pd.Series):
                return vals.to_numpy(dtype=np.float64)
            return None

        # 1) مطابقة مباشرة بالاسم
        candidates = [base_name]
        p = params
        if base_name == "rsi":
            candidates += [f"rsi_{int(p['period'])}", f"rsi({int(p['period'])})"]
        elif base_name == "ema":
            candidates += [f"ema_{int(p['period'])}", f"ema({int(p['period'])})"]
        elif base_name == "sma":
            candidates += [f"sma_{int(p['period'])}", f"sma({int(p['period'])})"]

        for key in candidates:
            if key not in results:
                continue
            res = results[key]
            if isinstance(res, dict):
                v = res.get("values")
                if isinstance(v, dict) and "data" in v:
                    arr = _to_arr(v["data"])
                    if arr is not None and len(arr) >= index_len:
                        return arr
                # مؤشرات بعدة خطوط داخل metadata (bollinger)
                meta = res.get("metadata") or {}
                for k in ("middle_band", "sma", "value", "k", "macd"):
                    if k in meta:
                        arr = _to_arr(meta[k])
                        if arr is not None and len(arr) >= index_len:
                            return arr
            elif isinstance(res, pd.Series):
                arr = res.to_numpy(dtype=np.float64)
                if len(arr) >= index_len:
                    return arr
        return None

    def _evaluate_mount(self, mount: MountedIndicator, tf: str, tf_weight: float,
                        work: pd.DataFrame, results: Dict[str, Any],
                        last_i: int, close: float) -> Optional[MTFSignal]:
        p = mount.effective_params()
        w = tf_weight * mount.weight
        n = len(work)

        def sig(direction, value, detail="", gate=None):
            return MTFSignal(timeframe=tf, indicator=mount.name, direction=direction,
                             weight=w, value=value, detail=detail, gate=gate)

        try:
            if mount.name == "rsi":
                arr = self._extract_series(results, "rsi", p, n)
                if arr is None or last_i >= len(arr) or np.isnan(arr[last_i]):
                    return sig(0, None, "rsi unavailable")
                v = float(arr[last_i])
                if v < p["buy_below"]:
                    return sig(+1, v, f"oversold <{p['buy_below']}")
                if v > p["sell_above"]:
                    return sig(-1, v, f"overbought >{p['sell_above']}")
                return sig(0, v, "neutral zone")

            if mount.name == "macd":
                res = results.get("macd")
                macd_arr = signal_arr = None
                if isinstance(res, dict):
                    meta = res.get("metadata") or {}
                    for key in ("macd", "macd_line"):
                        cand = _safe_arr(meta.get(key))
                        if cand is not None:
                            macd_arr = cand
                            break
                    for key in ("signal", "signal_line"):
                        cand = _safe_arr(meta.get(key))
                        if cand is not None:
                            signal_arr = cand
                            break
                    hist_direct = _safe_arr(meta.get("histogram"))
                    if macd_arr is not None and signal_arr is None and hist_direct is not None:
                        signal_arr = macd_arr - hist_direct  # اشتقاق الإشارة من الهيستوجرام
                if macd_arr is None or signal_arr is None or last_i >= len(macd_arr) or last_i >= len(signal_arr):
                    return sig(0, None, "macd unavailable")
                hist = float(macd_arr[last_i]) - float(signal_arr[last_i])
                prev_hist = (float(macd_arr[last_i - 1]) - float(signal_arr[last_i - 1])) if last_i >= 1 else np.nan
                fresh = ""
                if not np.isnan(prev_hist):
                    if prev_hist <= 0 < hist:
                        fresh = " (fresh bullish cross)"
                    elif prev_hist >= 0 > hist:
                        fresh = " (fresh bearish cross)"
                return sig(+1 if hist > 0 else (-1 if hist < 0 else 0), hist, f"histogram{fresh}")

            if mount.name == "ema_cross":
                fast = self._ema(work["close"], int(p["fast"]))
                slow = self._ema(work["close"], int(p["slow"]))
                if last_i >= len(fast) or last_i >= len(slow):
                    return sig(0, None, "ema unavailable")
                f, s = float(fast[last_i]), float(slow[last_i])
                if np.isnan(f) or np.isnan(s):
                    return sig(0, None, "ema warming up")
                return sig(+1 if f > s else (-1 if f < s else 0), round(f - s, 6),
                           f"ema{int(p['fast'])} vs ema{int(p['slow'])}")

            if mount.name == "sma_cross":
                fast = self._sma(work["close"], int(p["fast"]))
                slow = self._sma(work["close"], int(p["slow"]))
                if last_i >= len(fast) or last_i >= len(slow):
                    return sig(0, None, "sma unavailable")
                f, s = float(fast[last_i]), float(slow[last_i])
                if np.isnan(f) or np.isnan(s):
                    return sig(0, None, "sma warming up")
                detail = "golden alignment" if f > s else "death alignment"
                return sig(+1 if f > s else (-1 if f < s else 0), round(f - s, 6), detail)

            if mount.name == "stochastic":
                res = results.get("stochastic")
                k_arr = d_arr = None
                if isinstance(res, dict):
                    meta = res.get("metadata") or {}
                    for key in ("k_line", "k", "percent_k"):
                        cand = _safe_arr(meta.get(key))
                        if cand is not None:
                            k_arr = cand
                            break
                    for key in ("d_line", "d", "percent_d"):
                        cand = _safe_arr(meta.get(key))
                        if cand is not None:
                            d_arr = cand
                            break
                if k_arr is None or d_arr is None or last_i >= len(k_arr) or last_i >= len(d_arr):
                    return sig(0, None, "stoch unavailable")
                k, d = float(k_arr[last_i]), float(d_arr[last_i])
                if np.isnan(k) or np.isnan(d):
                    return sig(0, None, "stoch warming up")
                if k < p["buy_below"] and k > d:
                    return sig(+1, k, f"K={k:.1f}<D rising, oversold")
                if k > p["sell_above"] and k < d:
                    return sig(-1, k, f"K={k:.1f}<D falling, overbought")
                return sig(0, k, "neutral zone")

            if mount.name == "bollinger":
                res = results.get("bollinger_bands")
                upper = lower = None
                if isinstance(res, dict):
                    if all(k in res for k in ("upper", "lower")):
                        upper, lower = _safe_arr(res["upper"]), _safe_arr(res["lower"])
                    else:
                        meta = res.get("metadata") or {}
                        upper = _safe_arr(meta.get("upper_band"))
                        lower = _safe_arr(meta.get("lower_band"))
                if upper is None or lower is None or last_i >= len(upper) or last_i >= len(lower):
                    return sig(0, None, "bb unavailable")
                u, l = float(upper[last_i]), float(lower[last_i])
                if close <= l:
                    return sig(+1, close, f"close {close:.2f} ≤ lower {l:.2f}")
                if close >= u:
                    return sig(-1, close, f"close {close:.2f} ≥ upper {u:.2f}")
                return sig(0, close, "inside bands")

            if mount.name == "trend_filter":
                arr = self._sma(work["close"], int(p["period"]))
                if arr is None or last_i >= len(arr) or np.isnan(arr[last_i]):
                    return sig(0, None, "trend sma unavailable", gate=None)
                v = float(arr[last_i])
                direction = +1 if close > v else (-1 if close < v else 0)
                return sig(direction, v, f"close vs sma{int(p['period'])}")

            if mount.name == "liquidity":
                # ✅ SMA على الحجم مباشرة (registry sma يحسب على close فقط)
                vol_series = work["volume"].astype(np.float64)
                arr = self._sma(vol_series, int(p["period"]))
                if arr is None or last_i >= len(arr) or np.isnan(arr[last_i]):
                    return sig(0, None, "volume sma unavailable", gate=None)
                vol_avg = float(arr[last_i])
                vol_now = float(work["volume"].iloc[last_i])
                ratio = (vol_now / vol_avg) if vol_avg > 0 else 0.0
                ok = ratio >= p["min_ratio"]
                return sig(0, round(ratio, 3),
                           f"vol {vol_now:.2f} vs avg {vol_avg:.2f}",
                           gate=ok)

        except Exception as e:  # noqa: BLE001 — مؤشر واحد لا يُسقط التحليل كله
            logger.warning(f"MTF evaluate {mount.name}@{tf} failed: {e}")
            return sig(0, None, f"error: {e}")

        return None


def _safe_arr(v) -> Optional[np.ndarray]:
    if v is None:
        return None
    if isinstance(v, np.ndarray):
        return v.astype(np.float64)
    if isinstance(v, (list, tuple)):
        try:
            return np.asarray(v, dtype=np.float64)
        except (TypeError, ValueError):
            return None
    if isinstance(v, pd.Series):
        return v.to_numpy(dtype=np.float64)
    return None
