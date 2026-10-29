# trading_backend\app\backtest\reports.py
import json
import html as html_module
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
import plotly.graph_objects as go
import seaborn as sns
from io import BytesIO
import base64
import plotly.express as px
from plotly.subplots import make_subplots











from .schemas import BacktestResult, Trade

logger = logging.getLogger(__name__)

class ReportGenerator:
    """مولد تقارير الباك-تيست"""
    
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.template = "plotly_white"  # يمكن تغييرها إلى "plotly_dark" للمظهر الداكن
        
        # # إعداد الرسوم البيانية
        # plt.style.use('seaborn-v0_8-darkgrid')
        # sns.set_palette("husl")
    
    def generate_full_report(
        self,
        result: BacktestResult,
        include_charts: bool = True
    ) -> Dict[str, Any]:
        """توليد تقرير كامل"""
        report = {
            "metadata": self._generate_metadata(result),
            "summary": self._generate_summary(result),
            "performance_metrics": self._generate_performance_metrics(result),
            "trade_analysis": self._generate_trade_analysis(result),
            "risk_analysis": self._generate_risk_analysis(result),
            "periodic_analysis": self._generate_periodic_analysis(result),
            "symbol_analysis": self._generate_symbol_analysis(result)
        }
        
        if include_charts:
            report["charts"] = self._generate_charts(result)
        
        return report
    
    def _generate_metadata(self, result: BacktestResult) -> Dict[str, Any]:
        """توليد البيانات الوصفية"""
        return {
            "backtest_id": result.id,
            "name": result.config.name,
            "description": result.config.description,
            "timestamp": result.timestamp.isoformat(),
            "execution_time_seconds": result.execution_time_seconds,
            "period": {
                "start": result.config.start_date.isoformat(),
                "end": result.config.end_date.isoformat(),
                "days": (result.config.end_date - result.config.start_date).days
            },
            "market": result.config.market,
            "symbols": result.config.symbols,
            "timeframe": result.config.timeframe
        }
    
    def _generate_summary(self, result: BacktestResult) -> Dict[str, Any]:
        """توليد الملخص التنفيذي"""
        return {
            "capital": {
                "initial": result.initial_capital,
                "final": result.final_capital,
                "net_change": result.total_pnl,
                "net_change_percent": result.total_pnl_percent
            },
            "key_metrics": {
                "annual_return_percent": result.annual_return_percent,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown_percent": result.max_drawdown_percent,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor
            },
            "trades": {
                "total": result.total_trades,
                "winning": result.winning_trades,
                "losing": result.losing_trades,
                "avg_duration_hours": result.avg_trade_duration_hours
            }
        }
    
    def _generate_performance_metrics(self, result: BacktestResult) -> Dict[str, Any]:
        """توليد مقاييس الأداء"""
        return {
            "return_metrics": {
                "total_return_percent": result.total_pnl_percent,
                "annual_return_percent": result.annual_return_percent,
                "monthly_return_avg": self._calculate_average(result.monthly_returns.values()),
                "yearly_return_avg": self._calculate_average(result.yearly_returns.values())
            },
            "risk_adjusted_metrics": {
                "sharpe_ratio": result.sharpe_ratio,
                "sortino_ratio": result.sortino_ratio,
                "calmar_ratio": result.calmar_ratio,
                "profit_factor": result.profit_factor,
                "expectancy": result.expectancy
            },
            "advanced_metrics": {
                "system_quality_number": result.system_quality_number,
                "kelly_criterion": result.kelly_criterion,
                "recovery_factor": result.recovery_factor,
                "ulcer_index": result.ulcer_index
            }
        }
    
    def _generate_trade_analysis(self, result: BacktestResult) -> Dict[str, Any]:
        """تحليل الصفقات"""
        # ✅ BacktestResult (pydantic v2) لا يحمل حقل trades — نتحقق بأمان
        trades = getattr(result, "trades", None) or []
        if not trades:
            return {"trades": [], "statistics": {
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "expectancy": result.expectancy,
                "avg_winning_trade": result.avg_winning_trade,
                "avg_losing_trade": result.avg_losing_trade,
                "largest_winning_trade": result.largest_winning_trade,
                "largest_losing_trade": result.largest_losing_trade,
            }}
        
        trades_data = []
        for trade in trades:
            trades_data.append({
                "id": trade.id,
                "symbol": trade.symbol,
                "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
                "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                "position_type": trade.position_type,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "pnl": trade.pnl,
                "pnl_percent": trade.pnl_percent,
                "duration_hours": ((trade.exit_time - trade.entry_time).total_seconds() / 3600 
                                  if trade.exit_time and trade.entry_time else 0),
                "exit_reason": trade.exit_reason
            })
        
        # تحليل الإحصائيات
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl <= 0]
        
        best_trade = max(trades, key=lambda x: x.pnl or 0) if trades else None
        worst_trade = min(trades, key=lambda x: x.pnl or 0) if trades else None
        
        return {
            "trades": trades_data,
            "statistics": {
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "expectancy": result.expectancy,
                "avg_winning_trade": result.avg_winning_trade,
                "avg_losing_trade": result.avg_losing_trade,
                "largest_winning_trade": result.largest_winning_trade,
                "largest_losing_trade": result.largest_losing_trade,
                "best_trade": {
                    "id": best_trade.id if best_trade else None,
                    "pnl": best_trade.pnl if best_trade else None,
                    "symbol": best_trade.symbol if best_trade else None
                },
                "worst_trade": {
                    "id": worst_trade.id if worst_trade else None,
                    "pnl": worst_trade.pnl if worst_trade else None,
                    "symbol": worst_trade.symbol if worst_trade else None
                }
            }
        }
    
    def _generate_risk_analysis(self, result: BacktestResult) -> Dict[str, Any]:
        """تحليل المخاطر"""
        return {
            "drawdown_analysis": {
                "max_drawdown_percent": result.max_drawdown_percent,
                "max_drawdown_duration_days": result.max_drawdown_duration_days,
                "avg_drawdown": self._calculate_average(result.drawdown_curve),
                "drawdown_std": np.std(result.drawdown_curve) if result.drawdown_curve else 0
            },
            "volatility": {
                "annual_volatility_percent": result.volatility_annual,
                "daily_volatility_percent": result.volatility_annual / np.sqrt(252),
                "monthly_volatility_percent": result.volatility_annual / np.sqrt(12)
            },
            "value_at_risk": {
                "var_95_percent": result.var_95,
                "cvar_95_percent": result.cvar_95,
                "var_99_percent": result.var_95 * 1.5,  # تقدير
                "cvar_99_percent": result.cvar_95 * 1.5  # تقدير
            }
        }
    
    def _generate_periodic_analysis(self, result: BacktestResult) -> Dict[str, Any]:
        """تحليل الأداء الدوري"""
        return {
            "monthly_returns": result.monthly_returns,
            "yearly_returns": result.yearly_returns,
            "quarterly_analysis": self._analyze_quarterly(result),
            "weekly_analysis": self._analyze_weekly(result),
            "daily_analysis": self._analyze_daily(result)
        }
    
    def _generate_symbol_analysis(self, result: BacktestResult) -> Dict[str, Any]:
        """تحليل أداء الرموز"""
        return {
            "symbols_performance": result.symbols_performance,
            "best_performing_symbol": self._find_best_symbol(result),
            "worst_performing_symbol": self._find_worst_symbol(result),
            "correlation_analysis": self._analyze_correlations(result)
        }
    
    def _generate_charts(self, result: BacktestResult) -> Dict[str, str]:
        """توليد الرسوم البيانية"""
        charts = {}

        # ✅ try/except لكل رسم على حدة حتى لا يُسقط فشل واحد بقية الرسوم
        chart_builders = {
            "equity_curve": self._create_equity_chart,
            "drawdown_curve": self._create_drawdown_chart,
            "trades_distribution": self._create_trades_distribution_chart,
            "monthly_returns": self._create_monthly_returns_chart,
            "symbols_performance": self._create_symbols_performance_chart,
        }
        for name, builder in chart_builders.items():
            try:
                charts[name] = builder(result)
            except Exception as e:
                logger.warning(f"Chart '{name}' could not be generated: {e}")

        return charts
  


    def _create_equity_chart(self, result: BacktestResult) -> str:
        """إنشاء منحنى الأسهم باستخدام Plotly"""
        # حساب التواريخ (افتراضية)
        dates = pd.date_range(
            start=result.config.start_date,
            periods=len(result.equity_curve),
            freq='H'  # كل ساعة
        )
        
        fig = go.Figure()
        
        # إضافة منحنى الأسهم
        fig.add_trace(go.Scatter(
            x=dates,
            y=result.equity_curve,
            mode='lines',
            name='Equity',
            line=dict(color='blue', width=2),
            hovertemplate='تاريخ: %{x}<br>رأس المال: $%{y:,.0f}<extra></extra>'
        ))
        
        # خط رأس المال الأولي
        fig.add_hline(
            y=result.initial_capital,
            line_dash="dash",
            line_color="green",
            opacity=0.7,
            annotation_text=f'رأس المال الأولي (${result.initial_capital:,.0f})',
            annotation_position="bottom right"
        )
        
        # خط رأس المال النهائي
        fig.add_hline(
            y=result.final_capital,
            line_dash="dash",
            line_color="red",
            opacity=0.7,
            annotation_text=f'رأس المال النهائي (${result.final_capital:,.0f})',
            annotation_position="top right"
        )
        
        fig.update_layout(
            title=dict(
                text=f'منحنى الأسهم - {result.config.name}',
                font=dict(size=16, weight='bold')
            ),
            xaxis_title="التاريخ",
            yaxis_title="رأس المال ($)",
            hovermode="x unified",
            plot_bgcolor='white',
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        fig.update_xaxes(
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5
        )
        
        fig.update_yaxes(
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5,
            tickformat="$,.0f"
        )
        
        return self._plotly_fig_to_base64(fig)
    
    def _create_drawdown_chart(self, result: BacktestResult) -> str:
        """إنشاء منحنى الانخفاض باستخدام Plotly"""
        # حساب التواريخ (افتراضية)
        dates = pd.date_range(
            start=result.config.start_date,
            periods=len(result.drawdown_curve),
            freq='H'
        )
        
        fig = go.Figure()
        
        # إضافة منطقة الانخفاض
        fig.add_trace(go.Scatter(
            x=dates,
            y=result.drawdown_curve,
            fill='tozeroy',
            mode='lines',
            name='Drawdown',
            line=dict(color='red', width=1),
            fillcolor='rgba(255,0,0,0.3)',
            hovertemplate='تاريخ: %{x}<br>الانخفاض: %{y:.2f}%<extra></extra>'
        ))
        
        # إشارة إلى أقصى انخفاض
        max_dd_idx = np.argmax(result.drawdown_curve)
        max_dd_value = result.drawdown_curve[max_dd_idx]
        max_dd_date = dates[max_dd_idx]
        
        fig.add_trace(go.Scatter(
            x=[max_dd_date],
            y=[max_dd_value],
            mode='markers+text',
            name='أقصى انخفاض',
            marker=dict(
                color='darkred',
                size=12,
                symbol='circle'
            ),
            text=[f'أقصى انخفاض: {result.max_drawdown_percent:.2f}%'],
            textposition="top right",
            hovertemplate=f'أقصى انخفاض: {result.max_drawdown_percent:.2f}%<extra></extra>'
        ))
        
        fig.update_layout(
            title=dict(
                text='منحنى الانخفاض',
                font=dict(size=16, weight='bold')
            ),
            xaxis_title="التاريخ",
            yaxis_title="الانخفاض (%)",
            hovermode="x unified",
            plot_bgcolor='white',
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        fig.update_xaxes(
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5
        )
        
        fig.update_yaxes(
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5
        )
        
        return self._plotly_fig_to_base64(fig)
    
    def _create_trades_distribution_chart(self, result: BacktestResult) -> str:
        """إنشاء توزيع الصفقات باستخدام Plotly"""
        trades = getattr(result, "trades", None) or []
        if not trades:
            return ""
        
        # تجميع الربح/الخسارة للصفقات
        pnls = [t.pnl for t in trades if t.pnl is not None]
        
        if not pnls:
            return ""
        
        # إنشاء subplot بصفين
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('توزيع الربح/الخسارة', 'مخطط الصندوق للربح/الخسارة'),
            horizontal_spacing=0.15
        )
        
        # 1. توزيع الربح/الخسارة (Histogram)
        fig.add_trace(
            go.Histogram(
                x=pnls,
                nbinsx=30,
                name='التوزيع',
                marker_color='skyblue',
                marker_line_color='black',
                marker_line_width=1,
                opacity=0.7,
                hovertemplate='النطاق: %{x}<br>التكرار: %{y}<extra></extra>'
            ),
            row=1, col=1
        )
        
        # خط الصفر
        fig.add_vline(
            x=0,
            line_dash="dash",
            line_color="red",
            line_width=1,
            row=1, col=1
        )
        
        # 2. مخطط الصندوق (Box Plot)
        fig.add_trace(
            go.Box(
                y=pnls,
                name='P&L',
                boxpoints='outliers',
                marker_color='lightgreen',
                line_color='darkgreen',
                hovertemplate='القيمة: %{y}<br>الربح/الخسارة<extra></extra>'
            ),
            row=1, col=2
        )
        
        fig.update_layout(
            height=500,
            showlegend=False,
            plot_bgcolor='white',
            title=dict(
                text='تحليل توزيع الصفقات',
                font=dict(size=16, weight='bold')
            )
        )
        
        fig.update_xaxes(
            title_text="الربح/الخسارة ($)",
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5,
            row=1, col=1
        )
        
        fig.update_yaxes(
            title_text="التكرار",
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5,
            row=1, col=1
        )
        
        fig.update_xaxes(
            title_text="الربح/الخسارة ($)",
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5,
            row=1, col=2
        )
        
        fig.update_yaxes(
            title_text="",
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5,
            row=1, col=2
        )
        
        return self._plotly_fig_to_base64(fig)
    
    def _create_monthly_returns_chart(self, result: BacktestResult) -> str:
        """إنشاء مخطط العوائد الشهرية باستخدام Plotly"""
        if not result.monthly_returns:
            return ""
        
        months = list(result.monthly_returns.keys())
        returns = list(result.monthly_returns.values())
        
        # إنشاء ألوان حسب القيمة
        colors = ['green' if r >= 0 else 'red' for r in returns]
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=months,
            y=returns,
            name='العوائد الشهرية',
            marker_color=colors,
            text=[f'{r:.1f}%' for r in returns],
            textposition='auto',
            hovertemplate='الشهر: %{x}<br>العائد: %{y:.1f}%<extra></extra>'
        ))
        
        fig.add_hline(
            y=0,
            line_color="black",
            line_width=0.8
        )
        
        fig.update_layout(
            title=dict(
                text='العوائد الشهرية',
                font=dict(size=16, weight='bold')
            ),
            xaxis_title="الشهر",
            yaxis_title="العائد (%)",
            plot_bgcolor='white',
            showlegend=False
        )
        
        fig.update_xaxes(
            tickangle=45,
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5
        )
        
        fig.update_yaxes(
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5
        )
        
        return self._plotly_fig_to_base64(fig)
    
    def _create_symbols_performance_chart(self, result: BacktestResult) -> str:
        """إنشاء مخطط أداء الرموز باستخدام Plotly"""
        if not result.symbols_performance:
            return ""
        
        symbols = list(result.symbols_performance.keys())
        total_pnl = [perf.get('total_pnl_percent', 0) for perf in result.symbols_performance.values()]
        
        # إنشاء ألوان حسب القيمة
        colors = ['green' if p >= 0 else 'red' for p in total_pnl]
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=symbols,
            y=total_pnl,
            name='أداء الرموز',
            marker_color=colors,
            text=[f'{p:.1f}%' for p in total_pnl],
            textposition='auto',
            hovertemplate='الرمز: %{x}<br>إجمالي الربح/الخسارة: %{y:.1f}%<extra></extra>'
        ))
        
        fig.add_hline(
            y=0,
            line_color="black",
            line_width=0.8
        )
        
        fig.update_layout(
            title=dict(
                text='أداء الرموز',
                font=dict(size=16, weight='bold')
            ),
            xaxis_title="الرمز",
            yaxis_title="إجمالي الربح/الخسارة (%)",
            plot_bgcolor='white',
            showlegend=False
        )
        
        fig.update_xaxes(
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5
        )
        
        fig.update_yaxes(
            gridcolor='lightgray',
            griddash='dash',
            gridwidth=0.5
        )
        
        return self._plotly_fig_to_base64(fig)
    
    def _plotly_fig_to_base64(self, fig) -> str:
        """تحويل شكل Plotly إلى base64"""
        # تحويل الشكل إلى صورة PNG
        img_bytes = fig.to_image(format="png", width=1200, height=600, scale=2)
        
        # ترميز base64
        img_str = base64.b64encode(img_bytes).decode('utf-8')
        
        return img_str
    
    # دالة مساعدة للتحويل إلى HTML إذا لزم الأمر
    def _plotly_fig_to_html(self, fig) -> str:
        """تحويل شكل Plotly إلى HTML"""
        return fig.to_html(full_html=False, include_plotlyjs='cdn')    
    def _calculate_average(self, values) -> float:
        """حساب المتوسط (يتجاهل القيم غير العددية مثل قواميس _stats)"""
        if not values:
            return 0.0
        numeric = [float(v) for v in values if isinstance(v, (int, float, np.number)) and not isinstance(v, bool)]
        if not numeric:
            return 0.0
        return float(np.mean(numeric))
    
    def _find_best_symbol(self, result: BacktestResult) -> Optional[str]:
        """العثور على أفضل رمز أداءً"""
        if not result.symbols_performance:
            return None
        
        best_symbol = max(result.symbols_performance.items(), 
                         key=lambda x: x[1].get('total_pnl_percent', 0))
        return best_symbol[0]
    
    def _find_worst_symbol(self, result: BacktestResult) -> Optional[str]:
        """العثور على أسوأ رمز أداءً"""
        if not result.symbols_performance:
            return None
        
        worst_symbol = min(result.symbols_performance.items(), 
                          key=lambda x: x[1].get('total_pnl_percent', 0))
        return worst_symbol[0]
    
    def _analyze_correlations(self, result: BacktestResult) -> Dict[str, float]:
        """تحليل الارتباطات"""
        # في التطبيق الحقيقي، نحتاج إلى بيانات مفصلة لكل رمز
        return {}
    
    def _analyze_quarterly(self, result: BacktestResult) -> Dict[str, Any]:
        """تحليل الأداء الربع سنوي"""
        return {}
    
    def _analyze_weekly(self, result: BacktestResult) -> Dict[str, Any]:
        """تحليل الأداء الأسبوعي"""
        return {}
    
    def _analyze_daily(self, result: BacktestResult) -> Dict[str, Any]:
        """تحليل الأداء اليومي"""
        return {}
    
    def _render_html_report(self, result: BacktestResult, report: Dict[str, Any]) -> str:
        """تحويل التقرير إلى مستند HTML بسيط (مع الصور base64 إن وُجدت)"""
        e = html_module.escape

        def _rows(items: Dict[str, Any]) -> str:
            return "".join(
                f"<tr><th>{e(str(k))}</th><td>{e(str(v))}</td></tr>"
                for k, v in items.items()
                if not isinstance(v, dict)
            )

        charts = report.get("charts", {})

        # بناء أبسط وأوضح: جداول لكل قسم فرعي + الصور
        parts = [f"<h1>Backtest Report — {e(str(result.config.name))}</h1>"]
        for section_name, section_data in report.items():
            if section_name == "charts":
                continue
            parts.append(f"<h2>{e(section_name.replace('_', ' ').title())}</h2>")
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    parts.append(f"<h3>{e(str(key).replace('_', ' ').title())}</h3>")
                    if isinstance(value, dict):
                        parts.append(f"<table>{_rows(value)}</table>")
                    else:
                        parts.append(f"<p>{e(str(value))}</p>")
            else:
                parts.append(f"<p>{e(str(section_data))}</p>")

        if charts:
            parts.append("<h2>Charts</h2>")
            for chart_name, img_b64 in charts.items():
                if img_b64:
                    parts.append(
                        f'<h3>{e(chart_name.replace("_", " ").title())}</h3>'
                        f'<img src="data:image/png;base64,{img_b64}" '
                        f'style="max-width:100%;" alt="{e(chart_name)}"/>'
                    )

        return (
            "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>{e(str(result.config.name))} — Backtest Report</title>"
            "<style>body{font-family:sans-serif;margin:2rem;}"
            "table{border-collapse:collapse;}th,td{border:1px solid #ccc;padding:4px 10px;}"
            "th{text-align:left;background:#f5f5f5;}h2{border-bottom:1px solid #eee;}</style>"
            "</head><body>" + "".join(parts) + "</body></html>"
        )

    def save_report_to_file(
        self,
        result: BacktestResult,
        format: str = "json",
        include_charts: bool = True
    ) -> str:
        """حفظ التقرير إلى ملف (json أو html)"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # ✅ تعقيم اسم الملف (كان يُبنى من اسم الاستراتيجية كما هو)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in result.config.name) or "backtest"
        filename = f"backtest_report_{safe_name}_{timestamp}"

        report = self.generate_full_report(result, include_charts)
        fmt = (format or "json").lower()

        if fmt == "json":
            filepath = self.output_dir / f"{filename}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str, ensure_ascii=False)

        elif fmt == "html":
            # ✅ إصلاح: كان فرع HTML يكتب JSON بنفس صيغة فرع JSON (نسخ/لصق)
            filepath = self.output_dir / f"{filename}.html"
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self._render_html_report(result, report))

        else:
            raise ValueError(f"Unsupported format: {format}")

        return str(filepath)