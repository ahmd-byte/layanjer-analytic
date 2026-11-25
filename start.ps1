# Layan Je Analytics — Start Script
Write-Host "Starting Layan Je Analytics..." -ForegroundColor Cyan

# Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install Python 3.11+." -ForegroundColor Red
    exit 1
}

# Check Node
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Node.js not found. Install Node.js 18+." -ForegroundColor Red
    exit 1
}

$root = $PSScriptRoot

# Initialize database
Write-Host "Initializing database..." -ForegroundColor Yellow
Push-Location "$root\backend"
& .\.venv\Scripts\python.exe -m layan_engine.cli setup
Pop-Location

# Start backend
Write-Host "Starting backend on http://127.0.0.1:8000 ..." -ForegroundColor Yellow
$backend = Start-Process -FilePath "$root\backend\.venv\Scripts\python.exe" `
    -ArgumentList "-m", "layan_engine.cli", "run" `
    -WorkingDirectory "$root\backend" `
    -PassThru -WindowStyle Normal

# Start frontend
Write-Host "Starting frontend on http://localhost:5173 ..." -ForegroundColor Yellow
$frontend = Start-Process -FilePath "npm" `
    -ArgumentList "run", "dev" `
    -WorkingDirectory "$root\frontend" `
    -PassThru -WindowStyle Normal

Write-Host ""
Write-Host "Layan Je Analytics is running!" -ForegroundColor Green
Write-Host "  Dashboard: http://localhost:5173" -ForegroundColor Cyan
Write-Host "  API:       http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop, or close this window." -ForegroundColor Gray

try {
    Wait-Process -Id $backend.Id
} finally {
    if (-not $frontend.HasExited) { Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue }
    if (-not $backend.HasExited) { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue }
}
