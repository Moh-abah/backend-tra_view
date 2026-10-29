# app/routers/backtest1.py
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import math
from app.backtest.engine1 import BacktestEngine
from app.backtest.reports import ReportGenerator
from app.backtest.schemas import BacktestConfig, BacktestResult
from app.services.data_service import DataService
from app.database import get_db
from app.metrics.normalizer import MetricsNormalizer
from app.models.backtest_run import BacktestRun
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete as sqlalchemy_delete
from app.celery_app import celery_app
from celery.result import AsyncResult
from app.tasks.backtest_tasks import run_backtest_task 

router = APIRouter(tags=["backtest1"])
logger = logging.getLogger(__name__)

_backtest_engine = None
_report_generator = ReportGenerator()
_backtest_storage = {}  # {backtest_id: BacktestResult}
_engine_cache = None

async def get_backtest_from_db(backtest_id: str) -> Optional[BacktestResult]:
    """استرجاع نتيجة الباك-تست من التخزين المؤقت"""
    return _backtest_storage.get(backtest_id)


def get_backtest_engine(db) -> BacktestEngine:
    """Get or Create BacktestEngine"""
    global _backtest_engine
    if _backtest_engine is None:
        data_service = DataService(db)
        _backtest_engine = BacktestEngine(data_service)
    return _backtest_engine




def log_invalid_numbers(data, path="root"):
    if isinstance(data, dict):
        for k, v in data.items():
            log_invalid_numbers(v, f"{path}.{k}")
    elif isinstance(data, list):
        for i, v in enumerate(data):
            log_invalid_numbers(v, f"{path}[{i}]")
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            logger.error(f"❌ INVALID NUMBER FOUND | path={path} | value={data}")





@router.post("/run")
async def run_backtest(
    config: BacktestConfig = Body(...),
    # نتجاهل generate_report و save_to_file لأنها ستتم معالجتها داخل الـ worker أو لاحقاً
    db = Depends(get_db)
):
    """
    يرسل طلب الباك-تست إلى Celery Worker ويعود فوراً بـ task_id
    """
    try:
        logger.info(f"📤 Dispatching Backtest task to Celery: {config.name}")
        
        # إرسال المهمة للـ Worker
        task = run_backtest_task.delay(config.dict())
        
        return {
            "success": True,
            "message": "Backtest started successfully. Processing in background.",
            "task_id": task.id,
            "status": "PROCESSING"
        }
    except Exception as e:
        logger.error(f"Failed to dispatch task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# 2. نقطة لفحص حالة المهمة
# ==========================================
@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    

    task_result = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "state": task_result.state
    }
    
    if task_result.state == 'PENDING':
        response['message'] = "Task is waiting to be processed."
    elif task_result.state == 'PROGRESS':
        response['message'] = task_result.info.get('status', 'Processing...')
    elif task_result.state == 'SUCCESS':
        response['message'] = "Backtest completed successfully."
        response['result'] = task_result.result
    elif task_result.state == 'FAILURE':
        response['message'] = "Task failed."
        response['error'] = str(task_result.info)
        
    return response


# @router.post("/run")
# async def run_backtest(
#     config: BacktestConfig = Body(...),
#     generate_report: bool = Query(True),
#     save_to_file: bool = Query(False),
#     db = Depends(get_db)
# ):
#     """
#     تشغيل باك-تيست كامل (يعمل الآن كمحرك تنفيذ للقرارات)
#     """
#     try:
#         engine = get_backtest_engine(db)
        
#         strategy_name = config.strategy_config.get('name', 'Unknown') if config.strategy_config else 'Default'
#         logger.info(f"🚀 Starting Backtest for strategy: {strategy_name}")
        
#         # تشغيل المحرك (الذي سيقوم بإنشاء StrategyEngine داخلياً وتنفيذ القرارات)
#         result = await engine.run_backtest(config)

#         _backtest_storage[result.id] = result

        
#         response = {
#             "success": True,
#             "backtest_id": result.id,
#             "summary": {
#                 "name": config.name,
#                 "timeframe": config.timeframe,
#                 "initial_capital": result.initial_capital,
#                 "final_capital": result.final_capital,
#                 "total_pnl": result.total_pnl,
#                 "total_pnl_percent": result.total_pnl_percent,  # ★ الاسم الجديد
#                 "total_trades": result.total_trades,
#                 "winning_trades": result.winning_trades,
#                 "losing_trades": result.losing_trades,
#                 "win_rate": result.win_rate,
#                 "max_drawdown_percent": result.max_drawdown_percent,
#                 "sharpe_ratio": result.sharpe_ratio,
#                 "sortino_ratio": result.sortino_ratio,
#                 "calmar_ratio": result.calmar_ratio,
#                 "profit_factor": result.profit_factor,
#                 "expectancy": result.expectancy,
#                 "annual_return_percent": result.annual_return_percent,
#                 "execution_time_seconds": result.execution_time_seconds,
#                 "architecture_mode": "Strategy-Decision-Driven"
#             },
#             # بيانات إضافية يمكن استخدامها لاحقاً
#             "advanced_metrics": {
#                 "volatility_annual": result.volatility_annual,
#                 "var_95": result.var_95,
#                 "cvar_95": result.cvar_95,
#                 "system_quality_number": result.system_quality_number,
#                 "kelly_criterion": result.kelly_criterion
#             }
#         }
        
#         if hasattr(result, 'visual_candles'):
#             response["visual_candles_count"] = len(result.visual_candles)
#         if hasattr(result, 'trade_points'):
#             response["trade_points_count"] = len(result.trade_points)
        
#         # ==========================================
#         # ✅ إضافة كود الحفظ في قاعدة البيانات
#         # ==========================================
#         # ==========================================
#         # ✅ كود الحفظ المعدل (تعديل في السيف)
#         # ==========================================
#         try:
#             import json
#             from datetime import datetime
#             import pandas as pd
#             import numpy as np

#             # دالة مساعدة قوية لتنظيف البيانات قبل الحفظ
#             def clean_for_db(data):
#                 """
#                 تحويل البيانات إلى JSON ثم عودتها لقاموس.
#                 هذا يحل مشكلة datetime, timestamp, و numpy types المخفية.
#                 """
#                 class CleanEncoder(json.JSONEncoder):
#                     def default(self, obj):
                        
#                         # تحويل جميع أنواع التواريخ إلى نص ISO
#                         if isinstance(obj, (datetime, pd.Timestamp)):
                            
#                             return obj.isoformat()
#                         # تحويل أرقام numpy إلى float/int عادي
#                         if isinstance(obj, (np.integer, np.floating)):
#                             return float(obj)
                        

                        
#                         if isinstance(obj, np.ndarray):
#                             return obj.tolist()
#                         # للباقي
#                         return super().default(obj)
                
#                 # Roundtrip: dumps then loads
#                 return json.loads(json.dumps(data, cls=CleanEncoder))

#             # 1. تنظيف Summary
#             clean_summary = clean_for_db(response["summary"])

#             # 2. تجهيز وتنظيف Chart Data (الشموع + نقاط التداول)
#             # تحويل كائنات الشموع إلى قواميس أولاً
#             candles_as_dicts = []
#             for candle in result.visual_candles:
#                 if hasattr(candle, 'dict'):
#                     candles_as_dicts.append(candle.dict())
#                 elif hasattr(candle, '__dict__'):
#                     candles_as_dicts.append(candle.__dict__)
#                 else:
#                     candles_as_dicts.append(candle)
            
#             raw_chart_data = {
#                 "visual_candles": candles_as_dicts,
#                 "trade_points": result.trade_points
#             }
#             # تنظيف البيانات بالكامل
#             clean_chart_data = clean_for_db(raw_chart_data)

#             # 3. تنظيف Config (لأنه يحتوي على start_date و end_date)
#             clean_full_config = clean_for_db(config.dict())

#             # ✅ الحفظ الآن باستخدام البيانات المنظفة تماماً
#             db_backtest = BacktestRun(
#                 id=result.id,
#                 name=config.name,
#                 summary=clean_summary,          # ✅ تم التنظيف
#                 chart_data=clean_chart_data,    # ✅ تم التنظيف
#                 full_config=clean_full_config,  # ✅ تم التنظيف
#                 total_pnl_percent=result.total_pnl_percent,
#                 win_rate=result.win_rate,
#                 total_trades=result.total_trades,
#                 timeframe=config.timeframe,
#                 symbol=config.symbols[0] if config.symbols else "Unknown"
#             )
            
#             db.add(db_backtest)
#             await db.commit()
#             logger.error(f"DB state before commit | is_active={db.is_active} | in_transaction={db.in_transaction()} | bind={db.get_bind()}")

#             logger.info(f"✅ Backtest {result.id} saved to database successfully.")
            
#         except Exception as db_err:
#             logger.error(f"❌ Failed to save backtest to DB: {db_err}")
#             # لا نوقف العملية


#         if generate_report:
#             # التأكد من وجود دالة التوليد
#             try:
#                 report = _report_generator.generate_full_report(result, include_charts=True)
#                 response["report"] = report
                
#                 if save_to_file:
#                     filepath = _report_generator.save_report_to_file(result)
#                     response["report_file"] = filepath
#             except Exception as report_err:
#                 logger.warning(f"Failed to generate detailed report: {report_err}")
#                 response["report_note"] = "Report generation failed, but data is available in summary."


#         normalizer = MetricsNormalizer()
#         safe_response = normalizer.normalize(response)  # تمرير dict فقط
#         return safe_response        
#         # return response
        
#     except Exception as e:
#         logger.exception("Backtest execution failed")
#         raise HTTPException(status_code=500, detail=str(e))


























# ✅ 1. دالة مساعدة لتفكيك القواميس المتداخلة (مثل Bollinger Bands)
def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '_') -> Dict[str, Any]:
    """
    يحول قاموس متداخل مثل: {"bb": {"upper": 3000, "lower": 2900}}
    إلى قاموس مسطح مثل: {"bb_upper": 3000, "bb_lower": 2900}
    """
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items

@router.get("/{backtest_id}/chart-data")
async def get_chart_data(
    backtest_id: str,
    db: AsyncSession = Depends(get_db),
    start_index: int = Query(None), 
    limit: int = Query(None),
    include_indicators: Optional[List[str]] = Query(None)
):
    """
    جلب كامل بيانات الرسم البياني (Full Dump) - النسخة النهائية المحسنة
    """
    # 1. استرجاع الباك-تست
    # backtest = await get_backtest_from_db(backtest_id)


    query = select(BacktestRun).where(BacktestRun.id == backtest_id)
    result = await db.execute(query)
    backtest = result.scalar_one_or_none()

    if not backtest:
        raise HTTPException(status_code=404, detail="Backtest not found or expired")
    
    # 2. التحقق من وجود البيانات
    if not hasattr(backtest, 'visual_candles') or not backtest.visual_candles:
        raise HTTPException(status_code=404, detail="No chart data available")
    
    # 3. جلب البيانات
    all_candles = backtest.visual_candles
    all_trade_points = backtest.trade_points if hasattr(backtest, 'trade_points') else []
    
    # 4. تجهيز الشموع (Candle Processing)
    formatted_candles = []
    
    for candle in all_candles:
        # بناء جسم الشمعة (Basic Fields)
        formatted_candle = {
            "timestamp": candle.timestamp.isoformat() if hasattr(candle.timestamp, 'isoformat') else str(candle.timestamp),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            
            # بيانات الاستراتيجية
            "strategy_decision": candle.strategy_decision,
            "position_state": candle.position_state,
            "triggered_rules": getattr(candle, 'triggered_rules', []),
            "confidence": getattr(candle, 'confidence', None),
            
            # بيانات الصفقة
            "trade_action": getattr(candle, 'trade_action', None),
            "trade_id": getattr(candle, 'trade_id', None),
            "trade_price": getattr(candle, 'trade_price', None),
            "trade_size": getattr(candle, 'trade_size', None),
            
            # البيانات المالية
            "account_balance": getattr(candle, 'account_balance', None),
            "cumulative_pnl": getattr(candle, 'cumulative_pnl', None),
            "position_size": getattr(candle, 'position_size', None),
            "entry_price": getattr(candle, 'entry_price', None),
            "stop_loss": getattr(candle, 'stop_loss', None),
            "take_profit": getattr(candle, 'take_profit', None),
            "risk_reward_ratio": getattr(candle, 'risk_reward_ratio', None),
            "current_pnl": getattr(candle, 'current_pnl', None),
            "unrealized_pnl": getattr(candle, 'unrealized_pnl', None),
            "pnl": getattr(candle, 'pnl', None),
            "pnl_percentage": getattr(candle, 'pnl_percentage', None),
            
            # بيانات إضافية
            "market_condition": getattr(candle, 'market_condition', None),
            "signal_strength": getattr(candle, 'signal_strength', None),
            "price_change_percent": getattr(candle, 'price_change_percent', None),
            "volatility": getattr(candle, 'volatility', None),
            "leverage_used": getattr(candle, 'leverage_used', None),
            "margin_used": getattr(candle, 'margin_used', None),
            "free_margin": getattr(candle, 'free_margin', None),
            "return_on_investment": getattr(candle, 'return_on_investment', None),



            "volume_bar": getattr(candle, 'volume_bar', None),
            "climax_point": getattr(candle, 'climax_point', None)
        }
        
        # ✅ 5. معالجة المؤشرات (Indicators Handling Logic)
        if hasattr(candle, 'indicators') and candle.indicators:
            # نستخدم دالة flatten_dict لتفكيك أي بيانات متداخلة (مثل BB)
            flat_indicators = flatten_dict(candle.indicators)
            
            for ind_name, ind_value in flat_indicators.items():
                # التحقق من الفلترة
                if include_indicators is None or ind_name in include_indicators:
                    # ✅ التعامل مع أنواع البيانات المختلفة
                    if isinstance(ind_value, (float, int)):
                        formatted_candle[f"ind_{ind_name}"] = float(ind_value)
                    elif ind_value is None:
                        formatted_candle[f"ind_{ind_name}"] = None # سيظهر كـ null في JSON
                    else:
                        # إذا كانت قيمة نصية أو غير عددية (نادر في المؤشرات لكن احتياط)
                        formatted_candle[f"ind_{ind_name}"] = ind_value
        
        formatted_candles.append(formatted_candle)
    
    # 6. معالجة علامات التداول (Trade Markers)
    trade_markers = []
    if all_trade_points:
        for trade_point in all_trade_points:
            # تحديد الفهرس
            point_time = trade_point.get("timestamp")
            point_index = None
            if point_time:
                # بحث بسيط لتحديد مكان النقطة في الشارت
                for idx, candle in enumerate(all_candles):
                    if str(candle.timestamp) == str(point_time):
                        point_index = idx
                        break
            
            marker_data = {
                "timestamp": point_time.isoformat() if hasattr(point_time, 'isoformat') else str(point_time),
                "price": trade_point.get("price"),
                "type": trade_point.get("type"),
                "trade_id": trade_point.get("trade_id"),
                "position_type": trade_point.get("position_type"),
                "position_size": trade_point.get("position_size"),
                "exit_reason": trade_point.get("exit_reason"),
                "pnl": trade_point.get("pnl"),
                "pnl_percentage": trade_point.get("pnl_percentage"),
                "entry_price": trade_point.get("entry_price"),
                "exit_price": trade_point.get("exit_price"),
                "stop_loss": trade_point.get("stop_loss"),
                "take_profit": trade_point.get("take_profit"),
                "holding_period": trade_point.get("holding_period"),
                "risk_reward_ratio": trade_point.get("risk_reward_ratio"),
                "commission": trade_point.get("commission"),
                "account_balance_before": trade_point.get("account_balance_before"),
                "account_balance_after": trade_point.get("account_balance_after"),
                "cumulative_pnl": trade_point.get("cumulative_pnl"),
                "index": point_index,
                "decision_reason": trade_point.get("decision_reason"),
                "confidence": trade_point.get("confidence")
            }
            
            # إضافة صورة المؤشرات
            if "indicators_snapshot" in trade_point:
                marker_data["indicators_snapshot"] = trade_point["indicators_snapshot"]
                
            trade_markers.append(marker_data)
    
    # 7. جمع أسماء المؤشرات المتاحة (باستخدام آخر شمعة كمرجع)
    available_indicators = []
    if formatted_candles:
        available_indicators = [key.replace("ind_", "") for key in formatted_candles[0].keys() if key.startswith("ind_")]

    # 8. بناء الاستجابة النهائية
    response = {
        "backtest_id": backtest_id,
        "metadata": {
            "name": backtest.config.name if hasattr(backtest, 'config') else "Backtest",
            "symbol": backtest.config.symbols[0] if hasattr(backtest, 'config') and backtest.config.symbols else "Unknown",
            "timeframe": backtest.config.timeframe,
            "initial_capital": backtest.initial_capital,
            "final_capital": backtest.final_capital,
            "total_pnl": backtest.total_pnl,
            "total_pnl_percent": backtest.total_pnl_percent,
            "total_trades": backtest.total_trades,
            "win_rate": backtest.win_rate,
            "start_date": formatted_candles[0]['timestamp'] if formatted_candles else None,
            "end_date": formatted_candles[-1]['timestamp'] if formatted_candles else None
        },
        "chart_data": {
            "candles": formatted_candles,
            "trade_markers": trade_markers,
            "available_indicators": available_indicators,
            "total_candles": len(all_candles),
            "total_trades": len(trade_markers)
        },
        "summary": {
            "total_candles": len(all_candles),
            "total_trades": backtest.total_trades,
            "win_rate": backtest.win_rate,
            "total_pnl": backtest.total_pnl,
            "total_pnl_percent": backtest.total_pnl_percent,
            "max_drawdown_percent": backtest.max_drawdown_percent,
            "sharpe_ratio": backtest.sharpe_ratio,
            "sortino_ratio": backtest.sortino_ratio,
            "calmar_ratio": backtest.calmar_ratio,
            "profit_factor": backtest.profit_factor,
            "annual_return_percent": backtest.annual_return_percent,
            "visible_range": f"0-{len(all_candles)}",
            "has_more_data": False
        }
    }
    
    # إضافة البيانات الإضافية
    if hasattr(backtest, 'equity_curve'):
        response["equity_curve"] = backtest.equity_curve
    if hasattr(backtest, 'drawdown_curve'):
        response["drawdown_curve"] = backtest.drawdown_curve
    

    normalizer = MetricsNormalizer()
    safe_response = normalizer.normalize(response)  # تمرير dict فقط
    return safe_response    









@router.get("/list")
async def list_backtests(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    جلب قائمة بجميع عمليات الباك测试 المخزنة (مفيد للوحة التحكم)
    """
    try:
        # الاستعلام عن الباك测试 مرتبة من الأحدث للأقدم
        query = select(BacktestRun).order_by(BacktestRun.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        backtests = result.scalars().all()
        
        backtests_list = []
        for bt in backtests:
            backtests_list.append({
                "id": bt.id,
                "name": bt.name,
                "created_at": bt.created_at.isoformat() if bt.created_at else None,
                "summary_stats": {
                    "total_pnl_percent": bt.total_pnl_percent,
                    "win_rate": bt.win_rate,
                    "total_trades": bt.total_trades,
                    "timeframe": bt.timeframe,
                    "symbol": bt.symbol
                }
            })
            
        return {
            "success": True,
            "count": len(backtests_list),
            "data": backtests_list
        }
    except Exception as e:
        logger.error(f"Error listing backtests: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get/{backtest_id}")
async def get_backtest_details(
    backtest_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    جلب تفاصيل باك测试 محدد مع بيانات الشارت (الشموع) بالكامل
    هذا هو البديل الدائم للـ storage المؤقت
    """
    try:
        # البحث في قاعدة البيانات
        query = select(BacktestRun).where(BacktestRun.id == backtest_id)
        result = await db.execute(query)
        backtest = result.scalar_one_or_none()
        
        if not backtest:
            # إذا لم يجد في قاعدة البيانات، يمكنه البحث في الذاكرة المؤقتة كاحتياطي (اختياري)
            mem_result = _backtest_storage.get(backtest_id)
            if mem_result:
                # منطق إرجاع البيانات من الذاكرة (كما كان كودك السابق)
                # سنكتفي هنا برفع خطأ 404 لأن الهدف هو التخزين الدائم
                pass
            raise HTTPException(status_code=404, detail="Backtest not found in database")
        
        # تجهيز البيانات للإرجاع بنفس الشكل الذي طلبه المستخدم
        response_data = {
            "success": True,
            "backtest_id": backtest.id,
            "name": backtest.name,
            "created_at": backtest.created_at.isoformat(),
            
            # إرجاع الملخص المحفوظ
            "summary": backtest.summary,
            
            # إرجاع بيانات الشارت (الشموع) - هذا هو الجزء المهم
            "chart_data": backtest.chart_data,

            "config": backtest.full_config
        }
        
        
        
    # ✅ معالجة وتنسيق بيانات الشارت (Processing)
        # ==========================================
         # ==========================================
        
        # نسخة عميقة لتجنب تعديل البيانات الأصلية في الذاكرة إذا لزم الأمر
        chart_data = backtest.chart_data.copy() if backtest.chart_data else {}
        
        # التأكد من وجود الشموع
        if "visual_candles" in chart_data and isinstance(chart_data["visual_candles"], list):
            processed_candles = []
                   

            for candle in chart_data["visual_candles"]:
                # إنشاء نسخة من الشمعة للتعديل عليها
                formatted_candle = candle.copy()
                
                # 1. استخراج المؤشرات المتداخلة (nested)
                indicators_data = formatted_candle.pop("indicators", {})
                
                # 2. تسطيح المؤشرات (Flattening) باستخدام الدالة المساعدة الموجودة
                # تحول { "bb": { "upper": 3000 } } إلى { "bb_upper": 3000 }
                flat_indicators = flatten_dict(indicators_data)
                
                # 3. دمج المؤشرات المسطحة في الشمعة وإضافة البادئة ind_
                for key, value in flat_indicators.items():
                    formatted_candle[f"ind_{key}"] = value
                
                processed_candles.append(formatted_candle)
            
            # تحديث قائمة الشموع بالنسخة المنسقة
            chart_data["visual_candles"] = processed_candles

        # إضافة البيانات المعدلة للاستجابة
        response_data["chart_data"] = chart_data
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting backtest details: {e}")
        raise HTTPException(status_code=500, detail=str(e))







@router.delete("/delete/{backtest_id}")
async def delete_backtest_run(
    backtest_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    حذف نتيجة باك-تست محددة من قاعدة البيانات
    """
    try:
        # البحث عن السجل
        query = select(BacktestRun).where(BacktestRun.id == backtest_id)
        result = await db.execute(query)
        backtest = result.scalar_one_or_none()
        
        if not backtest:
            raise HTTPException(status_code=404, detail="Backtest not found")
        
        # حذف السجل
        await db.delete(backtest)
        await db.commit()
        
        return {
            "success": True,
            "message": f"Backtest '{backtest.name}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting backtest: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/walk-forward")
async def run_walk_forward_analysis(
    config: BacktestConfig = Body(...),
    periods: int = Query(5, ge=2, le=20),
    db = Depends(get_db)
):
    """
    تشغيل تحليل مشي للأمام (يدعمه المحرك الجديد)
    """
    try:
        engine = get_backtest_engine(db)
        logger.info(f"Starting Walk-Forward Analysis ({periods} periods)...")
        
        results = await engine.run_walk_forward_analysis(config, periods)
        
        periods_summary = []
        for i, res in enumerate(results):
            periods_summary.append({
                "period": i + 1,
                "start_date": res.config.start_date.isoformat(),
                "end_date": res.config.end_date.isoformat(),
                "pnl_percent": res.total_pnl_percent,
                "win_rate": res.win_rate
            })
        
        return {
            "success": True,
            "periods_summary": periods_summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/monte-carlo")
async def run_monte_carlo_simulation(
    config: BacktestConfig = Body(...),
    simulations: int = Query(1000, ge=100, le=10000),
    db = Depends(get_db)
):
    """
    تشغيل محاكاة مونت كارلو
    """
    try:
        engine = get_backtest_engine(db)
        results = await engine.run_monte_carlo_simulation(config, simulations)
        
        return {
            "success": True,
            "results": results,
            "interpretation": {
                "probability_of_profit": f"{results['probability_profit'] * 100:.1f}%"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics")
async def get_available_metrics():
    """الحصول على مقاييس متاحة"""
    return {
        "return_metrics": ["total_pnl", "sharpe_ratio", "win_rate"],
        "risk_metrics": ["max_drawdown", "volatility"],
        "trade_metrics": ["total_trades", "avg_win", "avg_loss"]
    }
