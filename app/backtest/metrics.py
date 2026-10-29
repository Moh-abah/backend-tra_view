# trading_backend\app\backtest\metrics.py
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
from datetime import datetime, timedelta
from scipy import stats

from .schemas import Trade, BacktestConfig


class PerformanceMetrics:
    """حساب مؤشرات الأداء المالية"""
    









    def calculate(self, trades: List[Trade], initial_capital: float) -> Dict[str, float]:
        """
        الطريقة العامة (Public Method) التي يستدعها المحرك (Engine).
        تقوم بتجميع النتائج من جميع الدوال المساعدة وترجعها في قاموس موحد.
        """
        if not trades:
            return self._empty_metrics_dict()
        
        # 1. بناء منحنى الرأس المال (مطلوب لمقاييس المخاطر)
        equity_curve = self._build_equity_curve(trades, initial_capital)
        drawdown_curve = self._calculate_drawdown_curve(equity_curve)

        # 2. حساب المقاييس الأساسية
        basic_metrics = self._calculate_basic_metrics(trades)

        # 3. حساب مقاييس المخاطر
        risk_metrics = self._calculate_risk_metrics(equity_curve, drawdown_curve)
        
        # 4. حساب مقاييس العائد المعدل بالمخاطرة
        risk_adj_metrics = self._calculate_risk_adjusted_metrics(equity_curve, risk_metrics)

        # 5. حساب مقاييس التوقيت
        timing_metrics = self._calculate_timing_metrics(trades)

        # 6. حساب المقاييس المتقدمة
        advanced_metrics = self._calculate_advanced_metrics(trades, equity_curve)

        # دمج كل المقاييس في قاموس واحد


        full_metrics = {
            **basic_metrics,
            **risk_metrics,
            **risk_adj_metrics,
            **timing_metrics,
            **advanced_metrics
        }
        
        # ★ إضافة الحقول الأساسية المطلوبة في BacktestResult
        final_capital = initial_capital
        if trades:
            final_capital = initial_capital + sum(t.pnl for t in trades if t.pnl is not None)
        
        total_pnl = final_capital - initial_capital
        total_pnl_percent = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0
        
        full_metrics['total_pnl'] = total_pnl
        full_metrics['total_pnl_percentage'] = total_pnl_percent  # للتوافق مع engine القديم
        full_metrics['total_pnl_percent'] = total_pnl_percent     # ★ للتوافق مع schemas.py الجديد
        full_metrics['final_capital'] = final_capital
        
        # ★ إضافة max_drawdown للتوافق
        if 'max_drawdown_percent' in full_metrics:
            full_metrics['max_drawdown'] = full_metrics['max_drawdown_percent']
        
        return full_metrics        
        # full_metrics = {
        #     **basic_metrics,
        #     **risk_metrics,
        #     **risk_adj_metrics,
        #     **timing_metrics,
        #     **advanced_metrics
        # }
        
        # # التأكد من وجود المفاتيح الأساسية المطلوبة في BacktestResult
        # # إذا كانت الدالة تُرجع شيئاً مختلفاً، قد يفشل إنشاء BacktestResult
        # full_metrics['total_pnl'] = basic_metrics.get('total_pnl', 0)
        # full_metrics['total_pnl_percentage'] = basic_metrics.get('total_pnl_percentage', 0)
        
        # return full_metrics

    def _build_equity_curve(self, trades: List[Trade], initial_capital: float) -> List[float]:
        """بناء منحنى الرأس المال من الصفقات"""
        if not trades:
            return [initial_capital]
        
        # ترتيب الصفقات حسب وقت الدخول
        sorted_trades = sorted(trades, key=lambda x: x.entry_time)
        
        # سنقوم بمحاكاة بسيطة لرسم المنحنى
        # ملاحظة: الباك-تيست يفعل هذا بشكل أدق في الحلقة الرئيسية، هنا فقط للحسابات
        curve = [initial_capital]
        current_capital = initial_capital
        
        for trade in sorted_trades:
            # عند الدخول، يحدث تغيير فوري (نفقات العمولة)
            entry_pnl = -trade.commission if trade.commission else 0
            curve.append(curve[-1] + entry_pnl)
            current_capital += entry_pnl
            
            # عند الخروج
            if trade.exit_time and trade.pnl is not None:
                # تعديل القيمة الأخيرة للتأكد من دقة الرسم
                # في المحاكاة الحقيقية، الخروج يحدث في بار معين
                # هنا نعتمد على التسلسل
                curve.append(curve[-1] + trade.pnl)
                current_capital += trade.pnl

        # التأكد من أن المنحنى تنتهي برأس المال النهائي
        # إذا كان هناك ربح/خسارة لم يتم احتسابه
        return curve

    def _empty_metrics_dict(self) -> Dict[str, float]:
        """قاموس فارغ عند عدم وجود صفقات"""
        return {
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'expectancy': 0.0,
            'max_drawdown_percent': 0.0,
            'max_drawdown_duration_days': 0,
            'volatility_annual': 0.0,
            'var_95': 0.0,
            'cvar_95': 0.0,
            'sharpe_ratio': 0.0,
            'sortino_ratio': 0.0,
            'calmar_ratio': 0.0,
            'annual_return_percent': 0.0,
            'total_pnl': 0.0,
            'total_pnl_percentage': 0.0,
            'avg_winning_trade': 0.0,
            'avg_losing_trade': 0.0,
            'largest_winning_trade': 0.0,
            'largest_losing_trade': 0.0,
            'avg_trade_duration_hours': 0.0,
            'system_quality_number': 0.0,
            'kelly_criterion': 0.0
        }





    def _calculate_drawdown_curve(self, equity_curve: List[float]) -> List[float]:
        """حساب منحنى الانخفاض"""
        if not equity_curve:
            return []

        peak = equity_curve[0]
        drawdowns = []

        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100 if peak > 0 else 0
            drawdowns.append(drawdown)

        return drawdowns






    async def calculate_all_metrics(
        self,
        trades: List[Trade],
        equity_curve: List[float],
        drawdown_curve: List[float],
        config: BacktestConfig
    ) -> Dict[str, float]:
        """حساب جميع المقاييس"""
        metrics = {}
        
        # المقاييس الأساسية
        metrics.update(self._calculate_basic_metrics(trades))
        
        # مقاييس المخاطرة
        metrics.update(self._calculate_risk_metrics(equity_curve, drawdown_curve))
        
        # مقاييس العائد المعدل بالمخاطرة
        metrics.update(self._calculate_risk_adjusted_metrics(equity_curve, metrics))
        
        # مقاييس التوقيت
        metrics.update(self._calculate_timing_metrics(trades))
        
        # مقاييس متقدمة
        metrics.update(self._calculate_advanced_metrics(trades, equity_curve))
        
        return metrics
    
    def _calculate_basic_metrics(self, trades: List[Trade]) -> Dict[str, float]:
        """حساب المقاييس الأساسية"""
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'expectancy': 0.0,
                'avg_winning_trade': 0.0,
                'avg_losing_trade': 0.0,
                'largest_winning_trade': 0.0,
                'largest_losing_trade': 0.0
            }
        
        # تصفية الصفقات المكتملة
        completed_trades = [t for t in trades if t.exit_time and t.pnl is not None]
        
        if not completed_trades:
            return {}
        
        winning_trades = [t for t in completed_trades if t.pnl > 0]
        losing_trades = [t for t in completed_trades if t.pnl <= 0]
        
        total_trades = len(completed_trades)
        winning_count = len(winning_trades)
        losing_count = len(losing_trades)
        
        win_rate = (winning_count / total_trades) * 100 if total_trades > 0 else 0
        
        # حساب عامل الربح
        gross_profit = sum(t.pnl for t in winning_trades)
        gross_loss = abs(sum(t.pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # حساب التوقع
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([abs(t.pnl) for t in losing_trades]) if losing_trades else 0
        expectancy = (avg_win * (winning_count / total_trades) - 
                     avg_loss * (losing_count / total_trades)) if total_trades > 0 else 0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_count,
            'losing_trades': losing_count,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'avg_winning_trade': avg_win,
            'avg_losing_trade': avg_loss,
            'largest_winning_trade': max([t.pnl for t in winning_trades], default=0),
            'largest_losing_trade': min([t.pnl for t in losing_trades], default=0)
        }
    
    def _calculate_risk_metrics(
        self,
        equity_curve: List[float],
        drawdown_curve: List[float]
    ) -> Dict[str, float]:
        """حساب مقاييس المخاطرة"""
        if len(equity_curve) < 2:
            return {
                'max_drawdown_percent': 0.0,
                'max_drawdown_duration_days': 0,
                'volatility_annual': 0.0,
                'var_95': 0.0,
                'cvar_95': 0.0
            }
        
        # أقصى انخفاض
        max_drawdown = max(drawdown_curve) if drawdown_curve else 0.0
        
        # مدة أقصى انخفاض
        max_dd_duration = self._calculate_max_dd_duration(drawdown_curve)
        
        # حساب التقلبات (الانحراف المعياري للعوائد)
        returns = self._calculate_returns(equity_curve)
        volatility_annual = np.std(returns) * np.sqrt(252) * 100 if len(returns) > 0 else 0
        
        # حساب القيمة المعرضة للخطر (VaR) والـ CVaR
        var_95, cvar_95 = self._calculate_var_cvar(returns)
        
        return {
            'max_drawdown_percent': max_drawdown,
            'max_drawdown_duration_days': max_dd_duration,
            'volatility_annual': volatility_annual,
            'var_95': var_95,
            'cvar_95': cvar_95
        }
    
    def _calculate_max_dd_duration(self, drawdown_curve: List[float]) -> int:
        """حساب مدة أقصى انخفاض"""
        if not drawdown_curve:
            return 0
        
        max_dd_start = 0
        max_dd_end = 0
        current_start = 0
        in_drawdown = False
        
        for i, dd in enumerate(drawdown_curve):
            if dd > 0 and not in_drawdown:
                in_drawdown = True
                current_start = i
            elif dd == 0 and in_drawdown:
                in_drawdown = False
                if i - current_start > max_dd_end - max_dd_start:
                    max_dd_start = current_start
                    max_dd_end = i
        
        return max_dd_end - max_dd_start
    
    def _calculate_returns(self, equity_curve: List[float]) -> List[float]:
        """حساب العوائد"""
        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i-1] != 0:
                ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
                returns.append(ret)
        return returns
    
    def _calculate_var_cvar(self, returns: List[float]) -> Tuple[float, float]:
        """حساب VaR وCVaR"""
        if not returns:
            return 0.0, 0.0
        
        # المستوى 95%
        confidence_level = 0.95
        
        # ترتيب العوائد
        sorted_returns = np.sort(returns)
        
        # حساب VaR
        var_index = int((1 - confidence_level) * len(sorted_returns))
        var = sorted_returns[var_index] * 100 if var_index < len(sorted_returns) else 0.0
        
        # حساب CVaR (متوسط الخسائر أسوأ من VaR)
        if var_index > 0:
            cvar = np.mean(sorted_returns[:var_index]) * 100
        else:
            cvar = 0.0
        
        return abs(var), abs(cvar)
    
    def _calculate_risk_adjusted_metrics(
        self,
        equity_curve: List[float],
        other_metrics: Dict[str, float]
    ) -> Dict[str, float]:
        """حساب مقاييس العائد المعدل بالمخاطرة"""
        if len(equity_curve) < 2:
            return {
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'calmar_ratio': 0.0,
                'annual_return_percent': 0.0
            }
        
        # حساب العوائد
        returns = self._calculate_returns(equity_curve)
        
        if not returns:
            return {
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'calmar_ratio': 0.0,
                'annual_return_percent': 0.0
            }
        
        # العائد الإجمالي السنوي
        total_return = (equity_curve[-1] - equity_curve[0]) / equity_curve[0]
        annual_return = ((1 + total_return) ** (252 / len(returns))) - 1
        annual_return_percent = annual_return * 100
        
        # نسبة شارب
        sharpe_ratio = self._calculate_sharpe_ratio(returns)
        
        # نسبة سورتينو
        sortino_ratio = self._calculate_sortino_ratio(returns)
        
        # نسبة كالمار
        max_drawdown = other_metrics.get('max_drawdown_percent', 0.0) / 100
        calmar_ratio = annual_return / max_drawdown if max_drawdown > 0 else 0.0
        
        return {
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'annual_return_percent': annual_return_percent
        }
    
    def _calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """حساب نسبة شارب"""
        if not returns:
            return 0.0
        
        excess_returns = np.array(returns) - (risk_free_rate / 252)
        if np.std(excess_returns) == 0:
            return 0.0
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
        return float(sharpe)
    
    def _calculate_sortino_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """حساب نسبة سورتينو"""
        if not returns:
            return 0.0
        
        excess_returns = np.array(returns) - (risk_free_rate / 252)
        downside_returns = excess_returns[excess_returns < 0]
        
        if len(downside_returns) == 0 or np.std(downside_returns) == 0:
            return 0.0
        
        sortino = np.mean(excess_returns) / np.std(downside_returns) * np.sqrt(252)
        return float(sortino)
    
    def _calculate_timing_metrics(self, trades: List[Trade]) -> Dict[str, float]:
        """حساب مقاييس التوقيت"""
        if not trades:
            return {
                'avg_trade_duration_hours': 0.0,
                'median_trade_duration_hours': 0.0,
                'max_trade_duration_hours': 0.0,
                'min_trade_duration_hours': 0.0
            }
        
        completed_trades = [t for t in trades if t.exit_time and t.entry_time]
        
        if not completed_trades:
            return {
                'avg_trade_duration_hours': 0.0,
                'median_trade_duration_hours': 0.0,
                'max_trade_duration_hours': 0.0,
                'min_trade_duration_hours': 0.0
            }
        
        durations = []
        for trade in completed_trades:
            duration = (trade.exit_time - trade.entry_time).total_seconds() / 3600
            durations.append(duration)
        
        return {
            'avg_trade_duration_hours': float(np.mean(durations)),
            'median_trade_duration_hours': float(np.median(durations)),
            'max_trade_duration_hours': float(max(durations)),
            'min_trade_duration_hours': float(min(durations))
        }
    
    def _calculate_advanced_metrics(
        self,
        trades: List[Trade],
        equity_curve: List[float]
    ) -> Dict[str, float]:
        """حساب المقاييس المتقدمة"""
        if not trades or len(equity_curve) < 2:
            return {
                'system_quality_number': 0.0,
                'kelly_criterion': 0.0,
                'recovery_factor': 0.0,
                'ulcer_index': 0.0
            }
        
        completed_trades = [t for t in trades if t.exit_time and t.pnl is not None]
        
        if not completed_trades:
            return {
                'system_quality_number': 0.0,
                'kelly_criterion': 0.0,
                'recovery_factor': 0.0,
                'ulcer_index': 0.0
            }
        
        # حساب SQN (System Quality Number)
        sqn = self._calculate_sqn(completed_trades)
        
        # حساب معيار كيلي
        kelly = self._calculate_kelly_criterion(completed_trades)
        
        # حساب عامل الاسترداد
        recovery_factor = self._calculate_recovery_factor(equity_curve)
        
        # حساب مؤشر القرحة (Ulcer Index)
        ulcer_index = self._calculate_ulcer_index(equity_curve)
        
        return {
            'system_quality_number': sqn,
            'kelly_criterion': kelly,
            'recovery_factor': recovery_factor,
            'ulcer_index': ulcer_index
        }
    
    def _calculate_sqn(self, trades: List[Trade]) -> float:
        """حساب رقم جودة النظام"""
        if not trades:
            return 0.0
        
        # استخدم pnl_percentage بدلاً من pnl_percent
        pnls = [t.pnl_percentage / 100 if t.pnl_percentage is not None else 0 for t in trades]
        
        if len(pnls) < 2 or np.std(pnls) == 0:
            return 0.0
        
        mean_pnl = np.mean(pnls)
        std_pnl = np.std(pnls)
        sqn = (mean_pnl / std_pnl) * np.sqrt(len(pnls))
        
        return float(sqn)
    
    def _calculate_kelly_criterion(self, trades: List[Trade]) -> float:
        """حساب معيار كيلي"""
        if not trades:
            return 0.0
        
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl <= 0]
        
        if not winning_trades or not losing_trades:
            return 0.0
        
        win_rate = len(winning_trades) / len(trades)
        
        avg_win = np.mean([t.pnl_percentage / 100 if t.pnl_percentage else 0 for t in winning_trades])
        avg_loss = abs(np.mean([t.pnl_percentage / 100 if t.pnl_percentage else 0 for t in losing_trades]))
        
        if avg_loss == 0:
            return 0.0
        
        kelly = win_rate - ((1 - win_rate) / (avg_win / avg_loss))
        
        # تقييد بين 0 و 0.5 (نصف كيلي أكثر أماناً)
        return max(0.0, min(0.5, float(kelly)))
    
    def _calculate_recovery_factor(self, equity_curve: List[float]) -> float:
        """حساب عامل الاسترداد"""
        if len(equity_curve) < 2:
            return 0.0
        
        net_profit = equity_curve[-1] - equity_curve[0]
        max_dd = max(self._calculate_drawdowns(equity_curve))
        
        if max_dd == 0:
            return 0.0
        
        return float(net_profit / max_dd)
    
    def _calculate_drawdowns(self, equity_curve: List[float]) -> List[float]:
        """حساب الانخفاضات"""
        drawdowns = []
        peak = equity_curve[0]
        
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak if peak > 0 else 0
            drawdowns.append(drawdown)
        
        return drawdowns
    
    def _calculate_ulcer_index(self, equity_curve: List[float]) -> float:
        """حساب مؤشر القرحة"""
        if len(equity_curve) < 2:
            return 0.0
        
        drawdowns = self._calculate_drawdowns(equity_curve)
        squared_drawdowns = [dd ** 2 for dd in drawdowns]
        
        if not squared_drawdowns:
            return 0.0
        
        ulcer_index = np.sqrt(np.mean(squared_drawdowns)) * 100
        return float(ulcer_index)
