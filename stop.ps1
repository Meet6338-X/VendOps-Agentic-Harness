# PowerShell Shutdown Script for VendOps
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "               VENDOPS AGENTIC HARNESS - SHUTDOWN                     " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Terminate Console Windows with title VendOps-API-Server
Write-Host "[1/3] Terminating VendOps API Server console windows..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.MainWindowTitle -match "VendOps-API-Server" } | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

# 2. Kill any process listening on port 8000
Write-Host "[2/3] Checking and stopping processes on port 8000..." -ForegroundColor Yellow
$connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($connections) {
    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pids) {
        if ($p -gt 0) {
            Write-Host "Terminating process on port 8000 (PID: $p)..." -ForegroundColor Yellow
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
}

# 3. Stop Docker Compose services
Write-Host "[3/3] Stopping Docker Compose Qdrant services..." -ForegroundColor Yellow
docker compose down

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "[SUCCESS] All VendOps services stopped cleanly." -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
