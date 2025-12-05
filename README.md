**PLEASE READ ALL DOCS AND ALL COMMENTS IN CODE FILES!**

# F1 Motion Simulator

Translates F1 game telemetry into motion platform commands for SMC and MOOG hardware.

## Project Structure

```
f1-motion-sim/
├── src/
│   ├── main.py                 # Main entry point
│   ├── telemetry/
│   │   ├── udp_listener.py     # INF-100: Receives F1 UDP packets
│   │   └── packet_parser.py    # INF-103: Parses motion packets
│   ├── drivers/
│   │   ├── smc_driver.py       # INF-105: SMC Modbus driver
│   │   └── moog_driver.py      # INF-108 (Future Sprint): MOOG UDP driver
│   ├── motion/
│   │   └── algorithm.py        # INF-107: Motion algorithm
│   └── utils/
│       ├── config.py           # Configuration loader
│       └── safety.py           # INF-112: Safety limits & E-stop
├── tests/                      # Unit tests
├── config/
│   └── settings.yaml           # Configuration file
├── docs/                       # Documentation
├── requirements.txt            # Python dependencies
└── README.md
```

## Ticket → File Mapping

|         Ticket        | File | Assignee |
|-----------------------|------|----------|
| INF-110: Integrate Telemetry | `src/main.py` | David |
| INF-100: UDP Listener | `src/telemetry/udp_listener.py` | [Teammate] |
| INF-103: Parse Packet | `src/telemetry/packet_parser.py` | David |
| INF-105: SMC Driver   | `src/drivers/smc_driver.py` | [Teammate] |
| INF-107: Motion Algorithm | `src/motion/algorithm.py` | David |
| INF-108 (Future Sprint): MOOG Driver | `src/drivers/moog_driver.py` | Sprint 3 |
| INF-112: Safety Limits | `src/utils/safety.py` | [Unassigned] |

## Setup

### 1. Clone the repository
```bash
git clone <repository-url>
cd f1-motion-sim
```

### 2. Create virtual environment
```bash
python -m venv venv

# Linux/Mac:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure settings
```bash
# Edit config/settings.yaml with your hardware settings
```

## Usage

### Run with SMC actuator
```bash
python -m src.main --hardware smc
```

### Run with MOOG platform
```bash
python -m src.main --hardware moog
```

### Test individual components
```bash
# Test UDP listener
python -m src.telemetry.udp_listener

# Test SMC driver
python -m src.drivers.smc_driver

# Test motion algorithm
python -m src.motion.algorithm
```

## Data Flow

```
F1 Game (UDP:20777)
       ↓
  UDPListener (INF-100)
       ↓
  PacketParser (INF-103)
       ↓
  MotionAlgorithm (INF-107)
       ↓
  SMCDriver (INF-105) or MOOGDriver (INF-108)
       ↓
  Hardware
```

## Development

### Run tests
```bash
pytest tests/
```

### Code formatting
```bash
black src/ tests/
```

### Linting
```bash
flake8 src/ tests/
```

## Hardware Requirements

### SMC Setup
- Controller: LECP6P-LEL25LT-900
- Actuator: LEL25LT (100mm stroke)
- Connection: USB-RS485 adapter → CN5 port
- Baud rate: 38400

### MOOG Setup
- Platform: 6-DOF Stewart platform
- Connection: Ethernet to ETHER PORT
- Protocol: UDP at 60Hz
- Home position: (0, 0, -0.18) meters

## Team

- David - Primary Developer
- [Teammate A] - Hardware Setup
- [Teammate B] - Documentation & Testing
- [Teammate C] - Documentation
