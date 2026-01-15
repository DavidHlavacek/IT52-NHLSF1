#!/usr/bin/env python3
"""
Simple G-force logger - logs EVERY value with timestamp.

This will show us exactly what G-forces the game is sending.
Run this while ONLY holding throttle to verify the values are correct.
"""

import time
from src.telemetry.udp_listener import UDPListener
from src.telemetry.packet_parser import PacketParser

def main():
    print("=" * 70)
    print("G-FORCE LOGGER - Every single value")
    print("=" * 70)
    print()
    print("Hold ONLY THROTTLE (accelerate) and watch the values.")
    print("g_long should be POSITIVE (+0.5 to +2.0) the ENTIRE time.")
    print()
    print("If you see negative values while accelerating,")
    print("something is very wrong!")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 70)
    print()
    print("Time       | g_long  | g_lat   | State")
    print("-" * 50)

    listener = UDPListener(port=20777)
    parser = PacketParser()
    start_time = time.time()
    count = 0
    player_idx_shown = False

    try:
        while True:
            data = listener.receive()
            if not data:
                continue

            # Show player car index once
            if not player_idx_shown:
                header = parser.parse_header(data)
                if header:
                    print(f"\n>>> Player car index: {header.player_car_index} <<<\n")
                    player_idx_shown = True

            telemetry = parser.parse_motion_packet(data)
            if not telemetry:
                continue

            count += 1
            elapsed = time.time() - start_time
            g_long = telemetry.g_force_longitudinal
            g_lat = telemetry.g_force_lateral

            # Determine state
            if g_long > 0.3:
                state = "ACCEL"
            elif g_long < -0.3:
                state = "BRAKE"
            else:
                state = "coast"

            # Print every 3rd value (~20Hz display) to avoid spam
            if count % 3 == 0:
                print(f"{elapsed:6.2f}s   | {g_long:+6.2f} | {g_lat:+6.2f} | {state}")

    except KeyboardInterrupt:
        print(f"\n\nLogged {count} motion packets")
    finally:
        listener.close()


if __name__ == "__main__":
    main()
