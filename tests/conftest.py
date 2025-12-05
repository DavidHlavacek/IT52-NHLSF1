"""
Pytest Configuration - Shared Fixtures

This file contains shared fixtures used across all test modules.
"""

import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def sample_telemetry():
    """Create sample telemetry data for testing."""
    from src.telemetry.packet_parser import TelemetryData
    return TelemetryData(
        g_force_lateral=0.5,
        g_force_longitudinal=-1.0,
        g_force_vertical=1.0,
        yaw=0.1,
        pitch=0.05,
        roll=0.02
    )
