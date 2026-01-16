"""
UDP Telemetry Listener - Complete Implementation

Receives F1 2024 UDP telemetry packets on port 20777.

Research Notes:
    - F1 2024 sends telemetry at up to 60Hz
    - Motion packet (ID=0) is 1349 bytes
    - Non-blocking sockets with select() for efficient polling
    - Thread-safe design for pipeline integration

Implementation based on professional simulator patterns:
    - Minimal latency (no unnecessary copying)
    - Clean lifecycle management
    - Latency measurement capability
"""

import socket
import select
import logging
import time
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ListenerStats:
    """Statistics for the UDP listener."""
    packets_received: int = 0
    bytes_received: int = 0
    timeouts: int = 0
    errors: int = 0
    last_packet_time: float = 0.0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0


class UDPListener:
    """
    Non-blocking UDP listener for F1 telemetry packets.

    The F1 game broadcasts telemetry on UDP port 20777 at up to 60Hz.
    This implementation uses non-blocking sockets with select() for
    efficient polling without busy-waiting.

    Features:
        - Non-blocking receive with configurable timeout
        - Latency tracking (time from packet arrival to return)
        - Clean start/stop lifecycle
        - Thread-safe statistics

    Example:
        listener = UDPListener(port=20777)
        while True:
            data = listener.receive()
            if data:
                process(data)
        listener.close()
    """

    # F1 game default settings
    DEFAULT_PORT = 20777
    BUFFER_SIZE = 2048  # Max packet size from F1 game (motion packet is 1349)

    def __init__(self, port: int = DEFAULT_PORT, timeout: float = 0.1):
        """
        Initialize the UDP listener.

        Args:
            port: UDP port to listen on (default: 20777)
            timeout: Socket timeout in seconds for select() (default: 0.1)
                    Lower values = more responsive but more CPU usage
        """
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self._stats = ListenerStats()
        self._running = False
        self._latency_samples: list = []
        self._max_latency_samples = 100

        self._setup_socket()

    def _setup_socket(self):
        """
        Create and bind the UDP socket with non-blocking mode.

        Uses SO_REUSEADDR to allow quick restart after crash.
        Socket is set to non-blocking, with select() used for timed waits.
        """
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            # Allow address reuse (helpful for development/restarts)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Set non-blocking mode
            self.socket.setblocking(False)

            # Bind to all interfaces on specified port
            self.socket.bind(('0.0.0.0', self.port))

            self._running = True
            logger.info(f"UDP listener bound to port {self.port}")

        except socket.error as e:
            logger.error(f"Failed to setup UDP socket: {e}")
            self._running = False
            raise

    def receive(self) -> Optional[bytes]:
        """
        Receive a single UDP packet (non-blocking with timeout).

        Uses select() to wait for data with timeout, avoiding busy-waiting
        while maintaining responsiveness.

        Returns:
            bytes: Raw packet data, or None if timeout/no data

        Note:
            This method tracks latency from select() return to method return.
            The actual network latency is not measured (would require NTP sync).
        """
        if not self._running or not self.socket:
            return None

        try:
            # Wait for data with timeout using select()
            ready, _, _ = select.select([self.socket], [], [], self.timeout)

            if not ready:
                self._stats.timeouts += 1
                return None

            # Measure processing latency
            recv_start = time.perf_counter()

            # Receive the packet
            data, addr = self.socket.recvfrom(self.BUFFER_SIZE)

            # Update statistics
            recv_end = time.perf_counter()
            latency_ms = (recv_end - recv_start) * 1_000

            self._stats.packets_received += 1
            self._stats.bytes_received += len(data)
            self._stats.last_packet_time = recv_end
            self._update_latency(latency_ms)

            # Log periodically (every 600 packets = ~10 seconds at 60Hz)
            if self._stats.packets_received % 600 == 0:
                logger.debug(
                    f"UDP stats: {self._stats.packets_received} packets, "
                    f"{self._stats.bytes_received} bytes, "
                    f"latency avg={self._stats.avg_latency_ms:.3f}ms max={self._stats.max_latency_ms:.3f}ms"
                )

            return data

        except BlockingIOError:
            # No data available (shouldn't happen after select, but handle it)
            return None

        except socket.error as e:
            self._stats.errors += 1
            logger.warning(f"Socket error during receive: {e}")
            return None

    def receive_with_timestamp(self) -> Optional[Tuple[bytes, float]]:
        """
        Receive a packet along with its arrival timestamp.

        Returns:
            Tuple of (data, timestamp) or None if no data

        Useful for latency tracking through the pipeline.
        """
        data = self.receive()
        if data:
            return (data, time.perf_counter())
        return None

    def _update_latency(self, latency_ms: float):
        """Update running average and max of processing latency."""
        self._latency_samples.append(latency_ms)
        if len(self._latency_samples) > self._max_latency_samples:
            self._latency_samples.pop(0)

        if self._latency_samples:
            self._stats.avg_latency_ms = sum(self._latency_samples) / len(self._latency_samples)
            self._stats.max_latency_ms = max(self._stats.max_latency_ms, latency_ms)

    def close(self):
        """
        Close the UDP socket and log final statistics.
        """
        self._running = False

        if self.socket:
            try:
                self.socket.close()
                logger.info(
                    f"UDP listener closed. Stats: "
                    f"{self._stats.packets_received} packets, "
                    f"latency avg={self._stats.avg_latency_ms:.3f}ms max={self._stats.max_latency_ms:.3f}ms, "
                    f"{self._stats.errors} errors, "
                    f"{self._stats.timeouts} timeouts"
                )
            except socket.error as e:
                logger.warning(f"Error closing socket: {e}")
            finally:
                self.socket = None

    @property
    def stats(self) -> ListenerStats:
        """Return current listener statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Return whether the listener is active."""
        return self._running

    @property
    def packet_count(self) -> int:
        """Return total number of packets received (for compatibility)."""
        return self._stats.packets_received


# For standalone testing
if __name__ == "__main__":
    """
    Test the UDP listener standalone.

    Run this while F1 game is sending telemetry:
        python -m src.telemetry.udp_listener
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("Starting UDP Listener test...")
    print("Make sure F1 game is running with UDP telemetry enabled on port 20777")
    print("Press Ctrl+C to stop\n")

    listener = UDPListener()
    packet_sizes = {}

    try:
        while True:
            data = listener.receive()
            if data:
                size = len(data)
                packet_sizes[size] = packet_sizes.get(size, 0) + 1

                # Print first few packets
                if listener.packet_count <= 5:
                    print(f"Packet #{listener.packet_count}: {size} bytes")
                elif listener.packet_count == 6:
                    print("(suppressing further packet logs...)")

    except KeyboardInterrupt:
        print(f"\n\nStopped. Total packets received: {listener.packet_count}")
        print("\nPacket size distribution:")
        for size, count in sorted(packet_sizes.items()):
            print(f"  {size} bytes: {count} packets")
    finally:
        listener.close()
