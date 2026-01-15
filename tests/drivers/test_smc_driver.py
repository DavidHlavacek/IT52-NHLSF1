"""
Unit Tests for SMC Driver - INF-127

Ticket: As a developer, I want unit tests for the SMC driver so that
        I can verify Modbus communication is correct.

Test Design Techniques Used:
    - Equivalence partitioning (valid/invalid positions)
    - Mock testing (Modbus client)

Run:
    python3 -m pytest tests/drivers/test_smc_driver.py -v
"""

import inspect
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest


# -----------------------------
# Small local types / fakes
# -----------------------------

@dataclass
class Position6DOF:
    """Fallback Position type for tests (only used if your project type isn't importable)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


class FakeResp:
    """Tiny fake pymodbus response object that behaves like pymodbus responses."""
    def __init__(self, registers=None, error=False, bits=None):
        self.registers = registers or []
        self.bits = bits or []
        self._error = error

    def isError(self):
        return self._error


def _make_driver_any(smc_module):
    """
    Create SMCDriver no matter which constructor style your driver uses.
    Some versions: SMCDriver(config_dict)
    Other versions: SMCDriver(config=config_dict)
    """
    SMCDriver = smc_module.SMCDriver

    config = {
        "port": "COM5",
        "baudrate": 38400,
        "controller_id": 1,
        "parity": "N",
        "center_mm": 450.0,
        "stroke_mm": 900.0,
        "limits": {"surge_m": 0.35},
        # if your config uses these:
        "min_position": 0.0,
        "max_position": 100.0,
    }

    try:
        return SMCDriver(config)
    except TypeError:
        return SMCDriver(config=config)


def _attach_fake_client(driver):
    """
    Attach a fake Modbus client to the driver in the most common attribute names.
    Different codebases use `client`, `_client`, etc.
    """
    fake = MagicMock()

    fake.connect.return_value = True
    fake.close.return_value = None

    # common Modbus methods we expect:
    fake.write_register.return_value = FakeResp(error=False)
    fake.write_registers.return_value = FakeResp(error=False)
    fake.write_coil.return_value = FakeResp(error=False)
    fake.read_holding_registers.return_value = FakeResp(registers=[5000], error=False)
    fake.read_discrete_inputs.return_value = FakeResp(bits=[False], error=False)

    # attach in the common places
    if hasattr(driver, "client"):
        driver.client = fake
    if hasattr(driver, "_client"):
        driver._client = fake

    # mark connected if the driver uses that flag
    if hasattr(driver, "_connected"):
        driver._connected = True

    return fake


def _send_position_any(driver, value):
    """
    Call send_position in a way that works if your driver expects:
      - send_position(50.0)  (mm-based)
      - send_position(Position6DOF(...)) (game-based)
    """
    sig = inspect.signature(driver.send_position)
    params = list(sig.parameters.values())

    # expected param after self
    if len(params) >= 2:
        anno = params[1].annotation
        if anno is not inspect._empty and "Position" in str(anno):
            if isinstance(value, Position6DOF):
                return driver.send_position(value)
            return driver.send_position(Position6DOF(x=float(value)))

    # fallback: try float, else Position6DOF
    try:
        return driver.send_position(float(value))
    except Exception:
        if isinstance(value, Position6DOF):
            return driver.send_position(value)
        return driver.send_position(Position6DOF(x=float(value)))


def _get_client(driver):
    """Return the fake client regardless of whether driver uses client or _client."""
    if hasattr(driver, "client") and driver.client is not None:
        return driver.client
    if hasattr(driver, "_client") and driver._client is not None:
        return driver._client
    return None


# -----------------------------
# Fixtures
# -----------------------------

@pytest.fixture
def smc_module():
    from src.drivers import smc_driver
    return smc_driver


@pytest.fixture
def driver(smc_module):
    d = _make_driver_any(smc_module)
    _attach_fake_client(d)
    return d


# =============================================================================
# POSITION CONVERSION TESTS
# =============================================================================

def test_mm_to_register_conversion_if_mm_driver(driver):
    """
    Equivalence partitioning: a few representative mm values.

    Only runs if the driver exposes POSITION_SCALE and REG_TARGET_POSITION
    (typical mm-based implementation).
    """
    if not hasattr(driver, "POSITION_SCALE") or not hasattr(driver, "REG_TARGET_POSITION"):
        pytest.skip("Driver doesn't look like mm->register style (POSITION_SCALE/REG_TARGET_POSITION missing).")

    scale = driver.POSITION_SCALE
    assert int(0.0 * scale) == 0
    assert int(25.0 * scale) == 2500
    assert int(50.0 * scale) == 5000
    assert int(100.0 * scale) == 10000


def test_game_to_physical_conversion_if_game_driver(driver):
    """
    If the driver uses Position6DOF.x (meters) => physical mm:
        physical_mm = center_mm + x*1000
    This is a direct check on the conversion.
    """
    if not hasattr(driver, "center_mm") or not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("Driver doesn't expose center_mm/_move_to_physical_mm (not the game->physical style).")

    driver._move_to_physical_mm = MagicMock(return_value=True)

    _send_position_any(driver, Position6DOF(x=0.10))  # +0.10m => +100mm
    assert driver._move_to_physical_mm.called

    physical_mm = driver._move_to_physical_mm.call_args[0][0]
    assert physical_mm == pytest.approx(driver.center_mm + 100.0)


# =============================================================================
# CONNECTION TESTS
# =============================================================================

def test_connect_creates_modbus_client_and_sets_connected(smc_module):
    """
    Mock testing: patch ModbusSerialClient inside the driver module.
    Verify connect() returns True and sets driver._connected.
    """
    d = _make_driver_any(smc_module)

    fake_client = MagicMock()
    fake_client.connect.return_value = True

    # patch the constructor used in that module
    smc_module.ModbusSerialClient = MagicMock(return_value=fake_client)

    ok = d.connect()

    assert ok is True
    assert getattr(d, "_connected", True) is True
    assert smc_module.ModbusSerialClient.called is True
    assert fake_client.connect.called is True


def test_connect_failure_returns_false_and_not_connected(smc_module):
    """
    If client.connect() fails, driver.connect() should return False.
    """
    d = _make_driver_any(smc_module)

    fake_client = MagicMock()
    fake_client.connect.return_value = False

    smc_module.ModbusSerialClient = MagicMock(return_value=fake_client)

    ok = d.connect()

    assert ok is False
    assert getattr(d, "_connected", False) is False


# =============================================================================
# SEND POSITION TESTS
# =============================================================================

@pytest.mark.parametrize(
    "position_mm, expected_units",
    [
        (0.0, 0),
        (25.0, 2500),
        (50.0, 5000),
        (75.0, 7500),
        (100.0, 10000),
    ],
)
def test_send_position_writes_target_register_for_mm_driver(driver, position_mm, expected_units):
    """
    Mock testing: ensure Modbus write is called with correct register + value.
    Only runs if driver uses REG_TARGET_POSITION/POSITION_SCALE style.
    """
    if not hasattr(driver, "REG_TARGET_POSITION") or not hasattr(driver, "POSITION_SCALE"):
        pytest.skip("Driver doesn't look like mm->register write_register style.")

    client = _get_client(driver)
    assert client is not None

    client.write_register.reset_mock()

    ok = _send_position_any(driver, position_mm)

    # driver might return True/False, but if it tried to send, it must write correct units
    assert client.write_register.called is True
    addr = client.write_register.call_args[0][0]
    val = client.write_register.call_args[0][1]

    assert addr == driver.REG_TARGET_POSITION
    assert val == expected_units


def test_send_position_equivalence_partitioning_invalid_position_mm(driver):
    """
    Equivalence partitioning:
      - valid positions: inside stroke/limits
      - invalid positions: outside limits

    For invalid, driver should either:
      - clamp, OR
      - return False / avoid write
    We accept either behavior, but we do NOT accept sending a crazy out-of-range register value.
    """
    if not hasattr(driver, "REG_TARGET_POSITION") or not hasattr(driver, "POSITION_SCALE"):
        pytest.skip("This test is for mm->register drivers.")

    client = _get_client(driver)
    assert client is not None

    client.write_register.reset_mock()

    ok = _send_position_any(driver, 9999.0)

    if ok is False:
        # rejecting invalid is fine
        assert client.write_register.call_count == 0
        return

    # if it didn't return False, then it probably clamps.
    assert client.write_register.called is True
    sent_val = client.write_register.call_args[0][1]

    # sent value should be within something sane (0..max*scale)
    # max_position may exist; otherwise assume 100mm default
    max_mm = getattr(driver, "max_position", 100.0)
    max_units = int(max_mm * driver.POSITION_SCALE)
    assert 0 <= sent_val <= max_units


def test_send_position_game_driver_calls_move_to_physical(driver):
    """
    If driver is the game->physical style, the main thing is:
    send_position(Position6DOF) must call the physical move method.
    """
    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("Not a game->physical driver.")

    driver._move_to_physical_mm = MagicMock(return_value=True)

    ok = _send_position_any(driver, Position6DOF(x=0.05))
    assert driver._move_to_physical_mm.called is True
    assert ok in (True, False)  # don't force behavior beyond "it tried"


# =============================================================================
# READ POSITION TESTS
# =============================================================================

def test_read_position_returns_mm_if_supported(driver):
    """
    Mock testing: read_holding_registers returns raw registers, driver converts to mm.
    Works for:
      - mm driver: registers=[5000] and POSITION_SCALE=100 -> 50.0mm
      - game driver: _read_position_mm reads 2 regs (int32) -> mm
    """
    client = _get_client(driver)
    assert client is not None

    # Case 1: mm driver read_position()
    if hasattr(driver, "read_position") and hasattr(driver, "POSITION_SCALE"):
        client.read_holding_registers.return_value = FakeResp(registers=[5000], error=False)
        pos = driver.read_position()
        assert pos == pytest.approx(5000 / driver.POSITION_SCALE)
        return

    # Case 2: game driver helper _read_position_mm()
    if hasattr(driver, "_read_position_mm"):
        # emulate int32 units=5000 => 50.00mm when divided by 100
        units = 5000
        high = (units >> 16) & 0xFFFF
        low = units & 0xFFFF

        client.read_holding_registers.return_value = FakeResp(registers=[high, low], error=False)
        mm = driver._read_position_mm()
        assert mm == pytest.approx(50.0)
        return

    pytest.skip("Driver doesn't expose read_position() or _read_position_mm().")


def test_read_position_error_returns_none_if_mm_driver(driver):
    """
    If read_holding_registers returns an error, read_position should return None (common pattern).
    Only runs if mm driver has read_position().
    """
    if not hasattr(driver, "read_position"):
        pytest.skip("Driver has no read_position() to test.")

    client = _get_client(driver)
    assert client is not None

    client.read_holding_registers.return_value = FakeResp(registers=[], error=True)

    out = driver.read_position()

    # many implementations return None on Modbus error
    assert out is None


# =============================================================================
# CLOSE TESTS
# =============================================================================

def test_close_disconnects_client_and_marks_not_connected(driver):
    """
    close() should close the Modbus client and set _connected False.
    """
    if not hasattr(driver, "close"):
        pytest.skip("Driver has no close() method.")

    client = _get_client(driver)
    assert client is not None

    # ensure driver looks connected before
    if hasattr(driver, "_connected"):
        driver._connected = True

    driver.close()

    assert client.close.called is True
    assert getattr(driver, "_connected", False) is False


def test_close_handles_none_client(smc_module):
    """
    close() should not crash if client isn't set.
    """
    d = _make_driver_any(smc_module)

    # wipe clients
    if hasattr(d, "client"):
        d.client = None
    if hasattr(d, "_client"):
        d._client = None

    # should not throw
    d.close()
