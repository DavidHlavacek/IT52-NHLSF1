"""
F1 Telemetry Recorder

Records live UDP packets from F1 game to a file for later replay.
Run this while playing the game.

Usage:
    python tools/telemetry_recorder.py --output race1.bin --duration 60
"""

import socket
import time
import argparse
import struct


def record(output_file: str, duration: int, port: int = 20777):
    """Record F1 telemetry packets to file."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', port))
    sock.settimeout(1.0)

    print(f"Recording on port {port} for {duration} seconds...")
    print("Start driving in F1 game now!")
    print()

    packets = []
    start_time = time.time()

    try:
        while time.time() - start_time < duration:
            try:
                data, addr = sock.recvfrom(2048)
                timestamp = time.time() - start_time
                packets.append((timestamp, data))

                if len(packets) % 60 == 0:
                    print(f"  {len(packets)} packets ({int(time.time() - start_time)}s)")

            except socket.timeout:
                print("  Waiting for packets...")

    except KeyboardInterrupt:
        print("\nStopped early")

    sock.close()

    with open(output_file, 'wb') as f:
        f.write(struct.pack('<I', len(packets)))
        for timestamp, data in packets:
            f.write(struct.pack('<fI', timestamp, len(data)))
            f.write(data)

    print()
    print(f"Saved {len(packets)} packets to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record F1 telemetry")
    parser.add_argument("--output", "-o", default="telemetry_recording.bin", help="Output file")
    parser.add_argument("--duration", "-d", type=int, default=60, help="Recording duration (seconds)")
    parser.add_argument("--port", "-p", type=int, default=20777, help="UDP port")
    args = parser.parse_args()

    record(args.output, args.duration, args.port)
