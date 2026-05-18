#!/usr/bin/env pwsh
# Start the Orchestra TPRM dev environment (backend + frontend)
# Usage: .\dev.ps1
# Both servers restart automatically on crash.

$root  = $PSScriptRoot
$front = Join-Path $root "dashboard"
$venv  = Join-Path $root ".venv\Scripts"

Write-Host "Starting Orchestra TPRM dev environment..." -ForegroundColor Cyan
Write-Host "  Backend : http://localhost:8080" -ForegroundColor Gray
Write-Host "  Frontend: http://localhost:3001  (3000 if free)" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop both.`n" -ForegroundColor Gray

$back = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoExit", "-Command",
        "Set-Location '$root'; Write-Host 'Backend starting...' -ForegroundColor Yellow; & '$venv\uvicorn.exe' orchestra_tprm.server.app:app --port 8080 --reload" `
    -PassThru -WindowStyle Normal

$front = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoExit", "-Command",
        "Set-Location '$front'; Write-Host 'Frontend starting...' -ForegroundColor Yellow; npm run dev" `
    -PassThru -WindowStyle Normal

Write-Host "Backend PID : $($back.Id)" -ForegroundColor Green
Write-Host "Frontend PID: $($front.Id)" -ForegroundColor Green
Write-Host "`nBoth servers running. Close their windows or Ctrl+C here to stop." -ForegroundColor Cyan

# Keep this script alive so the user can Ctrl+C
try { Wait-Process -Id $back.Id, $front.Id } catch {}
