"""
F1 2024 Packet Parser - Complete Implementation

Parses raw F1 2024 UDP packets and extracts telemetry data.

F1 2024 Packet Format:
    - Header: 29 bytes (includes gameYear field added in 2023)
    - Motion packet (ID=0): 1349 bytes total
    - CarMotionData: 60 bytes per car × 22 cars

Research Notes:
    - All values are little-endian
    - All data is packed (no padding)
    - Normalised int16 vectors: divide by 32767.0 to get float
    - G-forces are in G's (typically -6 to +6)
    - Orientation angles are in radians

Implementation optimizations:
    - struct module for efficient binary unpacking
    - Pre-compiled struct formats
    - Minimal allocations in hot path
"""

import struct
import logging
from dataclasses import dataclass
from typing import Optional
from enum import IntEnum

logger = logging.getLogger(__name__)


class PacketId(IntEnum):
    """F1 2024 packet type identifiers."""
    MOTION = 0
    SESSION = 1
    LAP_DATA = 2
    EVENT = 3
    PARTICIPANTS = 4
    CAR_SETUPS = 5
    CAR_TELEMETRY = 6
    CAR_STATUS = 7
    FINAL_CLASSIFICATION = 8
    LOBBY_INFO = 9
    CAR_DAMAGE = 10
    SESSION_HISTORY = 11
    TYRE_SETS = 12
    MOTION_EX = 13


@dataclass
class PacketHeader:
    """
    F1 2024 packet header (29 bytes).

    Contains metadata about the packet including format version,
    packet type, session info, and player car index.
    """
    packet_format: int      # 2024
    game_year: int          # 24
    game_major_version: int
    game_minor_version: int
    packet_version: int
    packet_id: int          # PacketId enum
    session_uid: int
    session_time: float
    frame_identifier: int
    overall_frame_identifier: int
    player_car_index: int
    secondary_player_car_index: int


@dataclass
class TelemetryData:
    """
    Parsed telemetry data from F1 motion packet.

    Contains the physics data needed for the motion algorithm.
    This is the primary output of the packet parser.
    """
    # G-Forces (in G's, typically -6 to +6)
    g_force_lateral: float      # Positive = right turn
    g_force_longitudinal: float # Positive = acceleration, negative = braking
    g_force_vertical: float     # Typically ~1.0 (gravity) + bumps

    # Orientation (in radians)
    yaw: float    # Rotation around vertical axis
    pitch: float  # Nose up/down
    roll: float   # Lean left/right

    # World position (meters) - useful for debugging
    world_position_x: float = 0.0
    world_position_y: float = 0.0
    world_position_z: float = 0.0

    # Velocities (m/s) - useful for motion prediction
    world_velocity_x: float = 0.0
    world_velocity_y: float = 0.0
    world_velocity_z: float = 0.0

    # Frame info for timing analysis
    frame_identifier: int = 0
    session_time: float = 0.0

    def __str__(self):
        return (
            f"TelemetryData(g_lat={self.g_force_lateral:+.2f}, "
            f"g_long={self.g_force_longitudinal:+.2f}, "
            f"g_vert={self.g_force_vertical:.2f}, "
            f"yaw={self.yaw:.2f}, pitch={self.pitch:.2f}, roll={self.roll:.2f})"
        )


class PacketParser:
    """
    Parses F1 2024 UDP telemetry packets.

    Optimized for minimal latency using pre-compiled struct formats.
    Extracts motion data for the player's car and returns TelemetryData.

    F1 2024 Header Structure (29 bytes):
        uint16  packetFormat         - 2024
        uint8   gameYear             - 24 (last two digits)
        uint8   gameMajorVersion
        uint8   gameMinorVersion
        uint8   packetVersion
        uint8   packetId             - 0 for motion packet
        uint64  sessionUID
        float   sessionTime
        uint32  frameIdentifier
        uint32  overallFrameIdentifier
        uint8   playerCarIndex
        uint8   secondaryPlayerCarIndex

    CarMotionData Structure (60 bytes per car):
        float   worldPositionX/Y/Z   - 12 bytes
        float   worldVelocityX/Y/Z   - 12 bytes
        int16   worldForwardDirX/Y/Z - 6 bytes (normalised, /32767)
        int16   worldRightDirX/Y/Z   - 6 bytes (normalised, /32767)
        float   gForceLateral        - 4 bytes
        float   gForceLongitudinal   - 4 bytes
        float   gForceVertical       - 4 bytes
        float   yaw                  - 4 bytes
        float   pitch                - 4 bytes
        float   roll                 - 4 bytes

    Example:
        parser = PacketParser()
        data = parser.parse_motion_packet(raw_bytes)
        if data:
            print(f"G-Force: {data.g_force_lateral}")
    """

    # F1 2024 packet format version
    EXPECTED_PACKET_FORMAT = 2024

    # Struct formats (little-endian, packed)
    # Header: uint16 + uint8*5 + uint64 + float + uint32*2 + uint8*2 = 29 bytes
    HEADER_FORMAT = '<HBBBBBQLIBB'
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 29 bytes

    # CarMotionData: 6 floats + 6 int16 + 6 floats = 60 bytes
    # Position(3f) + Velocity(3f) + ForwardDir(3h) + RightDir(3h) + GForces(3f) + Angles(3f)
    MOTION_DATA_FORMAT = '<ffffffhhhhhhffffff'
    MOTION_DATA_SIZE = struct.calcsize(MOTION_DATA_FORMAT)  # 60 bytes

    # Expected motion packet size: header + 22 cars
    MOTION_PACKET_SIZE = HEADER_SIZE + (22 * MOTION_DATA_SIZE)  # 1349 bytes

    # Validation ranges
    G_FORCE_MIN = -10.0
    G_FORCE_MAX = 10.0

    # Pre-compile struct objects for performance
    _header_struct = struct.Struct(HEADER_FORMAT)
    _motion_struct = struct.Struct(MOTION_DATA_FORMAT)

    def __init__(self):
        """Initialize the packet parser."""
        self._packets_parsed = 0
        self._motion_packets_parsed = 0
        self._invalid_packets = 0
        self._last_frame_id = 0

    def parse_header(self, data: bytes) -> Optional[PacketHeader]:
        """
        Parse the F1 2024 packet header (29 bytes).

        Args:
            data: Raw packet bytes (at least 29 bytes)

        Returns:
            PacketHeader object, or None if invalid
        """
        if len(data) < self.HEADER_SIZE:
            logger.warning(f"Packet too small for header: {len(data)} < {self.HEADER_SIZE}")
            return None

        try:
            unpacked = self._header_struct.unpack_from(data, 0)

            header = PacketHeader(
                packet_format=unpacked[0],
                game_year=unpacked[1],
                game_major_version=unpacked[2],
                game_minor_version=unpacked[3],
                packet_version=unpacked[4],
                packet_id=unpacked[5],
                session_uid=unpacked[6],
                session_time=unpacked[7],
                frame_identifier=unpacked[8],
                overall_frame_identifier=unpacked[9],
                player_car_index=unpacked[10],
                secondary_player_car_index=unpacked[11]
            )

            # Validate packet format
            if header.packet_format != self.EXPECTED_PACKET_FORMAT:
                # Log only occasionally to avoid spam
                if self._packets_parsed % 1000 == 0:
                    logger.debug(f"Packet format {header.packet_format}, expected {self.EXPECTED_PACKET_FORMAT}")

            return header

        except struct.error as e:
            logger.error(f"Failed to unpack header: {e}")
            self._invalid_packets += 1
            return None

    def parse_motion_packet(self, data: bytes) -> Optional[TelemetryData]:
        """
        Parse a motion packet and extract player car telemetry.

        This is the primary method for the motion simulator pipeline.
        It parses the header, validates the packet type, extracts the
        player car's motion data, and returns a TelemetryData object.

        Args:
            data: Raw UDP packet bytes

        Returns:
            TelemetryData object, or None if not a valid motion packet

        Performance:
            - Uses pre-compiled struct formats
            - Minimal allocations
            - Direct buffer access (no copying)
        """
        self._packets_parsed += 1

        # Parse header
        header = self.parse_header(data)
        if header is None:
            return None

        # Check if this is a motion packet
        if header.packet_id != PacketId.MOTION:
            return None

        # Validate packet size
        if len(data) < self.MOTION_PACKET_SIZE:
            logger.warning(
                f"Motion packet too small: {len(data)} < {self.MOTION_PACKET_SIZE}"
            )
            self._invalid_packets += 1
            return None

        # Validate player car index
        if header.player_car_index >= 22:
            logger.warning(f"Invalid player car index: {header.player_car_index}")
            self._invalid_packets += 1
            return None

        try:
            # Calculate offset for player car's motion data
            offset = self.HEADER_SIZE + (header.player_car_index * self.MOTION_DATA_SIZE)

            # Unpack motion data
            motion = self._motion_struct.unpack_from(data, offset)

            # Extract fields
            # Position: motion[0:3]
            # Velocity: motion[3:6]
            # ForwardDir: motion[6:9] (int16, normalised)
            # RightDir: motion[9:12] (int16, normalised)
            # G-Forces: motion[12:15]
            # Angles: motion[15:18]

            telemetry = TelemetryData(
                # G-Forces (indices 12, 13, 14)
                g_force_lateral=motion[12],
                g_force_longitudinal=motion[13],
                g_force_vertical=motion[14],

                # Orientation (indices 15, 16, 17)
                yaw=motion[15],
                pitch=motion[16],
                roll=motion[17],

                # Position (indices 0, 1, 2)
                world_position_x=motion[0],
                world_position_y=motion[1],
                world_position_z=motion[2],

                # Velocity (indices 3, 4, 5)
                world_velocity_x=motion[3],
                world_velocity_y=motion[4],
                world_velocity_z=motion[5],

                # Timing info
                frame_identifier=header.frame_identifier,
                session_time=header.session_time
            )

            # Validate telemetry data
            if not self._validate_telemetry(telemetry):
                self._invalid_packets += 1
                return None

            self._motion_packets_parsed += 1
            self._last_frame_id = header.frame_identifier

            return telemetry

        except struct.error as e:
            logger.error(f"Failed to unpack motion data: {e}")
            self._invalid_packets += 1
            return None

        except IndexError as e:
            logger.error(f"Index error unpacking motion data: {e}")
            self._invalid_packets += 1
            return None

    def _validate_telemetry(self, telemetry: TelemetryData) -> bool:
        """
        Validate telemetry values are within expected ranges.

        Args:
            telemetry: TelemetryData to validate

        Returns:
            True if valid, False otherwise

        Note:
            Invalid data usually indicates parsing errors or corrupt packets.
            Extreme but valid G-forces (e.g., crashes) should still pass.
        """
        # Check G-forces are within physical limits
        g_forces = [
            telemetry.g_force_lateral,
            telemetry.g_force_longitudinal,
            telemetry.g_force_vertical
        ]

        for g in g_forces:
            if not (self.G_FORCE_MIN <= g <= self.G_FORCE_MAX):
                logger.warning(f"G-force out of range: {g}")
                return False

            # Check for NaN
            if g != g:  # NaN check
                logger.warning("G-force is NaN")
                return False

        # Check angles are reasonable (not NaN)
        for angle in [telemetry.yaw, telemetry.pitch, telemetry.roll]:
            if angle != angle:  # NaN check
                logger.warning("Angle is NaN")
                return False

        return True

    @property
    def stats(self) -> dict:
        """Return parsing statistics."""
        return {
            "packets_parsed": self._packets_parsed,
            "motion_packets_parsed": self._motion_packets_parsed,
            "invalid_packets": self._invalid_packets,
            "last_frame_id": self._last_frame_id
        }


# For standalone testing
if __name__ == "__main__":
    """
    Test the packet parser.

    Run: python -m src.telemetry.packet_parser
    """
    logging.basicConfig(level=logging.DEBUG)

    print("Packet Parser Test")
    print("=" * 50)

    parser = PacketParser()

    print(f"Header size: {PacketParser.HEADER_SIZE} bytes")
    print(f"Motion data per car: {PacketParser.MOTION_DATA_SIZE} bytes")
    print(f"Expected motion packet size: {PacketParser.MOTION_PACKET_SIZE} bytes")

    # Integration test with UDP listener
    print("\nAttempting live test with UDP listener...")

    try:
        from src.telemetry.udp_listener import UDPListener

        listener = UDPListener()
        print("Waiting for F1 telemetry packets...")
        print("Press Ctrl+C to stop\n")

        motion_count = 0
        other_count = 0

        while motion_count < 10:
            data = listener.receive()
            if data:
                telemetry = parser.parse_motion_packet(data)
                if telemetry:
                    motion_count += 1
                    print(f"Motion {motion_count}: {telemetry}")
                else:
                    other_count += 1

        print(f"\nReceived {motion_count} motion packets, {other_count} other packets")
        print(f"Parser stats: {parser.stats}")
        listener.close()

    except KeyboardInterrupt:
        print("\nStopped by user")
    except ImportError:
        print("UDP listener not available for integration test")
    except Exception as e:
        print(f"Test error: {e}")
