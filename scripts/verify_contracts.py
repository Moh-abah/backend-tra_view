#!/usr/bin/env python3
"""
verify_contracts.py — فحص سريع لعقود API على الخادم الحي (بعد نشر حزمة الإصلاح).

Usage:
    python scripts/verify_contracts.py [BASE_URL]
    BASE_URL default: http://localhost:8000  (أو ضع CONTRACT_BASE_URL في البيئة)

يفحص (بدون بيانات اعتماد حقيقية):
  1. /health                     — حالة قاعدة البيانات (تقرير فقط)
  2. CORS preflight              — Origin خارجي يُقبل؟ (كان 400)
  3. POST /users/login (JSON+email) — يجب 401 (عقد سليم) لا 422
  4. POST /users/login (Form)        — يجب 401 (توافق Swagger/OAuth2)
  5. POST /backtest/run بحقول الفرونت القديمة — يجب task_id أو 503، لا 422
  6. GET  /market/top-movers     — زمن الاستجابة (< 5 ثوانٍ بعد الإصلاح)
  7. GET  /strategies/list       — count > 0 بعد المسح التلقائي
  8. GET  /market/historical/... — start_date بصيغة ISO أو null (لا "0")

الخروج: رمز 0 إذا نجحت كل الفحوص الحرجة، 1 إن فشل أحدها.
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else __import__("os").environ.get(
    "CONTRACT_BASE_URL", "http://localhost:8000"
)
API = BASE.rstrip("/") + "/api/v1"

results = []


def record(name: str, ok: bool, detail: str, critical: bool = True):
    results.append((name, ok, detail, critical))
    mark = "✅ PASS" if ok else ("🔴 FAIL" if critical else "🟠 WARN")
    print(f"{mark}  {name}: {detail}")


def main() -> int:
    client = httpx.Client(timeout=30.0)
    failed_critical = False

    # 1) Health
    try:
        r = client.get(f"{API}/health", timeout=15)
        db_state = "?"
        try:
            db_state = r.json().get("database", "?")
        except Exception:
            pass
        record(
            "health/db",
            r.status_code == 200,
            f"HTTP {r.status_code}, database={db_state}"
            + ("" if db_state == "up" else "  ← أصلح DATABASE_URL/كلمة المرور (P0)"),
        )
        if db_state != "up":
            print("   ⚠️ تنبيه: فحوص تتطلب قاعدة البيانات (دخول/باك تست) ستفشل حتى تُصلحها.")
    except Exception as e:
        record("health/db", False, f"unreachable: {e}")

    # 2) CORS preflight
    try:
        r = client.options(
            f"{API}/market/top-movers",
            headers={
                "Origin": "http://example-frontend.com",
                "Access-Control-Request-Method": "GET",
            },
            timeout=15,
        )
        ok = r.status_code == 200
        record(
            "cors/preflight",
            ok,
            f"HTTP {r.status_code}"
            + ("" if ok else "  ← أضف منبع الفرونت إلى CORS_ORIGINS في ملف .env الذي يقرؤه compose"),
        )
    except Exception as e:
        record("cors/preflight", False, f"error: {e}")

    # 3) Login JSON + email → عقد سليم = 401 (بيانات خاطئة) لا 422
    try:
        r = client.post(
            f"{API}/users/login",
            json={"email": "nobody@example.com", "password": "wrongpass"},
            timeout=15,
        )
        ok = r.status_code == 401
        record(
            "login/json-email",
            ok,
            f"HTTP {r.status_code}"
            + ("" if ok else "  ← المتوقع 401؛ 422 يعني أن إصلاح الدخول غير منشور"),
        )
    except Exception as e:
        record("login/json-email", False, f"error: {e}")

    # 4) Login Form (OAuth2/Swagger compat)
    try:
        r = client.post(
            f"{API}/users/login",
            data={"username": "nobody", "password": "wrongpass"},
            timeout=15,
        )
        ok = r.status_code == 401
        record("login/form-username", ok, f"HTTP {r.status_code}")
    except Exception as e:
        record("login/form-username", False, f"error: {e}")

    # 5) Backtest run بحقول الفرونت القديمة
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        legacy_payload = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "strategy": "rsi_default",
            "commission": 0.001,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        r = client.post(f"{API}/backtest/run", json=legacy_payload, timeout=20)
        body = {}
        try:
            body = r.json()
        except Exception:
            pass
        ok = r.status_code in (200, 503) and "detail" not in body or "task_id" in body
        # نجاح العقد: 200 (task_id) أو 503 (broker متوقف) — أما 422 فعقد مكسور
        ok = "task_id" in body or r.status_code == 503
        record(
            "backtest/run-legacy-fields",
            ok,
            f"HTTP {r.status_code}, task_id={'yes' if body.get('task_id') else 'no'}"
            + ("" if ok else "  ← 422 يعني أن قبول الحقول البديلة غير منشور"),
        )
    except Exception as e:
        record("backtest/run-legacy-fields", False, f"error: {e}")

    # 6) Top movers التوقيت
    try:
        t0 = time.perf_counter()
        r = client.get(f"{API}/market/top-movers", timeout=90)
        elapsed = time.perf_counter() - t0
        # أول استدعاء بعد إصلاح لا يزال قد يستغرق ثوانٍ (كاش 60s بعدها)
        ok = r.status_code == 200 and elapsed < 20
        record(
            "market/top-movers",
            ok,
            f"HTTP {r.status_code} في {elapsed:.1f}s"
            + (" (كاش)" if elapsed < 1 else "")
            + ("" if elapsed < 5 else "  ← ما زال بطيئاً؛ تأكد من نشر الإصلاح المتوازي"),
            critical=False,
        )
    except Exception as e:
        record("market/top-movers", False, f"error: {e}", critical=False)

    # 7) Strategies list
    try:
        r = client.get(f"{API}/strategies/list", timeout=30)
        count = r.json().get("count", 0) if r.status_code == 200 else -1
        ok = r.status_code == 200 and count > 0
        record(
            "strategies/list",
            ok,
            f"HTTP {r.status_code}, count={count}"
            + ("" if ok else "  ← 0 يعني أن مسح القرص غير منشور أو المجلد غير مركّب في Docker"),
        )
    except Exception as e:
        record("strategies/list", False, f"error: {e}")

    # 8) Historical start_date
    try:
        r = client.get(
            f"{API}/market/historical/crypto/BTCUSDT",
            params={"timeframe": "1h", "days": 2},
            timeout=60,
        )
        sd = r.json().get("start_date") if r.status_code == 200 else None
        bad = sd is not None and str(sd).strip() in ("0", "1")
        ok = r.status_code == 200 and not bad
        record(
            "market-data/historical",
            ok,
            f"HTTP {r.status_code}, start_date={sd!r}"
            + ("" if not bad else "  ← ما زال يعيد \"0\"؛ تأكد من نشر إصلاح _index_to_iso"),
        )
    except Exception as e:
        record("market-data/historical", False, f"error: {e}", critical=False)

    client.close()

    print("\n" + "=" * 60)
    failed = [(n, d) for (n, ok, d, c) in results if not ok and c]
    warned = [(n, d) for (n, ok, d, c) in results if not ok and not c]
    print(f"النتيجة: {len(results) - len(failed) - len(warned)} نجاح · {len(failed)} فشل حرج · {len(warned)} تحذير")
    if failed:
        print("الفحوص الحرجة الفاشلة:", ", ".join(n for n, _ in failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
