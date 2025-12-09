"""
Motion Algorithm - INF-107

Converts F1 telemetry (G-forces, orientation) into 6-DOF platform positions.

Output: Platform position (x, y, z, roll, pitch, yaw) - NOT actuator positions.
The MOOG controller handles inverse kinematics to calculate actuator lengths internally.

This algorithm uses direct mapping:
- G-forces -> translational positions (surge, sway, heave)
- Orientation angles -> rotational positions (roll, pitch, yaw)
- Two scale factors: translation (0.1 = 1G -> 10cm) and rotation (0.5 = 50% of game angles)

Note: Hardware limit clamping is handled by the drivers, not this algorithm.
Each driver is responsible for enforcing its hardware-specific limits before sending.
"""

from src.telemetry.packet_parser import TelemetryData
from src.shared.types import Position6DOF


class MotionAlgorithm:
    """
    Converts F1 telemetry to 6-DOF platform positions.

    Sign conventions:
        Surge:  -g_longitudinal (braking -> forward push)
        Sway:   +g_lateral (right turn -> right push)
        Heave:  +(g_vertical - 1.0) (bump -> platform down)
        Roll:   lean left/right (positive = right side down)
        Pitch:  tilt front/back (positive = nose up)
        Yaw:    rotate left/right (positive = clockwise from above)

    Note: Output is NOT clamped. Drivers must enforce hardware limits.
    """

    def __init__(self, config: dict):
        motion_cfg = config['motion']
        self.translation_scale = motion_cfg['translation_scale']
        self.rotation_scale = motion_cfg['rotation_scale']

    def calculate(self, telemetry: TelemetryData) -> Position6DOF:
        """
        Convert F1 telemetry to platform position.

        Args:
            telemetry: Current F1 game telemetry

        Returns:
            Position6DOF (unclamped - driver must enforce limits)
        """
        # === TRANSLATIONAL AXES (from G-forces) ===

        surge = -telemetry.g_force_longitudinal * self.translation_scale
        sway = telemetry.g_force_lateral * self.translation_scale
        heave = (telemetry.g_force_vertical - 1.0) * self.translation_scale

        # === ROTATIONAL AXES (from angles) ===

        roll = telemetry.roll * self.rotation_scale
        pitch = telemetry.pitch * self.rotation_scale
        yaw = telemetry.yaw * self.rotation_scale

        return Position6DOF(
            x=surge,
            y=sway,
            z=heave,
            roll=roll,
            pitch=pitch,
            yaw=yaw
        )

# Standalone test with recording file
if __name__ == '__main__':
    import struct
    import os

    config = {'motion': {'translation_scale': 0.1, 'rotation_scale': 0.5}}
    algo = MotionAlgorithm(config)

    # Test with recording
    recording = 'recordings/spa_60sec.bin'
    if os.path.exists(recording):
        from src.telemetry.packet_parser import PacketParser
        parser = PacketParser()

        with open(recording, 'rb') as f:
            count = struct.unpack('<I', f.read(4))[0]
            for _ in range(min(5, count)):
                ts, length = struct.unpack('<fI', f.read(8))
                data = f.read(length)
                tel = parser.parse_motion_packet(data)
                if tel:
                    pos = algo.calculate(tel)
                    print(f"[{ts:.2f}s] G=[{tel.g_force_lateral:+.2f},{tel.g_force_longitudinal:+.2f},{tel.g_force_vertical:+.2f}] -> [{pos.x:+.3f},{pos.y:+.3f},{pos.z:+.3f}]")
    else:
        print("No recording found")
