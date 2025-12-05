# 파일 전송 프로토콜 비교: TCP vs RUDP vs MIDTP vs QUIC

## 프로토콜 설명

### TCP
- 표준 TCP 소켓을 사용한 신뢰성 있는 파일 전송
- 순서 보장, 재전송 자동 처리

### RUDP (Reliable UDP)
- UDP 기반 + 수동 재전송 로직
- 메타데이터를 별도 패킷으로 전송
- 메타데이터 손실 시 전송 실패 가능성 있음

### MIDTP (Metadata-Integrated Data Transfer Protocol) ⭐ 권장
- 개선된 UDP 기반 프로토콜
- **메타데이터도 일반 패킷처럼 재전송 가능** (seq_num=0)
- 모든 패킷에 `last_seq` 포함 → 메타데이터 없어도 전체 청크 수 파악 가능
- 순서 무관 수신, 메타데이터 손실에 강건함

### QUIC
- 최신 UDP 기반 프로토콜 (HTTP/3의 기반)
- 내장 신뢰성, 혼잡 제어, 0-RTT 지원
- 스트림 기반 전송, 동적 버퍼 크기 조절
- TLS 1.3 내장으로 보안 강화

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

### 3. MIDTP 방식 ⭐ 권장

**서버 실행** (터미널 1):
```bash
cd src
python -c "from midtp import MIDTP; MIDTP().start_server('127.0.0.1', 9999)"
```

**파일 전송** (터미널 2):
```bash
cd src
python -c "from midtp import MIDTP; MIDTP().send_file('파일경로', '127.0.0.1', 9999)"
```

### 4. QUIC 방식 🚀 최신

**서버 실행** (터미널 1):
```bash
cd src
python -c "from quic_protocol import QUIC; QUIC().start_server('127.0.0.1', 9999)"
```

**파일 전송** (터미널 2):
```bash
cd src
python -c "from quic_protocol import QUIC; QUIC().send_file('파일경로', '127.0.0.1', 9999)"
```

**참고**: QUIC은 자체 서명 인증서가 필요합니다. 서버 첫 실행 시 자동 생성됩니다.

## 서버 종료

- `Ctrl+C` (KeyboardInterrupt)로 서버를 안전하게 종료할 수 있습니다.

## 참고사항

- 반드시 서버를 먼저 실행한 후 클라이언트를 실행하세요
- 수신된 파일은 `received/` 디렉토리에 저장됩니다
- 원격 전송 시 `127.0.0.1` 대신 실제 IP 주소를 사용하세요
- **안정성이 중요한 경우 MIDTP 사용을 권장합니다**
- **최신 기술과 최고 성능을 원하면 QUIC을 사용하세요**

## MIDTP의 장점

1. **메타데이터 재전송 가능**: 메타데이터 손실 시에도 ACK를 통해 재전송됨
2. **Robust한 설계**: 모든 패킷에 `last_seq` 포함으로 총 청크 수를 언제든지 파악 가능
3. **순서 무관**: 패킷이 순서 없이 도착해도 정상 처리
4. **파일명 오염 방지**: 메타데이터가 명시적으로 구분되어 데이터와 혼동 없음