"""
SMC Modbus Driver - INF-105

NOTE: This skeleton is a STARTING POINT. Feel free to completely rewrite
this file if you have a better approach. Just keep the core responsibility:
send position commands to SMC actuator via Modbus RTU.

Ticket: As a developer, I want a Python module that sends position commands 
        to the SMC controller so that I can move the actuator programmatically

Assignee: [TEAMMATE]

This module controls the SMC electric actuator via Modbus RTU over RS485.

Acceptance Criteria:
    ☐ USB-RS485 adapter connected and port identified
    ☐ Modbus connection established at 38400 bps
    ☐ Position command function implemented
    ☐ Position read-back function implemented
    ☐ Error handling for communication failures
    ☐ Actuator moves to commanded position
    ☐ Module documented with docstrings

Dependencies:
    - INF-104: SMC controller configured with LEC-W2
    - INF-117: USB-RS485 adapter procured

Hardware Setup:
    - Controller: LECP6P-LEL25LT-900
    - Actuator: LEL25LT (100mm stroke)
    - Connection: USB-RS485 adapter → CN5 port
    - Protocol: Modbus RTU
    - Baud rate: 38400
    - Controller ID: 1

Usage:
    from src.drivers.smc_driver import SMCDriver
    
    driver = SMCDriver(port='/dev/ttyUSB0')
    driver.connect()
    driver.send_position(50.0)  # Move to 50mm
    current_pos = driver.read_position()
"""

import logging
from typing import Optional
from dataclasses import dataclass

# pymodbus will be used for Modbus communication
# Install with: pip install pymodbus
try:
    from pymodbus.client import ModbusSerialClient
    PYMODBUS_AVAILABLE = True
except ImportError:
    PYMODBUS_AVAILABLE = False
    ModbusSerialClient = None

logger = logging.getLogger(__name__)


@dataclass
class SMCConfig:
    """Configuration for SMC controller connection."""
    port: str = '/dev/ttyUSB0'      # Serial port (Linux) or 'COM3' (Windows)
    baudrate: int = 38400           # Communication speed
    controller_id: int = 1          # Modbus slave ID
    stroke_mm: float = 100.0        # Actuator stroke length in mm
    min_position: float = 0.0       # Minimum position in mm
    max_position: float = 100.0     # Maximum position in mm


class SMCDriver:
    """
    Driver for SMC electric actuator via Modbus RTU.
    
    The SMC LECP6 controller accepts position commands via Modbus.
    Positions are sent in units of 0.01mm (so 50mm = 5000).
    
    Modbus Register Map (key registers):
        - 0x9900: Target position (write)
        - 0x9000: Current position (read)
        - 0x9001: Status register (read)
        
    Example:
        driver = SMCDriver(port='/dev/ttyUSB0')
        driver.connect()
        driver.send_position(50.0)  # Move to center
        driver.close()
    """
    
    # Modbus registers (from SMC documentation)
    REG_TARGET_POSITION = 0x9900
    REG_CURRENT_POSITION = 0x9000
    REG_STATUS = 0x9001
    
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
        
    def connect(self) -> bool:
        """
        Establish Modbus connection to the SMC controller.
        
        TODO [TEAMMATE]: Implement this method
        
        Returns:
            True if connection successful, False otherwise
            
        Steps:
            1. Create ModbusSerialClient with:
               - port=self.config.port
               - baudrate=self.config.baudrate
               - parity='E' (even parity)
               - stopbits=1
               - bytesize=8
               - timeout=1
            2. Call client.connect()
            3. Set self._connected = True on success
            4. Log connection status
            
        Handle exceptions:
            - Exception: Log error, return False
        """
        # TODO: Implement connection
        raise NotImplementedError("INF-105: Implement connect()")
    
    def send_position(self, position_mm: float) -> bool:
        """
        Send a position command to the actuator.
        
        TODO [TEAMMATE]: Implement this method
        
        Args:
            position_mm: Target position in millimeters (0-100)
            
        Returns:
            True if command sent successfully, False otherwise
            
        Steps:
            1. Validate position is within min/max limits
            2. Convert mm to register value: int(position_mm * POSITION_SCALE)
            3. Write to REG_TARGET_POSITION using:
               self.client.write_register(REG_TARGET_POSITION, value, slave=self.config.controller_id)
            4. Check response for errors
            5. Log the command
            
        Handle exceptions:
            - ModbusException: Log error, return False
        """
        # TODO: Implement position command
        raise NotImplementedError("INF-105: Implement send_position()")
    
    def read_position(self) -> Optional[float]:
        """
        Read the current actuator position.
        
        TODO [TEAMMATE]: Implement this method
        
        Returns:
            Current position in mm, or None if read failed
            
        Steps:
            1. Read from REG_CURRENT_POSITION using:
               self.client.read_holding_registers(REG_CURRENT_POSITION, 1, slave=self.config.controller_id)
            2. Check response for errors
            3. Convert register value to mm: value / POSITION_SCALE
            4. Return position
            
        Handle exceptions:
            - ModbusException: Log error, return None
        """
        # TODO: Implement position readback
        raise NotImplementedError("INF-105: Implement read_position()")
    
    def home(self) -> bool:
        """
        Command the actuator to return to home position.
        
        TODO [TEAMMATE]: Implement this method (optional, but useful)
        
        Returns:
            True if homing started successfully
        """
        # TODO: Implement homing (optional)
        logger.warning("home() not implemented yet")
        return False
    
    def close(self):
        """
        Close the Modbus connection.
        
        TODO [TEAMMATE]: Implement this method
        
        Steps:
            1. Check if client exists and is connected
            2. Call self.client.close()
            3. Set self._connected = False
            4. Log disconnection
        """
        # TODO: Implement cleanup
        raise NotImplementedError("INF-105: Implement close()")
    
    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._connected


# For standalone testing
if __name__ == "__main__":
    """
    Test the SMC driver standalone.
    
    Make sure:
        1. USB-RS485 adapter is connected
        2. SMC controller is powered on
        3. Correct port is specified
        
    Run: python -m src.drivers.smc_driver
    """
    import sys
    
    logging.basicConfig(level=logging.DEBUG)
    
    print("SMC Driver Test")
    print("=" * 40)
    
    if not PYMODBUS_AVAILABLE:
        print("ERROR: pymodbus not installed")
        print("Run: pip install pymodbus")
        sys.exit(1)
    
    # Default to common port names
    import platform
    if platform.system() == 'Windows':
        port = 'COM3'
    else:
        port = '/dev/ttyUSB0'
    
    print(f"Attempting connection on {port}...")
    
    driver = SMCDriver(config={'port': port})
    
    try:
        if driver.connect():
            print("Connected!")
            
            # Test position command
            print("Sending position: 50mm")
            driver.send_position(50.0)
            
            # Read back position
            pos = driver.read_position()
            print(f"Current position: {pos}mm")
        else:
            print("Connection failed")
    except NotImplementedError as e:
        print(f"Not implemented: {e}")
    finally:
        driver.close()
