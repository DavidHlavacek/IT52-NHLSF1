"""
MOOG UDP Driver - INF-108

NOTE: This skeleton is a STARTING POINT. Feel free to completely rewrite
this file if you have a better approach. Just keep the core responsibility:
send 6-DOF position commands to MOOG platform via UDP.

Ticket: As a developer, I want a Python module that sends 6-DOF commands 
        to the MOOG platform so that I can control platform movement

Assignee: Unassigned (Sprint 3)

This module controls the MOOG 6-DOF Stewart platform via UDP.

Acceptance Criteria:
    ☐ UDP socket created for MOOG communication
    ☐ 6-DOF command packet structure implemented
    ☐ Commands sent at 60Hz rate
    ☐ Feedback packet received and parsed
    ☐ State machine for platform engagement
    ☐ Error handling for connection loss
    ☐ Module documented with docstrings

Dependencies:
    - INF-106: MOOG network settings discovered (IP, port)
    - INF-109: PlatformCommander evaluation completed

Hardware:
    - MOOG 6-DOF platform (parts C12143-004, C37960-002)
    - Connection: Ethernet to ETHER PORT
    - Protocol: UDP, 60Hz bidirectional
    - Home position: (0, 0, -0.18) meters

Packet Format (send):
    6 floats (24 bytes): X, Y, Z, Roll, Pitch, Yaw
    - X, Y, Z in meters
    - Roll, Pitch, Yaw in radians

Usage:
    from src.drivers.moog_driver import MOOGDriver
    
    driver = MOOGDriver(ip='192.168.1.100', port=6000)
    driver.connect()
    driver.engage()
    driver.send_position(x=0, y=0, z=-0.18, roll=0, pitch=0, yaw=0)
"""

import socket
import struct
import logging
import time
from typing import Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PlatformState(Enum):
    """MOOG platform states."""
    UNKNOWN = 0
    POWER_UP = 1
    IDLE = 2
    ENGAGED = 3
    OPERATING = 4
    FAULT = 5


@dataclass
class MOOGConfig:
    """Configuration for MOOG platform connection."""
    ip: str = '192.168.1.100'       # MOOG IP address (discover with INF-106)
    port: int = 6000                 # MOOG UDP port (discover with INF-106)
    send_rate_hz: float = 60.0       # Command send rate
    timeout: float = 1.0             # Socket timeout
    
    # Home position
    home_x: float = 0.0
    home_y: float = 0.0
    home_z: float = -0.18            # -180mm below neutral
    
    # Position limits (meters)
    max_translation: float = 0.25    # ±250mm
    max_rotation: float = 0.35       # ±20 degrees in radians


@dataclass
class Position6DOF:
    """6-DOF position for the MOOG platform."""
    x: float = 0.0      # Surge (forward/back) in meters
    y: float = 0.0      # Sway (left/right) in meters
    z: float = -0.18    # Heave (up/down) in meters
    roll: float = 0.0   # Roll in radians
    pitch: float = 0.0  # Pitch in radians
    yaw: float = 0.0    # Yaw in radians
    
    def to_bytes(self) -> bytes:
        """Pack position into bytes for UDP transmission."""
        return struct.pack('<ffffff', 
            self.x, self.y, self.z, 
            self.roll, self.pitch, self.yaw
        )
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'Position6DOF':
        """Unpack position from received UDP bytes."""
        values = struct.unpack('<ffffff', data[:24])
        return cls(*values)


class MOOGDriver:
    """
    Driver for MOOG 6-DOF Stewart platform via UDP.
    
    The MOOG platform expects UDP packets at 60Hz containing
    6 floats representing the target position in 6 degrees of freedom.
    
    State sequence: PowerUp → Idle → Engaged → Operating
    
    Example:
        driver = MOOGDriver(ip='192.168.1.100', port=6000)
        driver.connect()
        driver.engage()
        driver.send_position(Position6DOF(z=-0.18))
        driver.disengage()
        driver.close()
    """
    
    PACKET_SIZE = 24  # 6 floats * 4 bytes
    
    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the MOOG driver.
        
        Args:
            config: Configuration dict with ip, port, etc.
                   If None, uses defaults from MOOGConfig.
        """
        if config:
            self.config = MOOGConfig(**config)
        else:
            self.config = MOOGConfig()
            
        self.socket: Optional[socket.socket] = None
        self.state = PlatformState.UNKNOWN
        self._connected = False
        self._last_send_time = 0.0
        
    def connect(self) -> bool:
        """
        Create UDP socket for MOOG communication.
        
        TODO [Sprint 3]: Implement this method
        
        Returns:
            True if socket created successfully
            
        Steps:
            1. Create UDP socket (socket.AF_INET, socket.SOCK_DGRAM)
            2. Set socket timeout
            3. Set self._connected = True
            4. Log connection info
        """
        # TODO: Implement connection
        raise NotImplementedError("INF-108: Implement connect()")

    def engage(self) -> bool:
        """
        Engage the platform (transition from Idle to Engaged).
        
        TODO [Sprint 3]: Implement this method
        
        Returns:
            True if engagement successful
            
        Steps:
            1. Send engagement command (platform-specific)
            2. Wait for acknowledgment
            3. Update self.state
            4. Log state change
        """
        # TODO: Implement engagement
        raise NotImplementedError("INF-108: Implement engage()")
    
    def send_position(self, position: Position6DOF) -> bool:
        """
        Send a 6-DOF position command to the platform.
        
        TODO [Sprint 3]: Implement this method
        
        Args:
            position: Target position as Position6DOF object
            
        Returns:
            True if command sent successfully
            
        Steps:
            1. Validate position is within limits
            2. Pack position to bytes using position.to_bytes()
            3. Send via UDP: self.socket.sendto(data, (self.config.ip, self.config.port))
            4. Update self._last_send_time
            5. Log if DEBUG level
            
        Handle exceptions:
            - socket.error: Log error, return False
        """
        # TODO: Implement position command
        raise NotImplementedError("INF-108: Implement send_position()")
    
    def receive_feedback(self) -> Optional[Position6DOF]:
        """
        Receive feedback position from the platform.
        
        TODO [Sprint 3]: Implement this method
        
        Returns:
            Current platform position, or None if no data
            
        Steps:
            1. Call self.socket.recvfrom(PACKET_SIZE)
            2. Parse using Position6DOF.from_bytes()
            3. Return position
            
        Handle exceptions:
            - socket.timeout: Return None
        """
        # TODO: Implement feedback reception
        raise NotImplementedError("INF-108: Implement receive_feedback()")
    
    def go_home(self) -> bool:
        """
        Command platform to home position.
        
        Returns:
            True if command sent successfully
        """
        home = Position6DOF(
            x=self.config.home_x,
            y=self.config.home_y,
            z=self.config.home_z
        )
        return self.send_position(home)
    
    def disengage(self) -> bool:
        """
        Disengage the platform (return to Idle state).
        
        TODO [Sprint 3]: Implement this method
        """
        # TODO: Implement disengagement
        raise NotImplementedError("INF-108: Implement disengage()")
    
    def close(self):
        """
        Close the UDP socket.
        
        TODO [Sprint 3]: Implement this method
        """
        # TODO: Implement cleanup
        raise NotImplementedError("INF-108: Implement close()")
    
    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected


# For standalone testing
if __name__ == "__main__":
    """
    Test the MOOG driver standalone.
    
    Make sure:
        1. MOOG platform is powered on
        2. Ethernet cable connected
        3. IP and port are correct (from INF-106)
        
    Run: python -m src.drivers.moog_driver
    """
    logging.basicConfig(level=logging.DEBUG)
    
    print("MOOG Driver Test")
    print("=" * 40)
    print("NOTE: This requires INF-106 (network discovery) to be completed first")
    print(f"Default config: IP={MOOGConfig.ip}, Port={MOOGConfig.port}")
