"""
Telemetry Debug Tool

Run this to see raw telemetry values and diagnose issues.
Does NOT move the actuator - just shows what data we're receiving.

Usage:
    python -m src.debug_telemetry
"""

import time
import statistics
from src.telemetry.udp_listener import UDPListener
from src.telemetry.packet_parser import PacketParser

def main():
    print("=" * 70)
    print("F1 Telemetry Debug Tool")
    print("=" * 70)
    print("This tool shows RAW telemetry values to diagnose issues.")
    print("Start F1 game and drive around. Press Ctrl+C to stop.")
    print("=" * 70)
    print()

    listener = UDPListener(port=20777, timeout=0.1)
    parser = PacketParser()

    # Collect samples for statistics
    g_long_samples = []
    g_lat_samples = []
    g_vert_samples = []

    packet_count = 0
    motion_count = 0
    last_print = time.time()
    print_interval = 0.5  # Print every 0.5 seconds

    try:
        while True:
            data = listener.receive()
            if data is None:
                continue

            packet_count += 1
            telemetry = parser.parse_motion_packet(data)

            if telemetry is None:
                continue

            motion_count += 1

            # Collect samples
            g_long_samples.append(telemetry.g_force_longitudinal)
            g_lat_samples.append(telemetry.g_force_lateral)
            g_vert_samples.append(telemetry.g_force_vertical)

            # Keep only last 60 samples (1 second at 60Hz)
            if len(g_long_samples) > 60:
                g_long_samples.pop(0)
                g_lat_samples.pop(0)
                g_vert_samples.pop(0)

            # Print periodically
            now = time.time()
            if now - last_print >= print_interval and len(g_long_samples) >= 10:
                last_print = now

                # Calculate statistics
                g_long_avg = statistics.mean(g_long_samples)
                g_long_std = statistics.stdev(g_long_samples) if len(g_long_samples) > 1 else 0
                g_long_min = min(g_long_samples)
                g_long_max = max(g_long_samples)

                g_lat_avg = statistics.mean(g_lat_samples)
                g_lat_std = statistics.stdev(g_lat_samples) if len(g_lat_samples) > 1 else 0

                g_vert_avg = statistics.mean(g_vert_samples)

                # Current values
                curr_long = telemetry.g_force_longitudinal
                curr_lat = telemetry.g_force_lateral

                # Calculate what position would be (center=450, gain=100)
                position = 450 + (g_long_avg * 100)

                print(f"[{motion_count:5d}] "
                      f"G_long: {curr_long:+6.2f} (avg:{g_long_avg:+5.2f} std:{g_long_std:.3f} range:{g_long_min:+.2f}~{g_long_max:+.2f}) | "
                      f"G_lat: {curr_lat:+6.2f} (avg:{g_lat_avg:+5.2f}) | "
                      f"-> pos:{position:.0f}mm")

                # Warn about noise
                if g_long_std > 0.1:
                    print(f"        ⚠️  HIGH NOISE in g_long (std={g_long_std:.3f}) - increase smoothing!")
                if abs(g_long_avg) < 0.1 and g_long_std > 0.05:
                    print(f"        ⚠️  NOISE WHEN STATIONARY - increase deadband!")

    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print("Final Statistics")
        print("=" * 70)
        print(f"Total packets received: {packet_count}")
        print(f"Motion packets parsed: {motion_count}")

        if g_long_samples:
            print(f"\nG-force Longitudinal (last {len(g_long_samples)} samples):")
            print(f"  Average: {statistics.mean(g_long_samples):+.3f} G")
            print(f"  Std Dev: {statistics.stdev(g_long_samples):.3f} G")
            print(f"  Min/Max: {min(g_long_samples):+.3f} / {max(g_long_samples):+.3f} G")

            print(f"\nG-force Lateral (last {len(g_lat_samples)} samples):")
            print(f"  Average: {statistics.mean(g_lat_samples):+.3f} G")
            print(f"  Std Dev: {statistics.stdev(g_lat_samples):.3f} G")

        print("=" * 70)

    finally:
        listener.close()


if __name__ == "__main__":
    main()
