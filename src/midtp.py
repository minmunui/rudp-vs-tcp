import array
import math
import os
import socket
import struct
import time
from pathlib import Path

from protocol import Protocol, BUFFER_SIZE
from utils import make_new_filename
import logger

KB = 1024
HEADER_SIZE = 8  # seq_num (4B) + seq_last (4B)


class MIDTP(Protocol):
    """
    MIDTP: Massive Irregular Data Transfer Protocol
    
    에폭 단위 누적 검증과 선택적 재전송을 통해
    저손실 지역망 환경에서 대용량 파일 전송을 최적화한 프로토콜
    """

    MSS = 1472

    def __init__(self):
        pass

    def send_file(
        self,
        filename: str,
        host: str,
        port: int = 9997,
        buffer_size: int = 1472,
        interval: float = 0.0,
    ):
        """
        알고리즘 1: 송신자 측 MIDTP
        
        Args:
            filename: 전송할 파일 경로
            host: 수신자 호스트 주소
            port: 수신자 포트 번호
            buffer_size: 세그먼트 크기 (헤더 포함)
            interval: 세그먼트 간 전송 간격 (테스트용)
        """
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = (host, port)
        
        logger.info(f"파일 {filename}을(를) MIDTP로 전송합니다...")
        logger.info(f"서버 주소: {host}:{port}")
        logger.info(f"버퍼 크기: {buffer_size}")

        chunk_size = buffer_size - HEADER_SIZE

        # 통계 변수
        total_packets_sent = 0
        total_packets_lost = 0
        epoch_count = 0

        try:
            # 파일 존재 확인
            if not os.path.exists(filename):
                logger.error(f"파일 {filename}을(를) 찾을 수 없습니다.")
                raise FileNotFoundError(f"파일 {filename}을(를) 찾을 수 없습니다.")

            # 파일 크기 확인 및 세그먼트 수 계산
            file_size = os.path.getsize(filename)
            total_segments = math.ceil(file_size / chunk_size)
            logger.info(f"총 세그먼트 수: {total_segments}")

            # 파일 정보 전송 (파일명 + 총 세그먼트 수 + 버퍼 크기)
            file_info = struct.pack(
                "!II256s", buffer_size, total_segments, filename.encode()[:256]
            )
            client_socket.sendto(file_info[:512], server_address)

            # S: 모든 세그먼트 배열 (딕셔너리로 구현)
            segments = {}
            
            # 파일을 세그먼트로 분할하여 저장
            with open(filename, "rb") as f:
                for seq_num in range(total_segments):
                    chunk_data = f.read(chunk_size)
                    segments[seq_num] = chunk_data

            # num_seq: 전송할 세그먼트 번호 목록
            num_seq = list(range(total_segments))
            # seq_last: 현재 에폭의 마지막 세그먼트 번호
            seq_last = total_segments - 1
            done = False

            start_time = time.time()

            # 메인 전송 루프 (알고리즘 1, line 6-22)
            while not done:
                epoch_count += 1
                logger.info(f"\n{'='*50}")
                logger.info(f"에폭 {epoch_count} 시작 - 전송할 세그먼트: {len(num_seq)}개")
                
                # 에폭 내 세그먼트 전송 (알고리즘 1, line 7-9)
                for i, seq_num in enumerate(num_seq):
                    chunk_data = segments[seq_num]
                    
                    # 헤더 구성: seq_num (4B) + seq_last (4B)
                    header = struct.pack("!II", seq_num, seq_last)
                    packet = header + chunk_data
                    
                    client_socket.sendto(packet, server_address)
                    total_packets_sent += 1

                    if interval > 0:
                        time.sleep(interval)

                    # 진행률 출력
                    progress = ((i + 1) / len(num_seq)) * 100
                    print(
                        f"\r에폭 {epoch_count} 전송: {progress:.1f}% ({i+1}/{len(num_seq)})",
                        end="",
                    )

                print()  # 줄바꿈
                logger.info(f"에폭 {epoch_count} 전송 완료")

                # ACK 대기 및 타임아웃 처리 (알고리즘 1, line 11-21)
                timeout = 3.0
                client_socket.settimeout(timeout)
                
                try:
                    # ACK 수신
                    ack_data, _ = client_socket.recvfrom(KB * 32)
                    ack_array = array.array("i")
                    ack_array.frombytes(ack_data)
                    
                    if len(ack_array) == 0:
                        # 빈 ACK: 전송 완료 (알고리즘 1, line 16-17)
                        logger.info("빈 ACK 수신 - 전송 완료!")
                        done = True
                    else:
                        # 누락 세그먼트 목록 수신: 선택적 재전송 (알고리즘 1, line 18-20)
                        num_seq = list(ack_array)
                        seq_last = num_seq[-1]  # 재전송 에폭의 마지막 seq
                        
                        lost_count = len(num_seq)
                        total_packets_lost += lost_count
                        
                        logger.info(f"누락된 세그먼트: {lost_count}개")
                        logger.info(f"누락 목록: {num_seq[:10]}{'...' if len(num_seq) > 10 else ''}")
                        
                except socket.timeout:
                    # 타임아웃: 마지막 세그먼트 또는 ACK 손실 (알고리즘 1, line 13-14)
                    logger.info("타임아웃 발생 - 마지막 세그먼트 재전송")
                    
                    last_seg_num = seq_last
                    chunk_data = segments[last_seg_num]
                    header = struct.pack("!II", last_seg_num, seq_last)
                    packet = header + chunk_data
                    
                    client_socket.sendto(packet, server_address)
                    total_packets_sent += 1

            # 전송 완료 후 통계 출력
            end_time = time.time()
            total_time = end_time - start_time
            transfer_speed = file_size / total_time / 1024 / 1024  # MB/s
            packet_loss_rate = (
                (total_packets_lost / total_packets_sent * 100)
                if total_packets_sent > 0
                else 0
            )

            logger.info(f"\n{'='*50}")
            logger.info(f"MIDTP 파일 전송 완료: {filename}")
            logger.info(
                f"파일 크기: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)"
            )
            logger.info(f"전송 시간: {total_time:.2f}초")
            logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
            logger.info(f"총 에폭: {epoch_count}")
            logger.info(f"총 전송 패킷: {total_packets_sent}")
            logger.info(f"손실 패킷: {total_packets_lost}")
            logger.info(f"패킷 손실률: {packet_loss_rate:.2f}%")
            logger.info(f"{'='*50}")

        finally:
            client_socket.close()

    def start_server(
        self,
        host: str,
        port: int,
        target_dir: str = "received",
        log_filename: str = None,
    ):
        """
        알고리즘 2: 수신자 측 MIDTP
        
        Args:
            host: 바인딩할 호스트 주소
            port: 바인딩할 포트 번호
            target_dir: 수신 파일 저장 디렉터리
            log_filename: 로그 파일명 (선택)
        """
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind((host, port))
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)

        if log_filename:
            logger.get_logger().start_file_logging(log_filename)

        logger.info(f"MIDTP 서버가 {host}:{port}에서 시작되었습니다...")
        logger.info(f"파일을 받을 디렉터리: {target_dir}")

        while True:
            try:
                # 파일 정보 수신 (초기 핸드셰이크)
                data, client_address = server_socket.recvfrom(512)
                buffer_size, total_segments, filename = struct.unpack("!II256s", data[:264])
                
                try:
                    filename = filename.decode().strip("\x00")
                except UnicodeDecodeError:
                    logger.info("잘못된 패킷 감지됨")
                    continue
                
                logger.info(
                    f"파일 {filename} 수신 시작 (총 {total_segments}개 세그먼트, 버퍼: {buffer_size})"
                )

                # R: 수신된 세그먼트 저장 배열 (알고리즘 2, line 1)
                segments = {}
                # received: 수신된 순서 번호 집합 (알고리즘 2, line 3)
                received = set()
                # seq_last: 현재 에폭의 마지막 세그먼트 번호 (알고리즘 2, line 2)
                seq_last = None
                
                epoch_count = 0
                start_time = time.time()
                
                # 메인 수신 루프 (알고리즘 2, line 5-20)
                while True:
                    try:
                        # 세그먼트 수신 대기 (알고리즘 2, line 6)
                        server_socket.settimeout(5.0)
                        data, _ = server_socket.recvfrom(buffer_size)
                        
                        # 헤더에서 seq_num과 seq_last 추출 (알고리즘 2, line 7)
                        seq_num, seq_last_recv = struct.unpack("!II", data[:HEADER_SIZE])
                        chunk_data = data[HEADER_SIZE:]
                        
                        # 첫 세그먼트에서 seq_last 설정
                        if seq_last is None:
                            seq_last = seq_last_recv
                            epoch_count += 1
                            logger.info(f"에폭 {epoch_count} 시작 (seq_last={seq_last})")
                        
                        # 새로운 에폭 감지 (seq_last 변경)
                        if seq_last_recv != seq_last:
                            seq_last = seq_last_recv
                            epoch_count += 1
                            logger.info(f"에폭 {epoch_count} 시작 (seq_last={seq_last})")
                        
                        # 세그먼트 저장 및 순서 번호 기록 (알고리즘 2, line 9-10)
                        if seq_num not in received:  # 중복 방지
                            segments[seq_num] = chunk_data
                            received.add(seq_num)
                        
                        # 진행률 출력
                        progress = (len(received) / total_segments) * 100
                        print(
                            f"\r에폭 {epoch_count} 수신: {progress:.1f}% (seq={seq_num}, last={seq_last})",
                            end="",
                        )
                        
                        # 에폭 완료 체크 (알고리즘 2, line 12)
                        if seq_num == seq_last:
                            print()  # 줄바꿈
                            logger.info(f"에폭 {epoch_count} 완료 감지")
                            
                            # 누락 세그먼트 계산 (알고리즘 2, line 13)
                            all_seqs = set(range(total_segments))
                            missing = sorted(list(all_seqs - received))
                            
                            if len(missing) == 0:
                                # 모든 세그먼트 수신: 빈 ACK 전송 (알고리즘 2, line 14-16)
                                logger.info("모든 세그먼트 수신 완료 - 빈 ACK 전송")
                                empty_ack = array.array("i", []).tobytes()
                                server_socket.sendto(empty_ack, client_address)
                                break  # 전송 완료
                            else:
                                # 누락 세그먼트 있음: 누락 목록을 ACK에 포함 (알고리즘 2, line 17-19)
                                logger.info(f"누락된 세그먼트: {len(missing)}개")
                                logger.info(f"누락 목록: {missing[:10]}{'...' if len(missing) > 10 else ''}")
                                
                                ack_array = array.array("i", missing)
                                server_socket.sendto(ack_array.tobytes(), client_address)
                                # received 집합 유지하여 다음 재전송 에폭 계속
                    
                    except socket.timeout:
                        logger.error("수신 타임아웃 - 전송 중단")
                        break
                    except (struct.error, IndexError) as e:
                        logger.error(f"패킷 손상: {e}")
                        continue

                # 파일 재조합 및 저장
                if len(received) == total_segments:
                    transfer_end_time = time.time()
                    transfer_elapsed_time = transfer_end_time - start_time
                    
                    logger.info(f"\n모든 세그먼트 수신 완료. 파일 재조합 시작...")
                    
                    file_path = f"{target_dir}/{filename}"
                    Path(target_dir).mkdir(parents=True, exist_ok=True)
                    make_new_filename(file_path)
                    
                    # 파일 쓰기
                    write_start = time.time()
                    with open(file_path, "wb") as f:
                        for i in range(total_segments):
                            if i in segments:
                                f.write(segments[i])
                            else:
                                logger.error(f"치명적 오류: 세그먼트 {i} 누락")
                    
                    write_end = time.time()
                    write_time = write_end - write_start
                    total_elapsed_time = write_end - start_time
                    file_size = os.path.getsize(file_path)
                    transfer_speed = file_size / transfer_elapsed_time / 1024 / 1024
                    
                    logger.info(f"\n{'='*50}")
                    logger.info(f"MIDTP 파일 수신 완료: {filename}")
                    logger.info(
                        f"파일 크기: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)"
                    )
                    logger.info(f"순수 전송 시간: {transfer_elapsed_time:.2f}초")
                    logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
                    logger.info(f"파일 쓰기 시간: {write_time:.2f}초")
                    logger.info(f"전체 시간: {total_elapsed_time:.2f}초")
                    logger.info(f"총 에폭: {epoch_count}")
                    logger.info(f"수신 세그먼트: {len(received)}/{total_segments}")
                    logger.info(f"저장 경로: {file_path}")
                    logger.info(f"{'='*50}")
                    logger.debug(f"{transfer_speed}")
                else:
                    logger.error(f"전송 실패: {len(received)}/{total_segments} 세그먼트만 수신")

            except Exception as e:
                logger.error(f"오류 발생: {e}")
                continue