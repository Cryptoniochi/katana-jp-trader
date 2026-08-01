@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\.."

set "TASK_NAME=Project KATANA Dashboard"
set "PORT=8000"
set "TAILSCALE_EXE=C:\Program Files\Tailscale\tailscale.exe"

echo [1/6] Stopping scheduled task...
schtasks /End /TN "%TASK_NAME%" >nul 2>&1

echo [2/6] Stopping any process listening on TCP %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    echo Stopping PID %%P
    taskkill /PID %%P /T /F >nul 2>&1
)

echo [3/6] Waiting for the port to be released...
for /L %%I in (1,1,20) do (
    netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
    if errorlevel 1 goto port_released
    timeout /t 1 /nobreak >nul
)

echo ERROR: TCP port %PORT% is still in use.
exit /b 1

:port_released
echo [4/6] Starting scheduled task...
schtasks /Run /TN "%TASK_NAME%"
if errorlevel 1 exit /b 1

echo [5/6] Waiting for Dashboard startup...
for /L %%I in (1,1,60) do (
    netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
    if not errorlevel 1 goto dashboard_listening
    timeout /t 1 /nobreak >nul
)

echo ERROR: Dashboard did not start within 60 seconds.
echo Check logs\dashboard\dashboard_resident.log
exit /b 1

:dashboard_listening
set "TAILSCALE_IP="
if exist "%TAILSCALE_EXE%" (
    for /f "usebackq delims=" %%A in (`"%TAILSCALE_EXE%" ip -4 2^>nul`) do (
        if not defined TAILSCALE_IP set "TAILSCALE_IP=%%A"
    )
)

if not defined TAILSCALE_IP (
    echo ERROR: Tailscale IPv4 address could not be resolved.
    exit /b 1
)

echo [6/6] Checking Service Status API...
powershell -NoProfile -Command ^
  "$u='http://%TAILSCALE_IP%:%PORT%/api/dashboard/service-status';" ^
  "try {$r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 10;" ^
  "Write-Host ('HTTP ' + [int]$r.StatusCode + ' ' + $u);" ^
  "if ($r.StatusCode -ne 200) {exit 1}}" ^
  "catch {Write-Error $_; exit 1}"

if errorlevel 1 (
    echo ERROR: Service Status API check failed.
    echo Check logs\dashboard\dashboard_resident.log
    exit /b 1
)

echo.
echo Dashboard refresh completed.
echo Mobile: http://%TAILSCALE_IP%:%PORT%/mobile
exit /b 0
