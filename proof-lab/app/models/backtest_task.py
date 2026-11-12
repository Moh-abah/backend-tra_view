# app/models/backtest_task.py
"""✅ الجولة 45 — نموذج سجل العمليات (Task Registry ORM).

جدول مؤسساتي واحد يوثّق كل عملية باك-تست من لحظة استلامها حتى نهايتها:

  * رقم عملية تسلسلي صريح (10000001 → 99999999) يراه المستخدم في الواجهة
    ويُستخدم للوصول والتقاسم بدل المعرّفات العشوائية (f397b2fa...).
  * حالة حية (PROGRESS/SUCCESS/FAILURE) + نسبة تقدّم + مرحلة نصية
    + رسالة — الفرونت يبني منها شريط تقدم وETA بدون أي تخمين.
  * طوابع زمنية كاملة (created/started/finished/updated) + duration_ms
    ⇒ «كم استغرق» و«كم بقي» إجابات محفوظة لا مشتقة من الذاكرة.
  * لقطة سطحية للنتيجة (pnl/win_rate/trades) عند النجاح — تكفي لعرض
    قائمة المكتبة بلا JOIN ثقيل مع جدول النتائج الضخم.
  * meta (JSON): إحصاءات كاش الشموع وغيرها من التفاصيل التشغيلية.

التخزين في نفس قاعدة بيانات التطبيق (SQLite/PostgreSQL) — ليس ذاكرة
مؤقتة: السجل يبقى بعد إعادة التشغيل ويمكن استرجاع أي عملية سابقة منه.

جدول task_id_counter: عدّاد أحادي الرقم (id=1) يتزايد ذرّياً بعبارة
UPDATE ... RETURNING واحدة — لا يعيد الأرقام حتى لو حُذفت صفوف، ويتحمل
التخصيص المتزامن من عدة عمليات (API + Worker) بأمان تحت درع R44.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from app.database.session import Base


def utcnow_naive() -> datetime:
    """UTC ساذج (بلا منطقة زمنية) — التمثيل المشترك الآمن بين
    SQLite (الذي يخزن النص) وPostgreSQL (timestamp without time zone)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BacktestTask(Base):
    """صف واحد لكل عملية باك-تست (المسار الموحد ج42 أو القياسي)."""

    __tablename__ = "backtest_tasks"
    __table_args__ = (
        Index("ix_bt_tasks_state_created", "state", "created_at"),
        Index("ix_bt_tasks_symbol_tf", "symbol", "timeframe"),
    )

    # رقم العملية التسلسلي — يُخصَّص من العدّاد ولا يُولَّد تلقائياً
    id = Column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=False,
    )

    # --- الحالة الحية ------------------------------------------------------
    state = Column(String(16), nullable=False, default="PROGRESS")  # PROGRESS | SUCCESS | FAILURE
    progress = Column(Float, nullable=False, default=0.0)           # 0..100
    phase = Column(String(32), nullable=True)   # register|fetch|simulate|save|done|error
    message = Column(String(500), nullable=True)  # رسالة تقدم للإنسان

    # --- تصنيف العملية ------------------------------------------------------
    mode = Column(String(32), nullable=False, default="inprocess")  # unified-exit|inprocess|celery
    name = Column(String(255), nullable=True)
    symbol = Column(String(32), nullable=True)
    timeframe = Column(String(16), nullable=True)
    market = Column(String(16), nullable=True)
    strategy = Column(String(64), nullable=True)
    days = Column(Integer, nullable=True)

    # --- الربط بالنتيجة الكاملة ----------------------------------------------
    backtest_id = Column(String(64), nullable=True)

    # --- لقطة سطحية (تُملأ عند النجاح فقط — لقائمة المكتبة) -------------------
    total_pnl_percent = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    total_trades = Column(Integer, nullable=True)
    duration_ms = Column(BigInteger, nullable=True)

    error = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)

    # --- الطوابع الزمنية (UTC دائماً) -----------------------------------------
    created_at = Column(DateTime, nullable=False, default=utcnow_naive)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utcnow_naive)


class TaskIdCounter(Base):
    """العدّاد الأحادي للعمليات — صف واحد (id=1) يتزايد ذرّياً.

    آخر رقم مُخصص محفوظ هنا؛ الرقم التالي = last_id + 1 حتى TASK_ID_MAX.
    الحذف من backtest_tasks لا يؤثر على العدّاد (لا إعادة استخدام أبداً).
    """

    __tablename__ = "task_id_counter"

    id = Column(Integer, primary_key=True, autoincrement=False, default=1)
    last_id = Column(BigInteger, nullable=False, default=10000000)
