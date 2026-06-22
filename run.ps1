$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Start-Process python -ArgumentList "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $root -WindowStyle Hidden -PassThru
$frontend = Start-Process npm.cmd -ArgumentList "run", "dev" -WorkingDirectory (Join-Path $root "frontend") -WindowStyle Hidden -PassThru
Write-Host "QuantLab started: http://127.0.0.1:5173"
Write-Host "Backend PID: $($backend.Id)  Frontend PID: $($frontend.Id)"
