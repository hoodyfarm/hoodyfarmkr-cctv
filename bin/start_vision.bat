@echo off
chcp 65001 > nul
title [후디팜 FMS] AI Vision & CCTV 데몬
cd /d "D:\workspace\hoodyfarmkr-cctv"

echo ===================================================
echo   [후디팜 FMS] 3500X AI Vision CCTV 데몬 서비스
echo ===================================================
echo.

:: 1. 가상환경 및 Python 인터프리터 점검
if not exist ".venv\Scripts\python.exe" (
    echo [오류] 가상환경(.venv)이 존재하지 않습니다.
    echo 관리자 또는 AI 에이전트를 통해 셋업을 완료해 주세요.
    pause
    exit /b 1
)

:: 2. 환경변수 및 UTF-8 설정
set PYTHONUTF8=1
set PYTHONPATH=D:\workspace\hoodyfarmkr-cctv

echo [상태] FastAPI & YOLO 비전 서버를 시작합니다...
echo [안내] 사내망 접속: http://192.168.0.234:8000
echo [안내] 외부망 접속(Tailscale): http://100.75.197.92:8000
echo [안내] API 문서: http://192.168.0.234:8000/docs
echo.
echo ===================================================
echo   종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.
echo ===================================================
echo.

:: 3. Uvicorn 서버 실행 (0.0.0.0 바인딩으로 사내망/외부망 모두 접속 가능)
".venv\Scripts\python.exe" -m uvicorn src.main:app --host 0.0.0.0 --port 8000

if %ERRORLEVEL% neq 0 (
    echo.
    echo [경고] 데몬이 비정상 종료되었습니다. (코드: %ERRORLEVEL%)
    pause
)
