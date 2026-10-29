import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import sys
import os

from app.services.indicators.registry import IndicatorRegistry
from app.services.indicators.base import BaseIndicator, IndicatorResult, IndicatorType,IndicatorConfig



@IndicatorRegistry.register(
    name="smc_order_block",
    display_name="SMC Order Blocks",
    description="مؤشر ذكي لكشف Order Blocks (بلوكات الطلبات) باستخدام مفاهيم SMC",
    category=IndicatorType.SUPPORT_RESISTANCE
)

class SMCOrderBlockIndicator(BaseIndicator):
    """
    مؤشر ذكي لكشف Order Blocks (بلوكات الطلبات) باستخدام مفاهيم SMC.
    يعتمد على اكتشاف القمم والقيعان (Swing Highs/Lows) أولاً.
    """

    def __init__(self, config: IndicatorConfig):
        # تعيين النوع الافتراضي إذا لم يتم توفيره
        if config.type is None:
            config = config.copy(update={'type': IndicatorType.SUPPORT_RESISTANCE})
        super().__init__(config)

    @classmethod
    def get_required_columns(cls) -> List[str]:
        """الأعمدة المطلوبة: فتح، أعلى، أدنى، إغلاق، حجم"""
        return ['open', 'high', 'low', 'close', 'volume']

    @classmethod
    def get_default_params(cls) -> Dict[str, Any]:
        """المعاملات الافتراضية"""
        return {
            'swing_length': 20,
            'close_mitigation': False,
            'range_percent': 0.01 # للمصفوفات الداخلية إذا لزم الأمر
        }
    

    def calculate(self, data: pd.DataFrame) -> IndicatorResult:
        """
        نقطة الحساب الرئيسية المعدلة لاستخدام البيانات المحسوبة مباشرة.
        """
        # 1. التحقق والمعالجة المسبقة
        self.validate_data(data)
        ohlc = data.copy()
        ohlc.columns = [c.lower() for c in ohlc.columns]

        swing_length = self.params.get('swing_length', 20)
        close_mitigation = self.params.get('close_mitigation', False)

        # 2. حساب Swing Highs and Lows
        swing_data = self._calculate_swing_highs_lows(ohlc, swing_length)

        # 3. حساب Order Blocks (الآن يحتوي على 'TimeTo' و 'Side')
        ob_data = self._calculate_order_blocks(ohlc, swing_data, close_mitigation)

        # 4. تحويل المصفوفات إلى قائمة كائنات (Order Blocks List)
        order_blocks_list = []

        # نبحث فقط عن الأماكن التي تم فيها اكتشاف OB (حيث القيمة ليست NaN)
        ob_indices = ob_data.index[~ob_data['OB'].isna()]

        # آخر وقت في البيانات (لتمديد الـ OB غير الملغاة)
        last_time = int(ohlc.index[-1].timestamp())

        for idx in ob_indices:
            i = ohlc.index.get_loc(idx) # موقعه الرقمي في الـ DataFrame

            # ✅ التحديث: قراءة البيانات المحسوبة مباشرة من ob_data بدلاً من إعادة الحساب
            
            # 1. قراءة الوقت النهائي (TimeTo) المحسوب مسبقاً
            calculated_time_to = ob_data['TimeTo'].iloc[i]
            
            if pd.notna(calculated_time_to):
                # إذا تم حساب وقت نهاية (تم المسح)
                time_to = int(calculated_time_to)
                is_mitigated = True
            else:
                # إذا لم يتم المسح، نجعل البلوك يمتد حتى آخر شمعة متاحة
                time_to = last_time
                is_mitigated = False

            # 2. قراءة الاتجاه (Side) المحسوب مسبقاً
            side_val = ob_data['Side'].iloc[i]
            side_str = "bullish" if side_val == 1 else "bearish"

            # بناء كائن الـ OB
            ob_obj = {
                "id": f"ob_{idx.to_pydatetime().strftime('%Y%m%d%H%M')}_{i}",
                "side": side_str,           # ✅ استخدام القيمة المحسوبة
                "time_from": int(idx.timestamp()),
                "time_to": time_to,         # ✅ استخدام القيمة المحسوبة
                "price_top": float(ob_data['Top'].iloc[i]),
                "price_bottom": float(ob_data['Bottom'].iloc[i]),
                "mitigated": is_mitigated,
                "strength": round(float(ob_data['Percentage'].iloc[i]) / 100, 2)
            }
            order_blocks_list.append(ob_obj)

        metadata = {
            "order_blocks": order_blocks_list,
            # إذا كنت لا تزال بحاجة لبيانات السوينغ للرسم
            "swing_points": self._format_swing_data(swing_data) 
        }

        return IndicatorResult(
            name=self.name,
            values=ob_data['OB'].tolist(), # نحولها لقائمة عادية لتقليل الحجم
            metadata=metadata
        )


    def _format_swing_data(self, swing_data: pd.DataFrame) -> List[Dict]:
        """دالة مساعدة لتحويل بيانات السوينغ أيضاً إلى نقاط بدلاً من مصفوفة ضخمة"""
        swings = []
        swing_indices = swing_data.index[~swing_data['HighLow'].isna()]
        for idx in swing_indices:
            swings.append({
                "time": int(idx.timestamp()),
                "type": "high" if swing_data.loc[idx, 'HighLow'] == 1 else "low",
                "level": float(swing_data.loc[idx, 'Level'])
            })
        return swings

   
    def _calculate_swing_highs_lows(self, ohlc: pd.DataFrame, swing_length: int = 50) -> pd.DataFrame:
        """
        حساب القمم والقيعان (مستخلص من الكود الأصلي)
        """
        swing_length *= 2
        
        # تحديد القمم والقيعان الأولية
        swing_highs_lows = np.where(
            ohlc["high"]
            == ohlc["high"]
            .shift(-(swing_length // 2))
            .rolling(swing_length)
            .max(),
            1,
            np.where(
                ohlc["low"]
                == ohlc["low"]
                .shift(-(swing_length // 2))
                .rolling(swing_length)
                .min(),
                -1,
                np.nan,
            ),
        )

        # تنظيف القمم والقيعان المتقاربة (Fractals)
        continue_ = True
        while continue_:
            positions = np.where(~np.isnan(swing_highs_lows))[0]
            continue_ = False
            for i in range(len(positions) - 1):
                current, next_val = (
                    swing_highs_lows[positions[i]],
                    swing_highs_lows[positions[i + 1]],
                )
                high, low = (
                    ohlc["high"].iloc[positions[i]],
                    ohlc["low"].iloc[positions[i]],
                )
                next_high, next_low = (
                    ohlc["high"].iloc[positions[i + 1]],
                    ohlc["low"].iloc[positions[i + 1]],
                )
                if current == -1 and next_val == -1:
                    remove_index = positions[i] if low > next_low else positions[i + 1]
                    swing_highs_lows[remove_index] = np.nan
                    continue_ = True
                elif current == 1 and next_val == 1:
                    remove_index = (
                        positions[i] if high < next_high else positions[i + 1]
                    )
                    swing_highs_lows[remove_index] = np.nan
                    continue_ = True

        # تعديل البداية والنهاية (Start and End)
        positions = np.where(~np.isnan(swing_highs_lows))[0]
        if len(positions) > 0:
            if swing_highs_lows[positions[0]] == 1:
                swing_highs_lows[0] = -1
            if swing_highs_lows[positions[-1]] == -1:
                swing_highs_lows[-1] = 1

        level = np.where(
            ~np.isnan(swing_highs_lows),
            np.where(swing_highs_lows == 1, ohlc["high"], ohlc["low"]),
            np.nan,
        )

        return pd.DataFrame({
            'HighLow': swing_highs_lows,
            'Level': level
        }, index=ohlc.index)


    def _calculate_order_blocks(
        self, 
        ohlc: pd.DataFrame, 
        swing_highs_lows: pd.DataFrame, 
        close_mitigation: bool = False
    ) -> pd.DataFrame:
        """
        حساب بلوكات الطلبات (منطق الدالة ob في الكود الأصلي)
        """
        crossed = np.full(len(ohlc), False, dtype=bool)
        ob = np.zeros(len(ohlc), dtype=np.int32)
        top = np.zeros(len(ohlc), dtype=np.float32)
        bottom = np.zeros(len(ohlc), dtype=np.float32)
        obVolume = np.zeros(len(ohlc), dtype=np.float32)
        lowVolume = np.zeros(len(ohlc), dtype=np.float32)
        highVolume = np.zeros(len(ohlc), dtype=np.float32)
        percentage = np.zeros(len(ohlc), dtype=np.int32)
        mitigated_index = np.zeros(len(ohlc), dtype=np.int32)
        
        # ✅ إضافة مصفوفات time_to و side المفقودة
        time_to = np.full(len(ohlc), np.nan, dtype=np.float64)
        side = np.zeros(len(ohlc), dtype=np.int32) # 1 for Bullish, -1 for Bearish
        
        breaker = np.full(len(ohlc), False, dtype=bool)

        # Bullish Order Block Logic
        for i in range(len(ohlc)):
            close_index = i
            close_price = ohlc["close"].iloc[close_index]

            # Mitigation check for existing Bullish OBs
            if len(ob[ob == 1]) > 0:
                for j in range(len(ob) - 1, -1, -1):
                    if ob[j] == 1:
                        currentOB = j
                        if breaker[currentOB]:
                            if ohlc.high.iloc[close_index] > top[currentOB]:
                                ob[j] = top[j] = bottom[j] = obVolume[j] = lowVolume[j] = highVolume[j] = mitigated_index[j] = percentage[j] = side[j] = 0.0
                                time_to[j] = np.nan
                        elif (
                                not close_mitigation
                                and ohlc["low"].iloc[close_index] < bottom[currentOB]
                            ) or (
                                close_mitigation
                                and min(
                                    ohlc["open"].iloc[close_index],
                                    ohlc["close"].iloc[close_index],
                                )
                                < bottom[currentOB]
                            ):
                            breaker[currentOB] = True
                            mitigated_index[currentOB] = close_index
                            # ✅ تحديث time_to عند حدوث الإلغاء
                            ts = ohlc.index[close_index]
                            if isinstance(ts, pd.Timestamp):
                                time_to[currentOB] = ts.timestamp()
                            else:
                                time_to[currentOB] = float(ts)
            
            # Detection of new Bullish OB
            last_top_index = None
            
            # ✅ الإصلاح: الحصول على الأماكن (Positions) بدلاً من الـ Timestamps
            # نحصل أولاً على الفلاتر، ثم نحول المؤشرات إلى مواقع صحيحة
            swing_high_indices = swing_highs_lows[swing_highs_lows["HighLow"] == 1].index
            
            if len(swing_high_indices) > 0:
                # تحويل الـ Timestamps إلى مواقع أعداد صحيحة (0, 1, 2...)
                swing_positions = ohlc.index.get_indexer_for(swing_high_indices)
                # التأكد من استبعاد القيم غير الصحيحة (-1 إذا لم يوجد تطابق)
                swing_positions = [pos for pos in swing_positions if pos >= 0]

                for pos in swing_positions:
                    if pos < close_index: # ✅ الآن نقارن عدد صحيح مع عدد صحيح
                        last_top_index = pos
            
            if last_top_index is not None:
                swing_top_price = ohlc["high"].iloc[last_top_index]
                if close_price > swing_top_price and not crossed[last_top_index]:
                    crossed[last_top_index] = True
                    obBtm = ohlc["high"].iloc[close_index - 1]
                    obTop = ohlc["low"].iloc[close_index - 1]
                    obIndex = close_index - 1
                    for j in range(1, close_index - last_top_index):
                        obBtm = min(ohlc["low"].iloc[last_top_index + j], obBtm)
                        if obBtm == ohlc["low"].iloc[last_top_index + j]:
                            obTop = ohlc["high"].iloc[last_top_index + j]
                        obIndex = (
                            last_top_index + j
                            if obBtm == ohlc["low"].iloc[last_top_index + j]
                            else obIndex
                        )

                    ob[obIndex] = 1
                    side[obIndex] = 1 # ✅ تحديد الاتجاه: Bullish
                    top[obIndex] = obTop
                    bottom[obIndex] = obBtm
                    obVolume[obIndex] = (
                        ohlc["volume"].iloc[close_index]
                        + ohlc["volume"].iloc[close_index - 1]
                        + ohlc["volume"].iloc[close_index - 2]
                    )
                    lowVolume[obIndex] = ohlc["volume"].iloc[close_index - 2]
                    highVolume[obIndex] = (
                        ohlc["volume"].iloc[close_index]
                        + ohlc["volume"].iloc[close_index - 1]
                    )
                    percentage[obIndex] = (
                        np.min([highVolume[obIndex], lowVolume[obIndex]], axis=0)
                        / np.max([highVolume[obIndex], lowVolume[obIndex]], axis=0)
                    ) * 100.0

        # Bearish Order Block Logic
        for i in range(len(ohlc)):
            close_index = i
            close_price = ohlc["close"].iloc[close_index]

            # Mitigation check for existing Bearish OBs
            if len(ob[ob == -1]) > 0:
                for j in range(len(ob) - 1, -1, -1):
                    if ob[j] == -1:
                        currentOB = j
                        if breaker[currentOB]:
                            if ohlc.low.iloc[close_index] < bottom[currentOB]:
                                ob[j] = top[j] = bottom[j] = obVolume[j] = lowVolume[j] = highVolume[j] = mitigated_index[j] = percentage[j] = side[j] = 0.0
                                time_to[j] = np.nan
                        elif (
                                not close_mitigation
                                and ohlc["high"].iloc[close_index] > top[currentOB]
                            ) or (
                                close_mitigation
                                and max(
                                    ohlc["open"].iloc[close_index],
                                    ohlc["close"].iloc[close_index],
                                )
                                > top[currentOB]
                            ):
                            breaker[currentOB] = True
                            mitigated_index[currentOB] = close_index
                            # ✅ تحديث time_to
                            ts = ohlc.index[close_index]
                            if isinstance(ts, pd.Timestamp):
                                time_to[currentOB] = ts.timestamp()
                            else:
                                time_to[currentOB] = float(ts)
            
            # Detection of new Bearish OB
            last_btm_index = None

            # ✅ الإصلاح: الحصول على الأماكن (Positions) بدلاً من الـ Timestamps
            swing_low_indices = swing_highs_lows[swing_highs_lows["HighLow"] == -1].index
            
            if len(swing_low_indices) > 0:
                swing_positions = ohlc.index.get_indexer_for(swing_low_indices)
                swing_positions = [pos for pos in swing_positions if pos >= 0]

                for pos in swing_positions:
                    if pos < close_index: # ✅ عدد صحيح مع عدد صحيح
                        last_btm_index = pos
            
            if last_btm_index is not None:
                swing_btm_price = ohlc["low"].iloc[last_btm_index]
                if close_price < swing_btm_price and not crossed[last_btm_index]:
                    crossed[last_btm_index] = True
                    obBtm = ohlc["low"].iloc[close_index - 1]
                    obTop = ohlc["high"].iloc[close_index - 1]
                    obIndex = close_index - 1
                    for j in range(1, close_index - last_btm_index):
                        obTop = max(ohlc["high"].iloc[last_btm_index + j], obTop)
                        obBtm = (
                            ohlc["low"].iloc[last_btm_index + j]
                            if obTop == ohlc["high"].iloc[last_btm_index + j]
                            else obBtm
                        )
                        obIndex = (
                            last_btm_index + j
                            if obTop == ohlc["high"].iloc[last_btm_index + j]
                            else obIndex
                        )

                    ob[obIndex] = -1
                    side[obIndex] = -1 # ✅ تحديد الاتجاه: Bearish
                    top[obIndex] = obTop
                    bottom[obIndex] = obBtm
                    obVolume[obIndex] = (
                        ohlc["volume"].iloc[close_index]
                        + ohlc["volume"].iloc[close_index - 1]
                        + ohlc["volume"].iloc[close_index - 2]
                    )
                    lowVolume[obIndex] = (
                        ohlc["volume"].iloc[close_index]
                        + ohlc["volume"].iloc[close_index - 1]
                    )
                    highVolume[obIndex] = ohlc["volume"].iloc[close_index - 2]
                    percentage[obIndex] = (
                        np.min([highVolume[obIndex], lowVolume[obIndex]], axis=0)
                        / np.max([highVolume[obIndex], lowVolume[obIndex]], axis=0)
                    ) * 100.0

        # Formatting Output
        ob = np.where(ob != 0, ob, np.nan)
        top = np.where(~np.isnan(ob), top, np.nan)
        bottom = np.where(~np.isnan(ob), bottom, np.nan)
        obVolume = np.where(~np.isnan(ob), obVolume, np.nan)
        mitigated_index = np.where(~np.isnan(ob), mitigated_index, np.nan)
        percentage = np.where(~np.isnan(ob), percentage, np.nan)
        side = np.where(~np.isnan(ob), side, np.nan)
        time_to = np.where(~np.isnan(ob), time_to, np.nan)

        return pd.DataFrame({
            'OB': ob,
            'Top': top,
            'Bottom': bottom,
            'OBVolume': obVolume,
            'MitigatedIndex': mitigated_index,
            'Percentage': percentage,
            'Side': side,
            'TimeTo': time_to
        }, index=ohlc.index)
