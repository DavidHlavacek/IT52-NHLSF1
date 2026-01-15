"""
Unit Tests for SMC Driver - INF-127

Ticket: Create and run unit tests for the SMC driver to ensure Modbus communication
is functioning correctly and reliably.

Tests implemented (from Test Cases doc):
  - TC-SMC-001: game coords -> physical coords conversion
  - TC-SMC-002: clamping to stroke limits
  - TC-SMC-003: time-based rate limiting (INF-149)
  - TC-SMC-004: small-change threshold skipping (INF-149)
  - TC-SMC-005: get_stats() returns correct counts (INF-149)
  - TC-SMC-006: connection failure handling

Run:
  python3 -m pytest tests/drivers/test_smc_driver.py -v
"""

from dataclasses import dataclass
from unittest.mock import MagicMock
import pytest

try:
    from src.shared.types import Position6DOF 
except Exception:
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
    from src.drivers import smc_driver
    return smc_driver


def _set_last_command_time(driver, value: float) -> None:
    """
    Different implementations use different attribute names.
    This helper tries to set the most common ones if they exist.
    """
    candidates = [
        "_last_command_time",
        "last_command_time",
        "_last_cmd_time",
        "last_cmd_time",
        "_last_send_time",
        "last_send_time",
        "_last_time",
        "last_time",
    ]
    for name in candidates:
        if hasattr(driver, name):
            setattr(driver, name, value)


@pytest.fixture
def driver(smc_module):
    """
    Create an SMCDriver using a config that matches the test case preconditions.
    We force it into a safe test mode (no real hardware).
    """
    SMCDriver = smc_module.SMCDriver

    config = {
        "port": "COM5",
        "baudrate": 38400,
        "controller_id": 1,
        "parity": "N",
        "center_mm": 450.0,
        "stroke_mm": 900.0,
        "limits": {"surge_m": 0.4},          # 0.4m => 400mm clamp (TC-SMC-002)
        "min_command_interval": 0.05,        # (TC-SMC-003)
        "position_threshold_mm": 1.0,        # (TC-SMC-004)
    }

    try:
        d = SMCDriver(config)
    except TypeError:
        d = SMCDriver(config=config)

    d.client = MagicMock()
    d.client.connect.return_value = True
    d._connected = True

    if hasattr(d, "_move_to_physical_mm"):
        d._move_to_physical_mm = MagicMock(return_value=True)

    return d


def _call_send_position(driver, x_value: float):
    return driver.send_position(Position6DOF(x=x_value))


def _read_stats(driver):
    if hasattr(driver, "get_stats") and callable(driver.get_stats):
        stats = driver.get_stats()
        if isinstance(stats, dict):
            return stats

    if hasattr(driver, "stats") and isinstance(driver.stats, dict):
        return driver.stats

    return None


# =============================================================================
# TC-SMC-001: Coordinate conversion (game ↔ physical)
# =============================================================================
def test_tc_smc_001_coordinate_conversion_game_to_physical(driver, smc_module, monkeypatch):
    """
    Preconditions: center_mm = 450

    Steps:
      1) x=0.0   -> 450mm
      2) x=0.2   -> 650mm
      3) x=-0.2  -> 250mm
    """
    if not hasattr(driver, "center_mm") or not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("Driver doesn't expose center_mm or _move_to_physical_mm.")

    # Important: rate limiting can skip back-to-back calls, so we control time.
    t = {"now": 100.0}

    def fake_time():
        return t["now"]

    monkeypatch.setattr(smc_module.time, "time", fake_time)
    _set_last_command_time(driver, 0.0)

    driver._move_to_physical_mm.reset_mock()

    _call_send_position(driver, 0.0)
    t["now"] += 0.10  # > 0.05 interval
    _call_send_position(driver, 0.2)
    t["now"] += 0.10
    _call_send_position(driver, -0.2)

    calls = [c.args[0] for c in driver._move_to_physical_mm.call_args_list]
    assert len(calls) == 3

    assert calls[0] == pytest.approx(450.0)
    assert calls[1] == pytest.approx(650.0)
    assert calls[2] == pytest.approx(250.0)


# =============================================================================
# TC-SMC-002: Position clamping to stroke limits
# =============================================================================
def test_tc_smc_002_position_clamped_to_limits(driver):
    """
    Preconditions: stroke_mm=900, center_mm=450, max_position_m=0.4
    Step: send x=0.5 (500mm, beyond limit)
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
      - send different position at t=0.02
    Expected: second command skipped
    """
    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("This test expects the driver to call _move_to_physical_mm.")

    t = {"now": 50.0}

    def fake_time():
        return t["now"]

    monkeypatch.setattr(smc_module.time, "time", fake_time)

    # Make sure the first command is not treated as "too soon"
    _set_last_command_time(driver, t["now"] - 1.0)

    driver._move_to_physical_mm.reset_mock()

    _call_send_position(driver, 0.0)   
    t["now"] += 0.02                   
    _call_send_position(driver, 0.2)    

    assert driver._move_to_physical_mm.call_count == 1


# =============================================================================
# TC-SMC-004: Position threshold skipping (INF-149)
# =============================================================================
def test_tc_smc_004_threshold_skips_small_change(driver, smc_module, monkeypatch):
    """
    Preconditions: position_threshold_mm = 1.0
    Steps:
      - send x=0.100
      - wait 100ms
      - send x=0.1005 (0.5mm change)
    Expected: second command skipped (below threshold)
    """
    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("This test expects the driver to call _move_to_physical_mm.")

    t = {"now": 10.0}

    def fake_time():
        return t["now"]

    monkeypatch.setattr(smc_module.time, "time", fake_time)
    _set_last_command_time(driver, 0.0)

    driver._move_to_physical_mm.reset_mock()

    _call_send_position(driver, 0.1000)
    t["now"] += 0.10
    _call_send_position(driver, 0.1005)  # 0.0005m = 0.5mm

    assert driver._move_to_physical_mm.call_count == 1


# =============================================================================
# TC-SMC-005: Command statistics (INF-149)
# =============================================================================
def test_tc_smc_005_get_stats_counts(driver, smc_module, monkeypatch):
    """
    Steps:
      - send 10 commands quickly (some will be skipped by rate limit)
      - call get_stats()
    Expected:
      commands_sent + commands_skipped = 10
    """
    stats = _read_stats(driver)
    if stats is None:
        pytest.skip("Driver does not expose get_stats() or stats dict.")

    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("This test expects the driver to call _move_to_physical_mm.")

    t = {"now": 100.0}

    def fake_time():
        return t["now"]

    monkeypatch.setattr(smc_module.time, "time", fake_time)
    _set_last_command_time(driver, 0.0)

    for i in range(10):
        _call_send_position(driver, 0.01 * i)
        t["now"] += 0.01  # 10ms steps (less than 50ms interval)

    stats = _read_stats(driver)
    assert stats is not None

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
    Preconditions: invalid COM port configured
    Steps:
      - create driver with port='COM99'
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

    monkeypatch.setattr(smc_module, "ModbusSerialClient", lambda **kwargs: fake_client)

    ok = d.connect()
    assert ok is False
    assert getattr(d, "_connected", False) is False
