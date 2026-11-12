# app/models/candle_cache.py
"""✅ الجولة 45 — نموذج كاش الشموع (Candle Cache ORM).

مشكلة الإنتاج (كلام المستخدم حرفياً): «اذا اردت اسوي اختبار سنه لبيتكوين
بمؤشرات مختلفه واستراتيجيه مختلفه لفريم دقيقه فكل مره بيجلب شموع جديده»
— كل تشغيل يعيد جلب مئات آلاف الشموع من المزوّد (بطيء، محدود بمعدل
الطلبات، ونتائجه نفسها لأن الشموع التاريخية المغلقة لا تتغير).

الجدول هذا يخزّن الشموع في قاعدة البيانات نهائياً (ليس كاشاً مؤقتاً
بذاكرة تُمسح): مفتاح واحد لكل (market, symbol, timeframe) والشموع
تُدمج تصاعدياً — التشغيل التالي يجلب فقط ما نقص من الرأس («يجلب فوقها
آخر شموع») ويقرأ الباقي من القاعدة فوراً.

مساحتا عمل منفصلتان (بادئة المفتاح) لضمان عزل تام بين تنسيقين:
  c:{market}:{symbol}:{timeframe}  ← فضاء الشموع (المسار الموحد ج42 —
                                     نفس قواميس الشموع التي يستهلكها
                                     محرك الخروج حرفياً، صفر مخاطرة)
  d:{market}:{symbol}:{timeframe}  ← فضاء الـDataFrame (المسار القياسي —
                                     يخزن السجلات + مخطط الأعمدة
                                     والأنواع ويُعيد بناء الإطار بنفس
                                     الشكل الذي أنتجه المزوّد)
"""
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from app.database.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CandleCache(Base):
    """صف واحد لكل مفتاح كاش — الشموع المدمجة كاملة + حدودها الزمنية."""

    __tablename__ = "candle_cache"
    __table_args__ = (
        Index("ix_candle_cache_symbol_tf", "symbol", "timeframe"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(160), nullable=False, unique=True, index=True)

    symbol = Column(String(32), nullable=False)
    timeframe = Column(String(16), nullable=False)
    market = Column(String(16), nullable=False)
    namespace = Column(String(4), nullable=False, default="c")  # c | d

    # الشموع المدمجة (JSON list) — صاعدة زمنياً ومُنقّاة من التكرار
    candles = Column(JSON, nullable=False)
    # مخطط الـDataFrame لفضاء d فقط (أعمدة/أنواع/فهرس) — NULL في فضاء c
    schema_json = Column(JSON, nullable=True)

    first_time = Column(BigInteger, nullable=False, default=0)  # epoch ثوانٍ
    last_time = Column(BigInteger, nullable=False, default=0)
    count = Column(Integer, nullable=False, default=0)

    # أثر آخر جلب (للشفافية والتشخيص)
    last_fetch_note = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
