@echo off
cd /d "D:\workspace\hoodyfarmkr-cctv"
powershell.exe -WindowStyle Hidden -Command "$env:PYTHONUTF8=1; $env:PYTHONPATH='D:\workspace\hoodyfarmkr-cctv'; & 'D:\workspace\hoodyfarmkr-cctv\.venv\Scripts\python.exe' -m uvicorn src.main:app --host 0.0.0.0 --port 8000"