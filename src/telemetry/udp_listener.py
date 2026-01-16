"""
UDP Telemetry Listener - INF-100

Receives raw UDP packets from the F1 game on port 20777.

This file must NOT parse packets (INF-103 handles that).
"""

import socket
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class UDPListener:
    DEFAULT_PORT = 20777
    BUFFER_SIZE = 2048  # F1 24 max packet size ~1500 bytes

    def __init__(self, port: int = DEFAULT_PORT, timeout: float = 0.1):
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self._packet_count = 0

        self._setup_socket()

    # ---------------------------------------------------------
    # Setup socket
    # ---------------------------------------------------------
    def _setup_socket(self):
        """Create and bind the UDP socket."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(self.timeout)

            # Bind to ALL interfaces → supports PC, Xbox, PlayStation
            self.socket.bind(("0.0.0.0", self.port))

            logger.info(f"UDPListener started on port {self.port}")

        except socket.error as e:
            logger.error(f"Failed to bind UDP socket: {e}")
            raise

    # ---------------------------------------------------------
    # Receive raw packet
    # ---------------------------------------------------------
    def receive(self) -> Optional[bytes]:
        """Return raw bytes from one UDP packet."""

        if not self.socket:
            logger.error("receive() called before socket setup")
            return None

        try:
            data, _ = self.socket.recvfrom(self.BUFFER_SIZE)
            self._packet_count += 1

            # Log every 100 packets (acceptance criteria)
            if self._packet_count % 100 == 0:
                logger.debug(f"Received {self._packet_count} packets so far")

            return data

        except socket.timeout:
            # Normal occurrence when game pauses or menu is open
            return None

        except socket.error as e:
            logger.error(f"Socket error while receiving: {e}")
            return None

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------
    def close(self):
        if self.socket:
            try:
                self.socket.close()
                logger.info(
                    f"UDPListener closed. Total packets received: {self._packet_count}"
                )
            finally:
                self.socket = None

    # ---------------------------------------------------------
    @property
    def packet_count(self) -> int:
        return self._packet_count


# Standalone testing mode
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    print("Testing UDP Listener...")
    listener = UDPListener()

    try:
        while True:
            data = listener.receive()
            if data:
                print(f"Packet: {len(data)} bytes")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        listener.close()
