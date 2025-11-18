import argparse
import datetime
import time

from protocol import Protocol
from rudp import RUDP
import logger
from tcp import TCP
from udp import UDP

try:
    from quic import QUIC

    QUIC_AVAILABLE = True
except ImportError:
    QUIC_AVAILABLE = False

KB = 1024


def program(
    filename: str,
    host: str = "localhost",
    port: int = 9999,
    _protocol: Protocol = RUDP(),
):
    start_buffer_size_coef = 4
    end_buffer_size_coef = 16

    iterate_num = 50

    start_interval = 0.0001
    end_interval = 0.001
    interval_of_interval = 0.0001

    interval = start_interval

    str_time_now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    log_name = (
        str_time_now
        + "itvl"
        + str(start_interval)
        + "-"
        + str(end_interval)
        + "bfr"
        + str(start_buffer_size_coef)
        + "-"
        + str(end_buffer_size_coef)
    )
    with open(log_name, "w", encoding="utf-8") as file:
        file.write(f"{log_name}\n")
        while interval <= end_interval:
            buffer_size_coef = start_buffer_size_coef
            while buffer_size_coef <= end_buffer_size_coef:
                file.write(
                    f"Buffer Size : {buffer_size_coef}\t Interval : {interval}\n"
                )
                for i in range(iterate_num):
                    losses = _protocol.send_file(
                        filename, host, port, 1024 * buffer_size_coef, interval
                    )
                    time.sleep(5)
                    file.write(f"Iteration : {i + 1}\n")
                    for loss in losses:
                        volume_lossed = len(loss) * buffer_size_coef * 4
                        file.write(f"LOSS : {volume_lossed}\n")
                        file.write(f"{loss}\n")
                    file.write("\n")

                buffer_size_coef *= 2

        interval += interval_of_interval
    file.write("\n")
    end_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file.write(f"end : {end_time}\n")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", type=str, default="./input/file")
    parser.add_argument("-c", "--client", type=bool, default=False)
    parser.add_argument("-t", "--target", type=str, default="localhost")
    parser.add_argument("-p", "--port", type=int, default=9999)
    parser.add_argument("-b", "--buffer_size", type=int, default=1)
    parser.add_argument("-d", "--developer", type=bool, default=False)
    parser.add_argument("-i", "--interval", type=float, default=0.0001)
    parser.add_argument("-l", "--log", type=str, default="")
    parser.add_argument("--protocol", type=str, default="rudp")

    args = parser.parse_args()

    arg_host = args.target
    arg_port = args.port
    arg_is_client = args.client

    arg_is_developer = args.developer
    arg_file_name = args.file
    arg_interval = args.interval
    arg_buffer_size = args.buffer_size
    arg_protocol = args.protocol
    arg_logger = args.log
    protocol = Protocol()

    if arg_logger:
        logger.get_logger().start_file_logging(arg_logger)

    if arg_protocol == "rudp":
        buffer_size = 1460 + (arg_buffer_size - 1) * RUDP.MSS
        protocol = RUDP()
    elif arg_protocol == "tcp":
        buffer_size = arg_buffer_size * TCP.MSS
        protocol = TCP()
    elif arg_protocol == "udp":
        buffer_size = arg_buffer_size * UDP.MSS
        protocol = UDP()
    elif arg_protocol == "quic":
        if not QUIC_AVAILABLE:
            logger.error(
                "QUIC 프로토콜을 사용하려면 aioquic와 cryptography 라이브러리를 설치해야 합니다."
            )
            logger.error("설치 명령어: pip install aioquic cryptography")
            exit(1)
        buffer_size = arg_buffer_size * QUIC.MSS
        protocol = QUIC()
    else:
        raise ValueError(
            "Invalid protocol. Please choose 'rudp', 'tcp', 'udp', or 'quic'."
        )

    if arg_is_developer:
        program(arg_file_name, host=arg_host, port=arg_port)

    if arg_is_client:
        protocol.send_file(
            arg_file_name,
            host=arg_host,
            port=arg_port,
            buffer_size=buffer_size,
            interval=arg_interval,
        )

    else:
        protocol.start_server(host=arg_host, port=arg_port, log_filename=arg_logger)
