@echo off
echo ========================================
echo 모든 프로토콜 서버 시작
echo ========================================
echo.
echo 각 프로토콜 서버를 별도 창에서 시작합니다...
echo.
echo TCP 서버 (포트 10000)
echo UDP 서버 (포트 9998)
echo RUDP 서버 (포트 9999)
echo MIDTP 서버 (포트 9997)
echo QUIC 서버 (포트 4433)
echo.
echo 각 창을 닫거나 Ctrl+C로 개별 종료할 수 있습니다.
echo ========================================
echo.

start "TCP Server" cmd /k python test_performance.py --mode server --protocol tcp
timeout /t 1 /nobreak >nul

start "UDP Server" cmd /k python test_performance.py --mode server --protocol udp
timeout /t 1 /nobreak >nul

start "RUDP Server" cmd /k python test_performance.py --mode server --protocol rudp
timeout /t 1 /nobreak >nul

start "MIDTP Server" cmd /k python test_performance.py --mode server --protocol midtp
timeout /t 1 /nobreak >nul

start "QUIC Server" cmd /k python test_performance.py --mode server --protocol quic

echo.
echo 모든 서버가 별도 창에서 시작되었습니다.
echo 이 창을 닫아도 서버는 계속 실행됩니다.
echo.
pause
