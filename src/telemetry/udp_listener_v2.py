"""
UDP Listener v2.0 - Optimized for low latency
"""

"""
use receive() instead of recvfrom() to avoid buffer accumulation!
get the latest packet, not old queued ones!
"""

import socket
import select


class UDPListenerV2:
    def __init__(self, port: int = 20777, timeout: float = 0.1):
        self.port = port
        self.timeout = timeout
        self.socket = None
        self._setup_socket()

    def _setup_socket(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setblocking(False)  # non-blocking
        self.socket.bind(('0.0.0.0', self.port))
        print(f"[UDP] Listening on port {self.port}")

    def receive(self) -> bytes:
        readable = select.select([self.socket], [], [], self.timeout)[0]

        if not readable:
            return None

        try:
            data = self.socket.recvfrom(2048)[0]
            return data
        except BlockingIOError:
            return None

    def close(self):
        if self.socket:
            self.socket.close()
            print("[UDP] Closed")
