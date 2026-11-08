@echo off
title [HoodyFarm FMS] Check AI Vision Daemon Status
echo ===================================================
echo   Checking HoodyFarm Vision Daemon on Port 8000...
echo ===================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    set FOUND=1
    echo [RUNNING] Daemon is active on Port 8000 (PID: %%a)
)

if "%FOUND%"=="0" (
    echo [STOPPED] AI Vision Daemon is NOT running.
) else (
    echo.
    echo --- Access Endpoints ---
    echo [LAN URL]       http://192.168.0.234:8000
    echo [Tailscale URL] http://100.75.197.92:8000
    echo [API Docs]      http://192.168.0.234:8000/docs
)

echo.
pause