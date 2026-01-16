"""
Motion Algorithm v2.0 - Optimized for SMC actuator
"""

from dataclasses import dataclass
from src.telemetry.packet_parser import TelemetryData

@dataclass
class AlgorithmConfig:
    dimension: str = "surge"      # surge, sway, heave
    scale: float = 80.0           # mm per g force
    smoothing: float = 0        # 0-1 no-max smoothing
    threshold: float = 0.05       # ignore g forces below
    center_mm: float = 350.0      # center pos on actuator
    min_mm: float = 50.0          # min safe position
    max_mm: float = 850.0         # max safe position


class MotionAlgorithmV2:
    def __init__(self, config: AlgorithmConfig = None):
        self.config = config or AlgorithmConfig()
        self.smoothed_g = 0.0
        self.last_g_force = 0.0

    def calculate(self, telemetry: TelemetryData) -> float:
        g_force = self._get_dimension_value(telemetry)

        # filter noise
        # if abs(g_force) < self.config.threshold:
        #     g_force = 0.0

        # ignore small changes
        if abs(g_force - self.last_g_force) < self.config.threshold:
            g_force = self.last_g_force
        else:
            self.last_g_force = g_force

        # smoothing
        smoothing = self.config.smoothing
        self.smoothed_g = smoothing * self.smoothed_g + (1.0 - smoothing) * g_force

        # position = center - (g force * scale)
        position_mm = self.config.center_mm - (self.smoothed_g * self.config.scale)

        # clamp to safe limits
        position_mm = max(self.config.min_mm, min(self.config.max_mm, position_mm))

        return position_mm

    def _get_dimension_value(self, telemetry: TelemetryData) -> float:
        dim = self.config.dimension

        if dim == "surge":
            return telemetry.g_force_longitudinal
        elif dim == "sway":
            return telemetry.g_force_lateral
        elif dim == "heave":
            return telemetry.g_force_vertical - 1.0  # remove gravity
        else:
            return telemetry.g_force_longitudinal

    def reset(self):
        self.smoothed_g = 0.0
