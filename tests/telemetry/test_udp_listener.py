"""
Unit Tests for UDP Listener - INF-126

Ticket: As a developer, I want unit tests for the UDP listener so that
        I can verify packet reception works correctly.

Test Design Techniques Used:
    - Equivalence partitioning (valid/timeout/error)
    - Mock testing (socket operations)

Run: pytest tests/telemetry/test_udp_listener.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import socket


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def mock_socket_instance():
    """Create a mock socket instance."""
    mock = MagicMock(spec=socket.socket)
    mock.recvfrom.return_value = (b'\x00' * 100, ('127.0.0.1', 12345))
    return mock


@pytest.fixture
def listener_with_mock_socket(mock_socket_instance):
    """
    Create a UDPListener with mocked socket to avoid real network binding.

    Since __init__ calls _setup_socket(), we must patch before instantiation.
    """
    with patch('socket.socket', return_value=mock_socket_instance):
        from src.telemetry.udp_listener import UDPListener
        listener = UDPListener(port=20777)
        yield listener
        listener.close()


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================

class TestInitialization:
    """Tests for UDPListener initialization."""

    def test_default_port_is_20777(self):
        """Test DEFAULT_PORT class attribute is 20777."""
        from src.telemetry.udp_listener import UDPListener
        assert UDPListener.DEFAULT_PORT == 20777

    def test_default_port_used_when_not_specified(self, mock_socket_instance):
        """Test default port is used when not specified."""
        with patch('socket.socket', return_value=mock_socket_instance):
            from src.telemetry.udp_listener import UDPListener
            listener = UDPListener()
            assert listener.port == 20777
            listener.close()

    def test_custom_port_configuration(self, mock_socket_instance):
        """Test custom port configuration."""
        with patch('socket.socket', return_value=mock_socket_instance):
            from src.telemetry.udp_listener import UDPListener
            listener = UDPListener(port=30000)
            assert listener.port == 30000
            listener.close()

    def test_custom_timeout_configuration(self, mock_socket_instance):
        """Test custom timeout configuration."""
        with patch('socket.socket', return_value=mock_socket_instance):
            from src.telemetry.udp_listener import UDPListener
            listener = UDPListener(timeout=5.0)
            assert listener.timeout == 5.0
            listener.close()

    def test_initial_packet_count_zero(self, listener_with_mock_socket):
        """Test packet count starts at zero."""
        assert listener_with_mock_socket._packet_count == 0

    def test_buffer_size_is_2048(self):
        """Test BUFFER_SIZE class attribute is 2048."""
        from src.telemetry.udp_listener import UDPListener
        assert UDPListener.BUFFER_SIZE == 2048


# =============================================================================
# SOCKET SETUP TESTS
# =============================================================================

class TestSetupSocket:
    """Tests for _setup_socket() method."""

    def test_creates_udp_socket(self):
        """Test UDP socket is created with correct parameters."""
        mock_sock = MagicMock(spec=socket.socket)
        with patch('socket.socket', return_value=mock_sock) as mock_socket_class:
            from src.telemetry.udp_listener import UDPListener
            listener = UDPListener()
            mock_socket_class.assert_called_with(socket.AF_INET, socket.SOCK_DGRAM)
            listener.close()

    def test_binds_to_all_interfaces(self):
        """Test socket binds to 0.0.0.0 (all interfaces)."""
        mock_sock = MagicMock(spec=socket.socket)
        with patch('socket.socket', return_value=mock_sock):
            from src.telemetry.udp_listener import UDPListener
            listener = UDPListener(port=20777)
            mock_sock.bind.assert_called_with(('0.0.0.0', 20777))
            listener.close()

    def test_binds_to_custom_port(self):
        """Test socket binds to custom port."""
        mock_sock = MagicMock(spec=socket.socket)
        with patch('socket.socket', return_value=mock_sock):
            from src.telemetry.udp_listener import UDPListener
            listener = UDPListener(port=12345)
            mock_sock.bind.assert_called_with(('0.0.0.0', 12345))
            listener.close()

    def test_sets_socket_timeout(self):
        """Test socket timeout is set."""
        mock_sock = MagicMock(spec=socket.socket)
        with patch('socket.socket', return_value=mock_sock):
            from src.telemetry.udp_listener import UDPListener
            listener = UDPListener(timeout=2.5)
            mock_sock.settimeout.assert_called_with(2.5)
            listener.close()

    def test_default_timeout_is_one_second(self):
        """Test default timeout is 1.0 second."""
        mock_sock = MagicMock(spec=socket.socket)
        with patch('socket.socket', return_value=mock_sock):
            from src.telemetry.udp_listener import UDPListener
            listener = UDPListener()
            mock_sock.settimeout.assert_called_with(1.0)
            listener.close()

    def test_socket_error_raises_exception(self):
        """Test socket binding error is raised."""
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.bind.side_effect = socket.error("Address already in use")
        with patch('socket.socket', return_value=mock_sock):
            from src.telemetry.udp_listener import UDPListener
            with pytest.raises(socket.error):
                UDPListener(port=20777)


# =============================================================================
# RECEIVE TESTS
# =============================================================================

class TestReceive:
    """Tests for receive() method."""

    def test_receive_returns_packet_data(self, listener_with_mock_socket, mock_socket_instance):
        """Test receive() returns packet data."""
        mock_socket_instance.recvfrom.return_value = (b'test_data', ('127.0.0.1', 12345))
        listener_with_mock_socket.socket = mock_socket_instance

        result = listener_with_mock_socket.receive()
        assert result == b'test_data'

    def test_receive_uses_buffer_size(self, listener_with_mock_socket, mock_socket_instance):
        """Test receive() uses BUFFER_SIZE."""
        listener_with_mock_socket.socket = mock_socket_instance
        listener_with_mock_socket.receive()

        mock_socket_instance.recvfrom.assert_called_with(2048)

    def test_receive_increments_packet_count(self, listener_with_mock_socket, mock_socket_instance):
        """Test packet count increments on each receive."""
        listener_with_mock_socket.socket = mock_socket_instance
        listener_with_mock_socket._packet_count = 0

        listener_with_mock_socket.receive()
        assert listener_with_mock_socket._packet_count == 1

        listener_with_mock_socket.receive()
        assert listener_with_mock_socket._packet_count == 2

    def test_receive_handles_timeout_returns_none(self, listener_with_mock_socket, mock_socket_instance):
        """Test receive() returns None on timeout."""
        mock_socket_instance.recvfrom.side_effect = socket.timeout
        listener_with_mock_socket.socket = mock_socket_instance

        result = listener_with_mock_socket.receive()
        assert result is None

    def test_receive_handles_socket_error_returns_none(self, listener_with_mock_socket, mock_socket_instance):
        """Test receive() returns None on socket error."""
        mock_socket_instance.recvfrom.side_effect = socket.error("Connection reset")
        listener_with_mock_socket.socket = mock_socket_instance

        result = listener_with_mock_socket.receive()
        assert result is None

    def test_receive_without_socket_returns_none(self, listener_with_mock_socket):
        """Test receive() returns None if socket is None."""
        listener_with_mock_socket.socket = None

        result = listener_with_mock_socket.receive()
        assert result is None

    def test_timeout_does_not_increment_packet_count(self, listener_with_mock_socket, mock_socket_instance):
        """Test packet count not incremented on timeout."""
        mock_socket_instance.recvfrom.side_effect = socket.timeout
        listener_with_mock_socket.socket = mock_socket_instance
        listener_with_mock_socket._packet_count = 5

        listener_with_mock_socket.receive()
        assert listener_with_mock_socket._packet_count == 5

    def test_receive_data_on_custom_port(self):
        """
        TC-UDP-005: Test that listener can receive data on a custom port.
        Verifies binding to custom port and successful data reception.
        """
        mock_sock = MagicMock(spec=socket.socket)
        test_data = b'\x01\x02\x03\x04custom_port_data'
        mock_sock.recvfrom.return_value = (test_data, ('192.168.1.100', 54321))

        with patch('socket.socket', return_value=mock_sock):
            from src.telemetry.udp_listener import UDPListener

            # Create listener on custom port
            custom_port = 30000
            listener = UDPListener(port=custom_port)

            # Verify bound to custom port
            mock_sock.bind.assert_called_with(('0.0.0.0', custom_port))

            # Receive data on custom port
            received = listener.receive()

            # Verify data received correctly
            assert received == test_data
            assert listener.packet_count == 1

            listener.close()


# =============================================================================
# CLOSE TESTS
# =============================================================================

class TestClose:
    """Tests for close() method."""

    def test_close_closes_socket(self, listener_with_mock_socket, mock_socket_instance):
        """Test close() closes the socket."""
        listener_with_mock_socket.socket = mock_socket_instance
        listener_with_mock_socket.close()

        mock_socket_instance.close.assert_called_once()

    def test_close_sets_socket_to_none(self, listener_with_mock_socket, mock_socket_instance):
        """Test close() sets socket to None."""
        listener_with_mock_socket.socket = mock_socket_instance
        listener_with_mock_socket.close()

        assert listener_with_mock_socket.socket is None

    def test_close_handles_none_socket(self, listener_with_mock_socket):
        """Test close() handles case where socket is already None."""
        listener_with_mock_socket.socket = None

        # Should not raise any exception
        listener_with_mock_socket.close()

    def test_close_can_be_called_multiple_times(self, listener_with_mock_socket, mock_socket_instance):
        """Test close() can be called multiple times safely."""
        listener_with_mock_socket.socket = mock_socket_instance

        listener_with_mock_socket.close()
        listener_with_mock_socket.close()  # Should not raise

    def test_close_releases_port_for_rebinding(self):
        """
        TC-UDP-004: Test that close() releases the socket so a new listener
        can bind to the same port.
        """
        mock_sock1 = MagicMock(spec=socket.socket)
        mock_sock2 = MagicMock(spec=socket.socket)
        mock_sockets = [mock_sock1, mock_sock2]

        with patch('socket.socket', side_effect=mock_sockets):
            from src.telemetry.udp_listener import UDPListener

            # First listener binds to port
            listener1 = UDPListener(port=20777)
            mock_sock1.bind.assert_called_with(('0.0.0.0', 20777))

            # Close first listener
            listener1.close()
            mock_sock1.close.assert_called_once()
            assert listener1.socket is None

            # Second listener can bind to same port after close
            listener2 = UDPListener(port=20777)
            mock_sock2.bind.assert_called_with(('0.0.0.0', 20777))
            listener2.close()


# =============================================================================
# PACKET COUNT PROPERTY TESTS
# =============================================================================

class TestPacketCountProperty:
    """Tests for packet_count property."""

    def test_packet_count_property_returns_count(self, listener_with_mock_socket):
        """Test packet_count property returns _packet_count."""
        listener_with_mock_socket._packet_count = 42
        assert listener_with_mock_socket.packet_count == 42

    def test_packet_count_starts_at_zero(self, listener_with_mock_socket):
        """Test packet_count starts at zero."""
        assert listener_with_mock_socket.packet_count == 0

    def test_packet_count_increments_with_receives(self, listener_with_mock_socket, mock_socket_instance):
        """Test packet_count increments with successful receives."""
        listener_with_mock_socket.socket = mock_socket_instance

        assert listener_with_mock_socket.packet_count == 0
        listener_with_mock_socket.receive()
        assert listener_with_mock_socket.packet_count == 1
        listener_with_mock_socket.receive()
        assert listener_with_mock_socket.packet_count == 2


# =============================================================================
# CONSTANTS TESTS
# =============================================================================

class TestConstants:
    """Tests for UDPListener constants."""

    def test_default_port_constant(self):
        """Test DEFAULT_PORT is 20777 (F1 game port)."""
        from src.telemetry.udp_listener import UDPListener
        assert UDPListener.DEFAULT_PORT == 20777

    def test_buffer_size_constant(self):
        """Test BUFFER_SIZE is 2048 bytes."""
        from src.telemetry.udp_listener import UDPListener
        assert UDPListener.BUFFER_SIZE == 2048
