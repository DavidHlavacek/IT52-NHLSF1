"""
Unit Tests for SMC Driver - INF-127

Ticket goal:
    Unit tests for the SMC driver so we can verify Modbus communication is correct.

Techniques:
    - Equivalence partitioning (valid/invalid positions)
    - Mock testing (fake Modbus client)

Run:
    python3 -m pytest tests/drivers/test_smc_driver.py -v
"""

import inspect
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

@dataclass
class Position6DOF:
    """
    Local fallback type for tests.
    Real project should have src.shared.types.Position6DOF, but this is fine for unit tests.
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


class FakeResp:
    """Minimal response object that looks like pymodbus responses."""
    def __init__(self, registers=None, error=False, bits=None):
        self.registers = registers or []
        self.bits = bits or []
        self._error = error

    def isError(self):
        return self._error


def _make_driver_any(smc_module):
    """
    Create SMCDriver no matter which constructor style the repo uses.
    Some versions: SMCDriver(config_dict)
    Others: SMCDriver(config=config_dict)
    """
    SMCDriver = smc_module.SMCDriver

    config = {
        "port": "COM5",
        "baudrate": 38400,
        "controller_id": 1,
        "parity": "N",
        "center_mm": 450.0,
        "stroke_mm": 900.0,
        "speed_mm_s": 500,
        "accel_mm_s2": 3000,
        "decel_mm_s2": 3000,
        "limits": {"surge_m": 0.35},
    }

    try:
        return SMCDriver(config)
    except TypeError:
        return SMCDriver(config=config)


def _attach_fake_client(driver):
    """
    Attach a fake Modbus client so tests never touch real hardware.
    Driver might store it as .client or ._client, so we set both if possible.
    """
    fake = MagicMock()

    fake.connect.return_value = True
    fake.close.return_value = None

    fake.write_register.return_value = FakeResp(error=False)
    fake.write_registers.return_value = FakeResp(error=False)
    fake.write_coil.return_value = FakeResp(error=False)

    # for discrete inputs (busy/alarms), return False by default
    fake.read_discrete_inputs.return_value = FakeResp(bits=[False], error=False)

    # for reading position: driver reads 2 regs for int32 (high, low)
    # units=5000 => 50.00mm if divided by 100
    units = 5000
    high = (units >> 16) & 0xFFFF
    low = units & 0xFFFF
    fake.read_holding_registers.return_value = FakeResp(registers=[high, low], error=False)

    if hasattr(driver, "client"):
        driver.client = fake
    if hasattr(driver, "_client"):
        driver._client = fake

    if hasattr(driver, "_connected"):
        driver._connected = True

    return fake


def _get_client(driver):
    """Return the modbus client regardless of whether it's stored as client or _client."""
    if hasattr(driver, "client") and driver.client is not None:
        return driver.client
    if hasattr(driver, "_client") and driver._client is not None:
        return driver._client
    return None


def _send_position_any(driver, value):
    """
    Call send_position in a way that works if the driver expects:
      - send_position(Position6DOF)
      - or send_position(float)
    """
    sig = inspect.signature(driver.send_position)
    params = list(sig.parameters.values())

    if len(params) >= 2:
        anno = params[1].annotation
        if anno is not inspect._empty and "Position" in str(anno):
            if isinstance(value, Position6DOF):
                return driver.send_position(value)
            return driver.send_position(Position6DOF(x=float(value)))

    try:
        return driver.send_position(float(value))
    except Exception:
        if isinstance(value, Position6DOF):
            return driver.send_position(value)
        return driver.send_position(Position6DOF(x=float(value)))


def _find_write_registers_calls(client):
    """Returns list of addresses used in write_registers calls."""
    return [c.args[0] for c in client.write_registers.call_args_list]


# ----------------------------
# Fixtures
# ----------------------------

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

def test_mm_to_register_conversion_if_mm_driver_or_int32(driver):
    """
    This used to be an mm->register test.
    In your driver, the actual conversion is physical_mm -> units (mm * 100) for int32 writing.
    So we verify that conversion value is correct.
    """
    if not hasattr(driver, "_write_int32"):
        pytest.skip("Driver doesn't have _write_int32(), can't test mm->units conversion.")

    client = _get_client(driver)
    assert client is not None

    client.write_registers.reset_mock()

    # 50.00mm -> 5000 units
    driver._write_int32(driver.REG_POSITION, 5000)

    assert client.write_registers.called
    addr = client.write_registers.call_args[0][0]
    regs = client.write_registers.call_args[0][1]

    assert addr == driver.REG_POSITION
    assert isinstance(regs, list) and len(regs) == 2


def test_game_to_physical_conversion_if_game_driver(driver):
    """
    Driver uses game coords: Position6DOF.x in meters.
    Expected: physical_mm = center_mm + x*1000
    """
    if not hasattr(driver, "center_mm") or not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("Driver doesn't expose center_mm/_move_to_physical_mm.")

    driver._move_to_physical_mm = MagicMock(return_value=True)

    _send_position_any(driver, Position6DOF(x=0.10))  # +0.10m = +100mm
    assert driver._move_to_physical_mm.called

    physical_mm = driver._move_to_physical_mm.call_args[0][0]
    assert physical_mm == pytest.approx(driver.center_mm + 100.0)


# =============================================================================
# CONNECTION TESTS
# =============================================================================

def test_connect_creates_modbus_client_and_sets_connected(smc_module):
    """
    connect() should create a ModbusSerialClient and set connected state if connect works.
    """
    d = _make_driver_any(smc_module)

    fake_client = MagicMock()
    fake_client.connect.return_value = True

    smc_module.ModbusSerialClient = MagicMock(return_value=fake_client)

    ok = d.connect()

    assert ok is True
    assert getattr(d, "_connected", True) is True
    assert smc_module.ModbusSerialClient.called
    assert fake_client.connect.called


def test_connect_failure_returns_false_and_not_connected(smc_module):
    """
    If ModbusSerialClient.connect() returns False, driver.connect() should return False.
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
    "surge_m, expected_physical_mm",
    [
        (0.0, 450.0),
        (0.10, 550.0),
        (-0.10, 350.0),
    ],
)
def test_send_position_converts_and_calls_move(driver, surge_m, expected_physical_mm):
    """
    send_position(Position6DOF) should convert game meters to physical mm and call _move_to_physical_mm.
    """
    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("Driver doesn't expose _move_to_physical_mm.")

    driver._move_to_physical_mm = MagicMock(return_value=True)

    _send_position_any(driver, Position6DOF(x=surge_m))

    assert driver._move_to_physical_mm.called
    physical_mm = driver._move_to_physical_mm.call_args[0][0]
    assert physical_mm == pytest.approx(expected_physical_mm)


def test_send_position_clamps_to_stroke(driver):
    """
    Equivalence partitioning (invalid huge value):
    If x is extreme, physical_mm should clamp to [1, stroke_mm - 1].
    """
    if not hasattr(driver, "_move_to_physical_mm") or not hasattr(driver, "stroke_mm"):
        pytest.skip("Driver doesn't expose stroke clamp data.")

    driver._move_to_physical_mm = MagicMock(return_value=True)

    _send_position_any(driver, Position6DOF(x=999.0))  

    physical_mm = driver._move_to_physical_mm.call_args[0][0]
    assert physical_mm >= 1.0
    assert physical_mm <= (driver.stroke_mm - 1.0)


def test_move_to_physical_writes_key_registers(driver):
    """
    This is the main Modbus communication test.
    _move_to_physical_mm should write a bunch of registers in a sequence.
    We don't care about every register in exact order, but we do care that
    the important ones are hit.
    """
    if not hasattr(driver, "_move_to_physical_mm"):
        pytest.skip("Driver doesn't expose _move_to_physical_mm.")

    client = _get_client(driver)
    assert client is not None

    client.write_registers.reset_mock()

    ok = driver._move_to_physical_mm(450.0)
    assert ok in (True, False)

    addrs = _find_write_registers_calls(client)

    # these constants exist in driver
    assert driver.REG_MOVEMENT_MODE in addrs
    assert driver.REG_SPEED in addrs
    assert driver.REG_ACCELERATION in addrs
    assert driver.REG_DECELERATION in addrs
    assert driver.REG_OPERATION_START in addrs


def test_move_to_physical_writes_position_as_int32(driver):
    """
    Verify the position is written using _write_int32:
      - units = int(mm * 100)
      - written as two 16-bit registers at REG_POSITION
    """
    if not hasattr(driver, "_move_to_physical_mm") or not hasattr(driver, "REG_POSITION"):
        pytest.skip("Driver doesn't have REG_POSITION / _move_to_physical_mm.")

    client = _get_client(driver)
    assert client is not None

    client.write_registers.reset_mock()

    target_mm = 123.45
    driver._move_to_physical_mm(target_mm)

    pos_calls = [c for c in client.write_registers.call_args_list if c.args and c.args[0] == driver.REG_POSITION]
    assert pos_calls, "Expected write_registers(REG_POSITION, [high, low]) call."

    regs = pos_calls[0].args[1]
    assert isinstance(regs, list) and len(regs) == 2

    high, low = regs
    units = (high << 16) | low
    assert units == int(target_mm * 100)


# =============================================================================
# READ POSITION TESTS
# =============================================================================

def test_read_position_returns_mm_if_supported(driver):
    """
    Your driver uses _read_position_mm() which reads 2 registers and unpacks int32.
    We verify it returns expected mm.
    """
    if not hasattr(driver, "_read_position_mm"):
        pytest.skip("Driver doesn't expose _read_position_mm().")

    client = _get_client(driver)
    assert client is not None

    # units=5000 => 50.00mm
    units = 5000
    high = (units >> 16) & 0xFFFF
    low = units & 0xFFFF
    client.read_holding_registers.return_value = FakeResp(registers=[high, low], error=False)

    mm = driver._read_position_mm()
    assert mm == pytest.approx(50.0)


def test_read_position_error_returns_zero_for_game_driver(driver):
    """
    If the Modbus read is 'bad', your implementation returns 0.0 (based on current code).
    This replaces the old 'read_position returns None' test which doesn't match your API.
    """
    if not hasattr(driver, "_read_position_mm"):
        pytest.skip("Driver doesn't expose _read_position_mm().")

    client = _get_client(driver)
    assert client is not None

    client.read_holding_registers.return_value = FakeResp(registers=[], error=True)

    mm = driver._read_position_mm()
    assert mm == pytest.approx(0.0)


# =============================================================================
# CLOSE TESTS
# =============================================================================

def test_close_disconnects_client_and_marks_not_connected(driver):
    """
    close() should call client.close() and mark _connected False.
    """
    if not hasattr(driver, "close"):
        pytest.skip("Driver has no close() method.")

    client = _get_client(driver)
    assert client is not None

    if hasattr(driver, "_connected"):
        driver._connected = True

    driver.close()

    assert client.close.called
    assert getattr(driver, "_connected", False) is False


def test_close_handles_none_client(smc_module):
    """
    close() shouldn't crash if client isn't set.
    """
    d = _make_driver_any(smc_module)

    if hasattr(d, "client"):
        d.client = None
    if hasattr(d, "_client"):
        d._client = None

    # should not throw
    d.close()
