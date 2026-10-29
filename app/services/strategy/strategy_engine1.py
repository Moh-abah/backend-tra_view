from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import datetime
import pandas as pd
import numpy as np
import logging

# استيراد التكوين والأدوات المساعدة للتفكير فقط
from .schemas import (
    StrategyConfig, Condition, CompositeCondition, PositionSide
)
from .conditions import ConditionEvaluator
from app.services.indicators import apply_indicators

logger = logging.getLogger(__name__)

class DecisionAction(Enum):
    """الأفعال المجردة التي يمكن للقرار اتخاذها"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"

@dataclass
class Decision:
    timestamp: datetime
    action: DecisionAction
    confidence: float
    reason: str
    metadata: Dict[str, Any] = None

class StrategyEngine:
    """
    محرك الاستراتيجية (Decision Provider)
    يستخدم منطق استخراج البيانات الموثق من النسخة السابقة.
    """
    
    def __init__(self, strategy_config: StrategyConfig):
        self.config = strategy_config
        self.condition_evaluator = ConditionEvaluator()
        self.current_data_frame = None
        self.full_data = None
        # ✅ كاش قاموس المؤشرات: بناؤه كان يتم داخل _evaluate_rule_condition
        # في كل تقييم/شمعة (تكرار كل أعمدة الـ DataFrame) — الآن مرة واحدة لكل
        # مجموعة بيانات (فحص هوية مثل full_data).
        self._ind_dict_cache_data = None
        self._ind_dict_cache: Dict[str, Any] = {}

    # async def run(self, market_context: pd.DataFrame) -> Decision:
    #     if market_context.empty or len(market_context) < 2:
    #         return self._create_hold_decision("Insufficient data")

    #     try:
    #         # 1. تحضير البيانات باستخدام المنطق القديم (القوي)
    #         df_clean = await self._prepare_indicators(market_context)
    #         self.current_data_frame = df_clean
            
    #         # 2. عملية التفكير
    #         current_index = len(df_clean) - 1


 
            
    #         # التحقق من شروط الخروج
    #         exit_reason = self._check_exit_conditions(df_clean, current_index)
    #         if exit_reason:
    #             return Decision(
    #                 timestamp=df_clean.index[current_index],
    #                 action=DecisionAction.HOLD,
    #                 confidence=1.0,
    #                 reason=f"Exit Condition: {exit_reason}",
    #                 metadata={"trigger": "exit_rule"}
    #             )
            
    #         # التحقق من شروط الدخول
    #         decision = self._determine_trend(df_clean, current_index)
    #         return decision

    #     except Exception as e:
    #         logger.exception(f"Strategy Engine Error: {e}")
    #         return self._create_hold_decision(f"Error: {str(e)}")





    async def run(self, market_context: pd.DataFrame, current_index: int = None, in_position: bool = False) -> Decision:
        if market_context.empty or len(market_context) < 2:
            return self._create_hold_decision("Insufficient data")

        try:
            # 1. تحضير البيانات باستخدام المنطق القديم (القوي)
            df_clean = await self._prepare_indicators(market_context)
            self.current_data_frame = df_clean
            # ✅ إصلاح أداء جوهري: كان run() لا يخزن النتيجة في full_data
            # فتُعاد حساب كل المؤشرات من الصفر مع كل قرار (~50ms بدل ~1ms)
            # والفحص الهووي في _prepare_indicators لا يُصيب أبداً.
            self.full_data = df_clean
            
            # 2. عملية التفكير
       


            if current_index is not None:
                idx = current_index
            else:
                idx = len(df_clean) - 1
            
 
            
            # التحقق من شروط الخروج — فقط عندما يوجد مركز مفتوح فعلاً
            # ✅ إصلاح: كان يُفحص الخروج حتى بدون مركز (NEUTRAL) فيُحجب تقييم
            # الدخول نهائياً عندما يبقى شرط الخروج صحيحاً (RSI=100 مثلاً)
            if in_position:
                exit_reason = self._check_exit_conditions(df_clean, idx)
                if exit_reason:
                    return Decision(
                        timestamp=df_clean.index[idx],
                        action=DecisionAction.HOLD,
                        confidence=1.0,
                        reason=f"Exit Condition: {exit_reason}",
                        metadata={"trigger": "exit_rule"}
                    )
            
            # التحقق من شروط الدخول
            decision = self._determine_trend(df_clean, idx)
            return decision

        except Exception as e:
            logger.exception(f"Strategy Engine Error: {e}")
            return self._create_hold_decision(f"Error: {str(e)}")




    # async def _prepare_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
    #     """
    #     إعداد المؤشرات.
    #     تم تعديل هذه الدالة لاستخدام منطق الاستخراج من الكود السابق (core.py)
    #     لأنه الأكثر ثباتاً.
    #     """
    #     try:


    #         all_indicators = apply_indicators(
    #             dataframe=data,
    #             indicators_config=self.config.indicators,
    #             use_cache=False,
    #             return_raw=True
    #         )

    #         # إنشاء نسخة من البيانات لإضافة المؤشرات إليها
    #         # df = data.copy()
    #         df = data.copy(deep=False)
            
    #         # ==========================================
    #         # ✅ بداية التعديل (دعم ID و Label)
    #         # ==========================================
            
    #         # بدلاً من جلب الأسماء فقط ({cfg.name})، سنقوم بجلب "المفاتيح"
    #         # سنستخدم set لتجنب التكرار من البداية



    #         required_keys = set()

    #         for cfg in self.config.indicators:
    #             # 1. نحاول جلب الـ ID (المعرف الجديد والفريد)
    #             target_key = getattr(cfg, 'id', None)
                
    #             # 2. إذا لم يوجد ID، نحاول جلب الـ label
    #             if not target_key:
    #                 target_key = getattr(cfg, 'label', None)
                
    #             # 3. إذا لم يوجد ID ولا label، نعود للاسم (للنظام القديم)
    #             if not target_key:
    #                 target_key = getattr(cfg, 'name', 'unknown')
                
    #             required_keys.add(target_key)
            
    #         # تحويل المجموعة إلى قائمة (نفس اسم المتغير عندك لضمان استمرار الكود)
    #         required_indicators = list(required_keys)
            
    #         # ==========================================
    #         # نهاية التعديل
    #         # ==========================================
            
    #         # جلب مؤشرات القواعد أيضاً (كما هو في كودك)
    #         for rule in self.config.entry_rules + self.config.exit_rules + self.config.filter_rules:
    #             condition = rule.condition
    #             conditions_list = [condition]
    #             if isinstance(condition, CompositeCondition):
    #                 conditions_list = condition.conditions
    #             for cond in conditions_list:
    #                 for val in [cond.left_value, cond.right_value]:
    #                     if isinstance(val, str) and val.startswith("indicator:"):
    #                         indicator_ref = val.split(":")[1]
    #                         required_indicators.append(indicator_ref)

    #         # إزالة التكرار (بسبب الإضافة في القواعد)
    #         required_indicators = list(set(required_indicators))

    #         # حلقة المعالجة (منطقك الأصلي - لم يتم لمسه)
    #         for ind_name in required_indicators:
    #             raw_values: list = [None] * len(data)
                

                    
    #             is_found = ind_name in all_indicators
          

    #             if ind_name in all_indicators:
    #                 result = all_indicators[ind_name]
                                    


               

    #                 if isinstance(result, dict) and 'metadata' in result and 'render' in result['metadata']:
                      
    #                     df.attrs[f'{ind_name}_render'] = result['metadata']['render']
                

    #                 if isinstance(result, dict):
    #                     # محاولة استخراج القائمة من المسارات المتعددة (كما في كودك السابق)
    #                     raw_values = result.get("values", {}).get("data", [None])
                        
    #                     # إذا لم تكن قائمة، نحاول استخراجها بطريقة أخرى
    #                     if not isinstance(raw_values, list):
    #                          raw_values = result.get("data", [None])
                             
    #                 elif isinstance(result, list):
    #                     raw_values = result
    #                 elif isinstance(result, pd.Series):
    #                     raw_values = result.tolist()


    #             else:
    #                 # لم يتم العثور عليه -> سيكون العمود NaN

    #                 pass

                
    #             # Padding لضمان تطابق الطول (منطقك الأصلي)
    #             padding_len = max(0, len(data) - len(raw_values))
    #             series_values = [None] * padding_len + raw_values[:len(data)]
                
    #             # إضافة العمود للـ DataFrame (منطقك الأصلي)
    #             # بما أننا غيرنا المفتاح في الأعلى ليكون (ID أو Name)، فإن df[ind_name] سيكون صحيحاً في الحالتين
    #             df[ind_name] = pd.Series(series_values, index=data.index)




    #     # ==================== Feature Engineering Loop (دعم تعدد المؤشرات والـ ID) ====================
            
    #         # 1. جلب جميع مؤشرات Volume Climax المفعلة (بدلاً من الأول فقط)
    #         vc_configs_list = [x for x in self.config.indicators if x.name == 'volume_climax' and x.enabled]

    #         # 2. دالة مساعدة موحدة لحساب التكرار المتتالي (Streak)
    #         def calculate_streak(mask):
    #             # تحديد بداية المجموعات كلما تغيرت الحالة
    #             groups = (mask != mask.shift()).cumsum()
    #             # حساب الترقيم المتتالي داخل كل مجموعة
    #             streak = mask.groupby(groups).cumsum()
    #             # تصفير القيم في الأماكن التي لم يتحقق فيها الشرط
    #             return streak.where(mask, 0)

    #         # 3. التحقق من توفر بيانات الشموع الأساسية
    #         has_candle_data = 'close' in df.columns and 'open' in df.columns
            
    #         # 4. معالجة كل مؤشر Volume Climax على حدة
    #         for vc_config in vc_configs_list:
                
    #             # --- تحديد المفتاح (ID أو Name) ---
    #             prefix = getattr(vc_config, 'id', None)
    #             if not prefix:
    #                 prefix = getattr(vc_config, 'label', None)
    #             if not prefix:
    #                 prefix = vc_config.name # الرجوع للاسم
                
    #             # التحقق من وجود البيانات في الـ DataFrame (Fallback للاسم إذا كان الـ ID غير موجود)
    #             active_data_key = prefix
    #             if prefix not in df.columns and vc_config.name in df.columns:
    #                 active_data_key = vc_config.name
                
    #             if active_data_key not in df.columns:
    #                 continue # تجاوز إذا لم توجد بيانات

    #             # --- أ) حساب Volume Streaks ---
    #             params = vc_config.params
    #             ratio_low = params.get('ratio_low', 0.4)
    #             ratio_normal = params.get('ratio_normal', 0.8)
    #             ratio_very_high = params.get('ratio_very_high', 1.8)
                
    #             vc_series = df[active_data_key]
                
    #             is_blue = (vc_series >= ratio_low) & (vc_series < ratio_normal)
    #             is_red = (vc_series >= ratio_very_high)
                
    #             # ✅ إنشاء الأعمدة باستخدام `:` لتتوافق مع القواعد (مثال: vc5:vc_blue_streak)
    #             df[f'{prefix}:vc_blue_streak'] = calculate_streak(is_blue)
    #             df[f'{prefix}:vc_red_streak'] = calculate_streak(is_red)

    #             # --- ب) حساب Candle Streaks (مرتبط بـ ID المؤشر) ---
    #             # ملاحظة: حساب الشموع يعتمد على بيانات الإطار الزمني الحالي للـ DataFrame
    #             if has_candle_data:
    #                 is_bull = (df['close'] > df['open'])
    #                 is_bear = (df['close'] < df['open'])
                    
    #                 # ✅ إنشاء أعمدة الشموع بنفس البادئة (مثال: vc5:green_candle_streak)
    #                 df[f'{prefix}:green_candle_streak'] = calculate_streak(is_bull)
    #                 df[f'{prefix}:red_candle_streak'] = calculate_streak(is_bear)
                
    #             # --- ج) معالجة Render (Volume Bars & Climax Points) ---
    #             # جلب بيانات الـ render الخاصة بهذا المؤشر فقط
    #             # (تم تخزينها في الحلقة السابقة باستخدام df.attrs[f'{ind_name}_render'])
    #             vc_render = df.attrs.get(f'{active_data_key}_render', {})
                
    #             # محاولة بديلة بالاسم إذا لم يتم العثور عليها بالمفتاح النشط
    #             if not vc_render:
    #                 vc_render = df.attrs.get(f'{vc_config.name}_render', {})

    #             vb_list = vc_render.get('volume_bars', []) or []
    #             cp_list = vc_render.get('climax_points', []) or []

    #             # دالة مساعدة للوقت
    #             def _parse_time(t):
    #                 try:
    #                     if isinstance(t, (int, float)):
    #                         try:
    #                             return pd.to_datetime(int(t), unit='ms', utc=True)
    #                         except Exception:
    #                             return pd.to_datetime(int(t), unit='s', utc=True)
    #                     return pd.to_datetime(t, utc=True)
    #                 except Exception:
    #                     return None

    #             vb_map = {}
    #             for v in vb_list:
    #                 t = _parse_time(v.get('time'))
    #                 if t is not None:
    #                     vb_map[pd.Timestamp(t)] = {
    #                         'time': pd.Timestamp(t),
    #                         'value': (float(v.get('value')) if v.get('value') is not None else None),
    #                         'ratio': (float(v.get('ratio')) if v.get('ratio') is not None else None),
    #                         'color': v.get('color')
    #                     }

    #             cp_map = {}
    #             for c in cp_list:
    #                 t = _parse_time(c.get('time'))
    #                 if t is not None:
    #                     cp_map[pd.Timestamp(t)] = {
    #                         'time': pd.Timestamp(t),
    #                         'high': (float(c.get('high')) if c.get('high') is not None else None),
    #                         'low': (float(c.get('low')) if c.get('low') is not None else None),
    #                         'ratio': (float(c.get('ratio')) if c.get('ratio') is not None else None),
    #                         'color': c.get('color')
    #                     }

    #             vol_bar_col = []
    #             climax_col = []
    #             for ts in df.index:
    #                 tkey = pd.Timestamp(ts)
    #                 vb = vb_map.get(tkey)
    #                 cp = cp_map.get(tkey)
    #                 vol_bar_col.append(vb if vb else None)
    #                 climax_col.append(cp if cp else None)

    #             # ✅ إنشاء أعمدة الـ Render بالبادئة (مثال: vc5:ind_volume_bar)
    #             df[f'{prefix}:ind_volume_bar'] = pd.Series(vol_bar_col, index=df.index)
    #             df[f'{prefix}:ind_climax_points'] = pd.Series(climax_col, index=df.index)

    #         # ============================================================
    #         # ✅ التعديل الجذري: استخراج وتسوية بيانات SMC (يدعم الـ ID المخصص)
    #         # ============================================================


    #  # ============================================================
    #         # ✅ التعديل الجذري: استخراج وتسوية بيانات SMC (يدعم الـ ID المخصص)
    #         # ============================================================
            
    #         # 1. البحث عن إعدادات مؤشر SMC في القائمة للحصول على الـ ID والاسم
    #         smc_config = next((cfg for cfg in self.config.indicators if cfg.name == 'smc_order_block'), None)
            
    #         smc_metadata = {}
    #         col_prefix = 'smc_order_block' # القيمة الافتراضية
            
    #         # 2. تحديد المفتاح (Key) الذي سيتم استخدامه
    #         # نعطي الأولوية للـ ID كما في الطلب (s123k)، ثم الاسم
    #         lookup_key = None
            
    #         if smc_config:
    #             # محاولة استخدام ID
    #             if hasattr(smc_config, 'id') and smc_config.id:
    #                 lookup_key = smc_config.id
    #                 col_prefix = smc_config.id # استخدام الـ ID كبادئة للأعمدة
                
    #             # إذا لم يتم العثور على البيانات بالـ ID في all_indicators، نحاول بالاسم
    #             if lookup_key and lookup_key not in all_indicators:
    #                  if smc_config.name in all_indicators:
    #                      lookup_key = smc_config.name
    #                      col_prefix = smc_config.name
            
    #         # 3. جلب البيانات والميتاداتا بناءً على المفتاح المحدد
    #         if lookup_key and lookup_key in all_indicators:
    #             result = all_indicators[lookup_key]
                
    #             # التعامل مع Dict
    #             if isinstance(result, dict) and 'metadata' in result:
    #                 smc_metadata = result['metadata']
    #             # التعامل مع Object
    #             elif hasattr(result, 'metadata') and result.metadata is not None:
    #                 meta = result.metadata
    #                 if isinstance(meta, dict) and 'order_blocks' in meta:
    #                     smc_metadata = meta
    #                 elif hasattr(meta, 'get') and 'order_blocks' in meta:
    #                     smc_metadata = meta

    #             # حفظ الميتاداتا في attrs للاستخدام اللاحق إذا لزم الأمر
    #             if smc_metadata:
    #                 df.attrs['smc_metadata'] = smc_metadata

    #         # 4. معالجة الميتاداتا إذا وجدت (المنطق الأصلي)
    #         if smc_metadata:
    #             obs_list = smc_metadata.get('order_blocks', [])
                
    #             # ✅ 1. تحديد خصائص توقيت الشموع
    #             df_tz = df.index.tz
                
    #             valid_obs = []

    #             # ✅ 2. المعالجة المسبقة (Pre-processing) للمناطق
    #             for ob in obs_list:
    #                 t_from = ob.get('time_from')
    #                 t_to = ob.get('time_to')
                    
    #                 if t_from is None:
    #                     continue

    #                 # التحويل من ثواني (Unix Timestamp) إلى Pandas Timestamp
    #                 dt_from = pd.to_datetime(t_from, unit='s')
                    
    #                 # ✅ 3. مواءمة التوقيت (Sync Timezone)
    #                 if df_tz is not None:
    #                     if dt_from.tz is None:
    #                         dt_from = dt_from.tz_localize('UTC').tz_convert(df_tz)
    #                     else:
    #                         dt_from = dt_from.tz_convert(df_tz)
                    
    #                 if pd.isna(t_to):
    #                     dt_to = df.index[-1] + pd.Timedelta(days=1)
    #                 else:
    #                     dt_to = pd.to_datetime(t_to, unit='s')
    #                     if df_tz is not None:
    #                         if dt_to.tz is None:
    #                             dt_to = dt_to.tz_localize('UTC').tz_convert(df_tz)
    #                         else:
    #                             dt_to = dt_to.tz_convert(df_tz)

    #                 ob['_dt_from'] = dt_from
    #                 ob['_dt_to'] = dt_to
    #                 valid_obs.append(ob)

    #             # ✅ 4. إنشاء الأعمدة باستخدام البادئة الديناميكية (col_prefix)
    #             # بدلاً من الترميز الثابت 'smc_order_block'، نستخدم المتغير col_prefix الذي يحمل القيمة 's123k'
                
    #             df[f'{col_prefix}:bullish_zone_top'] = np.nan
    #             df[f'{col_prefix}:bullish_zone_bottom'] = np.nan
    #             df[f'{col_prefix}:bearish_zone_top'] = np.nan
    #             df[f'{col_prefix}:bearish_zone_bottom'] = np.nan

    #             df[f'{col_prefix}:bullish_obj'] = None
    #             df[f'{col_prefix}:bearish_obj'] = None

    #             # ✅ 5. تعبئة الأعمدة
    #             for ts in df.index:
    #                 curr_ts = pd.Timestamp(ts)
                    
    #                 # فلترة المناطق الصاعدة (Bullish) النشطة حالياً
    #                 b_active = [ob for ob in valid_obs 
    #                             if ob['side'] == 'bullish' 
    #                             and ob['_dt_from'] <= curr_ts <= ob['_dt_to']]
                    
    #                 if b_active:
    #                     latest_b = max(b_active, key=lambda x: x['_dt_from'])
    #                     df.at[ts, f'{col_prefix}:bullish_zone_top'] = latest_b['price_top']
    #                     df.at[ts, f'{col_prefix}:bullish_zone_bottom'] = latest_b['price_bottom']
    #                     df.at[ts, f'{col_prefix}:bullish_obj'] = {k:v for k,v in latest_b.items() if not k.startswith('_')}

    #                 # فلترة المناطق الهابطة (Bearish) النشطة حالياً
    #                 s_active = [ob for ob in valid_obs 
    #                             if ob['side'] == 'bearish' 
    #                             and ob['_dt_from'] <= curr_ts <= ob['_dt_to']]
                    
    #                 if s_active:
    #                     latest_s = max(s_active, key=lambda x: x['_dt_from'])
    #                     df.at[ts, f'{col_prefix}:bearish_zone_top'] = latest_s['price_top']
    #                     df.at[ts, f'{col_prefix}:bearish_zone_bottom'] = latest_s['price_bottom']
    #                     df.at[ts, f'{col_prefix}:bearish_obj'] = {k:v for k,v in latest_s.items() if not k.startswith('_')}
    #         # === انتهى إضافة SMC ===

    #         return df

    #     except Exception as e:
    #         logger.error(f"Indicator preparation failed: {e}")
    #         return data






    # async def _prepare_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
    #     """
    #     إعداد المؤشرات.
    #     تم تعديل هذه الدالة لاستخدام منطق الاستخراج من الكود السابق (core.py)
    #     لأنه الأكثر ثباتاً.
    #     """
    #     try:

    #         if hasattr(self, 'full_data') and self.full_data is not None:
    #             if data is self.full_data:
    #                  return data
    #             # في حال كانت بيانات مختلفة (غير محتمل) نستخدم المنطق السابق
    #             return self.full_data.iloc[:len(data)]         
    #         # استدعاء apply_indicators
    #         all_indicators = apply_indicators(
    #             dataframe=data,
    #             indicators_config=self.config.indicators,
    #             use_cache=False,
    #             return_raw=True
    #         )

    #         # إنشاء نسخة من البيانات لإضافة المؤشرات إليها
    #         df = data.copy()
            
    #         # ==========================================
    #         # ✅ بداية التعديل (دعم ID و Label)
    #         # ==========================================
            
    #         # بدلاً من جلب الأسماء فقط ({cfg.name})، سنقوم بجلب "المفاتيح"
    #         # سنستخدم set لتجنب التكرار من البداية



    #         required_keys = set()

    #         for cfg in self.config.indicators:
    #             # 1. نحاول جلب الـ ID (المعرف الجديد والفريد)
    #             target_key = getattr(cfg, 'id', None)
                
    #             # 2. إذا لم يوجد ID، نحاول جلب الـ label
    #             if not target_key:
    #                 target_key = getattr(cfg, 'label', None)
                
    #             # 3. إذا لم يوجد ID ولا label، نعود للاسم (للنظام القديم)
    #             if not target_key:
    #                 target_key = getattr(cfg, 'name', 'unknown')
                
    #             required_keys.add(target_key)
            
    #         # تحويل المجموعة إلى قائمة (نفس اسم المتغير عندك لضمان استمرار الكود)
    #         required_indicators = list(required_keys)
            
    #         # ==========================================
    #         # نهاية التعديل
    #         # ==========================================
            
    #         # جلب مؤشرات القواعد أيضاً (كما هو في كودك)
    #         for rule in self.config.entry_rules + self.config.exit_rules + self.config.filter_rules:
    #             condition = rule.condition
    #             conditions_list = [condition]
    #             if isinstance(condition, CompositeCondition):
    #                 conditions_list = condition.conditions
    #             for cond in conditions_list:
    #                 for val in [cond.left_value, cond.right_value]:
    #                     if isinstance(val, str) and val.startswith("indicator:"):
    #                         indicator_ref = val.split(":")[1]
    #                         required_indicators.append(indicator_ref)

    #         # إزالة التكرار (بسبب الإضافة في القواعد)
    #         required_indicators = list(set(required_indicators))

    #         # حلقة المعالجة (منطقك الأصلي - لم يتم لمسه)
    #         for ind_name in required_indicators:
    #             raw_values: list = [None] * len(data)
                

                    
    #             is_found = ind_name in all_indicators
          

    #             if ind_name in all_indicators:
    #                 result = all_indicators[ind_name]
                                    


               

    #                 if isinstance(result, dict) and 'metadata' in result and 'render' in result['metadata']:
                      
    #                     df.attrs[f'{ind_name}_render'] = result['metadata']['render']
                

    #                 if isinstance(result, dict):
    #                     # محاولة استخراج القائمة من المسارات المتعددة (كما في كودك السابق)
    #                     raw_values = result.get("values", {}).get("data", [None])
                        
    #                     # إذا لم تكن قائمة، نحاول استخراجها بطريقة أخرى
    #                     if not isinstance(raw_values, list):
    #                          raw_values = result.get("data", [None])
                             
    #                 elif isinstance(result, list):
    #                     raw_values = result
    #                 elif isinstance(result, pd.Series):
    #                     raw_values = result.tolist()


    #             else:
    #                 # لم يتم العثور عليه -> سيكون العمود NaN

    #                 pass

                
    #             # Padding لضمان تطابق الطول (منطقك الأصلي)
    #             padding_len = max(0, len(data) - len(raw_values))
    #             series_values = [None] * padding_len + raw_values[:len(data)]
                
    #             # إضافة العمود للـ DataFrame (منطقك الأصلي)
    #             # بما أننا غيرنا المفتاح في الأعلى ليكون (ID أو Name)، فإن df[ind_name] سيكون صحيحاً في الحالتين
    #             df[ind_name] = pd.Series(series_values, index=data.index)




    #     # ==================== Feature Engineering Loop (دعم تعدد المؤشرات والـ ID) ====================
            
    #         # 1. جلب جميع مؤشرات Volume Climax المفعلة (بدلاً من الأول فقط)
    #         vc_configs_list = [x for x in self.config.indicators if x.name == 'volume_climax' and x.enabled]

    #         # 2. دالة مساعدة موحدة لحساب التكرار المتتالي (Streak)
    #         def calculate_streak(mask):
    #             # تحديد بداية المجموعات كلما تغيرت الحالة
    #             groups = (mask != mask.shift()).cumsum()
    #             # حساب الترقيم المتتالي داخل كل مجموعة
    #             streak = mask.groupby(groups).cumsum()
    #             # تصفير القيم في الأماكن التي لم يتحقق فيها الشرط
    #             return streak.where(mask, 0)

    #         # 3. التحقق من توفر بيانات الشموع الأساسية
    #         has_candle_data = 'close' in df.columns and 'open' in df.columns
            
    #         # 4. معالجة كل مؤشر Volume Climax على حدة
    #         for vc_config in vc_configs_list:
                
    #             # --- تحديد المفتاح (ID أو Name) ---
    #             prefix = getattr(vc_config, 'id', None)
    #             if not prefix:
    #                 prefix = getattr(vc_config, 'label', None)
    #             if not prefix:
    #                 prefix = vc_config.name # الرجوع للاسم
                
    #             # التحقق من وجود البيانات في الـ DataFrame (Fallback للاسم إذا كان الـ ID غير موجود)
    #             active_data_key = prefix
    #             if prefix not in df.columns and vc_config.name in df.columns:
    #                 active_data_key = vc_config.name
                
    #             if active_data_key not in df.columns:
    #                 continue # تجاوز إذا لم توجد بيانات

    #             # --- أ) حساب Volume Streaks ---
    #             params = vc_config.params
    #             ratio_low = params.get('ratio_low', 0.4)
    #             ratio_normal = params.get('ratio_normal', 0.8)
    #             ratio_very_high = params.get('ratio_very_high', 1.8)
                
    #             vc_series = df[active_data_key]
                
    #             is_blue = (vc_series >= ratio_low) & (vc_series < ratio_normal)
    #             is_red = (vc_series >= ratio_very_high)
                
    #             # ✅ إنشاء الأعمدة باستخدام `:` لتتوافق مع القواعد (مثال: vc5:vc_blue_streak)
    #             df[f'{prefix}:vc_blue_streak'] = calculate_streak(is_blue)
    #             df[f'{prefix}:vc_red_streak'] = calculate_streak(is_red)

    #             # --- ب) حساب Candle Streaks (مرتبط بـ ID المؤشر) ---
    #             # ملاحظة: حساب الشموع يعتمد على بيانات الإطار الزمني الحالي للـ DataFrame
    #             if has_candle_data:
    #                 is_bull = (df['close'] > df['open'])
    #                 is_bear = (df['close'] < df['open'])
                    
    #                 # ✅ إنشاء أعمدة الشموع بنفس البادئة (مثال: vc5:green_candle_streak)
    #                 df[f'{prefix}:green_candle_streak'] = calculate_streak(is_bull)
    #                 df[f'{prefix}:red_candle_streak'] = calculate_streak(is_bear)
                
    #             # --- ج) معالجة Render (Volume Bars & Climax Points) ---
    #             # جلب بيانات الـ render الخاصة بهذا المؤشر فقط
    #             # (تم تخزينها في الحلقة السابقة باستخدام df.attrs[f'{ind_name}_render'])
    #             vc_render = df.attrs.get(f'{active_data_key}_render', {})
                
    #             # محاولة بديلة بالاسم إذا لم يتم العثور عليها بالمفتاح النشط
    #             if not vc_render:
    #                 vc_render = df.attrs.get(f'{vc_config.name}_render', {})

    #             vb_list = vc_render.get('volume_bars', []) or []
    #             cp_list = vc_render.get('climax_points', []) or []

    #             # دالة مساعدة للوقت
    #             def _parse_time(t):
    #                 try:
    #                     if isinstance(t, (int, float)):
    #                         try:
    #                             return pd.to_datetime(int(t), unit='ms', utc=True)
    #                         except Exception:
    #                             return pd.to_datetime(int(t), unit='s', utc=True)
    #                     return pd.to_datetime(t, utc=True)
    #                 except Exception:
    #                     return None

    #             vb_map = {}
    #             for v in vb_list:
    #                 t = _parse_time(v.get('time'))
    #                 if t is not None:
    #                     vb_map[pd.Timestamp(t)] = {
    #                         'time': pd.Timestamp(t),
    #                         'value': (float(v.get('value')) if v.get('value') is not None else None),
    #                         'ratio': (float(v.get('ratio')) if v.get('ratio') is not None else None),
    #                         'color': v.get('color')
    #                     }

    #             cp_map = {}
    #             for c in cp_list:
    #                 t = _parse_time(c.get('time'))
    #                 if t is not None:
    #                     cp_map[pd.Timestamp(t)] = {
    #                         'time': pd.Timestamp(t),
    #                         'high': (float(c.get('high')) if c.get('high') is not None else None),
    #                         'low': (float(c.get('low')) if c.get('low') is not None else None),
    #                         'ratio': (float(c.get('ratio')) if c.get('ratio') is not None else None),
    #                         'color': c.get('color')
    #                     }

    #             vol_bar_col = []
    #             climax_col = []
    #             for ts in df.index:
    #                 tkey = pd.Timestamp(ts)
    #                 vb = vb_map.get(tkey)
    #                 cp = cp_map.get(tkey)
    #                 vol_bar_col.append(vb if vb else None)
    #                 climax_col.append(cp if cp else None)

    #             # ✅ إنشاء أعمدة الـ Render بالبادئة (مثال: vc5:ind_volume_bar)
    #             df[f'{prefix}:ind_volume_bar'] = pd.Series(vol_bar_col, index=df.index)
    #             df[f'{prefix}:ind_climax_points'] = pd.Series(climax_col, index=df.index)

    #         # ============================================================
    #         # ✅ التعديل الجذري: استخراج وتسوية بيانات SMC (يدعم الـ ID المخصص)
    #         # ============================================================


    #  # ============================================================
    #         # ✅ التعديل الجذري: استخراج وتسوية بيانات SMC (يدعم الـ ID المخصص)
    #         # ============================================================
            
    #         # 1. البحث عن إعدادات مؤشر SMC في القائمة للحصول على الـ ID والاسم
    #         smc_config = next((cfg for cfg in self.config.indicators if cfg.name == 'smc_order_block'), None)
            
    #         smc_metadata = {}
    #         col_prefix = 'smc_order_block' # القيمة الافتراضية
            
    #         # 2. تحديد المفتاح (Key) الذي سيتم استخدامه
    #         # نعطي الأولوية للـ ID كما في الطلب (s123k)، ثم الاسم
    #         lookup_key = None
            
    #         if smc_config:
    #             # محاولة استخدام ID
    #             if hasattr(smc_config, 'id') and smc_config.id:
    #                 lookup_key = smc_config.id
    #                 col_prefix = smc_config.id # استخدام الـ ID كبادئة للأعمدة
                
    #             # إذا لم يتم العثور على البيانات بالـ ID في all_indicators، نحاول بالاسم
    #             if lookup_key and lookup_key not in all_indicators:
    #                  if smc_config.name in all_indicators:
    #                      lookup_key = smc_config.name
    #                      col_prefix = smc_config.name
            
    #         # 3. جلب البيانات والميتاداتا بناءً على المفتاح المحدد
    #         if lookup_key and lookup_key in all_indicators:
    #             result = all_indicators[lookup_key]
                
    #             # التعامل مع Dict
    #             if isinstance(result, dict) and 'metadata' in result:
    #                 smc_metadata = result['metadata']
    #             # التعامل مع Object
    #             elif hasattr(result, 'metadata') and result.metadata is not None:
    #                 meta = result.metadata
    #                 if isinstance(meta, dict) and 'order_blocks' in meta:
    #                     smc_metadata = meta
    #                 elif hasattr(meta, 'get') and 'order_blocks' in meta:
    #                     smc_metadata = meta

    #             # حفظ الميتاداتا في attrs للاستخدام اللاحق إذا لزم الأمر
    #             if smc_metadata:
    #                 df.attrs['smc_metadata'] = smc_metadata

    #         # 4. معالجة الميتاداتا إذا وجدت (المنطق الأصلي)
    #         if smc_metadata:
    #             obs_list = smc_metadata.get('order_blocks', [])
                
    #             # ✅ 1. تحديد خصائص توقيت الشموع
    #             df_tz = df.index.tz
                
    #             valid_obs = []

    #             # ✅ 2. المعالجة المسبقة (Pre-processing) للمناطق
    #             for ob in obs_list:
    #                 t_from = ob.get('time_from')
    #                 t_to = ob.get('time_to')
                    
    #                 if t_from is None:
    #                     continue

    #                 # التحويل من ثواني (Unix Timestamp) إلى Pandas Timestamp
    #                 dt_from = pd.to_datetime(t_from, unit='s')
                    
    #                 # ✅ 3. مواءمة التوقيت (Sync Timezone)
    #                 if df_tz is not None:
    #                     if dt_from.tz is None:
    #                         dt_from = dt_from.tz_localize('UTC').tz_convert(df_tz)
    #                     else:
    #                         dt_from = dt_from.tz_convert(df_tz)
                    
    #                 if pd.isna(t_to):
    #                     dt_to = df.index[-1] + pd.Timedelta(days=1)
    #                 else:
    #                     dt_to = pd.to_datetime(t_to, unit='s')
    #                     if df_tz is not None:
    #                         if dt_to.tz is None:
    #                             dt_to = dt_to.tz_localize('UTC').tz_convert(df_tz)
    #                         else:
    #                             dt_to = dt_to.tz_convert(df_tz)

    #                 ob['_dt_from'] = dt_from
    #                 ob['_dt_to'] = dt_to
    #                 valid_obs.append(ob)

    #             # ✅ 4. إنشاء الأعمدة باستخدام البادئة الديناميكية (col_prefix)
    #             # بدلاً من الترميز الثابت 'smc_order_block'، نستخدم المتغير col_prefix الذي يحمل القيمة 's123k'
                
    #             df[f'{col_prefix}:bullish_zone_top'] = np.nan
    #             df[f'{col_prefix}:bullish_zone_bottom'] = np.nan
    #             df[f'{col_prefix}:bearish_zone_top'] = np.nan
    #             df[f'{col_prefix}:bearish_zone_bottom'] = np.nan

    #             df[f'{col_prefix}:bullish_obj'] = None
    #             df[f'{col_prefix}:bearish_obj'] = None

    #             # ✅ 5. تعبئة الأعمدة
    #             for ts in df.index:
    #                 curr_ts = pd.Timestamp(ts)
                    
    #                 # فلترة المناطق الصاعدة (Bullish) النشطة حالياً
    #                 b_active = [ob for ob in valid_obs 
    #                             if ob['side'] == 'bullish' 
    #                             and ob['_dt_from'] <= curr_ts <= ob['_dt_to']]
                    
    #                 if b_active:
    #                     latest_b = max(b_active, key=lambda x: x['_dt_from'])
    #                     df.at[ts, f'{col_prefix}:bullish_zone_top'] = latest_b['price_top']
    #                     df.at[ts, f'{col_prefix}:bullish_zone_bottom'] = latest_b['price_bottom']
    #                     df.at[ts, f'{col_prefix}:bullish_obj'] = {k:v for k,v in latest_b.items() if not k.startswith('_')}

    #                 # فلترة المناطق الهابطة (Bearish) النشطة حالياً
    #                 s_active = [ob for ob in valid_obs 
    #                             if ob['side'] == 'bearish' 
    #                             and ob['_dt_from'] <= curr_ts <= ob['_dt_to']]
                    
    #                 if s_active:
    #                     latest_s = max(s_active, key=lambda x: x['_dt_from'])
    #                     df.at[ts, f'{col_prefix}:bearish_zone_top'] = latest_s['price_top']
    #                     df.at[ts, f'{col_prefix}:bearish_zone_bottom'] = latest_s['price_bottom']
    #                     df.at[ts, f'{col_prefix}:bearish_obj'] = {k:v for k,v in latest_s.items() if not k.startswith('_')}
    #         # === انتهى إضافة SMC ===

    #         return df

    #     except Exception as e:
    #         logger.error(f"Indicator preparation failed: {e}")
    #         return data







    async def _prepare_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        إعداد المؤشرات.
        تم تعديل هذه الدالة لاستخدام منطق الاستخراج من الكود السابق (core.py)
        لأنه الأكثر ثباتاً.
        """
        try:

            if hasattr(self, 'full_data') and self.full_data is not None:
                if data is self.full_data:
                     return data
                # في حال كانت بيانات مختلفة (غير محتمل) نستخدم المنطق السابق
                return self.full_data.iloc[:len(data)] 




            all_indicators = apply_indicators(
                dataframe=data,
                indicators_config=self.config.indicators,
                use_cache=False,
                return_raw=True
            )

            df = data.copy()
            
            # ==========================================
            # ✅ بداية التعديل (دعم ID و Label)
            # ==========================================
            
            required_keys = set()
            for cfg in self.config.indicators:
                target_key = getattr(cfg, 'id', None)
                if not target_key:
                    target_key = getattr(cfg, 'label', None)
                if not target_key:
                    target_key = getattr(cfg, 'name', 'unknown')
                required_keys.add(target_key)
            
            required_indicators = list(required_keys)
            
            # ==========================================
            # نهاية التعديل
            # ==========================================
            
            # جلب مؤشرات القواعد أيضاً (كما هو في كودك)
            for rule in self.config.entry_rules + self.config.exit_rules + self.config.filter_rules:
                condition = rule.condition
                conditions_list = [condition]
                if isinstance(condition, CompositeCondition):
                    conditions_list = condition.conditions
                for cond in conditions_list:
                    for val in [cond.left_value, cond.right_value]:
                        if isinstance(val, str) and val.startswith("indicator:"):
                            indicator_ref = val.split(":")[1]
                            required_indicators.append(indicator_ref)

            required_indicators = list(set(required_indicators))

            # ✅ إصلاح جذري للأداء (O(n²) → O(n)):
            # بيانات render (volume_bars/climax_points) كانت تُخزن في df.attrs
            # وpandas يعمل deepcopy لكامل attrs عند كل وصول لعمود (df[col] →
            # __finalize__ → deepcopy) — أي ~127ms لكل عمود على بيانات كبيرة!
            # الآن تُخزن على المحرك (self.render_metadata) بدل df.attrs.
            render_meta = getattr(self, 'render_metadata', None)
            if render_meta is None:
                render_meta = {}
                self.render_metadata = render_meta

            # ✅ التحسين الثاني: تجميع المؤشرات الرئيسية في قاموس للحقن الدفعة الواحدة (Bulk Assignment)
            new_columns_dict = {}
            
            # حلقة المعالجة
            for ind_name in required_indicators:
                raw_values: list = [None] * len(data)
                    
                if ind_name in all_indicators:
                    result = all_indicators[ind_name]
                    if isinstance(result, dict) and 'metadata' in result and 'render' in result['metadata']:
                        render_meta[f'{ind_name}_render'] = result['metadata']['render']
                
                    if isinstance(result, dict):
                        raw_values = result.get("values", {}).get("data", [None])
                        if not isinstance(raw_values, list):
                             raw_values = result.get("data", [None])
                    elif isinstance(result, list):
                        raw_values = result
                    elif isinstance(result, pd.Series):
                        raw_values = result.tolist()

                # Padding لضمان تطابق الطول
                padding_len = max(0, len(data) - len(raw_values))
                # استخدام np.nan أسرع وأكثر احترافية للبيانات الرقمية
                series_values = [np.nan] * padding_len + raw_values[:len(data)]
                
                # ✅ تخزين البيانات في القاموس المؤقت بدلاً من الكتابة المباشرة
                new_columns_dict[ind_name] = series_values
            
            # ✅ الخطوة الذهبية: حقن جميع الأعمدة الجديدة دفعة واحدة
            if new_columns_dict:
                # نقوم بتحويل القاموس إلى DataFrame ثم ندمجه دفعة واحدة
                # هذا يقلل استدعاءات نظام إدارة الذاكرة بشكل كبير
                df[list(new_columns_dict.keys())] = pd.DataFrame(new_columns_dict, index=data.index)




        # ==================== Feature Engineering Loop (دعم تعدد المؤشرات والـ ID) ====================
            
            # 1. جلب جميع مؤشرات Volume Climax المفعلة (بدلاً من الأول فقط)
            vc_configs_list = [x for x in self.config.indicators if x.name == 'volume_climax' and x.enabled]

            # 2. دالة مساعدة موحدة لحساب التكرار المتتالي (Streak)
            def calculate_streak(mask):
                # تحديد بداية المجموعات كلما تغيرت الحالة
                groups = (mask != mask.shift()).cumsum()
                # حساب الترقيم المتتالي داخل كل مجموعة
                streak = mask.groupby(groups).cumsum()
                # تصفير القيم في الأماكن التي لم يتحقق فيها الشرط
                return streak.where(mask, 0)

            # 3. التحقق من توفر بيانات الشموع الأساسية
            has_candle_data = 'close' in df.columns and 'open' in df.columns
            
            # 4. معالجة كل مؤشر Volume Climax على حدة
            for vc_config in vc_configs_list:
                
                # --- تحديد المفتاح (ID أو Name) ---
                prefix = getattr(vc_config, 'id', None)
                if not prefix:
                    prefix = getattr(vc_config, 'label', None)
                if not prefix:
                    prefix = vc_config.name 
                
                active_data_key = prefix
                if prefix not in df.columns and vc_config.name in df.columns:
                    active_data_key = vc_config.name
                
                if active_data_key not in df.columns:
                    continue 

                # --- أ) حساب Volume Streaks ---
                params = vc_config.params
                ratio_low = params.get('ratio_low', 0.4)
                ratio_normal = params.get('ratio_normal', 0.8)
                ratio_very_high = params.get('ratio_very_high', 1.8)
                
                vc_series = df[active_data_key]
                is_blue = (vc_series >= ratio_low) & (vc_series < ratio_normal)
                is_red = (vc_series >= ratio_very_high)
                
                # ✅ إنشاء الأعمدة باستخدام `:` لتتوافق مع القواعد
                df[f'{prefix}:vc_blue_streak'] = calculate_streak(is_blue)
                df[f'{prefix}:vc_red_streak'] = calculate_streak(is_red)

                # --- ب) حساب Candle Streaks ---
                if has_candle_data:
                    is_bull = (df['close'] > df['open'])
                    is_bear = (df['close'] < df['open'])
                    df[f'{prefix}:green_candle_streak'] = calculate_streak(is_bull)
                    df[f'{prefix}:red_candle_streak'] = calculate_streak(is_bear)
                
                # --- ج) معالجة Render (Volume Bars & Climax Points) ---
                vc_render = render_meta.get(f'{active_data_key}_render', {})
                if not vc_render:
                    vc_render = render_meta.get(f'{vc_config.name}_render', {})

                vb_list = vc_render.get('volume_bars', []) or []
                cp_list = vc_render.get('climax_points', []) or []

                # ✅ التحسين الثالث: بناء المابات باستخدام Dictionary Comprehension
                def _parse_time(t):
                    try:
                        if isinstance(t, (int, float)):
                            # تحسين: محاولة تلقائية للوحدات
                            ts_int = int(t)
                            # إذا كان الرقم كبيراً جداً (بليون) فهو بالميلي ثانية، وإلا ثواني
                            unit = 'ms' if ts_int > 1e12 else 's'
                            return pd.to_datetime(ts_int, unit=unit, utc=True)
                        return pd.to_datetime(t, utc=True)
                    except: return None

                # ✅ تحسين: مفاتيح int64-nanoseconds بدل pd.Timestamp لكل شمعة
                # (بناء pd.Timestamp لكل شمعة على 527k شمعة كان يكلف عشرات الثواني)
                def _ts_to_ns(t):
                    ts = _parse_time(t)
                    return None if ts is None else ts.value

                vb_map = {_ts_to_ns(v.get('time')): v for v in vb_list if v.get('time')}
                cp_map = {_ts_to_ns(c.get('time')): c for c in cp_list if c.get('time')}
                vb_map.pop(None, None)
                cp_map.pop(None, None)

                # ✅ السطر السحري: تحويل الفهرس مرة واحدة (vectorized) ثم lookup O(1)
                if isinstance(df.index, pd.DatetimeIndex):
                    idx_ns = df.index.asi8
                else:
                    idx_ns = pd.to_datetime(df.index, utc=True).asi8
                df[f'{prefix}:ind_volume_bar'] = [vb_map.get(v) for v in idx_ns]
                df[f'{prefix}:ind_climax_points'] = [cp_map.get(v) for v in idx_ns]

            # ============================================================
            # ✅ التعديل الجذري: استخراج وتسوية بيانات SMC (يدعم الـ ID المخصص)
            # ============================================================
            
            smc_config = next((cfg for cfg in self.config.indicators if cfg.name == 'smc_order_block'), None)
            smc_metadata = {}
            col_prefix = 'smc_order_block'
            lookup_key = None
            
            if smc_config:
                if hasattr(smc_config, 'id') and smc_config.id:
                    lookup_key = smc_config.id
                    col_prefix = smc_config.id
                if lookup_key and lookup_key not in all_indicators:
                     if smc_config.name in all_indicators:
                         lookup_key = smc_config.name
                         col_prefix = smc_config.name
            
            if lookup_key and lookup_key in all_indicators:
                result = all_indicators[lookup_key]
                if isinstance(result, dict) and 'metadata' in result:
                    smc_metadata = result['metadata']
                elif hasattr(result, 'metadata') and result.metadata is not None:
                    meta = result.metadata
                    if isinstance(meta, dict) and 'order_blocks' in meta:
                        smc_metadata = meta
                    elif hasattr(meta, 'get') and 'order_blocks' in meta:
                        smc_metadata = meta

                if smc_metadata:
                    # ✅ يُخزن على المحرك بدل df.attrs (نفس سبب إصلاح render أعلاه)
                    render_meta['smc_metadata'] = smc_metadata

            # ✅ التحسين الرابع: معالجة SMC باستخدام Batch Lists بدلاً من df.at البطيء
            if smc_metadata:
                obs_list = smc_metadata.get('order_blocks', [])
                
                df_tz = df.index.tz
                valid_obs = []

                for ob in obs_list:
                    t_from = ob.get('time_from')
                    t_to = ob.get('time_to')
                    if t_from is None: continue

                    dt_from = pd.to_datetime(t_from, unit='s')
                    if df_tz is not None:
                        dt_from = dt_from.tz_localize('UTC').tz_convert(df_tz) if dt_from.tz is None else dt_from.tz_convert(df_tz)
                    
                    if pd.isna(t_to):
                        dt_to = df.index[-1] + pd.Timedelta(days=1)
                    else:
                        dt_to = pd.to_datetime(t_to, unit='s')
                        if df_tz is not None:
                            dt_to = dt_to.tz_localize('UTC').tz_convert(df_tz) if dt_to.tz is None else dt_to.tz_convert(df_tz)

                    ob['_dt_from'] = dt_from
                    ob['_dt_to'] = dt_to
                    valid_obs.append(ob)

                # ✅ إنشاء قوائم مسبقة (Pre-allocating Lists) للملء السريع
                # هذا أسرع بـ 100 مرة من استخدام df.at داخل حلقة
                b_top_list = [np.nan] * len(df)
                b_bot_list = [np.nan] * len(df)
                b_obj_list = [None] * len(df)
                s_top_list = [np.nan] * len(df)
                s_bot_list = [np.nan] * len(df)
                s_obj_list = [None] * len(df)
                
                # التعبئة (Logic Loop)
                for idx, ts in enumerate(df.index):
                    curr_ts = pd.Timestamp(ts)
                    
                    # Bullish
                    b_active = [ob for ob in valid_obs 
                                if ob['side'] == 'bullish' 
                                and ob['_dt_from'] <= curr_ts <= ob['_dt_to']]
                    
                    if b_active:
                        latest_b = max(b_active, key=lambda x: x['_dt_from'])
                        b_top_list[idx] = latest_b['price_top']
                        b_bot_list[idx] = latest_b['price_bottom']
                        b_obj_list[idx] = {k:v for k,v in latest_b.items() if not k.startswith('_')}

                    # Bearish
                    s_active = [ob for ob in valid_obs 
                                if ob['side'] == 'bearish' 
                                and ob['_dt_from'] <= curr_ts <= ob['_dt_to']]
                    
                    if s_active:
                        latest_s = max(s_active, key=lambda x: x['_dt_from'])
                        s_top_list[idx] = latest_s['price_top']
                        s_bot_list[idx] = latest_s['price_bottom']
                        s_obj_list[idx] = {k:v for k,v in latest_s.items() if not k.startswith('_')}
                
                # ✅ الحقن النهائي (Bulk Assign) للأعمدة الستة دفعة واحدة
                df[f'{col_prefix}:bullish_zone_top'] = b_top_list
                df[f'{col_prefix}:bullish_zone_bottom'] = b_bot_list
                df[f'{col_prefix}:bearish_zone_top'] = s_top_list
                df[f'{col_prefix}:bearish_zone_bottom'] = s_bot_list
                df[f'{col_prefix}:bullish_obj'] = b_obj_list
                df[f'{col_prefix}:bearish_obj'] = s_obj_list

            return df

        except Exception as e:
            logger.error(f"Indicator preparation failed: {e}")
            return data





    # async def _prepare_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
    #     """
    #     إعداد المؤشرات.
    #     تم تعديل هذه الدالة لاستخدام منطق الاستخراج من الكود السابق (core.py)
    #     لأنه الأكثر ثباتاً.
    #     """
    #     try:

    #         if hasattr(self, 'full_data') and self.full_data is not None:
    #             return self.full_data.iloc[:len(data)]            
    #         # استدعاء apply_indicators
    #         all_indicators = apply_indicators(
    #             dataframe=data,
    #             indicators_config=self.config.indicators,
    #             use_cache=False,
    #             return_raw=True
    #         )

    #         # إنشاء نسخة من البيانات لإضافة المؤشرات إليها
    #         df = data.copy()

    #         indicator_keys_map = {} 
            
    #         # تحديد المؤشرات المطلوبة
    #         required_indicators = list({cfg.name for cfg in self.config.indicators})
            
    #         # جلب مؤشرات القواعد أيضاً
    #         for rule in self.config.entry_rules + self.config.exit_rules + self.config.filter_rules:
    #             condition = rule.condition
    #             conditions_list = [condition]
    #             if isinstance(condition, CompositeCondition):
    #                 conditions_list = condition.conditions
    #             for cond in conditions_list:
    #                 for val in [cond.left_value, cond.right_value]:
    #                     if isinstance(val, str) and val.startswith("indicator:"):
    #                         required_indicators.append(val.split(":")[1])

    #         required_indicators = list(set(required_indicators))
    #         logger.info(f"📋 Required Indicators: {required_indicators}")

    #         # حلقة المعالجة (منطق مشابه للكود السابق)
    #         for ind_name in required_indicators:
    #             raw_values: list = [None] * len(data)
                
    #             if ind_name in all_indicators:
    #                 result = all_indicators[ind_name]
                    
    #                 # ✅ هنا منطقك السابق: التعامل مع هيكل النتائج المتعدد
    #                 # معالجة IndicatorResult
    #                 # (نفترض هنا التعامل مع Dict لأن return_raw=True)
                    
    #                 if isinstance(result, dict):
    #                     # محاولة استخراج القائمة من المسارات المتعددة (كما في كودك السابق)
    #                     raw_values = result.get("values", {}).get("data", [None])
                        
    #                     # إذا لم تكن قائمة، نحاول استخراجها بطريقة أخرى
    #                     if not isinstance(raw_values, list):
    #                          raw_values = result.get("data", [None])
                             
    #                 elif isinstance(result, list):
    #                     raw_values = result
    #                 elif isinstance(result, pd.Series):
    #                     raw_values = result.tolist()
                
    #             # Padding لضمان تطابق الطول
    #             padding_len = max(0, len(data) - len(raw_values))
    #             series_values = [None] * padding_len + raw_values[:len(data)]
                
    #             # إضافة العمود للـ DataFrame
    #             df[ind_name] = pd.Series(series_values, index=data.index)

    #         return df

    #     except Exception as e:
    #         logger.error(f"Indicator preparation failed: {e}")
    #         return data

    def _check_exit_conditions(self, data: pd.DataFrame, index: int) -> Optional[str]:
        if not self.config.exit_rules:
            return None
        for rule in self.config.exit_rules:
            if not rule.enabled:
                continue
            if self._evaluate_rule_condition(rule.condition, data, index):
                return rule.name
        return None

    def _determine_trend(self, data: pd.DataFrame, index: int) -> Decision:
        long_score = 0.0
        short_score = 0.0
        active_reason = "No clear trend direction"

        # ✅ تقييم واحد لكل قاعدة بدل مرتين (كان يُقيَّم شرط كل قاعدة في
        # مرورٍ للـ Long وآخر للـ Short — مضاعفة بلا داعٍ).
        # الدلالات مطابقة تماماً: القاعدة LONG تضيف للـ long، SHORT للـ short،
        # BOTH للاثنين، وactive_reason يتحدث بترتيب القواعد نفسه.
        for rule in self.config.entry_rules:
            if not rule.enabled:
                continue
            sides = rule.position_side
            is_long = sides in [PositionSide.LONG, PositionSide.BOTH]
            is_short = sides in [PositionSide.SHORT, PositionSide.BOTH]
            if not (is_long or is_short):
                continue
            if self._evaluate_rule_condition(rule.condition, data, index):
                if is_long:
                    long_score += rule.weight
                if is_short:
                    short_score += rule.weight
                active_reason = rule.name


        allowed_positions = []


        for filter_rule in self.config.filter_rules:
            if not filter_rule.enabled:
                continue

            
                
            # تحقق من شرط الفلتر
            if self._evaluate_rule_condition(filter_rule.condition, data, index):


                metadata = filter_rule.metadata or {} 
            
                if filter_rule.action == "allow":
                    allowed_side = metadata.get("allowed_position")
                    if allowed_side:  # تأكد من وجود قيمة
                        allowed_positions.append(allowed_side)
                
            
                elif filter_rule.action == "block":
                    blocked_side = metadata.get("blocked_position")
                    if blocked_side == "long":
                        long_score = 0.0  # منع Long
                    elif blocked_side == "short":
                        short_score = 0.0  # منع Short
                


        if allowed_positions:
            # إذا كان مسموح فقط Long
            if "long" in allowed_positions and "short" not in allowed_positions:
                short_score = 0.0  # منع Short
            
            # إذا كان مسموح فقط Short
            elif "short" in allowed_positions and "long" not in allowed_positions:
                long_score = 0.0  # منع Long
        



        if long_score > short_score and long_score > 0:
            return Decision(
                timestamp=data.index[index],
                action=DecisionAction.BUY,
                confidence=min(long_score, 1.0),
                reason=active_reason,
                metadata={"score": long_score}
            )
        elif short_score > long_score and short_score > 0:
            return Decision(
                timestamp=data.index[index],
                action=DecisionAction.SELL,
                confidence=min(short_score, 1.0),
                reason=active_reason,
                metadata={"score": short_score}
            )
        else:
            return self._create_hold_decision("No clear trend direction")

    # def _evaluate_rule_condition(self, condition: Any, data: pd.DataFrame, index: int) -> bool:
    #     """
    #     تقييم الشرط.
    #     البيانات الآن موجودة داخل df كأعمدة نظيفة (تم استخراجها في _prepare_indicators)
    #     """
    #     try:
    #         indicators_dict = {}
    #         indicator_names = [ind.name for ind in self.config.indicators]
            
    #         for ind_name in indicator_names:
    #             if ind_name in data.columns:
    #                 indicators_dict[ind_name] = data[ind_name]
            
    #         if isinstance(condition, Condition) or isinstance(condition, CompositeCondition):
    #             return self.condition_evaluator.evaluate(
    #                 condition,
    #                 data,
    #                 indicators_dict,
    #                 index
    #             )
    #         return False
    #     except Exception as e:
    #         print(f"[Error] Evaluation Failed: {e}")
    #         return False

    def _get_indicators_dict(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        ✅ بناء قاموس المؤشرات مرة واحدة لكل مجموعة بيانات (كاش بالهوية).
        كان يُبنى داخل كل تقييم شرط (عدة مرات في كل شمعة) — استهلاك هائل.
        """
        if self._ind_dict_cache_data is data and self._ind_dict_cache:
            return self._ind_dict_cache

        indicators_dict: Dict[str, Any] = {}

        # المفتاح: الأولوية للـ ID (مثل ema_999)، وإلا الاسم
        for ind_config in self.config.indicators:
            key = getattr(ind_config, 'id', None)
            if not key:
                key = getattr(ind_config, 'name', 'unknown')
            if key in data.columns:
                indicators_dict[key] = data[key]

        # دعم الأعمدة المشتقة (vc_blue_streak, green_candle_streak, ...)
        for col in data.columns:
            if col not in indicators_dict:
                indicators_dict[col] = data[col]

        self._ind_dict_cache_data = data
        self._ind_dict_cache = indicators_dict
        return indicators_dict

    def _evaluate_rule_condition(self, condition: Any, data: pd.DataFrame, index: int) -> bool:
        """
        تقييم الشرط.
        البيانات موجودة داخل df كأعمدة نظيفة.
        يدعم الـ IDs المخصصة — والقاموس مبني مسبقاً (كاش).
        """
        try:
            indicators_dict = self._get_indicators_dict(data)

            if isinstance(condition, Condition) or isinstance(condition, CompositeCondition):
                return self.condition_evaluator.evaluate(
                    condition,
                    data,
                    indicators_dict, 
                    index
                )
            return False
        except Exception as e:
            logger.error(f"[Error] Evaluation Failed: {e}")
            return False


    def _create_hold_decision(self, reason: str) -> Decision:
        return Decision(
            timestamp=datetime.now(),
            action=DecisionAction.HOLD,
            confidence=0.0,
            reason=reason
        )