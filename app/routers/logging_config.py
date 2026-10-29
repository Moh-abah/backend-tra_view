import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime
import json

def setup_logging():
    """إعداد نظام التسجيل (Logging) للتطبيق"""
    
    # إنشاء logger رئيسي
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # إزالة أي معالجات موجودة
    logger.handlers.clear()
    
    # تنسيق السجلات
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # معالج للتحكم (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # معالج لملف السجلات العامة
    file_handler = RotatingFileHandler(
        'logs/strategy_runner.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # معالج منفصل لسجلات الأخطاء
    error_handler = RotatingFileHandler(
        'logs/strategy_errors.log',
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    
    # معالج لسجلات الأداء
    performance_handler = RotatingFileHandler(
        'logs/performance_metrics.log',
        maxBytes=10*1024*1024,
        backupCount=5
    )
    performance_handler.setLevel(logging.INFO)
    
    # تنسيق خاص لسجلات الأداء (JSON)
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            if isinstance(record.msg, dict):
                log_data = record.msg
                log_data['level'] = record.levelname
                log_data['timestamp'] = datetime.now().isoformat()
                return json.dumps(log_data)
            return super().format(record)
    
    performance_handler.setFormatter(JSONFormatter())
    
    # إنشاء logger خاص للأداء
    perf_logger = logging.getLogger('performance')
    perf_logger.setLevel(logging.INFO)
    perf_logger.addHandler(performance_handler)
    perf_logger.propagate = False
    
    # تعطيل logging لبعض المكتبات الصاخبة
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    logger.info("تم إعداد نظام التسجيل بنجاح")

# إعداد logging عند استيراد الملف
setup_logging()