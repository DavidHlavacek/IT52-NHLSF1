"""
Safety Limits Module - INF-112

NOTE: This skeleton is a STARTING POINT. Feel free to completely rewrite
this file if you have a better approach. Just keep the core responsibility:
enforce position limits and provide emergency stop functionality.

Ticket: As a developer, I want safety limits in the software so that 
        the hardware cannot be commanded to dangerous positions or speeds.

Assignee: [Unassigned]

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
    from src.utils.safety import SafetyLimiter, EmergencyStop
    
    limiter = SafetyLimiter()
    safe_position = limiter.clamp_position(requested_position)
    
    # In case of emergency:
    EmergencyStop.trigger()
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class SafetyState(Enum):
    """System safety states."""
    NORMAL = "normal"
    WARNING = "warning"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class SafetyConfig:
    """Safety limit configuration."""
    # SMC position limits (mm)
    min_position_smc: float = 5.0       # 5% of stroke
    max_position_smc: float = 95.0      # 95% of stroke
    
    # MOOG position limits (meters)
    max_translation: float = 0.20       # ±200mm
    max_rotation: float = 0.30          # ±17 degrees
    min_heave: float = -0.28
    max_heave: float = -0.08
    
    # Speed limits
    max_speed_smc: float = 50.0         # mm/s
    max_speed_moog: float = 0.15        # m/s
    
    # Timing
    emergency_stop_timeout: float = 5.0


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
    def reset(cls) -> bool:
        if cls._trigger_time:
            elapsed = time.time() - cls._trigger_time
            if elapsed < SafetyConfig.emergency_stop_timeout:
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


class SafetyLimiter:
    """Enforces safety limits on actuator commands."""

    def __init__(self, config: Optional[SafetyConfig] = None):
        self.config = config or SafetyConfig()
        self._warning_count = 0
        self._last_position_smc: Optional[float] = None
        self._last_position_moog: Optional[tuple] = None
        self._last_timestamp: Optional[float] = None

    @property
    def warning_count(self) -> int:
        """Get the current warning count."""
        return self._warning_count

    @property
    def state(self) -> SafetyState:
        """Get current safety state."""
        if EmergencyStop.is_active():
            return SafetyState.EMERGENCY_STOP
        if self._warning_count > 0:
            return SafetyState.WARNING
        return SafetyState.NORMAL

    def clamp_smc_position(self, position_mm: float) -> float:
        """
        Clamp SMC position to safe range (5-95mm).

        TC-SAFE-001: Position must be within [5.0, 95.0] mm
        TC-SAFE-003: If E-stop active, return center position
        TC-SAFE-006: Values within limits pass unchanged
        TC-SAFE-007: Warning count increments on clamping

        Args:
            position_mm: Requested position in millimeters

        Returns:
            Clamped position in millimeters
        """
        # TC-SAFE-003: E-stop blocks all commands, return home
        if EmergencyStop.is_active():
            logger.warning(f"E-stop active: SMC commanded to home (50mm) instead of {position_mm:.2f}mm")
            return self.get_home_position_smc()

        original_position = position_mm

        # TC-SAFE-001: Clamp to safe range
        clamped_position = max(self.config.min_position_smc,
                               min(position_mm, self.config.max_position_smc))

        # TC-SAFE-007: Increment warning count if clamping occurred
        if abs(clamped_position - original_position) > 0.001:
            self._warning_count += 1
            logger.warning(
                f"SMC position clamped: {original_position:.2f}mm -> {clamped_position:.2f}mm "
                f"(limits: {self.config.min_position_smc}-{self.config.max_position_smc}mm) "
                f"[Warning #{self._warning_count}]"
            )

        # TC-SAFE-006: Values within limits pass unchanged
        return clamped_position

    def clamp_moog_position(self, x: float, y: float, z: float,
                            roll: float, pitch: float, yaw: float) -> tuple:
        """
        Clamp MOOG 6-DOF position to safe ranges.

        TC-SAFE-002: All 6 axes must be within safe limits
        TC-SAFE-003: If E-stop active, return home position
        TC-SAFE-006: Values within limits pass unchanged
        TC-SAFE-007: Warning count increments on clamping

        Args:
            x, y: Translation in meters (surge, sway)
            z: Heave in meters
            roll, pitch, yaw: Rotation in radians

        Returns:
            Tuple of (x, y, z, roll, pitch, yaw) clamped to safe ranges
        """
        # TC-SAFE-003: E-stop blocks all commands, return home
        if EmergencyStop.is_active():
            logger.warning(f"E-stop active: MOOG commanded to home instead of "
                          f"({x:.3f}, {y:.3f}, {z:.3f}, {roll:.3f}, {pitch:.3f}, {yaw:.3f})")
            return self.get_home_position_moog()

        original_values = (x, y, z, roll, pitch, yaw)

        # TC-SAFE-002: Clamp each axis to safe range
        x_clamped = max(-self.config.max_translation,
                        min(x, self.config.max_translation))
        y_clamped = max(-self.config.max_translation,
                        min(y, self.config.max_translation))
        z_clamped = max(self.config.min_heave,
                        min(z, self.config.max_heave))
        roll_clamped = max(-self.config.max_rotation,
                           min(roll, self.config.max_rotation))
        pitch_clamped = max(-self.config.max_rotation,
                            min(pitch, self.config.max_rotation))
        yaw_clamped = max(-self.config.max_rotation,
                          min(yaw, self.config.max_rotation))

        clamped_values = (x_clamped, y_clamped, z_clamped,
                         roll_clamped, pitch_clamped, yaw_clamped)

        # TC-SAFE-007: Increment warning count if any axis was clamped
        clamping_occurred = any(
            abs(original - clamped) > 0.0001
            for original, clamped in zip(original_values, clamped_values)
        )

        if clamping_occurred:
            self._warning_count += 1
            axis_names = ['X', 'Y', 'Z', 'Roll', 'Pitch', 'Yaw']
            changes = []
            for i, (orig, clamp, name) in enumerate(zip(original_values, clamped_values, axis_names)):
                if abs(orig - clamp) > 0.0001:
                    changes.append(f"{name}: {orig:.3f}->{clamp:.3f}")

            logger.warning(
                f"MOOG position clamped: {', '.join(changes)} "
                f"[Warning #{self._warning_count}]"
            )

        # TC-SAFE-006: Values within limits pass unchanged
        return clamped_values

    def check_smc_speed(self, position_mm: float) -> bool:
        """
        TC-SAFE-008: Check if SMC speed is within safe limits.

        Args:
            position_mm: New position command

        Returns:
            True if speed is safe, False otherwise
        """
        if self._last_position_smc is None or self._last_timestamp is None:
            # First command, no speed to check
            self._last_position_smc = position_mm
            self._last_timestamp = time.time()
            return True

        current_time = time.time()
        dt = current_time - self._last_timestamp

        if dt < 0.001:  # Avoid division by near-zero
            return True

        displacement = abs(position_mm - self._last_position_smc)
        speed = displacement / dt  # mm/s

        if speed > self.config.max_speed_smc:
            self._warning_count += 1
            logger.warning(
                f"SMC speed limit exceeded: {speed:.1f} mm/s > {self.config.max_speed_smc} mm/s "
                f"[Warning #{self._warning_count}]"
            )
            return False

        self._last_position_smc = position_mm
        self._last_timestamp = current_time
        return True

    def check_moog_speed(self, x: float, y: float, z: float,
                         roll: float, pitch: float, yaw: float) -> bool:
        """
        TC-SAFE-008: Check if MOOG speed is within safe limits.

        Args:
            x, y, z, roll, pitch, yaw: New position command

        Returns:
            True if speed is safe, False otherwise
        """
        current_position = (x, y, z, roll, pitch, yaw)

        if self._last_position_moog is None or self._last_timestamp is None:
            # First command, no speed to check
            self._last_position_moog = current_position
            self._last_timestamp = time.time()
            return True

        current_time = time.time()
        dt = current_time - self._last_timestamp

        if dt < 0.001:  # Avoid division by near-zero
            return True

        # Calculate translation speed (Euclidean distance in 3D space)
        dx = x - self._last_position_moog[0]
        dy = y - self._last_position_moog[1]
        dz = z - self._last_position_moog[2]
        translation_speed = (dx**2 + dy**2 + dz**2)**0.5 / dt  # m/s

        if translation_speed > self.config.max_speed_moog:
            self._warning_count += 1
            logger.warning(
                f"MOOG translation speed limit exceeded: {translation_speed:.3f} m/s > "
                f"{self.config.max_speed_moog} m/s [Warning #{self._warning_count}]"
            )
            return False

        self._last_position_moog = current_position
        self._last_timestamp = current_time
        return True

    def get_home_position_smc(self) -> float:
        """Get SMC home position (center of travel)."""
        return 50.0

    def get_home_position_moog(self) -> tuple:
        """Get MOOG home position (neutral stance)."""
        return (0.0, 0.0, -0.18, 0.0, 0.0, 0.0)


def check_safety_before_command(func):
    """Decorator to check safety before sending commands."""
    def wrapper(*args, **kwargs):
        if EmergencyStop.is_active():
            logger.warning("Command blocked: Emergency stop active")
            return None
        return func(*args, **kwargs)
    return wrapper