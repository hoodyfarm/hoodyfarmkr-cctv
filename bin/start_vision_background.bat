@echo off
cd /d "D:\workspace\hoodyfarmkr-cctv"
start "" /B "D:\workspace\hoodyfarmkr-cctv\.venv\Scripts\python.exe" -m uvicorn src.main:app --host 0.0.0.0 --port 8000