@echo off
title [HoodyFarm FMS] Auto-Labeler
cd /d "D:\workspace\hoodyfarmkr-cctv"

echo ===================================================
echo   [HoodyFarm FMS] 소 행동 반자동 의사 라벨러
echo ===================================================
echo.
echo [안내] 수집된 이미지에서 소를 탐지하고 자세를 자동 분류합니다.
echo.

set PYTHONUTF8=1
set PYTHONPATH=D:\workspace\hoodyfarmkr-cctv

"D:\workspace\hoodyfarmkr-cctv\.venv\Scripts\python.exe" src\tools\auto_labeler.py

echo.
echo 라벨링이 완료되었습니다. datasets\annotated_preview 에서 확인하세요.
pause
