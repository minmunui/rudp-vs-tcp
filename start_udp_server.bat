@echo off
echo ========================================
echo UDP 서버 시작
echo ========================================
echo 프로토콜: UDP
echo 포트: 9998
echo.
echo 서버 실행 중... (Ctrl+C로 종료)
echo ========================================
echo.

python test_performance.py --mode server --protocol udp

pause
