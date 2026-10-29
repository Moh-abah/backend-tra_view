from .core import FilteringEngine
from .schemas import FilterCriteria, FilterResult, FilterRule, CompositeFilter

__all__ = [
    "FilteringEngine",
    "FilterCriteria",
    "FilterResult",
    "FilterRule",
    "CompositeFilter"
]

# إنشاء كائن FilteringEngine عالمي
_filtering_engine = None

def get_filtering_engine() -> FilteringEngine:
    """الحصول على كائن FilteringEngine

    Bugfix: كان يُنشأ بلا ``data_service`` (None) → محرك الفلترة كان يعيد
    الرموز الافتراضية فقط وبأسعار 0 لأن ``get_live_price`` يُستدعى على
    None. الآن يُنشأ بمزوّد بيانات حقيقي (بدون جلسة DB — لا حاجة لها
    لجلب الأسعار/الرموز، ومحرك الفلترة singleton).
    """
    global _filtering_engine
    if _filtering_engine is None:
        from app.services.data_service import DataService

        try:
            data_service = DataService()
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "FilteringEngine: failed to build DataService; engine runs degraded"
            )
            data_service = None
        _filtering_engine = FilteringEngine(data_service=data_service)
    return _filtering_engine