"""
Unit Tests for Safety Module - INF-125

Ticket: As a developer, I want unit tests for the safety module so that
        I can verify position limits and emergency stop work correctly.

Test Design Techniques Used:
    - Boundary value analysis (position limits)
    - State transition testing (E-stop states)
    - Decision table testing (clamp conditions)

Run: pytest tests/utils/test_safety.py -v
"""

import pytest
import time
from unittest.mock import Mock

# from src.utils.safety import SafetyLimiter, SafetyConfig, EmergencyStop, SafetyState


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def limiter():
    """Create a SafetyLimiter instance."""
    from src.utils.safety import SafetyLimiter
    return SafetyLimiter()


@pytest.fixture
def custom_config():
    """Create custom safety configuration."""
    from src.utils.safety import SafetyConfig
    return SafetyConfig(
        min_position_smc=10.0,
        max_position_smc=90.0,
        max_translation=0.15,
        max_rotation=0.25,
        emergency_stop_timeout=1.0  # Short timeout for testing
    )


@pytest.fixture(autouse=True)
def reset_emergency_stop():
    """Reset EmergencyStop state before each test."""
    from src.utils.safety import EmergencyStop
    EmergencyStop._active = False
    EmergencyStop._trigger_time = None
    EmergencyStop._callbacks.clear()
    yield
    # Cleanup after test
    EmergencyStop._active = False
    EmergencyStop._trigger_time = None
    EmergencyStop._callbacks.clear()


# =============================================================================
# SMC POSITION CLAMPING TESTS
# =============================================================================

class TestClampSMCPosition:
    """Tests for clamp_smc_position() method."""
    
    def test_value_within_limits_unchanged(self, limiter):
        """Test values within limits pass through unchanged."""
        result = limiter.clamp_smc_position(50.0)
        assert result == 50.0
    
    def test_value_below_min_clamped(self, limiter):
        """Test values below minimum are clamped to min."""
        result = limiter.clamp_smc_position(2.0)  # Below 5mm min
        assert result == 5.0
    
    def test_value_above_max_clamped(self, limiter):
        """Test values above maximum are clamped to max."""
        result = limiter.clamp_smc_position(98.0)  # Above 95mm max
        assert result == 95.0
    
    @pytest.mark.parametrize("input_val,expected", [
        (0.0, 5.0),       # Below min
        (5.0, 5.0),       # At min
        (5.1, 5.1),       # Just above min
        (50.0, 50.0),     # Center
        (94.9, 94.9),     # Just below max
        (95.0, 95.0),     # At max
        (100.0, 95.0),    # Above max
        (-10.0, 5.0),     # Negative
    ])
    def test_boundary_values(self, limiter, input_val, expected):
        """Test boundary value clamping."""
        result = limiter.clamp_smc_position(input_val)
        assert abs(result - expected) < 0.001
    
    def test_estop_returns_center(self, limiter):
        """Test E-stop active returns center position."""
        from src.utils.safety import EmergencyStop
        EmergencyStop.trigger("Test")
        result = limiter.clamp_smc_position(80.0)
        assert result == 50.0  # Center/home position


# =============================================================================
# MOOG POSITION CLAMPING TESTS
# =============================================================================

class TestClampMOOGPosition:
    """Tests for clamp_moog_position() method."""
    
    def test_values_within_limits_unchanged(self, limiter):
        """Test values within limits pass through unchanged."""
        result = limiter.clamp_moog_position(0.05, 0.05, -0.15, 0.1, 0.1, 0.05)
        assert result == (0.05, 0.05, -0.15, 0.1, 0.1, 0.05)
    
    def test_translations_clamped(self, limiter):
        """Test X, Y translations are clamped to ±max_translation."""
        result = limiter.clamp_moog_position(0.5, -0.5, -0.18, 0, 0, 0)
        assert abs(result[0]) <= 0.20  # X clamped
        assert abs(result[1]) <= 0.20  # Y clamped
    
    def test_heave_clamped(self, limiter):
        """Test Z (heave) is clamped to min_heave/max_heave."""
        result = limiter.clamp_moog_position(0, 0, 0.0, 0, 0, 0)  # Z too high
        assert result[2] <= -0.08  # Max heave
        result = limiter.clamp_moog_position(0, 0, -0.5, 0, 0, 0)  # Z too low
        assert result[2] >= -0.28  # Min heave
    
    def test_rotations_clamped(self, limiter):
        """Test roll, pitch, yaw are clamped to ±max_rotation."""
        result = limiter.clamp_moog_position(0, 0, -0.18, 0.5, 0.5, 0.5)
        assert abs(result[3]) <= 0.30  # Roll
        assert abs(result[4]) <= 0.30  # Pitch
        assert abs(result[5]) <= 0.30  # Yaw
    
    def test_estop_returns_home(self, limiter):
        """Test E-stop active returns home position."""
        from src.utils.safety import EmergencyStop
        EmergencyStop.trigger("Test")
        result = limiter.clamp_moog_position(0.1, 0.1, -0.1, 0.2, 0.2, 0.1)
        assert result == (0.0, 0.0, -0.18, 0.0, 0.0, 0.0)


# =============================================================================
# EMERGENCY STOP TESTS
# =============================================================================

class TestEmergencyStop:
    """Tests for EmergencyStop class."""
    
    def test_initial_state_inactive(self):
        """Test E-stop is inactive initially."""
        from src.utils.safety import EmergencyStop
        assert EmergencyStop.is_active() == False
    
    def test_trigger_activates(self):
        """Test trigger() activates E-stop."""
        from src.utils.safety import EmergencyStop
        EmergencyStop.trigger("Test trigger")
        assert EmergencyStop.is_active() == True
    
    def test_reset_too_soon_fails(self):
        """Test reset() fails if called too soon after trigger."""
        from src.utils.safety import EmergencyStop
        EmergencyStop.trigger("Test")
        result = EmergencyStop.reset()
        assert result == False
        assert EmergencyStop.is_active() == True
    
    def test_reset_after_timeout_succeeds(self):
        """Test reset() succeeds after timeout period."""
        from src.utils.safety import EmergencyStop, SafetyConfig
        # Use very short timeout for testing
        original_timeout = SafetyConfig.emergency_stop_timeout
        SafetyConfig.emergency_stop_timeout = 0.1
        
        EmergencyStop.trigger("Test")
        time.sleep(0.15)  # Wait for timeout
        result = EmergencyStop.reset()
        
        SafetyConfig.emergency_stop_timeout = original_timeout  # Restore
        
        assert result == True
        assert EmergencyStop.is_active() == False
    
    def test_callback_executed_on_trigger(self):
        """Test registered callbacks are executed on trigger."""
        from src.utils.safety import EmergencyStop
        callback_executed = []
        
        def my_callback():
            callback_executed.append(True)
        
        EmergencyStop.register_callback(my_callback)
        EmergencyStop.trigger("Test")
        
        assert len(callback_executed) == 1
    
    def test_multiple_callbacks_executed(self):
        """Test multiple callbacks are all executed."""
        from src.utils.safety import EmergencyStop
        results = []
        
        EmergencyStop.register_callback(lambda: results.append('a'))
        EmergencyStop.register_callback(lambda: results.append('b'))
        EmergencyStop.trigger("Test")
        
        assert 'a' in results
        assert 'b' in results


# =============================================================================
# SAFETY STATE TESTS
# =============================================================================

class TestSafetyState:
    """Tests for safety state property."""
    
    def test_normal_state_when_not_estopped(self, limiter):
        """Test state is NORMAL when E-stop not active."""
        from src.utils.safety import SafetyState
        assert limiter.state == SafetyState.NORMAL
    
    def test_estop_state_when_triggered(self, limiter):
        """Test state is EMERGENCY_STOP when triggered."""
        from src.utils.safety import EmergencyStop, SafetyState
        EmergencyStop.trigger("Test")
        assert limiter.state == SafetyState.EMERGENCY_STOP


# =============================================================================
# WARNING COUNT TESTS
# =============================================================================

class TestWarningCount:
    """Tests for warning count tracking."""
    
    def test_initial_warning_count_zero(self, limiter):
        """Test warning count starts at zero."""
        assert limiter.warning_count == 0
    
    def test_warning_count_increments_on_clamp(self, limiter):
        """Test warning count increments when value is clamped."""
        limiter.clamp_smc_position(200.0)  # Way over limit
        assert limiter.warning_count > 0


# =============================================================================
# HOME POSITION TESTS
# =============================================================================

class TestHomePositions:
    """Tests for home position getters."""

    def test_smc_home_position(self, limiter):
        """Test SMC home position is center (50mm)."""
        assert limiter.get_home_position_smc() == 50.0

    def test_moog_home_position(self, limiter):
        """Test MOOG home position is correct."""
        home = limiter.get_home_position_moog()
        assert home == (0.0, 0.0, -0.18, 0.0, 0.0, 0.0)


# =============================================================================
# SPEED LIMIT TESTS (TC-SAFE-008)
# =============================================================================

class TestSpeedLimits:
    """Tests for speed limit enforcement."""

    def test_smc_slow_speed_passes(self, limiter):
        """Test SMC speed within limits passes."""
        limiter.check_smc_speed(50.0)
        time.sleep(0.1)
        result = limiter.check_smc_speed(51.0)  # 10 mm/s
        assert result == True

    def test_smc_fast_speed_fails(self, limiter):
        """Test SMC speed exceeding limits fails."""
        limiter.check_smc_speed(50.0)
        time.sleep(0.01)
        result = limiter.check_smc_speed(90.0)  # 4000 mm/s (way too fast)
        assert result == False

    def test_moog_slow_speed_passes(self, limiter):
        """Test MOOG speed within limits passes."""
        limiter.check_moog_speed(0.0, 0.0, -0.18, 0.0, 0.0, 0.0)
        time.sleep(0.1)
        result = limiter.check_moog_speed(0.01, 0.0, -0.18, 0.0, 0.0, 0.0)  # 0.1 m/s
        assert result == True

    def test_moog_fast_speed_fails(self, limiter):
        """Test MOOG speed exceeding limits fails."""
        limiter.check_moog_speed(0.0, 0.0, -0.18, 0.0, 0.0, 0.0)
        time.sleep(0.01)
        result = limiter.check_moog_speed(0.5, 0.0, -0.18, 0.0, 0.0, 0.0)  # 50 m/s (way too fast)
        assert result == False
