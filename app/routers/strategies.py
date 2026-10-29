# app\routers\strategies.py

from datetime import datetime  # ✅ صحيح
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body, File, Request, UploadFile, Query
from typing import List, Dict, Any, Optional
import json
import tempfile
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from app.services.strategy import get_loaded_strategies, get_strategy_loader

from app.database import get_db
from app.services.data_service import DataService
from app.utils.dataframe_utils import ensure_datetime_index
from app.services.strategy import (
    run_strategy,
    validate_strategy_config,
    save_strategy,
    load_strategy_from_file,
    update_strategy,
    get_loaded_strategies,
    reload_strategy
)


import logging

# إنشاء logger خاص لهذا الملف
logger = logging.getLogger(__name__)

router = APIRouter(tags=["strategies"])

# إعداد الـ logger
logger = logging.getLogger(__name__)

@router.post("/run")
async def run_strategy_on_data(
    symbol: str,
    timeframe: str,
    market: str = "crypto",
    strategy_config: Dict[str, Any] = Body(...),
    days: int = 30,
    live_mode: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    تشغيل إستراتيجية على بيانات السوق
    """
    # تسجيل بداية الطلب
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    logger.info(f"[{request_id}] بدء طلب run_strategy_on_data", extra={
        "symbol": symbol,
        "timeframe": timeframe,
        "market": market,
        "days": days,
        "live_mode": live_mode,
        "strategy_name": strategy_config.get("name"),
        "config_keys": list(strategy_config.keys())
    })
    
    # تسجيل config كامل (بحد معقول)
    try:
        config_summary = json.dumps(strategy_config, default=str, ensure_ascii=False)[:500]
        logger.debug(f"[{request_id}] إستراتيجية config (مختصر): {config_summary}")
    except Exception as e:
        logger.warning(f"[{request_id}] فشل في تسجيل config: {str(e)}")
    
    data_service = DataService(db)
    
    try:
        # الحصول على البيانات
        logger.info(f"[{request_id}] جلب البيانات التاريخية...")
        start_time = datetime.now()
        
        dataframe = await data_service.get_historical(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            days=days
        )
        
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"[{request_id}] تم جلب البيانات بنجاح", extra={
            "data_shape": dataframe.shape if not dataframe.empty else "empty",
            "data_columns": list(dataframe.columns) if not dataframe.empty else [],
            "data_head": dataframe.head(3).to_dict() if not dataframe.empty else {},
            "elapsed_seconds": elapsed_time
        })
        
        if dataframe.empty:
            logger.error(f"[{request_id}] لا توجد بيانات متاحة", extra={
                "symbol": symbol,
                "timeframe": timeframe,
                "market": market,
                "days": days
            })
            raise HTTPException(status_code=404, detail="No data available")

        # ✅ Bugfix: الفهرس الرقمي (0..n) كان يُفسد مقاييس الإشارات
        # ((t2 - t1).total_seconds() على int) وترتيب الإشارات — نطبّع إلى
        # DatetimeIndex مثل محرك الباك تست قبل تمريرها للمحرك.
        dataframe = ensure_datetime_index(dataframe)

        # تشغيل الإستراتيجية
        logger.info(f"[{request_id}] تشغيل الإستراتيجية...")
        strategy_start = datetime.now()
        
        result = await run_strategy(dataframe, strategy_config, live_mode)
        
        strategy_elapsed = (datetime.now() - strategy_start).total_seconds()
        logger.info(f"[{request_id}] تم تشغيل الإستراتيجية بنجاح", extra={
            "total_signals": len(result.signals),
            "filtered_signals": len(result.filtered_signals),
            "strategy_time_seconds": strategy_elapsed,
            "metrics_keys": list(result.metrics.keys()) if result.metrics else []
        })
        
        # تحويل النتيجة إلى قاموس
        result_dict = {
            "signals": [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "action": s.action,
                    "price": s.price,
                    "reason": s.reason,
                    "rule_name": s.rule_name,
                    "strength": s.strength,
                    "metadata": s.metadata
                }
                for s in result.signals
            ],
            "filtered_signals": [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "action": s.action,
                    "price": s.price,
                    "reason": s.reason,
                    "rule_name": s.rule_name,
                    "strength": s.strength
                }
                for s in result.filtered_signals
            ],
            "metrics": result.metrics,
            "strategy_summary": {
                "name": strategy_config.get("name"),
                "total_indicators": len(strategy_config.get("indicators", [])),
                "total_entry_rules": len(strategy_config.get("entry_rules", [])),
                "total_exit_rules": len(strategy_config.get("exit_rules", []))
            }
        }
        
        # تسجيل النتيجة النهائية
        logger.info(f"[{request_id}] اكتمل الطلب بنجاح", extra={
            "total_signals_count": len(result_dict["signals"]),
            "filtered_signals_count": len(result_dict["filtered_signals"])
        })
        
        return result_dict
        
    except HTTPException as he:
        # إعادة HTTPException كما هي (لأن FastAPI يتعامل معها بشكل خاص)
        logger.error(f"[{request_id}] HTTP Exception: {he.detail}", extra={
            "status_code": he.status_code,
            "detail": he.detail
        })
        raise he
        
    except Exception as e:
        # تسجيل الخطأ بالتفصيل
        logger.error(f"[{request_id}] حدث خطأ غير متوقع", exc_info=True, extra={
            "error_type": type(e).__name__,
            "error_message": str(e),
            "symbol": symbol,
            "timeframe": timeframe,
            "market": market,
            "days": days,
            "live_mode": live_mode
        })
        
        # يمكنك إضافة logging إضافي للـ traceback
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"[{request_id}] Traceback:\n{error_trace}")
        
        raise HTTPException(status_code=500, detail=str(e))
    





    

@router.post("/validate")
async def validate_strategy_config_api(
    strategy_config: Dict[str, Any] = Body(...)
):
    """
    التحقق من صحة تكوين الإستراتيجية
    
    - **strategy_config**: تكوين الإستراتيجية المراد التحقق منها
    """
    validation_result = validate_strategy_config(strategy_config)
    
    if validation_result["valid"]:
        return {
            "valid": True,
            "message": "Strategy configuration is valid",
            "config_summary": {
                "name": validation_result["config"]["name"],
                "version": validation_result["config"]["version"],
                "indicators_count": len(validation_result["config"]["indicators"]),
                "entry_rules_count": len(validation_result["config"]["entry_rules"]),
                "exit_rules_count": len(validation_result["config"]["exit_rules"])
            }
        }
    else:
        return {
            "valid": False,
            "message": "Strategy configuration is invalid",
            "errors": validation_result["errors"]
        }

@router.post("/save")
async def save_strategy_api(
    strategy_config: Dict[str, Any] = Body(...),
    file_name: Optional[str] = None
):
    """
    حفظ إستراتيجية إلى ملف على القرص
    
    - **strategy_config**: تكوين الإستراتيجية
    - **file_name**: اسم الملف (اختياري)
    """
    try:
        file_path = save_strategy(strategy_config, file_name)
        
        return {
            "success": True,
            "message": "Strategy saved successfully",
            "file_path": file_path,
            "strategy_name": strategy_config.get("name")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload_strategy_file(
    file: UploadFile = File(...)
):
    """
    رفع ملف إستراتيجية وتحليله
    
    - **file**: ملف الإستراتيجية (JSON أو YAML)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    # التحقق من امتداد الملف
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ['.json', '.yaml', '.yml']:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Use JSON or YAML"
        )
    
    # قراءة المحتوى
    content = await file.read()
    
    try:
        if file_ext == '.json':
            strategy_config = json.loads(content.decode('utf-8'))
        else:
            
            strategy_config = yaml.safe_load(content.decode('utf-8'))
        
        # التحقق من الصحة
        validation_result = validate_strategy_config(strategy_config)
        
        if not validation_result["valid"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid strategy configuration: {validation_result['errors']}"
            )
        
        # تحميل الإستراتيجية
        with tempfile.NamedTemporaryFile(mode='w', suffix=file_ext, delete=False) as tmp:
            tmp.write(content.decode('utf-8'))
            tmp_path = tmp.name
        
        try:
            engine = load_strategy_from_file(tmp_path)
            strategy_summary = engine.get_strategy_summary()
            
            return {
                "success": True,
                "message": "Strategy uploaded and validated successfully",
                "strategy_summary": strategy_summary,
                "file_name": file.filename
            }
        finally:
            # تنظيف الملف المؤقت
            Path(tmp_path).unlink(missing_ok=True)
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/list")
async def list_loaded_strategies_api(
    active_only: bool = Query(False, description="عرض الإستراتيجيات النشطة فقط"),
    rescan: bool = Query(True, description="مسح مجلد strategies/ تلقائياً إذا كانت الذاكرة فارغة"),
):
    """
    سرد جميع الإستراتيجيات المحملة في الذاكرة

    - **active_only**: عرض الإستراتيجيات النشطة فقط
    - **rescan**: Bugfix — كانت القائمة فارغة دائماً لأن لا أحد يحمّل مجلد
      strategies/ من القرص. الآن عند فراغ الذاكرة يُمسح المجلد أولاً
      (idempotent، وقابل للتعطيل بـ ?rescan=false).
    """
    strategies = get_loaded_strategies()

    if not strategies and rescan:
        try:
            loader = get_strategy_loader()
            scan = loader.load_all_from_disk()
            if scan.get("failed"):
                logger.warning("Strategy disk scan had failures: %s", scan)
            strategies = get_loaded_strategies()
        except Exception:  # noqa: BLE001 — فشل المسح لا يكسر الاستجابة
            logger.exception("Strategy disk scan failed")

    if active_only:
        strategies = [s for s in strategies if s.get("is_active", True)]

    return {
        "count": len(strategies),
        "strategies": strategies
    }

@router.put("/update/{strategy_name}")
async def update_strategy_api(
    strategy_name: str,
    updates: Dict[str, Any] = Body(...)
):
    """
    تحديث إستراتيجية محملة
    
    - **strategy_name**: اسم الإستراتيجية
    - **updates**: التحديثات المطلوبة
    """
    engine = update_strategy(strategy_name, updates)
    
    if not engine:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
    
    return {
        "success": True,
        "message": f"Strategy '{strategy_name}' updated successfully",
        "strategy_summary": engine.get_strategy_summary()
    }

@router.post("/reload/{strategy_name}")
async def reload_strategy_api(strategy_name: str):
    """
    إعادة تحميل إستراتيجية من الملف
    
    - **strategy_name**: اسم الإستراتيجية
    """
    engine = reload_strategy(strategy_name)
    
    if not engine:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
    
    return {
        "success": True,
        "message": f"Strategy '{strategy_name}' reloaded successfully",
        "strategy_summary": engine.get_strategy_summary()
    }

@router.get("/examples/{example_name}")
async def get_strategy_example(example_name: str):
    """
    الحصول على مثال إستراتيجية جاهزة
    
    - **example_name**: اسم المثال (rsi_basic, macd_advanced, trend_following)
    """
    examples = {
        "rsi_basic": {
            "name": "RSI Basic Strategy",
            "description": "استراتيجية RSI بسيطة للدخول عند التشبع بالبيع والخروج عند التشبع بالشراء",
            "indicators": ["rsi"],
            "complexity": "beginner",
            "timeframe": "1h"
        },
        "macd_advanced": {
            "name": "MACD Advanced Strategy",
            "description": "استراتيجية MACD متقدمة مع تأكيد من RSI ومتوسطات متحركة",
            "indicators": ["macd", "rsi", "ema"],
            "complexity": "intermediate",
            "timeframe": "4h"
        },
        "trend_following": {
            "name": "Trend Following Strategy",
            "description": "استراتيجية تتبع الاتجاه باستخدام متوسطات متحركة متعددة",
            "indicators": ["sma", "ema", "atr"],
            "complexity": "advanced",
            "timeframe": "1d"
        }
    }
    
    if example_name not in examples:
        raise HTTPException(status_code=404, detail="Example not found")
    
    # استيراد المثال المطلوب
    try:
        if example_name == "rsi_basic":
            from app.services.strategy.strategys.rsi_strategy import get_rsi_strategy
            strategy_config = get_rsi_strategy()
        elif example_name == "macd_advanced":
            from app.services.strategy.strategys.macd_strategy import get_macd_strategy
            strategy_config = get_macd_strategy()
        else:
            # يمكن إضافة المزيد من الأمثلة هنا
            raise HTTPException(status_code=404, detail="Example implementation not found")
        
        return {
            "example_info": examples[example_name],
            "strategy_config": strategy_config
        }
        
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Could not load example: {str(e)}")
    

