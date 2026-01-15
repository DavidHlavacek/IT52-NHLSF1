"""
Motion Algorithm - Professional Washout Filter Implementation

Converts F1 telemetry (G-forces, orientation) into actuator positions.

Research-Based Design:
    Professional motion simulators use "washout" filters to:
    1. Provide onset cue (initial motion sensation)
    2. Gradually return to neutral (washout)
    3. Stay within physical travel limits

    For single-axis systems (like our SMC actuator):
    - High-pass filter the G-force input
    - Scale and integrate to get position
    - Apply slew rate limiting for smooth motion
    - Use deadband to reject telemetry noise

Filter Theory:
    High-Pass Filter: y[n] = α * (y[n-1] + x[n] - x[n-1])
    Where α = τ / (τ + dt), τ = 1 / (2π * cutoff_freq)

    This passes rapid changes (onset cue) while filtering out
    sustained forces (which would exceed travel limits).

Anti-Oscillation Measures:
    1. Slew rate limiting - max position change per update
    2. Deadband - ignore small input changes
    3. Smooth position transitions
    4. Don't chase every telemetry update

Dimension Options:
    - surge: Longitudinal G-force (braking/acceleration)
    - sway: Lateral G-force (cornering)
    - heave: Vertical G-force (bumps/kerbs)
    - pitch: Pitch angle from game
    - roll: Roll angle from game
"""

import math
import logging
from dataclasses import dataclass, field
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
    """
    Configuration for the motion algorithm.

    All parameters are tunable and should be adjusted based on
    hardware testing and user preference.
    """
    # Dimension selection (which input drives the actuator)
    dimension: MotionDimension = MotionDimension.SURGE

    # High-pass filter cutoff frequency (Hz)
    # Lower = more sustained feel, higher = quicker washout
    # Recommended: 0.5 - 2.0 Hz for surge
    highpass_cutoff_hz: float = 1.0

    # Gain (G-force or angle to position scaling)
    # Units: mm per G (for G-forces) or mm per radian (for angles)
    gain: float = 100.0  # 1G = 100mm movement

    # Deadband (ignore input changes smaller than this)
    # Units: G (for G-forces) or radians (for angles)
    deadband: float = 0.05

    # Slew rate limit (max position change per second)
    # Prevents jerky motion and reduces oscillation
    # Units: mm/s
    slew_rate_limit: float = 500.0

    # Actuator limits
    stroke_mm: float = 900.0      # Total actuator stroke
    center_mm: float = 450.0      # Center/home position
    soft_limit_mm: float = 50.0   # Soft limit from ends (safety margin)

    # Computed limits
    @property
    def min_position_mm(self) -> float:
        return self.soft_limit_mm

    @property
    def max_position_mm(self) -> float:
        return self.stroke_mm - self.soft_limit_mm

    # Update rate (Hz) - should match command rate to actuator
    update_rate_hz: float = 30.0  # 30Hz is optimal for SMC


@dataclass
class HighPassFilter:
    """
    First-order high-pass filter for washout.

    y[n] = α * (y[n-1] + x[n] - x[n-1])
    Where α = τ / (τ + dt)

    This passes transient changes while filtering sustained values.
    """
    cutoff_hz: float
    sample_rate_hz: float

    # Internal state
    _prev_input: float = 0.0
    _prev_output: float = 0.0
    _alpha: float = field(init=False)

    def __post_init__(self):
        """Calculate filter coefficient."""
        dt = 1.0 / self.sample_rate_hz
        tau = 1.0 / (2.0 * math.pi * self.cutoff_hz)
        self._alpha = tau / (tau + dt)

    def update(self, x: float) -> float:
        """
        Process one sample through the filter.

        Args:
            x: Input value (G-force or angle)

        Returns:
            Filtered output
        """
        # High-pass filter equation
        y = self._alpha * (self._prev_output + x - self._prev_input)

        # Store state for next iteration
        self._prev_input = x
        self._prev_output = y

        return y

    def reset(self):
        """Reset filter state."""
        self._prev_input = 0.0
        self._prev_output = 0.0


class MotionAlgorithm:
    """
    Professional motion algorithm with washout filter.

    Converts F1 telemetry data to single-axis actuator position.
    Uses high-pass filtering for onset cue with gradual washout.

    Key Features:
        - Configurable dimension selection (surge/sway/heave/pitch/roll)
        - High-pass washout filter (prevents exceeding travel limits)
        - Slew rate limiting (smooth motion, anti-oscillation)
        - Deadband (noise rejection)
        - Soft position limits (safety margin from ends)

    Example:
        config = MotionConfig(dimension=MotionDimension.SURGE, gain=100.0)
        algo = MotionAlgorithm(config)

        # In main loop:
        position_mm = algo.calculate(telemetry)
        driver.send_position(position_mm)
    """

    def __init__(self, config: Optional[MotionConfig] = None):
        """
        Initialize the motion algorithm.

        Args:
            config: MotionConfig object. Uses defaults if None.
        """
        self.config = config or MotionConfig()

        # Initialize high-pass filter
        self._filter = HighPassFilter(
            cutoff_hz=self.config.highpass_cutoff_hz,
            sample_rate_hz=self.config.update_rate_hz
        )

        # State tracking
        self._current_position = self.config.center_mm
        self._last_input = 0.0
        self._samples_processed = 0

        logger.info(
            f"Motion algorithm initialized: "
            f"dimension={self.config.dimension.value}, "
            f"gain={self.config.gain}, "
            f"cutoff={self.config.highpass_cutoff_hz}Hz"
        )

    def calculate(self, telemetry: TelemetryData) -> float:
        """
        Calculate actuator position from telemetry.

        This is the main entry point for the motion pipeline.

        Args:
            telemetry: Parsed F1 telemetry data

        Returns:
            Target actuator position in mm
        """
        # Extract input value based on selected dimension
        raw_input = self._extract_input(telemetry)

        # Apply deadband
        if abs(raw_input - self._last_input) < self.config.deadband:
            raw_input = self._last_input
        self._last_input = raw_input

        # Apply high-pass washout filter
        filtered = self._filter.update(raw_input)

        # Scale to position offset from center
        offset_mm = filtered * self.config.gain

        # Calculate target position
        target_mm = self.config.center_mm + offset_mm

        # Apply slew rate limiting
        target_mm = self._apply_slew_rate(target_mm)

        # Clamp to soft limits
        target_mm = self._clamp_position(target_mm)

        # Update state
        self._current_position = target_mm
        self._samples_processed += 1

        return target_mm

    def _extract_input(self, telemetry: TelemetryData) -> float:
        """
        Extract the relevant input value based on dimension selection.

        Args:
            telemetry: Parsed telemetry data

        Returns:
            Input value (G-force or angle)

        Note on sign conventions:
            - Surge: Negative g_force_longitudinal = braking = push forward
                    We invert so braking moves actuator forward (positive)
            - Sway: Positive g_force_lateral = right turn = push right
            - Heave: Subtract 1.0 to remove gravity baseline
        """
        dim = self.config.dimension

        if dim == MotionDimension.SURGE:
            # Invert: braking (negative G) should move forward (positive)
            return -telemetry.g_force_longitudinal

        elif dim == MotionDimension.SWAY:
            return telemetry.g_force_lateral

        elif dim == MotionDimension.HEAVE:
            # Remove gravity baseline (1G at rest)
            return telemetry.g_force_vertical - 1.0

        elif dim == MotionDimension.PITCH:
            return telemetry.pitch

        elif dim == MotionDimension.ROLL:
            return telemetry.roll

        else:
            logger.warning(f"Unknown dimension: {dim}")
            return 0.0

    def _apply_slew_rate(self, target_mm: float) -> float:
        """
        Limit the rate of position change to prevent jerky motion.

        Args:
            target_mm: Desired target position

        Returns:
            Rate-limited target position
        """
        # Calculate max change per update
        dt = 1.0 / self.config.update_rate_hz
        max_change = self.config.slew_rate_limit * dt

        # Calculate required change
        change = target_mm - self._current_position

        # Limit change magnitude
        if abs(change) > max_change:
            change = math.copysign(max_change, change)

        return self._current_position + change

    def _clamp_position(self, position_mm: float) -> float:
        """
        Clamp position to safe operating range.

        Args:
            position_mm: Target position

        Returns:
            Clamped position within soft limits
        """
        return max(
            self.config.min_position_mm,
            min(self.config.max_position_mm, position_mm)
        )

    def reset(self):
        """
        Reset algorithm state (call when restarting or returning to center).
        """
        self._filter.reset()
        self._current_position = self.config.center_mm
        self._last_input = 0.0
        logger.info("Motion algorithm reset")

    def return_to_center(self) -> float:
        """
        Get center position (for shutdown or pause).

        Returns:
            Center position in mm
        """
        return self.config.center_mm

    @property
    def current_position(self) -> float:
        """Current position in mm."""
        return self._current_position

    @property
    def stats(self) -> dict:
        """Return algorithm statistics."""
        return {
            "samples_processed": self._samples_processed,
            "current_position": self._current_position,
            "dimension": self.config.dimension.value
        }


def create_motion_config_from_dict(config_dict: dict) -> MotionConfig:
    """
    Create MotionConfig from a configuration dictionary.

    Args:
        config_dict: Dictionary with configuration values

    Returns:
        MotionConfig object
    """
    # Map dimension string to enum
    dimension_str = config_dict.get("dimension", "surge").lower()
    try:
        dimension = MotionDimension(dimension_str)
    except ValueError:
        logger.warning(f"Unknown dimension '{dimension_str}', using surge")
        dimension = MotionDimension.SURGE

    return MotionConfig(
        dimension=dimension,
        highpass_cutoff_hz=config_dict.get("highpass_cutoff_hz", 1.0),
        gain=config_dict.get("gain", 100.0),
        deadband=config_dict.get("deadband", 0.05),
        slew_rate_limit=config_dict.get("slew_rate_limit", 500.0),
        stroke_mm=config_dict.get("stroke_mm", 900.0),
        center_mm=config_dict.get("center_mm", 450.0),
        soft_limit_mm=config_dict.get("soft_limit_mm", 50.0),
        update_rate_hz=config_dict.get("update_rate_hz", 30.0)
    )


# For standalone testing
if __name__ == "__main__":
    """
    Test the motion algorithm with simulated telemetry.

    Run: python -m src.motion.algorithm
    """
    import time
    logging.basicConfig(level=logging.DEBUG)

    print("Motion Algorithm Test")
    print("=" * 50)

    # Create algorithm with default config
    config = MotionConfig(
        dimension=MotionDimension.SURGE,
        gain=100.0,  # 1G = 100mm
        highpass_cutoff_hz=1.0,
        slew_rate_limit=500.0
    )
    algo = MotionAlgorithm(config)

    print(f"Config: {config}")
    print(f"Position limits: {config.min_position_mm} - {config.max_position_mm} mm")
    print()

    # Simulate braking event
    print("Simulating braking event (2G deceleration for 0.5s)...")
    print("-" * 50)

    dt = 1.0 / 30.0  # 30Hz
    positions = []

    # Ramp up braking
    for i in range(15):  # 0.5s at 30Hz
        g_long = -2.0  # 2G braking
        telemetry = TelemetryData(
            g_force_lateral=0.0,
            g_force_longitudinal=g_long,
            g_force_vertical=1.0,
            yaw=0.0, pitch=0.0, roll=0.0
        )
        pos = algo.calculate(telemetry)
        positions.append(pos)
        print(f"t={i*dt:.2f}s: G={g_long:.1f}, pos={pos:.1f}mm")

    # Release brake (washout)
    print("\nReleasing brake (washout)...")
    for i in range(45):  # 1.5s washout
        g_long = 0.0
        telemetry = TelemetryData(
            g_force_lateral=0.0,
            g_force_longitudinal=g_long,
            g_force_vertical=1.0,
            yaw=0.0, pitch=0.0, roll=0.0
        )
        pos = algo.calculate(telemetry)
        positions.append(pos)
        if i % 5 == 0:
            print(f"t={(15+i)*dt:.2f}s: G={g_long:.1f}, pos={pos:.1f}mm")

    print()
    print(f"Final position: {algo.current_position:.1f}mm")
    print(f"Center position: {config.center_mm:.1f}mm")
    print(f"Position should return toward center due to washout filter")

    # Test different dimensions
    print("\n" + "=" * 50)
    print("Testing dimension selection...")

    for dim in MotionDimension:
        config = MotionConfig(dimension=dim, gain=100.0)
        algo = MotionAlgorithm(config)

        telemetry = TelemetryData(
            g_force_lateral=1.0,
            g_force_longitudinal=-1.5,
            g_force_vertical=1.2,
            yaw=0.1, pitch=0.05, roll=0.03
        )

        pos = algo.calculate(telemetry)
        print(f"{dim.value:8s}: position = {pos:.1f}mm")
