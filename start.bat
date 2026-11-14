@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo                VENDOPS AGENTIC HARNESS - STARTUP
echo ======================================================================

echo [1/4] Checking and starting Qdrant Vector Store via Docker...
docker compose up -d qdrant
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to start Qdrant container. Please ensure Docker Desktop is running.
    exit /b 1
)

echo [2/4] Waiting for Qdrant health check on http://localhost:6333/healthz...
set RETRIES=15
:wait_qdrant
curl -s -f http://localhost:6333/healthz >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Qdrant is healthy and responding.
    goto seed_erp
)
set /a RETRIES-=1
if %RETRIES% LEQ 0 (
    echo [WARNING] Qdrant health check timed out. Continuing with local fallback...
    goto seed_erp
)
timeout /t 1 /nobreak >nul
goto wait_qdrant

:seed_erp
echo [3/4] Ensuring local SQLite ERP database is seeded...
uv run python -c "from vendops.erp.db import ERPDatabase; from vendops.erp.seed import seed_database; seed_database(ERPDatabase('vendops_erp.db'))"
echo [OK] ERP database ready.

echo [4/4] Starting VendOps FastAPI and SSE Service on port 8000...
echo ----------------------------------------------------------------------
echo Web API and Docs : http://localhost:8000/docs
echo Health Check     : http://localhost:8000/healthz
echo Qdrant Web UI    : http://localhost:6333/dashboard
echo ----------------------------------------------------------------------
echo Starting server in a new window (Run stop.bat to shut down)...
start "VendOps-API-Server" cmd /k "uv run uvicorn vendops.api.main:app --host 0.0.0.0 --port 8000"

echo [SUCCESS] VendOps services successfully launched!
exit /b 0
