"""
SMC LECP6P Modbus RTU Driver - Complete Implementation

Controls the SMC electric actuator via Modbus RTU over RS485.

Hardware:
    - Controller: SMC LECP6P (Step Motor Controller, PNP type)
    - Actuator: SMC LEL25LT-900 (900mm stroke)
    - Communication: RS485 via USB adapter at 38400 baud
    - Position units: 0.01mm (100 units = 1mm)

CRITICAL: After homing (SETUP coil), must clear SETUP coil once SETON goes high!
         Leaving SETUP high causes alarm state.
"""

import struct
import time
import logging
from typing import Optional
from dataclasses import dataclass

# pymodbus for Modbus communication
try:
    from pymodbus.client import ModbusSerialClient
except ImportError:
    try:
        from pymodbus.client.sync import ModbusSerialClient
    except ImportError:
        ModbusSerialClient = None

logger = logging.getLogger(__name__)


@dataclass
class SMCConfig:
    """Configuration for SMC controller connection."""
    port: str = '/dev/ttyUSB0'
    baudrate: int = 38400
    parity: str = 'N'
    controller_id: int = 1
    stroke_mm: float = 900.0
    center_mm: float = 450.0
    soft_limit_mm: float = 5.0
    default_speed: int = 500
    default_accel: int = 3000
    default_decel: int = 3000
    command_rate_hz: float = 30.0

    @property
    def min_position_mm(self) -> float:
        return self.soft_limit_mm

    @property
    def max_position_mm(self) -> float:
        return self.stroke_mm - self.soft_limit_mm


class SMCDriver:
    """
    Driver for SMC LECP6P electric actuator via Modbus RTU.

    Based on working implementation from commit b94c28d.
    """

    # Coil addresses
    COIL_SVON = 0x19              # Servo ON
    COIL_RESET = 0x1B             # Reset alarm
    COIL_SETUP = 0x1C             # Homing/setup
    COIL_INPUT_INVALID = 0x30    # Serial mode enable

    # Discrete input addresses
    INPUT_BUSY = 0x48             # Moving
    INPUT_SVRE = 0x49             # Servo ready
    INPUT_SETON = 0x4A            # Homing complete
    INPUT_ALARM = 0x4F            # Alarm active

    # Holding register addresses
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

    # Position unit conversion
    POSITION_SCALE = 100  # 0.01mm per unit

    def __init__(self, config: Optional[dict] = None):
        """Initialize the SMC driver."""
        if ModbusSerialClient is None:
            raise ImportError("pymodbus is required. Install with: pip install pymodbus")

        if config:
            self.config = SMCConfig(**config)
        else:
            self.config = SMCConfig()

        self.client: Optional[ModbusSerialClient] = None
        self._connected = False
        self._initialized = False
        self._last_command_time = 0.0
        self._command_interval = 1.0 / self.config.command_rate_hz
        self._commands_sent = 0
        self._last_position = self.config.center_mm

    def connect(self) -> bool:
        """Establish Modbus connection to the SMC controller."""
        try:
            self.client = ModbusSerialClient(
                port=self.config.port,
                baudrate=self.config.baudrate,
                parity=self.config.parity,
                stopbits=1,
                bytesize=8,
                timeout=1.0
            )

            if not self.client.connect():
                logger.error(f"Failed to connect to {self.config.port}")
                return False

            self._connected = True
            logger.info(f"Connected to SMC controller on {self.config.port}")

            # Quick connectivity test
            try:
                pos = self._read_position_mm()
                logger.info(f"Current position: {pos:.1f}mm")
            except Exception as e:
                logger.warning(f"Position read failed: {e}")

            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def initialize(self, home_first: bool = True) -> bool:
        """
        Full initialization sequence.

        CRITICAL: Must clear SETUP coil after homing completes!
        """
        if not self._connected:
            logger.error("Not connected")
            return False

        try:
            logger.info("Starting initialization sequence...")

            # Enable serial mode
            logger.info("Enabling serial mode...")
            self._write_coil(self.COIL_INPUT_INVALID, True)
            time.sleep(0.1)

            # Reset any alarms
            logger.info("Resetting alarms...")
            self._write_coil(self.COIL_RESET, True)
            time.sleep(0.1)
            self._write_coil(self.COIL_RESET, False)
            time.sleep(0.1)

            # Servo ON
            logger.info("Turning servo ON...")
            self._write_coil(self.COIL_SVON, True)
            time.sleep(0.5)

            # Wait for servo ready
            logger.info("Waiting for servo ready...")
            if not self._wait_for_input(self.INPUT_SVRE, True, timeout=5.0):
                logger.error("Servo did not become ready (SVRE timeout)")
                return False
            logger.info("Servo ready")

            # Homing
            if home_first:
                logger.info("Performing homing sequence...")
                self._write_coil(self.COIL_SETUP, True)

                # Wait for SETON (homing complete)
                for _ in range(100):  # 10 second timeout
                    if self._read_input(self.INPUT_SETON):
                        logger.info("Homing complete (SETON high)")
                        break
                    time.sleep(0.1)
                else:
                    logger.error("Homing did not complete (SETON timeout)")
                    return False

                # CRITICAL: Clear SETUP coil IMMEDIATELY after SETON goes high!
                # Leaving SETUP high causes alarm state
                self._write_coil(self.COIL_SETUP, False)
                time.sleep(0.3)

                # Reset any alarm that may have triggered during homing
                logger.info("Resetting any homing alarm...")
                self._write_coil(self.COIL_RESET, True)
                time.sleep(0.1)
                self._write_coil(self.COIL_RESET, False)
                time.sleep(0.2)

                # Check alarm status
                if self._read_input(self.INPUT_ALARM):
                    logger.info("No alarm active (ALARM input high = OK)")
                else:
                    logger.warning("ALARM input low - alarm may be active!")
                    # Try another reset
                    self._write_coil(self.COIL_RESET, True)
                    time.sleep(0.1)
                    self._write_coil(self.COIL_RESET, False)
                    time.sleep(0.2)

                pos = self._read_position_mm()
                logger.info(f"Position after homing: {pos:.1f}mm")

            # Set up motion parameters ONCE (speed, accel, etc.)
            # This is critical for low-latency operation!
            self._setup_motion_parameters()

            # Move to center (use full command for init)
            logger.info(f"Moving to center position ({self.config.center_mm}mm)...")
            self._move_to_position_mm_full(self.config.center_mm)
            time.sleep(0.1)
            self._wait_complete(timeout=5.0)

            pos = self._read_position_mm()
            logger.info(f"Position after center move: {pos:.1f}mm")

            # Retry if not at center
            if abs(pos - self.config.center_mm) > 10:
                logger.info("Retrying center move...")
                self._move_to_position_mm_full(self.config.center_mm)
                time.sleep(0.1)
                self._wait_complete(timeout=5.0)
                pos = self._read_position_mm()
                logger.info(f"Position after retry: {pos:.1f}mm")

            self._initialized = True
            self._last_position = pos
            logger.info(f"Initialization complete. Ready at {pos:.1f}mm")
            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def send_position(self, position_mm: float) -> bool:
        """Send a position command to the actuator (rate-limited)."""
        if not self._connected:
            return False

        # Rate limiting
        now = time.perf_counter()
        elapsed = now - self._last_command_time
        if elapsed < self._command_interval:
            return True  # Skip (rate limited)

        # Clamp position
        position_mm = max(
            self.config.min_position_mm,
            min(self.config.max_position_mm, position_mm)
        )

        # Only send if position changed significantly
        if abs(position_mm - self._last_position) < 0.5:
            return True

        try:
            self._move_to_position_mm(position_mm)

            self._last_command_time = now
            self._last_position = position_mm
            self._commands_sent += 1

            logger.info(f"[CMD {self._commands_sent}] Sent position: {position_mm:.1f}mm")
            return True

        except Exception as e:
            logger.warning(f"Position command failed: {e}")
            return False

    def _setup_motion_parameters(self):
        """
        Set motion parameters ONCE during initialization.
        These don't change between moves, so no need to write them every time.
        """
        logger.info("Setting up motion parameters (one-time)...")
        self._write_registers(self.REG_MOVEMENT_MODE, [1])  # Absolute positioning
        self._write_registers(self.REG_SPEED, [self.config.default_speed])
        self._write_registers(self.REG_ACCELERATION, [self.config.default_accel])
        self._write_registers(self.REG_DECELERATION, [self.config.default_decel])
        self._write_registers(self.REG_PUSHING_FORCE, [0])
        self._write_registers(self.REG_TRIGGER_LEVEL, [0])
        self._write_registers(self.REG_PUSHING_SPEED, [20])
        self._write_registers(self.REG_MOVING_FORCE, [100])
        self._write_int32(self.REG_AREA_1, 0)
        self._write_int32(self.REG_AREA_2, 0)
        self._write_int32(self.REG_IN_POSITION, 100)
        logger.info("Motion parameters set.")

    def _move_to_position_mm(self, position_mm: float) -> bool:
        """
        FAST position command - only writes position + start.

        The other parameters (speed, accel, etc.) are set once in _setup_motion_parameters().
        This reduces latency from ~200ms to ~20ms per command!
        """
        try:
            position_units = int(position_mm * self.POSITION_SCALE)

            # FAST: Only write position and start trigger
            # (other params set during init)
            self._write_int32(self.REG_POSITION, position_units)
            self._write_registers(self.REG_OPERATION_START, [0x0100])
            return True

        except Exception as e:
            logger.error(f"Move error: {e}")
            return False

    def _move_to_position_mm_full(self, position_mm: float) -> bool:
        """
        Full move command with all registers - use for initialization moves only.
        """
        try:
            position_units = int(position_mm * self.POSITION_SCALE)

            # Set all step data registers
            self._write_registers(self.REG_MOVEMENT_MODE, [1])  # Absolute
            self._write_registers(self.REG_SPEED, [self.config.default_speed])
            self._write_int32(self.REG_POSITION, position_units)
            self._write_registers(self.REG_ACCELERATION, [self.config.default_accel])
            self._write_registers(self.REG_DECELERATION, [self.config.default_decel])
            self._write_registers(self.REG_PUSHING_FORCE, [0])
            self._write_registers(self.REG_TRIGGER_LEVEL, [0])
            self._write_registers(self.REG_PUSHING_SPEED, [20])
            self._write_registers(self.REG_MOVING_FORCE, [100])
            self._write_int32(self.REG_AREA_1, 0)
            self._write_int32(self.REG_AREA_2, 0)
            self._write_int32(self.REG_IN_POSITION, 100)

            # Start movement
            self._write_registers(self.REG_OPERATION_START, [0x0100])
            return True

        except Exception as e:
            logger.error(f"Move error: {e}")
            return False

    def _read_position_mm(self) -> float:
        """Read current actuator position in mm."""
        result = self.client.read_holding_registers(
            self.REG_CURRENT_POSITION, count=2, device_id=self.config.controller_id
        )
        if hasattr(result, 'registers') and len(result.registers) >= 2:
            high, low = result.registers
            packed = struct.pack('>HH', high, low)
            units = struct.unpack('>i', packed)[0]
            return units / self.POSITION_SCALE
        return 0.0

    def read_position(self) -> float:
        """Public method to read position."""
        return self._read_position_mm()

    def shutdown(self) -> bool:
        """Graceful shutdown: return to center and turn off servo."""
        if not self._connected:
            return True

        try:
            logger.info("Shutting down...")

            logger.info(f"Returning to center ({self.config.center_mm}mm)...")
            self._move_to_position_mm(self.config.center_mm)
            self._wait_complete(timeout=5.0)

            logger.info("Turning servo OFF...")
            self._write_coil(self.COIL_SVON, False)
            time.sleep(0.5)

            self._initialized = False
            logger.info("Shutdown complete")
            return True

        except Exception as e:
            logger.error(f"Shutdown error: {e}")
            return False

    def close(self):
        """Close the Modbus connection."""
        if self.client:
            try:
                if self._initialized:
                    self.shutdown()
                self.client.close()
                logger.info(f"Connection closed. Commands sent: {self._commands_sent}")
            except Exception as e:
                logger.warning(f"Error during close: {e}")
            finally:
                self.client = None
                self._connected = False

    # ========== Low-level Modbus Operations ==========

    def _write_coil(self, address: int, value: bool):
        """Write single coil."""
        self.client.write_coil(address, value, device_id=self.config.controller_id)

    def _read_input(self, address: int) -> bool:
        """Read discrete input."""
        result = self.client.read_discrete_inputs(address, count=1, device_id=self.config.controller_id)
        if hasattr(result, 'bits'):
            return result.bits[0]
        return False

    def _write_registers(self, address: int, values: list):
        """Write multiple holding registers."""
        self.client.write_registers(address, values, device_id=self.config.controller_id)

    def _write_int32(self, address: int, value: int):
        """Write 32-bit signed integer to two registers."""
        packed = struct.pack('>i', value)
        high, low = struct.unpack('>HH', packed)
        self.client.write_registers(address, [high, low], device_id=self.config.controller_id)

    def _wait_for_input(self, address: int, expected: bool, timeout: float = 10.0) -> bool:
        """Wait for discrete input to reach expected state."""
        start = time.time()
        while time.time() - start < timeout:
            if self._read_input(address) == expected:
                return True
            time.sleep(0.1)
        return False

    def _wait_complete(self, timeout: float = 10.0) -> bool:
        """Wait for movement to complete (BUSY goes low)."""
        start = time.time()
        while time.time() - start < timeout:
            if not self._read_input(self.INPUT_BUSY):
                return True
            time.sleep(0.05)
        logger.warning("Movement timeout")
        return False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def stats(self) -> dict:
        return {
            "connected": self._connected,
            "initialized": self._initialized,
            "commands_sent": self._commands_sent,
            "last_position": self._last_position
        }


# For standalone testing
if __name__ == "__main__":
    import sys
    import platform

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("SMC Driver Test")
    print("=" * 50)

    if platform.system() == 'Windows':
        port = 'COM5'
    else:
        port = '/dev/ttyUSB0'

    driver = SMCDriver(config={'port': port})

    try:
        if not driver.connect():
            print("Connection failed!")
            sys.exit(1)

        print("\nInitializing (homing + center)...")
        if not driver.initialize(home_first=True):
            print("Initialization failed!")
            sys.exit(1)

        print("\nTesting position commands...")
        positions = [400, 500, 450, 300, 450]

        for target in positions:
            print(f"  Moving to {target}mm...")
            driver._move_to_position_mm(target)
            driver._wait_complete(timeout=3.0)
            time.sleep(0.5)
            current = driver.read_position()
            print(f"  Current position: {current:.1f}mm")

        print("\nShutting down...")
        driver.shutdown()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.close()
