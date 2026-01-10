"""
Unit Tests for Packet Parser - INF-123

Ticket: As a developer, I want unit tests for the packet parser so that
        I can verify F1 telemetry packets are parsed correctly.

Test Design Techniques Used:
    - Equivalence partitioning (valid/invalid packets)
    - Boundary value analysis (g-force warning thresholds)
    - Error guessing (malformed data)

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
    Create a valid F1 24 packet header (29 bytes).
    Format: '<hBBBBBQfIIBB'
    """
    return struct.pack(
        '<hBBBBBQfIIBB',
        2024,       # packet_format (int16)
        24,         # game_year (uint8)
        1,          # game_major_version (uint8)
        0,          # game_minor_version (uint8)
        1,          # packet_version (uint8)
        0,          # packet_id (0 = motion packet) (uint8)
        12345678,   # session_uid (uint64)
        123.456,    # session_time (float)
        1000,       # frame_identifier (uint32)
        5000,       # overall_frame_identifier (uint32)
        0,          # player_car_index (uint8)
        255         # secondary_player_car_index (uint8)
    )


@pytest.fixture
def valid_motion_data():
    """
    Create valid motion data for one car (60 bytes).
    Format: '<ffffffhhhhhhffffff'
    """
    return struct.pack(
        '<ffffffhhhhhhffffff',
        100.0, 200.0, 0.5,      # worldPosition X, Y, Z
        50.0, 10.0, 0.0,        # worldVelocity X, Y, Z
        0, 1, 0,                # worldForwardDir (normalized int16)
        1, 0, 0,                # worldRightDir (normalized int16)
        0.5,                    # gForceLateral
        -1.2,                   # gForceLongitudinal
        1.0,                    # gForceVertical
        0.1,                    # yaw
        0.05,                   # pitch
        0.02                    # roll
    )


@pytest.fixture
def valid_motion_packet(valid_header, valid_motion_data):
    """Create a complete valid motion packet with 22 cars."""
    empty_car = b'\x00' * 60
    return valid_header + valid_motion_data + (empty_car * 21)


# =============================================================================
# HEADER PARSING TESTS
# =============================================================================

class TestParseHeader:
    """Tests for parse_header() method."""

    def test_valid_header_returns_dict(self, parser, valid_header):
        """Test that a valid header returns a dictionary with expected keys."""
        result = parser.parse_header(valid_header)
        assert result is not None
        assert isinstance(result, dict)
        assert result['packet_id'] == 0

    def test_header_too_short_returns_none(self, parser):
        """Test that header < 29 bytes returns None."""
        short_header = b'\x00' * 20
        result = parser.parse_header(short_header)
        assert result is None

    def test_empty_data_returns_none(self, parser):
        """Test that empty data returns None."""
        result = parser.parse_header(b'')
        assert result is None

    def test_header_extracts_packet_format(self, parser, valid_header):
        """Test packet format (2024) extraction."""
        result = parser.parse_header(valid_header)
        assert result['packet_format'] == 2024

    def test_header_extracts_game_year(self, parser, valid_header):
        """Test game year (24) extraction - F1 24 specific field."""
        result = parser.parse_header(valid_header)
        assert result['game_year'] == 24

    def test_header_extracts_player_car_index(self, parser, valid_header):
        """Test player car index extraction."""
        result = parser.parse_header(valid_header)
        assert result['player_car_index'] == 0

    def test_header_size_is_29_bytes(self, parser):
        """Test that HEADER_SIZE constant is 29 bytes for F1 24."""
        assert parser.HEADER_SIZE == 29


# =============================================================================
# MOTION PACKET PARSING TESTS
# =============================================================================

class TestParseMotionPacket:
    """Tests for parse_motion_packet() method."""

    def test_valid_packet_returns_telemetry_data(self, parser, valid_motion_packet):
        """Test valid motion packet returns TelemetryData instance."""
        result = parser.parse_motion_packet(valid_motion_packet)
        assert result is not None
        assert isinstance(result, TelemetryData)

    def test_non_motion_packet_returns_none(self, parser, valid_motion_data):
        """Test packet_id != 0 returns None."""
        non_motion_header = struct.pack(
            '<hBBBBBQfIIBB',
            2024, 24, 1, 0, 1,
            1,              # packet_id=1 (not motion)
            123, 1.0, 1, 1, 0, 255
        )
        packet = non_motion_header + valid_motion_data + (b'\x00' * 60 * 21)
        result = parser.parse_motion_packet(packet)
        assert result is None

    def test_extracts_g_force_lateral(self, parser, valid_motion_packet):
        """Test lateral G-force extraction."""
        result = parser.parse_motion_packet(valid_motion_packet)
        assert abs(result.g_force_lateral - 0.5) < 0.001

    def test_extracts_g_force_longitudinal(self, parser, valid_motion_packet):
        """Test longitudinal G-force extraction."""
        result = parser.parse_motion_packet(valid_motion_packet)
        assert abs(result.g_force_longitudinal - (-1.2)) < 0.001

    def test_extracts_g_force_vertical(self, parser, valid_motion_packet):
        """Test vertical G-force extraction."""
        result = parser.parse_motion_packet(valid_motion_packet)
        assert abs(result.g_force_vertical - 1.0) < 0.001

    def test_extracts_yaw(self, parser, valid_motion_packet):
        """Test yaw extraction."""
        result = parser.parse_motion_packet(valid_motion_packet)
        assert abs(result.yaw - 0.1) < 0.001

    def test_extracts_pitch(self, parser, valid_motion_packet):
        """Test pitch extraction."""
        result = parser.parse_motion_packet(valid_motion_packet)
        assert abs(result.pitch - 0.05) < 0.001

    def test_extracts_roll(self, parser, valid_motion_packet):
        """Test roll extraction."""
        result = parser.parse_motion_packet(valid_motion_packet)
        assert abs(result.roll - 0.02) < 0.001

    def test_extracts_correct_car_by_index(self, parser):
        """Test correct car data extracted by playerCarIndex."""
        header_car2 = struct.pack(
            '<hBBBBBQfIIBB',
            2024, 24, 1, 0, 1, 0, 123, 1.0, 1, 1,
            2,      # player_car_index = 2
            255
        )
        car0 = struct.pack('<ffffffhhhhhhffffff', 0,0,0,0,0,0,0,0,0,0,0,0, 0.1,0.1,1.0,0,0,0)
        car1 = struct.pack('<ffffffhhhhhhffffff', 0,0,0,0,0,0,0,0,0,0,0,0, 0.2,0.2,1.0,0,0,0)
        car2 = struct.pack('<ffffffhhhhhhffffff', 0,0,0,0,0,0,0,0,0,0,0,0, 2.5,-2.0,1.5,0,0,0)
        packet = header_car2 + car0 + car1 + car2 + (b'\x00' * 60 * 19)

        result = parser.parse_motion_packet(packet)
        assert abs(result.g_force_lateral - 2.5) < 0.001

    def test_invalid_player_index_returns_none(self, parser, valid_motion_data):
        """Test player_car_index >= MAX_CARS returns None."""
        header_invalid = struct.pack(
            '<hBBBBBQfIIBB',
            2024, 24, 1, 0, 1, 0, 123, 1.0, 1, 1,
            25,     # player_car_index = 25 (> MAX_CARS=22)
            255
        )
        packet = header_invalid + valid_motion_data + (b'\x00' * 60 * 21)
        result = parser.parse_motion_packet(packet)
        assert result is None

    def test_increments_packets_parsed_counter(self, parser, valid_motion_packet):
        """Test that successfully parsing increments packets_parsed counter."""
        initial_count = parser.stats['packets_parsed']
        parser.parse_motion_packet(valid_motion_packet)
        assert parser.stats['packets_parsed'] == initial_count + 1


# =============================================================================
# BOUNDARY VALUE TESTS - G-Force Warning Threshold
# =============================================================================

class TestGForceWarningThreshold:
    """Boundary value analysis for G-force warning threshold (10.0G)."""

    def test_warning_threshold_constant(self, parser):
        """Test G_FORCE_WARN_THRESHOLD is 10.0."""
        assert parser.G_FORCE_WARN_THRESHOLD == 10.0

    @pytest.mark.parametrize("g_lateral,g_longitudinal,g_vertical", [
        (0.0, 0.0, 1.0),
        (3.0, -2.0, 1.0),
        (-3.0, 2.0, 1.0),
        (5.0, -5.0, 1.5),
        (9.9, 9.9, 9.9),
    ])
    def test_normal_g_forces_parsed(self, parser, g_lateral, g_longitudinal, g_vertical):
        """Test normal G-force values are parsed."""
        header = struct.pack(
            '<hBBBBBQfIIBB', 2024, 24, 1, 0, 1, 0, 123, 1.0, 1, 1, 0, 255
        )
        motion_data = struct.pack(
            '<ffffffhhhhhhffffff',
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            g_lateral, g_longitudinal, g_vertical, 0, 0, 0
        )
        packet = header + motion_data + (b'\x00' * 60 * 21)

        result = parser.parse_motion_packet(packet)
        assert result is not None

    @pytest.mark.parametrize("extreme_value", [10.1, 15.0, -10.1, -15.0])
    def test_extreme_g_forces_still_parsed(self, parser, extreme_value, caplog):
        """Test extreme G-forces are parsed but trigger warning."""
        import logging
        caplog.set_level(logging.WARNING)

        header = struct.pack(
            '<hBBBBBQfIIBB', 2024, 24, 1, 0, 1, 0, 123, 1.0, 1, 1, 0, 255
        )
        motion_data = struct.pack(
            '<ffffffhhhhhhffffff',
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            extreme_value, 0.0, 1.0, 0, 0, 0
        )
        packet = header + motion_data + (b'\x00' * 60 * 21)

        result = parser.parse_motion_packet(packet)
        assert result is not None
        assert "Extreme G-force" in caplog.text


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Error guessing tests for malformed data."""

    def test_truncated_header_returns_none(self, parser):
        """Test packet shorter than header size returns None."""
        truncated = b'\x00' * 20
        result = parser.parse_motion_packet(truncated)
        assert result is None

    def test_truncated_motion_data_returns_none(self, parser):
        """Test packet with incomplete motion data returns None."""
        header = struct.pack(
            '<hBBBBBQfIIBB', 2024, 24, 1, 0, 1, 0, 123, 1.0, 1, 1, 0, 255
        )
        truncated = header + (b'\x00' * 30)
        result = parser.parse_motion_packet(truncated)
        assert result is None

    def test_random_bytes_handled_gracefully(self, parser):
        """Test random garbage data doesn't crash parser."""
        garbage = os.urandom(200)
        result = parser.parse_motion_packet(garbage)
        # Should not crash

    def test_increments_invalid_packets_counter(self, parser):
        """Test that invalid packets increment invalid_packets counter."""
        initial_invalid = parser.stats['invalid_packets']
        parser.parse_motion_packet(b'\x00' * 10)
        assert parser.stats['invalid_packets'] == initial_invalid + 1


# =============================================================================
# TELEMETRYDATA DATACLASS TESTS
# =============================================================================

class TestTelemetryData:
    """Tests for TelemetryData dataclass."""

    def test_telemetry_data_fields(self):
        """Test TelemetryData has all required fields."""
        data = TelemetryData(
            g_force_lateral=1.0,
            g_force_longitudinal=-2.0,
            g_force_vertical=1.0,
            yaw=0.1,
            pitch=0.05,
            roll=0.02
        )
        assert data.g_force_lateral == 1.0
        assert data.g_force_longitudinal == -2.0

    def test_telemetry_data_str_representation(self):
        """Test TelemetryData string representation."""
        data = TelemetryData(
            g_force_lateral=1.5,
            g_force_longitudinal=-2.5,
            g_force_vertical=1.0,
            yaw=0.0, pitch=0.0, roll=0.0
        )
        str_repr = str(data)
        assert "TelemetryData" in str_repr


# =============================================================================
# PARSER STATISTICS TESTS
# =============================================================================

class TestParserStats:
    """Tests for parser statistics tracking."""

    def test_stats_returns_dict(self, parser):
        """Test stats property returns dictionary."""
        stats = parser.stats
        assert isinstance(stats, dict)
        assert 'packets_parsed' in stats
        assert 'invalid_packets' in stats

    def test_initial_stats_are_zero(self):
        """Test new parser starts with zero counts."""
        fresh_parser = PacketParser()
        assert fresh_parser.stats['packets_parsed'] == 0
        assert fresh_parser.stats['invalid_packets'] == 0


# =============================================================================
# CONSTANTS TESTS
# =============================================================================

class TestParserConstants:
    """Tests for PacketParser constants."""

    def test_packet_id_motion_is_zero(self, parser):
        """Test PACKET_ID_MOTION constant is 0."""
        assert parser.PACKET_ID_MOTION == 0

    def test_header_size_matches_format(self, parser):
        """Test HEADER_SIZE matches struct calculation."""
        calculated_size = struct.calcsize('<hBBBBBQfIIBB')
        assert parser.HEADER_SIZE == calculated_size
        assert parser.HEADER_SIZE == 29

    def test_motion_data_size_is_60_bytes(self, parser):
        """Test MOTION_DATA_SIZE is 60 bytes per car."""
        assert parser.MOTION_DATA_SIZE == 60

    def test_max_cars_is_22(self, parser):
        """Test MAX_CARS is 22."""
        assert parser.MAX_CARS == 22
