# Start both backend (Flask) and frontend (Vite) for local development.
# Run this from the project root (E:\Web App\Video-Kit).

Write-Host "=== VidLab — Starting Backend (Flask) ===" -ForegroundColor Cyan
$BackendJob = Start-Job -ScriptBlock {
    Set-Location -LiteralPath "$using:PWD\backend"
    python main.py
}

Start-Sleep 3

Write-Host "=== VidLab — Starting Frontend (Vite) ===" -ForegroundColor Cyan
Write-Host "Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Green

try {
    Push-Location -LiteralPath "$PSScriptRoot\frontend"
    pnpm run dev
} finally {
    Pop-Location
    Write-Host "Stopping backend..." -ForegroundColor Yellow
    Stop-Job $BackendJob
    Remove-Job $BackendJob
}
