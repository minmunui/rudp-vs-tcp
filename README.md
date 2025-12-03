# RUDP vs TCP 파일 전송

## 사용법

### 1. TCP 방식

**서버 실행** (터미널 1):
```bash
cd src
python -c "from tcp import TCP; TCP().start_server('127.0.0.1', 9999)"
```

**파일 전송** (터미널 2):
```bash
cd src
python -c "from tcp import TCP; TCP().send_file('파일경로', '127.0.0.1', 9999, 1460)"
```

### 2. RUDP 방식

**서버 실행** (터미널 1):
```bash
cd src
python -c "from rudp import RUDP; RUDP().start_server('127.0.0.1', 9999)"
```

**파일 전송** (터미널 2):
```bash
cd src
python -c "from rudp import RUDP; RUDP().send_file('파일경로', '127.0.0.1', 9999)"
```

### 서버 종료

- `Ctrl+C` (KeyboardInterrupt)로 서버를 안전하게 종료할 수 있습니다.

### 참고사항

- 반드시 서버를 먼저 실행한 후 클라이언트를 실행하세요
- 수신된 파일은 `received/` 디렉토리에 저장됩니다
- 원격 전송 시 `127.0.0.1` 대신 실제 IP 주소를 사용하세요