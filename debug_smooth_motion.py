#!/usr/bin/env python3
"""
Smooth motion test - with LOW-PASS FILTER on input.

The previous test was "erratic" because F1 G-forces vary rapidly during driving
(gear changes, wheelspin, kerbs, etc.). This version adds smoothing.

Smoothing formula (exponential moving average):
    smoothed = alpha * new_value + (1 - alpha) * smoothed
    where alpha = dt / (tau + dt), tau = 1 / (2 * pi * cutoff_freq)

Lower cutoff = more smoothing = slower response but less jitter
Higher cutoff = less smoothing = faster response but more jitter

Recommended: Start with 1-2 Hz cutoff for smooth feel.
"""

import time
import math
import logging
import signal
import sys

from src.telemetry.udp_listener import UDPListener
from src.telemetry.packet_parser import PacketParser
from src.drivers.smc_driver import SMCDriver

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
CENTER_MM = 350.0       # Center position
GAIN = 80.0             # mm per G (higher = more movement)
MIN_POS = 100.0         # Minimum position (mm)
MAX_POS = 800.0         # Maximum position (mm)
DEADBAND_G = 0.05       # Ignore G-force changes smaller than this
COMMAND_RATE = 30       # Commands per second (Hz)

# SMOOTHING - This is the key to removing jitter!
SMOOTHING_CUTOFF_HZ = 2.0  # Low-pass filter cutoff (1-3 Hz typical)

# Global flag for clean shutdown
running = True


class LowPassFilter:
    """Simple first-order low-pass filter (exponential moving average)."""

    def __init__(self, cutoff_hz: float, sample_rate_hz: float):
        """
        Initialize the filter.

        Args:
            cutoff_hz: Cutoff frequency in Hz (lower = more smoothing)
            sample_rate_hz: Expected sample rate in Hz
        """
        dt = 1.0 / sample_rate_hz
        tau = 1.0 / (2.0 * math.pi * cutoff_hz)
        self.alpha = dt / (tau + dt)
        self.value = 0.0
        self.initialized = False

    def update(self, new_value: float) -> float:
        """Process new sample and return filtered value."""
        if not self.initialized:
            self.value = new_value
            self.initialized = True
        else:
            self.value = self.alpha * new_value + (1 - self.alpha) * self.value
        return self.value

    def reset(self, value: float = 0.0):
        """Reset filter state."""
        self.value = value
        self.initialized = True


def signal_handler(signum, frame):
    global running
    running = False
    print("\nShutting down...")


def main():
    global running

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 70)
    print("SMOOTH MOTION TEST (with low-pass filter)")
    print("=" * 70)
    print()
    print(f"Center: {CENTER_MM}mm")
    print(f"Gain: {GAIN}mm per G")
    print(f"Range: {MIN_POS}mm - {MAX_POS}mm")
    print(f"Command rate: {COMMAND_RATE}Hz")
    print(f"Smoothing cutoff: {SMOOTHING_CUTOFF_HZ}Hz")
    print()
    print("Motion mapping:")
    print("  - Accelerating (G > 0): actuator moves LEFT (toward 0)")
    print("  - Braking (G < 0): actuator moves RIGHT (toward 900)")
    print("  - Coasting (G ≈ 0): actuator stays at CENTER")
    print()
    print("The smoothing filter removes rapid G-force jitter,")
    print("giving smooth, predictable motion.")
    print()

    # Initialize driver
    print("Connecting to SMC controller...")
    driver = SMCDriver(config={'port': 'COM5'})

    if not driver.connect():
        print("Failed to connect!")
        return

    print("Initializing (homing + center)...")
    if not driver.initialize(home_first=True):
        print("Initialization failed!")
        driver.close()
        return

    print("Ready! Starting telemetry reception...")
    print("=" * 70)
    print()

    # Initialize telemetry
    listener = UDPListener(port=20777)
    parser = PacketParser()

    # Initialize low-pass filter for G-force smoothing
    g_filter = LowPassFilter(SMOOTHING_CUTOFF_HZ, COMMAND_RATE)

    last_command_time = 0.0
    command_interval = 1.0 / COMMAND_RATE
    commands_sent = 0
    last_position = CENTER_MM

    try:
        while running:
            data = listener.receive()
            if not data:
                continue

            telemetry = parser.parse_motion_packet(data)
            if not telemetry:
                continue

            # Rate limiting
            now = time.perf_counter()
            if now - last_command_time < command_interval:
                continue
            last_command_time = now

            # Get raw longitudinal G-force
            g_raw = telemetry.g_force_longitudinal

            # Apply low-pass filter for smoothing
            g_smooth = g_filter.update(g_raw)

            # Apply deadband on the SMOOTHED value
            if abs(g_smooth) < DEADBAND_G:
                g_smooth = 0.0

            # Direct mapping (no washout - position proportional to G)
            # Invert so braking (negative G) moves RIGHT (positive position change)
            position = CENTER_MM - (g_smooth * GAIN)

            # Clamp to safe range
            position = max(MIN_POS, min(MAX_POS, position))

            # Only send if position changed enough (reduces unnecessary commands)
            if abs(position - last_position) < 1.0:
                continue

            last_position = position

            # Send to actuator
            driver.send_position(position)
            commands_sent += 1

            # Log every 15 commands (~0.5 seconds at 30Hz)
            if commands_sent % 15 == 0:
                direction = "LEFT" if g_smooth > 0.1 else ("RIGHT" if g_smooth < -0.1 else "CENTER")
                print(
                    f"g_raw: {g_raw:+5.2f} -> "
                    f"g_smooth: {g_smooth:+5.2f} -> "
                    f"pos: {position:6.1f}mm "
                    f"({direction})"
                )

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print(f"\nTotal commands sent: {commands_sent}")
        print("Returning to center and shutting down...")
        listener.close()
        driver.close()


if __name__ == "__main__":
    main()
