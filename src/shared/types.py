"""
Shared type definitions for F1 Motion Simulator.
"""

import struct
from dataclasses import dataclass


@dataclass
class Position6DOF:
    """
    6-DOF platform position for the MOOG Stewart platform.

    This represents the TARGET POSITION of the platform, not individual
    actuator positions. The MOOG controller handles inverse kinematics
    to calculate actuator lengths internally.

    Units:
        x, y, z: meters
        roll, pitch, yaw: radians
    """

    x: float = 0.0       # Surge (forward/back)
    y: float = 0.0       # Sway (left/right)
    z: float = 0.0       # Heave (up/down) — home position TBD (INF-106)
    roll: float = 0.0    # Lean left(-) / right(+)
    pitch: float = 0.0   # Nose down(-) / up(+)
    yaw: float = 0.0     # Rotate left(-) / right(+)

    def to_bytes(self) -> bytes:
        """Pack position into 24 bytes for UDP transmission to MOOG."""
        return struct.pack(
            '<ffffff',
            self.x, self.y, self.z,
            self.roll, self.pitch, self.yaw
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Position6DOF':
        """Unpack position from 24 bytes received from MOOG."""
        values = struct.unpack('<ffffff', data[:24])
        return cls(*values)

    def __str__(self):
        return (
            f"Position6DOF("
            f"x={self.x:.3f}, y={self.y:.3f}, z={self.z:.3f}, "
            f"roll={self.roll:.3f}, pitch={self.pitch:.3f}, yaw={self.yaw:.3f})"
        )
