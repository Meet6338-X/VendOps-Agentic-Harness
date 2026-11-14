@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo                VENDOPS AGENTIC HARNESS - STARTUP
echo ======================================================================

echo [1/3] Starting VendOps unified container stack (API + Qdrant)...
docker compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to start Docker Compose services. Please ensure Docker Desktop is running.
    exit /b 1
)

echo [2/3] Waiting for VendOps API health check on http://localhost:8000/healthz...
set RETRIES=20
:wait_api
curl -s -f http://localhost:8000/healthz >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] VendOps service is healthy and responding.
    goto ready
)
set /a RETRIES-=1
if %RETRIES% LEQ 0 (
    echo [WARNING] Health check wait timed out. Checking docker status...
    docker ps
    goto ready
)
timeout /t 1 /nobreak >nul
goto wait_api

:ready
echo [3/3] System is online and ready!
echo ----------------------------------------------------------------------
echo Web API and Docs : http://localhost:8000/docs
echo Health Checks    : http://localhost:8000/health  ^|  http://localhost:8000/healthz
echo Qdrant Web UI    : http://localhost:6333/dashboard
echo ----------------------------------------------------------------------
echo Running Containers:
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
echo ----------------------------------------------------------------------
echo Run stop.bat to shut down all containers.
echo ======================================================================
exit /b 0
