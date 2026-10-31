# =============================================================================
# Trading Backend API — Dockerfile
# FastAPI + Celery worker share this image (see docker-compose.yml).
# =============================================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# --- System dependencies (gcc for some wheels, curl for HEALTHCHECK) -------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        curl \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies (cached unless requirements change) ----------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application code (respects .dockerignore — secrets are NOT baked in) ---------
COPY . .

# --- Runtime directories (mounted as volumes in docker-compose) --------------------
# ✅ الجولة 6: chart_data — مجلد قواعد SQLite (المؤشرات المحفوظة + أدوات الرسم).
# وجوده في الصورة بملكية trader يجعل الـ named volume chart_data يرث الملكية
# الصحيحة عند أول ربط — لا readonly ولا directories فارغة بعد اليوم.
RUN mkdir -p /app/logs /app/strategies /app/reports /app/chart_data /app/data \
    && useradd -m -u 1000 trader \
    && chown -R trader:trader /app
USER trader

EXPOSE 8000

# --- Healthcheck: /health is served at the app root (app/main.py) -------------------
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# --- Start app ------------------------------------------------------------------------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
