@echo off
title [HoodyFarm FMS] CCTV Dataset Collector
cd /d "D:\workspace\hoodyfarmkr-cctv"

echo ===================================================
echo   [HoodyFarm FMS] 축사 CCTV 데이터셋 자동 수집기
echo ===================================================
echo.
echo [안내] 10대 CCTV에서 15초 간격으로 원본 프레임을 자동 수집합니다.
echo [저장위치] D:\workspace\hoodyfarmkr-cctv\datasets\raw_frames
echo.

set PYTHONUTF8=1
set PYTHONPATH=D:\workspace\hoodyfarmkr-cctv

"D:\workspace\hoodyfarmkr-cctv\.venv\Scripts\python.exe" src\tools\dataset_collector.py --interval 15.0 --max-frames 100

echo.
echo 수집이 종료되었습니다. 아무 키나 누르면 창이 닫힙니다.
pause
