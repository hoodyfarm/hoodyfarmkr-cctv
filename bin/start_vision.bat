@echo off
title [HoodyFarm FMS] AI Vision CCTV Daemon
cd /d "D:\workspace\hoodyfarmkr-cctv"

echo ===================================================
echo   [HoodyFarm FMS] 3500X AI Vision CCTV Daemon
echo ===================================================
echo.

if not exist "D:\workspace\hoodyfarmkr-cctv\.venv\Scripts\python.exe" (
    echo [ERROR] Virtualenv .venv not found.
    pause
    exit /b 1
)

set PYTHONUTF8=1
set PYTHONPATH=D:\workspace\hoodyfarmkr-cctv

echo [STATUS] Starting FastAPI & YOLO Vision Daemon...
echo [INFO] LAN: http://192.168.0.234:8000
echo [INFO] Tailscale: http://100.75.197.92:8000
echo [INFO] Docs: http://192.168.0.234:8000/docs
echo.
echo ===================================================
echo   To STOP daemon, close this window or press Ctrl+C
echo ===================================================
echo.

"D:\workspace\hoodyfarmkr-cctv\.venv\Scripts\python.exe" -m uvicorn src.main:app --host 0.0.0.0 --port 8000

if %ERRORLEVEL% neq 0 (
    echo.
    echo [WARNING] Daemon exited with code: %ERRORLEVEL%
    pause
)