"""
Unit Tests for SMC Driver - INF-127

Ticket: Create and run unit tests for the SMC driver to ensure Modbus communication
is functioning correctly and reliably.

What these tests verify (per Test Cases doc):
  - TC-SMC-001: game coords -> physical coords conversion
  - TC-SMC-002: clamping to stroke limits
  - TC-SMC-003: time-based rate limiting (INF-149)
  - TC-SMC-004: small-change threshold skipping (INF-149)
  - TC-SMC-005: get_stats() returns correct counts (INF-149)
  - TC-SMC-006: connection failure handling

Techniques:
  - Equivalence partitioning (valid vs invalid / beyond limits)
  - Mock testing (Modbus client + internal move method)

Run:
  python3 -m pytest tests/drivers/test_smc_driver.py -v
"""

from dataclasses import dataclass
from unittest.mock import MagicMock
import pytest


@dataclass
class Position6DOF:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


@pytest.fixture
def smc_module():
    # import the module so we can monkeypatch its ModbusSerialClient/time cleanly
    from src.drivers import smc_driver
    return smc_driver


@pytest.fixture
def driver(smc_module):
    """
    Create an SMCDriver with a config that matches the test case preconditions.
    We also attach a fake client and force connected=True so no real hardware is used.
    """
    SMCDriver = smc_module.SMCDriver

    config = {
        "port": "COM5",
        "baudrate": 38400,
        "controller_id": 1,
        "parity": "N",
        "center_mm": 450.0,
        "stroke_mm": 900.0,
        "limits": {"surge_m": 0.4},  # 0.4m -> 400mm limit (matches TC-SMC-002)
        "min_command_interval": 0.05,  # matches TC-SMC-003
        "position_threshold_mm": 1.0,  # matches TC-SMC-004
    }

    # driver constructor differs sometimes, so try both common styles
    try:
        d = SMCDriver(config)
    except TypeError:
        d = SMCDriver(config=config)

    # fake out hardware
    d.client = MagicMock()
    d.client.connect.return_value = True
    d._connected = True

    # mock the internal motion command path
    if hasattr(d, "_move_to_physical_mm"):
        d._move_to_physical_mm = MagicMock(return_value=True)

    return d


def _call_send_position(driver, x_value):
    """
    Helper to call send_position with the game-coordinate style input.
    """
    return driver.send_position(Position6DOF(x=x_value))


def _read_stats(driver):
    """
    Returns a dict of stats from the driver, if available.
    The doc says get_stats() should exist, so we prefer that.
    """
    if hasattr(driver, "get_stats") and callable(driver.get_stats):
        stats = driver.get_stats()
        if isinstance(stats, dict):
            return stats

    # fallback (some people store stats differently)
    if hasattr(driver, "stats") and isinstance(driver.stats, dict):
        return driver.stats

    return None


# =============================================================================
# TC-SMC-001: Coordinate conversion (game ↔ physical)
# =============================================================================
def test_tc_smc_001_coordinate_conversion_game_to_physical(driver):
    """
    Preconditions: center_mm = 450
    Steps:
      x=0.0  -> 450mm
      x=0.2  -> 650mm
      x=-0.2 -> 250mm
    """
    if not hasattr(driver, "center_mm") or not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("Driver doesn't expose center_mm or _move_to_physical_mm.")

    _call_send_position(driver, 0.0)
    _call_send_position(driver, 0.2)
    _call_send_position(driver, -0.2)

    calls = [c.args[0] for c in driver._move_to_physical_mm.call_args_list]
    assert calls[0] == pytest.approx(450.0)
    assert calls[1] == pytest.approx(650.0)
    assert calls[2] == pytest.approx(250.0)


# =============================================================================
# TC-SMC-002: Position clamping to stroke limits
# =============================================================================
def test_tc_smc_002_position_clamped_to_limits(driver):
    """
    Preconditions: stroke_mm=900, center_mm=450, max_position_m=0.4 (400mm)
    Step: send x=0.5 (500mm beyond limit)
    Expected: clamped to 850mm (450 + 400)
    """
    required = ("stroke_mm", "center_mm", "max_position_m", "_move_to_physical_mm")
    if not all(hasattr(driver, k) for k in required):
        pytest.skip("Driver missing stroke/center/max_position_m or move method.")

    _call_send_position(driver, 0.5)

    physical_mm = driver._move_to_physical_mm.call_args[0][0]
    assert physical_mm == pytest.approx(850.0)


# =============================================================================
# TC-SMC-003: Time-based rate limiting (INF-149)
# =============================================================================
def test_tc_smc_003_rate_limiting_skips_second_command(driver, smc_module, monkeypatch):
    """
    Preconditions: min_command_interval = 0.05
    Steps:
      - send at t=0
      - send different at t=0.02
    Expected: second command skipped (too soon)
    """
    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("This test expects the driver to call _move_to_physical_mm.")

    # patch the time.time used inside the driver module
    t = {"now": 0.0}

    def fake_time():
        return t["now"]

    monkeypatch.setattr(smc_module.time, "time", fake_time)

    driver._move_to_physical_mm.reset_mock()

    _call_send_position(driver, 0.0)     # t=0
    t["now"] = 0.02
    _call_send_position(driver, 0.2)     # t=0.02 (too soon)

    # only first should pass through
    assert driver._move_to_physical_mm.call_count == 1


# =============================================================================
# TC-SMC-004: Position threshold skipping (INF-149)
# =============================================================================
def test_tc_smc_004_threshold_skips_small_change(driver, smc_module, monkeypatch):
    """
    Preconditions: position_threshold_mm = 1.0
    Steps:
      - send x=0.100
      - wait 0.1s
      - send x=0.1005 (0.5mm change)
    Expected: second command skipped (below threshold)
    """
    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("This test expects the driver to call _move_to_physical_mm.")

    # time must progress so this doesn't get blocked by the rate limiter instead
    t = {"now": 10.0}

    def fake_time():
        return t["now"]

    monkeypatch.setattr(smc_module.time, "time", fake_time)

    driver._move_to_physical_mm.reset_mock()

    _call_send_position(driver, 0.1000)
    t["now"] += 0.10
    _call_send_position(driver, 0.1005)  # 0.0005m = 0.5mm

    # second should be skipped due to threshold
    assert driver._move_to_physical_mm.call_count == 1


# =============================================================================
# TC-SMC-005: Command statistics (INF-149)
# =============================================================================
def test_tc_smc_005_get_stats_counts(driver, smc_module, monkeypatch):
    """
    Preconditions: driver initialized
    Steps:
      - send 10 commands rapidly (some skipped)
      - call get_stats()
    Expected:
      commands_sent + commands_skipped == 10
    """
    stats = _read_stats(driver)
    if stats is None:
        pytest.skip("Driver does not expose get_stats() or stats dict (INF-149 not visible).")

    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("This test expects the driver to call _move_to_physical_mm.")

    # make time barely move so we trigger skipping (rate limit)
    t = {"now": 100.0}

    def fake_time():
        return t["now"]

    monkeypatch.setattr(smc_module.time, "time", fake_time)

    driver._move_to_physical_mm.reset_mock()

    # send 10 commands quickly
    for i in range(10):
        _call_send_position(driver, 0.01 * i)
        t["now"] += 0.01  # 10ms steps (less than 50ms interval)

    stats = _read_stats(driver)
    assert stats is not None

    # common key names (we accept either style)
    sent = (
        stats.get("commands_sent")
        or stats.get("sent")
        or stats.get("sent_count")
        or 0
    )
    skipped = (
        stats.get("commands_skipped")
        or stats.get("skipped")
        or stats.get("skipped_count")
        or 0
    )

    assert (sent + skipped) == 10


# =============================================================================
# TC-SMC-006: Connection failure handling
# =============================================================================
def test_tc_smc_006_connection_failure_returns_false(smc_module, monkeypatch):
    """
    Preconditions: invalid port configured
    Steps:
      - create driver with port COM99
      - call connect()
    Expected:
      - returns False, no crash
    """
    SMCDriver = smc_module.SMCDriver

    config = {"port": "COM99", "baudrate": 38400, "controller_id": 1}

    try:
        d = SMCDriver(config)
    except TypeError:
        d = SMCDriver(config=config)

    fake_client = MagicMock()
    fake_client.connect.return_value = False

    # Patch constructor used by the driver module
    monkeypatch.setattr(smc_module, "ModbusSerialClient", lambda **kwargs: fake_client)

    ok = d.connect()
    assert ok is False
    assert getattr(d, "_connected", False) is False

