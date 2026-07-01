@echo off
setlocal

title QuantLab-Frontend

set "NPM=%~1"
set "FRONTEND_LOG=%~2"
set "FRONTEND_DIR=%~3"

if "%NPM%"=="" set "NPM=npm.cmd"
if "%FRONTEND_DIR%"=="" set "FRONTEND_DIR=%~dp0..\frontend"
if "%FRONTEND_LOG%"=="" set "FRONTEND_LOG=%~dp0..\tmp\frontend.log"

cd /d "%FRONTEND_DIR%"

echo ==== %DATE% %TIME% Starting frontend ==== >"%FRONTEND_LOG%"
call %NPM% run dev 1>>"%FRONTEND_LOG%" 2>&1

echo.
echo Frontend process stopped. See log:
echo %FRONTEND_LOG%
echo.
pause
endlocal
