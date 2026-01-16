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
from src.utils.safety import SafetyModule, EmergencyStop, SafetyState
from src.shared.types import Position6DOF


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def safety():
    """Create a SafetyModule instance."""
    return SafetyModule()


@pytest.fixture(autouse=True)
def reset_emergency_stop():
    """Reset EmergencyStop state before each test."""
    EmergencyStop._active = False
    EmergencyStop._trigger_time = None
    EmergencyStop._callbacks.clear()
    yield
    # Cleanup after test
    EmergencyStop._active = False
    EmergencyStop._trigger_time = None
    EmergencyStop._callbacks.clear()


# =============================================================================
# SMC POSITION CLAMPING TESTS - TC-SAFE-001
# =============================================================================

class TestClampSMCPosition:
    """Tests for clamp_smc_position() method."""

    def test_value_within_limits_unchanged(self, safety):
        """TC-SAFE-001: Test values within limits pass through unchanged."""
        result = safety.clamp_smc_position(450.0)
        assert result == 450.0
        assert safety.warning_count == 0

    def test_value_below_min_clamped(self, safety):
        """TC-SAFE-001: Test values below minimum are clamped to min (5mm)."""
        result = safety.clamp_smc_position(2.0)
        assert result == 5.0
        assert safety.warning_count == 1

    def test_value_above_max_clamped(self, safety):
        """TC-SAFE-001: Test values above maximum are clamped to max (895mm)."""
        result = safety.clamp_smc_position(900.0)
        assert result == 895.0
        assert safety.warning_count == 1

    @pytest.mark.parametrize("input_val,expected", [
        (0.0, 5.0),       # Below min
        (5.0, 5.0),       # At min
        (5.1, 5.1),       # Just above min
        (450.0, 450.0),   # Center
        (894.9, 894.9),   # Just below max
        (895.0, 895.0),   # At max
        (1000.0, 895.0),  # Above max
        (-10.0, 5.0),     # Negative
    ])
    def test_boundary_values(self, safety, input_val, expected):
        """TC-SAFE-001: Test boundary value clamping."""
        result = safety.clamp_smc_position(input_val)
        assert abs(result - expected) < 0.001


# =============================================================================
# MOOG POSITION CLAMPING TESTS - TC-SAFE-002
# =============================================================================

class TestClampMOOGPosition:
    """Tests for clamp_moog_position() method."""

    def test_values_within_limits_unchanged(self, safety):
        """TC-SAFE-002: Test values within limits pass through unchanged."""
        pos = Position6DOF(x=0.05, y=0.05, z=-0.1, roll=0.1, pitch=0.1, yaw=0.05)
        result = safety.clamp_moog_position(pos)
        assert result.x == 0.05
        assert result.y == 0.05
        assert result.z == -0.1
        assert result.roll == 0.1
        assert result.pitch == 0.1
        assert result.yaw == 0.05
        assert safety.warning_count == 0

    def test_surge_clamped(self, safety):
        """TC-SAFE-002: Test surge (x) is clamped to -0.241/+0.259."""
        pos_low = Position6DOF(x=-0.5)
        result_low = safety.clamp_moog_position(pos_low)
        assert result_low.x == -0.241

        pos_high = Position6DOF(x=0.5)
        result_high = safety.clamp_moog_position(pos_high)
        assert result_high.x == 0.259

    def test_sway_clamped(self, safety):
        """TC-SAFE-002: Test sway (y) is clamped to ±0.259."""
        pos_low = Position6DOF(y=-0.5)
        result_low = safety.clamp_moog_position(pos_low)
        assert result_low.y == -0.259

        pos_high = Position6DOF(y=0.5)
        result_high = safety.clamp_moog_position(pos_high)
        assert result_high.y == 0.259

    def test_heave_clamped(self, safety):
        """TC-SAFE-002: Test heave (z) is clamped to ±0.178."""
        pos_low = Position6DOF(z=-0.5)
        result_low = safety.clamp_moog_position(pos_low)
        assert result_low.z == -0.178

        pos_high = Position6DOF(z=0.5)
        result_high = safety.clamp_moog_position(pos_high)
        assert result_high.z == 0.178

    def test_roll_clamped(self, safety):
        """TC-SAFE-002: Test roll is clamped to ±0.367 rad."""
        pos_low = Position6DOF(roll=-0.5)
        result_low = safety.clamp_moog_position(pos_low)
        assert result_low.roll == -0.367

        pos_high = Position6DOF(roll=0.5)
        result_high = safety.clamp_moog_position(pos_high)
        assert result_high.roll == 0.367

    def test_pitch_clamped(self, safety):
        """TC-SAFE-002: Test pitch is clamped to ±0.384 rad."""
        pos_low = Position6DOF(pitch=-0.5)
        result_low = safety.clamp_moog_position(pos_low)
        assert result_low.pitch == -0.384

        pos_high = Position6DOF(pitch=0.5)
        result_high = safety.clamp_moog_position(pos_high)
        assert result_high.pitch == 0.384

    def test_yaw_clamped(self, safety):
        """TC-SAFE-002: Test yaw is clamped to ±0.384 rad."""
        pos_low = Position6DOF(yaw=-0.5)
        result_low = safety.clamp_moog_position(pos_low)
        assert result_low.yaw == -0.384

        pos_high = Position6DOF(yaw=0.5)
        result_high = safety.clamp_moog_position(pos_high)
        assert result_high.yaw == 0.384


# =============================================================================
# EMERGENCY STOP TESTS - TC-SAFE-003, TC-SAFE-004, TC-SAFE-005
# =============================================================================

class TestEmergencyStopModule:
    """Tests for SafetyModule e-stop methods."""

    def test_initial_state_not_estopped(self, safety):
        """TC-SAFE-003: Test E-stop is inactive initially."""
        assert safety.is_estopped() == False

    def test_trigger_estop_activates(self, safety):
        """TC-SAFE-003: Test trigger_estop() activates E-stop."""
        safety.trigger_estop("Test trigger")
        assert safety.is_estopped() == True

    def test_reset_too_soon_fails(self, safety):
        """TC-SAFE-004: Test reset() fails if called too soon after trigger."""
        safety.trigger_estop("Test")
        result = safety.reset_estop()
        assert result == False
        assert safety.is_estopped() == True

    def test_reset_after_timeout_succeeds(self, safety):
        """TC-SAFE-004: Test reset() succeeds after 2-second timeout."""
        safety.trigger_estop("Test")
        time.sleep(2.1)  # Wait for timeout
        result = safety.reset_estop()
        assert result == True
        assert safety.is_estopped() == False

    def test_callback_executed_on_trigger(self, safety):
        """TC-SAFE-005: Test registered callbacks are executed on trigger."""
        callback_executed = []

        def my_callback():
            callback_executed.append(True)

        safety.register_estop_callback(my_callback)
        safety.trigger_estop("Test")

        assert len(callback_executed) == 1

    def test_multiple_callbacks_executed(self, safety):
        """TC-SAFE-005: Test multiple callbacks are all executed."""
        results = []

        safety.register_estop_callback(lambda: results.append('a'))
        safety.register_estop_callback(lambda: results.append('b'))
        safety.trigger_estop("Test")

        assert 'a' in results
        assert 'b' in results


class TestEmergencyStopGlobal:
    """Tests for global EmergencyStop class."""

    def test_initial_state_inactive(self):
        """TC-SAFE-003: Test E-stop is inactive initially."""
        assert EmergencyStop.is_active() == False

    def test_trigger_activates(self):
        """TC-SAFE-003: Test trigger() activates E-stop."""
        EmergencyStop.trigger("Test trigger")
        assert EmergencyStop.is_active() == True

    def test_reset_too_soon_fails(self):
        """TC-SAFE-004: Test reset() fails if called too soon."""
        EmergencyStop.trigger("Test")
        result = EmergencyStop.reset()
        assert result == False
        assert EmergencyStop.is_active() == True

    def test_reset_after_timeout_succeeds(self):
        """TC-SAFE-004: Test reset() succeeds after timeout."""
        EmergencyStop.trigger("Test")
        time.sleep(2.1)
        result = EmergencyStop.reset()
        assert result == True
        assert EmergencyStop.is_active() == False

    def test_callback_executed_on_trigger(self):
        """TC-SAFE-005: Test registered callbacks are executed."""
        callback_executed = []

        def my_callback():
            callback_executed.append(True)

        EmergencyStop.register_callback(my_callback)
        EmergencyStop.trigger("Test")

        assert len(callback_executed) == 1

    def test_multiple_callbacks_executed(self):
        """TC-SAFE-005: Test multiple callbacks are all executed."""
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

    def test_normal_state_when_not_estopped(self, safety):
        """Test state is NORMAL when E-stop not active and no warnings."""
        assert safety.state == SafetyState.NORMAL

    def test_warning_state_after_clamp(self, safety):
        """Test state is WARNING after clamping occurs."""
        safety.clamp_smc_position(1000.0)  # Trigger clamp
        assert safety.state == SafetyState.WARNING

    def test_estop_state_when_triggered(self, safety):
        """Test state is EMERGENCY_STOP when triggered."""
        safety.trigger_estop("Test")
        assert safety.state == SafetyState.EMERGENCY_STOP


# =============================================================================
# WARNING COUNT TESTS
# =============================================================================

class TestWarningCount:
    """Tests for warning count tracking."""

    def test_initial_warning_count_zero(self, safety):
        """Test warning count starts at zero."""
        assert safety.warning_count == 0

    def test_warning_count_increments_on_smc_clamp(self, safety):
        """Test warning count increments when SMC value is clamped."""
        safety.clamp_smc_position(1000.0)  # Way over limit
        assert safety.warning_count == 1
        safety.clamp_smc_position(-10.0)  # Below limit
        assert safety.warning_count == 2

    def test_warning_count_increments_on_moog_clamp(self, safety):
        """Test warning count increments when MOOG value is clamped."""
        pos = Position6DOF(x=1.0, y=1.0, z=1.0, roll=1.0, pitch=1.0, yaw=1.0)
        safety.clamp_moog_position(pos)
        # All 6 axes out of bounds = 6 warnings
        assert safety.warning_count == 6


# =============================================================================
# SPEED LIMITING TESTS
# =============================================================================

class TestSpeedLimiting:
    """Tests for limit_speed() method."""

    def test_speed_within_limit_unchanged(self, safety):
        """Test position change within speed limit passes unchanged."""
        current = 100.0
        target = 150.0  # 50mm change
        dt = 0.2  # 0.2 seconds = 250 mm/s (within 500 mm/s limit)
        result = safety.limit_speed(current, target, dt)
        assert result == target
        assert safety.warning_count == 0

    def test_speed_above_limit_clamped(self, safety):
        """Test position change above speed limit is clamped."""
        current = 100.0
        target = 300.0  # 200mm change
        dt = 0.2  # 0.2 seconds = 1000 mm/s (exceeds 500 mm/s limit)
        result = safety.limit_speed(current, target, dt)
        # Max change = 500 mm/s * 0.2s = 100mm
        expected = current + 100.0
        assert result == expected
        assert safety.warning_count == 1

    def test_speed_limit_negative_direction(self, safety):
        """Test speed limiting works in negative direction."""
        current = 300.0
        target = 100.0  # -200mm change
        dt = 0.2  # Would be 1000 mm/s
        result = safety.limit_speed(current, target, dt)
        # Max change = -100mm
        expected = current - 100.0
        assert result == expected


# =============================================================================
# BACKWARD COMPATIBILITY TESTS
# =============================================================================

class TestBackwardCompatibility:
    """Test that SafetyLimiter alias works."""

    def test_safety_limiter_alias_exists(self):
        """Test SafetyLimiter alias is available."""
        from src.utils.safety import SafetyLimiter
        limiter = SafetyLimiter()
        assert limiter is not None
        assert hasattr(limiter, 'clamp_smc_position')
        assert hasattr(limiter, 'clamp_moog_position')
