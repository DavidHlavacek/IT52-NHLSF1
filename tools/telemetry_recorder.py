"""
Telemetry Recorder - INF-165

Records F1 telemetry data for offline testing and development.

Usage:
    python tools/telemetry_recorder.py --name full_lap --duration 60
    python tools/telemetry_recorder.py --name heavy_braking --duration 30
    python tools/telemetry_recorder.py --name high_speed_corners --duration 30
    
"""

import os
import sys
import struct
import socket
import time
import argparse
from datetime import datetime


class TelemetryRecorder:
    """Records F1 telemetry packets to binary file for offline playback."""
    
    DEFAULT_PORT = 20777
    BUFFER_SIZE = 2048
    
    def __init__(self, output_dir: str = "recordings"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def record(self, name: str, duration: float, port: int = DEFAULT_PORT) -> str:
        """Record telemetry for specified duration."""
        # Create filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.bin"
        filepath = os.path.join(self.output_dir, filename)
        
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.5)
        
        try:
            sock.bind(("0.0.0.0", port))
        except socket.error as e:
            print(f"ERROR: Could not bind to port {port}: {e}")
            return None
        
        packets = []
        start_time = time.time()
        
        print("=" * 50)
        print("  TELEMETRY RECORDER - INF-165")
        print("=" * 50)
        print(f"  Recording: {name}")
        print(f"  Duration:  {duration} seconds")
        print(f"  Port:      {port}")
        print(f"  Output:    {filepath}")
        print("=" * 50)
        print()
        print("  Waiting for F1 game telemetry...")
        print("  Make sure UDP Telemetry is ON in game settings!")
        print()
        print("  Press Ctrl+C to stop early.")
        print("-" * 50)
        
        waiting_for_data = True
        
        try:
            while time.time() - start_time < duration:
                try:
                    data, addr = sock.recvfrom(self.BUFFER_SIZE)
                    elapsed = time.time() - start_time
                    packets.append((elapsed, data))
                    
                    if waiting_for_data:
                        print(f"  [OK] Receiving data from {addr[0]}")
                        print("-" * 50)
                        waiting_for_data = False
                    
                    if len(packets) % 60 == 0:
                        remaining = duration - elapsed
                        print(f"  [{elapsed:5.1f}s] {len(packets):5d} packets | {remaining:.0f}s remaining")
                        
                except socket.timeout:
                    if waiting_for_data:
                        elapsed = time.time() - start_time
                        sys.stdout.write(f"\r  Waiting... ({elapsed:.0f}s)   ")
                        sys.stdout.flush()
                    continue
                    
        except KeyboardInterrupt:
            print("\n")
            print("  Recording stopped by user.")
        finally:
            sock.close()
        
        if not packets:
            print("\n")
            print("  ERROR: No packets received!")
            print()
            print("  Check that:")
            print("    1. F1 game is running")
            print("    2. You are ON TRACK (not in menu)")
            print("    3. UDP Telemetry is ON in game settings")
            print("    4. UDP Port is set to", port)
            return None
        
        # Write to file
        with open(filepath, 'wb') as f:
            f.write(struct.pack('<I', len(packets)))
            for ts, data in packets:
                f.write(struct.pack('<fI', ts, len(data)))
                f.write(data)
        
        print("-" * 50)
        print("  [OK] RECORDING COMPLETE")
        print(f"    Packets:   {len(packets)}")
        print(f"    Duration:  {packets[-1][0]:.1f} seconds")
        print(f"    File:      {filepath}")
        print(f"    Size:      {os.path.getsize(filepath) / 1024:.1f} KB")
        print("=" * 50)
        
        return filepath


def main():
    parser = argparse.ArgumentParser(description="Record F1 telemetry data")
    parser.add_argument("--name", required=True, help="Descriptive name (e.g., full_lap)")
    parser.add_argument("--duration", type=float, default=60, help="Duration in seconds")
    parser.add_argument("--port", type=int, default=20777, help="UDP port")
    args = parser.parse_args()
    
    recorder = TelemetryRecorder()
    result = recorder.record(args.name, args.duration, args.port)
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()