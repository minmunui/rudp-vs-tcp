import socket
import time
import os
import struct
import json
import logger
import math
from pathlib import Path

from protocol import Protocol, BUFFER_SIZE
from utils import make_new_filename


class UDP(Protocol):
    """순수 UDP 프로토콜 구현 - 신뢰성 없음, 손실 감지"""

    MSS = 1472  # UDP MTU에서 헤더를 뺀 크기

    def send_file(
        self,
        filename: str,
        host: str,
        port: int,
        buffer_size: int,
        interval: float = 0.0,
    ):
        """
        UDP로 파일을 전송합니다. 재전송 없이 한 번만 전송하며, 손실이 있을 경우 서버에서 감지됩니다.

        Args:
            filename (str): 전송할 파일 이름입니다.
            host (str): 전송할 서버의 주소입니다.
            port (int): 전송할 서버의 포트입니다.
            buffer_size (int): 패킷 크기입니다.
            interval (float): 전송 간격입니다.

        Returns:
            bool: 전송 성공 여부를 반환합니다.
        """
        logger.info(f"UDP로 전송 시작 - 파일: {filename}")
        logger.info(f"서버 주소: {host}:{port}")
        logger.info(f"버퍼 크기: {buffer_size}")

        try:
            # UDP 소켓 생성
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            server_address = (host, port)

            # 파일 존재 확인
            if not os.path.exists(filename):
                logger.error(f"파일 {filename}을(를) 찾을 수 없습니다.")
                return False

            # 파일 크기 확인 및 청크 수 계산
            file_size = os.path.getsize(filename)
            chunk_size = (
                buffer_size - 12
            )  # 12 bytes for seq_num(4) + total_chunks(4) + chunk_size(4)
            total_chunks = math.ceil(file_size / chunk_size)

            logger.info(
                f"파일 크기: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)"
            )
            logger.info(f"총 청크 수: {total_chunks}")

            # 파일 정보 전송 (filename + filesize + total_chunks)
            file_info = {
                "filename": os.path.basename(filename),
                "filesize": file_size,
                "total_chunks": total_chunks,
                "chunk_size": chunk_size,
            }
            file_info_json = json.dumps(file_info).encode("utf-8")

            # 헤더 패킷 전송 (마커로 식별 가능하도록)
            header_packet = b"FILE_INFO:" + file_info_json
            sock.sendto(header_packet, server_address)
            time.sleep(0.1)  # 헤더 처리 대기

            # 파일 데이터 전송
            start_time = time.time()
            total_packets_sent = 0

            with open(filename, "rb") as f:
                for seq_num in range(total_chunks):
                    chunk_data = f.read(chunk_size)

                    # 패킷 구성: seq_num(4) + total_chunks(4) + data_size(4) + data
                    packet = (
                        struct.pack("!III", seq_num, total_chunks, len(chunk_data))
                        + chunk_data
                    )
                    sock.sendto(packet, server_address)
                    total_packets_sent += 1

                    time.sleep(interval)

                    # 진행률 출력
                    progress = ((seq_num + 1) / total_chunks) * 100
                    print(
                        f"\r전송 진행률: {progress:.1f}% ({seq_num + 1}/{total_chunks} 패킷)",
                        end="",
                    )

            print()  # 줄바꿈

            # 전송 완료 마커 전송
            end_packet = b"TRANSFER_END"
            sock.sendto(end_packet, server_address)

            # 서버로부터 결과 수신 (타임아웃 5초)
            sock.settimeout(5.0)
            try:
                response_data, _ = sock.recvfrom(4096)
                response = json.loads(response_data.decode("utf-8"))

                transfer_time = time.time() - start_time
                transfer_speed = file_size / transfer_time / 1024 / 1024

                # 통계 출력
                logger.info(f"\n{'='*50}")
                logger.info(f"파일 전송 완료: {filename}")
                logger.info(
                    f"파일 크기: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)"
                )
                logger.info(f"전송 시간: {transfer_time:.2f}초")
                logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
                logger.info(f"전송 패킷: {total_packets_sent}")

                if response["success"]:
                    logger.info(f"서버 수신 상태: 성공")
                    logger.info(
                        f"수신된 패킷: {response['received_packets']}/{response['expected_packets']}"
                    )

                    if response["packet_loss"] > 0:
                        loss_rate = (
                            response["packet_loss"] / response["expected_packets"] * 100
                        )
                        logger.warning(f"⚠️  패킷 손실 감지!")
                        logger.warning(f"손실 패킷: {response['packet_loss']}")
                        logger.warning(f"손실률: {loss_rate:.2f}%")
                    else:
                        logger.info(f"패킷 손실: 없음 ✓")
                else:
                    logger.error(
                        f"❌ 서버 수신 실패: {response.get('error', '알 수 없는 오류')}"
                    )
                    logger.error(
                        f"수신된 패킷: {response['received_packets']}/{response['expected_packets']}"
                    )
                    logger.error(f"손실 패킷: {response['packet_loss']}")

                logger.info(f"{'='*50}")

                return response["success"]

            except socket.timeout:
                logger.error("서버 응답 타임아웃")
                return False
            except json.JSONDecodeError:
                logger.error("서버 응답 파싱 실패")
                return False

        except Exception as e:
            logger.error(f"파일 전송 중 오류 발생: {e}")
            return False

        finally:
            sock.close()

    def start_server(
        self,
        host: str,
        port: int,
        target_dir: str = "received",
        log_filename: str = None,
    ):
        """
        UDP 서버를 시작합니다. 패킷 손실을 감지하고 통계를 출력합니다.

        Args:
            host (str): 서버의 주소입니다.
            port (int): 서버의 포트입니다.
            target_dir (str): 파일을 저장할 디렉토리입니다.
            log_filename (str): 로그 파일 이름입니다. None이면 자동 생성됩니다.
        """
        if log_filename:
            logger.get_logger().start_file_logging(log_filename)
        else:
            logger.get_logger().start_file_logging()
        logger.info(f"UDP 서버 시작 - {host}:{port}")
        logger.info(f"파일 저장 디렉토리: {target_dir}")

        # 저장 디렉토리 확인 및 생성
        Path(target_dir).mkdir(parents=True, exist_ok=True)

        # UDP 소켓 생성
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)

        logger.info(
            f"서버가 {host}:{port}에서 실행 중입니다. 클라이언트 연결 대기 중..."
        )

        try:
            while True:
                # 파일 정보 수신 대기
                try:
                    data, client_address = sock.recvfrom(4096)

                    # 헤더 패킷 확인
                    if not data.startswith(b"FILE_INFO:"):
                        continue

                    # 파일 정보 파싱
                    file_info_json = data[10:]  # 'FILE_INFO:' 제거
                    file_info = json.loads(file_info_json.decode("utf-8"))

                    filename = file_info["filename"]
                    filesize = file_info["filesize"]
                    total_chunks = file_info["total_chunks"]
                    chunk_size = file_info["chunk_size"]

                    logger.info(f"\n클라이언트 연결: {client_address}")
                    logger.info(f"파일 수신 시작: {filename}")
                    logger.info(
                        f"예상 크기: {filesize:,} bytes ({filesize/1024/1024:.2f} MB)"
                    )
                    logger.info(f"예상 청크: {total_chunks}")

                    # 데이터 수신
                    chunks = {}
                    start_time = time.time()
                    timeout = 10.0  # 10초 타임아웃
                    sock.settimeout(timeout)

                    last_packet_time = time.time()

                    while True:
                        try:
                            data, addr = sock.recvfrom(65536)

                            # 전송 완료 마커 확인
                            if data == b"TRANSFER_END":
                                logger.info(f"\n전송 완료 마커 수신")
                                break

                            # 패킷 파싱
                            if len(data) < 12:
                                continue

                            seq_num, total, data_size = struct.unpack("!III", data[:12])
                            chunk_data = data[12 : 12 + data_size]

                            chunks[seq_num] = chunk_data
                            last_packet_time = time.time()

                            # 진행률 출력
                            progress = (len(chunks) / total_chunks) * 100
                            print(
                                f"\r수신 진행률: {progress:.1f}% ({len(chunks)}/{total_chunks} 패킷)",
                                end="",
                            )

                        except socket.timeout:
                            # 일정 시간 동안 패킷이 없으면 종료
                            if time.time() - last_packet_time > 3.0:
                                logger.info(f"\n타임아웃 - 수신 종료")
                                break

                    print()  # 줄바꿈
                    receive_time = time.time() - start_time

                    # 패킷 손실 확인
                    received_packets = len(chunks)
                    expected_packets = total_chunks
                    packet_loss = expected_packets - received_packets
                    loss_rate = (
                        (packet_loss / expected_packets * 100)
                        if expected_packets > 0
                        else 0
                    )

                    # 파일 재조합 및 저장
                    success = False
                    error_message = ""

                    if packet_loss == 0:
                        # 손실 없음 - 파일 저장
                        filepath = os.path.join(target_dir, filename)
                        filepath = make_new_filename(filepath)

                        write_start = time.time()
                        with open(filepath, "wb") as f:
                            for i in range(total_chunks):
                                if i in chunks:
                                    f.write(chunks[i])

                        write_end = time.time()
                        write_time = write_end - write_start
                        total_time = write_end - start_time
                        actual_size = os.path.getsize(filepath)
                        transfer_speed = actual_size / receive_time / 1024 / 1024

                        # 성공 통계 출력
                        logger.info(f"\n{'='*50}")
                        logger.info(f"파일 수신 완료: {filename}")
                        logger.info(
                            f"파일 크기: {actual_size:,} bytes ({actual_size/1024/1024:.2f} MB)"
                        )
                        logger.info(f"순수 전송 시간: {receive_time:.2f}초")
                        logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
                        logger.info(f"파일 쓰기 시간: {write_time:.2f}초")
                        logger.info(f"전체 시간: {total_time:.2f}초")
                        logger.info(f"수신 패킷: {received_packets}/{expected_packets}")
                        logger.info(f"패킷 손실: 없음 ✓")
                        logger.info(f"저장 경로: {filepath}")
                        logger.info(f"{'='*50}")
                        logger.debug(f"{transfer_speed}")

                        success = True
                    else:
                        # 패킷 손실 발생 - 에러 처리
                        missing_packets = [
                            i for i in range(total_chunks) if i not in chunks
                        ]

                        logger.error(f"\n{'='*50}")
                        logger.error(f"❌ UDP 전송 실패: 패킷 손실 감지")
                        logger.error(f"파일: {filename}")
                        logger.error(f"예상 크기: {filesize:,} bytes")
                        logger.error(
                            f"수신 패킷: {received_packets}/{expected_packets}"
                        )
                        logger.error(f"손실 패킷: {packet_loss}")
                        logger.error(f"손실률: {loss_rate:.2f}%")
                        logger.error(
                            f"누락된 패킷 번호 (처음 10개): {missing_packets[:10]}"
                        )
                        if len(missing_packets) > 10:
                            logger.error(f"... 외 {len(missing_packets) - 10}개")
                        logger.error(f"{'='*50}")

                        error_message = (
                            f"패킷 손실 {packet_loss}개 (손실률 {loss_rate:.2f}%)"
                        )
                        success = False

                    # 클라이언트에 결과 응답
                    response = {
                        "success": success,
                        "received_packets": received_packets,
                        "expected_packets": expected_packets,
                        "packet_loss": packet_loss,
                        "loss_rate": loss_rate,
                        "error": error_message,
                    }
                    response_json = json.dumps(response).encode("utf-8")
                    sock.sendto(response_json, client_address)

                    # 타임아웃 해제
                    sock.settimeout(None)

                except json.JSONDecodeError:
                    logger.error("잘못된 파일 정보 패킷")
                    continue
                except Exception as e:
                    logger.error(f"수신 중 오류 발생: {e}")
                    continue

        except KeyboardInterrupt:
            logger.info("\n서버를 종료합니다.")
        finally:
            sock.close()
