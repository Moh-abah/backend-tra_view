# run_sandbox.py — إقلاع سيرفر الإثبات الحي R45 (راوترات حقيقية 100%)
"""يشغّل FastAPI حقيقيًا بالملفات الحقيقية لج45 فوق ستُبّات المحرك فقط.

الغرض: إثبات عقد HTTP كامل (ترقيم تسلسلي، سجل دائم، تقدّم، كاش شموع،
تزامن) بلا الحاجة لمصدر المستخدم المحروس (engine1/unified_backtest).
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from app.database import init_db  # noqa: E402
from app.routers import backtest, backtest1  # noqa: E402

app = FastAPI(title="R45 Proof Sandbox", version="45.0")
app.include_router(backtest.router, prefix="/api/v1/backtest")
app.include_router(backtest1.router, prefix="/api/v1/backtest1")


@app.on_event("startup")
async def _boot():
    await init_db()


if __name__ == "__main__":
    uvicorn.run(
        "run_sandbox:app",
        host="127.0.0.1",
        port=int(os.environ.get("SANDBOX_PORT", "8110")),
        log_level="warning",
    )


# ==========================================================================
# منفذ تحكم اختباري — موجود في الساندبوكس فقط (لا يُشحن في حزمة الإنتاج)
# يسمح لسكربت الإثبات بتقديم الساعة المجمّدة/تبطيء المحاكاة أثناء التشغيل.
# ==========================================================================
from fastapi import Body  # noqa: E402


@app.post("/sandbox/_test/control")
async def _sandbox_control(payload: dict = Body(...)):
    import os as _os

    for key in ("R45_TEST_CLOCK_EPOCH", "SANDBOX_SIM_DELAY"):
        if key in payload:
            if payload[key] is None:
                _os.environ.pop(key, None)
            else:
                _os.environ[key] = str(payload[key])
    return {
        "ok": True,
        "clock": _os.environ.get("R45_TEST_CLOCK_EPOCH"),
        "sim_delay": _os.environ.get("SANDBOX_SIM_DELAY"),
    }
