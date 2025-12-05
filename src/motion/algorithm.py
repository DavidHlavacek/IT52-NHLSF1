"""
Motion Algorithm - INF-107

NOTE: This skeleton is a STARTING POINT. Feel free to completely rewrite
this file if you have a better approach. Just keep the core responsibility:
convert telemetry data (G-forces) into actuator positions.

Ticket: As a developer, I want a motion algorithm that converts F1 physics data 
        to actuator positions so that the platform movement matches the game

Assignee: David

This module converts telemetry data (G-forces, orientation) into actuator positions.

Acceptance Criteria:
    ☐ G-force to position mapping implemented
    ☐ Scale factors configurable (SURGE_SCALE, SWAY_SCALE, etc.)
    ☐ Output clamped to safe actuator limits
    ☐ Smoothing/filtering applied to prevent jerky motion
    ☐ Algorithm works for both SMC (1-DOF) and MOOG (6-DOF)
    ☐ Unit tests validate output ranges
    
Dependencies:
    - INF-103: Telemetry data structure defined

Motion Cueing Theory:
    The algorithm uses "washout" filters to:
    1. Translate G-forces into initial motion
    2. Gradually return to neutral while maintaining the sensation
    3. Stay within the platform's physical limits
    
    For this project, we use a simplified approach:
    - Direct mapping of G-forces to positions
    - Configurable scale factors
    - Low-pass filtering for smoothness

Usage:
    from src.motion.algorithm import MotionAlgorithm
    from src.telemetry.packet_parser import TelemetryData
    
    algorithm = MotionAlgorithm()
    telemetry = TelemetryData(g_force_lateral=0.5, ...)
    position = algorithm.calculate(telemetry)
"""

import logging
import math
from dataclasses import dataclass
from typing import Optional, Union

from src.telemetry.packet_parser import TelemetryData
from src.drivers.moog_driver import Position6DOF

logger = logging.getLogger(__name__)


@dataclass
class MotionConfig:
    """
    Configuration for the motion algorithm.
    
    Scale factors control how much the platform moves in response to game forces.
    Lower values = subtler motion, higher values = more aggressive motion.
    """
    # Scale factors (adjust through INF-111 tuning)
    surge_scale: float = 0.05    # Longitudinal G-force → X translation
    sway_scale: float = 0.05     # Lateral G-force → Y translation
    heave_scale: float = 0.03    # Vertical G-force → Z translation
    roll_scale: float = 0.3      # Lateral G-force → Roll rotation
    pitch_scale: float = 0.3     # Longitudinal G-force → Pitch rotation
    yaw_scale: float = 0.1       # Yaw rate → Yaw rotation
    
    # Position limits
    max_translation: float = 0.1  # Max translation in meters (±100mm)
    max_rotation: float = 0.26    # Max rotation in radians (±15 degrees)
    
    # SMC specific (1-DOF)
    smc_stroke: float = 100.0     # Actuator stroke in mm
    smc_center: float = 50.0      # Center position in mm
    
    # Smoothing (low-pass filter)
    smoothing_factor: float = 0.3  # 0 = no smoothing, 1 = no change
    
    # Home position for MOOG
    home_z: float = -0.18  # MOOG home Z position


@dataclass 
class SMCPosition:
    """Position for the SMC 1-DOF actuator."""
    position_mm: float  # Position in millimeters (0-100)
    
    def clamp(self, min_val: float = 0.0, max_val: float = 100.0) -> 'SMCPosition':
        """Clamp position to valid range."""
        self.position_mm = max(min_val, min(max_val, self.position_mm))
        return self


class MotionAlgorithm:
    """
    Converts F1 telemetry data to actuator positions.
    
    The algorithm supports two output modes:
    1. SMC (1-DOF): Maps combined G-forces to a single linear position
    2. MOOG (6-DOF): Maps G-forces and orientation to full 6-DOF position
    
    Example:
        algo = MotionAlgorithm()
        
        # For MOOG
        position_6dof = algo.calculate_6dof(telemetry)
        
        # For SMC
        position_smc = algo.calculate_smc(telemetry)
    """
    
    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the motion algorithm.
        
        Args:
            config: Configuration dict. If None, uses defaults.
        """
        if config:
            self.config = MotionConfig(**config)
        else:
            self.config = MotionConfig()
        
        # Previous positions for smoothing
        self._prev_6dof: Optional[Position6DOF] = None
        self._prev_smc: Optional[SMCPosition] = None
    
    def calculate(self, telemetry: TelemetryData) -> Union[Position6DOF, SMCPosition]:
        """
        Calculate actuator position from telemetry (default: 6DOF).
        
        Args:
            telemetry: Parsed telemetry data from F1 game
            
        Returns:
            Position6DOF for MOOG platform
        """
        return self.calculate_6dof(telemetry)
    
    def calculate_6dof(self, telemetry: TelemetryData) -> Position6DOF:
        """
        Calculate 6-DOF position for MOOG platform.
        
        TODO [David]: Implement this method
        
        Args:
            telemetry: Parsed telemetry data
            
        Returns:
            Position6DOF with X, Y, Z, Roll, Pitch, Yaw
            
        Algorithm:
            1. Map G-forces to translations:
               - X (surge) = g_force_longitudinal * surge_scale
               - Y (sway) = g_force_lateral * sway_scale
               - Z (heave) = (g_force_vertical - 1.0) * heave_scale + home_z
               
            2. Map G-forces to rotations (tilt coordination):
               - Roll = g_force_lateral * roll_scale
               - Pitch = -g_force_longitudinal * pitch_scale (negative for correct feel)
               - Yaw = telemetry.yaw * yaw_scale
               
            3. Clamp values using _clamp_6dof()
            
            4. Apply smoothing using _smooth_6dof()
            
            5. Return Position6DOF
        """
        # TODO: Implement 6-DOF calculation
        raise NotImplementedError("INF-107: Implement calculate_6dof()")
    
    def calculate_smc(self, telemetry: TelemetryData) -> SMCPosition:
        """
        Calculate position for SMC 1-DOF actuator.
        
        TODO [David]: Implement this method
        
        Args:
            telemetry: Parsed telemetry data
            
        Returns:
            SMCPosition with position in mm
            
        Algorithm:
            For a single axis, combine G-forces into one motion:
            
            1. Calculate combined G-force influence:
               combined = (g_force_longitudinal * 0.6) + (g_force_lateral * 0.4)
               
            2. Map to position:
               position = center + (combined * scale * stroke / 2)
               Where:
               - center = 50mm (middle of stroke)
               - scale = configurable (start with 1.0)
               - stroke = 100mm
               
            3. Clamp to 0-100mm range
            
            4. Apply smoothing using _smooth_smc()
            
            5. Return SMCPosition
        """
        # TODO: Implement SMC calculation
        raise NotImplementedError("INF-107: Implement calculate_smc()")
    
    def _clamp_6dof(self, position: Position6DOF) -> Position6DOF:
        """
        Clamp 6-DOF position to safe limits.
        
        TODO [David]: Implement this method
        
        Args:
            position: Unclamped position
            
        Returns:
            Position with values clamped to max_translation and max_rotation
            
        Steps:
            1. Clamp X, Y to ±max_translation
            2. Clamp Z to (home_z - max_translation) to (home_z + max_translation)
            3. Clamp Roll, Pitch, Yaw to ±max_rotation
        """
        # TODO: Implement clamping
        raise NotImplementedError("INF-107: Implement _clamp_6dof()")
    
    def _smooth_6dof(self, position: Position6DOF) -> Position6DOF:
        """
        Apply low-pass filter smoothing to 6-DOF position.
        
        TODO [David]: Implement this method
        
        Args:
            position: New calculated position
            
        Returns:
            Smoothed position
            
        Algorithm (exponential moving average):
            smoothed = prev * smoothing_factor + new * (1 - smoothing_factor)
            
        Steps:
            1. If no previous position, return current position
            2. For each axis, calculate smoothed value
            3. Store result as new previous position
            4. Return smoothed position
        """
        # TODO: Implement smoothing
        raise NotImplementedError("INF-107: Implement _smooth_6dof()")
    
    def _smooth_smc(self, position: SMCPosition) -> SMCPosition:
        """
        Apply low-pass filter smoothing to SMC position.
        
        TODO [David]: Implement this method
        
        Same algorithm as _smooth_6dof but for single axis.
        """
        # TODO: Implement smoothing
        raise NotImplementedError("INF-107: Implement _smooth_smc()")
    
    def reset(self):
        """Reset smoothing state (call when restarting)."""
        self._prev_6dof = None
        self._prev_smc = None


# For standalone testing
if __name__ == "__main__":
    """
    Test the motion algorithm with sample data.
    
    Run: python -m src.motion.algorithm
    """
    logging.basicConfig(level=logging.DEBUG)
    
    print("Motion Algorithm Test")
    print("=" * 40)
    
    # Create sample telemetry data
    sample_telemetry = TelemetryData(
        g_force_lateral=0.5,      # Turning right
        g_force_longitudinal=-1.0, # Braking
        g_force_vertical=1.2,      # Slight bump
        yaw=0.1,
        pitch=0.05,
        roll=0.02
    )
    
    print(f"Input: {sample_telemetry}")
    
    algorithm = MotionAlgorithm()
    
    try:
        # Test 6-DOF calculation
        position_6dof = algorithm.calculate_6dof(sample_telemetry)
        print(f"6-DOF Output: {position_6dof}")
        
        # Test SMC calculation
        position_smc = algorithm.calculate_smc(sample_telemetry)
        print(f"SMC Output: {position_smc.position_mm}mm")
    except NotImplementedError as e:
        print(f"Not implemented: {e}")
