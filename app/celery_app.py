# app/celery_app.py
import os
from celery import Celery

# قراءة المتغيرات من الـ env
broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")

celery_app = Celery(
    "worker",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks.backtest_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # تعديل مهم: الوقت الزمني للمهمة (مهم جداً للباك-تست الثقيل)
    task_soft_time_limit=3600, # 60 دقيقة
    task_time_limit=3700,      # 61 دقيقة (إجباري الإنهاء)
    # ✅ إصلاح تحذير CPendingDeprecationWarning في Celery 5.3+/6:
    # يحدد سلوك إعادة محاولة الاتصال بالـ broker عند الإقلاع صراحة.
    broker_connection_retry_on_startup=True,
    # ✅ إصلاح: بدون هذه الإعدادات كان .delay() يعلّق طلب HTTP لِدقائق
    # بإعادة المحاولة اللانهائية على broker غير متاح — الآن فشل سريع (≤ ~3 ثوان)
    # ويعيد الـ router استجابة 503 فورية بدل تعليق العميل.
    broker_connection_timeout=2,        # مهلة اتصال قصيرة
    broker_connection_max_retries=1,    # محاولة واحدة فقط عند النشر
    broker_transport_options={"connect_timeout": 2, "socket_connect_timeout": 2},
    result_backend_transport_options={"connect_timeout": 2, "socket_connect_timeout": 2},
)


def is_broker_available(timeout: float = 2.0) -> bool:
    """فحص سريع لتوفر الـ broker (يستخدمه /backtest/run قبل النشر)."""
    try:
        with celery_app.connection_or_acquire(transport_options={"connect_timeout": timeout}) as conn:
            conn.ensure_connection(max_retries=1, timeout=timeout)
            return conn.default_channel.connection is not None
    except Exception:
        return False
