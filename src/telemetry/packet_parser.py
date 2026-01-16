"""
F1 Packet Parser - INF-103

Parses F1 24 UDP packets and extracts G-forces + orientation for the motion algorithm.

See F1_24_PACKET_FORMAT.md for full protocol documentation.
"""

import struct
import logging
from dataclasses import dataclass
from typing import Optional

from src import DEBUG

logger = logging.getLogger(__name__)

@dataclass
class TelemetryData:
    """
    Parsed telemetry data from F1 motion packet.

    G-Forces (in G's):
        lateral:      + right turn, - left turn
        longitudinal: + accelerating, - braking
        vertical:     ~1.0 at rest, >1.0 compression, <1.0 airborne

    Orientation (in radians):
        yaw:   heading direction (rotation around vertical axis)
        pitch: nose up (+) / down (-)
        roll:  lean right (+) / left (-)
    """

    g_force_lateral: float
    g_force_longitudinal: float
    g_force_vertical: float
    yaw: float
    pitch: float
    roll: float

    def __str__(self):
        return (
            f"TelemetryData("
            f"g=[{self.g_force_lateral:+.2f}, {self.g_force_longitudinal:+.2f}, {self.g_force_vertical:+.2f}], "
            f"rot=[{self.yaw:.2f}, {self.pitch:.2f}, {self.roll:.2f}])"
        )


class PacketParser:
    """
    Parses F1 24 UDP telemetry packets.

    Only extracts Motion packets (type 0) - other packet types are ignored.
    """

    # Packet type
    PACKET_ID_MOTION = 0

    # F1 24 Header: 29 bytes
    # <hBBBBBQfIIBB = int16, 6×uint8, uint64, float, 2×uint32, 2×uint8
    HEADER_FORMAT = '<hBBBBBQfIIBB'
    HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 29

    # Motion data per car: 60 bytes
    # 6 floats + 6 int16 + 6 floats
    MOTION_DATA_FORMAT = '<ffffffhhhhhhffffff'
    MOTION_DATA_SIZE = struct.calcsize(MOTION_DATA_FORMAT)  # 60

    # Warning threshold (normal racing is ±5G, crashes can exceed)
    G_FORCE_WARN_THRESHOLD = 10.0

    # Number of cars in packet
    MAX_CARS = 22

    def __init__(self):
        self._packets_parsed = 0
        self._invalid_packets = 0

    def parse_header(self, data: bytes) -> Optional[dict]:
        """
        Parse packet header (29 bytes for F1 24).

        Returns dict with header fields, or None if invalid.
        """
        if len(data) < self.HEADER_SIZE:
            return None

        try:
            fields = struct.unpack(self.HEADER_FORMAT, data[:self.HEADER_SIZE])
            return {
                'packet_format': fields[0],
                'game_year': fields[1],
                'game_major_version': fields[2],
                'game_minor_version': fields[3],
                'packet_version': fields[4],
                'packet_id': fields[5],
                'session_uid': fields[6],
                'session_time': fields[7],
                'frame_identifier': fields[8],
                'overall_frame_identifier': fields[9],
                'player_car_index': fields[10],
                'secondary_player_car_index': fields[11],
            }
        except struct.error:
            return None

    def parse_motion_packet(self, data: bytes) -> Optional[TelemetryData]:
        """
        Parse motion packet and extract player car telemetry.

        Returns TelemetryData or None if not a motion packet.
        """
        header = self.parse_header(data)
        if header is None:
            self._invalid_packets += 1
            return None

        # Only process Motion packets
        if header['packet_id'] != self.PACKET_ID_MOTION:
            return None

        player_index = header['player_car_index']
        if player_index >= self.MAX_CARS:
            logger.warning(f"Invalid player_car_index: {player_index}")
            self._invalid_packets += 1
            return None

        # Calculate offset to player's car data
        motion_offset = self.HEADER_SIZE + (player_index * self.MOTION_DATA_SIZE)
        motion_end = motion_offset + self.MOTION_DATA_SIZE

        if len(data) < motion_end:
            logger.warning(f"Packet too short: {len(data)} < {motion_end}")
            self._invalid_packets += 1
            return None

        try:
            motion = struct.unpack(
                self.MOTION_DATA_FORMAT,
                data[motion_offset:motion_end]
            )
        except struct.error as e:
            logger.warning(f"Failed to unpack motion data: {e}")
            self._invalid_packets += 1
            return None

        # Extract G-forces and orientation (indices 12-17 in motion tuple)
        telemetry = TelemetryData(
            g_force_lateral=motion[12],
            g_force_longitudinal=motion[13],
            g_force_vertical=motion[14],
            yaw=motion[15],
            pitch=motion[16],
            roll=motion[17],
        )

        self._warn_if_extreme(telemetry)
        self._packets_parsed += 1
        if DEBUG:
            print(telemetry)
        return telemetry

    def _warn_if_extreme(self, telemetry: TelemetryData) -> None:
        """Log warning if G-force values are unusually high (possible crash/glitch)."""
        g_forces = [
            ('lateral', telemetry.g_force_lateral),
            ('longitudinal', telemetry.g_force_longitudinal),
            ('vertical', telemetry.g_force_vertical),
        ]

        for name, value in g_forces:
            if abs(value) > self.G_FORCE_WARN_THRESHOLD:
                logger.warning(f"Extreme G-force {name}: {value:.1f}G")

    @property
    def stats(self) -> dict:
        """Return parsing statistics."""
        return {
            'packets_parsed': self._packets_parsed,
            'invalid_packets': self._invalid_packets,
        }


# Standalone test with recording file
if __name__ == '__main__':
    import os

    logging.basicConfig(level=logging.DEBUG)

    print("Packet Parser Test")
    print("=" * 40)
    print(f"Header size: {PacketParser.HEADER_SIZE} bytes")
    print(f"Motion data per car: {PacketParser.MOTION_DATA_SIZE} bytes")
    print()

    # Try to load a recording
    recording_path = 'recordings/spa_60sec.bin'
    if os.path.exists(recording_path):
        print(f"Testing with {recording_path}...")

        parser = PacketParser()

        with open(recording_path, 'rb') as f:
            count = struct.unpack('<I', f.read(4))[0]

            parsed = 0
            for i in range(min(100, count)):
                timestamp, length = struct.unpack('<fI', f.read(8))
                data = f.read(length)

                result = parser.parse_motion_packet(data)
                if result:
                    parsed += 1
                    if parsed <= 3:
                        print(f"  [{timestamp:.2f}s] {result}")

        print()
        print(f"Parsed {parsed} motion packets from first 100 packets")
        print(f"Stats: {parser.stats}")
    else:
        print("No recording found. Run telemetry_recorder.py first.")
