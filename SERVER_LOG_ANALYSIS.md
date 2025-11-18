# 서버 로그 분석 가이드

## 개요

버퍼 크기에 따른 프로토콜별 성능을 비교하기 위한 서버 로그 분석 도구입니다.

## 로그 파일 명명 규칙

서버 실행 시 다음과 같은 형식으로 로그 파일명을 지정하세요:

```
{protocol}_b{buffer_size}.log
```

예시:
- `tcp_b1.log` - TCP, 버퍼 크기 1
- `tcp_b2.log` - TCP, 버퍼 크기 2
- `udp_b1.log` - UDP, 버퍼 크기 1
- `rudp_b5.log` - RUDP, 버퍼 크기 5

## 테스트 시나리오

### 1. 서버 준비 (각 프로토콜 × 버퍼 크기 조합마다)

```bash
# TCP 서버 - 버퍼 크기 1부터 10까지
python3 src/main.py --protocol tcp --port 10000 --log tcp_b1.log
python3 src/main.py --protocol tcp --port 10000 --log tcp_b2.log
# ... 반복

# UDP 서버
python3 src/main.py --protocol udp --port 9998 --log udp_b1.log
python3 src/main.py --protocol udp --port 9998 --log udp_b2.log

# RUDP 서버
python3 src/main.py --protocol rudp --port 9999 --log rudp_b1.log
python3 src/main.py --protocol rudp --port 9999 --log rudp_b2.log
```

### 2. 클라이언트 테스트 실행

각 서버에 대해 여러 번 파일 전송:

```bash
# TCP 버퍼 크기 1 테스트 (10회 반복)
for i in {1..10}; do
    python3 src/main.py --file test.jpg --client True --protocol tcp \
        --target 192.168.0.60 --port 10000 --buffer_size 1
    sleep 2
done

# 서버 측에서 tcp_b1.log에 10개의 전송 기록이 쌓임
```

## 자동화 스크립트

### `run_buffer_test.sh` - 전체 테스트 자동화

```bash
#!/bin/bash

# 설정
TARGET="192.168.0.60"
FILE="test.jpg"
PROTOCOLS=("tcp" "udp" "rudp")
BUFFER_SIZES=(1 2 3 4 5 6 7 8 9 10)
ITERATIONS=10

echo "=== 버퍼 크기별 성능 테스트 시작 ==="
echo "파일: $FILE"
echo "반복: $ITERATIONS 회"
echo ""

for protocol in "${PROTOCOLS[@]}"; do
    # 프로토콜별 포트 설정
    case $protocol in
        tcp) port=10000 ;;
        udp) port=9998 ;;
        rudp) port=9999 ;;
    esac
    
    for buffer in "${BUFFER_SIZES[@]}"; do
        echo ""
        echo "[$protocol] 버퍼 크기 $buffer 테스트"
        echo "서버 준비: python3 src/main.py --protocol $protocol --port $port --log ${protocol}_b${buffer}.log"
        read -p "서버가 준비되면 Enter를 누르세요..."
        
        # 여러 번 전송
        for i in $(seq 1 $ITERATIONS); do
            echo "  [$i/$ITERATIONS] 전송 중..."
            python3 src/main.py --file "$FILE" --client True \
                --protocol "$protocol" --target "$TARGET" --port "$port" \
                --buffer_size "$buffer" > /dev/null 2>&1
            sleep 1
        done
        
        echo "  완료! 서버를 종료하고 다음 테스트로 진행하세요."
        read -p "Enter를 눌러 계속..."
    done
done

echo ""
echo "=== 모든 테스트 완료 ==="
echo "로그 파일 확인: ls -lh logs/"
```

### 실행 권한 부여 및 실행

```bash
chmod +x run_buffer_test.sh
./run_buffer_test.sh
```

## 로그 분석

### 1. 기본 분석 - 모든 로그 파일 요약

```bash
python3 analyze_server_logs.py logs/*.log
```

출력 예시:
```
프로토콜     전송 횟수    평균 속도        최소/최대            평균 손실률    
--------------------------------------------------------------------------------
TCP          100         7.23 MB/s       4.12 / 9.26          -           
UDP          80          8.52 MB/s       7.23 / 10.12         0.45%       
RUDP         95          6.87 MB/s       3.21 / 8.95          2.34%       
```

### 2. 버퍼 크기별 비교

```bash
python3 compare_buffer_sizes.py logs/*_b*.log
```

출력 예시:
```
【전송 속도 (MB/s)】

버퍼          TCP         UDP        RUDP
------------------------------------------------------------
1           6.68        8.29        7.10
2           6.31        N/A         7.46
3           6.44        N/A         6.89
4           6.46        N/A         6.17
...

【패킷 손실률 (%)】

버퍼          UDP        RUDP
------------------------------------------------------------
1           0.00       18.76
2           N/A        33.22
3           N/A        37.51
...

【권장사항】

• TCP: 버퍼 크기 8 (평균 8.47 MB/s)
• UDP: 버퍼 크기 1 (평균 8.29 MB/s)
• RUDP: 버퍼 크기 2 (평균 7.46 MB/s)
  └ 평균 손실률: 33.22%
```

### 3. CSV로 내보내기

```bash
# 전체 데이터
python3 analyze_server_logs.py logs/*.log --csv all_results.csv

# 버퍼 크기별 비교
python3 compare_buffer_sizes.py logs/*_b*.log --csv buffer_comparison.csv
```

### 4. 그래프 생성 (matplotlib 필요)

```bash
# matplotlib 설치
pip install matplotlib

# 그래프 생성
python3 compare_buffer_sizes.py logs/*_b*.log --plot comparison.png
```

## 실전 예제

### 시나리오: TCP 버퍼 크기 1~10 비교

```bash
# 1단계: 서버 실행 (10개의 터미널 또는 순차 실행)
for i in {1..10}; do
    python3 src/main.py --protocol tcp --port 10000 --log tcp_b${i}.log &
    # 각 서버에 대해 클라이언트 테스트 실행
    for j in {1..10}; do
        python3 src/main.py --file test.jpg --client True --protocol tcp \
            --target localhost --port 10000 --buffer_size $i
        sleep 1
    done
    # 서버 종료
    killall python3
    sleep 2
done

# 2단계: 분석
python3 compare_buffer_sizes.py logs/tcp_b*.log
```

## 분석 결과 활용

### 1. 최적 버퍼 크기 선정
- 전송 속도가 가장 높은 버퍼 크기 선택
- 안정성 고려 (표준편차가 낮은 것 선호)

### 2. 프로토콜별 특성 파악
- TCP: 버퍼 크기가 클수록 빠르지만 특정 임계점 이후 효과 감소
- UDP: 작은 버퍼에서 빠르지만 손실 위험
- RUDP: 중간 크기 버퍼에서 균형

### 3. 네트워크 환경 고려
- 로컬: 큰 버퍼 크기 사용 가능
- 원격: 작은 버퍼로 안정성 확보
- WiFi: 손실률 모니터링 필수

## 문제 해결

### 로그 파일이 생성되지 않음
- `logs/` 디렉토리가 있는지 확인
- 서버 실행 시 `--log` 옵션 사용 확인

### 분석 결과가 비어있음
- 로그 파일에 "파일 수신 완료" 메시지가 있는지 확인
- 파일명 형식 확인 (`protocol_bN.log`)

### 버퍼 크기가 감지되지 않음
- 파일명에 `_b숫자` 패턴 포함 확인
- 예: `tcp_b1.log`, `udp_buffer_5.log`

## 결과 예시

실제 테스트 결과 예시:

```
버퍼 크기별 TCP 성능:
- 버퍼 1-3: 6~7 MB/s (느리고 불안정)
- 버퍼 4-6: 7~8 MB/s (중간)
- 버퍼 7-9: 8~9 MB/s (가장 빠름) ✓ 권장
- 버퍼 10+: 7~8 MB/s (효과 감소)

결론: TCP는 버퍼 크기 7-9에서 최적 성능
```
