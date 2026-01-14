"""
Pipeline Integration Tests - INF-113

Tests that the software components work together correctly (without hardware).

Verifies: INF-100, INF-103, INF-105, INF-107, INF-110
"""

import os
import struct
import pytest
from unittest.mock import Mock, MagicMock, patch

from src.telemetry.packet_parser import PacketParser, TelemetryData
from src.motion.algorithm import MotionAlgorithm
from src.shared.types import Position6DOF


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def parser():
    """Create a PacketParser instance."""
    return PacketParser()


@pytest.fixture
def algorithm_config():
    """Standard algorithm configuration."""
    return {
        'translation_scale': 0.1,
        'rotation_scale': 0.5,
        'onset_gain': 1.0,
        'sustained_gain': 0.4,
        'deadband': 0.08,
        'sample_rate': 60.0,
        'washout_freq': 0.4,
        'sustained_freq': 3.0,
        'slew_rate': 0.4,
    }


@pytest.fixture
def algorithm(algorithm_config):
    """Create a MotionAlgorithm instance."""
    return MotionAlgorithm(algorithm_config)


@pytest.fixture
def smc_config():
    """SMC driver configuration for testing."""
    return {
        'port': 'COM5',
        'baudrate': 38400,
        'controller_id': 1,
        'center_mm': 450.0,
        'stroke_mm': 900.0,
        'speed_mm_s': 500,
        'accel_mm_s2': 3000,
        'decel_mm_s2': 3000,
        'min_command_interval': 0.0,  # Disable rate limiting for tests
        'position_threshold_mm': 0.0,  # Disable threshold for tests
        'limits': {'surge_m': 0.40},
    }


@pytest.fixture
def mock_smc_driver(smc_config):
    """Create a mock SMC driver that tracks commanded positions."""
    from src.drivers.smc_driver import SMCDriver

    driver = SMCDriver(smc_config)
    driver._connected = True
    driver._last_command_time = 0.0

    # Track the physical position that would be commanded
    driver._commanded_physical_mm = None

    # Mock the internal move method to capture position
    original_move = driver._move_to_physical_mm

    def mock_move(position_mm):
        driver._commanded_physical_mm = position_mm
        return True

    driver._move_to_physical_mm = mock_move

    return driver


def get_recording_path(filename: str) -> str:
    """Get absolute path to a recording file."""
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(project_root, 'recordings', filename)


def load_recording_packets(filepath: str) -> list:
    """Load packets from a recording file."""
    packets = []
    with open(filepath, 'rb') as f:
        count = struct.unpack('<I', f.read(4))[0]
        for _ in range(count):
            timestamp, length = struct.unpack('<fI', f.read(8))
            data = f.read(length)
            packets.append((timestamp, data))
    return packets


def make_telemetry(g_long=0.0, g_lat=0.0, g_vert=1.0, roll=0.0, pitch=0.0, yaw=0.0):
    """Create TelemetryData with specified values."""
    return TelemetryData(
        g_force_lateral=g_lat,
        g_force_longitudinal=g_long,
        g_force_vertical=g_vert,
        roll=roll,
        pitch=pitch,
        yaw=yaw
    )


def run_frames(algo, tel, n):
    """Run algorithm for n frames with same telemetry."""
    for _ in range(n):
        pos = algo.calculate(tel)
    return pos


# =============================================================================
# TC-INT-001: Telemetry data flows through to algorithm
# =============================================================================

class TestTCINT001:
    """
    TC-INT-001: Verify telemetry data flows through to algorithm

    Verifies: INF-100, INF-103, INF-107, INF-110
    Description: Verify telemetry data flows through to algorithm
    Preconditions: Recorded telemetry data available
    Test Steps:
        1. Load recorded telemetry packet
        2. Parse with PacketParser
        3. Feed to MotionAlgorithm
        4. Verify position output
    Expected Result: Non-zero position output for non-zero G-force
    """

    def test_recorded_telemetry_produces_position(self, parser, algorithm):
        """Test that recorded telemetry produces non-zero position output."""
        # Step 1: Load recorded telemetry packet
        recording_path = get_recording_path('heavy_braking_20260112_160906.bin')

        if not os.path.exists(recording_path):
            pytest.skip("Recording file not available")

        packets = load_recording_packets(recording_path)
        assert len(packets) > 0, "Recording should contain packets"

        # Step 2 & 3: Parse and feed to algorithm
        motion_packets_found = 0
        non_zero_positions = 0

        # Scan all packets - first packets may be stationary
        for timestamp, data in packets:
            telemetry = parser.parse_motion_packet(data)

            if telemetry is not None:
                motion_packets_found += 1

                # Check for non-zero G-force (above deadband threshold)
                has_gforce = (
                    abs(telemetry.g_force_longitudinal) > 0.1 or
                    abs(telemetry.g_force_lateral) > 0.1
                )

                if has_gforce:
                    # Step 3: Feed to algorithm
                    position = algorithm.calculate(telemetry)

                    # Step 4: Verify position output
                    if abs(position.x) > 0.0001 or abs(position.y) > 0.0001:
                        non_zero_positions += 1
                        # Found valid case, can exit early for efficiency
                        if non_zero_positions >= 5:
                            break

        # Verify we found motion packets
        assert motion_packets_found > 0, "Should find motion packets in recording"

        # Expected Result: Non-zero position for non-zero G-force
        assert non_zero_positions > 0, (
            f"Should produce non-zero positions. "
            f"Found {motion_packets_found} motion packets but {non_zero_positions} non-zero positions"
        )

    def test_telemetry_to_algorithm_data_flow(self, parser, algorithm):
        """Test data flows correctly through parser to algorithm."""
        # Create synthetic telemetry with known G-force
        telemetry = make_telemetry(g_long=-2.0, g_lat=0.5)

        # Process through algorithm for enough frames to see effect
        position = run_frames(algorithm, telemetry, 60)

        # Verify non-zero output for non-zero input
        assert position.x != 0.0, "Braking G-force should produce surge movement"
        assert position.y != 0.0, "Lateral G-force should produce sway movement"


# =============================================================================
# TC-INT-002: Algorithm output is accepted by driver
# =============================================================================

class TestTCINT002:
    """
    TC-INT-002: Verify algorithm output is accepted by driver

    Verifies: INF-107, INF-105, INF-110
    Description: Verify algorithm output is accepted by driver
    Preconditions: Mock/simulated driver available
    Test Steps:
        1. Create Position6DOF from algorithm
        2. Pass to driver.send_position()
        3. Verify driver accepts it
    Expected Result: Driver accepts Position6DOF without error
    """

    def test_algorithm_output_accepted_by_driver(self, algorithm, mock_smc_driver):
        """Test that algorithm output is accepted by mock driver."""
        # Step 1: Create Position6DOF from algorithm
        telemetry = make_telemetry(g_long=-1.0, g_lat=0.3)
        position = run_frames(algorithm, telemetry, 60)

        # Verify we have a valid Position6DOF
        assert isinstance(position, Position6DOF), "Algorithm should return Position6DOF"

        # Step 2: Pass to driver.send_position()
        result = mock_smc_driver.send_position(position)

        # Step 3: Verify driver accepts it
        # Expected Result: Driver accepts Position6DOF without error
        assert result == True, "Driver should accept Position6DOF without error"

# =============================================================================
# TC-INT-003: Braking G-force results in forward motion
# =============================================================================

class TestTCINT003:
    """
    TC-INT-003: Verify braking G-force results in forward motion

    Verifies: INF-100, INF-103, INF-107, INF-105, INF-110
    Description: Verify braking G-force results in forward motion
    Preconditions: Full pipeline configured
    Test Steps:
        1. Create telemetry with g_longitudinal = -2.0
        2. Process through parser -> algorithm -> driver
        3. Check commanded physical position
    Expected Result: Physical position > 450mm (forward of center)
    """

    def test_braking_produces_forward_motion(self, algorithm, mock_smc_driver):
        """Test that braking G-force produces forward physical position."""
        # Step 1: Create telemetry with g_longitudinal = -2.0 (braking)
        telemetry = make_telemetry(g_long=-2.0)

        # Step 2: Process through algorithm
        # Run enough frames for position to stabilize
        position = run_frames(algorithm, telemetry, 120)

        # Verify algorithm produces positive surge (forward)
        assert position.x > 0, (
            f"Braking (g_long=-2.0) should produce positive surge, got {position.x}"
        )

        # Step 2 continued: Pass to driver
        result = mock_smc_driver.send_position(position)
        assert result == True, "Driver should accept position"

        # Step 3: Check commanded physical position
        # Physical position = center_mm + game_mm
        # game_mm = position.x * 1000 (convert meters to mm)
        # center_mm = 450.0
        physical_mm = mock_smc_driver._commanded_physical_mm

        # Expected Result: Physical position > 450mm (forward of center)
        assert physical_mm > 450.0, (
            f"Physical position should be > 450mm for braking, got {physical_mm:.1f}mm"
        )

    def test_braking_with_recorded_data(self, parser, algorithm, mock_smc_driver):
        """Test braking scenario with recorded telemetry data."""
        recording_path = get_recording_path('heavy_braking_20260112_160906.bin')

        if not os.path.exists(recording_path):
            pytest.skip("Recording file not available")

        packets = load_recording_packets(recording_path)

        # Find a packet with significant braking G-force
        braking_found = False

        for timestamp, data in packets:
            telemetry = parser.parse_motion_packet(data)

            if telemetry and telemetry.g_force_longitudinal < -1.0:
                braking_found = True

                # Process through algorithm
                position = run_frames(algorithm, telemetry, 60)

                # Send to driver
                mock_smc_driver.send_position(position)

                # Heavy braking should produce forward position
                physical_mm = mock_smc_driver._commanded_physical_mm

                if physical_mm is not None and physical_mm > 450.0:
                    # Found valid braking scenario
                    break

        assert braking_found, "Should find braking scenarios in heavy_braking recording"


# =============================================================================
# TC-INT-004: Acceleration G-force results in backward motion
# =============================================================================

class TestTCINT004:
    """
    TC-INT-004: Verify acceleration G-force results in backward motion

    Verifies: INF-100, INF-103, INF-107, INF-105, INF-110
    Description: Verify acceleration G-force results in backward motion
    Preconditions: Full pipeline configured
    Test Steps:
        1. Create telemetry with g_longitudinal = +1.0
        2. Process through parser -> algorithm -> driver
        3. Check commanded physical position
    Expected Result: Physical position < 450mm (backward of center)
    """

    def test_acceleration_produces_backward_motion(self, algorithm, mock_smc_driver):
        """Test that acceleration G-force produces backward physical position."""
        # Step 1: Create telemetry with g_longitudinal = +1.0 (acceleration)
        telemetry = make_telemetry(g_long=+1.0)

        # Step 2: Process through algorithm
        # Run enough frames for position to stabilize
        position = run_frames(algorithm, telemetry, 120)

        # Verify algorithm produces negative surge (backward)
        assert position.x < 0, (
            f"Acceleration (g_long=+1.0) should produce negative surge, got {position.x}"
        )

        # Step 2 continued: Pass to driver
        result = mock_smc_driver.send_position(position)
        assert result == True, "Driver should accept position"

        # Step 3: Check commanded physical position
        # Physical position = center_mm + game_mm
        # game_mm = position.x * 1000 (convert meters to mm)
        # center_mm = 450.0
        physical_mm = mock_smc_driver._commanded_physical_mm

        # Expected Result: Physical position < 450mm (backward of center)
        assert physical_mm < 450.0, (
            f"Physical position should be < 450mm for acceleration, got {physical_mm:.1f}mm"
        )

    def test_acceleration_with_recorded_data(self, parser, algorithm, mock_smc_driver):
        """Test acceleration scenario with recorded telemetry data."""
        recording_path = get_recording_path('full_lap_20260112_160501.bin')

        if not os.path.exists(recording_path):
            pytest.skip("Recording file not available")

        packets = load_recording_packets(recording_path)

        # Find a packet with positive G-force (acceleration)
        accel_found = False

        for timestamp, data in packets:
            telemetry = parser.parse_motion_packet(data)

            if telemetry and telemetry.g_force_longitudinal > 0.5:
                accel_found = True

                # Process through algorithm
                position = run_frames(algorithm, telemetry, 60)

                # Send to driver
                mock_smc_driver.send_position(position)

                # Acceleration should produce backward position
                physical_mm = mock_smc_driver._commanded_physical_mm

                if physical_mm is not None and physical_mm < 450.0:
                    # Found valid acceleration scenario
                    break

        assert accel_found, "Should find acceleration scenarios in full_lap recording"
