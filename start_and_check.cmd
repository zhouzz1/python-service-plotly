@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Starting python-service...
start "python-service" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"

echo [2/3] Waiting service boot...
timeout /t 6 /nobreak >nul

echo [3/3] Checking nacos registration...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_nacos.ps1"

echo.
echo Done. If hosts is not empty, service is registered.
endlocal

