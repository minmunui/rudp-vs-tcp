# 리팩터링 및 개선사항 요약

## 완료된 작업

### 1. 전송 속도 및 시간 통계 추가 ✅

#### RUDP (rudp.py)
- **클라이언트 (send_file)**:
  - 초기 전송 시간 측정
  - 총 전송 시간 계산
  - 전송 속도 (MB/s) 계산 및 출력
  - 파일 크기 및 통계를 보기 좋은 형식으로 출력

- **서버 (start_server)**:
  - 순수 전송 시간 측정 (파일 쓰기 제외)
  - 파일 쓰기 시간 별도 측정
  - 전체 시간 계산
  - 전송 속도 계산 및 출력

#### TCP (tcp.py)
- **클라이언트 (send_file)**:
  - 연결 시간 측정
  - 전송 시간 측정
  - 전송 속도 계산
  - 전송 세그먼트 수 카운팅
  - 통계 출력 형식 개선

- **서버 (start_server)**:
  - 순수 전송 시간 측정
  - 파일 쓰기 시간 측정
  - 전체 시간 계산
  - 통계 출력 형식 통일

### 2. 패킷/세그먼트 손실 통계 추가 ✅

#### RUDP
- **클라이언트**:
  - `total_packets_sent`: 총 전송 패킷 수 (재전송 포함)
  - `total_packets_lost`: 손실된 패킷 수
  - `packet_loss_rate`: 패킷 손실률 (%) 계산
  - 재전송 시 패킷 카운터 업데이트

- **서버**:
  - `total_packets_received`: 총 수신 패킷 수
  - `unique_packets`: 고유 패킷 수 (중복 제외)
  - `duplicate_packets`: 중복 수신 패킷 수
  - `packet_loss_count`: 손실 패킷 수

#### TCP
- TCP는 커널 레벨에서 자동으로 재전송을 처리하므로 애플리케이션 레벨에서는:
  - 전송 세그먼트 수 카운팅
  - 연결 시간 측정 (재전송으로 인한 지연 포함)

### 3. QUIC 프로토콜 구현 ✅

새로운 파일: `src/quic.py`

#### 주요 기능
- **비동기 I/O**: asyncio 기반 구현으로 효율적인 파일 전송
- **TLS 1.3 내장**: 암호화된 통신 기본 제공
- **자체 서명 인증서**: 개발용 인증서 자동 생성
- **스트림 기반 전송**: QUIC의 다중 스트림 활용

#### 클래스 구조
- `QuicFileClientProtocol`: 클라이언트 프로토콜 핸들러
- `QuicFileServerProtocol`: 서버 프로토콜 핸들러
- `QUIC`: Protocol 인터페이스 구현

#### 측정 지표
- 연결 시간 (TLS 핸드셰이크 포함)
- 전송 시간
- 전송 속도
- 파일 쓰기 시간
- 전체 시간

### 4. main.py 통합 ✅

#### QUIC 지원 추가
```python
--protocol quic  # QUIC 프로토콜 사용
```

#### 의존성 체크
- aioquic와 cryptography 라이브러리가 없을 경우 친절한 에러 메시지 출력
- 설치 명령어 안내

### 5. 통계 출력 형식 통일 ✅

모든 프로토콜에서 일관된 형식으로 통계 출력:

```
==================================================
파일 전송/수신 완료: filename.ext
파일 크기: X,XXX,XXX bytes (X.XX MB)
[프로토콜별 추가 정보]
전송 시간: X.XX초
전송 속도: X.XX MB/s
[기타 통계]
==================================================
```

### 6. 프로젝트 문서화 ✅

#### README.md 업데이트
- 프로젝트 개요 및 지원 프로토콜 설명
- 설치 방법 (기본 / QUIC 지원)
- 사용법 (서버/클라이언트 각 프로토콜별)
- 명령행 옵션 표
- 성능 측정 지표 설명
- 프로젝트 구조
- 주요 개선사항 목록

#### requirements.txt 생성
- aioquic>=0.9.0
- cryptography>=41.0.0

## 성능 비교 포인트

이제 다음 항목들을 비교할 수 있습니다:

1. **처리량 (Throughput)**
   - 전송 속도 (MB/s)
   - 프로토콜별 오버헤드

2. **신뢰성 (Reliability)**
   - RUDP: 패킷 손실률 및 재전송 통계
   - TCP: 자동 재전송 (커널 레벨)
   - QUIC: 패킷 손실 복구

3. **지연시간 (Latency)**
   - TCP: 연결 설정 시간
   - QUIC: TLS 핸드셰이크 포함 연결 시간
   - RUDP: 즉시 전송 시작

4. **보안 (Security)**
   - TCP/RUDP: 암호화 없음
   - QUIC: TLS 1.3 내장

## 사용 예시

### 로컬 테스트
```bash
# 터미널 1: 서버 시작
python src/main.py --protocol quic

# 터미널 2: 파일 전송
python src/main.py --file test.jpg --client True --protocol quic
```

### 네트워크 테스트
```bash
# 서버 (192.168.0.60)
python src/main.py --protocol tcp --target 0.0.0.0 --port 10000

# 클라이언트
python src/main.py --file image.JPG --client True --protocol tcp --target 192.168.0.60 --port 10000
```

### 로그 저장
```bash
# 서버
python src/main.py --protocol rudp --log server_rudp.log

# 클라이언트 (서버 로그에 자동 기록됨)
python src/main.py --file data.bin --client True --protocol rudp --target 192.168.0.60
```

## 향후 개선 가능 사항

1. **통계 그래프**: matplotlib을 사용한 성능 비교 그래프
2. **자동화 테스트**: 다양한 파일 크기와 네트워크 조건에서 자동 테스트
3. **패킷 캡처 통합**: Wireshark와 연동하여 실제 패킷 분석
4. **멀티스레드**: 동시 다중 파일 전송 지원
5. **압축**: 전송 전 파일 압축 옵션
6. **재개 기능**: 중단된 전송 이어받기
7. **대역폭 제한**: 인위적인 네트워크 조건 시뮬레이션

## 기술적 세부사항

### QUIC 구현
- aioquic 라이브러리 사용
- 자체 서명 인증서 자동 생성 (개발용)
- 스트림 ID 기반 파일 전송
- 헤더: 8바이트(파일크기) + 256바이트(파일명)

### 에러 처리
- 모든 프로토콜에서 일관된 예외 처리
- 타임아웃 설정
- 재시도 로직 (RUDP)
- 로그를 통한 디버깅 정보

### 측정 정확도
- `time.time()`을 사용한 고정밀 시간 측정
- 순수 전송 시간과 파일 I/O 시간 분리
- 바이트 단위 정확한 크기 측정
