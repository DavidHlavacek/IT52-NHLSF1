"""
SMC Driver v2.0 - Optimized
"""

"""
_move_to_full vs _move_to_fast:

we use _move_to_full for initiial setup - write to all registers
we use _move_to_fast to write position only - faster and less writes = less latency
"""

"""
IF alarm is on / IF the controller's alarm's led is red:

ALARM NEEDS TO BE RESET, BECAUSE IF ALARM IS ON, THE CONTROLLER BLOCKS ALL COMMANDS!
"""

import struct
import time
from dataclasses import dataclass
from typing import Optional
from pymodbus.client import ModbusSerialClient



@dataclass
class DriverConfig:
    port: str = 'COM5'
    center_mm: float = 350.0
    min_mm: float = 50.0
    max_mm: float = 850.0
    speed: int = 1000 # 500 if too fast
    acceleration: int = 3000
    rate_limit_hz: float = None # try 30 if issues


class SMCDriverV2:
    # modbus addresses
    COIL_SVON = 0x19
    COIL_RESET = 0x1B
    COIL_SETUP = 0x1C
    COIL_INPUT_INVALID = 0x30

    INPUT_BUSY = 0x48
    INPUT_SVRE = 0x49
    INPUT_SETON = 0x4A

    REG_CURRENT_POSITION = 0x9000
    REG_OPERATION_START = 0x9100
    REG_MOVEMENT_MODE = 0x9102
    REG_SPEED = 0x9103
    REG_POSITION = 0x9104
    REG_ACCELERATION = 0x9106
    REG_DECELERATION = 0x9107
    REG_PUSHING_FORCE = 0x9108
    REG_TRIGGER_LEVEL = 0x9109
    REG_PUSHING_SPEED = 0x910A
    REG_MOVING_FORCE = 0x910B
    REG_AREA_1 = 0x910C
    REG_AREA_2 = 0x910E
    REG_IN_POSITION = 0x9110

    def __init__(self, config: DriverConfig = None):
        self.config = config or DriverConfig()
        self.client: Optional[ModbusSerialClient] = None
        self.connected = False
        self.last_command_time = 0.0

    def connect(self) -> bool:
        try:
            self.client = ModbusSerialClient(
                port=self.config.port,
                baudrate=38400,
                parity='N',
                stopbits=1,
                bytesize=8,
                timeout=1.0
            )

            if not self.client.connect():
                print(f"[SMC] Failed to open {self.config.port}")
                return False

            print(f"[SMC] Connected to {self.config.port}")

            # enable serial mode
            self._write_coil(self.COIL_INPUT_INVALID, True)
            time.sleep(0.1)

            # reset alarms
            self._write_coil(self.COIL_RESET, True)
            time.sleep(0.1)
            self._write_coil(self.COIL_RESET, False)
            time.sleep(0.1)

            # servo on
            self._write_coil(self.COIL_SVON, True)
            time.sleep(0.5)

            # wait for servo ready
            print("[SMC] Waiting for servo...")
            for _ in range(50):
                if self._read_input(self.INPUT_SVRE):
                    break
                time.sleep(0.1)
            else:
                print("[SMC] Servo not ready")
                return False

            # homing
            print("[SMC] Homing...")
            self._write_coil(self.COIL_SETUP, True)

            for _ in range(100):
                if self._read_input(self.INPUT_SETON):
                    break
                time.sleep(0.1)
            else:
                print("[SMC] Homing timeout")
                return False

            # IMPORTANT: clear setup coil after homing!
            self._write_coil(self.COIL_SETUP, False)
            time.sleep(0.3)

            # reset alarm from homing
            self._write_coil(self.COIL_RESET, True)
            time.sleep(0.1)
            self._write_coil(self.COIL_RESET, False)
            time.sleep(0.1)

            # setup motion parameters once
            self._setup_motion_parameters()

            # move to center
            print(f"[SMC] Moving to center ({self.config.center_mm}mm)...")
            self._move_to_full(self.config.center_mm)
            self._wait_complete()

            self.connected = True
            print(f"[SMC] Ready at {self._read_position():.0f}mm")
            return True

        except Exception as e:
            print(f"[SMC] Error: {e}")
            return False

    def _setup_motion_parameters(self):
        self._write_registers(self.REG_MOVEMENT_MODE, [1])
        self._write_registers(self.REG_SPEED, [self.config.speed])
        self._write_registers(self.REG_ACCELERATION, [self.config.acceleration])
        self._write_registers(self.REG_DECELERATION, [self.config.acceleration])
        self._write_registers(self.REG_PUSHING_FORCE, [0])
        self._write_registers(self.REG_TRIGGER_LEVEL, [0])
        self._write_registers(self.REG_PUSHING_SPEED, [20])
        self._write_registers(self.REG_MOVING_FORCE, [100])
        self._write_int32(self.REG_AREA_1, 0)
        self._write_int32(self.REG_AREA_2, 0)
        self._write_int32(self.REG_IN_POSITION, 100)

    def send_position(self, position_mm: float) -> bool:
        if not self.connected:
            return False

        # rate limiting
        if self.config.rate_limit_hz is not None:
            now = time.perf_counter()
            min_interval = 1.0 / self.config.rate_limit_hz
            if now - self.last_command_time < min_interval:
                return True
            self.last_command_time = now    

        # clamp to safe range
        position_mm = max(self.config.min_mm, min(self.config.max_mm, position_mm))

        self._move_to_fast(position_mm)
        return True

    def _move_to_fast(self, position_mm: float):
        position_units = int(position_mm * 100)
        self._write_int32(self.REG_POSITION, position_units)
        self._write_registers(self.REG_OPERATION_START, [0x0100])

    def _move_to_full(self, position_mm: float):
        position_units = int(position_mm * 100)

        self._write_registers(self.REG_MOVEMENT_MODE, [1])
        self._write_registers(self.REG_SPEED, [self.config.speed])
        self._write_int32(self.REG_POSITION, position_units)
        self._write_registers(self.REG_ACCELERATION, [self.config.acceleration])
        self._write_registers(self.REG_DECELERATION, [self.config.acceleration])
        self._write_registers(self.REG_PUSHING_FORCE, [0])
        self._write_registers(self.REG_TRIGGER_LEVEL, [0])
        self._write_registers(self.REG_PUSHING_SPEED, [20])
        self._write_registers(self.REG_MOVING_FORCE, [100])
        self._write_int32(self.REG_AREA_1, 0)
        self._write_int32(self.REG_AREA_2, 0)
        self._write_int32(self.REG_IN_POSITION, 100)
        self._write_registers(self.REG_OPERATION_START, [0x0100])

    def close(self):
        if self.connected:
            print("[SMC] Returning to center...")
            self._move_to_fast(self.config.center_mm)
            self._wait_complete()
            self._write_coil(self.COIL_SVON, False)

        if self.client:
            self.client.close()

        self.connected = False
        print("[SMC] Disconnected")

    def _wait_complete(self, timeout: float = 5.0):
        start = time.time()
        while time.time() - start < timeout:
            if not self._read_input(self.INPUT_BUSY):
                return
            time.sleep(0.05)

    def _read_position(self) -> float:
        result = self.client.read_holding_registers(
            self.REG_CURRENT_POSITION, count=2, device_id=1
        )
        if hasattr(result, 'registers') and len(result.registers) >= 2:
            high, low = result.registers
            packed = struct.pack('>HH', high, low)
            units = struct.unpack('>i', packed)[0]
            return units / 100.0
        return 0.0

    def _write_coil(self, address: int, value: bool):
        self.client.write_coil(address, value, device_id=1)

    def _read_input(self, address: int) -> bool:
        result = self.client.read_discrete_inputs(address, count=1, device_id=1)
        return result.bits[0] if hasattr(result, 'bits') else False

    def _write_registers(self, address: int, values: list):
        self.client.write_registers(address, values, device_id=1)

    def _write_int32(self, address: int, value: int):
        packed = struct.pack('>i', value)
        high, low = struct.unpack('>HH', packed)
        self.client.write_registers(address, [high, low], device_id=1)
