#!/usr/bin/env python3
"""
Debug script to verify telemetry parsing.

Run this while playing F1 to see the raw G-force values.
This will tell us if the data is correct or if parsing is wrong.

Expected behavior:
- Accelerating: gForceLongitudinal should be POSITIVE and stable
- Braking: gForceLongitudinal should be NEGATIVE and stable
- Coasting: gForceLongitudinal should be near ZERO

If values oscillate rapidly when you're doing ONE thing (only accelerating),
then either:
1. We're parsing wrong packet/field
2. The game sends noisy data
3. We're reading wrong car's data
"""

import time
import logging
from src.telemetry.udp_listener import UDPListener
from src.telemetry.packet_parser import PacketParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    print("=" * 70)
    print("TELEMETRY DEBUG - Verifying G-Force Values")
    print("=" * 70)
    print()
    print("Instructions:")
    print("  1. Start F1 2024 and enter a race/time trial")
    print("  2. Watch the values below while you:")
    print("     - ONLY accelerate (hold throttle)")
    print("     - ONLY brake (hold brake)")
    print("     - Coast (no inputs)")
    print()
    print("Expected:")
    print("  - Accelerating: g_long should be POSITIVE (e.g., +0.5 to +2.0)")
    print("  - Braking: g_long should be NEGATIVE (e.g., -2.0 to -5.0)")
    print("  - Coasting: g_long should be near ZERO")
    print()
    print("If g_long oscillates rapidly during PURE acceleration,")
    print("something is wrong with parsing!")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 70)
    print()

    listener = UDPListener(port=20777)
    parser = PacketParser()

    last_print = 0
    samples = []

    try:
        while True:
            data = listener.receive()
            if not data:
                continue

            telemetry = parser.parse_motion_packet(data)
            if not telemetry:
                continue

            # Collect sample
            samples.append({
                'g_lat': telemetry.g_force_lateral,
                'g_long': telemetry.g_force_longitudinal,
                'g_vert': telemetry.g_force_vertical,
                'time': time.time()
            })

            # Print every 0.1 seconds (10Hz) to see trends
            now = time.time()
            if now - last_print >= 0.1:
                last_print = now

                # Calculate stats from last 6 samples (0.1s at 60Hz)
                recent = samples[-6:] if len(samples) >= 6 else samples

                avg_long = sum(s['g_long'] for s in recent) / len(recent)
                min_long = min(s['g_long'] for s in recent)
                max_long = max(s['g_long'] for s in recent)
                spread = max_long - min_long

                # Determine what's happening
                if avg_long > 0.3:
                    state = "ACCELERATING"
                elif avg_long < -0.3:
                    state = "BRAKING"
                else:
                    state = "COASTING"

                # Warning if spread is high during stable input
                warning = ""
                if spread > 0.5:
                    warning = " ⚠️ HIGH VARIANCE!"

                print(
                    f"g_long: {avg_long:+6.2f} "
                    f"(min:{min_long:+5.2f} max:{max_long:+5.2f} spread:{spread:.2f}) "
                    f"| g_lat: {telemetry.g_force_lateral:+5.2f} "
                    f"| {state}{warning}"
                )

                # Keep only last 60 samples (1 second)
                if len(samples) > 60:
                    samples = samples[-60:]

    except KeyboardInterrupt:
        print("\n\nStopped.")
        print(f"Total motion packets received: {parser.stats['motion_packets_parsed']}")
    finally:
        listener.close()


if __name__ == "__main__":
    main()
