@echo off
echo ========================================
echo MIDTP 서버 시작
echo ========================================
echo 프로토콜: MIDTP
echo 포트: 9997
echo.
echo 서버 실행 중... (Ctrl+C로 종료)
echo ========================================
echo.

python test_performance.py --mode server --protocol midtp

pause
