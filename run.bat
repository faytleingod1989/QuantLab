@echo off
setlocal

title QuantLab Launcher

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND_DIR=%ROOT%\backend"
set "FRONTEND_DIR=%ROOT%\frontend"
set "LOG_DIR=%ROOT%\tmp"
set "BACKEND_LOG=%LOG_DIR%\backend.log"
set "FRONTEND_LOG=%LOG_DIR%\frontend.log"
set "BACKEND_WAIT_SECONDS=90"
set "FRONTEND_WAIT_SECONDS=45"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul

echo.
echo ================================================
echo   QuantLab launcher
echo   Project: %ROOT%
echo ================================================
echo.

if not exist "%BACKEND_DIR%\app.py" (
    echo [ERROR] backend entry not found:
    echo         %BACKEND_DIR%\app.py
    echo Put run.bat in the project root folder and try again.
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] frontend package.json not found:
    echo         %FRONTEND_DIR%\package.json
    echo Put run.bat in the project root folder and try again.
    pause
    exit /b 1
)

set "PYTHON="
for %%C in (python python3 py) do (
    where %%C >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON=%%C"
        goto :found_python
    )
)
echo [ERROR] Python was not found. Install Python 3.12+ and add it to PATH.
pause
exit /b 1

:found_python
echo [OK] Python command: %PYTHON%
%PYTHON% --version

set "NPM="
for %%C in (npm.cmd npm) do (
    where %%C >nul 2>nul
    if not errorlevel 1 (
        set "NPM=%%C"
        goto :found_npm
    )
)
echo [ERROR] npm was not found. Install Node.js 20+ and add it to PATH.
pause
exit /b 1

:found_npm
echo [OK] npm command: %NPM%
call %NPM% --version

echo.
echo [1/4] Checking backend dependencies...
if exist "%BACKEND_DIR%\requirements.txt" (
    %PYTHON% -m pip install -q -r "%BACKEND_DIR%\requirements.txt"
    if errorlevel 1 (
        echo [WARN] pip install failed. The launcher will continue.
    ) else (
        echo [OK] Backend dependencies are ready.
    )
) else (
    echo [SKIP] backend\requirements.txt not found.
)

echo.
echo [2/4] Checking frontend dependencies...
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [INFO] Installing frontend dependencies. This may take a while...
    pushd "%FRONTEND_DIR%"
    call %NPM% install
    if errorlevel 1 (
        popd
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
    popd
) else (
    echo [OK] Frontend dependencies are ready.
)

echo.
echo [3/4] Starting backend API: http://127.0.0.1:8000
%PYTHON% -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=1)" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Backend log: %BACKEND_LOG%
    echo ==== %DATE% %TIME% Starting backend ====>>"%BACKEND_LOG%"
    start "QuantLab-Backend" /MIN /D "%ROOT%" cmd /k call "%ROOT%\scripts\start-backend.bat" "%PYTHON%" "%BACKEND_LOG%" "%ROOT%"
) else (
    echo [OK] Backend is already running.
)

echo [WAIT] Backend health check...
set "BACKEND_READY=0"
for /L %%i in (1,1,%BACKEND_WAIT_SECONDS%) do (
    %PYTHON% -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=1)" >nul 2>nul
    if not errorlevel 1 (
        set "BACKEND_READY=1"
        goto :backend_ready
    )
    timeout /t 1 /nobreak >nul
)
echo [WARN] Backend did not become ready in %BACKEND_WAIT_SECONDS% seconds.
echo [WARN] Last backend log lines:
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path $env:BACKEND_LOG) { Get-Content -LiteralPath $env:BACKEND_LOG -Tail 60 } else { Write-Host 'Backend log file was not created.' }"

:backend_ready
if "%BACKEND_READY%"=="1" echo [OK] Backend is ready.

echo.
echo [4/4] Starting frontend app: http://127.0.0.1:5173
%PYTHON% -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5173', timeout=1)" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Frontend log: %FRONTEND_LOG%
    echo ==== %DATE% %TIME% Starting frontend ====>>"%FRONTEND_LOG%"
    start "QuantLab-Frontend" /MIN /D "%FRONTEND_DIR%" cmd /k call "%ROOT%\scripts\start-frontend.bat" "%NPM%" "%FRONTEND_LOG%" "%FRONTEND_DIR%"
) else (
    echo [OK] Frontend is already running.
)

echo [WAIT] Frontend health check...
set "FRONTEND_READY=0"
for /L %%i in (1,1,%FRONTEND_WAIT_SECONDS%) do (
    %PYTHON% -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5173', timeout=1)" >nul 2>nul
    if not errorlevel 1 (
        set "FRONTEND_READY=1"
        goto :frontend_ready
    )
    timeout /t 1 /nobreak >nul
)
echo [WARN] Frontend did not become ready in %FRONTEND_WAIT_SECONDS% seconds.
echo [WARN] Last frontend log lines:
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path $env:FRONTEND_LOG) { Get-Content -LiteralPath $env:FRONTEND_LOG -Tail 60 } else { Write-Host 'Frontend log file was not created.' }"

:frontend_ready
if "%FRONTEND_READY%"=="1" echo [OK] Frontend is ready.

echo.
echo ================================================
echo   QuantLab is ready
echo   Web:  http://127.0.0.1:5173
echo   API:  http://127.0.0.1:8000/docs
echo ================================================
echo.

start "" "http://127.0.0.1:5173"
pause
endlocal
