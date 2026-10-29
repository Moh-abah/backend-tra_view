# trading_backend/app/services/signals/engine.py
"""
SignalEngine — طبقة تكييف (Adapter) فوق StrategyEngine.

لا يحتوي أي منطق تداول بنفسه؛ فقط:
1. يبني StrategyEngine من تكوين الإستراتيجية (StrategyConfig).
2. يشغّل run_strategy بشكل async صحيح.
3. يحوّل TradeSignal objects إلى قواميس بسيطة قابلة للإرسال عبر JSON.

شكل الإشارة الناتجة:
    {
        "symbol": ..., "timeframe": ..., "signal_type": "buy"|"sell"|"close",
        "strength": float, "price": float, "timestamp": ISO-string,
        "reason": str, "rule_name": str
    }
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from app.services.strategy.core import StrategyEngine as _CoreStrategyEngine
from app.services.strategy.schemas import StrategyConfig

logger = logging.getLogger(__name__)


class SignalEngine:
    """محرك الإشارات — يلف StrategyEngine ويحوّل النتائج لقواميس آمنة لـ JSON."""

    def __init__(self):
        # لا نبني شيئاً ثقيلاً هنا؛ الإنشاء الكسول عند أول استدعاء evaluate
        self._config_cache: Dict[str, StrategyConfig] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    async def evaluate(
        self,
        symbol: str,
        timeframe: str,
        dataframe: pd.DataFrame,
        indicators_config: Optional[List[Dict[str, Any]]] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        live_mode: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        تقييم آخر شمعة وإرجاع قائمة إشارات تداول (عادة 0 أو 1 إشارة).

        Args:
            symbol: الرمز (مثال BTCUSDT)
            timeframe: الإطار الزمني
            dataframe: بيانات الشموع (فهرسها وقت الشمعة)
            indicators_config: مؤشرات اختيارية تُحقن في التكوين إن لم يحدد التكوين مؤشرات
            strategy_config: تكوين الإستراتيجية (قاموس متوافق مع StrategyConfig)
            live_mode: True = تقييم آخر شمعة فقط (مناسب للبث اللحظي)

        Returns:
            List[Dict]: إشارات بالشكل الموحد {symbol, timeframe, signal_type, ...}
        """
        # 1) حمايات المدخلات
        if dataframe is None or dataframe.empty or len(dataframe) < 2:
            logger.debug("SignalEngine.evaluate(%s/%s): بيانات غير كافية", symbol, timeframe)
            return []

        if not strategy_config or not isinstance(strategy_config, dict):
            logger.debug("SignalEngine.evaluate(%s/%s): لا يوجد تكوين إستراتيجية", symbol, timeframe)
            return []

        config_dict = self._prepare_config(strategy_config, indicators_config, timeframe)

        # 2) بناء محرك إستراتيجية خاص بهذا الاستدعاء
        #    (نبني محركاً جديداً لكل رمز لتجنب تلوث الكاش/الحالة بين الرموز)
        try:
            strategy_config_obj = self._build_strategy_config(config_dict)
        except Exception as e:
            logger.warning("SignalEngine.evaluate(%s/%s): تكوين إستراتيجية غير صالح: %s",
                           symbol, timeframe, e)
            return []

        engine = _CoreStrategyEngine(strategy_config_obj)

        # 3) تشغيل الإستراتيجية (coroutine — يجب انتظاره)
        try:
            result = await engine.run_strategy(dataframe, live_mode, False)
        except ValueError as e:
            # مثال: "Insufficient data to run strategy"
            logger.warning("SignalEngine.evaluate(%s/%s): %s", symbol, timeframe, e)
            return []
        except Exception:
            logger.exception("SignalEngine.evaluate(%s/%s): فشل تشغيل الإستراتيجية", symbol, timeframe)
            return []

        # 4) تحويل النتائج — نفضّل الإشارات المفلترة ونعود للخام إن لم توجد
        raw_signals = getattr(result, "filtered_signals", None) or getattr(result, "signals", None) or []

        signals: List[Dict[str, Any]] = []
        for sig in raw_signals:
            converted = self._signal_to_dict(symbol, timeframe, sig)
            if converted is not None:
                signals.append(converted)

        return signals

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _prepare_config(
        self,
        strategy_config: Dict[str, Any],
        indicators_config: Optional[List[Dict[str, Any]]],
        timeframe: str,
    ) -> Dict[str, Any]:
        """نسخة آمنة من التكوين + حقن المؤشرات إن كانت مفقودة."""
        config = dict(strategy_config)

        if not config.get("indicators") and indicators_config:
            sanitized = []
            for ind in indicators_config:
                if not isinstance(ind, dict) or not ind.get("name"):
                    continue
                ind = dict(ind)
                # IndicatorConfig يتطلب type؛ نضع افتراضياً "trend" إن غاب
                ind.setdefault("type", "trend")
                sanitized.append(ind)
            if sanitized:
                config["indicators"] = sanitized

        # الإطار الزمني الفعلي للبث يتقدم على الإطار الأساسي في التكوين
        if timeframe and not config.get("base_timeframe"):
            config["base_timeframe"] = timeframe

        return config

    def _build_strategy_config(self, config_dict: Dict[str, Any]) -> StrategyConfig:
        """بناء StrategyConfig مع كاش بسيط حسب الاسم/الإصدار لتقليل إعادة التحقق."""
        cache_key = f"{config_dict.get('name')}|{config_dict.get('version')}"
        cached = self._config_cache.get(cache_key)
        if cached is not None:
            # نسخة جديدة حتى لا تتأثر created_at/updated_at بين الرموز
            return cached.model_copy(update={"updated_at": datetime.utcnow()})

        config_obj = StrategyConfig(**config_dict)
        config_obj.updated_at = datetime.utcnow()
        if len(self._config_cache) > 50:
            self._config_cache.clear()
        self._config_cache[cache_key] = config_obj
        return config_obj.model_copy(update={"updated_at": datetime.utcnow()})

    def _signal_to_dict(
        self,
        symbol: str,
        timeframe: str,
        sig: Any,
    ) -> Optional[Dict[str, Any]]:
        """تحويل TradeSignal إلى dict موحد بشكل دفاعي (getattr مع بدائل)."""
        try:
            action = getattr(sig, "action", None) or "hold"

            timestamp = getattr(sig, "timestamp", None)
            if isinstance(timestamp, datetime):
                timestamp_str = timestamp.isoformat()
            elif timestamp is not None and not isinstance(timestamp, str):
                timestamp_str = str(timestamp)
            else:
                timestamp_str = datetime.utcnow().isoformat()

            try:
                price = float(getattr(sig, "price", 0.0) or 0.0)
            except (TypeError, ValueError):
                price = 0.0

            try:
                strength = float(getattr(sig, "strength", 1.0) or 1.0)
            except (TypeError, ValueError):
                strength = 1.0

            metadata = getattr(sig, "metadata", None)
            if not isinstance(metadata, dict):
                metadata = {}

            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "signal_type": action,
                "strength": strength,
                "price": price,
                "timestamp": timestamp_str,
                "reason": getattr(sig, "reason", "") or "",
                "rule_name": getattr(sig, "rule_name", "") or "",
                "metadata": metadata,
            }
        except Exception:
            logger.exception("SignalEngine: فشل تحويل إشارة إلى dict")
            return None
