"""
SMC Modbus Driver for LECP6P-LEL25LT-900 actuator
Modbus RTU over RS485, 900mm stroke

INF-105: Core driver implementation
INF-149: Command rate limiting
"""

import struct
import time
from typing import Optional
from src.shared.types import Position6DOF

try:
    from pymodbus.client import ModbusSerialClient
except ImportError:
    from pymodbus.client.sync import ModbusSerialClient




class SMCDriver:
    # Coils
    COIL_SVON = 0x19
    COIL_RESET = 0x1B
    COIL_SETUP = 0x1C
    COIL_INPUT_INVALID = 0x30

    # Inputs
    INPUT_BUSY = 0x48
    INPUT_SVRE = 0x49
    INPUT_SETON = 0x4A
    INPUT_ALARM = 0x4F

    # Registers
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

    def __init__(self, config: dict):
        self.port = config.get('port', 'COM5')
        self.baudrate = config.get('baudrate', 38400)
        self.parity = config.get('parity', 'N')
        self.device_id = config.get('controller_id', 1)

        self.center_mm = config.get('center_mm', 450.0)
        self.stroke_mm = config.get('stroke_mm', 900.0)
        self.speed = config.get('speed_mm_s', 500)
        self.acceleration = config.get('accel_mm_s2', 3000)
        self.deceleration = config.get('decel_mm_s2', 3000)

        limits = config.get('limits', {})
        self.max_position_m = limits.get('surge_m', 0.40)

        # rate limiting (INF-149)
        self.min_command_interval = config.get('min_command_interval', 0.05)
        self.position_threshold_mm = config.get('position_threshold_mm', 1.0)
        self._last_command_time = 0.0
        self._last_position_mm = None
        self._commands_sent = 0
        self._commands_skipped = 0

        self.client: Optional[ModbusSerialClient] = None
        self._connected = False

    def connect(self) -> bool:
        try:
            self.client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=1,
                bytesize=8,
                timeout=1.0
            )

            if not self.client.connect():
                print(f"[SMC] Failed to open {self.port}")
                return False

            print(f"[SMC] Connected to {self.port}")

            self._write_coil(self.COIL_INPUT_INVALID, True)
            time.sleep(0.1)

            # reset alarms
            self._write_coil(self.COIL_RESET, True)
            time.sleep(0.1)
            self._write_coil(self.COIL_RESET, False)
            time.sleep(0.1)

            self._write_coil(self.COIL_SVON, True)
            time.sleep(0.5)

            # wait for servo ready
            print("[SMC] Waiting for servo ready...")
            for _ in range(50):
                if self._read_input(self.INPUT_SVRE):
                    print("[SMC] Servo ready")
                    break
                time.sleep(0.1)
            else:
                print("[SMC] ERROR: Servo not ready")
                return False

            # homing
            print("[SMC] Homing...")
            self._write_coil(self.COIL_SETUP, True)

            for _ in range(100):
                if self._read_input(self.INPUT_SETON):
                    print("[SMC] Homing complete (SETON high)")
                    break
                time.sleep(0.1)
            else:
                print("[SMC] ERROR: Homing timeout")
                return False

            # CRITICAL: Clear SETUP coil IMMEDIATELY after SETON goes high!
            # Leaving SETUP high causes alarm state
            self._write_coil(self.COIL_SETUP, False)
            time.sleep(0.3)

            # Reset any alarm that may have triggered during homing
            print("[SMC] Resetting any homing alarm...")
            self._write_coil(self.COIL_RESET, True)
            time.sleep(0.1)
            self._write_coil(self.COIL_RESET, False)
            time.sleep(0.2)

            # Check alarm status (ALARM input: high = OK, low = alarm active)
            if self._read_input(self.INPUT_ALARM):
                print("[SMC] No alarm active")
            else:
                print("[SMC] WARNING: Alarm still active, retrying reset...")
                self._write_coil(self.COIL_RESET, True)
                time.sleep(0.1)
                self._write_coil(self.COIL_RESET, False)
                time.sleep(0.2)

            pos = self._read_position_mm()
            print(f"[SMC] Position after homing: {pos:.1f}mm")

            # move to center
            print(f"[SMC] Moving to center ({self.center_mm}mm)...")
            self._move_to_physical_mm(self.center_mm)
            time.sleep(0.1)
            self._wait_complete(timeout=5.0)

            pos = self._read_position_mm()
            if abs(pos - self.center_mm) > 10:
                self._move_to_physical_mm(self.center_mm)
                time.sleep(0.1)
                self._wait_complete(timeout=5.0)
                pos = self._read_position_mm()

            print(f"[SMC] Ready at {pos:.1f}mm")
            self._connected = True
            return True

        except Exception as e:
            print(f"[SMC] Connection error: {e}")
            return False

    def send_position(self, position: Position6DOF) -> bool:
        if not self._connected:
            if not self.connect():
                return False

        surge_m = max(-self.max_position_m, min(self.max_position_m, position.x))
        game_mm = surge_m * 1000.0

        # rate limiting
        now = time.time()
        if now - self._last_command_time < self.min_command_interval:
            self._commands_skipped += 1
            return False

        if self._last_position_mm is not None:
            if abs(game_mm - self._last_position_mm) < self.position_threshold_mm:
                self._commands_skipped += 1
                return False

        physical_mm = self.center_mm + game_mm
        physical_mm = max(1.0, min(self.stroke_mm - 1.0, physical_mm))

        if self._move_to_physical_mm(physical_mm):
            self._last_command_time = now
            self._last_position_mm = game_mm
            self._commands_sent += 1
            return True

        return False

    def _move_to_physical_mm(self, position_mm: float) -> bool:
        try:
            position_units = int(position_mm * 100)

            self._write_registers(self.REG_MOVEMENT_MODE, [1])
            self._write_registers(self.REG_SPEED, [self.speed])
            self._write_int32(self.REG_POSITION, position_units)
            self._write_registers(self.REG_ACCELERATION, [self.acceleration])
            self._write_registers(self.REG_DECELERATION, [self.deceleration])
            self._write_registers(self.REG_PUSHING_FORCE, [0])
            self._write_registers(self.REG_TRIGGER_LEVEL, [0])
            self._write_registers(self.REG_PUSHING_SPEED, [20])
            self._write_registers(self.REG_MOVING_FORCE, [100])
            self._write_int32(self.REG_AREA_1, 0)
            self._write_int32(self.REG_AREA_2, 0)
            self._write_int32(self.REG_IN_POSITION, 100)

            self._write_registers(self.REG_OPERATION_START, [0x0100])
            return True

        except Exception as e:
            print(f"[SMC] Move error: {e}")
            return False

    def get_position_mm(self) -> float:
        if not self._connected:
            return 0.0
        return self._read_position_mm() - self.center_mm

    def get_physical_position_mm(self) -> float:
        if not self._connected:
            return 0.0
        return self._read_position_mm()

    def is_busy(self) -> bool:
        if not self._connected:
            return False
        return self._read_input(self.INPUT_BUSY)

    def has_alarm(self) -> bool:
        if not self._connected:
            return False
        return self._read_input(self.INPUT_ALARM)

    def reset_alarm(self) -> bool:
        if not self._connected:
            return False
        try:
            self._write_coil(self.COIL_RESET, True)
            time.sleep(0.1)
            self._write_coil(self.COIL_RESET, False)
            return True
        except:
            return False

    def get_stats(self) -> dict:
        total = self._commands_sent + self._commands_skipped
        return {
            "commands_sent": self._commands_sent,
            "commands_skipped": self._commands_skipped,
            "total_requests": total,
            "skip_rate": self._commands_skipped / max(1, total)
        }

    def reset_stats(self):
        self._commands_sent = 0
        self._commands_skipped = 0

    def close(self):
        if self._connected:
            try:
                print("[SMC] Returning to center...")
                self._move_to_physical_mm(self.center_mm)
                self._wait_complete(timeout=5.0)

                self._write_coil(self.COIL_SVON, False)
                print("[SMC] Servo OFF")
            except Exception as e:
                print(f"[SMC] Shutdown error: {e}")

        if self.client:
            self.client.close()

        self._connected = False
        print(f"[SMC] Disconnected. Stats: {self.get_stats()}")

    def _wait_complete(self, timeout: float = 10.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if not self._read_input(self.INPUT_BUSY):
                return True
            time.sleep(0.05)
        print("[SMC] Movement timeout")
        return False

    def _write_coil(self, address: int, value: bool):
        self.client.write_coil(address, value, device_id=self.device_id)

    def _read_input(self, address: int) -> bool:
        result = self.client.read_discrete_inputs(address, count=1, device_id=self.device_id)
        if hasattr(result, 'bits'):
            return result.bits[0]
        return False

    def _write_registers(self, address: int, values: list):
        self.client.write_registers(address, values, device_id=self.device_id)

    def _write_int32(self, address: int, value: int):
        packed = struct.pack('>i', value)
        high, low = struct.unpack('>HH', packed)
        self.client.write_registers(address, [high, low], device_id=self.device_id)

    def _read_position_mm(self) -> float:
        result = self.client.read_holding_registers(self.REG_CURRENT_POSITION, count=2, device_id=self.device_id)
        if hasattr(result, 'registers') and len(result.registers) >= 2:
            high, low = result.registers
            packed = struct.pack('>HH', high, low)
            units = struct.unpack('>i', packed)[0]
            return units / 100.0
        return 0.0


if __name__ == '__main__':
    config = {
        'port': 'COM5',
        'baudrate': 38400,
        'controller_id': 1,
        'center_mm': 450.0,
        'speed_mm_s': 500,
        'accel_mm_s2': 3000,
        'decel_mm_s2': 3000,
        'limits': {'surge_m': 0.35},
    }
    
    driver = SMCDriver(config)
    
    try:
        if driver.connect():
            print("\nTesting movement...")
            
            test_positions = [
                (0.0, "Center"),
                (0.2, "+200mm"),
                (-0.2, "-200mm"),
                (0.0, "Center"),
            ]
            
            for pos_m, desc in test_positions:
                print(f"Moving to {desc}...")
                driver.send_position(Position6DOF(x=pos_m))
                time.sleep(1.5)
                actual = driver.get_position_mm()
                print(f"  Commanded: {pos_m*1000:.0f}mm, Actual: {actual:.1f}mm")
    finally:
        driver.close()