@echo off
title [HoodyFarm FMS] Stop AI Vision Daemon
echo ===================================================
echo   Stopping HoodyFarm Vision Daemon on Port 8000...
echo ===================================================
echo.

set STOPPED=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    set STOPPED=1
    echo [KILL] Terminating PID: %%a ...
    taskkill /F /PID %%a > nul 2>&1
)

if "%STOPPED%"=="1" (
    echo [SUCCESS] Vision Daemon stopped successfully.
) else (
    echo [INFO] No running Vision Daemon found on port 8000.
)
timeout /t 3