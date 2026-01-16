"""
Telemetry Replay - INF-165

Replays recorded telemetry for offline testing.

Usage:
    python tools/telemetry_replayer.py recordings/full_lap_20260112_160501.bin
    python tools/telemetry_replayer.py recordings/full_lap_20260112_160501.bin --verbos
    python tools/telemetry_replayer.py recordings/full_lap_20251223_143022.bin --speed 2.0
"""

import os
import sys
import struct
import time
import argparse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)


try:
    from src.telemetry.packet_parser import PacketParser
    from src.motion.algorithm import MotionAlgorithm
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False


class TelemetryReplay:
    """Replays recorded telemetry through the motion algorithm."""
    
    def __init__(self, config: dict = None):
        self.config = config or {
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
        
        if IMPORTS_AVAILABLE:
            self.parser = PacketParser()
            self.algorithm = MotionAlgorithm(self.config)
        else:
            self.parser = None
            self.algorithm = None
    
    def load(self, filepath: str) -> list:
        """Load packets from recording file."""
        packets = []
        with open(filepath, 'rb') as f:
            count = struct.unpack('<I', f.read(4))[0]
            for _ in range(count):
                timestamp, length = struct.unpack('<fI', f.read(8))
                data = f.read(length)
                packets.append((timestamp, data))
        return packets
    
    def get_info(self, filepath: str) -> dict:
        """Get information about a recording file."""
        packets = self.load(filepath)
        file_size = os.path.getsize(filepath)
        duration = packets[-1][0] if packets else 0
        motion_count = sum(1 for _, data in packets if len(data) > 6 and data[6] == 0)
        
        return {
            "file": filepath,
            "file_size_kb": file_size / 1024,
            "total_packets": len(packets),
            "motion_packets": motion_count,
            "duration_seconds": duration,
        }
    
    def replay(self, filepath: str, speed: float = 1.0, callback=None) -> dict:
        """Replay recording through motion algorithm."""
        packets = self.load(filepath)
        
        print(f"Loaded {len(packets)} packets from {filepath}")
        
        if not IMPORTS_AVAILABLE:
            print("ERROR: Cannot replay - imports not available")
            return {"error": "imports_not_available"}
        
        start_time = time.time()
        motion_packets = 0
        
        for packet_time, data in packets:
            target_time = start_time + (packet_time / speed)
            now = time.time()
            if target_time > now:
                time.sleep(target_time - now)
            
            telemetry = self.parser.parse_motion_packet(data)
            if telemetry:
                position = self.algorithm.calculate(telemetry)
                motion_packets += 1
                if callback:
                    callback(packet_time, telemetry, position)
        
        print(f"Replay complete. Processed {motion_packets} motion packets.")
        return {"motion_packets": motion_packets}


def main():
    parser = argparse.ArgumentParser(description="Replay recorded telemetry")
    parser.add_argument("file", help="Recording file path")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each packet")
    parser.add_argument("--info", action="store_true", help="Show file info only")
    args = parser.parse_args()
    
    replay = TelemetryReplay()
    
    if args.info:
        info = replay.get_info(args.file)
        for key, value in info.items():
            print(f"  {key}: {value}")
        return
    
    def verbose_callback(ts, tel, pos):
        print(f"[{ts:6.2f}s] G=[{tel.g_force_lateral:+5.2f}, "
              f"{tel.g_force_longitudinal:+5.2f}] -> pos={pos.x*1000:+6.1f}mm")
    
    replay.replay(args.file, args.speed, verbose_callback if args.verbose else None)


if __name__ == "__main__":
    main()