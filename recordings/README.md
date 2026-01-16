# Telemetry Recordings

Binary recordings of F1 game telemetry for offline testing and development.

## Quick Start

### Record Telemetry

```bash
# Record a full lap (60 seconds)
python tools/telemetry_recorder.py --name full_lap --duration 60

# Record heavy braking zone (30 seconds)
python tools/telemetry_recorder.py --name heavy_braking --duration 30

# Record high-speed corners (30 seconds)
python tools/telemetry_recorder.py --name high_speed_corners --duration 30
```

### Replay Telemetry

```bash
# Basic replay
python tools/telemetry_replayer.py recordings/full_lap_20251223_143022.bin

# Verbose output (show each packet)
python tools/telemetry_replayer.py recordings/full_lap_20251223_143022.bin --verbose

# Fast replay (2x speed)
python tools/telemetry_replayer.py recordings/full_lap_20251223_143022.bin --speed 2.0

# Get file info only
python tools/telemetry_replayer.py recordings/full_lap_20251223_143022.bin --info
```

---

## Binary File Format

Each `.bin` file uses a custom binary format optimized for accurate playback.

### File Structure

```
+------------------+
|  FILE HEADER     |
+------------------+
|  PACKET 1        |
+------------------+
|  PACKET 2        |
+------------------+
|  ...             |
+------------------+
|  PACKET N        |
+------------------+
```

### File Header

| Offset | Size (bytes) | Type   | Description                    |
|--------|--------------|--------|--------------------------------|
| 0      | 4            | uint32 | Total number of packets (N)    |

### Packet Structure (repeated N times)

| Offset | Size (bytes) | Type   | Description                           |
|--------|--------------|--------|---------------------------------------|
| 0      | 4            | float  | Timestamp (seconds from start)        |
| 4      | 4            | uint32 | Packet data length (L)                |
| 8      | L            | bytes  | Raw UDP packet data from F1 game      |

### Data Types

- All numeric values are **little-endian**
- `uint32`: Unsigned 32-bit integer (`<I` in Python struct)
- `float`: 32-bit floating point (`<f` in Python struct)

---

## Example: Reading a Recording in Python

```python
import struct

def read_recording(filepath):
    """Read a telemetry recording file."""
    packets = []
    
    with open(filepath, 'rb') as f:
        # Read header: packet count (4 bytes)
        count = struct.unpack('<I', f.read(4))[0]
        print(f"File contains {count} packets")
        
        # Read each packet
        for i in range(count):
            # Read timestamp (4 bytes) and length (4 bytes)
            timestamp, length = struct.unpack('<fI', f.read(8))
            
            # Read packet data
            data = f.read(length)
            
            packets.append({
                'timestamp': timestamp,
                'length': length,
                'data': data
            })
    
    return packets

# Usage
packets = read_recording('recordings/full_lap_20251223_143022.bin')
print(f"First packet at {packets[0]['timestamp']:.3f}s")
print(f"Last packet at {packets[-1]['timestamp']:.3f}s")
```

---

## Example: Writing a Recording in Python

```python
import struct

def write_recording(filepath, packets):
    """
    Write packets to a recording file.
    
    Args:
        filepath: Output file path
        packets: List of (timestamp, data) tuples
    """
    with open(filepath, 'wb') as f:
        # Write header: packet count
        f.write(struct.pack('<I', len(packets)))
        
        # Write each packet
        for timestamp, data in packets:
            # Write timestamp and length
            f.write(struct.pack('<fI', timestamp, len(data)))
            # Write packet data
            f.write(data)

# Usage
packets = [
    (0.0, b'packet_data_here'),
    (0.016, b'next_packet_data'),
    # ...
]
write_recording('recordings/test.bin', packets)
```

---

## F1 UDP Packet Types

The recording captures ALL UDP packet types from the F1 game. The packet type is identified by byte 5 (packet_id) in each packet:

| Packet ID | Name              | Description                        | Used by Motion Sim |
|-----------|-------------------|------------------------------------|--------------------|
| 0         | Motion            | Car motion data (G-forces, angles) | ✅ Yes             |
| 1         | Session           | Session info (weather, track)      | No                 |
| 2         | Lap Data          | Lap times, positions               | No                 |
| 3         | Event             | Events (start, finish, penalties)  | No                 |
| 4         | Participants      | Driver names, teams                | No                 |
| 5         | Car Setups        | Car setup data                     | No                 |
| 6         | Car Telemetry     | Speed, throttle, brake, gear       | No                 |
| 7         | Car Status        | Fuel, tyres, damage                | No                 |
| 8         | Final Class.      | End of race standings              | No                 |
| 9         | Lobby Info        | Multiplayer lobby                  | No                 |
| 10        | Car Damage        | Damage status                      | No                 |
| 11        | Session History   | Lap history                        | No                 |
| 12        | Tyre Sets         | Available tyre sets                | No                 |
| 13        | Motion Ex         | Extended motion (F1 23+)           | No                 |

**Note:** Only **Motion packets (ID 0)** are processed by the motion algorithm. Other packets are stored but ignored during replay.

---

## Recording Scenarios

The acceptance criteria require 3 specific scenarios:

| Scenario             | Duration | Description                              | Recommended Track        |
|----------------------|----------|------------------------------------------|--------------------------|
| `full_lap`           | 60s      | Complete lap with varied conditions      | Monza, Spa               |
| `heavy_braking`      | 30s      | Focus on hard braking zones              | Monza Turn 1, Chicanes   |
| `high_speed_corners` | 30s      | High-speed corner sequences              | Silverstone Maggots/Becketts |

---

## File Naming Convention

Files are automatically named with timestamp:

```
{scenario_name}_{YYYYMMDD}_{HHMMSS}.bin
```

**Examples:**
- `full_lap_20251223_143022.bin`
- `heavy_braking_20251223_144512.bin`
- `high_speed_corners_20251223_145033.bin`

---

## F1 Game Setup

Before recording, enable UDP telemetry in the F1 game:

1. Launch **F1 24** (or F1 23)
2. Go to **Settings** → **Telemetry Settings**
3. Configure:

| Setting          | Value       |
|------------------|-------------|
| UDP Telemetry    | **On**      |
| UDP Port         | **20777**   |
| UDP Send Rate    | **60Hz**    |
| UDP Format       | **2024**    |

If running the game on a different PC, also set **UDP IP Address** to your development PC's IP address.

---

## Troubleshooting

### No packets received during recording

1. ✅ Verify F1 game is running
2. ✅ Make sure you are **on track** (not in menu)
3. ✅ Check UDP Telemetry is **On** in game settings
4. ✅ Verify UDP Port is **20777**
5. ✅ Check Windows Firewall allows Python on port 20777
6. ✅ Try running as Administrator

### Recording file is very small

- You may have recorded while in the menu
- Re-record while actively driving on track

### Replay shows 0 motion packets

- The recording may only contain non-motion packets
- Use `--info` flag to check packet counts
- Re-record while driving (motion packets only sent on track)

### Import errors during replay

- Run from the project root directory
- Verify `src/telemetry/packet_parser.py` exists
- Verify `src/motion/algorithm.py` exists

---

## Technical Notes

- **Byte order:** Little-endian (Intel/AMD standard)
- **Timestamps:** Relative to recording start (first packet ≈ 0.0s)
- **Packet rate:** ~60 packets/second at 60Hz UDP setting
- **Typical file size:** ~1-2 MB per minute of recording
- **F1 24 packet sizes:** 1349-1460 bytes depending on type

---

## Version History

| Version | Date       | Changes                          |
|---------|------------|----------------------------------|
| 1.0     | 2025-01-12 | Initial format (INF-165)         |
