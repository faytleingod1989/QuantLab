@echo off
setlocal

title QuantLab Stopper

echo.
echo ================================================
echo   QuantLab stopper
echo   Closing local API and web services
echo ================================================
echo.

set "STOPPED=0"

echo [1/2] Stopping named QuantLab windows...
for /f "tokens=2" %%P in ('tasklist /fi "WINDOWTITLE eq QuantLab-Backend" /fo list ^| findstr /i "PID:"') do (
    taskkill /PID %%P /F >nul 2>nul
    if not errorlevel 1 (
        set "STOPPED=1"
        echo [OK] Backend window stopped, PID %%P
    )
)

for /f "tokens=2" %%P in ('tasklist /fi "WINDOWTITLE eq QuantLab-Frontend" /fo list ^| findstr /i "PID:"') do (
    taskkill /PID %%P /F >nul 2>nul
    if not errorlevel 1 (
        set "STOPPED=1"
        echo [OK] Frontend window stopped, PID %%P
    )
)

echo.
echo [2/2] Stopping listeners on ports 8000 and 5173...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING"') do (
    taskkill /PID %%P /F >nul 2>nul
    if not errorlevel 1 (
        set "STOPPED=1"
        echo [OK] Port 8000 listener stopped, PID %%P
    )
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":5173 .*LISTENING"') do (
    taskkill /PID %%P /F >nul 2>nul
    if not errorlevel 1 (
        set "STOPPED=1"
        echo [OK] Port 5173 listener stopped, PID %%P
    )
)

echo.
if "%STOPPED%"=="0" (
    echo [INFO] No QuantLab services were running.
) else (
    echo [DONE] QuantLab services have been stopped.
)
echo.
pause
endlocal
