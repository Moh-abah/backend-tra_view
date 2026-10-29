# run_tests.py (اختياري)
#!/usr/bin/env python3
"""
نص تشغيل الاختبارات
"""
import sys
import pytest

if __name__ == "__main__":

    sys.exit(pytest.main([
        "app/tests/unit/test_indicators_base.py",
        "-v",  # تفصيلي
        "--tb=short",  # تتبع بسيط للأخطاء
    ]))