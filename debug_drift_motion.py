#!/usr/bin/env python3
"""
Drift-based motion - position ACCUMULATES during sustained G-force.

Unlike proportional mapping (position = G * gain), this INTEGRATES:
- Sustained acceleration → position keeps drifting backward
- Sustained braking → position keeps drifting forward
- Coasting → slowly returns to center

This gives the "continuous drift" feel during sustained acceleration.
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
CENTER_MM = 350.0
MIN_POS = 100.0
MAX_POS = 800.0
COMMAND_RATE = 30

# DRIFT PARAMETERS - tune these!
DRIFT_GAIN = 30.0       # mm/s per G (how fast it drifts during sustained G)
RETURN_RATE = 0.5       # How fast it returns to center when coasting (0-1, higher = faster)
DEADBAND_G = 0.15       # Ignore G below this (coasting threshold)
SMOOTHING_HZ = 3.0      # Low-pass filter cutoff for G-force smoothing

# Global
running = True


class LowPassFilter:
    def __init__(self, cutoff_hz: float, sample_rate_hz: float):
        dt = 1.0 / sample_rate_hz
        tau = 1.0 / (2.0 * math.pi * cutoff_hz)
        self.alpha = dt / (tau + dt)
        self.value = 0.0
        self.initialized = False

    def update(self, new_value: float) -> float:
        if not self.initialized:
            self.value = new_value
            self.initialized = True
        else:
            self.value = self.alpha * new_value + (1 - self.alpha) * self.value
        return self.value


def signal_handler(signum, frame):
    global running
    running = False
    print("\nShutting down...")


def main():
    global running

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 70)
    print("DRIFT MOTION TEST")
    print("=" * 70)
    print()
    print("Unlike proportional mapping, this INTEGRATES G-force over time:")
    print(f"  - Drift rate: {DRIFT_GAIN} mm/s per G")
    print(f"  - Return rate: {RETURN_RATE} (when coasting)")
    print(f"  - Deadband: {DEADBAND_G} G")
    print()
    print("Behavior:")
    print("  - Sustained acceleration: keeps drifting backward (slowly)")
    print("  - Sustained braking: keeps drifting forward (slowly)")
    print("  - Coasting: slowly returns to center")
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

    print("Ready!")
    print("=" * 70)
    print()

    # Initialize telemetry
    listener = UDPListener(port=20777)
    parser = PacketParser()
    g_filter = LowPassFilter(SMOOTHING_HZ, COMMAND_RATE)

    # State
    position = CENTER_MM  # Current position (integrated)
    last_time = time.perf_counter()
    commands_sent = 0
    last_sent_pos = CENTER_MM

    try:
        while running:
            data = listener.receive()
            if not data:
                continue

            telemetry = parser.parse_motion_packet(data)
            if not telemetry:
                continue

            # Calculate dt
            now = time.perf_counter()
            dt = now - last_time
            last_time = now

            # Skip if dt is too large (pause/lag)
            if dt > 0.5:
                dt = 1.0 / COMMAND_RATE

            # Get smoothed G-force
            g_raw = telemetry.g_force_longitudinal
            g_smooth = g_filter.update(g_raw)

            # DRIFT INTEGRATION
            if abs(g_smooth) > DEADBAND_G:
                # Drift away from center based on G-force
                # Negative G (braking) → drift forward (increase position)
                # Positive G (accel) → drift backward (decrease position)
                drift = -g_smooth * DRIFT_GAIN * dt
                position += drift
            else:
                # Slowly return to center when coasting
                position += (CENTER_MM - position) * RETURN_RATE * dt

            # Clamp to limits
            position = max(MIN_POS, min(MAX_POS, position))

            # Only send if position changed enough
            if abs(position - last_sent_pos) < 0.5:
                continue

            last_sent_pos = position
            driver.send_position(position)
            commands_sent += 1

            # Log every 20 commands
            if commands_sent % 20 == 0:
                state = "ACCEL" if g_smooth > DEADBAND_G else ("BRAKE" if g_smooth < -DEADBAND_G else "coast")
                print(
                    f"g: {g_smooth:+5.2f} | "
                    f"pos: {position:6.1f}mm | "
                    f"drift: {-g_smooth * DRIFT_GAIN:+6.1f}mm/s | "
                    f"{state}"
                )

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print(f"\nTotal commands sent: {commands_sent}")
        listener.close()
        driver.close()


if __name__ == "__main__":
    main()
