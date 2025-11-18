BUFFER_SIZE = 1024 * 1024 * 1024


class Protocol:

    def send_file(
        self, filename: str, host: str, port: int, buffer_size: int, interval: float
    ): ...

    def start_server(
        self, host: str, port: int, target_dir: str, log_filename: str = None
    ): ...
