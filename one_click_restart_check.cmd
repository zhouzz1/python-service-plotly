@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PORT=5001"
set "SERVICE_NAME=python-service"
set "NACOS_SERVER=192.168.10.187:8848"
set "DISCOVERY_IP=192.168.2.150"
set "NACOS_NAMESPACE="
set "NACOS_TARGETS=192.168.10.187:8848"

echo [0/5] Kill old process on port %PORT% (if exists)...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  echo   - killing PID %%p
  taskkill /PID %%p /F >nul 2>nul
)

echo [1/5] Start python service...
start "python-service" powershell -NoExit -NoProfile -ExecutionPolicy Bypass -Command ^
  "$env:NACOS_DISCOVERY_IP='%DISCOVERY_IP%'; $env:APP_PORT='%PORT%'; $env:NACOS_SERVER_ADDR='%NACOS_SERVER%'; $env:NACOS_SERVICE_NAME='%SERVICE_NAME%'; $env:NACOS_NAMESPACE='%NACOS_NAMESPACE%'; $env:NACOS_TARGETS='%NACOS_TARGETS%'; & '%~dp0run.ps1'"

echo [2/5] Wait boot...
timeout /t 8 /nobreak >nul

echo [3/5] Health check...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r=Invoke-WebRequest 'http://127.0.0.1:%PORT%/common/receive-data' -UseBasicParsing -TimeoutSec 10; Write-Host ('HEALTH_OK: ' + $r.StatusCode + ' ' + $r.Content) } catch { Write-Host ('HEALTH_FAIL: ' + $_.Exception.Message); exit 1 }"
if errorlevel 1 (
  echo.
  echo [FAIL] Service health check failed.
  goto :END
)

echo [4/5] Nacos check...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$url='http://%NACOS_SERVER%/nacos/v1/ns/instance/list?serviceName=%SERVICE_NAME%'; if('%NACOS_NAMESPACE%' -ne ''){ $url = $url + '&namespaceId=%NACOS_NAMESPACE%' }; try { $c=(Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10).Content; Write-Host $c; if($c -match '\"hosts\":\\[\\]'){ Write-Host 'NACOS_FAIL: hosts is empty'; exit 2 } else { Write-Host 'NACOS_OK: hosts is not empty' } } catch { Write-Host ('NACOS_FAIL: ' + $_.Exception.Message); exit 2 }"
if errorlevel 1 (
  echo.
  echo [WARN] Service is up but nacos registration is not ready.
  goto :END
)

echo [5/5] Done.
echo [OK] Service restarted and registered.

:END
echo.
echo Tips:
echo   - health URL:  http://127.0.0.1:%PORT%/common/receive-data
echo   - nacos check: .\check.cmd
endlocal

