# F1 Motion Simulator - User & Installation Manual

**Comprehensive guide for installation, configuration, and operation**

---

## Table of Contents

1. [Safety Precautions](#1-safety-precautions)
2. [System Requirements](#2-system-requirements)
3. [Installation](#3-installation)
4. [Hardware Setup](#4-hardware-setup)
5. [Configuration Guide](#5-configuration-guide)
6. [Usage Instructions](#6-usage-instructions)
7. [Troubleshooting](#7-troubleshooting)
8. [Appendix](#8-appendix)

---

## 1. Safety Precautions

### Critical Warnings

```
  ╔════════════════════════════════════════════════════════════════════╗
  ║  WARNING: MOVING MACHINERY - READ BEFORE OPERATION                 ║
  ║                                                                    ║
  ║  - Keep hands and loose clothing clear of actuators                ║
  ║  - Ensure emergency stop is accessible at all times                ║
  ║  - Never operate with damaged cables or connections                ║
  ║  - Do not exceed rated load capacity of platform                   ║
  ╚════════════════════════════════════════════════════════════════════╝
```

### Before Each Session

1. **Inspect hardware** - Check for loose connections, damaged cables, or debris
2. **Verify E-stop** - Ensure emergency stop button is functional and within reach
3. **Clear the area** - Remove obstacles around the motion platform
4. **Check limits** - Verify software limits are configured correctly in settings.yaml
5. **Start conservative** - Begin with low motion scaling values

### Emergency Procedures

| Situation | Action |
|-----------|--------|
| Platform moving erratically | Press E-stop immediately |
| Software crash during motion | Platform should hold position; restart software |
| Loss of communication | Platform holds last position; check cables |
| Unusual noises/vibration | Press E-stop; inspect hardware before restart |

### Load Limits

| Platform | Maximum Load |
|----------|--------------|
| SMC Actuator | Refer to actuator specifications |
| MOOG 6DOF2000E | 250 kg (including seat and rider) |

---

## 2. System Requirements

### Software Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.10+ | 3.11+ |
| Operating System | Windows 10 / Ubuntu 20.04 | Windows 11 / Ubuntu 22.04 |
| F1 24 Game | Any version | Latest patch |

### Hardware Requirements

#### SMC Setup
- Controller: LECP6P-LEL25LT-900
- Actuator: LEL25LT (900mm stroke)
- Connection: USB-RS485 adapter to CN4 port
- Cable: 3-wire (A+, B-, GND)

#### MOOG Setup
- Platform: 6DOF2000E Stewart platform
- Connection: Ethernet cable to ETHER PORT
- Network: Static IP configuration

### Network Requirements

| Service | Port | Protocol | Direction |
|---------|------|----------|-----------|
| F1 Telemetry | 20777 | UDP | Inbound |
| MOOG Platform | 6000 | UDP | Outbound |

---

## 3. Installation

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd f1-motion-sim
```

### Step 2: Create Virtual Environment

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `pymodbus` - SMC Modbus communication
- `pyserial` - Serial port access
- `PyYAML` - Configuration file parsing
- `pytest` - Testing framework

### Step 4: Verify Installation

```bash
python -c "from src.main import F1MotionSimulator; print('Installation OK')"
```

### Step 5: Configure F1 Game

Enable UDP telemetry in F1 24:

1. Launch F1 24
2. Go to **Settings > Telemetry Settings**
3. Set **UDP Telemetry** to **On**
4. Set **UDP Port** to **20777** (default)
5. Set **UDP Send Rate** to **60Hz**
6. Set **UDP Format** to **2024**

---

## 4. Hardware Setup

### SMC Actuator Wiring

#### Communication Cable (CN4)

```
  USB-RS485 Adapter              SMC Controller (CN4)
  ┌─────────────────┐            ┌─────────────────┐
  │                 │            │                 │
  │  A+ (Data+)  ───┼────────────┼─── Pin 1 (A+)   │
  │  B- (Data-)  ───┼────────────┼─── Pin 2 (B-)   │
  │  GND         ───┼────────────┼─── Pin 3 (GND)  │
  │                 │            │                 │
  └─────────────────┘            └─────────────────┘
```

**Note:** Either the LEC-W2-U cable or a standard USB-RS485 adapter can be used.

#### E-Stop Connection (Required)

The E-stop must be connected for the SMC controller to operate. Connect a normally-closed (NC) E-stop switch to the EMG (emergency stop) terminals on the controller. Without this connection, the controller will not enable the servo.

```
  E-Stop Switch (NC)             SMC Controller
  ┌─────────────────┐            ┌─────────────────┐
  │                 │            │                 │
  │  COM         ───┼────────────┼─── EMG1         │
  │  NC          ───┼────────────┼─── EMG2         │
  │                 │            │                 │
  └─────────────────┘            └─────────────────┘
```

**If no E-stop switch is available:** Bridge/jumper the EMG terminals to bypass (for testing only - not recommended for normal operation).

### SMC Controller Configuration

Before first use, configure the controller using ACT Controller software. Choose one of the following options:

#### Option A: Import Pre-configured Settings (Recommended)

A backup file (`LECP6_F1_Config.dat`) is provided in this folder with all settings pre-configured.

1. Open ACT Controller software
2. Connect to the controller via LEC-W2-U cable
3. Go to **File > Open** and select `LECP6_F1_Config.dat`
4. Go to **Communication > PC -> Controller** to upload settings to the controller
5. **Perform homing:** Execute return-to-origin to establish position reference

#### Option B: Manual Configuration

1. Set baud rate to **38400**
2. Set controller ID to **1**
3. Configure home position at **450mm** (physical center)
4. **Perform homing:** Execute return-to-origin to establish position reference

**Note:** Homing must be performed after importing settings or after power cycling the controller.

### MOOG Platform Connection

```
  Computer                        MOOG Platform
  ┌─────────────────┐            ┌─────────────────┐
  │                 │            │                 │
  │  Ethernet    ───┼────────────┼─── ETHER PORT   │
  │  (Static IP)    │            │  (192.168.1.100)│
  │                 │            │                 │
  └─────────────────┘            └─────────────────┘
```

Configure your computer's network adapter:
- IP: 192.168.1.10 (or any address on same subnet)
- Subnet: 255.255.255.0
- Gateway: 192.168.1.1

---

## 5. Configuration Guide

All settings are in `config/settings.yaml`. Edit this file to match your hardware and preferences.

### Telemetry Settings

```yaml
telemetry:
  port: 20777           # Must match F1 game settings
  buffer_size: 2048     # UDP buffer size (default is fine)
```

| Parameter | Description | Default | Range |
|-----------|-------------|---------|-------|
| `port` | UDP port for F1 telemetry | 20777 | 1024-65535 |
| `buffer_size` | Receive buffer size in bytes | 2048 | 1024-8192 |

### Motion Algorithm Settings

```yaml
motion:
  translation_scale: 0.1  # G-force to meters conversion
  rotation_scale: 0.5     # Rotation multiplier
  onset_gain: 1.0         # High-pass filter gain
  sustained_gain: 0.4     # Low-pass filter gain
  deadband: 0.08          # Noise threshold
  sample_rate: 60.0       # Telemetry rate (Hz)
  washout_freq: 0.4       # High-pass cutoff (Hz)
  sustained_freq: 3.0     # Low-pass cutoff (Hz)
  slew_rate: 0.4          # Max position change (m/s)
```

| Parameter | Description | Default | Tuning Notes |
|-----------|-------------|---------|--------------|
| `translation_scale` | G-force to meters (1G = Xcm) | 0.1 | Higher = more movement. Start at 0.05 |
| `rotation_scale` | Angle multiplier | 0.5 | 0.5 = 50% of game rotation |
| `onset_gain` | Sudden movement intensity | 1.0 | Higher = stronger braking/acceleration feel |
| `sustained_gain` | Sustained tilt intensity | 0.4 | Higher = more sustained cornering feel |
| `deadband` | Ignore small movements | 0.08 | Higher = less jitter, less sensitivity |
| `washout_freq` | How fast onset cues fade | 0.4 | Lower = longer onset feel |
| `sustained_freq` | Smoothing for sustained | 3.0 | Lower = smoother but more lag |
| `slew_rate` | Max velocity limit | 0.4 | Prevents jerky motion |

### SMC Hardware Settings

```yaml
hardware:
  smc:
    port: "/dev/ttyUSB0"        # Linux. Windows: "COM3"
    baudrate: 38400             # Fixed by protocol
    parity: "E"                 # Even parity
    controller_id: 1            # Modbus slave ID
    stroke_mm: 900.0            # Actuator stroke length
    min_command_interval: 0.05  # Rate limiting (seconds)
    position_threshold_mm: 1.0  # Minimum movement to send
    limits:
      surge_m: 0.45             # +/-450mm from center
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `port` | Serial port path | /dev/ttyUSB0 |
| `baudrate` | Communication speed | 38400 |
| `controller_id` | Modbus slave address | 1 |
| `stroke_mm` | Physical stroke length | 900 |
| `min_command_interval` | Seconds between commands | 0.05 |
| `position_threshold_mm` | Min position delta to send | 1.0 |
| `limits.surge_m` | Max travel from center | 0.45 |

### MOOG Hardware Settings

```yaml
hardware:
  moog:
    ip: "192.168.1.100"       # Platform IP address
    port: 6000                # UDP port
    send_rate_hz: 60.0        # Command rate
    limits:
      surge_pos_m: 0.259      # Forward limit
      surge_neg_m: 0.241      # Backward limit (asymmetric)
      sway_m: 0.259           # Left/right
      heave_m: 0.178          # Up/down
      roll_rad: 0.3665        # +/-21 degrees
      pitch_rad: 0.3840       # +/-22 degrees
      yaw_rad: 0.3840         # +/-22 degrees
```

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ip` | Platform IP address | 192.168.1.100 |
| `port` | UDP port | 6000 |
| `send_rate_hz` | Command send rate | 60.0 |
| `limits.surge_pos_m` | Forward limit (asymmetric) | 0.259 |
| `limits.surge_neg_m` | Backward limit (asymmetric) | 0.241 |
| `limits.sway_m` | Left/right limit | 0.259 |
| `limits.heave_m` | Up/down limit | 0.178 |
| `limits.roll_rad` | Roll limit (+/-21 deg) | 0.3665 |
| `limits.pitch_rad` | Pitch limit (+/-22 deg) | 0.3840 |
| `limits.yaw_rad` | Yaw limit (+/-22 deg) | 0.3840 |

---

## 6. Usage Instructions

### Starting the Simulator

#### With SMC Actuator

```bash
python -m src.main --hardware smc
```

#### With MOOG Platform

```bash
python -m src.main --hardware moog
```

### Startup Sequence

```
  ┌─────────────────────────────────────────────────────────────┐
  │  1. Start simulator software                                │
  │         ↓                                                   │
  │  2. Software initializes hardware                           │
  │         ↓                                                   │
  │  3. Platform moves to home/center position                  │
  │         ↓                                                   │
  │  4. "Setup complete" message appears                        │
  │         ↓                                                   │
  │  5. Start F1 game and enter a session                       │
  │         ↓                                                   │
  │  6. Platform responds to telemetry                          │
  └─────────────────────────────────────────────────────────────┘
```

### Normal Operation

1. **Start the simulator** - Run the appropriate command above
2. **Wait for initialization** - Software will connect to hardware and home the platform
3. **Launch F1 24** - Start the game
4. **Enter a session** - Practice, Time Trial, or Race
5. **Drive** - Platform will respond to vehicle motion
6. **Exit cleanly** - Press `Ctrl+C` in terminal to stop

### Shutdown Sequence

Press `Ctrl+C` to stop the simulator. The software will:
1. Log latency statistics
2. Return platform to home position
3. Close hardware connections
4. Exit cleanly

### Testing Individual Components

```bash
# Test UDP listener (requires F1 game running)
python -m src.telemetry.udp_listener

# Test motion algorithm (uses recorded telemetry)
python -m src.motion.algorithm

# Test SMC driver (moves actuator)
python -m src.drivers.smc_driver
```

---

## 7. Troubleshooting

### Connection Issues

#### COM Port Not Found (Windows)

**Symptoms:** Error: "could not open port 'COM3'"

**Solutions:**
1. Check Device Manager for correct COM port number
2. Update settings.yaml with correct port
3. Ensure USB-RS485 adapter is connected
4. Install adapter drivers if needed

#### Serial Port Permission Denied (Linux)

**Symptoms:** Error: "Permission denied: '/dev/ttyUSB0'"

**Solutions:**
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Log out and back in, or run:
newgrp dialout
```

#### UDP Not Receiving Data

**Symptoms:** "Starting main loop..." but no motion

**Solutions:**
1. Verify F1 game telemetry settings (UDP On, port 20777)
2. Check firewall allows UDP port 20777
3. Ensure game is in an active session (not menus)
4. Test with: `python -m src.telemetry.udp_listener`

### Hardware Issues

#### SMC Actuator Not Responding

| Check | Solution |
|-------|----------|
| Wiring | Verify A+, B-, GND connections |
| Baud rate | Must be 38400 in both software and controller |
| Controller ID | Default is 1, check ACT Controller settings |
| Serial mode | Software enables this automatically |
| Alarm state | May need reset via ACT Controller |

#### MOOG Platform Not Moving

| Check | Solution |
|-------|----------|
| Network | Verify IP addresses and subnet |
| Cable | Test Ethernet connection |
| Platform state | Must be in "Engaged" mode |
| Firewall | Allow UDP traffic on configured port |

### Motion Issues

#### No Motion Response

1. Verify telemetry is being received (check terminal output)
2. Increase `translation_scale` in settings.yaml
3. Reduce `deadband` value
4. Check hardware limits aren't too restrictive

#### Jerky/Oscillating Motion

1. Reduce `slew_rate` value
2. Increase `min_command_interval`
3. Increase `deadband`
4. Lower `onset_gain`

#### Motion Feels Delayed

1. Increase `sustained_freq`
2. Reduce `washout_freq`
3. Decrease `min_command_interval`
4. Check system latency stats on shutdown

### Latency Issues

The simulator logs latency statistics on shutdown:

```
Latency stats: avg=1.2ms, max=5.3ms, >20ms: 0.0%
```

| Metric | Good | Investigate |
|--------|------|-------------|
| Average | <5ms | >10ms |
| Maximum | <20ms | >50ms |
| % over threshold | 0% | >1% |

If latency is high:
1. Close other applications
2. Disable antivirus real-time scanning
3. Check CPU usage
4. Use wired network connection (MOOG)

---

## 8. Appendix

### System Architecture

```
  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
  │  F1 24 Game   │    │    Motion     │    │    Safety     │    │   Hardware    │
  │  UDP @ 60Hz   │───>│   Algorithm   │───>│    Module     │───>│    Driver     │───> Platform
  │               │    │               │    │               │    │               │
  └───────────────┘    └───────────────┘    └───────────────┘    └───────────────┘
         │                    │                    │                    │
    Raw UDP bytes       Position6DOF          1st clamp            2nd clamp
    (1349 bytes)        (unclamped)         + E-stop check      + speed limit
```

The safety module provides **defense in depth** - position clamping happens in both the safety module AND the hardware driver (double protection).

### Motion Mapping

| Game Event | G-Force | Platform Response |
|------------|---------|-------------------|
| Accelerating | Negative longitudinal | Tilt backward |
| Braking | Positive longitudinal | Tilt forward |
| Right turn | Positive lateral | Tilt right |
| Left turn | Negative lateral | Tilt left |
| Bump/compression | Increased vertical | Platform drops |
| Airborne | Decreased vertical | Platform rises |

### File Locations

| File | Purpose |
|------|---------|
| `config/settings.yaml` | All configuration parameters |
| `src/main.py` | Main entry point |
| `src/motion/algorithm.py` | Motion processing |
| `src/safety/safety.py` | Safety limits and E-stop |
| `src/drivers/smc_driver.py` | SMC hardware control |
| `src/drivers/moog_driver.py` | MOOG hardware control |

### Useful Commands

```bash
# Run with verbose logging
python -m src.main --hardware smc 2>&1 | tee session.log

# Run tests
pytest tests/ -v

# Check configuration syntax
python -c "from src.utils.config import load_config; print(load_config())"
```

### Support

For issues not covered in this manual:
1. Review code comments for implementation details
2. Contact project maintainers

---

*F1 Motion Simulator Project - INF-163 User Manual* 

*Last Updated: January 2026*
