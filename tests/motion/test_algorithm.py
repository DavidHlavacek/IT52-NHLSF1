"""
Unit Tests for Motion Algorithm - INF-124
Covers: INF-107, INF-147, INF-148
"""

import pytest
from src.motion.algorithm import MotionAlgorithm
from src.telemetry.packet_parser import TelemetryData
from src.shared.types import Position6DOF


@pytest.fixture
def config():
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
def algo(config):
    return MotionAlgorithm(config)


def make_telemetry(g_long=0.0, g_lat=0.0, g_vert=1.0, roll=0.0, pitch=0.0, yaw=0.0):
    return TelemetryData(
        g_force_lateral=g_lat,
        g_force_longitudinal=g_long,
        g_force_vertical=g_vert,
        roll=roll,
        pitch=pitch,
        yaw=yaw
    )


def run_frames(algo, tel, n):
    for _ in range(n):
        pos = algo.calculate(tel)
    return pos


# TC-ALGO-001
def test_zero_gforce_returns_center(algo):
    pos = run_frames(algo, make_telemetry(g_long=0.0), 60)

    assert abs(pos.x) < 0.001
    assert abs(pos.y) < 0.001


# TC-ALGO-002
def test_positive_g_maps_to_negative_position(algo):
    pos = run_frames(algo, make_telemetry(g_long=1.0), 180)

    assert pos.x < 0


# TC-ALGO-003
def test_negative_g_maps_to_positive_position(algo):
    pos = run_frames(algo, make_telemetry(g_long=-2.0), 180)

    assert pos.x > 0


# TC-ALGO-005
def test_gforce_below_deadband_ignored(algo):
    pos = run_frames(algo, make_telemetry(g_long=0.05), 60)  # below 0.08 deadband

    assert abs(pos.x) < 0.001


# TC-ALGO-006
def test_highpass_onset_cue(config):
    config['sustained_gain'] = 0.0  # isolate high-pass
    algo = MotionAlgorithm(config)

    run_frames(algo, make_telemetry(g_long=0.0), 30)
    pos = algo.calculate(make_telemetry(g_long=-2.0))

    assert pos.x > 0.001


# TC-ALGO-007
def test_highpass_washes_out(config):
    config['sustained_gain'] = 0.0  # isolate high-pass
    config['slew_rate'] = 10.0  # disable slew limiting
    algo = MotionAlgorithm(config)

    tel = make_telemetry(g_long=-2.0)

    run_frames(algo, tel, 20)
    early = algo.calculate(tel)
    run_frames(algo, tel, 160)
    late = algo.calculate(tel)

    assert abs(late.x) < abs(early.x)


# TC-ALGO-008
def test_lowpass_sustained(config):
    config['onset_gain'] = 0.0  # isolate low-pass
    config['slew_rate'] = 10.0  # disable slew limiting
    algo = MotionAlgorithm(config)

    tel = make_telemetry(g_long=-2.0)
    pos = run_frames(algo, tel, 180)

    assert pos.x > 0.01


# TC-ALGO-009
def test_slew_rate_limits_change(config):
    algo = MotionAlgorithm(config)
    max_delta = config['slew_rate'] / config['sample_rate']

    run_frames(algo, make_telemetry(g_long=0.0), 10)
    pos = algo.calculate(make_telemetry(g_long=-3.0))

    assert abs(pos.x) <= max_delta + 0.001


# TC-ALGO-010
def test_slew_rate_ramps_position(config):
    config['onset_gain'] = 0.0  # disable high-pass
    config['sustained_gain'] = 1.0  # full low-pass
    algo = MotionAlgorithm(config)

    tel = make_telemetry(g_long=-2.0)

    pos1 = algo.calculate(tel)
    pos2 = run_frames(algo, tel, 30)

    assert pos2.x > pos1.x


# TC-ALGO-011
def test_reset_clears_state(algo):
    run_frames(algo, make_telemetry(g_long=-2.0), 60)
    algo.reset()
    pos = run_frames(algo, make_telemetry(g_long=0.0), 60)

    assert abs(pos.x) < 0.001


# TC-ALGO-012
def test_six_dof_output(algo, config):
    tel = make_telemetry(
        g_long=-1.0, g_lat=0.5, g_vert=1.2,
        roll=0.1, pitch=0.2, yaw=0.3
    )
    pos = run_frames(algo, tel, 60)

    assert isinstance(pos, Position6DOF)
    rot_scale = config['rotation_scale']
    assert pos.roll == 0.1 * rot_scale
    assert pos.pitch == 0.2 * rot_scale
    assert pos.yaw == 0.3 * rot_scale
