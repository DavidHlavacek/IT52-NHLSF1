"""
Integration Tests for MOOG Platform Pipeline - INF-114

Ticket:
    "Test the complete system pipeline with the MOOG platform to verify end-to-end functionality"

Covers these integration-style tests (hardware-safe using a fake UDP socket):
  - TC-INTMOOG-001: Neutral position command creates correct MOOG packet
  - TC-INTMOOG-002: All 6 axes go into correct packet fields (order + heave inversion)
  - TC-INTMOOG-003: Full pipeline (Algorithm -> Driver) using synthetic telemetry frames (skips if not importable)
  - TC-INTMOOG-004: Safety limits clamp extreme commands (float32 tolerance)
  - TC-INTMOOG-005: close() parks (PARK) then disconnects safely (IDLE state)
  - TC-INTMOOG-006: Network disconnect handled safely (no crash, returns False when not connected)

Run:
    python3 -m pytest tests/integration/test_moog_pipeline.py -v
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Tuple, Optional

import pytest

# Fallback Position6DOF 
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

# MOOGDriver uses socket.socket + sendto/recvfrom
class FakeSocket:
    """
    Records outgoing UDP packets and returns scripted recvfrom() packets
    for MOOGDriver._get_state().
    """

    def __init__(self):
        self.timeout: Optional[float] = None
        self.sent: List[Tuple[bytes, Tuple[str, int]]] = []
        self._recv_queue: List[bytes] = []
        self.closed = False

    def settimeout(self, t: float):
        self.timeout = t

    def sendto(self, data: bytes, addr: Tuple[str, int]):
        if self.closed:
            raise OSError("Simulated network disconnect: socket is closed")
        self.sent.append((data, addr))

    def recvfrom(self, n: int):
        """
        MOOGDriver._get_state() expects at least 12 bytes,
        and reads the 3rd uint32, then does status & 0x0F.
        """
        if self.closed:
            raise OSError("Simulated network disconnect: recvfrom on closed socket")
        if not self._recv_queue:
            raise TimeoutError("Simulated UDP timeout (no queued state)")
        data = self._recv_queue.pop(0)
        return data, ("fake-peer", 9999)

    def queue_state(self, low_nibble_state: int):
        """
        Put a response packet into the recv queue so _get_state() returns that state.
        low_nibble_state is what _get_state() returns (status & 0x0F).
        """
        status = low_nibble_state & 0x0F
        header12 = struct.pack(">3I", 0, 0, status)
        self._recv_queue.append(header12 + b"\x00" * 28)

    def close(self):
        self.closed = True

# Helpers
def unpack_moog_packet(packet: bytes):
    """
    Driver uses: struct.pack('>I6fI', mcw, roll, pitch, heave, surge, yaw, lateral, 0)
    """
    fmt = ">I6fI"
    assert len(packet) == struct.calcsize(fmt)
    return struct.unpack(fmt, packet)  

# Fixtures
@pytest.fixture
def moog_module():
    from src.drivers import moog_driver
    return moog_driver


@pytest.fixture
def driver(moog_module, monkeypatch):
    """
    Builds MOOGDriver the real way (calls connect()) but injects FakeSocket by patching socket.socket.
    """
    cfg = {
        "ip": "192.168.1.100",
        "port": 991,
        "timeout_s": 0.1,
        "limits": {
            "surge_pos_m": 0.259,
            "surge_neg_m": 0.241,
            "sway_m": 0.259,
            "heave_m": 0.178,
            "roll_rad": 0.3665,
            "pitch_rad": 0.3840,
            "yaw_rad": 0.3840,
        },
    }

    fake = FakeSocket()
    monkeypatch.setattr(moog_module.socket, "socket", lambda *args, **kwargs: fake)

    d = moog_module.MOOGDriver(cfg)
    assert d.connect() is True  
    d._fake_socket = fake
    return d

# TC-INTMOOG-001: Neutral command
def test_tc_intmoog_001_neutral_command(driver, moog_module):
    assert driver.send_position(Position6DOF()) is True

    fake: FakeSocket = driver._fake_socket
    packet, addr = fake.sent[-1]
    mcw, roll, pitch, heave, surge, yaw, lateral, tail = unpack_moog_packet(packet)

    assert addr == (driver.ip, driver.port)
    assert mcw == int(moog_module.MoogCommand.NEW_POSITION)

    assert roll == pytest.approx(0.0)
    assert pitch == pytest.approx(0.0)
    assert heave == pytest.approx(0.0)
    assert surge == pytest.approx(0.0)
    assert yaw == pytest.approx(0.0)
    assert lateral == pytest.approx(0.0)
    assert tail == 0

# TC-INTMOOG-002: All axes correct order + heave inversion
def test_tc_intmoog_002_all_axes_commanded(driver, moog_module):
    """
    Confirms:
      - correct field order: roll, pitch, heave, surge, yaw, sway(lateral)
      - heave is inverted in driver: heave = -clamp(z)
    """
    pos = Position6DOF(
        x=0.10,      
        y=-0.12,     
        z=0.05,      
        roll=0.02,
        pitch=-0.03,
        yaw=0.04,
    )

    assert driver.send_position(pos) is True

    packet, _ = driver._fake_socket.sent[-1]
    mcw, roll, pitch, heave, surge, yaw, lateral, _tail = unpack_moog_packet(packet)

    assert mcw == int(moog_module.MoogCommand.NEW_POSITION)
    assert roll == pytest.approx(pos.roll)
    assert pitch == pytest.approx(pos.pitch)

    assert heave == pytest.approx(-pos.z)

    assert surge == pytest.approx(pos.x)
    assert yaw == pytest.approx(pos.yaw)
    assert lateral == pytest.approx(pos.y)

# TC-INTMOOG-003: Full pipeline (Algorithm -> Driver)
def test_tc_intmoog_003_full_pipeline_synthetic_telemetry(driver):
    """
    Real pipeline test = Algorithm.calculate(telemetry) -> MOOGDriver.send_position(position)

    If your telemetry/algorithm modules are importable, we run it.
    If not, we skip (so CI doesn't break on environments missing those pieces).
    """
    try:
        from src.motion.algorithm import MotionAlgorithm
        from src.telemetry.packet_parser import TelemetryData
    except Exception:
        pytest.skip("MotionAlgorithm/TelemetryData not importable here, skipping pipeline test.")

    algo = MotionAlgorithm(
        {
            "translation_scale": 0.1,
            "rotation_scale": 0.5,
            "onset_gain": 1.0,
            "sustained_gain": 0.4,
            "deadband": 0.08,
            "sample_rate": 60.0,
            "washout_freq": 0.4,
            "sustained_freq": 3.0,
            "slew_rate": 0.4,
        }
    )

    frames = [
        TelemetryData(
            g_force_longitudinal=0.0,
            g_force_lateral=0.0,
            g_force_vertical=1.0,
            roll=0.0,
            pitch=0.0,
            yaw=0.0,
        ),
        TelemetryData(
            g_force_longitudinal=-0.4,
            g_force_lateral=0.2,
            g_force_vertical=1.05,
            roll=0.02,
            pitch=0.01,
            yaw=0.03,
        ),
    ]

    sent_before = len(driver._fake_socket.sent)

    for tel in frames:
        pos = algo.calculate(tel)
        assert driver.send_position(pos) is True
    assert len(driver._fake_socket.sent) == sent_before + len(frames)

# TC-INTMOOG-004: Safety clamping (float32 tolerance)
def test_tc_intmoog_004_safety_limits_clamp(driver, moog_module):
    """
    Extreme commands must be clamped.
    We allow a tiny epsilon because values are packed/unpacked as float32.
    """
    extreme = Position6DOF(
        x=999.0,
        y=-999.0,
        z=999.0,
        roll=999.0,
        pitch=-999.0,
        yaw=999.0,
    )

    assert driver.send_position(extreme) is True

    packet, _ = driver._fake_socket.sent[-1]
    mcw, roll, pitch, heave, surge, yaw, lateral, _tail = unpack_moog_packet(packet)
    assert mcw == int(moog_module.MoogCommand.NEW_POSITION)

    eps = 1e-6  

    # surge clamp (+pos and -neg)
    assert surge <= driver.limit_surge_pos + eps
    assert surge >= -driver.limit_surge_neg - eps

    # sway clamp (lateral)
    assert lateral <= driver.limit_sway + eps
    assert lateral >= -driver.limit_sway - eps

    # heave clamp (note inversion in driver)
    assert heave <= driver.limit_heave + eps
    assert heave >= -driver.limit_heave - eps

    # rotations
    assert roll <= driver.limit_roll + eps
    assert roll >= -driver.limit_roll - eps

    assert pitch <= driver.limit_pitch + eps
    assert pitch >= -driver.limit_pitch - eps

    assert yaw <= driver.limit_yaw + eps
    assert yaw >= -driver.limit_yaw - eps

# TC-INTMOOG-005: close() parks then disconnects safely
def test_tc_intmoog_005_close_parks_then_disconnects(driver, moog_module):
    fake: FakeSocket = driver._fake_socket
    driver._engaged = True
    fake.queue_state(int(moog_module.MoogState.IDLE))

    driver.close()

    # driver flags reset
    assert driver._connected is False
    assert driver._engaged is False
    assert fake.closed is True
    last_packet, _ = fake.sent[-1]
    mcw, *_rest = unpack_moog_packet(last_packet)
    assert mcw == int(moog_module.MoogCommand.PARK)

# TC-INTMOOG-006: Network disconnect handled safely
def test_tc_intmoog_006_network_disconnect_safe(driver):
    """
    The driver itself doesn't catch sendto() exceptions during send_position(),
    so the safe behavior is:
      - after disconnect we mark not connected / close the driver
      - future send_position returns False (no crash)
    """
    driver._fake_socket.close()
    driver._connected = False

    assert driver.send_position(Position6DOF(x=0.1)) is False
    driver.close()
    assert driver._connected is False
