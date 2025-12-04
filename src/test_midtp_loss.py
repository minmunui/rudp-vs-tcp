"""
Test MIDTP with simulated packet loss
"""
import random
from midtp import MIDTP, send_ack, create_packet, parse_packet, METADATA_SEQ, MAX_UDP_PAYLOAD
import socket
import logger
from pathlib import Path
import json
import os
import time

LOSS_RATE = 0.05  # 5% packet loss

class MIDTPWithLoss(MIDTP):
    """MIDTP server that simulates packet loss"""
    
    def start_server(self, host: str, port: int, target_dir: str = "received"):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind((host, port))
        
        try:
            desired_rcvbuf = 4 * 1024 * 1024
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, desired_rcvbuf)
            actual_rcv = server_socket.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            logger.info(f"SO_RCVBUF: {actual_rcv}")
        except OSError as e:
            logger.info(f"SO_RCVBUF 설정 실패: {e}")
        
        logger.info(f"[MIDTP with {LOSS_RATE*100}% loss] 서버 시작: {host}:{port}")
        logger.info(f"파일 저장 디렉터리: {target_dir}")
        
        try:
            while True:
                logger.info("파일 수신 대기 중...")
                
                packets = {}
                metadata = None
                total_chunks = None
                last_seq = None
                client_address = None
                start_time = time.time()
                timeout = 5.0
                dropped_count = 0
                
                server_socket.settimeout(timeout)
                
                receiving = True
                while receiving:
                    try:
                        data, addr = server_socket.recvfrom(MAX_UDP_PAYLOAD)
                        
                        # Simulate packet loss
                        if random.random() < LOSS_RATE:
                            dropped_count += 1
                            continue  # Drop packet
                        
                        if client_address is None:
                            client_address = addr
                            logger.info(f"클라이언트 연결: {addr}")
                        
                        try:
                            seq_num, pkt_last_seq, chunk_size, payload = parse_packet(data)
                            
                            if total_chunks is None:
                                total_chunks = pkt_last_seq
                                logger.info(f"총 청크 수 확인: {total_chunks} (첫 번째 라운드)")
                            
                            last_seq = pkt_last_seq
                            
                            if seq_num == METADATA_SEQ:
                                metadata = json.loads(payload.decode('utf-8'))
                                logger.info(f"메타데이터 수신: {metadata['filename']}, {metadata['file_size']} bytes")
                                packets[seq_num] = payload
                            elif seq_num > 0:
                                packets[seq_num] = payload
                                
                                data_chunks_received = len([s for s in packets.keys() if s > 0])
                                if total_chunks:
                                    progress = (data_chunks_received / total_chunks) * 100
                                    print(f"\r수신 진행률: {progress:.1f}% ({data_chunks_received}/{total_chunks}) [드롭: {dropped_count}]", end="")
                            
                            if total_chunks is not None and last_seq is not None:
                                expected_seqs = set([METADATA_SEQ] + list(range(1, total_chunks + 1)))
                                received_seqs = set(packets.keys())
                                
                                if expected_seqs == received_seqs:
                                    print()
                                    logger.info(f"모든 패킷 수신 완료 (총 드롭: {dropped_count})")
                                    receiving = False
                                elif seq_num == last_seq:
                                    missed_seqs = sorted(list(expected_seqs - received_seqs))
                                    logger.info(f"\n라운드 종료 (last_seq={last_seq}) - ACK 전송: 누락 {len(missed_seqs)}개")
                                    send_ack(missed_seqs, server_socket, client_address)
                        
                        except (Exception) as e:
                            logger.info(f"패킷 파싱 오류: {e}")
                            continue
                    
                    except socket.timeout:
                        logger.info(f"\n수신 타임아웃 (총 드롭: {dropped_count})")
                        
                        if total_chunks is not None and client_address is not None:
                            expected_seqs = set([METADATA_SEQ] + list(range(1, total_chunks + 1)))
                            received_seqs = set(packets.keys())
                            missed_seqs = sorted(list(expected_seqs - received_seqs))
                            
                            if len(missed_seqs) == 0:
                                send_ack([], server_socket, client_address)
                                receiving = False
                            else:
                                logger.info(f"타임아웃 - 누락 패킷 {len(missed_seqs)}개")
                                send_ack(missed_seqs, server_socket, client_address)
                        break
                    
                    except KeyboardInterrupt:
                        raise
                
                # Reconstruct file
                if total_chunks is not None and len(packets) > 0:
                    transfer_time = time.time() - start_time
                    
                    if metadata:
                        filename = metadata['filename']
                    else:
                        logger.info("메타데이터 누락 - 기본 파일명 사용")
                        filename = f"received_{int(time.time())}.bin"
                    
                    filename = os.path.basename(filename)
                    if not filename or any(c in filename for c in r'\/:*?"<>|'):
                        filename = f"received_{int(time.time())}.bin"
                    
                    file_path = os.path.join(target_dir, filename)
                    Path(target_dir).mkdir(parents=True, exist_ok=True)
                    
                    logger.info(f"파일 재조합 중: {file_path}")
                    with open(file_path, 'wb') as f:
                        for i in range(total_chunks):
                            seq_num = i + 1
                            if seq_num in packets:
                                f.write(packets[seq_num])
                            else:
                                logger.info(f"경고: 청크 {seq_num} 누락됨")
                    
                    file_size = os.path.getsize(file_path)
                    transfer_speed = file_size / transfer_time / 1024 / 1024
                    
                    logger.info(f"파일 수신 완료: {filename}")
                    logger.info(f"크기: {file_size} bytes, 시간: {transfer_time:.2f}초")
                    logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
                    logger.info(f"총 드롭된 패킷: {dropped_count}")
                    logger.debug(f"{transfer_speed}")
                    
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


if __name__ == '__main__':
    server = MIDTPWithLoss()
    server.start_server('127.0.0.1', 9998)  # Use different port
