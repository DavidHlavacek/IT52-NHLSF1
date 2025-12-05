"""
UDP Telemetry Listener - INF-100

NOTE: This skeleton is a STARTING POINT. Feel free to completely rewrite
this file if you have a better approach. Just keep the core responsibility:
receive UDP packets from F1 game on port 20777.

Ticket: As a developer, I want a Python script that receives F1 UDP packets 
        so that I can access the raw telemetry data

Assignee: [TEAMMATE]

This module receives raw UDP packets from the F1 game on port 20777.

Acceptance Criteria:
    ☐ Script binds to UDP port 20777
    ☐ Script receives packets without errors
    ☐ Packet size and frequency logged
    ☐ Script handles network errors gracefully
    ☐ Script can run continuously without memory leaks

Dependencies:
    - INF-97: F1 game must have UDP telemetry enabled

Usage:
    from src.telemetry.udp_listener import UDPListener
    
    listener = UDPListener(port=20777)
    raw_data = listener.receive()
"""

import socket
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class UDPListener:
    """
    Listens for F1 telemetry UDP packets.
    
    The F1 game broadcasts telemetry on UDP port 20777 at up to 60Hz.
    Packet sizes vary by type (motion packets are typically ~1300 bytes).
    
    Example:
        listener = UDPListener(port=20777)
        while True:
            data = listener.receive()
            if data:
                process(data)
    """
    
    # F1 game default settings
    DEFAULT_PORT = 20777
    BUFFER_SIZE = 2048  # Max packet size from F1 game
    
    def __init__(self, port: int = DEFAULT_PORT, timeout: float = 1.0):
        """
        Initialize the UDP listener.
        
        Args:
            port: UDP port to listen on (default: 20777)
            timeout: Socket timeout in seconds (default: 1.0)
        """
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self._packet_count = 0
        
        self._setup_socket()
    
    def _setup_socket(self):
        """
        Create and bind the UDP socket.
        
        TODO [TEAMMATE]: Implement this method
        
        Steps:
            1. Create UDP socket (socket.AF_INET, socket.SOCK_DGRAM)
            2. Set socket timeout
            3. Bind to ('0.0.0.0', self.port)
            4. Log success message
            
        Handle exceptions:
            - socket.error: Log error and re-raise
        """
        # TODO: Implement socket setup
        raise NotImplementedError("INF-100: Implement _setup_socket()")
    
    def receive(self) -> Optional[bytes]:
        """
        Receive a single UDP packet.
        
        TODO [TEAMMATE]: Implement this method
        
        Returns:
            bytes: Raw packet data, or None if timeout/error
            
        Steps:
            1. Call self.socket.recvfrom(BUFFER_SIZE)
            2. Increment self._packet_count
            3. Log packet size periodically (every 100 packets)
            4. Return the data (not the address)
            
        Handle exceptions:
            - socket.timeout: Return None (this is normal)
            - socket.error: Log error, return None
        """
        # TODO: Implement packet reception
        raise NotImplementedError("INF-100: Implement receive()")
    
    def close(self):
        """
        Close the UDP socket.
        
        TODO [TEAMMATE]: Implement this method
        
        Steps:
            1. Check if socket exists
            2. Close the socket
            3. Log total packets received
        """
        # TODO: Implement socket cleanup
        raise NotImplementedError("INF-100: Implement close()")
    
    @property
    def packet_count(self) -> int:
        """Return total number of packets received."""
        return self._packet_count


# For standalone testing
if __name__ == "__main__":
    """
    Test the UDP listener standalone.
    
    Run this while F1 game is sending telemetry:
        python -m src.telemetry.udp_listener
    """
    logging.basicConfig(level=logging.DEBUG)
    
    print("Starting UDP Listener test...")
    print("Make sure F1 game is running with UDP telemetry enabled on port 20777")
    print("Press Ctrl+C to stop\n")
    
    listener = UDPListener()
    
    try:
        while True:
            data = listener.receive()
            if data:
                print(f"Received packet: {len(data)} bytes")
    except KeyboardInterrupt:
        print(f"\nStopped. Total packets received: {listener.packet_count}")
    finally:
        listener.close()
