# F1 24 UDP Telemetry Format

Official packet format for F1 24 (EA Sports).

**Source:** [EA Forums - F1 24 UDP Specification](https://answers.ea.com/t5/General-Discussion/F1-24-UDP-Specification/td-p/13745220)

## Packet Header (29 bytes)

| Offset | Field | Type | Size | Description |
|--------|-------|------|------|-------------|
| 0 | packet_format | int16 | 2 | 2024 |
| 2 | game_year | uint8 | 1 | 24 |
| 3 | game_major_version | uint8 | 1 | e.g. 1 |
| 4 | game_minor_version | uint8 | 1 | e.g. 21 |
| 5 | packet_version | uint8 | 1 | Packet spec version |
| 6 | packet_id | uint8 | 1 | See packet types below |
| 7 | session_uid | uint64 | 8 | Unique session identifier |
| 15 | session_time | float | 4 | Session time in seconds |
| 19 | frame_identifier | uint32 | 4 | Frame number |
| 23 | overall_frame_identifier | uint32 | 4 | Overall frame number |
| 27 | player_car_index | uint8 | 1 | Index of player's car |
| 28 | secondary_player_car_index | uint8 | 1 | Splitscreen player (255 if none) |

**Python struct format:** `'<hBBBBBQfIIBB'`

## Packet Types (packet_id)

| ID | Name | Size (bytes) |
|----|------|--------------|
| 0 | Motion | 1349 |
| 1 | Session | 753 |
| 2 | Lap Data | 1285 |
| 3 | Event | varies |
| 4 | Participants | varies |
| 5 | Car Setups | 1133 |
| 6 | Car Telemetry | 1352 |
| 7 | Car Status | 1239 |
| 10 | Car Damage | 953 |
| 11 | Session History | 1460 |
| 12 | Tyre Sets | 231 |
| 13 | Motion Ex | 237 |

## Motion Packet (packet_id = 0)

Total size: 1349 bytes (29 header + 22 cars × 60 bytes)

### CarMotionData (60 bytes per car)

| Offset | Field | Type | Size | Description |
|--------|-------|------|------|-------------|
| 0 | world_position_x | float | 4 | World X position |
| 4 | world_position_y | float | 4 | World Y position |
| 8 | world_position_z | float | 4 | World Z position |
| 12 | world_velocity_x | float | 4 | Velocity X (m/s) |
| 16 | world_velocity_y | float | 4 | Velocity Y (m/s) |
| 20 | world_velocity_z | float | 4 | Velocity Z (m/s) |
| 24 | world_forward_dir_x | int16 | 2 | Forward direction X (normalized) |
| 26 | world_forward_dir_y | int16 | 2 | Forward direction Y |
| 28 | world_forward_dir_z | int16 | 2 | Forward direction Z |
| 30 | world_right_dir_x | int16 | 2 | Right direction X (normalized) |
| 32 | world_right_dir_y | int16 | 2 | Right direction Y |
| 34 | world_right_dir_z | int16 | 2 | Right direction Z |
| 36 | g_force_lateral | float | 4 | Lateral G-force |
| 40 | g_force_longitudinal | float | 4 | Longitudinal G-force |
| 44 | g_force_vertical | float | 4 | Vertical G-force |
| 48 | yaw | float | 4 | Yaw angle (radians) |
| 52 | pitch | float | 4 | Pitch angle (radians) |
| 56 | roll | float | 4 | Roll angle (radians) |

**Python struct format:** `'<ffffffhhhhhhffffff'`

## G-Force Reference

| Value | Meaning |
|-------|---------|
| g_force_lateral > 0 | Turning right |
| g_force_lateral < 0 | Turning left |
| g_force_longitudinal > 0 | Accelerating |
| g_force_longitudinal < 0 | Braking |
| g_force_vertical ≈ 1.0 | Normal (gravity) |

Typical ranges during racing: ±5 G lateral, ±5 G longitudinal.

## Notes

- All values are **little-endian**
- All data is **packed** (no padding)
- Maximum 22 cars in data structures
- Use `player_car_index` to find player's car in the array
