"""
Unit Tests for MOOG Driver - INF-128
Covers: INF-108
"""

import pytest
import struct
import socket
from unittest.mock import Mock, patch

from src.drivers.moog_driver import MOOGDriver, MoogCommand
from src.shared.types import Position6DOF
from src.utils.config import load_config


@pytest.fixture
def config():
    return load_config()['hardware']['moog']


@pytest.fixture
def driver(config):
    return MOOGDriver(config)


# TC-MOOG-001
def test_connect_creates_udp_socket(driver):
    with patch('socket.socket') as mock_socket_class:
        mock_socket_class.return_value = Mock()
        driver.connect()
        mock_socket_class.assert_called_with(socket.AF_INET, socket.SOCK_DGRAM)


# TC-MOOG-002
def test_send_position_sends_packet(driver):
    mock_sock = Mock()
    driver.socket = mock_sock
    driver._connected = True

    result = driver.send_position(Position6DOF())

    assert result == True
    mock_sock.sendto.assert_called_once()


# TC-MOOG-003
def test_packet_format_matches_protocol(driver):
    mock_sock = Mock()
    driver.socket = mock_sock
    driver._connected = True

    driver.send_position(Position6DOF())

    packet, address = mock_sock.sendto.call_args[0]
    assert len(packet) == 32
    assert address == (driver.ip, driver.port)

    unpacked = struct.unpack('>I6fI', packet)
    assert unpacked[0] == MoogCommand.NEW_POSITION
    assert unpacked[7] == 0


# TC-MOOG-004
def test_send_position_not_connected_returns_false(driver):
    result = driver.send_position(Position6DOF())
    assert result == False


# TC-MOOG-005
def test_all_six_axes_in_packet(driver):
    mock_sock = Mock()
    driver.socket = mock_sock
    driver._connected = True

    driver.send_position(Position6DOF(x=0.1, y=0.05, z=0.02, roll=0.1, pitch=0.2, yaw=0.15))

    packet = mock_sock.sendto.call_args[0][0]
    unpacked = struct.unpack('>I6fI', packet)
    roll, pitch, heave, surge, yaw, lateral = unpacked[1:7]

    assert abs(surge - 0.1) < 0.001
    assert abs(lateral - 0.05) < 0.001
    assert abs(heave - (-0.02)) < 0.001
    assert abs(roll - 0.1) < 0.001
    assert abs(pitch - 0.2) < 0.001
    assert abs(yaw - 0.15) < 0.001


# TC-MOOG-006
def test_units_are_meters_and_radians(driver):
    mock_sock = Mock()
    driver.socket = mock_sock
    driver._connected = True

    driver.send_position(Position6DOF(x=0.15, y=0.10, z=0.05))

    packet = mock_sock.sendto.call_args[0][0]
    unpacked = struct.unpack('>I6fI', packet)
    heave = unpacked[3]
    surge = unpacked[4]
    lateral = unpacked[6]

    assert abs(surge - 0.15) < 0.001
    assert abs(lateral - 0.10) < 0.001
    assert abs(heave - (-0.05)) < 0.001


# TC-MOOG-007
def test_no_rate_limiting_in_driver(driver):
    mock_sock = Mock()
    driver.socket = mock_sock
    driver._connected = True

    for _ in range(5):
        driver.send_position(Position6DOF())

    assert mock_sock.sendto.call_count == 5


# TC-MOOG-008
def test_close_releases_socket(driver):
    mock_sock = Mock()
    driver.socket = mock_sock
    driver._connected = True
    driver._engaged = False  # skip disengage

    driver.close()

    mock_sock.close.assert_called_once()
    assert driver.socket is None
