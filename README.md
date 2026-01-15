# F1 Motion Simulator

Professional-grade single-axis motion simulator that translates F1 2024 Xbox telemetry into physical actuator movement.

## Pipeline

```
F1 2024 (Xbox) → UDP Listener → Packet Parser → Motion Algorithm → SMC Driver → Actuator
     │              │               │                 │                │
   60Hz UDP    Port 20777     F1 2024 Format    Washout Filter    Rate-limited
                                                                   (30Hz)
```

## Hardware

- **Controller:** SMC LECP6P (Step Motor Controller, PNP type)
- **Actuator:** SMC LEL25LT-900 (Electric Linear Slider, 900mm stroke)
- **Communication:** RS485 via USB adapter at 38400 baud
- **Game:** F1 2024 on Xbox, UDP telemetry enabled (port 20777)

## Quick Start

### 1. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 2. Configure Hardware

Edit `config/settings.yaml`:
- Set `hardware.smc.port` to your USB-RS485 adapter port
- Adjust motion parameters as needed

### 3. Enable F1 2024 Telemetry

In F1 2024 on Xbox:
1. Go to Settings → Telemetry Settings
2. Set UDP Telemetry to "On"
3. Set IP Address to your PC's IP
4. Set Port to 20777

### 4. Run the Simulator

```bash
# Default mode (surge/braking feel)
python -m src.main

# Select different dimension
python -m src.main --dimension sway    # Cornering feel
python -m src.main --dimension heave   # Bump/kerb feel

# Test without hardware
python -m src.main --dry-run

# Debug mode
python -m src.main --debug
```

## Dimension Options

| Dimension | Feel | Best For |
|-----------|------|----------|
| `surge` | Braking/acceleration | Most realistic overall feel |
| `sway` | Cornering G-forces | High-speed corners |
| `heave` | Bumps and kerbs | Track surface feedback |
| `pitch` | Nose dive/lift | Brake dive sensation |
| `roll` | Body lean | Corner entry feel |

## Project Structure

```
f1-motion-sim/
├── src/
│   ├── main.py                 # Main entry point
│   ├── telemetry/
│   │   ├── udp_listener.py     # F1 UDP packet receiver
│   │   └── packet_parser.py    # F1 2024 packet parser
│   ├── drivers/
│   │   ├── smc_driver.py       # SMC Modbus RTU driver
│   │   └── moog_driver.py      # MOOG driver (future)
│   ├── motion/
│   │   └── algorithm.py        # Washout filter algorithm
│   └── utils/
│       ├── config.py           # Configuration loader
│       └── safety.py           # Safety limits
├── tests/                      # Unit tests
├── config/
│   └── settings.yaml           # Configuration file
└── docs/                       # Documentation
```

## Architecture

### Motion Algorithm

The motion algorithm uses a **high-pass washout filter** to:
1. Provide onset cue (initial motion sensation from G-force changes)
2. Gradually return to center (washout) to stay within travel limits
3. Apply slew rate limiting to prevent jerky motion

```
G-Force Input → Deadband → High-Pass Filter → Gain → Slew Rate Limit → Position
                   │              │              │           │
              Noise reject   Washout      Scale to mm    Anti-jerk
```

### Anti-Oscillation Measures

Previous implementations had oscillation issues. This rebuild addresses them:

1. **Rate-limited commands** - 30Hz max to SMC controller (not 60Hz)
2. **Slew rate limiting** - Max 500mm/s position change
3. **Deadband** - Ignore small input changes (0.05G default)
4. **Motion profiles** - Acceleration/deceleration ramping
5. **High-pass washout** - Prevents sustained positions that fight the filter

### Startup Sequence

1. Connect to SMC controller
2. Enable serial mode
3. Turn servo ON
4. Perform homing sequence
5. Move to center position (450mm)
6. Wait for stabilization
7. Begin accepting telemetry

### Shutdown Sequence

1. Stop accepting new commands
2. Return actuator to center
3. Turn servo OFF
4. Close connections

## Configuration

All parameters are in `config/settings.yaml`. Key settings:

### Motion Settings
```yaml
motion:
  dimension: surge              # Which input drives actuator
  highpass_cutoff_hz: 1.0       # Washout speed (0.5-2.0 Hz)
  gain: 100.0                   # mm per G
  deadband: 0.05                # Noise rejection threshold
  slew_rate_limit: 500.0        # Max mm/s change
```

### Hardware Settings
```yaml
hardware:
  smc:
    port: "/dev/ttyUSB0"        # Serial port
    command_rate_hz: 30.0       # Don't exceed 30Hz!
    default_speed: 500          # mm/s
```

## Tuning Guide

1. **Start conservative**: `gain: 50.0`
2. **Test gently**: Brake softly in game
3. **Increase gradually**: Raise gain in steps of 25
4. **If oscillation occurs**:
   - Lower `command_rate_hz` to 20
   - Increase `deadband` to 0.1
   - Decrease `slew_rate_limit` to 300
5. **Adjust feel**:
   - Lower `highpass_cutoff_hz` (0.5) = more sustained
   - Higher `highpass_cutoff_hz` (2.0) = quicker return

## Latency

**Target: <1ms processing latency** (excluding network and hardware delays)

The system achieves this through:
- Pre-compiled struct formats for packet parsing
- Non-blocking socket I/O
- Minimal allocations in hot path
- Rate-limited output (30Hz) decoupled from input (60Hz)

Run with `--debug` to see latency statistics.

## Testing

```bash
# Run all tests
pytest tests/

# Test individual modules
python -m src.telemetry.udp_listener    # Test UDP reception
python -m src.telemetry.packet_parser   # Test packet parsing
python -m src.motion.algorithm          # Test motion algorithm
python -m src.drivers.smc_driver        # Test SMC communication
```

## Troubleshooting

### No packets received
- Check F1 2024 telemetry settings
- Verify PC IP address is correct in game
- Check firewall allows UDP port 20777

### Oscillation
- Reduce `command_rate_hz` to 20
- Increase `deadband` to 0.1
- Check mechanical mounting

### Random movements
- Increase `deadband`
- Check USB-RS485 connection
- Verify Modbus settings match controller

### Motion doesn't match game
- Adjust `gain` (higher = more motion)
- Tune `highpass_cutoff_hz` for washout feel
- Try different `dimension` setting

## Requirements

- Python 3.8+
- pymodbus (for SMC communication)
- PyYAML (for configuration)

## License

[Project License]

## References

- [F1 2024 UDP Specification](https://forums.ea.com/discussions/f1-24-general-discussion-en/f1-24-udp-specification/8369125)
- [SMC LECP6 Modbus Register Map](docs/SMC_LECP6_Modbus_Register_Map.md)
- Motion cueing theory: Classical washout filter design
