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
    
    def clamp_smc_position(self, position_mm: float) -> float:
        """
        TODO [INF-112]: Implement this method
        
        Clamp SMC position to safe range (5-95mm).
        """
        raise NotImplementedError("INF-112: Implement clamp_smc_position()")
    
    def clamp_moog_position(self, x: float, y: float, z: float,
                            roll: float, pitch: float, yaw: float) -> tuple:
        """
        TODO [INF-112]: Implement this method
        
        Clamp MOOG 6-DOF position to safe ranges.
        """
        raise NotImplementedError("INF-112: Implement clamp_moog_position()")
    
    def get_home_position_smc(self) -> float:
        return 50.0
    
    def get_home_position_moog(self) -> tuple:
        return (0.0, 0.0, -0.18, 0.0, 0.0, 0.0)


def check_safety_before_command(func):
    """Decorator to check safety before sending commands."""
    def wrapper(*args, **kwargs):
        if EmergencyStop.is_active():
            logger.warning("Command blocked: Emergency stop active")
            return None
        return func(*args, **kwargs)
    return wrapper