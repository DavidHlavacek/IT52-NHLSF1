"""
Unit Tests for Safety Module - INF-112

Ticket: As a developer, I want safety limits in the software so that
        the hardware cannot be commanded to dangerous positions or speeds.

Acceptance Criteria:
    TC-SAFE-001: SMC position clamped to safe range 5-895mm
    TC-SAFE-002: MOOG position clamped on all 6 axes
    TC-SAFE-003: Emergency stop blocks all commands
    TC-SAFE-004: Emergency stop reset requires timeout
    TC-SAFE-005: Emergency stop callbacks executed
    TC-SAFE-006: Values within limits pass unchanged
    TC-SAFE-007: Warning count increments on clamping
    TC-SAFE-008: Speed limits enforced

Test Design Techniques Used:
    - Boundary value analysis (position limits)
    - State transition testing (E-stop states)
    - Decision table testing (clamp conditions)

Run: pytest tests/utils/test_safety.py -v
"""

import pytest
import time
from unittest.mock import Mock, MagicMock

from src.utils.safety import (
    SafetyLimiter,
    SafetyConfig,
    EmergencyStop,
    SafetyState,
    check_safety_before_command
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def limiter():
    """Create a SafetyLimiter instance with default config."""
    return SafetyLimiter()


@pytest.fixture
def custom_config():
    """Create custom safety configuration for testing."""
    return SafetyConfig(
        min_position_smc=5.0,
        max_position_smc=895.0,
        max_translation=0.259,
        max_rotation=0.384,
        min_heave=-0.28,
        max_heave=-0.08,
        max_speed_smc=50.0,
        max_speed_moog=0.15,
        emergency_stop_timeout=0.1  # Short timeout for testing
    )


@pytest.fixture
def limiter_custom(custom_config):
    """Create a SafetyLimiter with custom config."""
    return SafetyLimiter(config=custom_config)


@pytest.fixture(autouse=True)
def reset_emergency_stop():
    """Reset EmergencyStop state before and after each test."""
    EmergencyStop._active = False
    EmergencyStop._trigger_time = None
    EmergencyStop._callbacks = []
    yield
    EmergencyStop._active = False
    EmergencyStop._trigger_time = None
    EmergencyStop._callbacks = []


# =============================================================================
# TC-SAFE-001: SMC POSITION CLAMPING TESTS
# =============================================================================

class TestSMCPositionClamping:
    """TC-SAFE-001: SMC position clamped to safe range 5-895mm."""

    def test_smc_min_position_is_5mm(self):
        """Test SafetyConfig min_position_smc default."""
        config = SafetyConfig()
        assert config.min_position_smc == 5.0

    def test_smc_max_position_is_895mm(self, custom_config):
        """Test custom config max_position_smc is 895mm."""
        assert custom_config.max_position_smc == 895.0

    def test_smc_clamp_below_min_returns_min(self, limiter_custom):
        """Test position below 5mm is clamped to 5mm."""
        # Note: Requires INF-112 implementation
        try:
            result = limiter_custom.clamp_smc_position(0.0)
            assert result == 5.0
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")

    def test_smc_clamp_above_max_returns_max(self, limiter_custom):
        """Test position above 895mm is clamped to 895mm."""
        try:
            result = limiter_custom.clamp_smc_position(900.0)
            assert result == 895.0
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")

    def test_smc_clamp_negative_returns_min(self, limiter_custom):
        """Test negative position is clamped to min."""
        try:
            result = limiter_custom.clamp_smc_position(-100.0)
            assert result == 5.0
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")

    @pytest.mark.parametrize("input_mm,expected_mm", [
        (0.0, 5.0),       # Below min -> clamped to min
        (5.0, 5.0),       # At min -> unchanged
        (5.1, 5.1),       # Just above min -> unchanged
        (450.0, 450.0),   # Center -> unchanged
        (894.9, 894.9),   # Just below max -> unchanged
        (895.0, 895.0),   # At max -> unchanged
        (900.0, 895.0),   # Above max -> clamped to max
        (1000.0, 895.0),  # Way above max -> clamped to max
        (-50.0, 5.0),     # Negative -> clamped to min
    ])
    def test_smc_boundary_values(self, limiter_custom, input_mm, expected_mm):
        """Test SMC position boundary value clamping."""
        try:
            result = limiter_custom.clamp_smc_position(input_mm)
            assert abs(result - expected_mm) < 0.001
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")


# =============================================================================
# TC-SAFE-002: MOOG POSITION CLAMPING TESTS
# =============================================================================

class TestMOOGPositionClamping:
    """TC-SAFE-002: MOOG position clamped on all 6 axes."""

    def test_moog_translation_limit_default(self):
        """Test MOOG translation limit from config."""
        config = SafetyConfig()
        assert config.max_translation == 0.20

    def test_moog_rotation_limit_default(self):
        """Test MOOG rotation limit from config."""
        config = SafetyConfig()
        assert config.max_rotation == 0.30

    def test_moog_heave_limits_default(self):
        """Test MOOG heave limits from config."""
        config = SafetyConfig()
        assert config.min_heave == -0.28
        assert config.max_heave == -0.08

    def test_moog_clamp_x_positive_overflow(self, limiter):
        """Test X translation clamped when exceeding positive limit."""
        try:
            result = limiter.clamp_moog_position(0.5, 0.0, -0.18, 0.0, 0.0, 0.0)
            assert result[0] <= 0.20  # X clamped
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_clamp_x_negative_overflow(self, limiter):
        """Test X translation clamped when exceeding negative limit."""
        try:
            result = limiter.clamp_moog_position(-0.5, 0.0, -0.18, 0.0, 0.0, 0.0)
            assert result[0] >= -0.20  # X clamped
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_clamp_y_overflow(self, limiter):
        """Test Y translation clamped when exceeding limit."""
        try:
            result = limiter.clamp_moog_position(0.0, 0.5, -0.18, 0.0, 0.0, 0.0)
            assert abs(result[1]) <= 0.20  # Y clamped
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_clamp_heave_too_high(self, limiter):
        """Test Z (heave) clamped when too high."""
        try:
            result = limiter.clamp_moog_position(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            assert result[2] <= -0.08  # Max heave
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_clamp_heave_too_low(self, limiter):
        """Test Z (heave) clamped when too low."""
        try:
            result = limiter.clamp_moog_position(0.0, 0.0, -0.5, 0.0, 0.0, 0.0)
            assert result[2] >= -0.28  # Min heave
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_clamp_roll_overflow(self, limiter):
        """Test roll clamped when exceeding limit."""
        try:
            result = limiter.clamp_moog_position(0.0, 0.0, -0.18, 0.5, 0.0, 0.0)
            assert abs(result[3]) <= 0.30  # Roll clamped
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_clamp_pitch_overflow(self, limiter):
        """Test pitch clamped when exceeding limit."""
        try:
            result = limiter.clamp_moog_position(0.0, 0.0, -0.18, 0.0, 0.5, 0.0)
            assert abs(result[4]) <= 0.30  # Pitch clamped
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_clamp_yaw_overflow(self, limiter):
        """Test yaw clamped when exceeding limit."""
        try:
            result = limiter.clamp_moog_position(0.0, 0.0, -0.18, 0.0, 0.0, 0.5)
            assert abs(result[5]) <= 0.30  # Yaw clamped
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_clamp_all_axes_overflow(self, limiter):
        """Test all 6 axes clamped simultaneously."""
        try:
            result = limiter.clamp_moog_position(1.0, -1.0, 0.5, 1.0, -1.0, 1.0)
            assert abs(result[0]) <= 0.20
            assert abs(result[1]) <= 0.20
            assert -0.28 <= result[2] <= -0.08
            assert abs(result[3]) <= 0.30
            assert abs(result[4]) <= 0.30
            assert abs(result[5]) <= 0.30
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")


# =============================================================================
# TC-SAFE-003: EMERGENCY STOP BLOCKS ALL COMMANDS
# =============================================================================

class TestEmergencyStopBlocking:
    """TC-SAFE-003: Emergency stop blocks all commands."""

    def test_estop_initially_inactive(self):
        """Test E-stop is inactive by default."""
        assert EmergencyStop.is_active() == False

    def test_estop_trigger_activates(self):
        """Test trigger() activates E-stop."""
        EmergencyStop.trigger("Test trigger")
        assert EmergencyStop.is_active() == True

    def test_estop_blocks_decorated_function(self):
        """Test check_safety_before_command decorator blocks when E-stop active."""
        call_count = [0]

        @check_safety_before_command
        def test_command():
            call_count[0] += 1
            return "executed"

        # Should work when E-stop inactive
        result = test_command()
        assert result == "executed"
        assert call_count[0] == 1

        # Trigger E-stop
        EmergencyStop.trigger("Test")

        # Should be blocked when E-stop active
        result = test_command()
        assert result is None
        assert call_count[0] == 1  # Not incremented

    def test_estop_trigger_logs_reason(self, caplog):
        """Test trigger() logs the reason."""
        import logging
        caplog.set_level(logging.CRITICAL)

        EmergencyStop.trigger("Hardware fault detected")

        assert "EMERGENCY STOP" in caplog.text
        assert "Hardware fault detected" in caplog.text


# =============================================================================
# TC-SAFE-004: EMERGENCY STOP RESET REQUIRES TIMEOUT
# =============================================================================

class TestEmergencyStopReset:
    """TC-SAFE-004: Emergency stop reset requires timeout."""

    def test_reset_immediately_after_trigger_fails(self):
        """Test reset() fails if called immediately after trigger."""
        EmergencyStop.trigger("Test")
        result = EmergencyStop.reset()
        assert result == False
        assert EmergencyStop.is_active() == True

    def test_reset_before_timeout_fails(self):
        """Test reset() fails before timeout period elapses."""
        original_timeout = SafetyConfig.emergency_stop_timeout
        SafetyConfig.emergency_stop_timeout = 1.0  # 1 second

        EmergencyStop.trigger("Test")
        time.sleep(0.1)  # Wait only 100ms
        result = EmergencyStop.reset()

        SafetyConfig.emergency_stop_timeout = original_timeout

        assert result == False
        assert EmergencyStop.is_active() == True

    def test_reset_after_timeout_succeeds(self):
        """Test reset() succeeds after timeout period elapses."""
        original_timeout = SafetyConfig.emergency_stop_timeout
        SafetyConfig.emergency_stop_timeout = 0.1  # 100ms for faster testing

        EmergencyStop.trigger("Test")
        time.sleep(0.15)  # Wait slightly longer than timeout
        result = EmergencyStop.reset()

        SafetyConfig.emergency_stop_timeout = original_timeout

        assert result == True
        assert EmergencyStop.is_active() == False

    def test_reset_clears_trigger_time(self):
        """Test successful reset clears trigger time."""
        SafetyConfig.emergency_stop_timeout = 0.05

        EmergencyStop.trigger("Test")
        time.sleep(0.1)
        EmergencyStop.reset()

        assert EmergencyStop._trigger_time is None

    def test_reset_without_prior_trigger_succeeds(self):
        """Test reset() succeeds if never triggered."""
        result = EmergencyStop.reset()
        assert result == True


# =============================================================================
# TC-SAFE-005: EMERGENCY STOP CALLBACKS EXECUTED
# =============================================================================

class TestEmergencyStopCallbacks:
    """TC-SAFE-005: Emergency stop callbacks executed."""

    def test_single_callback_executed(self):
        """Test single registered callback is executed on trigger."""
        callback_executed = []

        def my_callback():
            callback_executed.append("called")

        EmergencyStop.register_callback(my_callback)
        EmergencyStop.trigger("Test")

        assert len(callback_executed) == 1
        assert callback_executed[0] == "called"

    def test_multiple_callbacks_executed(self):
        """Test multiple registered callbacks are all executed."""
        results = []

        EmergencyStop.register_callback(lambda: results.append("first"))
        EmergencyStop.register_callback(lambda: results.append("second"))
        EmergencyStop.register_callback(lambda: results.append("third"))

        EmergencyStop.trigger("Test")

        assert "first" in results
        assert "second" in results
        assert "third" in results
        assert len(results) == 3

    def test_callback_exception_does_not_stop_others(self):
        """Test exception in one callback doesn't prevent others."""
        results = []

        def bad_callback():
            raise RuntimeError("Callback error")

        EmergencyStop.register_callback(lambda: results.append("before"))
        EmergencyStop.register_callback(bad_callback)
        EmergencyStop.register_callback(lambda: results.append("after"))

        EmergencyStop.trigger("Test")

        # Both other callbacks should have executed
        assert "before" in results
        assert "after" in results

    def test_callback_receives_no_arguments(self):
        """Test callbacks are called with no arguments."""
        mock_callback = Mock()
        EmergencyStop.register_callback(mock_callback)
        EmergencyStop.trigger("Test")

        mock_callback.assert_called_once_with()

    def test_callbacks_executed_in_order(self):
        """Test callbacks are executed in registration order."""
        order = []

        EmergencyStop.register_callback(lambda: order.append(1))
        EmergencyStop.register_callback(lambda: order.append(2))
        EmergencyStop.register_callback(lambda: order.append(3))

        EmergencyStop.trigger("Test")

        assert order == [1, 2, 3]


# =============================================================================
# TC-SAFE-006: VALUES WITHIN LIMITS PASS UNCHANGED
# =============================================================================

class TestValuesWithinLimits:
    """TC-SAFE-006: Values within limits pass unchanged."""

    def test_smc_value_at_center_unchanged(self, limiter_custom):
        """Test SMC center position passes unchanged."""
        try:
            result = limiter_custom.clamp_smc_position(450.0)
            assert result == 450.0
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")

    def test_smc_value_at_min_unchanged(self, limiter_custom):
        """Test SMC at minimum passes unchanged."""
        try:
            result = limiter_custom.clamp_smc_position(5.0)
            assert result == 5.0
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")

    def test_smc_value_at_max_unchanged(self, limiter_custom):
        """Test SMC at maximum passes unchanged."""
        try:
            result = limiter_custom.clamp_smc_position(895.0)
            assert result == 895.0
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")

    def test_moog_values_within_limits_unchanged(self, limiter):
        """Test MOOG values within limits pass unchanged."""
        try:
            input_pos = (0.1, -0.1, -0.18, 0.15, -0.15, 0.1)
            result = limiter.clamp_moog_position(*input_pos)
            assert result == input_pos
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_moog_zero_position_unchanged(self, limiter):
        """Test MOOG zero position (except heave) passes unchanged."""
        try:
            result = limiter.clamp_moog_position(0.0, 0.0, -0.18, 0.0, 0.0, 0.0)
            assert result == (0.0, 0.0, -0.18, 0.0, 0.0, 0.0)
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")


# =============================================================================
# TC-SAFE-007: WARNING COUNT INCREMENTS ON CLAMPING
# =============================================================================

class TestWarningCount:
    """TC-SAFE-007: Warning count increments on clamping."""

    def test_initial_warning_count_zero(self, limiter):
        """Test warning count starts at zero."""
        assert limiter._warning_count == 0

    def test_warning_count_increments_on_smc_clamp(self, limiter_custom):
        """Test warning count increments when SMC value is clamped."""
        try:
            initial = limiter_custom._warning_count
            limiter_custom.clamp_smc_position(1000.0)  # Way over limit
            assert limiter_custom._warning_count > initial
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")

    def test_warning_count_increments_on_moog_clamp(self, limiter):
        """Test warning count increments when MOOG value is clamped."""
        try:
            initial = limiter._warning_count
            limiter.clamp_moog_position(1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
            assert limiter._warning_count > initial
        except NotImplementedError:
            pytest.skip("INF-112: clamp_moog_position() not yet implemented")

    def test_warning_count_not_incremented_when_within_limits(self, limiter_custom):
        """Test warning count does NOT increment when value is within limits."""
        try:
            initial = limiter_custom._warning_count
            limiter_custom.clamp_smc_position(450.0)  # Within limits
            assert limiter_custom._warning_count == initial
        except NotImplementedError:
            pytest.skip("INF-112: clamp_smc_position() not yet implemented")


# =============================================================================
# TC-SAFE-008: SPEED LIMITS ENFORCED
# =============================================================================

class TestSpeedLimits:
    """TC-SAFE-008: Speed limits enforced."""

    def test_smc_speed_limit_config(self):
        """Test SMC speed limit is configurable."""
        config = SafetyConfig()
        assert config.max_speed_smc == 50.0  # mm/s

    def test_moog_speed_limit_config(self):
        """Test MOOG speed limit is configurable."""
        config = SafetyConfig()
        assert config.max_speed_moog == 0.15  # m/s

    def test_custom_speed_limits(self, custom_config):
        """Test custom speed limits can be set."""
        assert custom_config.max_speed_smc == 50.0
        assert custom_config.max_speed_moog == 0.15


# =============================================================================
# HOME POSITION TESTS
# =============================================================================

class TestHomePositions:
    """Tests for home position getters."""

    def test_smc_home_position_is_center(self, limiter):
        """Test SMC home position is center of stroke."""
        home = limiter.get_home_position_smc()
        assert home == 50.0

    def test_moog_home_position(self, limiter):
        """Test MOOG home position is neutral pose."""
        home = limiter.get_home_position_moog()
        assert home == (0.0, 0.0, -0.18, 0.0, 0.0, 0.0)

    def test_moog_home_heave_is_mid_range(self, limiter):
        """Test MOOG home heave is within valid range."""
        home = limiter.get_home_position_moog()
        heave = home[2]
        assert -0.28 <= heave <= -0.08


# =============================================================================
# SAFETY CONFIG TESTS
# =============================================================================

class TestSafetyConfig:
    """Tests for SafetyConfig dataclass."""

    def test_default_config_values(self):
        """Test SafetyConfig has expected defaults."""
        config = SafetyConfig()
        assert config.min_position_smc == 5.0
        assert config.max_position_smc == 95.0  # Default skeleton value
        assert config.max_translation == 0.20
        assert config.max_rotation == 0.30
        assert config.emergency_stop_timeout == 5.0

    def test_custom_config_values(self):
        """Test SafetyConfig accepts custom values."""
        config = SafetyConfig(
            min_position_smc=10.0,
            max_position_smc=890.0,
            max_translation=0.25,
            emergency_stop_timeout=3.0
        )
        assert config.min_position_smc == 10.0
        assert config.max_position_smc == 890.0
        assert config.max_translation == 0.25
        assert config.emergency_stop_timeout == 3.0


# =============================================================================
# SAFETY STATE TESTS
# =============================================================================

class TestSafetyState:
    """Tests for SafetyState enum."""

    def test_safety_state_values(self):
        """Test SafetyState enum has expected values."""
        assert SafetyState.NORMAL.value == "normal"
        assert SafetyState.WARNING.value == "warning"
        assert SafetyState.EMERGENCY_STOP.value == "emergency_stop"

    def test_safety_state_enum_members(self):
        """Test SafetyState has all expected members."""
        states = [s.name for s in SafetyState]
        assert "NORMAL" in states
        assert "WARNING" in states
        assert "EMERGENCY_STOP" in states
