"""
QUIC-based file transfer protocol

Uses aioquic library for QUIC implementation.
QUIC provides built-in reliability, congestion control, and 0-RTT support.
"""

import asyncio
import os
import time
import json
from pathlib import Path

try:
    from aioquic.asyncio import connect, serve
    from aioquic.asyncio.protocol import QuicConnectionProtocol
    from aioquic.quic.configuration import QuicConfiguration
    from aioquic.quic.events import QuicEvent, StreamDataReceived
except ImportError:
    print("aioquic not installed. Install with: pip install aioquic")
    raise

from protocol import Protocol
import logger


class FileTransferClientProtocol(QuicConnectionProtocol):
    """QUIC client protocol for file transfer"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_sent = asyncio.Event()
        self.transfer_time = 0
        self.file_size = 0
    
    async def send_file(self, filename: str):
        """Send a file over QUIC stream"""
        start_time = time.time()
        
        # Check file exists
        if not os.path.exists(filename):
            logger.error(f"파일 {filename}을(를) 찾을 수 없습니다.")
            raise FileNotFoundError(f"파일 {filename}을(를) 찾을 수 없습니다.")
        
        file_size = os.path.getsize(filename)
        self.file_size = file_size
        basename = os.path.basename(filename)
        
        logger.info(f"[QUIC] 파일 {basename} 전송 시작 ({file_size} bytes)")
        
        # Create a stream
        stream_id = self._quic.get_next_available_stream_id()
        
        # Send metadata as JSON
        metadata = {
            'filename': basename,
            'file_size': file_size
        }
        metadata_json = json.dumps(metadata).encode('utf-8')
        metadata_size = len(metadata_json).to_bytes(4, 'big')
        
        # Send metadata size + metadata
        self._quic.send_stream_data(stream_id, metadata_size + metadata_json, end_stream=False)
        self.transmit()
        
        # Send file data
        with open(filename, 'rb') as f:
            chunk_size = 1024 * 1024  # 1MB chunks
            sent = 0
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                
                is_last = (sent + len(chunk) >= file_size)
                self._quic.send_stream_data(stream_id, chunk, end_stream=is_last)
                self.transmit()
                
                sent += len(chunk)
                progress = (sent / file_size) * 100
                print(f"\r전송 진행률: {progress:.1f}% ({sent}/{file_size} bytes)", end='')
        
        print()  # Newline
        self.transfer_time = time.time() - start_time
        logger.info(f"파일 전송 완료 (소요 시간: {self.transfer_time:.2f}초)")
        
        self.file_sent.set()


class FileTransferServerProtocol(QuicConnectionProtocol):
    """QUIC server protocol for file transfer"""
    
    def __init__(self, *args, target_dir="received", **kwargs):
        super().__init__(*args, **kwargs)
        self.target_dir = target_dir
        self.stream_data = {}  # stream_id -> accumulated data
        self.stream_metadata = {}  # stream_id -> metadata dict
        self.transfer_start = {}  # stream_id -> start time
    
    def quic_event_received(self, event: QuicEvent):
        """Handle QUIC events"""
        if isinstance(event, StreamDataReceived):
            stream_id = event.stream_id
            
            # Initialize stream data if new
            if stream_id not in self.stream_data:
                self.stream_data[stream_id] = bytearray()
                self.transfer_start[stream_id] = time.time()
                logger.info(f"새 스트림 수신 시작: {stream_id}")
            
            # Accumulate data
            self.stream_data[stream_id].extend(event.data)
            
            # If stream ended, process the file
            if event.end_stream:
                self._process_received_file(stream_id)
    
    def _process_received_file(self, stream_id: int):
        """Process received file data"""
        data = bytes(self.stream_data[stream_id])
        transfer_time = time.time() - self.transfer_start[stream_id]
        
        try:
            # Parse metadata size (first 4 bytes)
            metadata_size = int.from_bytes(data[:4], 'big')
            
            # Parse metadata
            metadata_json = data[4:4+metadata_size].decode('utf-8')
            metadata = json.loads(metadata_json)
            
            filename = metadata['filename']
            expected_size = metadata['file_size']
            
            # Extract file data
            file_data = data[4+metadata_size:]
            
            logger.info(f"파일 수신: {filename} ({len(file_data)} bytes)")
            
            # Sanitize filename
            filename = os.path.basename(filename)
            if not filename or any(c in filename for c in r'\/:*?"<>|'):
                filename = f"received_{int(time.time())}.bin"
            
            # Save file
            file_path = os.path.join(self.target_dir, filename)
            Path(self.target_dir).mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            actual_size = os.path.getsize(file_path)
            transfer_speed = actual_size / transfer_time / 1024 / 1024
            
            logger.info(f"파일 수신 완료: {filename}")
            logger.info(f"크기: {actual_size} bytes, 시간: {transfer_time:.2f}초")
            logger.info(f"전송 속도: {transfer_speed:.2f} MB/s")
            logger.debug(f"{transfer_speed}")
            
            # Cleanup
            del self.stream_data[stream_id]
            del self.transfer_start[stream_id]
            
        except Exception as e:
            logger.error(f"파일 처리 중 오류: {e}")


class QUIC(Protocol):
    """QUIC-based file transfer protocol"""
    
    def __init__(self):
        pass
    
    def send_file(self, filename: str, host: str, port: int = 9999, 
                  buffer_size: int = None, interval: float = 0.0):
        """
        Send a file using QUIC protocol.
        
        Args:
            filename: Path to file to send
            host: Target host
            port: Target port
            buffer_size: Ignored (QUIC handles this automatically)
            interval: Ignored (QUIC handles pacing)
            
        Returns:
            Empty list (for compatibility with other protocols)
        """
        return asyncio.run(self._async_send_file(filename, host, port))
    
    async def _async_send_file(self, filename: str, host: str, port: int):
        """Async implementation of send_file"""
        # Create QUIC configuration
        configuration = QuicConfiguration(
            is_client=True,
            alpn_protocols=["file-transfer"],
        )
        configuration.verify_mode = False  # Disable certificate verification for testing
        
        async with connect(
            host,
            port,
            configuration=configuration,
            create_protocol=FileTransferClientProtocol,
        ) as client:
            # Send file
            await client.send_file(filename)
            
            # Wait for transfer to complete
            await client.file_sent.wait()
            
            # Log transfer speed
            if client.transfer_time > 0 and client.file_size > 0:
                speed = client.file_size / client.transfer_time / 1024 / 1024
                logger.info(f"전송 속도: {speed:.2f} MB/s")
                logger.debug(f"{speed}")
        
        return []
    
    def start_server(self, host: str, port: int, target_dir: str = "received"):
        """
        Start QUIC server to receive files.
        
        Args:
            host: Host to bind to
            port: Port to bind to
            target_dir: Directory to save received files
        """
        asyncio.run(self._async_start_server(host, port, target_dir))
    
    async def _async_start_server(self, host: str, port: int, target_dir: str):
        """Async implementation of start_server"""
        # Create QUIC configuration
        configuration = QuicConfiguration(
            is_client=False,
            alpn_protocols=["file-transfer"],
        )
        
        # Generate self-signed certificate for testing
        # In production, use proper certificates
        try:
            from aioquic.quic.configuration import QuicConfiguration
            import ssl
            
            # Try to load existing certificate
            cert_file = "cert.pem"
            key_file = "key.pem"
            
            if not os.path.exists(cert_file) or not os.path.exists(key_file):
                logger.info("인증서가 없습니다. 자체 서명 인증서를 생성하세요:")
                logger.info("openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes")
                
                # Create dummy cert for testing
                import subprocess
                subprocess.run([
                    "openssl", "req", "-x509", "-newkey", "rsa:2048", 
                    "-keyout", "key.pem", "-out", "cert.pem", 
                    "-days", "365", "-nodes", "-subj", "/CN=localhost"
                ], check=True, capture_output=True)
                logger.info("자체 서명 인증서 생성 완료")
            
            configuration.load_cert_chain(cert_file, key_file)
            
        except Exception as e:
            logger.error(f"인증서 로드/생성 실패: {e}")
            logger.info("기본 설정으로 계속...")
        
        logger.info(f"[QUIC] 서버 시작: {host}:{port}")
        logger.info(f"파일 저장 디렉터리: {target_dir}")
        
        # Create protocol factory
        def create_protocol(*args, **kwargs):
            return FileTransferServerProtocol(*args, target_dir=target_dir, **kwargs)
        
        try:
            await serve(
                host,
                port,
                configuration=configuration,
                create_protocol=create_protocol,
            )
            
            # Keep server running
            await asyncio.Future()  # Run forever
            
        except KeyboardInterrupt:
            logger.info("서버 종료 (KeyboardInterrupt)")
        except Exception as e:
            logger.error(f"서버 오류: {e}")
