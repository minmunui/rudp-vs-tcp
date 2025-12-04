#!/usr/bin/env python3
"""
TCP와 RUDP의 전송 속도를 buffer_size별로 측정하여 CSV로 저장하는 스크립트
"""

import csv
import time
from tcp import TCP
from rudp import RUDP
import logger

# 설정
FILE_TO_SEND = "../image.JPG"
SERVER_HOST = "192.168.1.161"
TCP_PORT = 10000
RUDP_PORT = 9999
BUFFER_SIZE_MULTIPLIERS = range(1, 11)  # 1460*1 ~ 1460*10
BASE_BUFFER_SIZE = 1460
TRIALS_PER_SIZE = 10  # 각 buffer_size마다 3번 측정
WAIT_BETWEEN_TRANSFERS = 2.0  # 전송 간 1초 대기
OUTPUT_CSV = "benchmark_10_results_drop2.csv"

def run_benchmark():
    """
    TCP와 RUDP의 전송 속도를 측정하고 CSV 파일로 저장
    """
    results = []
    
    tcp = TCP()
    rudp = RUDP()
    
    print(f"벤치마크 시작: {FILE_TO_SEND}")
    print(f"서버: {SERVER_HOST}")
    print(f"TCP 포트: {TCP_PORT}, RUDP 포트: {RUDP_PORT}")
    print(f"Buffer size 범위: {BASE_BUFFER_SIZE}*1 ~ {BASE_BUFFER_SIZE}*10")
    print(f"각 설정당 시도 횟수: {TRIALS_PER_SIZE}")
    print("-" * 60)
    
    for multiplier in BUFFER_SIZE_MULTIPLIERS:
        buffer_size = BASE_BUFFER_SIZE * multiplier
        print(f"\n[Buffer Size: {buffer_size} bytes ({BASE_BUFFER_SIZE}*{multiplier})]")
        
        for trial in range(1, TRIALS_PER_SIZE + 1):
            print(f"  Trial {trial}/{TRIALS_PER_SIZE}")
            
            # TCP 전송
            print(f"    TCP 전송 중...")
            try:
                tcp_result = tcp.send_file(
                    filename=FILE_TO_SEND,
                    host=SERVER_HOST,
                    port=TCP_PORT,
                    buffer_size=buffer_size,
                    interval=0.0005
                )
                
                if tcp_result["success"]:
                    print(f"      TCP 완료: {tcp_result['speed_mbps']:.2f} MB/s")
                    results.append({
                        "protocol": "TCP",
                        "buffer_size": buffer_size,
                        "trial": trial,
                        "transfer_time": tcp_result["transfer_time"],
                        "speed_mbps": tcp_result["speed_mbps"],
                        "filesize": tcp_result["filesize"],
                        "success": True
                    })
                else:
                    print(f"      TCP 실패")
                    results.append({
                        "protocol": "TCP",
                        "buffer_size": buffer_size,
                        "trial": trial,
                        "transfer_time": 0,
                        "speed_mbps": 0,
                        "filesize": 0,
                        "success": False
                    })
            except Exception as e:
                print(f"      TCP 오류: {e}")
                results.append({
                    "protocol": "TCP",
                    "buffer_size": buffer_size,
                    "trial": trial,
                    "transfer_time": 0,
                    "speed_mbps": 0,
                    "filesize": 0,
                    "success": False
                })
            
            # 전송 간 대기
            time.sleep(WAIT_BETWEEN_TRANSFERS)
            
            # RUDP 전송
            print(f"    RUDP 전송 중...")
            try:
                rudp_result = rudp.send_file(
                    filename=FILE_TO_SEND,
                    host=SERVER_HOST,
                    port=RUDP_PORT,
                    buffer_size=buffer_size,
                    interval=0.0005
                )
                
                if rudp_result["success"]:
                    print(f"      RUDP 완료: {rudp_result['speed_mbps']:.2f} MB/s")
                    results.append({
                        "protocol": "RUDP",
                        "buffer_size": buffer_size,
                        "trial": trial,
                        "transfer_time": rudp_result["transfer_time"],
                        "speed_mbps": rudp_result["speed_mbps"],
                        "filesize": rudp_result["filesize"],
                        "success": True,
                        "loss_count": len([l for l in rudp_result["losses"] if len(l) > 0])
                    })
                else:
                    print(f"      RUDP 실패")
                    results.append({
                        "protocol": "RUDP",
                        "buffer_size": buffer_size,
                        "trial": trial,
                        "transfer_time": 0,
                        "speed_mbps": 0,
                        "filesize": 0,
                        "success": False,
                        "loss_count": 0
                    })
            except Exception as e:
                print(f"      RUDP 오류: {e}")
                results.append({
                    "protocol": "RUDP",
                    "buffer_size": buffer_size,
                    "trial": trial,
                    "transfer_time": 0,
                    "speed_mbps": 0,
                    "filesize": 0,
                    "success": False,
                    "loss_count": 0
                })
            
            # 전송 간 대기
            time.sleep(WAIT_BETWEEN_TRANSFERS)
    
    # CSV 파일로 저장
    print(f"\n결과를 {OUTPUT_CSV}에 저장 중...")
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['protocol', 'buffer_size', 'trial', 'transfer_time', 'speed_mbps', 
                      'filesize', 'success', 'loss_count']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in results:
            # TCP는 loss_count가 없으므로 기본값 설정
            if 'loss_count' not in result:
                result['loss_count'] = 'N/A'
            writer.writerow(result)
    
    print(f"벤치마크 완료! 결과가 {OUTPUT_CSV}에 저장되었습니다.")
    print(f"총 {len(results)}개의 측정값이 기록되었습니다.")
    
    # 요약 통계 출력
    print("\n=== 요약 ===")
    for protocol in ["TCP", "RUDP"]:
        protocol_results = [r for r in results if r["protocol"] == protocol and r["success"]]
        if protocol_results:
            avg_speed = sum(r["speed_mbps"] for r in protocol_results) / len(protocol_results)
            print(f"{protocol} 평균 속도: {avg_speed:.2f} MB/s")

if __name__ == "__main__":
    try:
        run_benchmark()
    except KeyboardInterrupt:
        print("\n\n벤치마크가 중단되었습니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()
