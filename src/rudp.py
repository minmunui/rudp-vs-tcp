import array
import math
import os
import socket
import struct
import time
from pathlib import Path

from protocol import Protocol, BUFFER_SIZE
from utils import flush_receive_buffer, make_new_filename
import logger

KB = 1024
MTU_DATA_SIZE = 1480
REDUNDANCY_SIZE = 8


def wait_ack(sock: socket.socket, timeout: float = 3.0) -> array.array[int]:
    """
    ack를 기다립니다. 일정 시간동안 응답이 없을 경우 예외를 발생시킵니다.
    Args:
        sock : ack를 받아들일 socket을 지정합니다.
        timeout : ack가 해당 시간동안 없을 경우 예외를 발생시킵니다.

    Returns:
        ack를 받았을 경우 해당 ack에 존재하는 missed_seq_numbers를 반환합니다.

    Raises:
        socket.timeout : 해당 소켓에서 일정 시간동안 응답이 없을 경우 발생합니다.
    """
    sock.settimeout(timeout)

    try:
        packed_data, addr = sock.recvfrom(KB * 32)
        # ACK는 정수의 배열
        result_array = array.array("i")
        result_array.frombytes(packed_data)
        logger.info(f"ACK전달받음 : {result_array}")
    except socket.timeout:
        raise socket.timeout

    sock.setblocking(False)
    return result_array


def send_ack(missed_seqs: list[int], sock: socket.socket, target_address: tuple):
    arr = array.array("i", missed_seqs)
    packed = arr.tobytes()
    logger.info(f"전송할 패킷정보 크기 {len(packed)}")
    logger.info(f"손실된 옹량 {len(packed) / 4 * MTU_DATA_SIZE}")
    try:
        sock.sendto(packed, target_address)
    except OSError as e:
        logger.info(f"너무 많은 loss")


def resend_dropped_data(
    sock: socket.socket,
    dropped_seq_numbers: list[int] | array.array[int],
    packet_dict: dict,
    server_addr: tuple[str, int],
):
    """ """
    for seq_number in dropped_seq_numbers:
        sock.sendto(packet_dict[seq_number], server_addr)


def process_ack(
    sock: socket.socket,
    client_address: tuple,
    packet_dict: dict,
    last_seq_number: int,
    timeout: float = 0.5,
) -> array.array:
    """
    ack를 받아 처리하고, ack가 오지 않을 경우 마지막 chucnk를 재전송합니다. ack를 받을 경우 ack를 반환합니다.

    Args:
        sock (socket) : ACK수신 및 마지막 청크 재전송을 위한 소켓입니다.
        client_address (tuple) : 이를 위한 타켓 네트워크 주소 및 포트입니다.
        packet_dict (dict) : ACK를 전달맏지 못할 경우 전송하는데 사용하는 패킷 dict입니다.
        last_seq_number (int): 현재 전송에서 ACK를 유발하는 마지막 seq_number입니다.
        timeout (float): ACK를 기다리는 시간입니다.
    """
    retry_count = 0
    while True:
        try:
            logger.info(f"ACK를 기다리는 중")
            logger.info(f"받아야 할 seq_number: {last_seq_number}")
            return wait_ack(sock, timeout)
        except socket.timeout:
            retry_count += 1
            if retry_count > 5:
                logger.info(f"재전송 초과됨 횟수 초과됨")
                raise socket.timeout
            logger.info(
                f"ACK 재전송 seq_number {last_seq_number} | 재전송 : {retry_count}"
            )
            sock.sendto(packet_dict[last_seq_number], client_address)


class RUDP(Protocol):

    MSS = 1472

    def __init__(self):
        pass

    def send_file(
        self,
        filename: str,
        host: str,
        port: int = 9999,
        buffer_size: int = MTU_DATA_SIZE,
        interval: float = 0.0,
    ):
        # 클라이언트 소켓 생성
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = (host, port)
        logger.info(f"파일 {filename}을(를) 전송합니다...")
        logger.info(f"서버 주소: {host}:{port}")
        logger.info(f"버퍼 크기: {buffer_size}")

        chunk_size = buffer_size - REDUNDANCY_SIZE

        losses = []
        total_packets_sent = 0
        total_packets_lost = 0

        try:
            # 파일 존재 확인
            if not os.path.exists(filename):
                logger.error(f"파일 {filename}을(를) 찾을 수 없습니다.")
                raise FileNotFoundError(f"파일 {filename}을(를) 찾을 수 없습니다.")

            # 파일 크기 확인 및 청크 수 계산
            file_size = os.path.getsize(filename)
            total_chunks = math.ceil(file_size / chunk_size)
            logger.info(f"청크 수: {total_chunks}")

            # 파일 정보 전송 (파일명 + 총 청크 수)
            file_info = struct.pack(
                "!II256s", buffer_size, total_chunks, filename.encode()[:256]
            )
            client_socket.sendto(file_info[:512], server_address)

            # 청크를 보관하기 위한 dictionary
            packet_dict = {}
            # 파일 전송 시작

            start_time = time.time()
            with open(filename, "rb") as f:
                for seq_num in range(total_chunks):
                    chunk_data = f.read(chunk_size)

                    # SEQ 번호와 청크 크기를 포함하여 패킷 구성
                    packet = struct.pack("!II", seq_num, chunk_size) + chunk_data
                    packet_dict[seq_num] = packet
                    client_socket.sendto(packet, server_address)
                    total_packets_sent += 1

                    time.sleep(interval)

                    # 진행률 출력
                    progress = ((seq_num + 1) / total_chunks) * 100
                    print(
                        f"\r전송 진행률: {progress:.1f}% 전송한 패킷 {seq_num:d}",
                        end="",
                    )

            initial_send_time = time.time() - start_time
            logger.info(f"\n파일 {filename} 초기 전송 완료")
            logger.info(f"초기 전송 소요시간 {initial_send_time:.2f}초")

            transfer_complete = False

            last_seq_number = len(packet_dict) - 1
            while not transfer_complete:
                try:
                    dropped_seq_numbers = process_ack(
                        client_socket, server_address, packet_dict, last_seq_number
                    )
                    losses.append(dropped_seq_numbers)
                except socket.timeout:
                    losses.append([-1])
                    break
                if len(dropped_seq_numbers) == 0:
                    logger.info(f"완료된 ACK 전달받음")
                    transfer_complete = True
                else:
                    last_seq_number = max(dropped_seq_numbers)
                    packet_loss_count = len(dropped_seq_numbers)
                    total_packets_lost += packet_loss_count
                    total_packets_sent += packet_loss_count  # 재전송도 카운트
                    logger.info(
                        f"소실패킷 재전송 dropped_seq_numbers: {dropped_seq_numbers}"
                    )
                    resend_dropped_data(
                        client_socket, dropped_seq_numbers, packet_dict, server_address
                    )

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
            logger.info(f"파일 전송 완료: {filename}")
            logger.info(
                f"파일 크기: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)"
            )
            logger.info(f"전송 시간: {total_time:.2f}초")
            logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
            logger.info(f"총 전송 패킷: {total_packets_sent}")
            logger.info(f"손실 패킷: {total_packets_lost}")
            logger.info(f"패킷 손실률: {packet_loss_rate:.2f}%")
            logger.info(f"{'='*50}")

        finally:
            client_socket.close()
            return losses

    def start_server(self, host: str, port: int, target_dir: str = "received"):
        # 서버 소켓 생성
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind((host, port))

        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, BUFFER_SIZE)

        logger.info(f"서버가 {host}:{port}에서 시작되었습니다...")
        logger.info(f"파일을 받을 디렉터리: {target_dir}")

        while True:
            # flush_receive_buffer(server_socket)

            # 파일 정보는 항상 고정된 크기로 받기
            try:
                data, client_address = server_socket.recvfrom(
                    512
                )  # 초기 정보는 작은 크기로 받음
            except:
                # flush_receive_buffer(server_socket)
                continue
            buffer_size, total_chunks, filename = struct.unpack("!II256s", data[:264])
            try:
                filename = filename.decode().strip("\x00")
            except UnicodeDecodeError:
                logger.info(f"잘못된 패킷 감지됨")
                continue
            logger.info(
                f"파일 {filename}을(를) 받기 시작합니다... (총 {total_chunks}개 청크) (버퍼사이즈 {buffer_size})"
            )

            # 이후 데이터 수신할 때는 지정된 버퍼 크기 사용
            chunks = {}
            start_time = time.time()
            timeout = 5

            last_seq_num = total_chunks - 1
            total_packets_received = 0
            total_packets_expected = total_chunks

            is_error = False

            while len(chunks) < total_chunks:
                try:
                    # 실제 데이터 수신 시에는 buffer_size 사용
                    last_signal_time = time.time()

                    server_socket.settimeout(timeout)
                    data, _ = server_socket.recvfrom(buffer_size)

                    seq_num, chunk_size = struct.unpack("!II", data[:REDUNDANCY_SIZE])
                    chunk_data = data[REDUNDANCY_SIZE : REDUNDANCY_SIZE + chunk_size]

                    chunks[seq_num] = chunk_data
                    total_packets_received += 1

                    # 진행률 출력
                    progress = (len(chunks) / total_chunks) * 100
                    print(
                        f"\r수신 진행률: {progress:.1f}% seq_num: {seq_num} / {last_seq_num}",
                        end="",
                    )

                    # 마지막 청크인지 체크
                    if seq_num == last_seq_num:

                        received_seqs = set(chunks.keys())
                        all_seqs = set(range(total_chunks))
                        missed_seqs = list(all_seqs - received_seqs)
                        logger.info(f"마지막 청크 도달 seq_num = {seq_num}")

                        logger.info(f"분실된 패킷 : {missed_seqs}")
                        if len(missed_seqs) > 0:
                            last_seq_num = max(missed_seqs)
                            logger.info(f"새로운 last_seq = {last_seq_num}")

                        send_ack(missed_seqs, server_socket, client_address)

                except (struct.error, IndexError) as e:
                    logger.info(f"\n패킷 손상: {e}")
                    is_error = True
                    break
                except socket.timeout:
                    logger.info(f"데이터 타임아웃")
                    is_error = True
                    break

            if not is_error:
                transfer_end_time = time.time()
                transfer_elapsed_time = transfer_end_time - start_time

                logger.info("\n모든 청크 수신 완료. 파일 재조합 시작...")

                file_path = f"{target_dir}/{filename}"

                Path(target_dir).mkdir(parents=True, exist_ok=True)

                make_new_filename(file_path)

                # 파일 재조합
                write_start = time.time()
                with open(file_path, "wb") as f:
                    for i in range(total_chunks):
                        if i in chunks:
                            f.write(chunks[i])
                        else:
                            logger.info(f"경고: 청크 {i} 유실")

                write_end = time.time()
                write_time = write_end - write_start
                total_elapsed_time = write_end - start_time
                file_size = os.path.getsize(file_path)
                transfer_speed = file_size / transfer_elapsed_time / 1024 / 1024

                # 패킷 손실률 계산 (총 수신 패킷 대비 unique 패킷)
                unique_packets = len(chunks)
                duplicate_packets = total_packets_received - unique_packets
                packet_loss_count = total_packets_expected - unique_packets

                logger.info(f"\n{'='*50}")
                logger.info(f"파일 수신 완료: {filename}")
                logger.info(
                    f"파일 크기: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)"
                )
                logger.info(f"순수 전송 시간: {transfer_elapsed_time:.2f}초")
                logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
                logger.info(f"파일 쓰기 시간: {write_time:.2f}초")
                logger.info(f"전체 시간: {total_elapsed_time:.2f}초")
                logger.info(f"예상 패킷: {total_packets_expected}")
                logger.info(f"수신 패킷: {unique_packets}")
                logger.info(f"중복 수신: {duplicate_packets}")
                logger.info(f"손실 패킷: {packet_loss_count}")
                logger.info(f"저장 경로: {file_path}")
                logger.info(f"{'='*50}")
                logger.debug(f"{transfer_speed}")
