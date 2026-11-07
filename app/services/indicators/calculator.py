# trading_backend\app\services\indicators\calculator.py
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np
import asyncio
import threading
import time
from collections import OrderedDict
from .base import IndicatorConfig, IndicatorResult, sanitize_indicator_config
from .registry import IndicatorRegistry
from concurrent.futures import ThreadPoolExecutor

class IndicatorCalculator:
    """محرك حساب المؤشرات فقط - لا يعتمد على أي خدمات خارجية"""

    # ---- Cache bounds (bugfix: cache used to be an unbounded dict keyed by
    # DataFrame hash -> memory leak on long-running processes) ----
    _max_size: int = 256        # LRU eviction bound (max cached entries)
    _cache_ttl: float = 300.0   # seconds; entries older than this are purged

    def __init__(self):
        self.registry = IndicatorRegistry()
        # Ordered map: cache_key -> (monotonic_ts, value). OrderedDict gives us
        # O(1) move_to_end / popitem for LRU semantics while staying dict-compatible.
        self.cache = OrderedDict()
        # Guard against concurrent mutation from the ThreadPoolExecutor path.
        self._cache_lock = threading.Lock()

    # ==================== Cache helpers (LRU + TTL) ====================

    def _cache_get(self, cache_key: str):
        """Return cached value if present and fresh (moves key to MRU end)."""
        now = time.monotonic()
        with self._cache_lock:
            entry = self.cache.get(cache_key)
            if entry is None:
                return None
            ts, value = entry
            if now - ts > self._cache_ttl:
                # Expired entry: purge it and report a miss.
                del self.cache[cache_key]
                return None
            self.cache.move_to_end(cache_key)  # mark as recently used
            return value

    def _cache_set(self, cache_key: str, value) -> None:
        """Insert/update a cache entry, purging expired + LRU-overflow entries."""
        now = time.monotonic()
        with self._cache_lock:
            self.cache[cache_key] = (now, value)
            self.cache.move_to_end(cache_key)
            self._evict_cache_locked(now)

    def _evict_cache_locked(self, now: float) -> None:
        """Must be called while holding self._cache_lock."""
        # 1) Purge expired entries (oldest first — OrderedDict keeps insertion
        #    / access order, so the front is the least-recently-used).
        while self.cache:
            oldest_ts, _ = next(iter(self.cache.values()))
            if now - oldest_ts <= self._cache_ttl:
                break
            self.cache.popitem(last=False)
        # 2) Enforce the hard size bound by dropping least-recently-used entries.
        while len(self.cache) > self._max_size:
            self.cache.popitem(last=False)

    def clear_cache(self) -> None:
        """Explicit cache wipe (useful for tests / forced refresh)."""
        with self._cache_lock:
            self.cache.clear()

    # ==================== ✅ الجولة 11: جسر مؤشرات البنية ====================

    # الأسماء المقبولة (القصيرة والكاملة — يدعم أيضاً الاسم النقطي base.sub):
    _OVERLAY_ALIASES = {
        "zigzag": "zigzag", "zigzag_channels": "zigzag",
        "fib": "fib", "auto_fib_retracement": "fib",
        "trendline": "trendline", "auto_trendline": "trendline",
        # الجولة 12: فيبو الزيجزاق المدمج
        "zigzag_fib": "zzfib", "zzfib": "zzfib",
        # ✅ ROUND22: ZLF-End-To-End — المحرك المنفصل الجديد
        "zigzag_fib_e2e": "zzfib_e2e", "zzfib_e2e": "zzfib_e2e",
        # ✅ ROUND32: الترندية (استنساخ E2E + بوابة الترند) + مؤشر الترند المستقل
        "zigzag_fib_e2e_trendy": "zzfib_e2e_trendy", "zzfib_e2e_trendy": "zzfib_e2e_trendy",
        "trend_fractal": "trend_fractal", "fractal_trendlines": "trend_fractal",
    }
    # العمود التعاقدي الأساسي لكل base (العقد الملزم مع الفرونت — الجولة 11/12)
    _OVERLAY_PRIMARY = {
        "zigzag": "ind_zz_pivot",
        "fib": "ind_fib_signal",
        "trendline": "ind_atl_signal",
        "zzfib": "ind_zzf_touch",
        # ✅ ROUND22: الأساسي للمحرك المنفصل = عمود الدخول الجامع
        "zzfib_e2e": "ind_zzfe_entry",
        # ✅ ROUND32: الترندية = عمود الدخول الجامع بعد البوابة · الترند = بوابة الإجماع
        "zzfib_e2e_trendy": "ind_zzfet_entry",
        "trend_fractal": "ind_trf_trend_ok",
    }
    # مرادفات الأسماء الفرعية → أعمدة ind_* التعاقدية
    _OVERLAY_SUB_COLUMNS = {
        "zz_state": "ind_zz_state", "state": "ind_zz_state", "os": "ind_zz_state",
        "zz_pivot": "ind_zz_pivot", "pivot": "ind_zz_pivot",
        "zz_pivot_high": "ind_zz_pivot_high", "pivot_high": "ind_zz_pivot_high", "pivothigh": "ind_zz_pivot_high",
        "zz_pivot_low": "ind_zz_pivot_low", "pivot_low": "ind_zz_pivot_low", "pivotlow": "ind_zz_pivot_low",
        "zz_prev_pivot_low": "ind_zz_prev_pivot_low", "prev_pivot_low": "ind_zz_prev_pivot_low",
        "zz_prev_pivot_high": "ind_zz_prev_pivot_high", "prev_pivot_high": "ind_zz_prev_pivot_high",
        "fib_dir": "ind_fib_dir", "dir": "ind_fib_dir",
        "fib_start": "ind_fib_start", "start": "ind_fib_start",
        "fib_end": "ind_fib_end", "end": "ind_fib_end",
        "fib_target": "ind_fib_target", "target": "ind_fib_target",
        "fib_signal": "primary", "signal": "primary",
        "atl_upper": "ind_atl_upper", "tl_upper": "ind_atl_upper", "upper": "ind_atl_upper",
        "atl_lower": "ind_atl_lower", "tl_lower": "ind_atl_lower", "lower": "ind_atl_lower",
        "atl_signal": "ind_atl_signal",
        "atl_cross_upper": "ind_atl_cross_upper", "tl_cross_upper": "ind_atl_cross_upper", "cross_upper": "ind_atl_cross_upper",
        "atl_cross_lower": "ind_atl_cross_lower", "tl_cross_lower": "ind_atl_cross_lower", "cross_lower": "ind_atl_cross_lower",
        # الجولة 12: أعمدة فيبو الزيجزاق المدمج
        "zzfib_dir": "ind_zzf_dir", "zzf_dir": "ind_zzf_dir",
        "zzfib_p1": "ind_zzf_p1", "zzf_p1": "ind_zzf_p1",
        "zzfib_p2": "ind_zzf_p2", "zzf_p2": "ind_zzf_p2",
        "zzfib_i1": "ind_zzf_i1", "zzf_i1": "ind_zzf_i1",
        "zzfib_i2": "ind_zzf_i2", "zzf_i2": "ind_zzf_i2",
        "zzfib_touch": "ind_zzf_touch", "zzf_touch": "ind_zzf_touch", "touch": "ind_zzf_touch",
        # ✅ ROUND22 (ZLF-End-To-End) — أعمدة المحرك المنفصل (أسماء جديدة كلياً)
        "zzfe_dir": "ind_zzfe_dir", "zzfib_e2e_dir": "ind_zzfe_dir",
        "zzfe_p1": "ind_zzfe_p1", "zzfe_p2": "ind_zzfe_p2",
        "zzfe_i1": "ind_zzfe_i1", "zzfe_i2": "ind_zzfe_i2",
        "zzfe_liq_state": "ind_zzfe_liq_state", "zzfe_state": "ind_zzfe_liq_state",
        "zzfe_liq_ref_high": "ind_zzfe_liq_ref_high", "zzfe_ref_high": "ind_zzfe_liq_ref_high",
        "zzfe_liq_ref_vol": "ind_zzfe_liq_ref_vol", "zzfe_ref_vol": "ind_zzfe_liq_ref_vol",
        "zzfe_liq_vol_ok": "ind_zzfe_liq_vol_ok", "zzfe_vol_ok": "ind_zzfe_liq_vol_ok",
        "zzfe_signal_s1": "ind_zzfe_signal_s1", "zzfe_signal_s2": "ind_zzfe_signal_s2",
        "zzfe_signal_s3": "ind_zzfe_signal_s3", "zzfe_signal_any": "ind_zzfe_signal_any",
        "zzfe_entry": "ind_zzfe_entry", "entry": "ind_zzfe_entry",
        "zzfe_entry_s1": "ind_zzfe_entry_s1", "zzfe_entry_s2": "ind_zzfe_entry_s2",
        "zzfe_entry_s3": "ind_zzfe_entry_s3",
        # ✅ ROUND32 (الترندية) — أعمدة المحرك المعزول الجديد (أسماء جديدة كلياً)
        "zzfet_dir": "ind_zzfet_dir", "zzfib_e2e_trendy_dir": "ind_zzfet_dir",
        "zzfet_p1": "ind_zzfet_p1", "zzfet_p2": "ind_zzfet_p2",
        "zzfet_i1": "ind_zzfet_i1", "zzfet_i2": "ind_zzfet_i2",
        "zzfet_anchor": "ind_zzfet_anchor", "zzfet_range_index": "ind_zzfet_range_index",
        "zzfet_liq_state": "ind_zzfet_liq_state", "zzfet_state": "ind_zzfet_liq_state",
        "zzfet_liq_ref_high": "ind_zzfet_liq_ref_high", "zzfet_ref_high": "ind_zzfet_liq_ref_high",
        "zzfet_liq_ref_vol": "ind_zzfet_liq_ref_vol", "zzfet_ref_vol": "ind_zzfet_liq_ref_vol",
        "zzfet_liq_vol_ok": "ind_zzfet_liq_vol_ok", "zzfet_vol_ok": "ind_zzfet_liq_vol_ok",
        "zzfet_signal_s1": "ind_zzfet_signal_s1", "zzfet_signal_s2": "ind_zzfet_signal_s2",
        "zzfet_signal_s3": "ind_zzfet_signal_s3", "zzfet_signal_any": "ind_zzfet_signal_any",
        "zzfet_entry": "ind_zzfet_entry",
        "zzfet_entry_raw": "ind_zzfet_entry_raw",
        "zzfet_entry_s1": "ind_zzfet_entry_s1", "zzfet_entry_s2": "ind_zzfet_entry_s2",
        "zzfet_entry_s3": "ind_zzfet_entry_s3",
        "zzfet_entry_raw_s1": "ind_zzfet_entry_raw_s1", "zzfet_entry_raw_s2": "ind_zzfet_entry_raw_s2",
        "zzfet_entry_raw_s3": "ind_zzfet_entry_raw_s3",
        "zzfet_entry_blocked_s1": "ind_zzfet_entry_blocked_s1", "zzfet_entry_blocked_s2": "ind_zzfet_entry_blocked_s2",
        "zzfet_entry_blocked_s3": "ind_zzfet_entry_blocked_s3",
        "zzfet_trend_ok": "ind_zzfet_trend_ok", "zzfet_trend_bias": "ind_zzfet_trend_bias",
        "zzfet_trend_votes_bull": "ind_zzfet_trend_votes_bull", "zzfet_trend_votes_bear": "ind_zzfet_trend_votes_bear",
        # ✅ ROUND32 (مؤشر الترند المستقل) — المجاميع والبوابة
        "trf_trend_ok": "ind_trf_trend_ok", "trf_bias": "ind_trf_bias",
        "trf_bull_votes": "ind_trf_bull_votes", "trf_bear_votes": "ind_trf_bear_votes",
        "trf_threshold": "ind_trf_threshold",
        "trf_cross_upper": "ind_trf_cross_upper", "trf_cross_lower": "ind_trf_cross_lower",
    }

    def _calculate_overlay_indicator(self, dataframe, config):
        """✅ الجولة 11 — جسر مؤشرات البنية إلى محرك الاستراتيجيات/الباك-تست.

        الأسماء المقبولة (غير حساسة لحالة الأحرف):
          zigzag | zigzag.zz_state | zigzag.zz_pivot_high | zigzag.zz_pivot_low
          fib | fib.signal | fib.fib_start | fib.fib_end | fib.fib_target
          trendline | trendline.signal | trendline.tl_upper | trendline.tl_lower
                    | trendline.tl_cross_upper | trendline.tl_cross_lower

        الاسم المجرد (بدون نقطة) يعيد عمود الإشارة الجاهز للشروط:
          zigzag:    +1 تأكيد قاع (شرائي) / -1 تأكيد قمة (بيعي) / 0 — عند شمعة التأكيد (بدون repaint)
          fib:       +1 Buy Retrace / -1 Sell Retrace / 0 — عند شمعة تحقق مستوى الإدارة
          trendline: +1 تقاطع صاعد فوق أي خط (اختراق العلوي أو استعادة السفلي) /
                     -1 تقاطع هابط تحت أي خط (فقدان السفلي أو العودة تحت العلوي) / 0

        يعيد None إن لم يكن الاسماً من أسماء البنية (لتمرّ للسجل الكلاسيكي كما هو).
        """
        try:
            raw_name = str((config or {}).get('name') or '')
            if not raw_name:
                return None
            parts = raw_name.split('.')
            base = self._OVERLAY_ALIASES.get(parts[0].strip().lower())
            if base is None:
                return None
            sub = parts[1].strip().lower() if len(parts) > 1 and parts[1].strip() else None
            params = dict((config or {}).get('params') or {})

            # استيراد مؤجل — compute_overlays نقية 100% وتقبل DataFrame مباشرة،
            # والأعمدة تُشتق من الوحدة المركزية overlay_columns (مصدر حقيقة واحد
            # للمحرك + الحاسبة + chart-data — مطابقة بايت-ببايت).
            from app.services.indicators.overlays import compute_overlays
            from app.services.indicators.overlay_columns import (
                columns_from_overlays_result,
                CONTRACT_COLUMNS,
            )

            idx = list(dataframe.index)

            if base == 'zigzag':
                kw = {}
                if 'length' in params:
                    kw['length'] = max(2, int(float(params['length'])))
            elif base == 'fib':
                kw = {}
                if 'depth' in params:
                    kw['depth'] = max(1, int(float(params['depth'])))
                for k in ('dev_threshold', 'dev', 'deviation', 'deviation_threshold'):
                    if k in params:
                        kw['dev_threshold'] = float(params[k])
                        break
                for k in ('retracement', 'ret', 'target_ratio'):
                    if k in params:
                        kw['retracement'] = float(params[k])
                        break
                for k in ('reverse', 'extend_left', 'extend_right'):
                    if k in params:
                        kw[k] = bool(params[k])
                lv = params.get('level_ratios', params.get('levels'))
                if isinstance(lv, (list, tuple)) and lv:
                    kw['level_ratios'] = [float(x) for x in lv]
            elif base == 'zzfib':
                # الجولة 12: فيبو الزيجزاق المدمج
                kw = {}
                if 'length' in params:
                    kw['length'] = max(2, int(float(params['length'])))
                if 'reverse' in params:
                    kw['reverse'] = bool(params['reverse'])
                lv = params.get('levels', params.get('level_ratios'))
                if isinstance(lv, (list, tuple)) and lv:
                    kw['levels'] = [float(x) for x in lv]
                for k in ('extend_right', 'extend_leg_to_live'):
                    if k in params:
                        kw[k] = bool(params[k])
                for k in ('touch_level', 'touch', 'target'):
                    if k in params:
                        kw['touch_level'] = float(params[k])
                        break
                # ✅ ROUND19: وضع زقزاق TradingView + معاملاته (mode/depth/deviation/
                # backstep) — كانت تُسقَط هنا بصمت فبقية المسار الحي يعمل luxalgo
                # رغم البريسِت. مُصلَح الآن في الجسور الثلاثة (calculator /
                # overlay_adapters / config_to_overlay_params) بذات الدلالة.
                if 'mode' in params:
                    kw['mode'] = str(params['mode']).strip().lower()
                _v = params.get('depth')
                if _v is not None:
                    try:
                        kw['depth'] = max(2, int(float(_v)))
                    except (TypeError, ValueError):
                        pass
                _v = params.get('deviation')
                if _v is not None:
                    try:
                        kw['deviation'] = float(_v)
                    except (TypeError, ValueError):
                        pass
                _v = params.get('backstep')
                if _v is not None:
                    try:
                        kw['backstep'] = max(1, int(float(_v)))
                    except (TypeError, ValueError):
                        pass
                # ✅ معاملات السيولة (الجولات 13.1/13.2) — كانت تمر عبر
                # config_to_overlay_params فقط؛ تُوحَّد هنا أيضاً (نفس القيم
                # كانت تسري كافتراضيات — الآن تُمرَّر حرفياً من أي بريسِت).
                _v = params.get('liq_lookback')
                if _v is not None:
                    try:
                        kw['liq_lookback'] = max(1, int(float(_v)))
                    except (TypeError, ValueError):
                        pass
                _v = params.get('liq_arm_bars')
                if _v is not None:
                    try:
                        kw['liq_arm_bars'] = max(1, int(float(_v)))
                    except (TypeError, ValueError):
                        pass
                if 'liq_signals' in params:
                    kw['liq_signals'] = bool(params['liq_signals'])
                if 'liq_sfp_signals' in params:
                    kw['liq_sfp_signals'] = bool(params['liq_sfp_signals'])
            elif base == 'zzfib_e2e':
                # ✅ ROUND22 (ZLF-End-To-End) — المحرك المنفصل: نفس معاملات الزقزاق
                # (+ launch_touch_ticks). لا liq_* — النطاق يعتمد لحظة ظهور الزقزاق
                # ونافذة الحساب = عمر النطاق (لا عدد شموع في التعريف).
                kw = {}
                if 'length' in params:
                    kw['length'] = max(2, int(float(params['length'])))
                if 'reverse' in params:
                    kw['reverse'] = bool(params['reverse'])
                lv = params.get('levels', params.get('level_ratios'))
                if isinstance(lv, (list, tuple)) and lv:
                    kw['levels'] = [float(x) for x in lv]
                for k in ('extend_right', 'extend_leg_to_live'):
                    if k in params:
                        kw[k] = bool(params[k])
                if 'mode' in params:
                    kw['mode'] = str(params['mode']).strip().lower()
                _v = params.get('depth')
                if _v is not None:
                    try:
                        kw['depth'] = max(2, int(float(_v)))
                    except (TypeError, ValueError):
                        pass
                _v = params.get('deviation')
                if _v is not None:
                    try:
                        kw['deviation'] = float(_v)
                    except (TypeError, ValueError):
                        pass
                _v = params.get('backstep')
                if _v is not None:
                    try:
                        kw['backstep'] = max(1, int(float(_v)))
                    except (TypeError, ValueError):
                        pass
                _v = params.get('launch_touch_ticks')
                if _v is not None:
                    try:
                        kw['launch_touch_ticks'] = float(_v)
                    except (TypeError, ValueError):
                        pass
            elif base == 'zzfib_e2e_trendy':
                # ✅ ROUND32 — الترندية: نفس معاملات E2E حرفياً + القوالب الترندية
                # الثلاثة (trend_periods قائمة بأي طول — إضافة ترند رابع = تعديل
                # القالب بلا أي كود — لا أرقام فترات داخل المنطق).
                kw = {}
                if 'length' in params:
                    kw['length'] = max(2, int(float(params['length'])))
                if 'reverse' in params:
                    kw['reverse'] = bool(params['reverse'])
                lv = params.get('levels', params.get('level_ratios'))
                if isinstance(lv, (list, tuple)) and lv:
                    kw['levels'] = [float(x) for x in lv]
                for k in ('extend_right', 'extend_leg_to_live'):
                    if k in params:
                        kw[k] = bool(params[k])
                if 'mode' in params:
                    kw['mode'] = str(params['mode']).strip().lower()
                _v = params.get('depth')
                if _v is not None:
                    try:
                        kw['depth'] = max(2, int(float(_v)))
                    except (TypeError, ValueError):
                        pass
                _v = params.get('deviation')
                if _v is not None:
                    try:
                        kw['deviation'] = float(_v)
                    except (TypeError, ValueError):
                        pass
                _v = params.get('backstep')
                if _v is not None:
                    try:
                        kw['backstep'] = max(1, int(float(_v)))
                    except (TypeError, ValueError):
                        pass
                _v = params.get('launch_touch_ticks')
                if _v is not None:
                    try:
                        kw['launch_touch_ticks'] = float(_v)
                    except (TypeError, ValueError):
                        pass
                _v = params.get('trend_periods', params.get('periods'))
                if _v is not None:
                    kw['trend_periods'] = _v
                if 'trend_confirm' in params:
                    kw['trend_confirm'] = params['trend_confirm']
                _v = params.get('trend_gate', params.get('gate'))
                if _v is not None:
                    kw['trend_gate'] = _v
            elif base == 'trend_fractal':
                # ✅ ROUND32 — مؤشر الترند المستقل: فترات قالبية بأي طول + الإجماع.
                kw = {}
                _v = params.get('periods', params.get('trend_periods'))
                if _v is not None:
                    kw['periods'] = _v
                if 'confirm_mode' in params:
                    kw['confirm_mode'] = params['confirm_mode']
            else:  # trendline
                kw = {}
                for k in ('period', 'n', 'fractal_period'):
                    if k in params:
                        kw['period'] = max(2, int(float(params[k])))
                        break
                for k in ('max_pairs', 'pairs', 'max_tl'):
                    if k in params:
                        kw['max_pairs'] = max(1, int(float(params[k])))
                        break
                if 'extend' in params:
                    kw['extend'] = str(params['extend'])

            res = compute_overlays(dataframe, types=[base], params={base: kw})
            cols = columns_from_overlays_result(res)
            primary = self._OVERLAY_PRIMARY[base]
            sub_used = primary
            if sub:
                sub_l = sub.strip().lower()
                col = None
                # الجولة 12: مستويات zzfib الديناميكية zzfib_level_<L> → ind_zzf_level_<L>
                if base == 'zzfib':
                    if sub_l.startswith('zzfib_level_'):
                        col = 'ind_zzf_level_' + sub_l[len('zzfib_level_'):]
                    elif sub_l.startswith('zzf_level_'):
                        col = 'ind_zzf_level_' + sub_l[len('zzf_level_'):]
                # ✅ ROUND22: مستويات المحرك المنفصل zzfe_level_<L> → ind_zzfe_level_<L>
                if base == 'zzfib_e2e':
                    if sub_l.startswith('zzfe_level_'):
                        col = 'ind_zzfe_level_' + sub_l[len('zzfe_level_'):]
                    elif sub_l.startswith('zzfib_e2e_level_'):
                        col = 'ind_zzfe_level_' + sub_l[len('zzfib_e2e_level_'):]
                # ✅ ROUND32: أي اسم فرعي من عائلة الترندية/الترند يُحل بالقاعدة العامة
                # (سلسلة zzfet_X/trf_X → عمود ind_zzfet_X/ind_trf_X — يشمل مستويات
                # zzfet_level_<L> ومرايا الفترات zzfet_tr_p{n}_* وأعمدة trf_p{n}_*).
                if base in ('zzfib_e2e_trendy', 'trend_fractal'):
                    if sub_l.startswith('zzfet_') or sub_l.startswith('trf_'):
                        col = 'ind_' + sub_l
                    elif base == 'zzfib_e2e_trendy' and sub_l.startswith('zigzag_fib_e2e_trendy_'):
                        col = 'ind_' + sub_l[len('zigzag_fib_e2e_trendy_'):]
                if col is None:
                    col = self._OVERLAY_SUB_COLUMNS.get(sub_l)
                if col and col != 'primary':
                    sub_used = col
            data = cols.get(sub_used)
            if data is None:
                data = cols.get(primary) or [None] * len(dataframe)
                sub_used = primary
            desc = ('أعمدة العقد الملزم: ' + ', '.join(CONTRACT_COLUMNS.get(base) or [])
                    + ' — الأساسي هنا: ' + primary)

            return {
                "name": raw_name,
                "values": {"data": data, "index": idx, "dtype": "object"},
                "signals": None,
                "metadata": {
                    "overlay": base,
                    "sub": sub_used,
                    "params": kw,
                    "available_columns": sorted(cols.keys()),
                    "description": desc,
                    "engine": "overlays_v2 (الجولة 11)",
                },
            }
        except Exception:
            # لا نبتلع بصمت: نطبع التتبع ونعيد None ليمر الاسم للسجل الكلاسيكي
            # (الذي سيعيد نتيجة الخطأ المعتادة — نفس سلوك الإصدارات السابقة).
            import logging as _logging
            _logging.getLogger(__name__).exception(
                "Overlay bridge failed for '%s' — falling back to registry",
                (config or {}).get('name'),
            )
            return None

    @staticmethod
    def _overlay_available_subs(base: str):
        from app.services.indicators.overlay_columns import CONTRACT_COLUMNS
        return list(CONTRACT_COLUMNS.get(base) or [])

    @staticmethod
    def _zigzag_signal_from_state(state):
        """+1 عند تأكيد قاع (انتقال 0→1)، -1 عند تأكيد قمة (1→0)، وإلا 0.

        مطابق لمنطق Pine: top = os==0 and os[1]!=0 / btm = os==1 and os[1]!=1.
        الإشارة توضع على شمعة التأكيد نفسها — بلا repaint.
        """
        out = [0.0] * len(state)
        prev = None
        for i, v in enumerate(state):
            if v is None:
                continue
            if prev is not None:
                if v == 1 and prev == 0:
                    out[i] = 1.0
                elif v == 0 and prev == 1:
                    out[i] = -1.0
            prev = v
        return out, 'signal'

    @staticmethod
    def _fib_signal_from_events(signals, n_bars: int):
        """+1 عند شمعة Buy Retrace، -1 عند شمعة Sell Retrace، وإلا 0."""
        out = [0.0] * n_bars
        for ev in signals or []:
            try:
                bar = int(ev.get('bar'))
            except (TypeError, ValueError):
                continue
            if not (0 <= bar < n_bars):
                continue
            side = str(ev.get('side') or '').strip().lower()
            sig = str(ev.get('signal') or '').strip().lower()
            if side == 'buy' or sig.startswith('buy'):
                out[bar] = 1.0
            elif side == 'sell' or sig.startswith('sell'):
                out[bar] = -1.0
        return out, 'signal'

    @staticmethod
    def _trendline_signal_from_crosses(crosses, n_bars: int):
        """+1 تقاطع صاعد (over فوق أي خط)، -1 تقاطع هابط (under تحت أي خط)، وإلا 0.

        over فوق الخط العلوي = اختراق مقاومة الاتجاه (شرائي)؛
        over فوق الخط السفلي = استعادة دعم الاتجاه (شرائي)؛
        under تحت الخط السفلي = كسر الدعم (بيعي)؛
        under تحت الخط العلوي = رجوع تحت مقاومة الاتجاه (بيعي).
        """
        out = [0.0] * n_bars
        for cr in crosses or []:
            try:
                bar = int(cr.get('bar'))
            except (TypeError, ValueError):
                continue
            if not (0 <= bar < n_bars):
                continue
            direction = str(cr.get('direction') or '').strip().lower()
            if direction == 'over':
                out[bar] += 1.0
            elif direction == 'under':
                out[bar] -= 1.0
        return [max(-1.0, min(1.0, v)) for v in out], 'signal'

    def _calculate_single_indicator(self, dataframe, config, use_cache):
        import pandas as pd
        import numpy as np

        if callable(dataframe):
            raise ValueError(f"Expected a DataFrame, got callable: {dataframe}")

        if not isinstance(dataframe, pd.DataFrame):
            raise ValueError(f"Expected a DataFrame, got {type(dataframe)}")

        name = config.get('name', 'unknown')
        cache_key = self._generate_cache_key(dataframe, config)

        if use_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return name, cached

        # ✅ الجولة 11: جسر مؤشرات البنية (zigzag/fib/trendline) — تُحسب مباشرة
        # من app/services/indicators/overlays.py بدل السجل الكلاسيكي الذي لا يعرفها.
        # هذا يُصلح: "Indicator 'fib' not found in registry" في strategies1/run والباك-تست.
        overlay_result = self._calculate_overlay_indicator(dataframe, config)
        if overlay_result is not None:
            if use_cache:
                self._cache_set(cache_key, overlay_result)
            return name, overlay_result

        try:
            # ✅ الجولة 5: طبّع النوع الفاسد الوارد من العملاء (مثل "oscillator")
            # قبل pydantic — بدل فشل الحساب كل نبضة وإرجاع قيم NaN للفرونت.
            config = sanitize_indicator_config(config)
            indicator_config = IndicatorConfig(**config)
            indicator = self.registry.create_indicator(indicator_config)
            result = indicator.calculate(dataframe)
            result_dict = result.to_dict()
            if use_cache:
                self._cache_set(cache_key, result_dict)
            return name, result_dict
        except Exception as e:
            # ⚠️ لا نبتلع الخطأ بصمت — كان هذا يخفي أعطالاً حقيقية (مثل فشل
            # IndicatorConfig) وجعل كل قيم المؤشرات ترجع NaN دون أي تتبع
            import logging as _logging

            _logging.getLogger(__name__).exception(
                "Indicator '%s' failed to calculate: %s", name, e
            )
            return name, {
                "name": name,
                "values": {"data": [np.nan] * len(dataframe), "index": list(dataframe.index), "dtype": "float64"},
                "signals": None,
                "metadata": {"error": str(e)},
            }


    # def apply_indicators(
    #     self,
    #     dataframe: pd.DataFrame,
    #     indicators_config: List[Dict[str, Any]],  # استخدام Dict مباشرة
    #     use_cache: bool = True,
    #     parallel: bool = False  # ✅ إضافة خيار parallel
    # ) -> Dict[str, Dict[str, Any]]:

    #     results = {}

   
    #     if parallel:
    #         with ThreadPoolExecutor() as executor:
    #             futures = [
    #                 executor.submit(self._calculate_single_indicator, dataframe, cfg, use_cache)
    #                 for cfg in indicators_config if cfg.get('enabled', True)
    #             ]
    #             for future in futures:
    #                 name, res = future.result()
    #                 # تنظيف النتيجة
    #                 results[name] = self._clean_indicator_result(res)
    #     else:
    #         # التشغيل المتسلسل
            
    #         for cfg in indicators_config:
    #             if not cfg.get('enabled', True):
    #                 continue
    #             name, res = self._calculate_single_indicator(dataframe, cfg, use_cache)
    #             # تنظيف النتيجة
    #             results[name] = self._clean_indicator_result(res)

    #     return results  # ✅ إرجاع results هنا


    def apply_indicators(
        self,
        dataframe: pd.DataFrame,
        indicators_config: List[Dict[str, Any]],  # استخدام Dict مباشرة
        use_cache: bool = True,
        parallel: bool = False  # ✅ إضافة خيار parallel
    ) -> Dict[str, Dict[str, Any]]:

        results = {}

        has_ids = any(cfg.get('id') for cfg in indicators_config)



        if parallel:
            # ✅ تعديل الـ Parallel ليدعم IDs
            with ThreadPoolExecutor() as executor:
                futures = []
                
                # نقوم بتخزين الـ config مع الـ future لاسترجاعته لاحقاً
                for cfg in indicators_config:
                    if cfg.get('enabled', True):
                        future = executor.submit(self._calculate_single_indicator, dataframe, cfg, use_cache)
                        futures.append((future, cfg)) # <--- تخزين الـ Config مع الـ Future

                for future, original_cfg in futures:
                    # نستقبل النتيجة
                    name, res = future.result()
                    
                    # ✅ تحديد المفتاح باستخدام الـ original_cfg (وليس المتغير name)
                    if original_cfg.get('id'):
                        unique_key = original_cfg.get('id')
                       
                    elif original_cfg.get('label'):
                        unique_key = original_cfg.get('label')
                    else:
                        unique_key = name
                

                    results[unique_key] = self._clean_indicator_result(res)


        # if parallel:
        #     with ThreadPoolExecutor() as executor:
        #         futures = [
        #             executor.submit(self._calculate_single_indicator, dataframe, cfg, use_cache)
        #             for cfg in indicators_config if cfg.get('enabled', False)
        #         ]


        #         for future in futures:
        #             name, res = future.result()
        #             # تنظيف النتيجة
        #             # results[name] = self._clean_indicator_result(res)
        #             pass
        else:
   
            for i, cfg in enumerate(indicators_config):
                if not cfg.get('enabled', True):
                    continue

                name, res = self._calculate_single_indicator(dataframe, cfg, use_cache)
                
                if cfg.get('id'):
                    unique_key = cfg.get('id')

                elif cfg.get('label'): # دعم الـ label من الـ JSON
                    unique_key = cfg.get('label')
                 
                else:
                    unique_key = name
        

                # تنظيف النتيجة
                results[unique_key] = self._clean_indicator_result(res)


        return results  # ✅ إرجاع results هنا



    
    def _clean_indicator_result(self, result):
      
        if isinstance(result, dict):
           
            return self._clean_dict(result)
        elif isinstance(result, pd.Series):
            return self._clean_series(result)
        elif isinstance(result, pd.DataFrame):
            return self._clean_dataframe(result)
        elif isinstance(result, (list, tuple)):
            return [self._clean_value(v) for v in result]
        elif isinstance(result, np.ndarray):
            return [self._clean_value(v) for v in result.tolist()]
        else:
            return self._clean_value(result)
    
    def _clean_value(self, val):
        """تنظيف قيمة واحدة"""
        if val is None:
            return None
        elif isinstance(val, (float, np.float32, np.float64)):
            if np.isinf(val) or np.isnan(val):
                return None
            # تقريب لتجنب أرقام الفاصلة العائمة الكبيرة جدًا
            if abs(val) > 1e308:  # تجاوز الحد الأقصى لـ JSON
                return None
            return round(float(val), 8)
        elif isinstance(val, (np.int32, np.int64, np.integer)):
            return int(val)
        elif isinstance(val, (pd.Timestamp, pd.DatetimeIndex)):
            return val.isoformat() if hasattr(val, 'isoformat') else str(val)
        else:
            return val
    
    def _clean_series(self, series: pd.Series):
        """تنظيف Series"""
        if series is None or series.empty:
            return []
        
        cleaned = []
        for val in series.tolist():
            cleaned.append(self._clean_value(val))
        return cleaned
    
    def _clean_dataframe(self, df: pd.DataFrame):
        """تنظيف DataFrame"""
        if df is None or df.empty:
            return []
        
        records = []
        for _, row in df.iterrows():
            record = {}
            for col in row.index:
                record[col] = self._clean_value(row[col])
            records.append(record)
        return records
    
    def _clean_dict(self, d: Dict):
        """تنظيف قاموس"""
        if not d:
            return {}
        
        cleaned = {}
        for key, value in d.items():
            cleaned[key] = self._clean_indicator_result(value)  # ✅ تنظيف متكرر
        return cleaned
    
    def calculate_trading_signals(
        self,
        dataframe: pd.DataFrame,
        indicator_configs: List[Dict[str, Any]],
        signal_threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        توليد إشارات تداول من مجموعة مؤشرات
        
        Args:
            dataframe: البيانات
            indicator_configs: تكوينات المؤشرات
            signal_threshold: عتبة الإشارة
            
        Returns:
            Dict: إشارات التداول والبيانات التحليلية
        """
        # حساب جميع المؤشرات
        indicator_results = self.apply_indicators(
            dataframe, 
            indicator_configs, 
            use_cache=True
        )
        
        # استخراج الإشارات من النتائج
        signals_series = self._extract_signals(indicator_results, dataframe)
        
        # تحليل الإشارات
        signal_analysis = self._analyze_signals(signals_series, dataframe)
        
        # تنظيف النتائج
        clean_signals = self._clean_series(signals_series) if hasattr(signals_series, 'tolist') else []
        clean_analysis = self._clean_dict(signal_analysis) if signal_analysis else {}
        clean_indicators = self._clean_dict(indicator_results)
        
        # تجميع النتائج
        result = {
            "signals": clean_signals,
            "signal_analysis": clean_analysis,
            "indicators": clean_indicators,
            "last_signal": 0 if not clean_signals else int(clean_signals[-1]) if clean_signals else 0,
            "signal_strength": 0 if not clean_signals else abs(float(clean_signals[-1])) if clean_signals else 0
        }
        
        return result
    
    def _extract_signals(
        self, 
        indicator_results: Dict[str, Dict[str, Any]], 
        dataframe: pd.DataFrame
    ) -> pd.Series:
        """استخراج إشارات من نتائج المؤشرات"""
        if not indicator_results:
            return pd.Series([0] * len(dataframe), index=dataframe.index)
        
        # جمع الإشارات من جميع المؤشرات
        combined = pd.Series(0, index=dataframe.index)
        
        for name, result in indicator_results.items():
            if 'signals' in result and result['signals'] is not None:
                signals = pd.Series(result['signals'], index=dataframe.index)
                # تطبيع وجمع
                if not signals.empty:
                    signals_normalized = signals.fillna(0)
                    combined = combined.add(signals_normalized, fill_value=0)
        
        # تحويل إلى إشارات منفصلة
        discrete = pd.Series(0, index=combined.index)
        discrete[combined > 0.3] = 1
        discrete[combined < -0.3] = -1
        
        return discrete
    
    def _analyze_signals(
        self, 
        signals: pd.Series, 
        dataframe: pd.DataFrame
    ) -> Dict[str, Any]:
        """تحليل إشارات التداول"""
        if len(signals) == 0:
            return {}
        
        # تحليل الإشارات
        buy_signals = (signals == 1).sum()
        sell_signals = (signals == -1).sum()
        neutral_signals = (signals == 0).sum()
        
        total_signals = len(signals)
        
        # اتجاه الإشارات الأخيرة
        recent_signals = signals.iloc[-10:] if len(signals) >= 10 else signals
        signal_trend = "neutral"
        
        if len(recent_signals) > 0:
            buy_count = (recent_signals == 1).sum()
            sell_count = (recent_signals == -1).sum()
            
            if buy_count > sell_count:
                signal_trend = "bullish"
            elif sell_count > buy_count:
                signal_trend = "bearish"
        
        return {
            "buy_signals": int(buy_signals),
            "sell_signals": int(sell_signals),
            "neutral_signals": int(neutral_signals),
            "total_signals": int(total_signals),
            "buy_percentage": float(buy_signals / total_signals * 100) if total_signals > 0 else 0,
            "sell_percentage": float(sell_signals / total_signals * 100) if total_signals > 0 else 0,
            "signal_trend": signal_trend,
            "last_signal": int(signals.iloc[-1]) if len(signals) > 0 else 0
        }
    
    def _generate_cache_key(
        self, 
        dataframe: pd.DataFrame, 
        config: Dict[str, Any]
    ) -> str:
        """إنشاء مفتاح كاش فريد"""
        # استخدام هاش DataFrame والتكوين
        data_hash = hash(str(dataframe.iloc[-100:].to_dict()))
        config_hash = hash(str(config))
        
        return f"indicator_{config.get('name', 'unknown')}_{data_hash}_{config_hash}"
    
    def validate_dataframe(self, dataframe: pd.DataFrame) -> bool:
        """التحقق من صحة DataFrame"""
        required_columns = ['open', 'high', 'low', 'close']
        
        if dataframe is None or dataframe.empty:
            return False
        
        for col in required_columns:
            if col not in dataframe.columns:
                return False
        
        # التحقق من وجود قيم NaN
        if dataframe[required_columns].isnull().any().any():
            return False
        
        return True


