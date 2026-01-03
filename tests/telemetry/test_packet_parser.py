"""
Unit Tests for Packet Parser - INF-123

Ticket: As a developer, I want unit tests for the packet parser so that
        I can verify F1 telemetry packets are parsed correctly.

Verifies: INF-103 (Packet Parser Implementation)

Test Cases Covered:
    - TC-PARSE-001: Valid motion packet (ID=0) parsed correctly
    - TC-PARSE-002: 24-byte header correctly unpacked
    - TC-PARSE-003: Correct car data extracted using player index
    - TC-PARSE-004: Undersized packet returns None
    - TC-PARSE-005: Non-motion packet (ID!=0) returns None
    - TC-PARSE-006: Extreme G-force values parsed correctly
    - TC-PARSE-007: Malformed packet handled gracefully

Test Design Techniques Used:
    - Equivalence Partitioning (valid/invalid packet types)
    - Boundary Value Analysis (G-force limits, packet sizes)
    - Error Guessing (malformed/corrupted data)

Run: pytest tests/telemetry/test_packet_parser.py -v
"""

import pytest
import struct
import os

from src.telemetry.packet_parser import PacketParser, TelemetryData


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def parser():
    """Create a PacketParser instance for testing."""
    return PacketParser()


@pytest.fixture
def valid_header():
    """
    Create a valid F1 2023 packet header (24 bytes).

    Format: '<HBBBBQfIBB'
    Fields: packetFormat, gameMajorVersion, gameMinorVersion, packetVersion,
            packetId, sessionUID, sessionTime, frameIdentifier,
            playerCarIndex, secondaryPlayerCarIndex
    """
    return struct.pack(
        '<HBBBBQfIBB',
        2023,           # packetFormat
        1,              # gameMajorVersion
        0,              # gameMinorVersion
        1,              # packetVersion
        0,              # packetId (0 = motion packet)
        123456789,      # sessionUID
        100.5,          # sessionTime
        5000,           # frameIdentifier
        0,              # playerCarIndex (first car)
        255             # secondaryPlayerCarIndex (none)
    )


@pytest.fixture
def valid_motion_data():
    """
    Create valid motion data for one car (60 bytes).

    Format: '<ffffffhhhhhhffffff'
    Fields: worldPos(x,y,z), worldVel(x,y,z), forwardDir(x,y,z),
            rightDir(x,y,z), gForceLat, gForceLong, gForceVert, yaw, pitch, roll
    """
    return struct.pack(
        '<ffffffhhhhhhffffff',
        100.0, 200.0, 0.5,      # worldPosition X, Y, Z
        50.0, 10.0, 0.0,        # worldVelocity X, Y, Z
        0, 1, 0,                # worldForwardDir (normalized int16)
        1, 0, 0,                # worldRightDir (normalized int16)
        0.5,                    # gForceLateral (turning right)
        -1.2,                   # gForceLongitudinal (braking)
        1.0,                    # gForceVertical (normal gravity)
        0.1,                    # yaw
        0.05,                   # pitch
        0.02                    # roll
    )


@pytest.fixture
def empty_car_data():
    """Create empty/zeroed motion data for padding (60 bytes)."""
    return b'\x00' * 60


@pytest.fixture
def valid_motion_packet(valid_header, valid_motion_data, empty_car_data):
    """
    Create a complete valid motion packet with 22 cars.
    Player car is at index 0 with valid data, rest are empty.
    """
    return valid_header + valid_motion_data + (empty_car_data * 21)


# =============================================================================
# TC-PARSE-001: Valid motion packet (ID=0) is parsed correctly
# Test Technique: Equivalence Partitioning
# =============================================================================

class TestValidMotionPacket:
    """TC-PARSE-001: Verify valid motion packet parsing."""

    def test_valid_packet_returns_telemetry_data(self, parser, valid_motion_packet):
        """Valid motion packet should return TelemetryData object."""
        result = parser.parse_motion_packet(valid_motion_packet)

        assert result is not None, "Valid packet should not return None"
        assert isinstance(result, TelemetryData), "Should return TelemetryData instance"

    def test_returns_correct_g_force_values(self, parser, valid_motion_packet):
        """Parsed G-force values should match input data."""
        result = parser.parse_motion_packet(valid_motion_packet)

        assert result is not None
        assert abs(result.g_force_lateral - 0.5) < 0.001, "Lateral G-force mismatch"
        assert abs(result.g_force_longitudinal - (-1.2)) < 0.001, "Longitudinal G-force mismatch"
        assert abs(result.g_force_vertical - 1.0) < 0.001, "Vertical G-force mismatch"

    def test_returns_correct_orientation_values(self, parser, valid_motion_packet):
        """Parsed orientation values should match input data."""
        result = parser.parse_motion_packet(valid_motion_packet)

        assert result is not None
        assert abs(result.yaw - 0.1) < 0.001, "Yaw mismatch"
        assert abs(result.pitch - 0.05) < 0.001, "Pitch mismatch"
        assert abs(result.roll - 0.02) < 0.001, "Roll mismatch"


# =============================================================================
# TC-PARSE-002: 24-byte header is correctly unpacked
# Test Technique: Boundary Value Analysis
# =============================================================================

class TestHeaderParsing:
    """TC-PARSE-002: Verify header parsing."""

    def test_header_returns_dict(self, parser, valid_header):
        """Valid header should return a dictionary."""
        result = parser.parse_header(valid_header)

        assert result is not None, "Valid header should not return None"
        assert isinstance(result, dict), "Should return dictionary"

    def test_extracts_packet_format(self, parser, valid_header):
        """Should extract packet format (2023)."""
        result = parser.parse_header(valid_header)

        assert result is not None
        assert result['packet_format'] == 2023, "Packet format should be 2023"

    def test_extracts_packet_id(self, parser, valid_header):
        """Should extract packet ID at byte 5."""
        result = parser.parse_header(valid_header)

        assert result is not None
        assert result['packet_id'] == 0, "Packet ID should be 0 (motion)"

    def test_extracts_player_car_index(self, parser, valid_header):
        """Should extract player car index."""
        result = parser.parse_header(valid_header)

        assert result is not None
        assert result['player_car_index'] == 0, "Player car index should be 0"

    def test_header_exactly_24_bytes(self, parser):
        """Header format should be exactly 24 bytes."""
        assert PacketParser.HEADER_SIZE == 24, "Header size should be 24 bytes"


# =============================================================================
# TC-PARSE-003: Correct car data is extracted using player index
# Test Technique: Equivalence Partitioning
# =============================================================================

class TestPlayerCarIndex:
    """TC-PARSE-003: Verify correct car extraction by player index."""

    def test_extracts_car_at_index_0(self, parser, valid_header, valid_motion_data, empty_car_data):
        """Should extract data for car at index 0."""
        packet = valid_header + valid_motion_data + (empty_car_data * 21)
        result = parser.parse_motion_packet(packet)

        assert result is not None
        assert abs(result.g_force_lateral - 0.5) < 0.001

    def test_extracts_car_at_index_5(self, parser, empty_car_data):
        """Should extract data for car at index 5 (middle of grid)."""
        # Header with playerCarIndex = 5
        header_car5 = struct.pack(
            '<HBBBBQfIBB',
            2023, 1, 0, 1, 0, 123, 1.0, 1, 5, 255
        )

        # Car 5 has unique G-force values
        car5_data = struct.pack(
            '<ffffffhhhhhhffffff',
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            2.5,    # gForceLateral - unique value
            -2.0,   # gForceLongitudinal - unique value
            1.5,    # gForceVertical
            0, 0, 0
        )

        # Build packet: header + 5 empty cars + car5 + 16 empty cars
        packet = header_car5 + (empty_car_data * 5) + car5_data + (empty_car_data * 16)

        result = parser.parse_motion_packet(packet)

        assert result is not None
        assert abs(result.g_force_lateral - 2.5) < 0.001, "Should extract car 5 lateral G"
        assert abs(result.g_force_longitudinal - (-2.0)) < 0.001, "Should extract car 5 longitudinal G"

    def test_extracts_car_at_index_21(self, parser, empty_car_data):
        """Should extract data for car at index 21 (last car)."""
        # Header with playerCarIndex = 21
        header_car21 = struct.pack(
            '<HBBBBQfIBB',
            2023, 1, 0, 1, 0, 123, 1.0, 1, 21, 255
        )

        car21_data = struct.pack(
            '<ffffffhhhhhhffffff',
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            -1.5, 3.0, 0.8, 0, 0, 0
        )

        packet = header_car21 + (empty_car_data * 21) + car21_data

        result = parser.parse_motion_packet(packet)

        assert result is not None
        assert abs(result.g_force_lateral - (-1.5)) < 0.001


# =============================================================================
# TC-PARSE-004: Undersized packet returns None
# Test Technique: Boundary Value Analysis
# =============================================================================

class TestUndersizedPacket:
    """TC-PARSE-004: Verify undersized packets are handled."""

    def test_packet_20_bytes_returns_none(self, parser):
        """Packet with only 20 bytes should return None."""
        short_packet = b'\x00' * 20
        result = parser.parse_motion_packet(short_packet)

        assert result is None, "Undersized packet should return None"

    def test_empty_packet_returns_none(self, parser):
        """Empty packet should return None."""
        result = parser.parse_motion_packet(b'')

        assert result is None, "Empty packet should return None"

    def test_header_only_returns_none(self, parser, valid_header):
        """Header without motion data should return None."""
        result = parser.parse_motion_packet(valid_header)

        assert result is None, "Header-only packet should return None"

    def test_truncated_motion_data_returns_none(self, parser, valid_header):
        """Truncated motion data should return None."""
        # Header (24) + partial motion data (30 bytes instead of 60)
        truncated = valid_header + (b'\x00' * 30)
        result = parser.parse_motion_packet(truncated)

        assert result is None, "Truncated motion data should return None"


# =============================================================================
# TC-PARSE-005: Non-motion packet (ID!=0) returns None
# Test Technique: Equivalence Partitioning
# =============================================================================

class TestNonMotionPacket:
    """TC-PARSE-005: Verify non-motion packets return None."""

    def test_session_packet_returns_none(self, parser, valid_motion_data, empty_car_data):
        """Packet with ID=1 (session) should return None."""
        header_session = struct.pack(
            '<HBBBBQfIBB',
            2023, 1, 0, 1, 1, 123, 1.0, 1, 0, 255  # packetId = 1
        )
        packet = header_session + valid_motion_data + (empty_car_data * 21)

        result = parser.parse_motion_packet(packet)

        assert result is None, "Session packet (ID=1) should return None"

    def test_lap_data_packet_returns_none(self, parser, valid_motion_data, empty_car_data):
        """Packet with ID=2 (lap data) should return None."""
        header_lap = struct.pack(
            '<HBBBBQfIBB',
            2023, 1, 0, 1, 2, 123, 1.0, 1, 0, 255  # packetId = 2
        )
        packet = header_lap + valid_motion_data + (empty_car_data * 21)

        result = parser.parse_motion_packet(packet)

        assert result is None, "Lap data packet (ID=2) should return None"

    def test_telemetry_packet_returns_none(self, parser, valid_motion_data, empty_car_data):
        """Packet with ID=6 (car telemetry) should return None."""
        header_telemetry = struct.pack(
            '<HBBBBQfIBB',
            2023, 1, 0, 1, 6, 123, 1.0, 1, 0, 255  # packetId = 6
        )
        packet = header_telemetry + valid_motion_data + (empty_car_data * 21)

        result = parser.parse_motion_packet(packet)

        assert result is None, "Telemetry packet (ID=6) should return None"


# =============================================================================
# TC-PARSE-006: Extreme G-force values are parsed correctly
# Test Technique: Boundary Value Analysis
# =============================================================================

class TestExtremeGForce:
    """TC-PARSE-006: Verify extreme G-force values at boundaries."""

    @pytest.mark.parametrize("g_lateral,g_longitudinal", [
        (0.0, 0.0),       # Zero G (stationary)
        (6.0, 6.0),       # Maximum positive
        (-6.0, -6.0),     # Maximum negative
        (5.9, -5.9),      # Just under limits
        (3.0, -3.0),      # Typical racing values
    ])
    def test_valid_g_force_range(self, parser, g_lateral, g_longitudinal, empty_car_data):
        """G-forces within +/-6G range should parse correctly."""
        header = struct.pack(
            '<HBBBBQfIBB',
            2023, 1, 0, 1, 0, 123, 1.0, 1, 0, 255
        )

        motion_data = struct.pack(
            '<ffffffhhhhhhffffff',
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            g_lateral, g_longitudinal, 1.0, 0, 0, 0
        )

        packet = header + motion_data + (empty_car_data * 21)
        result = parser.parse_motion_packet(packet)

        assert result is not None, f"G-force ({g_lateral}, {g_longitudinal}) should be valid"
        assert abs(result.g_force_lateral - g_lateral) < 0.001
        assert abs(result.g_force_longitudinal - g_longitudinal) < 0.001

    def test_positive_6g_boundary(self, parser, empty_car_data):
        """G-force at +6.0 (upper boundary) should be valid."""
        header = struct.pack('<HBBBBQfIBB', 2023, 1, 0, 1, 0, 123, 1.0, 1, 0, 255)
        motion_data = struct.pack(
            '<ffffffhhhhhhffffff',
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            6.0, 6.0, 1.0, 0, 0, 0
        )
        packet = header + motion_data + (empty_car_data * 21)

        result = parser.parse_motion_packet(packet)

        assert result is not None, "+6G should be within valid range"

    def test_negative_6g_boundary(self, parser, empty_car_data):
        """G-force at -6.0 (lower boundary) should be valid."""
        header = struct.pack('<HBBBBQfIBB', 2023, 1, 0, 1, 0, 123, 1.0, 1, 0, 255)
        motion_data = struct.pack(
            '<ffffffhhhhhhffffff',
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            -6.0, -6.0, 1.0, 0, 0, 0
        )
        packet = header + motion_data + (empty_car_data * 21)

        result = parser.parse_motion_packet(packet)

        assert result is not None, "-6G should be within valid range"


# =============================================================================
# TC-PARSE-007: Malformed packet data is handled gracefully
# Test Technique: Error Guessing
# =============================================================================

class TestMalformedPacket:
    """TC-PARSE-007: Verify malformed packets are handled gracefully."""

    def test_random_garbage_no_crash(self, parser):
        """Random bytes should not crash the parser."""
        garbage = os.urandom(200)

        try:
            result = parser.parse_motion_packet(garbage)
            # Should return None or raise handled exception
            assert result is None or isinstance(result, TelemetryData)
        except (struct.error, ValueError):
            pass  # Acceptable - handled exception
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    def test_corrupted_header_no_crash(self, parser):
        """Corrupted header should not crash."""
        corrupted = b'\xff' * 24 + b'\x00' * 60 * 22

        try:
            result = parser.parse_motion_packet(corrupted)
        except (struct.error, ValueError):
            pass  # Acceptable
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    def test_none_input_handled(self, parser):
        """None input should be handled gracefully."""
        try:
            result = parser.parse_motion_packet(None)
            assert result is None
        except TypeError:
            pass  # Acceptable - explicit type check
        except Exception as e:
            pytest.fail(f"Unexpected exception for None: {type(e).__name__}: {e}")

    def test_non_bytes_input_handled(self, parser):
        """Non-bytes input should be handled gracefully."""
        try:
            result = parser.parse_motion_packet("not bytes")
            assert result is None
        except (TypeError, AttributeError):
            pass  # Acceptable
        except Exception as e:
            pytest.fail(f"Unexpected exception: {type(e).__name__}: {e}")

    def test_partial_struct_data_handled(self, parser):
        """Packet that partially unpacks should be handled."""
        # Valid header but motion data that won't unpack correctly
        header = struct.pack('<HBBBBQfIBB', 2023, 1, 0, 1, 0, 123, 1.0, 1, 0, 255)
        bad_motion = b'\x00' * 59  # 59 bytes instead of 60

        try:
            result = parser.parse_motion_packet(header + bad_motion)
            assert result is None
        except struct.error:
            pass  # Acceptable


# =============================================================================
# TELEMETRY DATA CLASS TESTS
# =============================================================================

class TestTelemetryData:
    """Tests for TelemetryData dataclass."""

    def test_telemetry_data_creation(self):
        """TelemetryData should be creatable with required fields."""
        data = TelemetryData(
            g_force_lateral=0.5,
            g_force_longitudinal=-1.0,
            g_force_vertical=1.0,
            yaw=0.1,
            pitch=0.05,
            roll=0.02
        )

        assert data.g_force_lateral == 0.5
        assert data.g_force_longitudinal == -1.0
        assert data.g_force_vertical == 1.0

    def test_telemetry_data_str(self):
        """TelemetryData __str__ should return readable format."""
        data = TelemetryData(
            g_force_lateral=0.5,
            g_force_longitudinal=-1.0,
            g_force_vertical=1.0,
            yaw=0.1,
            pitch=0.05,
            roll=0.02
        )

        str_repr = str(data)
        assert "g_lat" in str_repr or "lateral" in str_repr.lower()


# =============================================================================
# PARSER STATISTICS TESTS
# =============================================================================

class TestParserStats:
    """Tests for parser statistics tracking."""

    def test_initial_stats_zero(self, parser):
        """Initial statistics should be zero."""
        stats = parser.stats

        assert stats['packets_parsed'] == 0
        assert stats['invalid_packets'] == 0
