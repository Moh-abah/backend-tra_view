# ساندبوكس إثبات R45 — بلا وسيط فعلي: كل المسارات تسلك inprocess/unified
import os

from celery import Celery

celery_app = Celery(
    "sandbox",
    broker=os.environ.get("SANDBOX_FAKE_BROKER", ""),
    result_backend="cache+memory://",  # يحاكي backend الإنتاج حتى يعمل عقد /status القديم
)


def is_broker_available(timeout=2.0):
    return os.environ.get("SANDBOX_BROKER_UP", "") == "1"
