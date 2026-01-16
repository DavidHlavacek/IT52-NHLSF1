"""
Motion Algorithm - Simple Direct Mapping

Converts F1 telemetry G-forces directly to actuator positions.
NO washout filter, NO complex processing.

Simple formula:
    position = center - (g_force_longitudinal * gain)

Why subtract? Because in F1 2024:
    - Braking gives NEGATIVE g_force_longitudinal
    - Accelerating gives POSITIVE g_force_longitudinal

So with subtraction:
    - Braking (g_long < 0): center - (negative * gain) = center + something = moves RIGHT
    - Accelerating (g_long > 0): center - (positive * gain) = center - something = moves LEFT
"""

import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from src.telemetry.packet_parser import TelemetryData

logger = logging.getLogger(__name__)


class MotionDimension(Enum):
    """Selectable motion dimension."""
    SURGE = "surge"
    SWAY = "sway"
    HEAVE = "heave"
    PITCH = "pitch"
    ROLL = "roll"


@dataclass
class MotionConfig:
    """Configuration for motion algorithm."""
    dimension: MotionDimension = MotionDimension.SURGE
    gain: float = 100.0
    smoothing: float = 0.5
    deadband: float = 0.05
    stroke_mm: float = 900.0
    center_mm: float = 450.0
    soft_limit_mm: float = 50.0

    # Legacy params (kept for config compatibility)
    highpass_cutoff_hz: float = 1.0
    slew_rate_limit: float = 500.0
    update_rate_hz: float = 30.0

    @property
    def min_position_mm(self) -> float:
        return self.soft_limit_mm

    @property
    def max_position_mm(self) -> float:
        return self.stroke_mm - self.soft_limit_mm


class MotionAlgorithm:
    """
    Simple direct motion mapping.

    Follows debug_simple_motion.py pattern exactly:
        position = center - (g_force * gain)
    """

    def __init__(self, config: Optional[MotionConfig] = None):
        self.config = config or MotionConfig()
        self._smoothed_g = 0.0
        self._current_position = self.config.center_mm
        self._samples = 0

        logger.info(
            f"MotionAlgorithm: dim={self.config.dimension.value}, "
            f"gain={self.config.gain}, center={self.config.center_mm}"
        )

    def calculate(self, telemetry: TelemetryData) -> float:
        """
        Calculate actuator position from telemetry.

        Simple direct mapping - NO washout.
        """
        # Get raw G-force based on dimension
        raw_g = self._get_g_force(telemetry)

        # Apply deadband
        if abs(raw_g) < self.config.deadband:
            raw_g = 0.0

        # Apply smoothing (simple exponential)
        alpha = self.config.smoothing
        self._smoothed_g = alpha * self._smoothed_g + (1.0 - alpha) * raw_g

        # SIMPLE DIRECT MAPPING (matches debug_simple_motion.py)
        # position = center - (g_force * gain)
        position = self.config.center_mm - (self._smoothed_g * self.config.gain)

        # Clamp to limits
        position = max(self.config.min_position_mm,
                       min(self.config.max_position_mm, position))

        self._current_position = position
        self._samples += 1

        return position

    def _get_g_force(self, telemetry: TelemetryData) -> float:
        """Extract G-force based on selected dimension."""
        dim = self.config.dimension

        if dim == MotionDimension.SURGE:
            # Use longitudinal G-force directly - NO INVERSION
            return telemetry.g_force_longitudinal

        elif dim == MotionDimension.SWAY:
            return telemetry.g_force_lateral

        elif dim == MotionDimension.HEAVE:
            return telemetry.g_force_vertical - 1.0  # Remove gravity

        elif dim == MotionDimension.PITCH:
            return telemetry.pitch

        elif dim == MotionDimension.ROLL:
            return telemetry.roll

        return 0.0

    def reset(self):
        """Reset to center."""
        self._smoothed_g = 0.0
        self._current_position = self.config.center_mm

    def return_to_center(self) -> float:
        return self.config.center_mm

    @property
    def current_position(self) -> float:
        return self._current_position

    @property
    def stats(self) -> dict:
        return {
            "samples_processed": self._samples,
            "current_position": self._current_position,
            "smoothed_g": self._smoothed_g,
            "dimension": self.config.dimension.value
        }


def create_motion_config_from_dict(config_dict: dict) -> MotionConfig:
    """Create MotionConfig from dictionary."""
    dimension_str = config_dict.get("dimension", "surge").lower()
    try:
        dimension = MotionDimension(dimension_str)
    except ValueError:
        dimension = MotionDimension.SURGE

    return MotionConfig(
        dimension=dimension,
        gain=config_dict.get("gain", 100.0),
        smoothing=config_dict.get("smoothing", 0.5),
        deadband=config_dict.get("deadband", 0.05),
        stroke_mm=config_dict.get("stroke_mm", 900.0),
        center_mm=config_dict.get("center_mm", 450.0),
        soft_limit_mm=config_dict.get("soft_limit_mm", 50.0),
    )


if __name__ == "__main__":
    """Quick test."""
    logging.basicConfig(level=logging.INFO)

    config = MotionConfig(gain=100.0, center_mm=450.0)
    algo = MotionAlgorithm(config)

    print("Testing simple direct mapping:")
    print(f"  Center: {config.center_mm}mm, Gain: {config.gain}")
    print()

    tests = [
        (0.0, "Coasting"),
        (1.0, "Accelerating 1G"),
        (-1.0, "Braking 1G"),
        (2.0, "Accelerating 2G"),
        (-2.0, "Braking 2G"),
    ]

    for g, desc in tests:
        # Run a few times for smoothing to settle
        for _ in range(20):
            tel = TelemetryData(
                g_force_lateral=0, g_force_longitudinal=g, g_force_vertical=1,
                yaw=0, pitch=0, roll=0
            )
            pos = algo.calculate(tel)
        print(f"  {desc:20s}: g_long={g:+.1f} -> pos={pos:.0f}mm")
