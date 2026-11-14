# PowerShell Startup Script for VendOps
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "               VENDOPS AGENTIC HARNESS - STARTUP                      " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Start Qdrant Container
Write-Host "[1/4] Checking and starting Qdrant Vector Store via Docker..." -ForegroundColor Yellow
docker compose up -d qdrant
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to start Qdrant. Please ensure Docker Desktop is running." -ForegroundColor Red
    exit 1
}

# 2. Wait for Qdrant Healthz
Write-Host "[2/4] Waiting for Qdrant health check on http://localhost:6333/healthz..." -ForegroundColor Yellow
$healthy = $false
for ($i = 0; $i -lt 15; $i++) {
    try {
        $res = Invoke-RestMethod -Uri "http://localhost:6333/healthz" -TimeoutSec 1 -ErrorAction Stop
        if ($res -match "healthz check passed" -or $res -eq "healthz check passed") {
            $healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if ($healthy) {
    Write-Host "[OK] Qdrant is healthy and responding." -ForegroundColor Green
} else {
    Write-Host "[WARNING] Qdrant health check timed out. Continuing with local fallback..." -ForegroundColor DarkYellow
}

# 3. Seed SQLite ERP Database
Write-Host "[3/4] Ensuring local SQLite ERP database is seeded..." -ForegroundColor Yellow
uv run python -c "from vendops.erp.db import ERPDatabase; from vendops.erp.seed import seed_database; seed_database(ERPDatabase('vendops_erp.db'))"
Write-Host "[OK] ERP database ready." -ForegroundColor Green

# 4. Start FastAPI server in a new window or process
Write-Host "[4/4] Starting VendOps FastAPI & SSE Service on port 8000..." -ForegroundColor Yellow
Write-Host "----------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "Web API & Docs  : http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Health Check    : http://localhost:8000/healthz" -ForegroundColor Cyan
Write-Host "Qdrant Web UI   : http://localhost:6333/dashboard" -ForegroundColor Cyan
Write-Host "----------------------------------------------------------------------" -ForegroundColor Gray

Start-Process -FilePath "cmd.exe" -ArgumentList '/k "title VendOps-API-Server && uv run uvicorn vendops.api.main:app --host 0.0.0.0 --port 8000"'

Write-Host "[SUCCESS] VendOps services successfully launched! Run .\stop.ps1 to shut down." -ForegroundColor Green
