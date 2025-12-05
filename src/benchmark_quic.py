#!/usr/bin/env python3
"""
QUIC의 전송 속도를 buffer_size별로 측정하여 CSV로 저장하는 스크립트
buffer_size는 QUIC에서 자동으로 처리되므로 실제로는 사용되지 않지만,
다른 프로토콜과의 비교를 위해 동일한 범위로 측정합니다.
"""

import csv
import time
from quic_protocol import QUIC
import logger

# 설정
FILE_TO_SEND = "../image.JPG"
SERVER_HOST = "192.168.1.161"
QUIC_PORT = 9998  # QUIC 전용 포트
BUFFER_SIZE_MULTIPLIERS = range(1, 11)  # 1460*1 ~ 1460*10 (호환성을 위해)
BASE_BUFFER_SIZE = 1460
TRIALS_PER_SIZE = 10  # 각 buffer_size마다 측정
WAIT_BETWEEN_TRANSFERS = 2.0  # 전송 간 대기
OUTPUT_CSV = "benchmark_quic_drop0.csv"


def run_benchmark():
    """
    QUIC의 전송 속도를 측정하고 CSV 파일로 저장
    """
    results = []

    quic = QUIC()

    print(f"QUIC 벤치마크 시작: {FILE_TO_SEND}")
    print(f"서버: {SERVER_HOST}")
    print(f"QUIC 포트: {QUIC_PORT}")
    print(f"Buffer size 범위: {BASE_BUFFER_SIZE}*1 ~ {BASE_BUFFER_SIZE}*10 (참고용)")
    print(f"각 설정당 시도 횟수: {TRIALS_PER_SIZE}")
    print(
        "참고: QUIC는 내부적으로 최적화된 전송을 수행하므로 buffer_size는 실제로 사용되지 않습니다."
    )
    print("-" * 60)

    for multiplier in BUFFER_SIZE_MULTIPLIERS:
        buffer_size = BASE_BUFFER_SIZE * multiplier
        print(
            f"\n[Buffer Size: {buffer_size} bytes ({BASE_BUFFER_SIZE}*{multiplier}) - 참고용]"
        )

        for trial in range(1, TRIALS_PER_SIZE + 1):
            print(f"  Trial {trial}/{TRIALS_PER_SIZE}")

            # QUIC 전송
            print(f"    QUIC 전송 중...")
            try:
                quic_result = quic.send_file(
                    filename=FILE_TO_SEND,
                    host=SERVER_HOST,
                    port=QUIC_PORT,
                    buffer_size=buffer_size,  # QUIC는 이 값을 무시하지만 호환성을 위해 전달
                    interval=0.0,  # QUIC는 자체 pacing 사용
                )

                if quic_result["success"]:
                    print(f"      QUIC 완료: {quic_result['speed_mbps']:.2f} MB/s")
                    results.append(
                        {
                            "protocol": "QUIC",
                            "buffer_size": buffer_size,
                            "trial": trial,
                            "transfer_time": quic_result["transfer_time"],
                            "speed_mbps": quic_result["speed_mbps"],
                            "filesize": quic_result["filesize"],
                            "success": True,
                            "loss_count": 0,  # QUIC는 내부적으로 재전송 처리
                        }
                    )
                else:
                    print(f"      QUIC 실패")
                    results.append(
                        {
                            "protocol": "QUIC",
                            "buffer_size": buffer_size,
                            "trial": trial,
                            "transfer_time": 0,
                            "speed_mbps": 0,
                            "filesize": 0,
                            "success": False,
                            "loss_count": 0,
                        }
                    )
            except Exception as e:
                print(f"      QUIC 오류: {e}")
                results.append(
                    {
                        "protocol": "QUIC",
                        "buffer_size": buffer_size,
                        "trial": trial,
                        "transfer_time": 0,
                        "speed_mbps": 0,
                        "filesize": 0,
                        "success": False,
                        "loss_count": 0,
                    }
                )

            # 전송 간 대기
            time.sleep(WAIT_BETWEEN_TRANSFERS)

    # CSV 파일로 저장
    print(f"\n결과를 {OUTPUT_CSV}에 저장 중...")
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = [
            "protocol",
            "buffer_size",
            "trial",
            "transfer_time",
            "speed_mbps",
            "filesize",
            "success",
            "loss_count",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        writer.writerows(results)

    print(f"벤치마크 완료! 결과가 {OUTPUT_CSV}에 저장되었습니다.")
    print(f"총 {len(results)}개의 측정값이 기록되었습니다.")

    # 요약 통계 출력
    print("\n=== 요약 ===")
    quic_results = [r for r in results if r["success"]]
    if quic_results:
        avg_speed = sum(r["speed_mbps"] for r in quic_results) / len(quic_results)
        max_speed = max(r["speed_mbps"] for r in quic_results)
        min_speed = min(r["speed_mbps"] for r in quic_results)
        print(f"QUIC 평균 속도: {avg_speed:.2f} MB/s")
        print(f"QUIC 최대 속도: {max_speed:.2f} MB/s")
        print(f"QUIC 최소 속도: {min_speed:.2f} MB/s")
        print(
            f"성공률: {len(quic_results)}/{len(results)} ({len(quic_results)/len(results)*100:.1f}%)"
        )


if __name__ == "__main__":
    try:
        run_benchmark()
    except KeyboardInterrupt:
        print("\n\n벤치마크가 중단되었습니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback

        traceback.print_exc()
