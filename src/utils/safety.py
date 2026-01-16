"""
Safety Limits Module - INF-112

This module sits between the motion algorithm and hardware drivers, providing
defense in depth - clamping happens here AND in the drivers (double protection).

Ticket: As a developer, I want safety limits in the software so that
        the hardware cannot be commanded to dangerous positions or speeds.

This module enforces safety constraints on all actuator commands.

Acceptance Criteria:
    - Position limits enforced in driver code
    - Speed/acceleration limits enforced
    - Emergency stop function implemented
    - Limits configurable in config file
    - Out-of-range commands logged as warnings

Dependencies:
    - INF-105: SMC Driver (applies limits before sending)
    - INF-108: MOOG Driver (applies limits before sending)

Usage:
    from src.utils.safety import SafetyModule
    from src.shared.types import Position6DOF

    safety = SafetyModule()

    # Clamp SMC position
    safe_smc = safety.clamp_smc_position(position_mm)

    # Clamp MOOG position
    safe_moog = safety.clamp_moog_position(position_6dof)

    # In case of emergency:
    safety.trigger_estop()
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum
from src.shared.types import Position6DOF

logger = logging.getLogger(__name__)


class SafetyState(Enum):
    """System safety states."""
    NORMAL = "normal"
    WARNING = "warning"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class SafetyConfig:
    """Safety limit configuration."""
    # SMC position limits (mm) - Per INF-112 Guide
    min_position_smc: float = 5.0       # Safe range: 5-895mm
    max_position_smc: float = 895.0

    # MOOG position limits (meters and radians) - Per INF-112 Guide
    # Surge limits
    surge_min: float = -0.241
    surge_max: float = 0.259
    # Sway limits
    sway_min: float = -0.259
    sway_max: float = 0.259
    # Heave limits
    heave_min: float = -0.178
    heave_max: float = 0.178
    # Roll limits (radians, ±21°)
    roll_min: float = -0.367
    roll_max: float = 0.367
    # Pitch limits (radians, ±22°)
    pitch_min: float = -0.384
    pitch_max: float = 0.384
    # Yaw limits (radians, ±22°)
    yaw_min: float = -0.384
    yaw_max: float = 0.384

    # Speed limits
    max_speed_smc: float = 500.0        # mm/s - Per INF-112 Guide

    # Timing
    emergency_stop_timeout: float = 2.0  # seconds - Per INF-112 Guide


class EmergencyStop:
    """Global emergency stop controller."""
    
    _active: bool = False
    _trigger_time: Optional[float] = None
    _callbacks: list = []
    
    @classmethod
    def trigger(cls, reason: str = "Manual trigger"):
        cls._active = True
        cls._trigger_time = time.time()
        logger.critical(f"EMERGENCY STOP: {reason}")
        for callback in cls._callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"E-stop callback failed: {e}")
    
    @classmethod
    def reset(cls, timeout: float = 2.0) -> bool:
        """
        Reset emergency stop after timeout period.

        Args:
            timeout: Minimum seconds to wait before reset (default 2.0)

        Returns:
            True if reset successful, False if timeout not elapsed
        """
        if cls._trigger_time:
            elapsed = time.time() - cls._trigger_time
            if elapsed < timeout:
                return False
        cls._active = False
        cls._trigger_time = None
        return True
    
    @classmethod
    def is_active(cls) -> bool:
        return cls._active
    
    @classmethod
    def register_callback(cls, callback: Callable):
        cls._callbacks.append(callback)


class SafetyModule:
    """
    Safety module for enforcing position limits and emergency stop.

    Sits between motion algorithm and hardware drivers to provide
    defense in depth.
    """

    # SMC limits (mm)
    SMC_MIN_MM = 5.0
    SMC_MAX_MM = 895.0
    SMC_MAX_SPEED_MM_S = 500.0
    SMC_CENTER_MM = 450.0

    # MOOG limits (meters and radians)
    MOOG_LIMITS = {
        'surge': (-0.241, +0.259),
        'sway':  (-0.259, +0.259),
        'heave': (-0.178, +0.178),
        'roll':  (-0.367, +0.367),
        'pitch': (-0.384, +0.384),
        'yaw':   (-0.384, +0.384),
    }

    # E-stop
    ESTOP_TIMEOUT_S = 2.0

    def __init__(self):
        self._estopped = False
        self._estop_time: Optional[float] = None
        self._estop_callbacks: list[Callable] = []
        self._warning_count = 0

    def clamp_smc_position(self, position_mm: float) -> float:
        """
        Clamp SMC position to safe range (5-895mm).
        Increment warning_count if clamping occurs.

        Args:
            position_mm: Requested SMC position in millimeters

        Returns:
            Clamped position in safe range
        """
        original = position_mm

        if position_mm < self.SMC_MIN_MM:
            position_mm = self.SMC_MIN_MM
            self._warning_count += 1
            logger.warning(f"SMC position clamped: {original:.1f}mm -> {position_mm:.1f}mm (below minimum)")
        elif position_mm > self.SMC_MAX_MM:
            position_mm = self.SMC_MAX_MM
            self._warning_count += 1
            logger.warning(f"SMC position clamped: {original:.1f}mm -> {position_mm:.1f}mm (above maximum)")

        return position_mm

    def clamp_moog_position(self, position: Position6DOF) -> Position6DOF:
        """
        Clamp all 6 MOOG axes to safe ranges.
        Increment warning_count if any axis clamped.

        Args:
            position: Position6DOF object with requested position

        Returns:
            New Position6DOF with clamped values
        """
        clamped = Position6DOF(
            x=position.x,
            y=position.y,
            z=position.z,
            roll=position.roll,
            pitch=position.pitch,
            yaw=position.yaw
        )

        # Clamp surge (x)
        surge_min, surge_max = self.MOOG_LIMITS['surge']
        if clamped.x < surge_min:
            self._warning_count += 1
            logger.warning(f"MOOG surge clamped: {clamped.x:.3f}m -> {surge_min:.3f}m")
            clamped.x = surge_min
        elif clamped.x > surge_max:
            self._warning_count += 1
            logger.warning(f"MOOG surge clamped: {clamped.x:.3f}m -> {surge_max:.3f}m")
            clamped.x = surge_max

        # Clamp sway (y)
        sway_min, sway_max = self.MOOG_LIMITS['sway']
        if clamped.y < sway_min:
            self._warning_count += 1
            logger.warning(f"MOOG sway clamped: {clamped.y:.3f}m -> {sway_min:.3f}m")
            clamped.y = sway_min
        elif clamped.y > sway_max:
            self._warning_count += 1
            logger.warning(f"MOOG sway clamped: {clamped.y:.3f}m -> {sway_max:.3f}m")
            clamped.y = sway_max

        # Clamp heave (z)
        heave_min, heave_max = self.MOOG_LIMITS['heave']
        if clamped.z < heave_min:
            self._warning_count += 1
            logger.warning(f"MOOG heave clamped: {clamped.z:.3f}m -> {heave_min:.3f}m")
            clamped.z = heave_min
        elif clamped.z > heave_max:
            self._warning_count += 1
            logger.warning(f"MOOG heave clamped: {clamped.z:.3f}m -> {heave_max:.3f}m")
            clamped.z = heave_max

        # Clamp roll
        roll_min, roll_max = self.MOOG_LIMITS['roll']
        if clamped.roll < roll_min:
            self._warning_count += 1
            logger.warning(f"MOOG roll clamped: {clamped.roll:.3f}rad -> {roll_min:.3f}rad")
            clamped.roll = roll_min
        elif clamped.roll > roll_max:
            self._warning_count += 1
            logger.warning(f"MOOG roll clamped: {clamped.roll:.3f}rad -> {roll_max:.3f}rad")
            clamped.roll = roll_max

        # Clamp pitch
        pitch_min, pitch_max = self.MOOG_LIMITS['pitch']
        if clamped.pitch < pitch_min:
            self._warning_count += 1
            logger.warning(f"MOOG pitch clamped: {clamped.pitch:.3f}rad -> {pitch_min:.3f}rad")
            clamped.pitch = pitch_min
        elif clamped.pitch > pitch_max:
            self._warning_count += 1
            logger.warning(f"MOOG pitch clamped: {clamped.pitch:.3f}rad -> {pitch_max:.3f}rad")
            clamped.pitch = pitch_max

        # Clamp yaw
        yaw_min, yaw_max = self.MOOG_LIMITS['yaw']
        if clamped.yaw < yaw_min:
            self._warning_count += 1
            logger.warning(f"MOOG yaw clamped: {clamped.yaw:.3f}rad -> {yaw_min:.3f}rad")
            clamped.yaw = yaw_min
        elif clamped.yaw > yaw_max:
            self._warning_count += 1
            logger.warning(f"MOOG yaw clamped: {clamped.yaw:.3f}rad -> {yaw_max:.3f}rad")
            clamped.yaw = yaw_max

        return clamped

    def trigger_estop(self, reason: str = "Manual trigger") -> None:
        """
        Activate emergency stop.
        - Block all commands
        - Record timestamp
        - Execute all registered callbacks

        Args:
            reason: Description of why e-stop was triggered
        """
        self._estopped = True
        self._estop_time = time.time()
        logger.critical(f"EMERGENCY STOP: {reason}")

        for callback in self._estop_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"E-stop callback failed: {e}")

    def reset_estop(self) -> bool:
        """
        Reset e-stop after timeout (2 seconds).

        Returns:
            True if reset successful, False if timeout not elapsed
        """
        if self._estop_time:
            elapsed = time.time() - self._estop_time
            if elapsed < self.ESTOP_TIMEOUT_S:
                return False

        self._estopped = False
        self._estop_time = None
        logger.info("Emergency stop reset")
        return True

    def is_estopped(self) -> bool:
        """Check if e-stop is active."""
        return self._estopped

    def register_estop_callback(self, callback: Callable) -> None:
        """Register a function to call when e-stop triggers."""
        self._estop_callbacks.append(callback)

    def limit_speed(self, current_mm: float, target_mm: float, dt: float) -> float:
        """
        Limit position change to respect max speed (500 mm/s).

        Args:
            current_mm: Current SMC position in mm
            target_mm: Requested target position in mm
            dt: Time delta in seconds

        Returns:
            Adjusted target position respecting speed limit
        """
        if dt <= 0:
            # If dt is zero or negative (clock skew), maintain current position
            return current_mm

        max_change = self.SMC_MAX_SPEED_MM_S * dt
        actual_change = target_mm - current_mm

        if abs(actual_change) > max_change:
            # Limit the change
            direction = 1 if actual_change > 0 else -1
            limited_target = current_mm + (direction * max_change)
            self._warning_count += 1
            logger.warning(
                f"SMC speed limited: requested change {actual_change:.1f}mm in {dt:.3f}s "
                f"(would be {abs(actual_change)/dt:.1f}mm/s), limited to {max_change:.1f}mm"
            )
            return limited_target

        return target_mm

    @property
    def warning_count(self) -> int:
        """Number of times clamping has occurred."""
        return self._warning_count

    @property
    def state(self) -> SafetyState:
        """Current safety state."""
        if self._estopped:
            return SafetyState.EMERGENCY_STOP
        elif self._warning_count > 0:
            return SafetyState.WARNING
        return SafetyState.NORMAL


# Maintain backward compatibility
SafetyLimiter = SafetyModule


def check_safety_before_command(func):
    """Decorator to check safety before sending commands."""
    def wrapper(*args, **kwargs):
        if EmergencyStop.is_active():
            logger.warning("Command blocked: Emergency stop active")
            return None
        return func(*args, **kwargs)
    return wrapper