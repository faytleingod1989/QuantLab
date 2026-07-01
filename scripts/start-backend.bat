@echo off
setlocal

title QuantLab-Backend

set "PYTHON=%~1"
set "BACKEND_LOG=%~2"
set "ROOT=%~3"

if "%PYTHON%"=="" set "PYTHON=python"
if "%ROOT%"=="" set "ROOT=%~dp0.."
if "%BACKEND_LOG%"=="" set "BACKEND_LOG=%ROOT%\tmp\backend.log"

cd /d "%ROOT%"

echo ==== %DATE% %TIME% Starting backend ==== >"%BACKEND_LOG%"
"%PYTHON%" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 1>>"%BACKEND_LOG%" 2>&1

echo.
echo Backend process stopped. See log:
echo %BACKEND_LOG%
echo.
pause
endlocal
