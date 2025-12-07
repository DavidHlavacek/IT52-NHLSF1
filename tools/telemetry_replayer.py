"""
F1 Telemetry Replayer

Replays recorded telemetry packets as if they were coming from the game.
Use this to test without needing the actual game.

Usage:
    python tools/telemetry_replayer.py --input race1.bin
    python tools/telemetry_replayer.py --input race1.bin --loop
"""

import socket
import time
import argparse
import struct


def load_recording(input_file: str) -> list:
    """Load recorded packets from file."""
    packets = []

    with open(input_file, 'rb') as f:
        count = struct.unpack('<I', f.read(4))[0]

        for _ in range(count):
            timestamp, length = struct.unpack('<fI', f.read(8))
            data = f.read(length)
            packets.append((timestamp, data))

    return packets


def replay(input_file: str, port: int = 20777, loop: bool = False, speed: float = 1.0):
    """Replay recorded packets via UDP."""

    packets = load_recording(input_file)
    print(f"Loaded {len(packets)} packets from {input_file}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = ('127.0.0.1', port)

    print(f"Replaying to localhost:{port} (speed: {speed}x)")
    print("Press Ctrl+C to stop")
    print()

    try:
        while True:
            start_time = time.time()

            for i, (timestamp, data) in enumerate(packets):
                target_time = start_time + (timestamp / speed)
                sleep_time = target_time - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)

                sock.sendto(data, target)

                if i % 60 == 0:
                    print(f"  Packet {i}/{len(packets)}")

            if not loop:
                break

            print("\n  Looping...\n")

    except KeyboardInterrupt:
        print("\nStopped")

    sock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay F1 telemetry")
    parser.add_argument("--input", "-i", required=True, help="Input recording file")
    parser.add_argument("--port", "-p", type=int, default=20777, help="UDP port")
    parser.add_argument("--loop", "-l", action="store_true", help="Loop playback")
    parser.add_argument("--speed", "-s", type=float, default=1.0, help="Playback speed")
    args = parser.parse_args()

    replay(args.input, args.port, args.loop, args.speed)
