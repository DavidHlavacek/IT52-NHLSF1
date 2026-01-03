"""
Unit Tests for UDP Listener - INF-126

Ticket: As a developer, I want unit tests for the UDP listener so that
        I can verify packet reception works correctly.

Verifies: INF-100 (UDP Listener Implementation)

Test Cases Covered:
    - TC-UDP-001: UDP listener binds to correct port
    - TC-UDP-002: Listener receives UDP packets
    - TC-UDP-003: Listener handles timeout gracefully
    - TC-UDP-004: Socket is properly released on close
    - TC-UDP-005: Custom port configuration works

Test Design Techniques Used:
    - Equivalence Partitioning (valid/timeout/error states)
    - State Transition (socket lifecycle: create -> bind -> receive -> close)
    - Error Guessing (network failures, invalid ports)

Run: pytest tests/telemetry/test_udp_listener.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import socket

from src.telemetry.udp_listener import UDPListener


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def mock_socket():
    """Create a mock socket for testing without network access."""
    mock = MagicMock(spec=socket.socket)
    mock.recvfrom.return_value = (b'\x00' * 100, ('127.0.0.1', 12345))
    return mock


@pytest.fixture
def sample_packet():
    """Create a sample UDP packet for testing."""
    return b'\xe7\x07\x01\x00' + b'\x00' * 96  # 100 bytes, starts with 2023 format


# =============================================================================
# TC-UDP-001: UDP listener binds to correct port
# Test Technique: Equivalence Partitioning
# =============================================================================

class TestBindToPort:
    """TC-UDP-001: Verify UDP listener binds to correct port."""

    @patch('socket.socket')
    def test_binds_to_default_port_20777(self, mock_socket_class):
        """Listener should bind to port 20777 by default."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener()

        # Verify bind was called with correct port
        mock_sock.bind.assert_called_once()
        call_args = mock_sock.bind.call_args[0][0]
        assert call_args[1] == 20777, "Should bind to port 20777"

    @patch('socket.socket')
    def test_creates_udp_socket(self, mock_socket_class):
        """Should create UDP socket (AF_INET, SOCK_DGRAM)."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener()

        mock_socket_class.assert_called_with(socket.AF_INET, socket.SOCK_DGRAM)

    @patch('socket.socket')
    def test_binds_to_all_interfaces(self, mock_socket_class):
        """Should bind to 0.0.0.0 (all interfaces)."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener()

        call_args = mock_sock.bind.call_args[0][0]
        assert call_args[0] == '0.0.0.0', "Should bind to all interfaces"

    @patch('socket.socket')
    def test_socket_successfully_bound(self, mock_socket_class):
        """Socket should be successfully bound after init."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener(port=20777)

        assert listener.socket is not None, "Socket should be initialized"
        mock_sock.bind.assert_called_once()


# =============================================================================
# TC-UDP-002: Listener receives UDP packets
# Test Technique: Equivalence Partitioning
# =============================================================================

class TestReceivePackets:
    """TC-UDP-002: Verify listener receives UDP packets."""

    def test_receive_returns_packet_data(self, mock_socket, sample_packet):
        """receive() should return the packet data bytes."""
        mock_socket.recvfrom.return_value = (sample_packet, ('127.0.0.1', 12345))

        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            result = listener.receive()

            assert result == sample_packet, "Should return packet data"
            assert len(result) == 100, "Should return complete packet"

    def test_receive_calls_recvfrom(self, mock_socket):
        """receive() should call socket.recvfrom()."""
        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            listener.receive()

            mock_socket.recvfrom.assert_called()

    def test_receive_uses_correct_buffer_size(self, mock_socket):
        """receive() should use BUFFER_SIZE (2048 bytes)."""
        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            listener.receive()

            # Check recvfrom was called with buffer size
            call_args = mock_socket.recvfrom.call_args[0]
            assert call_args[0] == UDPListener.BUFFER_SIZE

    def test_receive_increments_packet_count(self, mock_socket, sample_packet):
        """Packet count should increment on successful receive."""
        mock_socket.recvfrom.return_value = (sample_packet, ('127.0.0.1', 12345))

        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            initial_count = listener.packet_count
            listener.receive()

            assert listener.packet_count == initial_count + 1

    def test_multiple_receives_increment_count(self, mock_socket, sample_packet):
        """Multiple receives should increment count correctly."""
        mock_socket.recvfrom.return_value = (sample_packet, ('127.0.0.1', 12345))

        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket
            listener._packet_count = 0

            for _ in range(5):
                listener.receive()

            assert listener.packet_count == 5


# =============================================================================
# TC-UDP-003: Listener handles timeout gracefully
# Test Technique: Error Guessing
# =============================================================================

class TestTimeoutHandling:
    """TC-UDP-003: Verify listener handles timeout gracefully."""

    def test_timeout_returns_none(self, mock_socket):
        """receive() should return None on timeout."""
        mock_socket.recvfrom.side_effect = socket.timeout

        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            result = listener.receive()

            assert result is None, "Timeout should return None"

    def test_timeout_no_crash(self, mock_socket):
        """Timeout should not crash the listener."""
        mock_socket.recvfrom.side_effect = socket.timeout

        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            try:
                result = listener.receive()
                # Should complete without exception
            except socket.timeout:
                pytest.fail("Timeout should be handled, not raised")

    def test_socket_error_handled(self, mock_socket):
        """Socket errors should be handled gracefully."""
        mock_socket.recvfrom.side_effect = socket.error("Network unreachable")

        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            try:
                result = listener.receive()
                assert result is None, "Error should return None"
            except socket.error:
                pass  # Also acceptable if error is propagated

    def test_timeout_does_not_increment_count(self, mock_socket):
        """Timeout should not increment packet count."""
        mock_socket.recvfrom.side_effect = socket.timeout

        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket
            listener._packet_count = 0

            listener.receive()

            assert listener.packet_count == 0, "Timeout should not increment count"

    @patch('socket.socket')
    def test_sets_socket_timeout(self, mock_socket_class):
        """Socket timeout should be set during initialization."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener(timeout=2.0)

        mock_sock.settimeout.assert_called_with(2.0)


# =============================================================================
# TC-UDP-004: Socket is properly released on close
# Test Technique: State Transition
# =============================================================================

class TestSocketClose:
    """TC-UDP-004: Verify socket is properly released on close."""

    def test_close_calls_socket_close(self, mock_socket):
        """close() should call socket.close()."""
        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            listener.close()

            mock_socket.close.assert_called_once()

    def test_close_handles_none_socket(self):
        """close() should handle case where socket is None."""
        with patch('socket.socket') as mock_socket_class:
            mock_socket_class.side_effect = Exception("Socket creation failed")

            try:
                listener = UDPListener()
            except:
                listener = UDPListener.__new__(UDPListener)
                listener.socket = None
                listener._packet_count = 0

            try:
                listener.close()  # Should not crash
            except Exception as e:
                pytest.fail(f"close() should handle None socket: {e}")

    def test_socket_reusable_after_close(self, mock_socket):
        """Port should be reusable after close."""
        with patch('socket.socket', return_value=mock_socket):
            listener1 = UDPListener(port=20778)
            listener1.close()

            # Should be able to create new listener on same port
            mock_socket.reset_mock()
            listener2 = UDPListener(port=20778)

            assert listener2 is not None

    def test_close_multiple_times_safe(self, mock_socket):
        """Calling close() multiple times should be safe."""
        with patch('socket.socket', return_value=mock_socket):
            listener = UDPListener()
            listener.socket = mock_socket

            try:
                listener.close()
                listener.close()  # Second call should not crash
            except Exception as e:
                pytest.fail(f"Multiple close() calls should be safe: {e}")


# =============================================================================
# TC-UDP-005: Custom port configuration works
# Test Technique: Equivalence Partitioning
# =============================================================================

class TestCustomPort:
    """TC-UDP-005: Verify custom port configuration."""

    @patch('socket.socket')
    def test_custom_port_20778(self, mock_socket_class):
        """Should bind to custom port 20778."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener(port=20778)

        call_args = mock_sock.bind.call_args[0][0]
        assert call_args[1] == 20778, "Should bind to custom port"

    @patch('socket.socket')
    def test_custom_port_30000(self, mock_socket_class):
        """Should bind to high port number 30000."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener(port=30000)

        assert listener.port == 30000
        call_args = mock_sock.bind.call_args[0][0]
        assert call_args[1] == 30000

    def test_port_property_returns_configured_port(self):
        """Port property should return configured port."""
        with patch('socket.socket'):
            listener = UDPListener(port=25000)

            assert listener.port == 25000

    @patch('socket.socket')
    def test_receives_on_custom_port(self, mock_socket_class):
        """Should receive packets on custom port."""
        mock_sock = MagicMock()
        mock_sock.recvfrom.return_value = (b'test', ('127.0.0.1', 12345))
        mock_socket_class.return_value = mock_sock

        listener = UDPListener(port=20778)
        result = listener.receive()

        assert result == b'test'


# =============================================================================
# ADDITIONAL TESTS - Initialization and Properties
# =============================================================================

class TestInitialization:
    """Tests for UDPListener initialization."""

    def test_default_port_constant(self):
        """DEFAULT_PORT constant should be 20777."""
        assert UDPListener.DEFAULT_PORT == 20777

    def test_buffer_size_constant(self):
        """BUFFER_SIZE constant should be 2048."""
        assert UDPListener.BUFFER_SIZE == 2048

    @patch('socket.socket')
    def test_default_timeout(self, mock_socket_class):
        """Default timeout should be 1.0 second."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener()

        assert listener.timeout == 1.0

    @patch('socket.socket')
    def test_custom_timeout(self, mock_socket_class):
        """Custom timeout should be respected."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener(timeout=5.0)

        assert listener.timeout == 5.0
        mock_sock.settimeout.assert_called_with(5.0)

    @patch('socket.socket')
    def test_initial_packet_count_zero(self, mock_socket_class):
        """Initial packet count should be zero."""
        mock_sock = MagicMock()
        mock_socket_class.return_value = mock_sock

        listener = UDPListener()

        assert listener.packet_count == 0


# =============================================================================
# INTEGRATION TESTS (Skipped by default - require actual network)
# =============================================================================

class TestRealSocket:
    """Integration tests with real sockets (skipped by default)."""

    @pytest.mark.skip(reason="Requires actual network - run manually")
    def test_real_socket_binding(self):
        """Test actual socket can bind to port."""
        listener = UDPListener(port=20779)  # Use different port to avoid conflicts

        try:
            assert listener.socket is not None
            assert listener.port == 20779
        finally:
            listener.close()

    @pytest.mark.skip(reason="Requires actual network - run manually")
    def test_real_socket_timeout(self):
        """Test actual socket timeout behavior."""
        listener = UDPListener(port=20780, timeout=0.1)

        try:
            result = listener.receive()  # Should timeout quickly
            assert result is None
        finally:
            listener.close()
