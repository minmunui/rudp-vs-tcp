@echo off
echo ========================================
echo RUDP 서버 시작
echo ========================================
echo 프로토콜: RUDP
echo 포트: 9999
echo.
echo 서버 실행 중... (Ctrl+C로 종료)
echo ========================================
echo.

python test_performance.py --mode server --protocol rudp

pause
