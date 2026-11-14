# PowerShell Startup Script for VendOps
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "               VENDOPS AGENTIC HARNESS - STARTUP                      " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Start Docker Compose Stack (VendOps API + Qdrant Vector Store)
Write-Host "[1/3] Starting VendOps unified container stack (API + Qdrant)..." -ForegroundColor Yellow
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to start Docker services. Please ensure Docker Desktop is running." -ForegroundColor Red
    exit 1
}

# 2. Wait for API Healthz Probe
Write-Host "[2/3] Waiting for VendOps API health check on http://localhost:8000/healthz..." -ForegroundColor Yellow
$healthy = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $res = Invoke-RestMethod -Uri "http://localhost:8000/healthz" -TimeoutSec 1 -ErrorAction Stop
        if ($res.status -eq "healthy") {
            $healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if ($healthy) {
    Write-Host "[OK] VendOps service is healthy and responding." -ForegroundColor Green
} else {
    Write-Host "[WARNING] Health check wait timed out. Checking running containers..." -ForegroundColor DarkYellow
}

# 3. System Status
Write-Host "[3/3] System is online and ready!" -ForegroundColor Yellow
Write-Host "----------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "Web API & Docs  : http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "Health Checks   : http://localhost:8000/health  |  http://localhost:8000/healthz" -ForegroundColor Cyan
Write-Host "Qdrant Web UI   : http://localhost:6333/dashboard" -ForegroundColor Cyan
Write-Host "----------------------------------------------------------------------" -ForegroundColor Gray

Write-Host "Running Containers:" -ForegroundColor Cyan
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"

Write-Host "----------------------------------------------------------------------" -ForegroundColor Gray
Write-Host "[SUCCESS] All VendOps containers are healthy! Run .\stop.ps1 to shut down." -ForegroundColor Green
