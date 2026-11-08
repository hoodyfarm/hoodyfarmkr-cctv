@echo off
chcp 65001 > nul
title [후디팜 FMS] AI Vision 데몬 종료
echo ===================================================
echo   [후디팜 FMS] 3500X AI Vision 데몬 종료 스크립트
echo ===================================================
echo.

echo [실행] 포트 8000번을 점유 중인 비전 데몬 프로세스를 확인합니다...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo [종료] 프로세스 PID: %%a 를 안전하게 종료합니다...
    taskkill /F /PID %%a > nul 2>&1
)

echo.
echo [완료] AI Vision 데몬이 정상적으로 종료되었습니다.
timeout /t 3
