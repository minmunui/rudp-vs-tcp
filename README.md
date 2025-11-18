
# RUDP vs TCP vs UDP vs QUIC 파일 전송 성능 비교

이 프로젝트는 네 가지 네트워크 프로토콜(TCP, UDP, RUDP, QUIC)을 사용한 파일 전송의 성능을 비교하는 프로그램입니다.

## 지원 프로토콜

- **TCP**: 전통적인 신뢰성 있는 전송 프로토콜 (자동 재전송)
- **UDP**: 신뢰성 없는 빠른 전송 프로토콜 ⚠️ **패킷 손실 시 에러 발생**
- **RUDP**: UDP 기반의 사용자 정의 신뢰성 전송 프로토콜 (수동 재전송)
- **QUIC**: UDP 기반의 최신 전송 프로토콜 (TLS 1.3 내장, 자동 재전송)

## 설치

### 기본 설치 (TCP, UDP, RUDP만 사용)
```bash
# 의존성 없음 - Python 표준 라이브러리만 사용
python3 --version  # Python 3.7 이상 필요
```

### QUIC 프로토콜 사용 시 추가 설치
```bash
pip install -r requirements.txt
# 또는
pip install aioquic cryptography
```

## 사용법

### 서버 실행

```bash
# TCP 서버
python src/main.py --protocol tcp --target 0.0.0.0 --port 10000

# UDP 서버
python src/main.py --protocol udp --target 0.0.0.0 --port 9998

# RUDP 서버
python src/main.py --protocol rudp --target 0.0.0.0 --port 9999

# QUIC 서버
python src/main.py --protocol quic --target 0.0.0.0 --port 4433

# 로그 파일 저장
python src/main.py --protocol tcp --target 0.0.0.0 --port 10000 --log server.log
```

### 클라이언트 실행

```bash
# TCP 클라이언트
python src/main.py --file image.JPG --client True --protocol tcp --target 192.168.0.60 --port 10000

# UDP 클라이언트 (패킷 손실 시 실패)
python src/main.py --file image.JPG --client True --protocol udp --target 192.168.0.60 --port 9998

# RUDP 클라이언트
python src/main.py --file image.JPG --client True --protocol rudp --target 192.168.0.60 --port 9999 --buffer_size 2

# QUIC 클라이언트
python src/main.py --file image.JPG --client True --protocol quic --target 192.168.0.60 --port 4433
```

## 명령행 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `-f, --file` | 전송할 파일 경로 | `./input/file` |
| `-c, --client` | 클라이언트 모드 활성화 | `False` |
| `-t, --target` | 서버 주소 | `localhost` |
| `-p, --port` | 포트 번호 | `9999` |
| `-b, --buffer_size` | 버퍼 크기 계수 | `1` |
| `-i, --interval` | 전송 간격 (초) | `0.0001` |
| `-l, --log` | 로그 파일 이름 | (없음) |
| `--protocol` | 사용할 프로토콜 (tcp/udp/rudp/quic) | `rudp` |

## 성능 측정 지표

모든 프로토콜에서 다음 정보를 측정하고 출력합니다:

### 공통 지표
- 파일 크기
- 전송 시간
- 전송 속도 (MB/s)
- 파일 쓰기 시간
- 전체 소요 시간

### 프로토콜별 추가 지표

#### TCP
- 연결 시간
- 전송 세그먼트 수

#### UDP
- 수신 패킷 / 예상 패킷
- 손실 패킷 수
- 손실률 (%)
- ⚠️ **패킷 손실 시 전송 실패 및 에러 발생**

#### RUDP
- 총 전송 패킷 수
- 손실 패킷 수
- 패킷 손실률 (%)
- 재전송 통계

#### QUIC
- 연결 시간 (TLS 핸드셰이크 포함)
- 암호화된 전송 통계

## 출력 예시

```
==================================================
파일 전송 완료: image.JPG
파일 크기: 1,234,567 bytes (1.18 MB)
전송 시간: 0.45초
전송 속도: 2.62 MB/s
총 전송 패킷: 850
손실 패킷: 12
패킷 손실률: 1.41%
==================================================
```

## 출력 예시 - UDP

### UDP 성공 (패킷 손실 없음)
```
==================================================
파일 수신 완료: test.jpg
파일 크기: 1,048,576 bytes (1.00 MB)
순수 전송 시간: 0.15초
전송 속도: 6.87 MB/s
수신 패킷: 715/715
패킷 손실: 없음 ✓
==================================================
```

### UDP 실패 (패킷 손실 발생)
```
==================================================
❌ UDP 전송 실패: 패킷 손실 감지
파일: test.jpg
예상 크기: 1,048,576 bytes
수신 패킷: 710/715
손실 패킷: 5
손실률: 0.70%
누락된 패킷 번호: [45, 123, 234, 456, 678]
==================================================
```

## UDP 사용 시 주의사항

⚠️ **UDP는 신뢰성이 없는 프로토콜입니다:**

1. **패킷 손실 시 에러 발생**: 단 하나의 패킷이라도 손실되면 전송 실패로 처리됩니다
2. **재전송 없음**: 손실된 패킷을 재전송하지 않습니다
3. **용도**: 네트워크 품질 테스트, 최대 속도 측정, 프로토콜 비교용

**권장 사용 시나리오:**
- 로컬 네트워크에서 빠른 파일 전송
- 네트워크 품질 측정 (손실률 확인)
- 다른 프로토콜과의 성능 비교

**프로덕션에서는 사용하지 마세요:**
- 중요한 파일 전송에는 TCP, RUDP, 또는 QUIC 사용
- UDP는 실험 및 벤치마크 용도로만 사용

## 프로젝트 구조

```
rudp-vs-tcp/
├── src/
│   ├── main.py          # 메인 프로그램
│   ├── protocol.py      # 프로토콜 인터페이스
│   ├── tcp.py           # TCP 구현
│   ├── udp.py           # UDP 구현 (NEW!)
│   ├── rudp.py          # RUDP 구현
│   ├── quic.py          # QUIC 구현
│   ├── logger.py        # 로깅 시스템
│   └── utils.py         # 유틸리티 함수
├── received/            # 수신된 파일 저장
├── logs/                # 로그 파일
├── certs/               # QUIC 인증서 (자동 생성)
├── requirements.txt     # Python 의존성
├── CHANGES.md          # 변경사항 문서
└── README.md
```

## 주요 개선사항

### v2.1 (2025)
- ✅ **UDP 프로토콜 추가** - 패킷 손실 감지 및 에러 처리
- ✅ QUIC 프로토콜 지원 추가
- ✅ 모든 프로토콜에서 전송 속도 및 시간 통계 출력
- ✅ RUDP 패킷 손실률 계산 및 표시
- ✅ 일관된 통계 출력 형식
- ✅ 비동기 I/O를 통한 QUIC 성능 최적화

## 프로토콜 비교표

| 특징 | TCP | UDP | RUDP | QUIC |
|------|-----|-----|------|------|
| 신뢰성 | ✅ 자동 | ❌ 없음 | ✅ 수동 | ✅ 자동 |
| 재전송 | 커널 레벨 | ❌ | 앱 레벨 | 프로토콜 레벨 |
| 손실 처리 | 자동 재전송 | **에러 발생** | 재전송 | 자동 재전송 |
| 순서 보장 | ✅ | ❌ | ✅ | ✅ |
| 암호화 | 별도 (TLS) | ❌ | ❌ | ✅ 내장 |
| 연결 설정 | 3-way | ❌ | ❌ | 1-RTT |
| 오버헤드 | 중간 | 최소 | 중간 | 중간 |
| 속도 | 중간 | **가장 빠름** | 중간 | 빠름 |

## 라이선스

이 프로젝트는 교육 목적으로 제작되었습니다.