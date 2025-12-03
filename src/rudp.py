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
MAX_UDP_PAYLOAD = 65507


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
        result_array = array.array('i')
        result_array.frombytes(packed_data)
        logger.info(f"ACK전달받음 : {result_array}")
    except socket.timeout:
        raise socket.timeout

    sock.setblocking(False)
    return result_array


def send_ack(missed_seqs: list[int], sock: socket.socket, target_address: tuple):
    arr = array.array('i', missed_seqs)
    packed = arr.tobytes()
    logger.info(f"전송할 패킷정보 크기 {len(packed)}")
    logger.info(f"손실된 옹량 {len(packed) / 4 * MTU_DATA_SIZE}")
    try:
        sock.sendto(packed, target_address)
    except OSError as e:
        logger.info(f"너무 많은 loss")


def resend_dropped_data(sock: socket.socket, dropped_seq_numbers: list[int] | array.array[int], packet_dict: dict,
                        server_addr: tuple[str, int]):
    """

    """
    for seq_number in dropped_seq_numbers:
        sock.sendto(packet_dict[seq_number], server_addr)


def process_ack(sock: socket.socket, client_address: tuple, packet_dict: dict, last_seq_number: int,
                timeout: float = 0.5) -> array.array:
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
            logger.info(f"ACK 재전송 seq_number {last_seq_number} | 재전송 : {retry_count}")
            sock.sendto(packet_dict[last_seq_number], client_address)


class RUDP(Protocol):

    MSS = 1472

    def __init__(self):
        pass

    def send_file(self, filename: str, host: str, port: int = 9999, buffer_size: int = MTU_DATA_SIZE,
                  interval: float = 0.0005):
        # 클라이언트 소켓 생성
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = (host, port)
        logger.info(f"파일 {filename}을(를) 전송합니다...")
        logger.info(f"서버 주소: {host}:{port}")
        logger.info(f"버퍼 크기: {buffer_size}")

        chunk_size = buffer_size - REDUNDANCY_SIZE

        losses = []

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
            file_info = struct.pack('!II256s', buffer_size, total_chunks, filename.encode()[:256])
            logger.info(f"파일 정보 전송: buffer_size={buffer_size}, total_chunks={total_chunks}, 크기={len(file_info)} bytes")
            sent_bytes = client_socket.sendto(file_info[:512], server_address)
            logger.info(f"파일 정보 전송 완료: {sent_bytes} bytes sent to {server_address}")

            # 청크를 보관하기 위한 dictionary
            packet_dict = {}
            # 파일 전송 시작

            start_time = time.time()
            with open(filename, 'rb') as f:
                for seq_num in range(total_chunks):
                    chunk_data = f.read(chunk_size)

                    # SEQ 번호와 청크 크기를 포함하여 패킷 구성
                    packet = struct.pack('!II', seq_num, chunk_size) + chunk_data
                    packet_dict[seq_num] = packet
                    client_socket.sendto(packet, server_address)

                    time.sleep(interval)

                    # 진행률 출력
                    progress = ((seq_num + 1) / total_chunks) * 100
                    print(f"\r전송 진행률: {progress:.1f}% 전송한 패킷 {seq_num:d}", end='')

            logger.info(f"\n파일 {filename} 전송")
            logger.info(f"소요시간 {time.time() - start_time}")
            transfer_complete = False

            last_seq_number = len(packet_dict) - 1
            while not transfer_complete:
                try:
                    dropped_seq_numbers = process_ack(client_socket, server_address, packet_dict, last_seq_number)
                    losses.append(dropped_seq_numbers)
                except socket.timeout:
                    losses.append([-1])
                    break
                if len(dropped_seq_numbers) == 0:
                    logger.info(f"완료된 ACK 전달받음")
                    transfer_complete = True
                else:
                    last_seq_number = max(dropped_seq_numbers)
                    logger.info(f"소실패킷 재전송 dropped_seq_numbers: {dropped_seq_numbers}")
                    resend_dropped_data(client_socket, dropped_seq_numbers, packet_dict, server_address)

        finally:
            client_socket.close()
        
        return losses

    def start_server(self, host: str, port: int, target_dir: str = "received"):
        # 서버 소켓 생성
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind((host, port))

        # Try to give the socket a reasonably large OS receive buffer (4MB).
        # Note: OS may clamp this to allowed limits.
        try:
            desired_rcvbuf = 4 * 1024 * 1024
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, desired_rcvbuf)
            actual_rcv = server_socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            logger.info(f"SO_RCVBUF set to {actual_rcv}")
        except OSError as e:
            logger.info(f"Failed to set SO_RCVBUF: {e}")

        logger.info(f"서버가 {host}:{port}에서 시작되었습니다...")
        logger.info(f"파일을 받을 디렉터리: {target_dir}")

        try:
            while True:
                # flush_receive_buffer(server_socket)

                # 파일 정보는 항상 고정된 크기로 받기
                logger.info("파일 정보 대기 중...")
                try:
                    # Use a large receive buffer for the initial metadata packet to avoid
                    # WSAEMSGSIZE (WinError 10040) when a sender uses a large datagram.
                    data, client_address = server_socket.recvfrom(MAX_UDP_PAYLOAD)
                    logger.info(f"패킷 수신: {len(data)} bytes from {client_address}")
                except KeyboardInterrupt:
                    raise
                except OSError as e:
                    logger.info(f"Socket error while waiting for file info: {e}")
                    continue

                try:
                    buffer_size, total_chunks, filename = struct.unpack('!II256s', data[:264])
                except struct.error:
                    logger.info(f"잘못된 초기 패킷 수신(길이 부족) - 무시합니다")
                    continue

                try:
                    filename = filename.decode().strip('\x00')
                except UnicodeDecodeError:
                    logger.info(f"잘못된 패킷 감지됨")
                    continue

                logger.info(f"파일 {filename}을(를) 받기 시작합니다... (총 {total_chunks}개 청크) (버퍼사이즈 {buffer_size})")

                # 이후 데이터 수신할 때는 지정된 버퍼 크기 사용
                chunks = {}
                start_time = time.time()
                timeout = 5

                last_seq_num = total_chunks - 1

                is_error = False

                while len(chunks) < total_chunks:
                    try:
                        # 실제 데이터 수신 시에는 buffer_size 사용
                        last_signal_time = time.time()

                        server_socket.settimeout(timeout)
                        # Ensure the recv buffer used here is at least the maximum UDP payload
                        # or the negotiated buffer_size. This prevents recvfrom from failing
                        # when the incoming datagram is larger than the provided buffer.
                        recv_buf = max(buffer_size, MAX_UDP_PAYLOAD)
                        data, _ = server_socket.recvfrom(recv_buf)

                        seq_num, chunk_size = struct.unpack('!II', data[:REDUNDANCY_SIZE])
                        chunk_data = data[REDUNDANCY_SIZE:REDUNDANCY_SIZE + chunk_size]

                        chunks[seq_num] = chunk_data

                        # 진행률 출력
                        progress = (len(chunks) / total_chunks) * 100
                        print(f"\r수신 진행률: {progress:.1f}% seq_num: {seq_num} / {last_seq_num}", end="")

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
                    except KeyboardInterrupt:
                        logger.info("서버가 KeyboardInterrupt로 종료됩니다")
                        raise

                if not is_error:
                    transfer_end_time = time.time()
                    transfer_elapsed_time = transfer_end_time - start_time
                    logger.info(f"transfer_elapsed_time\t{transfer_elapsed_time}")

                    logger.info("\n모든 청크 수신 완료. 파일 재조합 시작...")

                    file_path = f"{target_dir}/{filename}"

                    Path(target_dir).mkdir(parents=True, exist_ok=True)

                    make_new_filename(file_path)

                    # 파일 재조합
                    with open(file_path, 'wb') as f:
                        for i in range(total_chunks):
                            # logger.info()(f"{i}번째 청크 조합중\n{chunks[i]}", end='')
                            if i in chunks:
                                f.write(chunks[i])
                            else:
                                logger.info(f"경고: 청크 {i} 유실")

                    total_end_time = time.time()
                    total_elapsed_time = total_end_time - start_time
                    file_size = os.path.getsize(file_path)
                    logger.info(f"순수 전송 속도 \t{file_size / transfer_elapsed_time / 1024 / 1024}MB/s")
                    logger.debug(f"{file_size / transfer_elapsed_time / 1024 / 1024}")
                    logger.info(f"전체 속도 \t{file_size / total_elapsed_time / 1024 / 1024}MB/s")
                    logger.info(f"파일 {filename} 수신 완료!")
                    logger.info(f"저장 경로 {file_path}")
        except KeyboardInterrupt:
            logger.info("서버가 KeyboardInterrupt로 종료됩니다")
        finally:
            try:
                server_socket.close()
            except Exception:
                pass
            logger.info("서버 소켓 닫음")
