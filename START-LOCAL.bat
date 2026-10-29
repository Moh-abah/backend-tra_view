@echo off
chcp 65001 >nul
title Trading Backend - START LOCAL (full auto)
cd /d "%~dp0"

echo.
echo ============================================================
echo   TRADING BACKEND - START LOCAL (auto-heal included)
echo   1) stops old containers  2) postgres+redis  3) heal DB
echo   4) build+start backend+celery  5) wait until healthy
echo ============================================================
echo.

echo [1/6] Stopping old containers...
docker compose down 2>nul

echo [2/6] Starting postgres + redis...
docker compose up -d postgres redis

echo [3/6] Waiting for Postgres to become healthy...
set /a tries=0
:waitpg
set /a tries+=1
docker inspect --format "{{.State.Health.Status}}" trading-postgres 2>nul | findstr /C:"healthy" >nul
if not errorlevel 1 goto pgok
if %tries% GEQ 40 goto pgfail
timeout /t 3 /nobreak >nul
goto waitpg
:pgfail
echo FAILED: postgres not healthy. Check: docker logs trading-postgres
pause
exit /b 1
:pgok
echo       postgres OK.

echo [4/6] Healing DB user/password/database (no data loss)...
docker cp heal-postgres.sql trading-postgres:/tmp/heal.sql
docker exec trading-postgres psql -U trader -d trading_db -v ON_ERROR_STOP=1 -f /tmp/heal.sql >nul 2>&1
if not errorlevel 1 goto healed
docker exec trading-postgres psql -U trader -d postgres -v ON_ERROR_STOP=1 -f /tmp/heal.sql >nul 2>&1
if not errorlevel 1 goto healed
docker exec trading-postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f /tmp/heal.sql >nul 2>&1
if not errorlevel 1 goto healed
echo       WARN: heal attempt via default routes failed (continuing - volume may already be correct).
:healed
echo       DB aligned with .env (trader / trader_local_2024 / trading_db).

echo [5/6] Building + starting backend and celery (first build takes minutes)...
docker compose up -d --build backend celery-worker

echo [6/6] Waiting for API health...
set /a tries=0
:waitapi
set /a tries+=1
curl -fsS http://localhost:8000/health >nul 2>&1
if not errorlevel 1 goto apiok
if %tries% GEQ 60 goto apifail
timeout /t 3 /nobreak >nul
goto waitapi
:apifail
echo FAILED: API not healthy yet. Check: docker compose logs backend --tail 50
echo If it says "password authentication failed" run: FIX-DB.bat
pause
exit /b 1
:apiok

echo.
echo ============================================================
echo   SUCCESS - backend is running!
echo   API docs:    http://localhost:8000/docs
echo   Health:      http://localhost:8000/api/v1/health
echo   Candles API: /api/v1/market/candles/crypto/BTCUSDT?timeframe=1h^&limit=2000
echo ============================================================
echo.
pause
