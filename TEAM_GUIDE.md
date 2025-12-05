# F1 Motion Simulator — Team Quick Start

## What Are We Building?

A Python app that makes a motion simulator move based on F1 game physics.

```
F1 Game → UDP Packets → Our Code → Actuator Moves
```

---

## Project Structure (Only the Important Files)

```
src/
├── main.py                 # Ties everything together (INF-110)
├── telemetry/
│   ├── udp_listener.py     # Receives game data (INF-100) ← Kaiser
│   └── packet_parser.py    # Extracts G-forces (INF-103) ← David
├── motion/
│   └── algorithm.py        # Converts G-force → position (INF-107) ← David
├── drivers/
│   ├── smc_driver.py       # Controls SMC actuator (INF-105)
│   └── moog_driver.py      # Controls MOOG platform (INF-108) — Sprint 3
└── utils/
    ├── config.py           # Loads settings (done)
    └── safety.py           # Safety limits (INF-112)

config/
└── settings.yaml           # All configurable values

tests/
├── conftest.py                     # Shared test fixtures
├── telemetry/
│   ├── test_packet_parser.py       # INF-123
│   └── test_udp_listener.py        # INF-126
├── motion/
│   └── test_algorithm.py           # INF-124
├── drivers/
│   ├── test_smc_driver.py          # INF-127
│   └── test_moog_driver.py         # INF-128
└── utils/
    └── test_safety.py              # INF-125
```

---

## Who Does What

### Sprint 2 — Implementation

| Person | Ticket | File | Status |
|--------|--------|------|--------|
| **Kaiser** | INF-100 | `udp_listener.py` | In Progress |
| **David** | INF-103 | `packet_parser.py` | To Do |
| **David** | INF-107 | `algorithm.py` | To Do |
| TBD | INF-105 | `smc_driver.py` | Blocked (need USB adapter) |
| TBD | INF-112 | `safety.py` | To Do |

### Sprint 3 — Unit Tests (20% of grade!)

| Person | Ticket | Test File | Tests For |
|--------|--------|-----------|-----------|
| **David** | INF-123 | `tests/telemetry/test_packet_parser.py` | INF-103 |
| **David** | INF-124 | `tests/motion/test_algorithm.py` | INF-107 |
| **Kaiser** | INF-126 | `tests/telemetry/test_udp_listener.py` | INF-100 |
| TBD | INF-125 | `tests/utils/test_safety.py` | INF-112 |
| TBD | INF-127 | `tests/drivers/test_smc_driver.py` | INF-105 |

### Sprint 4

| Person | Ticket | Test File | Tests For |
|--------|--------|-----------|-----------|
| TBD | INF-128 | `tests/drivers/test_moog_driver.py` | INF-108 |

---

## How to Run

```bash
# Setup (once)
cd f1-motion-sim
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/telemetry/test_packet_parser.py -v

# Run tests matching a pattern
pytest tests/ -k "packet" -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing

# Run the app (once implemented)
python -m src.main --hardware smc
```

### Test Design Techniques (Required: 3 minimum)

1. **Equivalence Partitioning** — valid/invalid packets
2. **Boundary Value Analysis** — g-force limits (-6 to +6)
3. **State Transition Testing** — E-stop states
4. **Error Guessing** — malformed data, timeouts
5. **Mock Testing** — socket/Modbus operations

---

## Finding Your TODOs

Every unfinished method has this pattern:

```python
def some_method(self):
    """
    TODO [YOUR_NAME]: Implement this method

    Steps:
        1. Do this
        2. Then this
        3. Return result
    """
    raise NotImplementedError("INF-XXX: Implement some_method()")
```

**Quick way to find all TODOs:**
```bash
grep -r "NotImplementedError" src/
```

---

## Data Flow Explained

```
1. F1 Game sends UDP packet (port 20777)
         ↓
2. udp_listener.py receives raw bytes
         ↓
3. packet_parser.py extracts:
   - g_force_lateral (turning)
   - g_force_longitudinal (braking/accelerating)
   - g_force_vertical (bumps)
         ↓
4. algorithm.py converts to actuator position
         ↓
5. smc_driver.py or moog_driver.py sends command to hardware
```

---

## Key Numbers to Remember

| What | Value |
|------|-------|
| UDP Port | 20777 |
| Packet rate | 60 Hz |
| Header size | 24 bytes |
| Motion data per car | 60 bytes |
| SMC stroke | 0-100 mm |
| Target latency | < 50 ms |

---

## Blocked? Check These

| Problem | Solution |
|---------|----------|
| Can't test SMC | Need USB-RS485 adapter (INF-117) |
| Can't test MOOG | Need to discover IP/port (INF-106) |
| Import errors | Run `pip install -r requirements.txt` |
| No game data | Enable UDP telemetry in F1 game settings |

---

## Git Workflow

```bash
# Before starting work
git pull

# After finishing a feature
git add .
git commit -m "INF-XXX: Brief description"
git push
```

**Branch naming:** `feature/INF-XXX-short-description`

---

## Dependency Graph (What Blocks What)

```
                    ┌─────────────────┐
                    │  settings.yaml  │
                    │    (INF-111)    │
                    │   ⚠️ PLACEHOLDERS │
                    └────────┬────────┘
                             │ loads
                             ▼
                    ┌─────────────────┐
                    │    config.py    │
                    └────────┬────────┘
                             │
         ┌───────────────────┴───────────────────┐
         ▼                                       ▼
┌─────────────────┐                     ┌─────────────────┐
│  udp_listener   │                     │  packet_parser  │
│   (INF-100)     │ ──────────────────▶ │    (INF-103)    │
│    Kaiser       │   sends bytes to    │     David       │
└─────────────────┘                     └────────┬────────┘
                                                 │
                                                 ▼ TelemetryData
                                        ┌─────────────────┐
                                        │    algorithm    │
                                        │    (INF-107)    │
                                        │     David       │
                                        └────────┬────────┘
                                                 │
                      ┌──────────────────────────┼──────────────────────────┐
                      ▼                          ▼                          ▼
             ┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
             │   smc_driver    │        │   moog_driver   │        │    safety.py    │
             │    (INF-105)    │        │    (INF-108)    │        │    (INF-112)    │
             │   ⚠️ BLOCKED    │        │    Sprint 3     │        │      TBD        │
             └─────────────────┘        └─────────────────┘        └─────────────────┘
                      │                          │
                      │    ┌─────────────────────┘
                      ▼    ▼
             ┌─────────────────┐
             │     main.py     │
             │    (INF-110)    │
             │   Integration   │
             └─────────────────┘
```

### Build Order (Critical Path)

```
IMPLEMENTATION                          TESTS (Sprint 3+)
──────────────                          ─────────────────
INF-100 (UDP Listener)      ──────────▶ INF-126 (UDP tests)
    │
    ▼
INF-103 (Packet Parser)     ──────────▶ INF-123 (Parser tests)
    │
    ▼
INF-107 (Motion Algorithm)  ──────────▶ INF-124 (Algorithm tests)
    │
    ├──▶ INF-105 (SMC Driver) ────────▶ INF-127 (SMC tests)
    │
    └──▶ INF-108 (MOOG Driver) ───────▶ INF-128 (MOOG tests)

INF-112 (Safety Module)     ──────────▶ INF-125 (Safety tests)
```

**Rule:** Implement first, then write tests. Each test ticket depends on its implementation ticket.

---

## Questions?

- **Hardware issues:** Ask Gerard van der Kolk
- **Project scope:** Ask Gert-Jan van der Vegt
- **Code questions:** Check the detailed handover in `docs/F1_Motion_Simulator_Handover.md`
