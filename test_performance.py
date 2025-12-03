#!/usr/bin/env python3
"""
네트워크 프로토콜 성능 테스트 스크립트

각 프로토콜(TCP, UDP, RUDP, QUIC)별로 여러 번 전송하여
평균 전송률과 통계를 측정합니다.

사용법:
    서버: python test_performance.py --mode server --protocol tcp
    클라이언트: python test_performance.py --mode client --file test.jpg --target 192.168.0.60
"""

import subprocess
import time
import json
import re
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
import argparse


class PerformanceTest:
    """프로토콜 성능 테스트"""

    def __init__(
        self,
        test_file: str,
        target: str = "localhost",
        iterations: int = 10,
        interval: float = 0.0,
    ):
        self.test_file = test_file
        self.target = target
        self.iterations = iterations
        self.interval = interval
        self.results = {}

        # 프로토콜별 포트 설정
        self.protocols = {
            "tcp": 10000,
            "udp": 9998,
            "rudp": 9999,
            "midtp": 9997,
            "quic": 4433,
        }

    def extract_speed(self, output: str) -> Optional[float]:
        """로그에서 전송 속도 추출 (MB/s)"""
        # 다양한 패턴 시도
        patterns = [
            r"전송 속도:\s*(\d+\.?\d*)\s*MB/s",
            r"transfer speed:\s*(\d+\.?\d*)\s*MB/s",
            r"(\d+\.?\d*)\s*MB/s",
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def extract_packet_loss(self, output: str) -> Optional[float]:
        """로그에서 패킷 손실률 추출 (%)"""
        patterns = [
            r"패킷 손실률:\s*(\d+\.?\d*)%",
            r"손실률:\s*(\d+\.?\d*)%",
            r"packet loss rate:\s*(\d+\.?\d*)%",
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return None

    def run_single_test(self, protocol: str, buffer_size: int = 1) -> Dict:
        """단일 테스트 실행"""
        port = self.protocols[protocol]

        cmd = [
            "python3",
            "src/main.py",
            "--file",
            self.test_file,
            "--client",
            "True",
            "--protocol",
            protocol,
            "--target",
            self.target,
            "--port",
            str(port),
            "--buffer_size",
            str(buffer_size),
            "--interval",
            str(self.interval),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            output = result.stdout + result.stderr

            # 전송 속도 추출
            speed = self.extract_speed(output)
            packet_loss = self.extract_packet_loss(output)

            success = result.returncode == 0 and speed is not None

            return {
                "success": success,
                "speed": speed,
                "packet_loss": packet_loss,
                "output": (
                    output[-500:] if len(output) > 500 else output
                ),  # 마지막 500자만
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "speed": None,
                "packet_loss": None,
                "error": "Timeout",
            }
        except Exception as e:
            return {
                "success": False,
                "speed": None,
                "packet_loss": None,
                "error": str(e),
            }

    def test_protocol(self, protocol: str, buffer_size: int = 1) -> Dict:
        """특정 프로토콜에 대해 여러 번 테스트"""
        print(f"\n{'='*60}")
        print(
            f"테스트 시작: {protocol.upper()} (버퍼 크기: {buffer_size}, interval: {self.interval})"
        )
        print(f"{'='*60}")

        results = []
        speeds = []
        packet_losses = []

        for i in range(self.iterations):
            print(f"\n[{i+1}/{self.iterations}] 전송 중...", end=" ", flush=True)

            result = self.run_single_test(protocol, buffer_size)
            results.append(result)

            if result["success"]:
                speeds.append(result["speed"])
                if result["packet_loss"] is not None:
                    packet_losses.append(result["packet_loss"])
                print(f"✓ {result['speed']:.2f} MB/s")
            else:
                print(f"✗ 실패")
                if "error" in result:
                    print(f"   에러: {result['error']}")

            # 다음 테스트 전 대기
            # if i < self.iterations - 1:
            time.sleep(2)

        # 통계 계산
        success_count = len(speeds)
        success_rate = (success_count / self.iterations) * 100

        stats = {
            "protocol": protocol,
            "buffer_size": buffer_size,
            "iterations": self.iterations,
            "success_count": success_count,
            "success_rate": success_rate,
            "speeds": speeds,
            "packet_losses": packet_losses,
        }

        if speeds:
            stats.update(
                {
                    "avg_speed": sum(speeds) / len(speeds),
                    "min_speed": min(speeds),
                    "max_speed": max(speeds),
                    "std_dev": self._std_dev(speeds),
                }
            )

        if packet_losses:
            stats.update(
                {
                    "avg_packet_loss": sum(packet_losses) / len(packet_losses),
                    "min_packet_loss": min(packet_losses),
                    "max_packet_loss": max(packet_losses),
                }
            )

        return stats

    def _std_dev(self, data: List[float]) -> float:
        """표준편차 계산"""
        if len(data) < 2:
            return 0.0
        mean = sum(data) / len(data)
        variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
        return variance**0.5

    def run_all_tests(
        self,
        protocols: Optional[List[str]] = None,
        buffer_sizes: Optional[List[int]] = None,
    ):
        """모든 프로토콜 테스트"""
        if protocols is None:
            protocols = list(self.protocols.keys())

        if buffer_sizes is None:
            buffer_sizes = [1]

        print(f"\n{'='*60}")
        print(f"성능 테스트 시작")
        print(f"{'='*60}")
        print(f"테스트 파일: {self.test_file}")
        print(f"파일 크기: {os.path.getsize(self.test_file):,} bytes")
        print(f"대상 서버: {self.target}")
        print(f"반복 횟수: {self.iterations}")
        print(f"전송 간격: {self.interval}초")
        print(f"테스트 프로토콜: {', '.join(p.upper() for p in protocols)}")
        print(f"버퍼 크기: {buffer_sizes}")

        all_results = []

        for protocol in protocols:
            for buffer_size in buffer_sizes:
                try:
                    result = self.test_protocol(protocol, buffer_size)
                    all_results.append(result)
                    self.results[f"{protocol}_b{buffer_size}"] = result
                except KeyboardInterrupt:
                    print("\n\n테스트 중단됨")
                    break

        # 결과 출력
        self.print_summary(all_results)

        # 결과 저장
        self.save_results(all_results)

    def print_summary(self, results: List[Dict]):
        """결과 요약 출력"""
        print(f"\n\n{'='*80}")
        print(f"{'테스트 결과 요약':^80}")
        print(f"{'='*80}\n")

        # 헤더
        print(
            f"{'프로토콜':<12} {'버퍼':<8} {'성공률':<10} {'평균 속도':<15} {'최소/최대':<20} {'패킷손실':<12}"
        )
        print(f"{'-'*80}")

        for result in results:
            protocol = result["protocol"].upper()
            buffer_size = result["buffer_size"]
            success_rate = result["success_rate"]

            if result.get("avg_speed"):
                avg_speed = f"{result['avg_speed']:.2f} MB/s"
                min_max = f"{result['min_speed']:.2f} / {result['max_speed']:.2f}"
            else:
                avg_speed = "N/A"
                min_max = "N/A"

            if result.get("avg_packet_loss") is not None:
                packet_loss = f"{result['avg_packet_loss']:.2f}%"
            else:
                packet_loss = "-"

            print(
                f"{protocol:<12} {buffer_size:<8} {success_rate:>6.1f}%   {avg_speed:<15} {min_max:<20} {packet_loss:<12}"
            )

        print(f"{'-'*80}\n")

        # 가장 빠른 프로토콜
        fastest = max(
            (r for r in results if r.get("avg_speed")),
            key=lambda x: x["avg_speed"],
            default=None,
        )
        if fastest:
            print(
                f"🏆 가장 빠른 설정: {fastest['protocol'].upper()} "
                f"(버퍼 크기: {fastest['buffer_size']}) - "
                f"{fastest['avg_speed']:.2f} MB/s"
            )

        # 가장 안정적인 프로토콜
        most_reliable = max(results, key=lambda x: x["success_rate"])
        print(
            f"✓ 가장 안정적: {most_reliable['protocol'].upper()} "
            f"(버퍼 크기: {most_reliable['buffer_size']}) - "
            f"성공률 {most_reliable['success_rate']:.1f}%"
        )

    def save_results(self, results: List[Dict]):
        """결과를 JSON 파일로 저장"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")

        # 클라이언트 결과 디렉터리 생성
        results_dir = Path("experiment_results/client")
        results_dir.mkdir(parents=True, exist_ok=True)

        filename = results_dir / f"client_results_{timestamp}.json"

        # 실험 파라미터 및 결과 저장
        output = {
            "experiment_info": {
                "timestamp": timestamp,
                "role": "client",
                "test_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "test_parameters": {
                "test_file": self.test_file,
                "file_size_bytes": os.path.getsize(self.test_file),
                "file_size_mb": round(os.path.getsize(self.test_file) / 1024 / 1024, 2),
                "target_server": self.target,
                "iterations": self.iterations,
                "interval_seconds": self.interval,
            },
            "protocols_tested": [r["protocol"] for r in results],
            "buffer_sizes_tested": list(set(r["buffer_size"] for r in results)),
            "results": results,
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n✓ 클라이언트 결과 저장: {filename}")

        # CSV 형식으로도 저장 (분석 용이)
        csv_filename = results_dir / f"client_results_{timestamp}.csv"
        self._save_results_csv(results, csv_filename)
        print(f"✓ CSV 결과 저장: {csv_filename}")

    def _save_results_csv(self, results: List[Dict], filename: Path):
        """결과를 CSV 파일로 저장"""
        with open(filename, "w", encoding="utf-8") as f:
            # 헤더
            f.write(
                "Protocol,BufferSize,Iterations,SuccessCount,SuccessRate(%),"
                "AvgSpeed(MB/s),MinSpeed(MB/s),MaxSpeed(MB/s),StdDev,"
                "AvgPacketLoss(%),MinPacketLoss(%),MaxPacketLoss(%)\n"
            )

            # 데이터
            for r in results:
                f.write(
                    f"{r['protocol']},{r['buffer_size']},{r['iterations']},"
                    f"{r['success_count']},{r['success_rate']:.2f},"
                    f"{r.get('avg_speed', 0):.2f},{r.get('min_speed', 0):.2f},"
                    f"{r.get('max_speed', 0):.2f},{r.get('std_dev', 0):.2f},"
                    f"{r.get('avg_packet_loss', 0):.2f},"
                    f"{r.get('min_packet_loss', 0):.2f},"
                    f"{r.get('max_packet_loss', 0):.2f}\n"
                )


def start_server(protocol: str, port: Optional[int] = None, save_logs: bool = True):
    """서버 시작"""
    protocols = {"tcp": 10000, "udp": 9998, "rudp": 9999, "midtp": 9997, "quic": 4433}

    if port is None:
        port = protocols.get(protocol, 9999)

    # 서버 로그 디렉터리 생성
    if save_logs:
        logs_dir = Path("experiment_results/server")
        logs_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        log_filename = logs_dir / f"server_{protocol}_{timestamp}.log"
    else:
        log_filename = None

    print(f"{'='*60}")
    print(f"{protocol.upper()} 서버 시작")
    print(f"{'='*60}")
    print(f"프로토콜: {protocol}")
    print(f"포트: {port}")
    if log_filename:
        print(f"로그 파일: {log_filename}")
    print(f"\n서버 실행 중... (Ctrl+C로 종료)")
    print(f"{'='*60}\n")

    cmd = [
        "python",
        "src/main.py",
        "--protocol",
        protocol,
        "--target",
        "0.0.0.0",
        "--port",
        str(port),
    ]

    # 로그 파일 옵션 추가
    if log_filename:
        cmd.extend(["--log", str(log_filename)])

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\n서버 종료")
        if log_filename:
            print(f"✓ 서버 로그 저장됨: {log_filename}")


def main():
    parser = argparse.ArgumentParser(
        description="네트워크 프로토콜 성능 테스트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  # 서버 시작
  python test_performance.py --mode server --protocol tcp
  
  # 모든 프로토콜 테스트 (기본 10회)
  python test_performance.py --mode client --file image.JPG --target 192.168.0.60
  
  # 특정 프로토콜만 테스트
  python test_performance.py --mode client --file image.JPG --target 192.168.0.60 --protocols tcp udp
  
  # 반복 횟수 변경
  python test_performance.py --mode client --file image.JPG --iterations 20
  
  # 버퍼 크기 테스트
  python test_performance.py --mode client --file image.JPG --buffer-sizes 1 2 4
  
  # interval 설정 (0.001초 간격)
  python test_performance.py --mode client --file image.JPG --interval 0.001
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["server", "client"],
        required=True,
        help="서버 또는 클라이언트 모드",
    )
    parser.add_argument(
        "--protocol",
        type=str,
        choices=["tcp", "udp", "rudp", "midtp", "quic"],
        help="서버 모드: 실행할 프로토콜",
    )
    parser.add_argument("--file", type=str, help="클라이언트 모드: 전송할 파일")
    parser.add_argument(
        "--target",
        type=str,
        default="localhost",
        help="클라이언트 모드: 서버 주소 (기본: localhost)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=10,
        help="클라이언트 모드: 반복 횟수 (기본: 10)",
    )
    parser.add_argument(
        "--protocols",
        nargs="+",
        choices=["tcp", "udp", "rudp", "midtp", "quic"],
        help="클라이언트 모드: 테스트할 프로토콜 (기본: 전체)",
    )
    parser.add_argument(
        "--buffer-sizes",
        nargs="+",
        type=int,
        default=[1],
        help="클라이언트 모드: 테스트할 버퍼 크기 (기본: 1)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.0,
        help="클라이언트 모드: 패킷 전송 간격(초) (기본: 0.0 - 최대 속도)",
    )
    parser.add_argument("--port", type=int, help="서버 모드: 포트 번호")
    parser.add_argument(
        "--no-logs",
        action="store_true",
        help="서버 모드: 로그 파일 저장 안 함",
    )

    args = parser.parse_args()

    if args.mode == "server":
        if not args.protocol:
            parser.error("서버 모드에서는 --protocol 옵션이 필요합니다")
        start_server(args.protocol, args.port, save_logs=not args.no_logs)

    elif args.mode == "client":
        if not args.file:
            parser.error("클라이언트 모드에서는 --file 옵션이 필요합니다")

        if not os.path.exists(args.file):
            print(f"오류: 파일을 찾을 수 없습니다: {args.file}")
            sys.exit(1)

        tester = PerformanceTest(args.file, args.target, args.iterations, args.interval)
        tester.run_all_tests(args.protocols, args.buffer_sizes)


if __name__ == "__main__":
    main()
