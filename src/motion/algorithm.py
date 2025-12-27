"""
Motion Algorithm - INF-107, INF-147, INF-148

INF-107: Converts F1 telemetry to 6-DOF platform positions.
INF-147: Uses hybrid washout: high-pass for onset cues + low-pass for sustained feel.
INF-148: Slew rate limiting: prevents impossible position jumps.

Output in meters. Drivers handle clamping.
"""

import math
from src.telemetry.packet_parser import TelemetryData
from src.shared.types import Position6DOF


class HighPassFilter:
    """Second-order Butterworth high-pass filter for onset cues."""

    def __init__(self, cutoff_hz: float, sample_rate: float):
        omega = 2.0 * math.pi * cutoff_hz / sample_rate
        alpha = math.sin(omega) / (2.0 * 0.707)  # Q = 0.707 for Butterworth
        cos_omega = math.cos(omega)

        a0 = 1.0 + alpha
        self.b0 = ((1.0 + cos_omega) / 2.0) / a0
        self.b1 = (-(1.0 + cos_omega)) / a0
        self.b2 = ((1.0 + cos_omega) / 2.0) / a0
        self.a1 = (-2.0 * cos_omega) / a0
        self.a2 = (1.0 - alpha) / a0

        self.x1 = self.x2 = 0.0
        self.y1 = self.y2 = 0.0

    def process(self, x: float) -> float:
        y = (self.b0 * x + self.b1 * self.x1 + self.b2 * self.x2
             - self.a1 * self.y1 - self.a2 * self.y2)
        self.x2, self.x1 = self.x1, x
        self.y2, self.y1 = self.y1, y
        return y

    def reset(self):
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0


class LowPassFilter:
    """First-order low-pass filter for sustained component."""

    def __init__(self, cutoff_hz: float, sample_rate: float):
        rc = 1.0 / (2.0 * math.pi * cutoff_hz)
        dt = 1.0 / sample_rate
        self.alpha = dt / (rc + dt)
        self.y = 0.0

    def process(self, x: float) -> float:
        self.y += self.alpha * (x - self.y)
        return self.y

    def reset(self):
        self.y = 0.0


class MotionAlgorithm:
    """
    Converts F1 telemetry to 6-DOF platform positions.

    Translational axes use hybrid washout (HP onset + LP sustained).
    Rotational axes use direct scaling.

    Sign conventions:
        Surge:  -g_longitudinal (braking -> forward push)
        Sway:   +g_lateral (right turn -> right push)
        Heave:  +(g_vertical - 1.0) (bump -> platform down)
        Roll/Pitch/Yaw: direct from game angles
    """

    def __init__(self, config: dict):

        self.translation_scale = config.get('translation_scale', 0.1)
        self.rotation_scale = config.get('rotation_scale', 0.5)

        # washout parameters (INF-147)
        self.onset_gain = config.get('onset_gain', 1.0)
        self.sustained_gain = config.get('sustained_gain', 0.4)
        self.deadband = config.get('deadband', 0.08)

        sample_rate = config.get('sample_rate', 60.0)
        washout_freq = config.get('washout_freq', 0.4)
        sustained_freq = config.get('sustained_freq', 3.0)

        # filters for translational axes
        self.hp_surge = HighPassFilter(washout_freq, sample_rate)
        self.lp_surge = LowPassFilter(sustained_freq, sample_rate)

        self.hp_sway = HighPassFilter(washout_freq, sample_rate)
        self.lp_sway = LowPassFilter(sustained_freq, sample_rate)

        self.hp_heave = HighPassFilter(washout_freq, sample_rate)
        self.lp_heave = LowPassFilter(sustained_freq, sample_rate)

        # slew rate limiting (INF-148)
        slew_rate = config.get('slew_rate', 0.4)
        self.max_delta = slew_rate / sample_rate

        # previous output for slew limiting
        self._prev_surge = 0.0
        self._prev_sway = 0.0
        self._prev_heave = 0.0

    def calculate(self, telemetry: TelemetryData) -> Position6DOF:
        """Convert telemetry to platform position with washout filtering and slew limiting."""
        g_long = telemetry.g_force_longitudinal
        g_lat = telemetry.g_force_lateral
        g_vert = telemetry.g_force_vertical

        # apply deadband to filter noise
        if abs(g_long) < self.deadband:
            g_long = 0.0
        if abs(g_lat) < self.deadband:
            g_lat = 0.0

        # convert G-forces to base position in meters
        surge_in = -g_long * self.translation_scale
        sway_in = g_lat * self.translation_scale
        heave_in = (g_vert - 1.0) * self.translation_scale

        # apply hybrid washout: HP for onset + LP for sustained
        surge = (self.hp_surge.process(surge_in) * self.onset_gain +
                 self.lp_surge.process(surge_in) * self.sustained_gain)

        sway = (self.hp_sway.process(sway_in) * self.onset_gain +
                self.lp_sway.process(sway_in) * self.sustained_gain)

        heave = (self.hp_heave.process(heave_in) * self.onset_gain +
                 self.lp_heave.process(heave_in) * self.sustained_gain)

        # apply slew rate limiting
        surge = self._slew_limit(self._prev_surge, surge)
        sway = self._slew_limit(self._prev_sway, sway)
        heave = self._slew_limit(self._prev_heave, heave)

        self._prev_surge = surge
        self._prev_sway = sway
        self._prev_heave = heave

        # rotational axes - direct scaling, no washout
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

    def _slew_limit(self, prev: float, target: float) -> float:
        # limit position change per frame
        delta = target - prev
        if abs(delta) > self.max_delta:
            delta = math.copysign(self.max_delta, delta)
        return prev + delta

    def reset(self):
        self.hp_surge.reset()
        self.lp_surge.reset()
        self.hp_sway.reset()
        self.lp_sway.reset()
        self.hp_heave.reset()
        self.lp_heave.reset()
        self._prev_surge = 0.0
        self._prev_sway = 0.0
        self._prev_heave = 0.0


# test
if __name__ == '__main__':
    import struct
    import os

    config = {
        'translation_scale': 0.1,
        'rotation_scale': 0.5,
        'onset_gain': 1.0,
        'sustained_gain': 0.4,
        'deadband': 0.08,
        'sample_rate': 60.0,
        'washout_freq': 0.4,
        'sustained_freq': 3.0,
        'slew_rate': 0.4,
    }

    algo = MotionAlgorithm(config)

    recording = 'recordings/spa_60sec.bin'
    if os.path.exists(recording):
        from src.telemetry.packet_parser import PacketParser
        parser = PacketParser()

        with open(recording, 'rb') as f:
            count = struct.unpack('<I', f.read(4))[0]
            for _ in range(min(10, count)):
                ts, length = struct.unpack('<fI', f.read(8))
                data = f.read(length)
                tel = parser.parse_motion_packet(data)
                if tel:
                    pos = algo.calculate(tel)
                    print(f"[{ts:.2f}s] G=[{tel.g_force_lateral:+.2f},{tel.g_force_longitudinal:+.2f},{tel.g_force_vertical:+.2f}] -> [{pos.x:+.4f},{pos.y:+.4f},{pos.z:+.4f}]")
    else:
        print("No recording found")
