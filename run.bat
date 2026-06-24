@echo off
chcp 65001 >nul
setlocal

title QuantLab - A股量化回测平台

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND_DIR=%ROOT%\backend"
set "FRONTEND_DIR=%ROOT%\frontend"

echo.
echo ================================================
echo   QuantLab v0.4.0 正在启动
echo   项目目录: %ROOT%
echo ================================================
echo.

if not exist "%BACKEND_DIR%\app.py" (
    echo [错误] 找不到后端目录或入口文件:
    echo        %BACKEND_DIR%\app.py
    echo 请把 run.bat 放在项目根目录后再运行。
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\package.json" (
    echo [错误] 找不到前端目录或 package.json:
    echo        %FRONTEND_DIR%\package.json
    echo 请把 run.bat 放在项目根目录后再运行。
    pause
    exit /b 1
)

set "PYTHON="
for %%C in (python python3 py) do (
    where %%C >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=%%C"
        goto :found_python
    )
)
echo [错误] 未找到 Python，请安装 Python 3.12+ 并添加到 PATH。
pause
exit /b 1

:found_python
echo [检查] Python: %PYTHON%
%PYTHON% --version

set "NPM="
for %%C in (npm.cmd npm) do (
    where %%C >nul 2>&1
    if not errorlevel 1 (
        set "NPM=%%C"
        goto :found_npm
    )
)
echo [错误] 未找到 Node.js/npm，请安装 Node.js 20+ 并添加到 PATH。
pause
exit /b 1

:found_npm
echo [检查] npm: %NPM%
call %NPM% --version

echo.
echo [步骤 1/4] 检查后端 Python 依赖...
if exist "%BACKEND_DIR%\requirements.txt" (
    %PYTHON% -m pip install -q -r "%BACKEND_DIR%\requirements.txt"
    if errorlevel 1 (
        echo [警告] pip install 失败，将继续尝试启动；如启动失败请手动检查依赖。
    ) else (
        echo [完成] 后端依赖已就绪。
    )
) else (
    echo [跳过] 未找到 backend\requirements.txt。
)

echo.
echo [步骤 2/4] 检查前端 Node.js 依赖...
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [安装] 首次启动需要执行 npm install，请稍候...
    pushd "%FRONTEND_DIR%"
    call %NPM% install
    if errorlevel 1 (
        popd
        echo [错误] npm install 失败。
        pause
        exit /b 1
    )
    popd
) else (
    echo [完成] 前端依赖已就绪。
)

echo.
echo [步骤 3/4] 启动后端 API 服务: http://127.0.0.1:8000
start "QuantLab-Backend" /MIN cmd /k "cd /d ""%ROOT%"" && %PYTHON% -m uvicorn backend.app:app --host 127.0.0.1 --port 8000"

echo [等待] 后端健康检查...
set "BACKEND_READY=0"
for /L %%i in (1,1,30) do (
    %PYTHON% -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=1)" >nul 2>nul
    if not errorlevel 1 (
        set "BACKEND_READY=1"
        goto :backend_ready
    )
    timeout /t 1 /nobreak >nul
)
echo [警告] 后端启动超时，将继续启动前端；请检查 QuantLab-Backend 窗口日志。

:backend_ready
if "%BACKEND_READY%"=="1" echo [完成] 后端 API 已就绪。

echo.
echo [步骤 4/4] 启动前端开发服务: http://127.0.0.1:5173
start "QuantLab-Frontend" /MIN cmd /k "cd /d ""%FRONTEND_DIR%"" && %NPM% run dev"

echo [等待] 前端服务...
for /L %%i in (1,1,20) do (
    %PYTHON% -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5173', timeout=1)" >nul 2>nul
    if not errorlevel 1 goto :frontend_ready
    timeout /t 1 /nobreak >nul
)
echo [警告] 前端启动可能仍在进行中，请稍后打开浏览器。

:frontend_ready
echo.
echo ================================================
echo   QuantLab 已启动
echo   Web 界面: http://127.0.0.1:5173
echo   API 文档: http://127.0.0.1:8000/docs
echo   停止服务: 运行 stop.bat
echo ================================================
echo.

start "" http://127.0.0.1:5173
pause
endlocal
