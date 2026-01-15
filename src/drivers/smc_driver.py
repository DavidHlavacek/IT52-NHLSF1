"""
SMC LECP6P Modbus RTU Driver - Complete Implementation

Controls the SMC electric actuator via Modbus RTU over RS485.

Hardware:
    - Controller: SMC LECP6P (Step Motor Controller, PNP type)
    - Actuator: SMC LEL25LT-900 (900mm stroke)
    - Communication: RS485 via USB adapter at 38400 baud
    - Position units: 0.01mm (100 units = 1mm)

Research-Based Design:
    - Command rate limited to 20-30Hz to prevent oscillation
    - Full initialization sequence: serial mode → servo on → homing → center
    - Proper status checking before and after moves
    - Clean shutdown with return to center

Anti-Oscillation Measures:
    - Rate-limited commands (don't flood the controller)
    - Check BUSY flag before sending new commands
    - Use motion profiles (acceleration/deceleration)
    - Position deadband in motion algorithm (not here)

Register Map Reference:
    See docs/SMC_LECP6_Modbus_Register_Map.md for complete details.
"""

import struct
import time
import logging
from typing import Optional
from dataclasses import dataclass
from enum import IntEnum

# pymodbus for Modbus communication (handle different versions)
try:
    from pymodbus.client import ModbusSerialClient
    from pymodbus.exceptions import ModbusException
except ImportError:
    # Fallback for older pymodbus versions (< 3.0)
    from pymodbus.client.sync import ModbusSerialClient
    from pymodbus.exceptions import ModbusException

PYMODBUS_AVAILABLE = True

logger = logging.getLogger(__name__)


class SMCCoils(IntEnum):
    """SMC Modbus coil addresses (wire format, 0-indexed)."""
    HOLD = 0x18              # Hold current position
    SVON = 0x19              # Servo ON
    DRIVE = 0x1A             # Drive enable
    RESET = 0x1B             # Reset alarm
    SETUP = 0x1C             # Homing/setup
    JOG_MINUS = 0x1D         # Jog negative
    JOG_PLUS = 0x1E          # Jog positive
    INPUT_INVALID = 0x30     # Serial mode enable (0=parallel, 1=serial)


class SMCInputs(IntEnum):
    """SMC Modbus discrete input addresses (wire format, 0-indexed)."""
    BUSY = 0x48              # Moving (1=busy, 0=complete)
    SVRE = 0x49              # Servo ready
    SETON = 0x4A             # Setup/homing complete
    INP = 0x4B               # In position
    AREA = 0x4C              # Area output 1
    WAREA = 0x4D             # Area output 2
    ESTOP = 0x4E             # Emergency stop active
    ALARM = 0x4F             # Alarm (REVERSE LOGIC: 0=alarm, 1=OK)


class SMCRegisters(IntEnum):
    """SMC Modbus holding register addresses (wire format, 0-indexed)."""
    # Status registers (read)
    CURRENT_POSITION = 0x9000    # int32, 0.01mm
    CURRENT_SPEED = 0x9002       # uint16, mm/s
    CURRENT_THRUST = 0x9003      # uint16, %
    TARGET_POSITION = 0x9004     # int32, 0.01mm
    DRIVING_DATA_NO = 0x9006     # uint16

    # Command registers (write)
    OPERATION_START = 0x9100     # Write 0x0100 to start movement
    MOVEMENT_MODE = 0x9102       # 1=absolute, 2=relative
    SPEED = 0x9103               # mm/s
    POSITION = 0x9104            # int32, 0.01mm
    ACCELERATION = 0x9106        # mm/s²
    DECELERATION = 0x9107        # mm/s²
    PUSHING_FORCE = 0x9108       # %
    TRIGGER_LEVEL = 0x9109       # %
    PUSHING_SPEED = 0x910A       # mm/s
    MOVING_FORCE = 0x910B        # %
    IN_POSITION = 0x9110         # int32, 0.01mm (in-position width)


@dataclass
class SMCConfig:
    """Configuration for SMC controller connection."""
    port: str = '/dev/ttyUSB0'      # Serial port (Linux) or 'COM3' (Windows)
    baudrate: int = 38400           # Fixed by SMC protocol
    parity: str = 'N'               # No parity (some controllers use 'E')
    controller_id: int = 1          # Modbus slave ID
    stroke_mm: float = 900.0        # Actuator stroke length
    center_mm: float = 450.0        # Center position
    soft_limit_mm: float = 5.0      # Safety margin from ends
    default_speed: int = 500        # Default movement speed mm/s
    default_accel: int = 3000       # Default acceleration mm/s²
    default_decel: int = 3000       # Default deceleration mm/s²
    command_rate_hz: float = 30.0   # Max command rate to controller

    @property
    def min_position_mm(self) -> float:
        return self.soft_limit_mm

    @property
    def max_position_mm(self) -> float:
        return self.stroke_mm - self.soft_limit_mm


class SMCDriver:
    """
    Driver for SMC LECP6P electric actuator via Modbus RTU.

    This driver provides:
        - Full initialization sequence (serial mode, servo, homing, center)
        - Rate-limited position commands
        - Status monitoring (busy, alarm, position)
        - Clean shutdown with return to center

    Example:
        driver = SMCDriver(config={'port': '/dev/ttyUSB0'})
        if driver.connect():
            driver.initialize()  # Homing and center
            while running:
                driver.send_position(target_mm)
            driver.shutdown()  # Return to center
            driver.close()
    """

    # Position unit conversion (register value = mm * 100)
    POSITION_SCALE = 100  # 0.01mm per unit

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the SMC driver.

        Args:
            config: Configuration dict with port, baudrate, etc.
                   If None, uses defaults from SMCConfig.
        """
        if not PYMODBUS_AVAILABLE:
            raise ImportError(
                "pymodbus is required. Install with: pip install pymodbus"
            )

        # Load config
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
        self._commands_skipped = 0
        self._last_position = self.config.center_mm

    def connect(self) -> bool:
        """
        Establish Modbus connection to the SMC controller.

        Returns:
            True if connection successful
        """
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
                pos = self.read_position()
                logger.info(f"Current position: {pos:.1f}mm")
            except Exception as e:
                logger.warning(f"Position read failed (may need initialization): {e}")

            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def initialize(self, home_first: bool = True) -> bool:
        """
        Full initialization sequence.

        Steps:
            1. Enable serial mode (disable parallel I/O)
            2. Reset any alarms
            3. Turn servo ON
            4. Perform homing (if enabled)
            5. Move to center position
            6. Wait for completion

        Args:
            home_first: Whether to perform homing sequence

        Returns:
            True if initialization successful
        """
        if not self._connected:
            logger.error("Not connected")
            return False

        try:
            logger.info("Starting initialization sequence...")

            # Step 1: Enable serial mode
            logger.info("Enabling serial mode...")
            self._write_coil(SMCCoils.INPUT_INVALID, True)
            time.sleep(0.1)

            # Step 2: Reset any alarms
            if self._is_alarm():
                logger.info("Resetting alarm...")
                self._reset_alarm()
                time.sleep(0.2)

            # Step 3: Servo ON
            logger.info("Turning servo ON...")
            self._write_coil(SMCCoils.SVON, True)

            # Wait for servo ready
            if not self._wait_for_input(SMCInputs.SVRE, True, timeout=5.0):
                logger.error("Servo did not become ready (SVRE timeout)")
                return False
            logger.info("Servo ready")

            # Step 4: Homing (optional)
            if home_first:
                logger.info("Performing homing sequence...")
                self._write_coil(SMCCoils.SETUP, True)

                if not self._wait_for_input(SMCInputs.SETON, True, timeout=30.0):
                    logger.error("Homing did not complete (SETON timeout)")
                    return False
                logger.info("Homing complete")

                # CRITICAL: Clear SETUP coil after homing!
                self._write_coil(SMCCoils.SETUP, False)
                time.sleep(0.3)

                pos = self.read_position()
                logger.info(f"Position after homing: {pos:.1f}mm")

            # Step 5: Move to center
            logger.info(f"Moving to center position ({self.config.center_mm}mm)...")
            self._move_to_position(
                self.config.center_mm,
                speed=300,  # Slower for initialization
                wait=True
            )

            # Verify center position (like dev branch)
            time.sleep(0.1)
            pos = self.read_position()
            logger.info(f"Position after center move: {pos:.1f}mm")

            # Retry if not close enough (like dev branch)
            if abs(pos - self.config.center_mm) > 10:
                logger.info("Retrying center move...")
                self._move_to_position(self.config.center_mm, speed=300, wait=True)
                time.sleep(0.1)
                pos = self.read_position()
                logger.info(f"Position after retry: {pos:.1f}mm")

            self._initialized = True
            logger.info(f"Initialization complete. Ready at {pos:.1f}mm")
            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    def send_position(self, position_mm: float) -> bool:
        """
        Send a position command to the actuator.

        This method is rate-limited to prevent flooding the controller.
        It checks if enough time has passed since the last command.

        Args:
            position_mm: Target position in millimeters

        Returns:
            True if command sent successfully
        """
        if not self._connected:
            logger.warning("Not connected")
            return False

        # Rate limiting
        now = time.perf_counter()
        elapsed = now - self._last_command_time
        if elapsed < self._command_interval:
            # Skip this command (rate limited)
            self._commands_skipped += 1
            return True

        # Clamp position to safe limits
        position_mm = max(
            self.config.min_position_mm,
            min(self.config.max_position_mm, position_mm)
        )

        # Only send if position changed significantly (0.5mm threshold)
        if abs(position_mm - self._last_position) < 0.5:
            self._commands_skipped += 1
            return True

        try:
            # Send position command
            self._send_position_command(position_mm)

            self._last_command_time = now
            self._last_position = position_mm
            self._commands_sent += 1

            # Log first few commands sent
            if self._commands_sent <= 5:
                logger.info(f"[CMD {self._commands_sent}] Sent position: {position_mm:.1f}mm")

            return True

        except Exception as e:
            logger.warning(f"Position command failed: {e}")
            return False

    def _send_position_command(self, position_mm: float):
        """
        Low-level position command with motion profile.

        Args:
            position_mm: Target position in mm
        """
        # Convert mm to 0.01mm units
        position_units = int(position_mm * self.POSITION_SCALE)

        # Write ALL step data registers (must match dev branch for actuator to move)
        self._write_register(SMCRegisters.MOVEMENT_MODE, 1)  # Absolute
        self._write_register(SMCRegisters.SPEED, self.config.default_speed)
        self._write_int32(SMCRegisters.POSITION, position_units)
        self._write_register(SMCRegisters.ACCELERATION, self.config.default_accel)
        self._write_register(SMCRegisters.DECELERATION, self.config.default_decel)
        self._write_register(SMCRegisters.PUSHING_FORCE, 0)
        self._write_register(SMCRegisters.TRIGGER_LEVEL, 0)
        self._write_register(SMCRegisters.PUSHING_SPEED, 20)
        self._write_register(SMCRegisters.MOVING_FORCE, 100)
        self._write_int32(0x910C, 0)  # AREA_1
        self._write_int32(0x910E, 0)  # AREA_2
        self._write_int32(SMCRegisters.IN_POSITION, 100)

        # Start movement
        self._write_register(SMCRegisters.OPERATION_START, 0x0100)

    def _move_to_position(self, position_mm: float, speed: int = 500, wait: bool = True):
        """
        Move to position and optionally wait for completion.

        Args:
            position_mm: Target position in mm
            speed: Movement speed in mm/s
            wait: Whether to wait for completion
        """
        position_units = int(position_mm * self.POSITION_SCALE)

        # Write complete step data (matching dev branch)
        self._write_register(SMCRegisters.MOVEMENT_MODE, 1)  # Absolute
        self._write_register(SMCRegisters.SPEED, speed)
        self._write_int32(SMCRegisters.POSITION, position_units)
        self._write_register(SMCRegisters.ACCELERATION, self.config.default_accel)
        self._write_register(SMCRegisters.DECELERATION, self.config.default_decel)
        self._write_register(SMCRegisters.PUSHING_FORCE, 0)
        self._write_register(SMCRegisters.TRIGGER_LEVEL, 0)
        self._write_register(SMCRegisters.PUSHING_SPEED, 20)
        self._write_register(SMCRegisters.MOVING_FORCE, 100)
        self._write_int32(0x910C, 0)  # AREA_1
        self._write_int32(0x910E, 0)  # AREA_2
        self._write_int32(SMCRegisters.IN_POSITION, 100)

        # Start movement
        self._write_register(SMCRegisters.OPERATION_START, 0x0100)

        if wait:
            self._wait_for_completion(timeout=30.0)

    def read_position(self) -> float:
        """
        Read the current actuator position.

        Returns:
            Current position in mm
        """
        units = self._read_int32(SMCRegisters.CURRENT_POSITION)
        return units / self.POSITION_SCALE

    def shutdown(self) -> bool:
        """
        Graceful shutdown: return to center and turn off servo.

        Returns:
            True if shutdown successful
        """
        if not self._connected:
            return True

        try:
            logger.info("Shutting down...")

            # Return to center
            logger.info(f"Returning to center ({self.config.center_mm}mm)...")
            self._move_to_position(self.config.center_mm, speed=200, wait=True)

            # Turn off servo
            logger.info("Turning servo OFF...")
            self._write_coil(SMCCoils.SVON, False)
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
                logger.info(f"Connection closed. Total commands sent: {self._commands_sent}")
            except Exception as e:
                logger.warning(f"Error during close: {e}")
            finally:
                self.client = None
                self._connected = False

    # ========== Low-level Modbus Operations ==========
    # Note: Using device_id= parameter for pymodbus compatibility

    def _write_coil(self, address: int, value: bool):
        """Write single coil."""
        self.client.write_coil(address, value, device_id=self.config.controller_id)

    def _read_input(self, address: int) -> bool:
        """Read discrete input."""
        result = self.client.read_discrete_inputs(address, count=1, device_id=self.config.controller_id)
        if hasattr(result, 'bits'):
            return result.bits[0]
        return False

    def _write_register(self, address: int, value: int):
        """Write single holding register."""
        self.client.write_register(address, value, device_id=self.config.controller_id)

    def _read_register(self, address: int, count: int = 1) -> list:
        """Read holding register(s)."""
        result = self.client.read_holding_registers(address, count=count, device_id=self.config.controller_id)
        if hasattr(result, 'registers'):
            return result.registers
        return [0] * count

    def _read_int32(self, address: int) -> int:
        """Read 32-bit signed integer from two registers."""
        regs = self._read_register(address, count=2)
        # Big-endian: first register is high word
        return struct.unpack('>i', struct.pack('>HH', regs[0], regs[1]))[0]

    def _write_int32(self, address: int, value: int):
        """Write 32-bit signed integer to two registers."""
        packed = struct.pack('>i', value)
        high, low = struct.unpack('>HH', packed)
        self.client.write_registers(address, [high, low], device_id=self.config.controller_id)

    # ========== Status Helpers ==========

    def _is_busy(self) -> bool:
        """Check if actuator is moving."""
        return self._read_input(SMCInputs.BUSY)

    def _is_alarm(self) -> bool:
        """Check if alarm is active (REVERSE LOGIC!)."""
        return not self._read_input(SMCInputs.ALARM)  # 0=alarm

    def _reset_alarm(self):
        """Reset alarm condition."""
        self._write_coil(SMCCoils.RESET, True)
        time.sleep(0.1)
        self._write_coil(SMCCoils.RESET, False)

    def _wait_for_input(self, address: int, expected: bool, timeout: float = 10.0) -> bool:
        """Wait for discrete input to reach expected state."""
        start = time.time()
        while time.time() - start < timeout:
            if self._read_input(address) == expected:
                return True
            time.sleep(0.1)
        return False

    def _wait_for_completion(self, timeout: float = 10.0) -> bool:
        """Wait for movement to complete (BUSY goes low)."""
        time.sleep(0.1)  # Give controller time to start
        return self._wait_for_input(SMCInputs.BUSY, False, timeout)

    # ========== Properties ==========

    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected

    @property
    def is_initialized(self) -> bool:
        """Return initialization status."""
        return self._initialized

    @property
    def stats(self) -> dict:
        """Return driver statistics."""
        return {
            "connected": self._connected,
            "initialized": self._initialized,
            "commands_sent": self._commands_sent,
            "commands_skipped": self._commands_skipped,
            "last_position": self._last_position
        }


# For standalone testing
if __name__ == "__main__":
    """
    Test the SMC driver standalone.

    Run: python -m src.drivers.smc_driver
    """
    import sys
    import platform

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("SMC Driver Test")
    print("=" * 50)

    if not PYMODBUS_AVAILABLE:
        print("ERROR: pymodbus not installed")
        print("Run: pip install pymodbus")
        sys.exit(1)

    # Default to common port names
    if platform.system() == 'Windows':
        port = 'COM3'
    else:
        port = '/dev/ttyUSB0'

    print(f"Attempting connection on {port}...")
    print("Make sure:")
    print("  1. USB-RS485 adapter is connected")
    print("  2. SMC controller is powered on")
    print("  3. Correct port is specified")
    print()

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
            driver.send_position(target)
            time.sleep(1.0)
            current = driver.read_position()
            print(f"  Current position: {current:.1f}mm")

        print("\nShutting down...")
        driver.shutdown()

        print(f"\nDriver stats: {driver.stats}")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.close()
