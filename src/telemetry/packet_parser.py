"""
F1 Packet Parser - INF-103

NOTE: This skeleton is a STARTING POINT. Feel free to completely rewrite
this file if you have a better approach. Just keep the core responsibility:
parse F1 UDP packets and extract G-forces + orientation.

Ticket: As a developer, I want to parse the F1 motion packet so that I can 
        extract G-force and orientation data

Assignee: David

This module parses raw F1 UDP packets and extracts telemetry data.

Acceptance Criteria:
    ☐ Packet header parsed correctly (24 bytes)
    ☐ Motion packet identified (packetId = 0)
    ☐ Player car data extracted using playerCarIndex
    ☐ gForceLateral, gForceLongitudinal, gForceVertical extracted
    ☐ yaw, pitch, roll extracted
    ☐ Values validated against expected ranges
    ☐ Unit tests written for parser

Dependencies:
    - INF-100: UDP Listener must provide raw packets

F1 2023 Packet Structure:
    Header (24 bytes):
        - packetFormat (uint16): 2023
        - gameMajorVersion (uint8)
        - gameMinorVersion (uint8)
        - packetVersion (uint8)
        - packetId (uint8): 0 = Motion
        - sessionUID (uint64)
        - sessionTime (float)
        - frameIdentifier (uint32)
        - playerCarIndex (uint8)
        - secondaryPlayerCarIndex (uint8)
        
    Motion Data (per car, 60 bytes):
        - worldPositionX, Y, Z (float)
        - worldVelocityX, Y, Z (float)
        - worldForwardDirX, Y, Z (int16, normalized)
        - worldRightDirX, Y, Z (int16, normalized)
        - gForceLateral (float)
        - gForceLongitudinal (float)
        - gForceVertical (float)
        - yaw (float)
        - pitch (float)
        - roll (float)

Usage:
    from src.telemetry.packet_parser import PacketParser, TelemetryData
    
    parser = PacketParser()
    telemetry = parser.parse_motion_packet(raw_data)
    print(telemetry.g_force_lateral)
"""

import struct
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TelemetryData:
    """
    Parsed telemetry data from F1 motion packet.
    
    Contains the physics data needed for the motion algorithm.
    """
    # G-Forces (in G's, typically -3 to +3)
    g_force_lateral: float      # Left/right (negative = left, positive = right)
    g_force_longitudinal: float # Forward/back (negative = braking, positive = acceleration)
    g_force_vertical: float     # Up/down (typically around 1.0 due to gravity)
    
    # Orientation (in radians)
    yaw: float    # Rotation around vertical axis
    pitch: float  # Nose up/down
    roll: float   # Lean left/right
    
    # Optional: suspension data for enhanced motion
    suspension_position: Optional[list] = None  # [RL, RR, FL, FR] in mm
    
    def __str__(self):
        return (
            f"TelemetryData(g_lat={self.g_force_lateral:.2f}, "
            f"g_long={self.g_force_longitudinal:.2f}, "
            f"g_vert={self.g_force_vertical:.2f}, "
            f"yaw={self.yaw:.2f}, pitch={self.pitch:.2f}, roll={self.roll:.2f})"
        )


class PacketParser:
    """
    Parses F1 UDP telemetry packets.
    
    Supports F1 2023 packet format. The parser extracts motion data
    for the player's car and returns a TelemetryData object.
    
    Example:
        parser = PacketParser()
        data = parser.parse_motion_packet(raw_bytes)
        if data:
            print(f"G-Force: {data.g_force_lateral}")
    """
    
    # Packet type IDs
    PACKET_ID_MOTION = 0
    PACKET_ID_SESSION = 1
    PACKET_ID_LAP_DATA = 2
    # ... other packet types not needed for motion
    
    # Struct formats (little-endian)
    HEADER_FORMAT = '<HBBBBQfIBB'  # 24 bytes
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
    
    # Motion data per car
    MOTION_DATA_FORMAT = '<ffffffhhhhhhffffff'  # 60 bytes per car
    MOTION_DATA_SIZE = struct.calcsize(MOTION_DATA_FORMAT)
    
    # Valid ranges for data validation
    G_FORCE_MIN = -6.0
    G_FORCE_MAX = 6.0
    
    def __init__(self):
        """Initialize the packet parser."""
        self._packets_parsed = 0
        self._invalid_packets = 0
    
    def parse_header(self, data: bytes) -> Optional[dict]:
        """
        Parse the packet header.
        
        TODO [David]: Implement this method
        
        Args:
            data: Raw packet bytes (at least 24 bytes)
            
        Returns:
            dict with header fields, or None if invalid
            
        Steps:
            1. Check data length >= HEADER_SIZE
            2. Unpack using HEADER_FORMAT
            3. Return dict with keys:
               - packet_format, game_major_version, game_minor_version
               - packet_version, packet_id, session_uid
               - session_time, frame_identifier
               - player_car_index, secondary_player_car_index
        """
        # TODO: Implement header parsing
        raise NotImplementedError("INF-103: Implement parse_header()")
    
    def parse_motion_packet(self, data: bytes) -> Optional[TelemetryData]:
        """
        Parse a motion packet and extract player car telemetry.
        
        TODO [David]: Implement this method
        
        Args:
            data: Raw UDP packet bytes
            
        Returns:
            TelemetryData object, or None if not a motion packet
            
        Steps:
            1. Parse header using parse_header()
            2. Check if packet_id == PACKET_ID_MOTION, return None if not
            3. Calculate offset for player car: 
               HEADER_SIZE + (player_car_index * MOTION_DATA_SIZE)
            4. Unpack motion data using MOTION_DATA_FORMAT
            5. Extract g-forces and orientation
            6. Validate values using _validate_telemetry()
            7. Return TelemetryData object
            
        Handle exceptions:
            - struct.error: Log error, return None
            - IndexError: Log error, return None
        """
        # TODO: Implement motion packet parsing
        raise NotImplementedError("INF-103: Implement parse_motion_packet()")
    
    def _validate_telemetry(self, telemetry: TelemetryData) -> bool:
        """
        Validate telemetry values are within expected ranges.
        
        TODO [David]: Implement this method
        
        Args:
            telemetry: TelemetryData to validate
            
        Returns:
            True if valid, False otherwise
            
        Checks:
            - G-forces within G_FORCE_MIN to G_FORCE_MAX
            - Log warning if values seem unusual
        """
        # TODO: Implement validation
        raise NotImplementedError("INF-103: Implement _validate_telemetry()")
    
    @property
    def stats(self) -> dict:
        """Return parsing statistics."""
        return {
            "packets_parsed": self._packets_parsed,
            "invalid_packets": self._invalid_packets
        }


# For standalone testing
if __name__ == "__main__":
    """
    Test the packet parser with sample data.
    
    Run: python -m src.telemetry.packet_parser
    """
    logging.basicConfig(level=logging.DEBUG)
    
    # Create a mock motion packet for testing
    # In real usage, this comes from UDPListener
    print("Packet Parser test")
    print("=" * 40)
    
    parser = PacketParser()
    
    # TODO: Add test with real or mock packet data
    print("Parser initialized successfully")
    print(f"Header size: {PacketParser.HEADER_SIZE} bytes")
    print(f"Motion data size per car: {PacketParser.MOTION_DATA_SIZE} bytes")
