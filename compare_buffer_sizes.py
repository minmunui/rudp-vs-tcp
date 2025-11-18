#!/usr/bin/env python3
"""
버퍼 크기별 프로토콜 성능 비교 도구

서버 로그 파일을 분석하여 버퍼 크기에 따른
각 프로토콜의 전송 속도와 손실률을 비교합니다.

사용법:
    python compare_buffer_sizes.py logs/tcp_b*.log logs/udp_b*.log logs/rudp_b*.log
"""

import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
import statistics


class BufferSizeComparison:
    """버퍼 크기별 성능 비교"""

    def __init__(self):
        self.data = defaultdict(lambda: defaultdict(list))
        # data[protocol][buffer_size] = [speeds]
        self.loss_data = defaultdict(lambda: defaultdict(list))
        # loss_data[protocol][buffer_size] = [loss_rates]

    def parse_log_file(self, log_file: str) -> Tuple[str, int]:
        """로그 파일에서 프로토콜과 버퍼 크기 추출"""
        filename = Path(log_file).name

        # 파일명에서 프로토콜과 버퍼 크기 추출
        # 예: tcp_b1.log, tcp_b2.log, rudp_buffer_3.log
        protocol = None
        buffer_size = None

        # 프로토콜 감지
        for p in ["tcp", "udp", "rudp", "quic"]:
            if p in filename.lower():
                if p == "udp" and "rudp" in filename.lower():
                    protocol = "RUDP"
                else:
                    protocol = p.upper()
                break

        # 버퍼 크기 추출
        buffer_match = re.search(r"[_\-]?b(?:uffer)?[_\-]?(\d+)", filename.lower())
        if buffer_match:
            buffer_size = int(buffer_match.group(1))

        return protocol, buffer_size

    def extract_stats(self, log_file: str):
        """로그 파일에서 통계 추출"""
        protocol, buffer_size = self.parse_log_file(log_file)

        if not protocol or buffer_size is None:
            print(f"경고: {log_file}에서 프로토콜 또는 버퍼 크기를 감지할 수 없습니다.")
            return

        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 전송 속도 추출
        speeds = re.findall(r"전송 속도:\s*([\d.]+)\s*MB/s", content)
        speeds = [float(s) for s in speeds]

        if speeds:
            self.data[protocol][buffer_size].extend(speeds)

        # 손실률 추출
        if protocol in ["RUDP", "UDP"]:
            # RUDP 패킷 손실
            loss_blocks = re.findall(
                r"예상 패킷:\s*(\d+).*?수신 패킷:\s*(\d+).*?손실 패킷:\s*(\d+)",
                content,
                re.DOTALL,
            )

            for expected, received, lost in loss_blocks:
                expected = int(expected)
                lost = int(lost)
                if expected > 0:
                    loss_rate = (lost / expected) * 100
                    self.loss_data[protocol][buffer_size].append(loss_rate)

            # UDP 성공 케이스
            if protocol == "UDP":
                udp_loss = re.findall(r"수신 패킷:\s*(\d+)/(\d+)", content)
                for received, expected in udp_loss:
                    received = int(received)
                    expected = int(expected)
                    if expected > 0:
                        loss_rate = ((expected - received) / expected) * 100
                        self.loss_data[protocol][buffer_size].append(loss_rate)

        print(
            f"처리 완료: {log_file} → {protocol}, 버퍼 크기={buffer_size}, {len(speeds)}개 기록"
        )

    def calculate_stats(self):
        """통계 계산"""
        results = {}

        for protocol in self.data:
            results[protocol] = {}

            for buffer_size in sorted(self.data[protocol].keys()):
                speeds = self.data[protocol][buffer_size]
                losses = self.loss_data[protocol].get(buffer_size, [])

                stats = {
                    "count": len(speeds),
                    "avg_speed": statistics.mean(speeds),
                    "min_speed": min(speeds),
                    "max_speed": max(speeds),
                    "std_dev": statistics.stdev(speeds) if len(speeds) > 1 else 0,
                }

                if losses:
                    stats["avg_loss"] = statistics.mean(losses)
                    stats["min_loss"] = min(losses)
                    stats["max_loss"] = max(losses)
                else:
                    stats["avg_loss"] = 0
                    stats["min_loss"] = 0
                    stats["max_loss"] = 0

                results[protocol][buffer_size] = stats

        return results

    def print_comparison(self, results: Dict):
        """비교 결과 출력"""
        print(f"\n{'='*100}")
        print(f"{'버퍼 크기별 프로토콜 성능 비교':^100}")
        print(f"{'='*100}\n")

        # 모든 버퍼 크기 수집
        all_buffer_sizes = set()
        for protocol_data in results.values():
            all_buffer_sizes.update(protocol_data.keys())

        buffer_sizes = sorted(all_buffer_sizes)
        protocols = sorted(results.keys())

        # 전송 속도 비교
        print(f"【전송 속도 (MB/s)】\n")
        print(f"{'버퍼':<8}", end="")
        for protocol in protocols:
            print(f"{protocol:>12}", end="")
        print()
        print(f"{'-'*100}")

        for buffer_size in buffer_sizes:
            print(f"{buffer_size:<8}", end="")
            for protocol in protocols:
                if buffer_size in results[protocol]:
                    stats = results[protocol][buffer_size]
                    print(f"{stats['avg_speed']:>10.2f}  ", end="")
                else:
                    print(f"{'N/A':>12}", end="")
            print()

        # 손실률 비교 (RUDP, UDP만)
        loss_protocols = [p for p in protocols if p in ["RUDP", "UDP"]]
        if loss_protocols:
            print(f"\n{'='*100}")
            print(f"【패킷 손실률 (%)】\n")
            print(f"{'버퍼':<8}", end="")
            for protocol in loss_protocols:
                print(f"{protocol:>12}", end="")
            print()
            print(f"{'-'*100}")

            for buffer_size in buffer_sizes:
                print(f"{buffer_size:<8}", end="")
                for protocol in loss_protocols:
                    if buffer_size in results[protocol]:
                        stats = results[protocol][buffer_size]
                        if stats["avg_loss"] > 0:
                            print(f"{stats['avg_loss']:>10.2f}  ", end="")
                        else:
                            print(f"{'0.00':>12}", end="")
                    else:
                        print(f"{'N/A':>12}", end="")
                print()

        print(f"\n{'='*100}\n")

        # 최적 버퍼 크기 추천
        print("【권장사항】\n")
        for protocol in protocols:
            if not results[protocol]:
                continue

            # 가장 빠른 버퍼 크기
            best_buffer = max(
                results[protocol].items(), key=lambda x: x[1]["avg_speed"]
            )

            print(
                f"• {protocol}: 버퍼 크기 {best_buffer[0]} "
                f"(평균 {best_buffer[1]['avg_speed']:.2f} MB/s"
            )

            if protocol in ["RUDP", "UDP"] and best_buffer[1]["avg_loss"] > 0:
                print(f"  └ 평균 손실률: {best_buffer[1]['avg_loss']:.2f}%")
            print()

    def export_csv(self, results: Dict, output_file: str):
        """CSV 파일로 내보내기"""
        import csv

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # 헤더
            header = [
                "Protocol",
                "BufferSize",
                "Count",
                "AvgSpeed",
                "MinSpeed",
                "MaxSpeed",
                "StdDev",
                "AvgLoss",
                "MinLoss",
                "MaxLoss",
            ]
            writer.writerow(header)

            # 데이터
            for protocol in sorted(results.keys()):
                for buffer_size in sorted(results[protocol].keys()):
                    stats = results[protocol][buffer_size]
                    row = [
                        protocol,
                        buffer_size,
                        stats["count"],
                        f"{stats['avg_speed']:.2f}",
                        f"{stats['min_speed']:.2f}",
                        f"{stats['max_speed']:.2f}",
                        f"{stats['std_dev']:.2f}",
                        f"{stats['avg_loss']:.2f}",
                        f"{stats['min_loss']:.2f}",
                        f"{stats['max_loss']:.2f}",
                    ]
                    writer.writerow(row)

        print(f"CSV 파일 생성: {output_file}")

    def plot_graph(self, results: Dict, output_file: str = "buffer_comparison.png"):
        """그래프 생성 (matplotlib 필요)"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib

            matplotlib.use("Agg")  # GUI 없이 사용
        except ImportError:
            print("matplotlib이 설치되어 있지 않아 그래프를 생성할 수 없습니다.")
            print("설치: pip install matplotlib")
            return

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

        # 전송 속도 그래프
        for protocol in sorted(results.keys()):
            buffer_sizes = sorted(results[protocol].keys())
            speeds = [results[protocol][bs]["avg_speed"] for bs in buffer_sizes]
            ax1.plot(buffer_sizes, speeds, marker="o", label=protocol, linewidth=2)

        ax1.set_xlabel("Buffer Size", fontsize=12)
        ax1.set_ylabel("Transfer Speed (MB/s)", fontsize=12)
        ax1.set_title("Transfer Speed vs Buffer Size", fontsize=14, fontweight="bold")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 손실률 그래프 (RUDP, UDP만)
        loss_protocols = [p for p in sorted(results.keys()) if p in ["RUDP", "UDP"]]
        if loss_protocols:
            for protocol in loss_protocols:
                buffer_sizes = sorted(results[protocol].keys())
                losses = [results[protocol][bs]["avg_loss"] for bs in buffer_sizes]
                ax2.plot(buffer_sizes, losses, marker="s", label=protocol, linewidth=2)

            ax2.set_xlabel("Buffer Size", fontsize=12)
            ax2.set_ylabel("Packet Loss Rate (%)", fontsize=12)
            ax2.set_title(
                "Packet Loss Rate vs Buffer Size", fontsize=14, fontweight="bold"
            )
            ax2.legend()
            ax2.grid(True, alpha=0.3)
        else:
            ax2.text(
                0.5,
                0.5,
                "No Loss Data Available",
                ha="center",
                va="center",
                fontsize=12,
            )
            ax2.set_xticks([])
            ax2.set_yticks([])

        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches="tight")
        print(f"그래프 생성: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="버퍼 크기별 프로토콜 성능 비교",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  # 모든 로그 파일 비교
  python compare_buffer_sizes.py logs/*_b*.log
  
  # 특정 프로토콜만
  python compare_buffer_sizes.py logs/tcp_b*.log logs/rudp_b*.log
  
  # CSV로 내보내기
  python compare_buffer_sizes.py logs/*_b*.log --csv comparison.csv
  
  # 그래프 생성
  python compare_buffer_sizes.py logs/*_b*.log --plot comparison.png

파일명 형식:
  - protocol_bN.log (예: tcp_b1.log, tcp_b2.log)
  - protocol_buffer_N.log (예: udp_buffer_10.log)
        """,
    )

    parser.add_argument("log_files", nargs="+", help="분석할 로그 파일들")
    parser.add_argument("--csv", type=str, help="CSV 파일로 내보내기")
    parser.add_argument("--plot", type=str, help="그래프 파일로 저장")

    args = parser.parse_args()

    comparison = BufferSizeComparison()

    # 로그 파일 처리
    for log_file in args.log_files:
        if not Path(log_file).exists():
            print(f"경고: 파일을 찾을 수 없습니다: {log_file}")
            continue

        comparison.extract_stats(log_file)

    # 통계 계산
    results = comparison.calculate_stats()

    if not results:
        print("\n분석할 데이터가 없습니다.")
        return

    # 결과 출력
    comparison.print_comparison(results)

    # CSV 내보내기
    if args.csv:
        comparison.export_csv(results, args.csv)

    # 그래프 생성
    if args.plot:
        comparison.plot_graph(results, args.plot)


if __name__ == "__main__":
    main()
