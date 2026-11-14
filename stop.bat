@echo off
setlocal

echo ======================================================================
echo                VENDOPS AGENTIC HARNESS - SHUTDOWN
echo ======================================================================

echo [1/2] Terminating VendOps API Server processes on port 8000...
powershell -NoProfile -Command "Get-Process | Where-Object { $_.MainWindowTitle -match 'VendOps-API-Server' } | Stop-Process -Force -ErrorAction SilentlyContinue"
powershell -NoProfile -Command "$p = (Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue).OwningProcess; if ($p) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }"

echo [2/2] Stopping Docker Compose Qdrant services...
docker compose down

echo ======================================================================
echo [SUCCESS] All VendOps services stopped cleanly.
echo ======================================================================
exit /b 0
