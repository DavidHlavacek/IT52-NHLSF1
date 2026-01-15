"""
Motion Algorithm - Direct Proportional Mapping

Converts F1 telemetry (G-forces) directly to actuator positions.

Design Philosophy:
    DIRECT PROPORTIONAL - NOT washout filtering!

    The user wants:
    - Accelerating → actuator moves one direction and STAYS there
    - Braking → actuator moves opposite direction and STAYS there
    - Coasting → actuator at center

    This is simple proportional mapping:
    position = center + (g_force * gain)

Sign Convention (for surge/longitudinal):
    - F1 telemetry: positive g_force_longitudinal = acceleration
    - Our mapping: acceleration → position INCREASES (away from 0)
                   braking → position DECREASES (toward 0)

    So if center is 450mm on 900mm stroke:
    - Accelerating: position > 450mm (toward 900mm end)
    - Braking: position < 450mm (toward 0mm end)

Smoothing:
    Simple exponential smoothing to prevent jitter from noisy telemetry.
    NOT a washout filter - just noise reduction.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from src.telemetry.packet_parser import TelemetryData

logger = logging.getLogger(__name__)


class MotionDimension(Enum):
    """Selectable motion dimension for single-axis actuator."""
    SURGE = "surge"           # Longitudinal G-force (braking/accel)
    SWAY = "sway"             # Lateral G-force (cornering)
    HEAVE = "heave"           # Vertical G-force (bumps)
    PITCH = "pitch"           # Pitch angle
    ROLL = "roll"             # Roll angle


@dataclass
class MotionConfig:
    """Configuration for the motion algorithm."""

    # Dimension selection
    dimension: MotionDimension = MotionDimension.SURGE

    # Gain: how much actuator moves per G (or per radian for angles)
    # Example: gain=100 means 1G causes 100mm movement from center
    gain: float = 100.0

    # Smoothing factor (0.0-1.0)
    # Higher = more smoothing (slower response)
    # Lower = less smoothing (faster but noisier)
    # 0.0 = no smoothing (raw input)
    smoothing: float = 0.3

    # Deadband: ignore G-forces smaller than this
    deadband: float = 0.02

    # Actuator limits
    stroke_mm: float = 900.0
    center_mm: float = 450.0
    soft_limit_mm: float = 50.0

    # NOT USED anymore (was for washout)
    highpass_cutoff_hz: float = 1.0  # Kept for config compatibility
    slew_rate_limit: float = 500.0   # Kept for config compatibility
    update_rate_hz: float = 30.0     # Kept for config compatibility

    @property
    def min_position_mm(self) -> float:
        return self.soft_limit_mm

    @property
    def max_position_mm(self) -> float:
        return self.stroke_mm - self.soft_limit_mm


class MotionAlgorithm:
    """
    Direct proportional motion algorithm.

    Maps G-forces directly to actuator position:
        position = center + (g_force * gain)

    With simple exponential smoothing for noise reduction.

    Example:
        config = MotionConfig(dimension=MotionDimension.SURGE, gain=100.0)
        algo = MotionAlgorithm(config)

        # In main loop:
        position_mm = algo.calculate(telemetry)
        driver.send_position(position_mm)
    """

    def __init__(self, config: Optional[MotionConfig] = None):
        """Initialize the motion algorithm."""
        self.config = config or MotionConfig()

        # Smoothed input value
        self._smoothed_input = 0.0

        # Current calculated position
        self._current_position = self.config.center_mm

        # Statistics
        self._samples_processed = 0

        logger.info(
            f"Motion algorithm initialized: "
            f"dimension={self.config.dimension.value}, "
            f"gain={self.config.gain}, "
            f"smoothing={self.config.smoothing}"
        )

    def calculate(self, telemetry: TelemetryData) -> float:
        """
        Calculate actuator position from telemetry.

        DIRECT PROPORTIONAL MAPPING:
            position = center + (smoothed_g_force * gain)

        Args:
            telemetry: Parsed F1 telemetry data

        Returns:
            Target actuator position in mm
        """
        # Extract raw input based on dimension
        raw_input = self._extract_input(telemetry)

        # Apply deadband
        if abs(raw_input) < self.config.deadband:
            raw_input = 0.0

        # Apply exponential smoothing (simple low-pass, NOT washout!)
        # smoothed = smoothing * old + (1 - smoothing) * new
        alpha = self.config.smoothing
        self._smoothed_input = alpha * self._smoothed_input + (1.0 - alpha) * raw_input

        # DIRECT PROPORTIONAL: position = center + (input * gain)
        offset_mm = self._smoothed_input * self.config.gain
        target_mm = self.config.center_mm + offset_mm

        # Clamp to safe limits
        target_mm = self._clamp_position(target_mm)

        # Update state
        self._current_position = target_mm
        self._samples_processed += 1

        return target_mm

    def _extract_input(self, telemetry: TelemetryData) -> float:
        """
        Extract the relevant input value based on dimension.

        Sign conventions for F1 2024:
            g_force_longitudinal: positive = acceleration, negative = braking
            g_force_lateral: positive = turning right, negative = turning left
            g_force_vertical: ~1.0 at rest (gravity), higher on bumps

        For SURGE dimension:
            We want: acceleration → position increases (toward stroke end)
                     braking → position decreases (toward 0)
            So we use g_force_longitudinal directly (positive = forward motion)
        """
        dim = self.config.dimension

        if dim == MotionDimension.SURGE:
            # Positive g_long = acceleration = move toward high end
            # Negative g_long = braking = move toward low end
            return telemetry.g_force_longitudinal

        elif dim == MotionDimension.SWAY:
            # Positive = right turn = move one way
            return telemetry.g_force_lateral

        elif dim == MotionDimension.HEAVE:
            # Remove gravity baseline (1G at rest)
            return telemetry.g_force_vertical - 1.0

        elif dim == MotionDimension.PITCH:
            return telemetry.pitch

        elif dim == MotionDimension.ROLL:
            return telemetry.roll

        else:
            return 0.0

    def _clamp_position(self, position_mm: float) -> float:
        """Clamp position to safe operating range."""
        return max(
            self.config.min_position_mm,
            min(self.config.max_position_mm, position_mm)
        )

    def reset(self):
        """Reset algorithm state."""
        self._smoothed_input = 0.0
        self._current_position = self.config.center_mm
        logger.info("Motion algorithm reset")

    def return_to_center(self) -> float:
        """Get center position."""
        return self.config.center_mm

    @property
    def current_position(self) -> float:
        return self._current_position

    @property
    def stats(self) -> dict:
        return {
            "samples_processed": self._samples_processed,
            "current_position": self._current_position,
            "smoothed_input": self._smoothed_input,
            "dimension": self.config.dimension.value
        }


def create_motion_config_from_dict(config_dict: dict) -> MotionConfig:
    """Create MotionConfig from configuration dictionary."""

    # Map dimension string to enum
    dimension_str = config_dict.get("dimension", "surge").lower()
    try:
        dimension = MotionDimension(dimension_str)
    except ValueError:
        logger.warning(f"Unknown dimension '{dimension_str}', using surge")
        dimension = MotionDimension.SURGE

    return MotionConfig(
        dimension=dimension,
        gain=config_dict.get("gain", 100.0),
        smoothing=config_dict.get("smoothing", 0.3),
        deadband=config_dict.get("deadband", 0.02),
        stroke_mm=config_dict.get("stroke_mm", 900.0),
        center_mm=config_dict.get("center_mm", 450.0),
        soft_limit_mm=config_dict.get("soft_limit_mm", 50.0),
        # Legacy params (ignored)
        highpass_cutoff_hz=config_dict.get("highpass_cutoff_hz", 1.0),
        slew_rate_limit=config_dict.get("slew_rate_limit", 500.0),
        update_rate_hz=config_dict.get("update_rate_hz", 30.0)
    )


# For standalone testing
if __name__ == "__main__":
    """Test direct proportional mapping."""
    import time
    logging.basicConfig(level=logging.DEBUG)

    print("Motion Algorithm Test - Direct Proportional")
    print("=" * 50)

    config = MotionConfig(
        dimension=MotionDimension.SURGE,
        gain=100.0,      # 1G = 100mm movement
        smoothing=0.3,   # Light smoothing
        center_mm=450.0
    )
    algo = MotionAlgorithm(config)

    print(f"Config: gain={config.gain}, center={config.center_mm}mm")
    print(f"Limits: {config.min_position_mm} - {config.max_position_mm}mm")
    print()

    # Test cases
    test_cases = [
        (0.0, "Coasting (0G)"),
        (1.0, "Accelerating (1G)"),
        (2.0, "Hard acceleration (2G)"),
        (-1.0, "Braking (1G)"),
        (-2.0, "Hard braking (2G)"),
        (0.0, "Back to coasting"),
    ]

    print("Testing direct proportional mapping:")
    print("-" * 50)

    for g_force, desc in test_cases:
        # Simulate a few samples to let smoothing settle
        for _ in range(10):
            telemetry = TelemetryData(
                g_force_lateral=0.0,
                g_force_longitudinal=g_force,
                g_force_vertical=1.0,
                yaw=0.0, pitch=0.0, roll=0.0
            )
            pos = algo.calculate(telemetry)

        expected = config.center_mm + (g_force * config.gain)
        print(f"{desc:25s}: G={g_force:+.1f} -> pos={pos:.1f}mm (expected ~{expected:.0f}mm)")

    print()
    print("Expected behavior:")
    print("  - Accelerating: position > 450mm (toward 900mm)")
    print("  - Braking: position < 450mm (toward 0mm)")
    print("  - Coasting: position = 450mm (center)")
