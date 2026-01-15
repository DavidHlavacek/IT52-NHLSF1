#!/usr/bin/env python3
"""
Raw packet debug - see exactly what bytes we're receiving.

This will show:
1. Packet header fields (format, game year, packet ID, player car index)
2. Raw G-force bytes and decoded values
3. Multiple cars' G-forces to verify we're reading the right one
"""

import struct
import time
from src.telemetry.udp_listener import UDPListener

# F1 2024 packet structure (CORRECT format - 29 bytes)
# H=packetFormat, BBBBB=year/major/minor/version/id, Q=sessionUID,
# f=sessionTime, II=frameId+overallFrameId, BB=playerIdx+secondaryIdx
HEADER_FORMAT = '<HBBBBBQfIIBB'  # 29 bytes
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

# CarMotionData: 60 bytes per car
# Position(3f) + Velocity(3f) + ForwardDir(3h) + RightDir(3h) + GForces(3f) + Angles(3f)
CAR_MOTION_FORMAT = '<ffffffhhhhhhffffff'
CAR_MOTION_SIZE = struct.calcsize(CAR_MOTION_FORMAT)


def main():
    print("=" * 70)
    print("RAW PACKET DEBUG")
    print("=" * 70)
    print()
    print(f"Header size: {HEADER_SIZE} bytes")
    print(f"Car motion data size: {CAR_MOTION_SIZE} bytes per car")
    print(f"Expected motion packet: {HEADER_SIZE + 22 * CAR_MOTION_SIZE} bytes")
    print()

    listener = UDPListener(port=20777)
    motion_packets = 0

    try:
        while motion_packets < 10:  # Just show first 10 motion packets
            data = listener.receive()
            if not data:
                continue

            if len(data) < HEADER_SIZE:
                continue

            # Parse header
            header = struct.unpack_from(HEADER_FORMAT, data, 0)
            packet_format = header[0]
            game_year = header[1]
            packet_id = header[5]
            player_car_index = header[10]

            # Only process motion packets (ID = 0)
            if packet_id != 0:
                continue

            motion_packets += 1
            print(f"\n{'='*70}")
            print(f"MOTION PACKET #{motion_packets}")
            print(f"{'='*70}")
            print(f"Packet format: {packet_format}")
            print(f"Game year: {game_year}")
            print(f"Packet ID: {packet_id} (0 = Motion)")
            print(f"Packet size: {len(data)} bytes")
            print(f"Player car index: {player_car_index}")
            print()

            # Parse player car's motion data
            player_offset = HEADER_SIZE + (player_car_index * CAR_MOTION_SIZE)
            print(f"Player car data offset: {player_offset}")

            if len(data) < player_offset + CAR_MOTION_SIZE:
                print("ERROR: Packet too small for player car data!")
                continue

            car_data = struct.unpack_from(CAR_MOTION_FORMAT, data, player_offset)

            print()
            print("Player car motion data:")
            print(f"  Position: X={car_data[0]:.1f}, Y={car_data[1]:.1f}, Z={car_data[2]:.1f}")
            print(f"  Velocity: X={car_data[3]:.1f}, Y={car_data[4]:.1f}, Z={car_data[5]:.1f}")
            print(f"  G-Forces:")
            print(f"    Lateral (sideways):     {car_data[12]:+.3f} G")
            print(f"    Longitudinal (accel):   {car_data[13]:+.3f} G")
            print(f"    Vertical:               {car_data[14]:+.3f} G")
            print(f"  Angles:")
            print(f"    Yaw:   {car_data[15]:+.3f} rad")
            print(f"    Pitch: {car_data[16]:+.3f} rad")
            print(f"    Roll:  {car_data[17]:+.3f} rad")

            # Also show car 0 for comparison (in case player index is wrong)
            if player_car_index != 0:
                car0_offset = HEADER_SIZE
                car0_data = struct.unpack_from(CAR_MOTION_FORMAT, data, car0_offset)
                print()
                print("Car 0 (for comparison):")
                print(f"  G-Forces: lat={car0_data[12]:+.3f}, long={car0_data[13]:+.3f}, vert={car0_data[14]:+.3f}")

            # Show raw bytes of G-force fields for player car
            g_offset = player_offset + 48  # Skip position(12) + velocity(12) + dirs(12) + gLat(4) + gLong starts at +40... wait
            # Actually: 6 floats (24) + 6 int16 (12) = 36 bytes, then G-forces start
            g_offset = player_offset + 36  # gForceLateral starts here
            print()
            print(f"Raw G-force bytes at offset {g_offset}:")
            g_bytes = data[g_offset:g_offset+12]  # 3 floats = 12 bytes
            print(f"  Hex: {g_bytes.hex()}")
            print(f"  Decoded: lat={struct.unpack('<f', g_bytes[0:4])[0]:+.3f}, "
                  f"long={struct.unpack('<f', g_bytes[4:8])[0]:+.3f}, "
                  f"vert={struct.unpack('<f', g_bytes[8:12])[0]:+.3f}")

            time.sleep(0.5)  # Don't spam

    except KeyboardInterrupt:
        print("\n\nStopped.")
    finally:
        listener.close()


if __name__ == "__main__":
    main()
