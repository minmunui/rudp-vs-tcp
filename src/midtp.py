"""
MIDTP (Metadata-Integrated Data Transfer Protocol)

Improved UDP-based file transfer protocol where:
- All packets have uniform structure: seq_num, last_seq, chunk_size, data
- Metadata is sent as seq_num=-1 packet (can be retransmitted if lost)
- Every packet includes last_seq so receiver knows total chunks even if metadata is lost
- Robust against packet loss and out-of-order delivery
"""

import array
import json
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
MTU_DATA_SIZE = 1480
PACKET_HEADER_SIZE = 12  # seq_num(4) + last_seq(4) + chunk_size(4)
MAX_UDP_PAYLOAD = 65507

# Metadata packet uses seq_num = 0
# Data chunks use seq_num = 1, 2, 3, ..., N
METADATA_SEQ = 0


def wait_ack(sock: socket.socket, timeout: float = 3.0) -> array.array[int]:
    """
    Wait for ACK packet containing list of missing sequence numbers.

    Args:
        sock: Socket to receive ACK from
        timeout: Timeout in seconds

    Returns:
        Array of missing sequence numbers (can include 0 for metadata)

    Raises:
        socket.timeout: If no ACK received within timeout
    """
    sock.settimeout(timeout)

    try:
        packed_data, addr = sock.recvfrom(KB * 32)
        result_array = array.array("i")
        result_array.frombytes(packed_data)
        logger.info(f"ACK 수신: {list(result_array)}")
        return result_array
    except socket.timeout:
        raise socket.timeout
    finally:
        sock.setblocking(False)


def send_ack(missed_seqs: list[int], sock: socket.socket, target_address: tuple):
    """
    Send ACK with list of missing sequence numbers.

    Args:
        missed_seqs: List of missing seq numbers (can include 0 for metadata)
        sock: Socket to send from
        target_address: Target address
    """
    arr = array.array("i", missed_seqs)
    packed = arr.tobytes()
    logger.info(f"ACK 전송: 누락된 패킷 {len(missed_seqs)}개, 크기 {len(packed)} bytes")

    try:
        sock.sendto(packed, target_address)
    except OSError as e:
        logger.info(f"ACK 전송 실패 (누락 패킷이 너무 많음): {e}")


def create_packet(seq_num: int, last_seq: int, data: bytes) -> bytes:
    """
    Create a uniform packet structure.

    Args:
        seq_num: Sequence number (0 for metadata, 1+ for data chunks)
        last_seq: Total number of data chunks (not including metadata)
        data: Payload data

    Returns:
        Packed packet bytes
    """
    chunk_size = len(data)
    header = struct.pack("!iii", seq_num, last_seq, chunk_size)
    return header + data


def parse_packet(data: bytes) -> tuple[int, int, int, bytes]:
    """
    Parse a uniform packet.

    Args:
        data: Raw packet bytes

    Returns:
        Tuple of (seq_num, last_seq, chunk_size, payload)

    Raises:
        struct.error: If packet is malformed
    """
    if len(data) < PACKET_HEADER_SIZE:
        raise struct.error("Packet too short")

    seq_num, last_seq, chunk_size = struct.unpack("!iii", data[:PACKET_HEADER_SIZE])
    payload = data[PACKET_HEADER_SIZE : PACKET_HEADER_SIZE + chunk_size]

    return seq_num, last_seq, chunk_size, payload


class MIDTP(Protocol):
    """
    Metadata-Integrated Data Transfer Protocol

    Improvements over RUDP:
    - Metadata is a regular packet (seq_num=0) that can be retransmitted
    - Data chunks use seq_num=1,2,3,...,N
    - All packets include last_seq for robustness
    - Uniform packet structure throughout
    """

    MSS = 1472

    def __init__(self):
        pass

    def send_file(
        self,
        filename: str,
        host: str,
        port: int = 9999,
        buffer_size: int = MTU_DATA_SIZE,
        interval: float = 0.0005,
    ):
        """
        Send a file using MIDTP protocol.

        Args:
            filename: Path to file to send
            host: Target host
            port: Target port
            buffer_size: Chunk size for data packets
            interval: Delay between packets (seconds)

        Returns:
            List of loss information from each ACK round
        """
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_address = (host, port)

        # 송신 버퍼 크기를 buffer_size에 맞게 설정 (최소 64KB)
        send_buffer_size = max(buffer_size * 2, 64 * 1024)
        client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, send_buffer_size)

        logger.info(f"[MIDTP] 파일 {filename} 전송 시작")
        logger.info(f"서버: {host}:{port}, 버퍼 크기: {buffer_size}")

        chunk_size = buffer_size - PACKET_HEADER_SIZE
        losses = []

        try:
            # File validation
            if not os.path.exists(filename):
                logger.error(f"파일 {filename}을(를) 찾을 수 없습니다.")
                raise FileNotFoundError(f"파일 {filename}을(를) 찾을 수 없습니다.")

            file_size = os.path.getsize(filename)
            total_chunks = math.ceil(file_size / chunk_size)
            logger.info(f"파일 크기: {file_size} bytes, 청크 수: {total_chunks}")

            # Prepare metadata packet (seq_num = 0)
            # total_chunks is NOT included - receiver learns it from first round's last_seq
            metadata = {
                "filename": os.path.basename(filename),
                "buffer_size": buffer_size,
                "file_size": file_size,
            }
            metadata_json = json.dumps(metadata).encode("utf-8")
            metadata_packet = create_packet(METADATA_SEQ, total_chunks, metadata_json)

            # Build packet dictionary (including metadata)
            packet_dict = {METADATA_SEQ: metadata_packet}

            # Read file and create data packets (seq_num = 1, 2, 3, ...)
            logger.info("데이터 패킷 생성 중...")
            with open(filename, "rb") as f:
                for i in range(total_chunks):
                    chunk_data = f.read(chunk_size)
                    seq_num = i + 1  # Data chunks start at 1
                    packet = create_packet(seq_num, total_chunks, chunk_data)
                    packet_dict[seq_num] = packet

            # Send all packets (metadata first, then data)
            start_time = time.time()

            # Send metadata
            client_socket.sendto(metadata_packet, server_address)
            logger.info(f"메타데이터 패킷 전송 (seq={METADATA_SEQ})")
            time.sleep(interval)

            # Send data chunks (seq_num = 1 to N)
            for i in range(total_chunks):
                seq_num = i + 1
                client_socket.sendto(packet_dict[seq_num], server_address)
                time.sleep(interval)

                # Progress
                progress = ((i + 1) / total_chunks) * 100
                print(
                    f"\r전송 진행률: {progress:.1f}% (패킷 {i + 1}/{total_chunks})",
                    end="",
                )

            print()  # Newline after progress
            logger.info(f"초기 전송 완료 (소요 시간: {time.time() - start_time:.2f}초)")

            # ACK and retransmission phase
            transfer_complete = False
            retry_count = 0
            max_retries = 5

            while not transfer_complete and retry_count < max_retries:
                try:
                    # Wait for ACK
                    logger.info("ACK 대기 중...")
                    missed_seqs = wait_ack(client_socket, timeout=1.0)
                    losses.append(missed_seqs)

                    if len(missed_seqs) == 0:
                        logger.info("전송 완료 확인됨")
                        transfer_complete = True
                    else:
                        logger.info(f"누락 패킷 {len(missed_seqs)}개 재전송 중...")

                        # Find the maximum seq_num in this retransmission round
                        max_retrans_seq = max(missed_seqs)

                        # Rebuild packets with updated last_seq for this retransmission round
                        for seq_num in missed_seqs:
                            if seq_num == METADATA_SEQ:
                                # Rebuild metadata packet with new last_seq
                                metadata_json = json.dumps(metadata).encode("utf-8")
                                retrans_packet = create_packet(
                                    METADATA_SEQ, max_retrans_seq, metadata_json
                                )
                            else:
                                # Rebuild data packet with new last_seq
                                original_packet = packet_dict[seq_num]
                                _, _, _, original_payload = parse_packet(
                                    original_packet
                                )
                                retrans_packet = create_packet(
                                    seq_num, max_retrans_seq, original_payload
                                )

                            client_socket.sendto(retrans_packet, server_address)
                            time.sleep(interval)

                        logger.info(f"재전송 완료 (last_seq={max_retrans_seq})")

                except socket.timeout:
                    retry_count += 1
                    logger.info(f"ACK 타임아웃 (재시도 {retry_count}/{max_retries})")
                    # Resend last packet to trigger ACK
                    if total_chunks > 0:
                        client_socket.sendto(packet_dict[total_chunks], server_address)
                    losses.append(array.array("i", [-999]))  # Timeout marker

            if not transfer_complete:
                logger.info("최대 재시도 횟수 초과")

            # 전송 소요시간 및 속도 계산
            transfer_elapsed = time.time() - start_time
            speed_mbps = (
                file_size / transfer_elapsed / 1024 / 1024
                if transfer_elapsed > 0
                else 0
            )
            logger.info(
                f"전송 소요시간: {transfer_elapsed:.3f}s, 전송 속도: {speed_mbps:.3f} MB/s"
            )

        finally:
            client_socket.close()

        return {
            "success": transfer_complete,
            "transfer_time": transfer_elapsed,
            "speed_mbps": speed_mbps,
            "filesize": file_size,
            "losses": losses,
        }

    def start_server(self, host: str, port: int, target_dir: str = "received"):
        """
        Start MIDTP server to receive files.

        Args:
            host: Host to bind to
            port: Port to bind to
            target_dir: Directory to save received files
        """
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind((host, port))

        # Set large receive buffer
        try:
            desired_rcvbuf = 4 * 1024 * 1024
            server_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_RCVBUF, desired_rcvbuf
            )
            actual_rcv = server_socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            logger.info(f"SO_RCVBUF: {actual_rcv}")
        except OSError as e:
            logger.info(f"SO_RCVBUF 설정 실패: {e}")

        logger.info(f"[MIDTP] 서버 시작: {host}:{port}")
        logger.info(f"파일 저장 디렉터리: {target_dir}")

        try:
            while True:
                logger.info("파일 수신 대기 중...")

                # Receive packets until we have all chunks
                packets = {}  # seq_num -> payload
                metadata = None
                last_seq = None  # Current round's last seq
                total_chunks = None  # Total data chunks (learned from first round)
                client_address = None
                start_time = time.time()
                timeout = 5.0

                server_socket.settimeout(timeout)

                receiving = True
                while receiving:
                    try:
                        data, addr = server_socket.recvfrom(MAX_UDP_PAYLOAD)

                        if client_address is None:
                            client_address = addr
                            logger.info(f"클라이언트 연결: {addr}")

                        # Parse packet
                        try:
                            seq_num, pkt_last_seq, chunk_size, payload = parse_packet(
                                data
                            )

                            # Save total_chunks from first round's last_seq
                            if total_chunks is None:
                                total_chunks = pkt_last_seq
                                logger.info(
                                    f"총 청크 수 확인: {total_chunks} (첫 번째 라운드)"
                                )

                            # Update current round's last_seq
                            last_seq = pkt_last_seq

                            # Handle metadata packet
                            if seq_num == METADATA_SEQ:
                                metadata = json.loads(payload.decode("utf-8"))
                                logger.info(
                                    f"메타데이터 수신: {metadata['filename']}, "
                                    f"{metadata['file_size']} bytes"
                                )
                                packets[seq_num] = payload

                            # Handle data packet
                            elif seq_num > 0:
                                packets[seq_num] = payload

                                # Progress
                                data_chunks_received = len(
                                    [s for s in packets.keys() if s > 0]
                                )
                                if total_chunks:
                                    progress = (
                                        data_chunks_received / total_chunks
                                    ) * 100
                                    print(
                                        f"\r수신 진행률: {progress:.1f}% "
                                        f"({data_chunks_received}/{total_chunks})",
                                        end="",
                                    )

                            # Check if transfer complete and send ACK
                            if total_chunks is not None and last_seq is not None:
                                # Expected seqs based on total_chunks (never changes)
                                expected_seqs = set(
                                    [METADATA_SEQ] + list(range(1, total_chunks + 1))
                                )
                                received_seqs = set(packets.keys())

                                if expected_seqs == received_seqs:
                                    print()  # Newline after progress
                                    logger.info("모든 패킷 수신 완료")
                                    receiving = False

                                # Check if current round ended (received packet with seq_num == last_seq)
                                elif seq_num == last_seq:
                                    missed_seqs = sorted(
                                        list(expected_seqs - received_seqs)
                                    )
                                    logger.info(
                                        f"라운드 종료 (last_seq={last_seq}) - ACK 전송: 누락 {len(missed_seqs)}개"
                                    )
                                    send_ack(missed_seqs, server_socket, client_address)

                        except (struct.error, json.JSONDecodeError, KeyError) as e:
                            logger.info(f"패킷 파싱 오류: {e}")
                            continue

                    except socket.timeout:
                        logger.info("수신 타임아웃")

                        # Send final ACK if we have some packets
                        if total_chunks is not None and client_address is not None:
                            expected_seqs = set(
                                [METADATA_SEQ] + list(range(1, total_chunks + 1))
                            )
                            received_seqs = set(packets.keys())
                            missed_seqs = sorted(list(expected_seqs - received_seqs))

                            if len(missed_seqs) == 0:
                                send_ack([], server_socket, client_address)
                                receiving = False
                            else:
                                logger.info(
                                    f"타임아웃 - 누락 패킷 {len(missed_seqs)}개"
                                )
                                send_ack(missed_seqs, server_socket, client_address)
                        break

                    except KeyboardInterrupt:
                        raise

                # Reconstruct file
                if total_chunks is not None and len(packets) > 0:
                    transfer_time = time.time() - start_time

                    # Determine filename
                    if metadata:
                        filename = metadata["filename"]
                    else:
                        logger.info("메타데이터 누락 - 기본 파일명 사용")
                        filename = f"received_{int(time.time())}.bin"

                    # Sanitize filename
                    filename = os.path.basename(filename)
                    if not filename or any(c in filename for c in r'\/:*?"<>|'):
                        filename = f"received_{int(time.time())}.bin"

                    file_path = os.path.join(target_dir, filename)
                    Path(target_dir).mkdir(parents=True, exist_ok=True)

                    # Write file
                    logger.info(f"파일 재조합 중: {file_path}")
                    with open(file_path, "wb") as f:
                        for i in range(total_chunks):
                            seq_num = i + 1  # Data chunks are 1-based
                            if seq_num in packets:
                                f.write(packets[seq_num])
                            else:
                                logger.info(f"경고: 청크 {seq_num} 누락됨")

                    file_size = os.path.getsize(file_path)
                    transfer_speed = file_size / transfer_time / 1024 / 1024

                    logger.info(f"파일 수신 완료: {filename}")
                    logger.info(f"크기: {file_size} bytes, 시간: {transfer_time:.2f}초")
                    logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
                    logger.debug(f"{transfer_speed}")

                    # Send final ACK
                    if client_address:
                        send_ack([], server_socket, client_address)

        except KeyboardInterrupt:
            logger.info("서버 종료 (KeyboardInterrupt)")
        finally:
            try:
                server_socket.close()
            except Exception:
                pass
            logger.info("서버 소켓 닫음")
