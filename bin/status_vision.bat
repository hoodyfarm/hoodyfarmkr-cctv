@echo off
chcp 65001 > nul
title [후디팜 FMS] AI Vision 데몬 상태 확인
echo ===================================================
echo   [후디팜 FMS] 3500X AI Vision 데몬 상태 점검
echo ===================================================
echo.

set FOUND=0
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    set FOUND=1
    echo [정상 가동 중] 포트 8000 (PID: %%a) 에서 데몬이 실행 중입니다.
)

if "%FOUND%"=="0" (
    echo [미실행] 현재 AI Vision 데몬이 실행되어 있지 않습니다.
) else (
    echo.
    echo --- 네트워크 접속 정보 ---
    echo [사내망 IP] http://192.168.0.234:8000
    echo [Tailscale IP] http://100.75.197.92:8000
    echo [Swagger 문서] http://192.168.0.234:8000/docs
)

echo.
echo 아무 키나 누르면 창을 닫습니다...
pause > nul
