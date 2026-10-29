@echo off
chcp 65001 >nul
title Trading Backend - FIX DB PASSWORD only
cd /d "%~dp0"

echo.
echo ============================================================
echo   FIX DB: aligns trader password / database with .env
echo   (no data loss - safe to run anytime)
echo ============================================================
echo.

docker compose up -d postgres redis

echo Waiting for Postgres...
set /a tries=0
:waitpg
set /a tries+=1
docker inspect --format "{{.State.Health.Status}}" trading-postgres 2>nul | findstr /C:"healthy" >nul
if not errorlevel 1 goto pgok
if %tries% GEQ 40 goto pgfail
timeout /t 3 /nobreak >nul
goto waitpg
:pgfail
echo FAILED: Postgres not healthy. Check: docker logs trading-postgres
pause
exit /b 1
:pgok

docker cp heal-postgres.sql trading-postgres:/tmp/heal.sql
docker exec trading-postgres psql -U trader -d trading_db -v ON_ERROR_STOP=1 -f /tmp/heal.sql >nul 2>&1
if not errorlevel 1 goto healed
echo Trying via trader on default db...
docker exec trading-postgres psql -U trader -d postgres -v ON_ERROR_STOP=1 -f /tmp/heal.sql >nul 2>&1
if not errorlevel 1 goto healed
echo Trying via postgres superuser...
docker exec trading-postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f /tmp/heal.sql
if errorlevel 1 goto healfail
:healed
echo DB fixed. Restarting backend + celery...
docker compose restart backend celery-worker
echo.
echo DONE. Check: http://localhost:8000/api/v1/health
pause
exit /b 0
:healfail
echo HEAL FAILED. Manual check: docker logs trading-postgres
pause
exit /b 1
