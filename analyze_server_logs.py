#!/usr/bin/env python3
"""
서버 측 성능 로그 파서 및 분석 도구

서버 로그 파일에서 전송 속도와 패킷 손실률을 추출하여
프로토콜별, 버퍼 크기별로 정리합니다.

사용법:
    python analyze_server_logs.py logs/tcp_server.log
    python analyze_server_logs.py logs/*.log  # 모든 로그 분석
"""

import re
import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
import statistics


class ServerLogAnalyzer:
    """서버 로그 분석기"""

    def __init__(self):
        self.records = []

    def parse_log_file(self, log_file: str) -> List[Dict]:
        """로그 파일에서 전송 기록 추출"""
        records = []

        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 프로토콜 타입 추정 (파일명 또는 로그 내용에서)
        protocol = self._detect_protocol(log_file, content)

        # 파일 수신 완료 블록 찾기
        # ========== 로 구분된 블록 추출
        blocks = re.findall(r"={50}.*?파일 수신 완료:.*?={50}", content, re.DOTALL)

        for block in blocks:
            record = self._parse_block(block, protocol)
            if record:
                records.append(record)

        return records

    def _detect_protocol(self, filename: str, content: str) -> str:
        """프로토콜 타입 감지"""
        filename_lower = filename.lower()

        if "tcp" in filename_lower or "TCP로 서버 시작" in content:
            return "TCP"
        elif "udp" in filename_lower and "rudp" not in filename_lower:
            if "UDP 서버 시작" in content:
                return "UDP"
        elif "rudp" in filename_lower or "RUDP" in content:
            return "RUDP"
        elif "quic" in filename_lower or "QUIC" in content:
            return "QUIC"

        # 로그 내용으로 판단
        if "손실 패킷:" in content and "재전송" not in content:
            return "UDP"
        elif "패킷 손실률:" in content or "손실 패킷:" in content:
            return "RUDP"

        return "UNKNOWN"

    def _parse_block(self, block: str, protocol: str) -> Dict:
        """블록에서 정보 추출"""
        record = {"protocol": protocol}

        # 파일명
        filename_match = re.search(r"파일 수신 완료:\s*(\S+)", block)
        if filename_match:
            record["filename"] = filename_match.group(1)

        # 파일 크기
        size_match = re.search(
            r"파일 크기:\s*([\d,]+)\s*bytes\s*\(([\d.]+)\s*MB\)", block
        )
        if size_match:
            record["file_size_bytes"] = int(size_match.group(1).replace(",", ""))
            record["file_size_mb"] = float(size_match.group(2))

        # 전송 속도
        speed_match = re.search(r"전송 속도:\s*([\d.]+)\s*MB/s", block)
        if speed_match:
            record["transfer_speed"] = float(speed_match.group(1))

        # 전송 시간
        time_match = re.search(r"순수 전송 시간:\s*([\d.]+)초", block)
        if time_match:
            record["transfer_time"] = float(time_match.group(1))

        # RUDP 패킷 손실 정보
        if protocol == "RUDP":
            expected_match = re.search(r"예상 패킷:\s*(\d+)", block)
            received_match = re.search(r"수신 패킷:\s*(\d+)", block)
            lost_match = re.search(r"손실 패킷:\s*(\d+)", block)

            if expected_match and received_match and lost_match:
                expected = int(expected_match.group(1))
                received = int(received_match.group(1))
                lost = int(lost_match.group(1))

                record["packets_expected"] = expected
                record["packets_received"] = received
                record["packets_lost"] = lost
                record["packet_loss_rate"] = (
                    (lost / expected * 100) if expected > 0 else 0
                )

        # UDP 손실 정보
        elif protocol == "UDP":
            # UDP 성공 케이스
            expected_match = re.search(r"수신 패킷:\s*(\d+)/(\d+)", block)
            if expected_match:
                received = int(expected_match.group(1))
                expected = int(expected_match.group(2))
                record["packets_expected"] = expected
                record["packets_received"] = received
                record["packets_lost"] = expected - received
                record["packet_loss_rate"] = (
                    ((expected - received) / expected * 100) if expected > 0 else 0
                )

        return record if "transfer_speed" in record else None

    def analyze_by_protocol(self, records: List[Dict]) -> Dict:
        """프로토콜별 통계 분석"""
        protocol_stats = defaultdict(list)

        for record in records:
            protocol = record["protocol"]
            protocol_stats[protocol].append(record)

        results = {}
        for protocol, data in protocol_stats.items():
            speeds = [r["transfer_speed"] for r in data]
            loss_rates = [
                r.get("packet_loss_rate", 0) for r in data if "packet_loss_rate" in r
            ]

            results[protocol] = {
                "count": len(data),
                "avg_speed": statistics.mean(speeds),
                "min_speed": min(speeds),
                "max_speed": max(speeds),
                "std_dev_speed": statistics.stdev(speeds) if len(speeds) > 1 else 0,
                "avg_loss_rate": statistics.mean(loss_rates) if loss_rates else 0,
                "records": data,
            }

        return results

    def export_csv(self, records: List[Dict], output_file: str):
        """CSV 형식으로 내보내기"""
        if not records:
            print("내보낼 데이터가 없습니다.")
            return

        import csv

        # 모든 가능한 필드 수집
        all_fields = set()
        for record in records:
            all_fields.update(record.keys())

        fields = [
            "protocol",
            "filename",
            "file_size_mb",
            "transfer_speed",
            "transfer_time",
            "packet_loss_rate",
            "packets_expected",
            "packets_received",
            "packets_lost",
        ]
        fields = [f for f in fields if f in all_fields]

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)

        print(f"CSV 파일 생성: {output_file}")

    def print_summary(self, results: Dict):
        """결과 요약 출력"""
        print(f"\n{'='*80}")
        print(f"{'서버 로그 분석 결과':^80}")
        print(f"{'='*80}\n")

        print(
            f"{'프로토콜':<12} {'전송 횟수':<12} {'평균 속도':<15} {'최소/최대':<20} {'평균 손실률':<15}"
        )
        print(f"{'-'*80}")

        for protocol in sorted(results.keys()):
            stats = results[protocol]
            loss_str = (
                f"{stats['avg_loss_rate']:.2f}%" if stats["avg_loss_rate"] > 0 else "-"
            )

            print(
                f"{protocol:<12} {stats['count']:<12} "
                f"{stats['avg_speed']:>6.2f} MB/s   "
                f"{stats['min_speed']:>6.2f} / {stats['max_speed']:>6.2f}     "
                f"{loss_str:<15}"
            )

        print(f"{'-'*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="서버 로그 파일 분석 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  # 단일 로그 파일 분석
  python analyze_server_logs.py logs/tcp_server.log
  
  # 여러 로그 파일 분석
  python analyze_server_logs.py logs/tcp_server.log logs/udp_server.log
  
  # CSV로 내보내기
  python analyze_server_logs.py logs/*.log --csv results.csv
  
  # JSON으로 내보내기
  python analyze_server_logs.py logs/*.log --json results.json
        """,
    )

    parser.add_argument("log_files", nargs="+", help="분석할 로그 파일들")
    parser.add_argument("--csv", type=str, help="CSV 파일로 내보내기")
    parser.add_argument("--json", type=str, help="JSON 파일로 내보내기")
    parser.add_argument(
        "--summary", action="store_true", default=True, help="요약 정보 출력 (기본값)"
    )

    args = parser.parse_args()

    analyzer = ServerLogAnalyzer()
    all_records = []

    # 모든 로그 파일 처리
    for log_file in args.log_files:
        if not Path(log_file).exists():
            print(f"경고: 파일을 찾을 수 없습니다: {log_file}")
            continue

        print(f"분석 중: {log_file}")
        records = analyzer.parse_log_file(log_file)
        all_records.extend(records)
        print(f"  → {len(records)}개 전송 기록 발견")

    if not all_records:
        print("\n분석할 데이터가 없습니다.")
        return

    # 프로토콜별 분석
    results = analyzer.analyze_by_protocol(all_records)

    # 요약 출력
    if args.summary:
        analyzer.print_summary(results)

    # CSV 내보내기
    if args.csv:
        analyzer.export_csv(all_records, args.csv)

    # JSON 내보내기
    if args.json:
        output_data = {
            "total_records": len(all_records),
            "protocol_stats": results,
            "records": all_records,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"JSON 파일 생성: {args.json}")


if __name__ == "__main__":
    main()
