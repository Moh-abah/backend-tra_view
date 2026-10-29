# app/routers/strategies1.py
from datetime import datetime, timedelta, timezone
from sqlalchemy.future import select
from fastapi import APIRouter, Depends, HTTPException, Body, File, Query,UploadFile, File
from typing import List, Dict, Any, Optional
import json
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
import yaml

from app.database import get_db
from app.services.data_service import DataService
from app.utils.dataframe_utils import ensure_datetime_index
# ✅ تحديث الاستيرادات لاستخدام المحرك الجديد والكيانات
from app.services.strategy.strategy_engine1 import StrategyEngine, Decision, DecisionAction

from app.services.strategy.schemas import StrategyConfig as StrategyConfigSchema
from app.models.strategy import Strategy as StrategyModel 
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["strategies1"])


# ====================== إدارة الاستراتيجيات في قاعدة البيانات ======================

@router.post("/save_to_db")
async def save_strategy_to_database(
    strategy_config: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    حفظ إستراتيجية في قاعدة البيانات
    """
    try:
        # التحقق من صحة تكوين الإستراتيجية
        valid_config = StrategyConfigSchema(**strategy_config)
        
        # التحقق من عدم وجود استراتيجية بنفس الاسم
        existing_query = select(StrategyModel).where(StrategyModel.name == valid_config.name)
        existing_result = await db.execute(existing_query)
        existing_strategy = existing_result.scalar_one_or_none()
        
        if existing_strategy:
            # تحديث الاستراتيجية الموجودة
            existing_strategy.config = json.dumps(strategy_config, ensure_ascii=False)
            existing_strategy.version = valid_config.version
            existing_strategy.description = valid_config.description
            existing_strategy.updated_at = datetime.utcnow()
        else:
            # إنشاء استراتيجية جديدة
            new_strategy = StrategyModel(
                name=valid_config.name,
                version=valid_config.version,
                description=valid_config.description,
                config=json.dumps(strategy_config, ensure_ascii=False),
                author=strategy_config.get("author", "unknown"),
                base_timeframe=valid_config.base_timeframe,
                position_side=valid_config.position_side.value,
                is_active=True
            )
            db.add(new_strategy)
        
        await db.commit()
        
        return {
            "success": True,
            "message": "Strategy saved to database successfully",
            "strategy_name": valid_config.name,
            "version": valid_config.version
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error saving strategy to database: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving strategy: {str(e)}")





@router.get("/list_from_db")
async def list_strategies_from_database(
    db: AsyncSession = Depends(get_db),
    active_only: bool = True
):
    """
    قائمة جميع الاستراتيجيات المحفوظة في قاعدة البيانات
    """
    try:
        query = select(StrategyModel)
        if active_only:
            query = query.where(StrategyModel.is_active == True)
        
        result = await db.execute(query)
        strategies = result.scalars().all()
        
        strategies_list = []
        for strategy in strategies:
            # تحويل JSON المخزن إلى dict
            config_dict = json.loads(strategy.config)
            
            # استخراج المعلومات المطلوبة من config
            indicators = config_dict.get("indicators", [])
            entry_rules = config_dict.get("entry_rules", [])
            exit_rules = config_dict.get("exit_rules", [])
            filter_rules = config_dict.get("filter_rules", [])
            
            # جمع المؤشرات مع أطرها الزمنية فقط
            indicator_list = []
            for indicator in indicators:
                if isinstance(indicator, dict):
                    indicator_name = indicator.get("name", "Unknown")
                    indicator_timeframe = indicator.get("timeframe", strategy.base_timeframe)
                    indicator_list.append({
                        "name": indicator_name,
                        "timeframe": indicator_timeframe
                    })
            
            # جمع الأطر الزمنية الفريدة
            unique_timeframes = list(set([ind["timeframe"] for ind in indicator_list]))
            
            # حساب عدد المؤشرات والقواعد
            indicators_count = len(indicators) if isinstance(indicators, list) else 0
            entry_rules_count = len(entry_rules) if isinstance(entry_rules, list) else 0
            exit_rules_count = len(exit_rules) if isinstance(exit_rules, list) else 0
            filter_rules_count = len(filter_rules) if isinstance(filter_rules, list) else 0
            
            strategies_list.append({
                "id": strategy.id,
                "name": strategy.name,
                "version": strategy.version,
                "description": strategy.description,
                "author": strategy.author,
                "base_timeframe": strategy.base_timeframe,
                "position_side": strategy.position_side,
                "is_active": strategy.is_active,
                "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
                "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
                # المعلومات الجديدة
                "indicators_count": indicators_count,
                "entry_rules_count": entry_rules_count,
                "exit_rules_count": exit_rules_count,
                "filter_rules_count": filter_rules_count,
                "total_rules_count": entry_rules_count + exit_rules_count + filter_rules_count,
                # جميع المؤشرات مع أطرها الزمنية
                "indicators": indicator_list,
                # الأطر الزمنية الفريدة
                "indicator_timeframes": unique_timeframes,
                "has_indicators": indicators_count > 0,
                "has_rules": (entry_rules_count + exit_rules_count + filter_rules_count) > 0
            })
        
        return {
            "success": True,
            "strategies": strategies_list,
            "count": len(strategies_list)
        }
        
    except Exception as e:
        logger.error(f"Error listing strategies: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing strategies: {str(e)}")

@router.get("/get_from_db/{strategy_name}")
async def get_strategy_from_database(
    strategy_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    جلب استراتيجية محددة من قاعدة البيانات
    """
    try:
        query = select(StrategyModel).where(StrategyModel.name == strategy_name)
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
        
        # تحويل JSON المخزن إلى dict
        config_dict = json.loads(strategy.config)
        
        return {
            "success": True,
            "strategy": {
                "id": strategy.id,
                "name": strategy.name,
                "version": strategy.version,
                "description": strategy.description,
                "author": strategy.author,
                "base_timeframe": strategy.base_timeframe,
                "position_side": strategy.position_side,
                "is_active": strategy.is_active,
                "config": config_dict,
                "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
                "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting strategy: {str(e)}")

@router.delete("/delete_from_db/{strategy_name}")
async def delete_strategy_from_database(
    strategy_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    حذف استراتيجية من قاعدة البيانات
    """
    try:
        query = select(StrategyModel).where(StrategyModel.name == strategy_name)
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
        
        await db.delete(strategy)
        await db.commit()
        
        return {
            "success": True,
            "message": f"Strategy '{strategy_name}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting strategy: {str(e)}")

@router.put("/update_in_db/{strategy_name}")
async def update_strategy_in_database(
    strategy_name: str,
    strategy_config: Dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    تحديث استراتيجية في قاعدة البيانات
    """
    try:
        # التحقق من صحة التكوين الجديد
        valid_config = StrategyConfigSchema(**strategy_config)
        
        query = select(StrategyModel).where(StrategyModel.name == strategy_name)
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
        
        # تحديث البيانات
        strategy.config = json.dumps(strategy_config, ensure_ascii=False)
        strategy.version = valid_config.version
        strategy.description = valid_config.description
        strategy.base_timeframe = valid_config.base_timeframe
        strategy.position_side = valid_config.position_side.value
        strategy.updated_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Strategy '{strategy_name}' updated successfully",
            "version": valid_config.version
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating strategy: {str(e)}")

# ====================== تشغيل الاستراتيجية من قاعدة البيانات ======================

@router.post("/run_from_db")
async def run_strategy_from_database(
    symbol: str,
    timeframe: str,
    strategy_name: str,
    market: str = "crypto",
    days: int = 30,
    live_mode: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    تشغيل استراتيجية محفوظة في قاعدة البيانات
    """
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    logger.info(f"[{request_id}] بدء تشغيل استراتيجية من قاعدة البيانات", extra={
        "symbol": symbol, "timeframe": timeframe, "strategy": strategy_name
    })
    
    data_service = DataService(db)
    
    try:
        # 1. جلب الاستراتيجية من قاعدة البيانات
        query = select(StrategyModel).where(StrategyModel.name == strategy_name)
        result = await db.execute(query)
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found in database")
        
        if not strategy.is_active:
            raise HTTPException(status_code=400, detail=f"Strategy '{strategy_name}' is not active")
        
        # تحويل JSON المخزن إلى dict
        strategy_config = json.loads(strategy.config)
        
        # 2. جلب البيانات
        dataframe = await data_service.get_historical(
            symbol=symbol, timeframe=timeframe, market=market, days=days
        )

        if dataframe.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # ✅ Bugfix: DataService يعيد فهرساً رقمياً (0..n) — ومحرك القرارات
        # ينشئ Decision(timestamp=data.index[i]) فينهار لاحقاً عند
        # isoformat(). نطبّع الفهرس إلى DatetimeIndex مركزياً هنا.
        dataframe = ensure_datetime_index(dataframe)
        
        # 3. إنشاء محرك الاستراتيجية
        try:
            schema_config = StrategyConfigSchema(**strategy_config)
            strategy_engine = StrategyEngine(schema_config)
        except Exception as e:
            logger.error(f"[{request_id}] خطأ في تكوين الاستراتيجية: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid strategy configuration: {e}")

        decisions = []
        
        # 4. محاكاة الزمن
        for i in range(len(dataframe)):
            # مراعاة الحد الأدنى للبيانات لحساب المؤشرات
            if i < 50: 
                continue

            current_context = dataframe.iloc[:i+1]
            
            try:
                # طلب القرار من المحرك
                decision = await strategy_engine.run(current_context, in_position=True)  # معاينة: قيّم الخروج والدخول معاً
                
                decisions.append({
                    "timestamp": decision.timestamp.isoformat(),
                    "action": decision.action.value,  # BUY, SELL, HOLD
                    "confidence": decision.confidence,
                    "reason": decision.reason,
                    "metadata": decision.metadata
                })
                
            except Exception as inner_e:
                logger.warning(f"فشل في اتخاذ قرار في الشمعة {i}: {inner_e}")
                # إضافة قرار افتراضي لحفظ تسلسل الوقت
                decisions.append({
                    "timestamp": dataframe.index[i].isoformat(),
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "Error",
                    "metadata": {}
                })

        # 5. تجهيز الرد
        active_decisions = [d for d in decisions if d['action'] in ['BUY', 'SELL']]

        logger.info(f"[{request_id}] اكتمل التنفيذ من قاعدة البيانات", extra={
            "total_decisions": len(decisions),
            "active_decisions": len(active_decisions)
        })
        
        return {
            "request_id": request_id,
            "strategy_id": strategy.id,
            "strategy_name": strategy.name,
            "strategy_version": strategy.version,
            "symbol": symbol,
            "timeframe": timeframe,
            "total_bars_processed": len(decisions),
            "active_decisions_count": len(active_decisions),
            "decisions": decisions,
            "active_decisions_summary": active_decisions
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[{request_id}] خطأ غير متوقع: {e}")
        raise HTTPException(status_code=500, detail=str(e))







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
    تشغيل الاستراتيجية على بيانات السوق وإرجاع القرارات (Decisions).
    
    ملاحظة: بما أن الاستراتيجية عبارة عن Black Box تقوم بإرجاع قرار واحد لكل لحظة،
    سنقوم هنا بمحاكاة الزمن (Loop) لجمع القرارات عبر الفترة الزمنية المطلوبة.
    """
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    logger.info(f"[{request_id}] بدء طلب تشغيل استراتيجية (Black Box Mode)", extra={
        "symbol": symbol, "timeframe": timeframe, "strategy": strategy_config.get("name")
    })
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    data_service = DataService(db)
    
    try:
        # 1. جلب البيانات
        # dataframe = await data_service.get_historicallastvirsion(
        #     symbol=symbol, timeframe=timeframe, market=market, days=days
        # )
        dataframe = await data_service.get_historicallastvirsion(
            symbol=symbol,
            timeframe=timeframe,
            market=market,
            start_date=start_date,
            end_date=end_date
        )        

        if dataframe.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # ✅ Bugfix: تطبيع الفهرس الزمني (نفس سبب run_from_db أعلاه) —
        # القرارات timestamp=data.index[i] يجب أن تكون datetimes لا أعداداً.
        dataframe = ensure_datetime_index(dataframe)
        
        # 2. إنشاء محرك الاستراتيجية (Black Box)
        try:
            schema_config = StrategyConfigSchema(**strategy_config)
            strategy_engine = StrategyEngine(schema_config)
        except Exception as e:
            logger.error(f"[{request_id}] خطأ في تكوين الاستراتيجية: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid strategy configuration: {e}")


        decisions = []
        
     
        for i in range(len(dataframe)):
            # مراعاة الحد الأدنى للبيانات لحساب المؤشرات
            if i < 50: continue 


            current_context = dataframe.iloc[:i+1]
            
            try:
                # طلب القرار من المحرك
                decision = await strategy_engine.run(current_context, in_position=True)  # معاينة: قيّم الخروج والدخول معاً
                ts = decision.timestamp
                if isinstance(ts, int):
                    ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                elif not isinstance(ts, datetime):
                    ts = datetime.now(timezone.utc)

                decisions.append({
                    "timestamp": ts.isoformat(),
                    "action": decision.action.value,      # BUY, SELL, HOLD
                    "confidence": decision.confidence,
                    "reason": decision.reason,
                    "metadata": decision.metadata
                })
                
            except Exception as inner_e:
                logger.warning(f"فشل في اتخاذ قرار في الشمعة {i}: {inner_e}")
                # إضافة قرار افتراضي لحفظ تسلسل الوقت
                decisions.append({
                    "timestamp": dataframe.index[i].isoformat(),
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "Error",
                    "metadata": {}
                })

        # 4. تجهيز الرد
        # سنقوم بفلترة النتائج لإرجاع فقط الإشارات المهمة (BUY/SELL) لتسهيل القراءة
        active_decisions = [d for d in decisions if d['action'] in ['BUY', 'SELL']]

        logger.info(f"[{request_id}] اكتمل التنفيذ، تم توليد {len(decisions)} قرار، منها {len(active_decisions)} نشط")
        
        return {
            "request_id": request_id,
            "symbol": symbol,
            "timeframe": timeframe,
            "total_bars_processed": len(decisions),
            "active_decisions_count": len(active_decisions),
            "decisions": decisions, # يمكن إرجاع الكل أو فقط active_decisions حسب الحاجة
            "active_decisions_summary": active_decisions # ملخص سريع
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"خطأ غير متوقع: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/validate")
async def validate_strategy_config_api(
    strategy_config: Dict[str, Any] = Body(...)
):
    """
    التحقق من صحة تكوين الإستراتيجية باستخدام Pydantic Schema
    """
    try:
        # محاولة تحويل القاموس إلى Schema صالح
        valid_config = StrategyConfigSchema(**strategy_config)
        return {
            "valid": True,
            "message": "Strategy configuration is valid",
            "config_summary": {
                "name": valid_config.name,
                "version": valid_config.version,
                "indicators_count": len(valid_config.indicators),
                "entry_rules_count": len(valid_config.entry_rules),
                "exit_rules_count": len(valid_config.exit_rules)
            }
        }
    except Exception as e:
        return {
            "valid": False,
            "message": "Validation failed",
            "errors": str(e)
        }

@router.post("/save")
async def save_strategy_api(
    strategy_config: Dict[str, Any] = Body(...),
    file_name: Optional[str] = None
):
    """
    حفظ إستراتيجية
    """
    try:
        # نتحقق من الصحة قبل الحفظ
        StrategyConfigSchema(**strategy_config)
        
        # سنقوم بمحاكاة الحفظ (حيث أن دالة save_strategy غير موجودة في السياق الحالي)
        # في التطبيق الحقيقي ستستدعي دالة الخدمة
        if not file_name:
            file_name = f"{strategy_config.get('name', 'strategy')}.json"
            
        # محاكاة مسار الحفظ
        file_path = f"./strategies/{file_name}"
        
        # كتابة الملف
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(strategy_config, f, indent=4, default=str)
            
        return {
            "success": True,
            "message": "Strategy saved successfully",
            "file_path": file_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload_strategy_file(
    file: UploadFile = File(...)
):
    """
    رفع ملف إستراتيجية
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")
    
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ['.json', '.yaml', '.yml']:
        raise HTTPException(status_code=400, detail="Use JSON or YAML")
    
    content = await file.read()
    
    try:
        if file_ext == '.json':
            strategy_config = json.loads(content.decode('utf-8'))
        else:
            strategy_config = yaml.safe_load(content.decode('utf-8'))
        
        # التحقق من الصحة باستخدام Schema
        valid_config = StrategyConfigSchema(**strategy_config)
        
        # ملاحظة: في المحرك الجديد لا توجد دالة get_strategy_summary داخل المحرك
        # لأنه Black Box بسيط، لذا نأخذ الملخص من التكوين نفسه
        summary = {
            "name": valid_config.name,
            "version": valid_config.version,
            "description": valid_config.description,
            "indicators_count": len(valid_config.indicators),
            "rules_count": len(valid_config.entry_rules) + len(valid_config.exit_rules)
        }
        
        return {
            "success": True,
            "message": "Strategy uploaded and validated",
            "strategy_summary": summary,
            "file_name": file.filename
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Strategy: {str(e)}")

# باقي النقاط (مثل list و update) تحتاج لتعديل مشابه للـ upload
# نظراً لأن المحرك الجديد لا يحمل ملفات في الذاكرة (Stateless)، فالأمر يعتمد على الـ Config