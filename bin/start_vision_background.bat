@echo off
chcp 65001 > nul
cd /d "D:\workspace\hoodyfarmkr-cctv"

:: 백그라운드 무인 실행용 (콘솔 창 없이 숨김 실행)
powershell.exe -WindowStyle Hidden -Command "$env:PYTHONUTF8=1; $env:PYTHONPATH='D:\workspace\hoodyfarmkr-cctv'; & 'D:\workspace\hoodyfarmkr-cctv\.venv\Scripts\python.exe' -m uvicorn src.main:app --host 0.0.0.0 --port 8000"
