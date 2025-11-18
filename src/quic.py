import asyncio
import os
import time
import ssl
from pathlib import Path
from typing import Optional

try:
    from aioquic.asyncio import connect, serve
    from aioquic.asyncio.protocol import QuicConnectionProtocol
    from aioquic.quic.configuration import QuicConfiguration
    from aioquic.quic.events import QuicEvent, StreamDataReceived, HandshakeCompleted

    QUIC_AVAILABLE = True
except ImportError:
    QUIC_AVAILABLE = False

from protocol import Protocol
import logger


class QuicFileClientProtocol(QuicConnectionProtocol):
    """QUIC 파일 전송 클라이언트 프로토콜"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_data = None
        self.filename = None
        self.response_received = asyncio.Event()
        self.response_data = b""

    def quic_event_received(self, event: QuicEvent):
        if isinstance(event, StreamDataReceived):
            # 서버로부터의 응답 수신
            self.response_data += event.data
            if event.end_stream:
                self.response_received.set()


class QuicFileServerProtocol(QuicConnectionProtocol):
    """QUIC 파일 수신 서버 프로토콜"""

    def __init__(self, *args, target_dir: str = "received", **kwargs):
        super().__init__(*args, **kwargs)
        self.target_dir = target_dir
        self.streams = {}  # stream_id -> {data, filename, filesize, start_time}

    def quic_event_received(self, event: QuicEvent):
        if isinstance(event, HandshakeCompleted):
            logger.info("QUIC 핸드셰이크 완료")

        elif isinstance(event, StreamDataReceived):
            stream_id = event.stream_id

            # 새로운 스트림 초기화
            if stream_id not in self.streams:
                self.streams[stream_id] = {
                    "data": bytearray(),
                    "filename": None,
                    "filesize": None,
                    "start_time": time.time(),
                    "header_parsed": False,
                }

            stream_info = self.streams[stream_id]
            stream_info["data"].extend(event.data)

            # 헤더 파싱 (처음 256바이트에 파일명과 크기 정보)
            if not stream_info["header_parsed"] and len(stream_info["data"]) >= 264:
                import struct

                filesize = struct.unpack("!Q", bytes(stream_info["data"][:8]))[0]
                filename = (
                    bytes(stream_info["data"][8:264]).decode("utf-8").strip("\x00")
                )

                stream_info["filename"] = filename
                stream_info["filesize"] = filesize
                stream_info["header_parsed"] = True
                stream_info["data"] = bytearray(stream_info["data"][264:])  # 헤더 제거

                logger.info(f"파일 수신 시작: {filename} (크기: {filesize:,} bytes)")

            # 스트림 종료 시 파일 저장
            if event.end_stream and stream_info["header_parsed"]:
                self._save_file(stream_id)

    def _save_file(self, stream_id: int):
        """파일을 디스크에 저장"""
        stream_info = self.streams[stream_id]
        filename = stream_info["filename"]
        filesize = stream_info["filesize"]
        file_data = stream_info["data"]
        start_time = stream_info["start_time"]

        # 디렉토리 생성
        Path(self.target_dir).mkdir(parents=True, exist_ok=True)
        filepath = os.path.join(self.target_dir, filename)

        # 파일 쓰기
        write_start = time.time()
        with open(filepath, "wb") as f:
            f.write(file_data)
        write_end = time.time()

        # 통계 계산
        transfer_time = write_start - start_time
        write_time = write_end - write_start
        total_time = write_end - start_time
        actual_size = len(file_data)
        transfer_speed = (
            actual_size / transfer_time / 1024 / 1024 if transfer_time > 0 else 0
        )

        # 통계 출력
        logger.info(f"\n{'='*50}")
        logger.info(f"파일 수신 완료: {filename}")
        logger.info(f"예상 크기: {filesize:,} bytes")
        logger.info(
            f"실제 크기: {actual_size:,} bytes ({actual_size/1024/1024:.2f} MB)"
        )
        logger.info(f"순수 전송 시간: {transfer_time:.2f}초")
        logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
        logger.info(f"파일 쓰기 시간: {write_time:.2f}초")
        logger.info(f"전체 시간: {total_time:.2f}초")
        logger.info(f"저장 경로: {filepath}")
        logger.info(f"{'='*50}")
        logger.debug(f"{transfer_speed}")

        # 클라이언트에 응답 전송
        response = f"파일 수신 완료. 전송 속도: {transfer_speed:.2f} MB/s".encode(
            "utf-8"
        )
        self._quic.send_stream_data(stream_id, response, end_stream=True)

        # 스트림 정보 삭제
        del self.streams[stream_id]


class QUIC(Protocol):
    """QUIC 프로토콜 구현"""

    MSS = 1200  # QUIC의 일반적인 최대 UDP 페이로드 크기

    def __init__(self):
        if not QUIC_AVAILABLE:
            raise ImportError(
                "aioquic 라이브러리가 설치되지 않았습니다. "
                "다음 명령어로 설치하세요: pip install aioquic"
            )

    def send_file(
        self,
        filename: str,
        host: str,
        port: int,
        buffer_size: int = 65536,
        interval: float = 0.0,
    ):
        """
        QUIC를 사용하여 파일을 전송합니다.

        Args:
            filename: 전송할 파일 경로
            host: 서버 주소
            port: 서버 포트
            buffer_size: 버퍼 크기 (사용되지 않음, 인터페이스 호환성을 위해 유지)
            interval: 전송 간격 (사용되지 않음)
        """
        return asyncio.run(self._send_file_async(filename, host, port))

    async def _send_file_async(self, filename: str, host: str, port: int):
        """비동기 파일 전송"""
        logger.info(f"QUIC로 전송 시작 - 파일: {filename}")
        logger.info(f"서버 주소: {host}:{port}")

        if not os.path.exists(filename):
            logger.error(f"파일을 찾을 수 없습니다: {filename}")
            return False

        # QUIC 설정
        configuration = QuicConfiguration(
            is_client=True,
            alpn_protocols=["file-transfer"],
        )
        configuration.verify_mode = (
            ssl.CERT_NONE
        )  # 개발용 (프로덕션에서는 인증서 검증 필요)

        start_time = time.time()

        try:
            # 서버 연결
            async with connect(
                host,
                port,
                configuration=configuration,
                create_protocol=QuicFileClientProtocol,
            ) as client:
                connection_time = time.time() - start_time
                logger.info(f"서버 연결 완료 (소요 시간: {connection_time:.2f}초)")

                # 파일 읽기
                filesize = os.path.getsize(filename)
                with open(filename, "rb") as f:
                    file_data = f.read()

                # 헤더 생성 (8바이트 파일크기 + 256바이트 파일명)
                import struct

                header = struct.pack("!Q", filesize) + os.path.basename(
                    filename
                ).encode("utf-8").ljust(256, b"\x00")

                # 스트림 생성 및 데이터 전송
                stream_id = client._quic.get_next_available_stream_id()
                transfer_start = time.time()

                client._quic.send_stream_data(
                    stream_id, header + file_data, end_stream=True
                )
                client.transmit()

                # 응답 대기
                await asyncio.wait_for(client.response_received.wait(), timeout=30.0)

                transfer_end = time.time()
                transfer_time = transfer_end - transfer_start
                total_time = transfer_end - start_time
                transfer_speed = filesize / transfer_time / 1024 / 1024

                # 서버 응답
                response = client.response_data.decode("utf-8")
                logger.info(f"서버 응답: {response}")

                # 통계 출력
                logger.info(f"\n{'='*50}")
                logger.info(f"파일 전송 완료: {filename}")
                logger.info(
                    f"파일 크기: {filesize:,} bytes ({filesize/1024/1024:.2f} MB)"
                )
                logger.info(f"연결 시간: {connection_time:.2f}초")
                logger.info(f"전송 시간: {transfer_time:.2f}초")
                logger.info(f"전체 시간: {total_time:.2f}초")
                logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
                logger.info(f"{'='*50}")

                return True

        except Exception as e:
            logger.error(f"파일 전송 중 오류 발생: {e}")
            return False

    def start_server(
        self,
        host: str,
        port: int,
        target_dir: str = "received",
        log_filename: str = None,
    ):
        """
        QUIC 서버를 시작합니다.

        Args:
            host: 서버 바인딩 주소
            port: 서버 포트
            target_dir: 파일 저장 디렉토리
            log_filename: 로그 파일 이름. None이면 자동 생성됩니다.
        """
        return asyncio.run(
            self._start_server_async(host, port, target_dir, log_filename)
        )

    async def _start_server_async(
        self, host: str, port: int, target_dir: str, log_filename: str = None
    ):
        """비동기 서버 시작"""
        if log_filename:
            logger.get_logger().start_file_logging(log_filename)
        else:
            logger.get_logger().start_file_logging()
        logger.info(f"QUIC 서버 시작 - {host}:{port}")
        logger.info(f"파일 저장 디렉토리: {target_dir}")

        # 디렉토리 생성
        Path(target_dir).mkdir(parents=True, exist_ok=True)

        # 자체 서명 인증서 생성 (개발용)
        cert_path, key_path = self._generate_self_signed_cert()

        # QUIC 설정
        configuration = QuicConfiguration(
            is_client=False,
            alpn_protocols=["file-transfer"],
        )
        configuration.load_cert_chain(cert_path, key_path)

        # 서버 시작
        try:
            await serve(
                host,
                port,
                configuration=configuration,
                create_protocol=lambda *args, **kwargs: QuicFileServerProtocol(
                    *args, target_dir=target_dir, **kwargs
                ),
            )

            # 서버 무한 실행
            await asyncio.Future()  # 무한 대기

        except KeyboardInterrupt:
            logger.info("서버를 종료합니다.")
        except Exception as e:
            logger.error(f"서버 오류: {e}")

    def _generate_self_signed_cert(self):
        """자체 서명 인증서 생성 (개발용)"""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime

        # 개인키 생성
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # 인증서 생성
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Seoul"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Seoul"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "RUDP-TCP-QUIC"),
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName("localhost"),
                        x509.DNSName("127.0.0.1"),
                    ]
                ),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )

        # 파일로 저장
        cert_dir = Path("certs")
        cert_dir.mkdir(exist_ok=True)

        cert_path = cert_dir / "cert.pem"
        key_path = cert_dir / "key.pem"

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        with open(key_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        logger.info(f"자체 서명 인증서 생성: {cert_path}, {key_path}")

        return str(cert_path), str(key_path)
