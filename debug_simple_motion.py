#!/usr/bin/env python3
"""
Simple direct motion test - NO washout filter.

This maps G-force DIRECTLY to actuator position:
- Center (450mm) = no G-force
- Accelerating (positive G) = move LEFT (toward 0mm)
- Braking (negative G) = move RIGHT (toward 900mm)

If this works smoothly, the problem is in the washout filter.
If this still oscillates, the problem is in telemetry parsing.
"""

import time
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
GAIN = 50.0             # mm per G (start conservative!)
MIN_POS = 100.0         # Minimum position (mm)
MAX_POS = 800.0         # Maximum position (mm)
DEADBAND = 0.1          # Ignore G-force changes smaller than this
COMMAND_RATE = 20       # Commands per second (Hz)

# Global flag for clean shutdown
running = True


def signal_handler(signum, frame):
    global running
    running = False
    print("\nShutting down...")


def main():
    global running

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("=" * 70)
    print("SIMPLE DIRECT MOTION TEST")
    print("=" * 70)
    print()
    print(f"Center: {CENTER_MM}mm")
    print(f"Gain: {GAIN}mm per G")
    print(f"Range: {MIN_POS}mm - {MAX_POS}mm")
    print(f"Command rate: {COMMAND_RATE}Hz")
    print()
    print("Motion mapping (NO washout filter):")
    print("  - Accelerating (G > 0): actuator moves LEFT (toward 0)")
    print("  - Braking (G < 0): actuator moves RIGHT (toward 900)")
    print("  - Coasting (G ≈ 0): actuator stays at CENTER")
    print()
    print("If motion is smooth during pure acceleration,")
    print("the problem was in the washout filter.")
    print()

    # Initialize driver
    print("Connecting to SMC controller...")
    driver = SMCDriver(config={'port': 'COM5'})  # Adjust port as needed

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

    last_g_long = 0.0
    last_command_time = 0.0
    command_interval = 1.0 / COMMAND_RATE
    commands_sent = 0

    try:
        while running:
            data = listener.receive()
            if not data:
                continue

            telemetry = parser.parse_motion_packet(data)
            if not telemetry:
                continue

            # Get longitudinal G-force
            g_long = telemetry.g_force_longitudinal

            # Apply deadband
            if abs(g_long - last_g_long) < DEADBAND:
                g_long = last_g_long
            last_g_long = g_long

            # Rate limiting
            now = time.perf_counter()
            if now - last_command_time < command_interval:
                continue
            last_command_time = now

            # SIMPLE DIRECT MAPPING (no washout!)
            # Invert so braking (negative G) moves RIGHT (positive position)
            position = CENTER_MM - (g_long * GAIN)

            # Clamp to safe range
            position = max(MIN_POS, min(MAX_POS, position))

            # Send to actuator
            driver.send_position(position)
            commands_sent += 1

            # Log
            if commands_sent % 10 == 0:  # Every 0.5 seconds at 20Hz
                direction = "LEFT" if g_long > 0.1 else ("RIGHT" if g_long < -0.1 else "CENTER")
                print(
                    f"g_long: {g_long:+5.2f}G -> "
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
