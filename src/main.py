"""
F1 Motion Simulator - Main Entry Point

NOTE: This skeleton is a STARTING POINT. Feel free to completely rewrite
this file if you have a better approach. Just keep the core responsibility:
orchestrate the pipeline (UDP → Parse → Algorithm → Hardware).

INF-110: Integrate Telemetry with Motion Algorithm

This is the main application that ties together:
- F1 UDP Telemetry reception (INF-100)
- Packet parsing (INF-103)
- Motion algorithm (INF-107)
- Hardware drivers: SMC (INF-105) / MOOG (INF-108)

Acceptance Criteria for INF-110:
    ☐ Telemetry listener calls motion algorithm on each packet
    ☐ Motion algorithm outputs position commands
    ☐ Commands sent to hardware driver
    ☐ Full pipeline tested end-to-end
    ☐ Latency measured and acceptable (<50ms)

Usage:
    python -m src.main --hardware smc
    python -m src.main --hardware moog
"""

import argparse
import logging
import time  # Added for latency measurement
from typing import Optional

from src.telemetry.udp_listener import UDPListener
from src.telemetry.packet_parser import PacketParser
from src.motion.algorithm import MotionAlgorithm
from src.drivers.smc_driver import SMCDriver
from src.drivers.moog_driver import MOOGDriver
from src.utils.config import load_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class F1MotionSimulator:
    """
    Main application class that orchestrates all components.
    
    INF-110: This class implements the integration between
    telemetry reception and motion output.
    
    Flow:
        F1 Game → UDP Listener → Packet Parser → Motion Algorithm → Hardware Driver
    """
    
    def __init__(self, hardware_type: str = "smc"):
        """
        Initialize the motion simulator.
        
        Args:
            hardware_type: Either "smc" or "moog"
        """
        self.config = load_config()
        self.hardware_type = hardware_type
        
        # Initialize components
        self.udp_listener: Optional[UDPListener] = None
        self.packet_parser: Optional[PacketParser] = None
        self.motion_algorithm: Optional[MotionAlgorithm] = None
        self.driver = None
        
        # Latency tracking (INF-110)
        self._latency_samples: list = []
        self._max_latency_samples = 100
        
    def setup(self):
        """Initialize all components."""
        logger.info("Setting up F1 Motion Simulator...")
        
        # Telemetry components (INF-100, INF-103)
        self.udp_listener = UDPListener(
            port=self.config["telemetry"]["port"]
        )
        self.packet_parser = PacketParser()
        
        # Motion algorithm (INF-107)
        self.motion_algorithm = MotionAlgorithm(
            config=self.config["motion"]
        )
        
        # Hardware driver (INF-105 / INF-108)
        if self.hardware_type == "smc":
            self.driver = SMCDriver(
                config=self.config["hardware"]["smc"]
            )
        elif self.hardware_type == "moog":
            self.driver = MOOGDriver(
                config=self.config["hardware"]["moog"]
            )
        else:
            raise ValueError(f"Unknown hardware type: {self.hardware_type}")
        
        logger.info(f"Setup complete. Using {self.hardware_type.upper()} hardware.")
        
    def run(self):
        """
        Main loop: receive telemetry → process → send to hardware.
        
        INF-110: This is the core integration point.
        
        TODO [INF-110]: 
            - Measure and log latency
            - Verify latency < 50ms
            - Add performance monitoring
        """
        logger.info("Starting main loop...")
        
        try:
            while True:
                # Start latency measurement (INF-110)
                start_time = time.perf_counter()
                
                # Step 1: Receive UDP packet (INF-100)
                raw_packet = self.udp_listener.receive()
                
                if raw_packet is None:
                    continue
                
                # Step 2: Parse the packet (INF-103)
                telemetry_data = self.packet_parser.parse_motion_packet(raw_packet)
                
                if telemetry_data is None:
                    continue
                
                # Step 3: Calculate actuator positions (INF-107)
                positions = self.motion_algorithm.calculate(telemetry_data)
                
                # Step 4: Send to hardware (INF-105 / INF-108)
                self.driver.send_position(positions)
                
                # End latency measurement (INF-110)
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000
                self._record_latency(latency_ms)
                
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self._log_latency_stats()
            self.cleanup()
    
    def _record_latency(self, latency_ms: float):
        """
        Record latency sample for monitoring (INF-110).
        
        TODO [INF-110]: Implement this method
        
        Args:
            latency_ms: Processing latency in milliseconds
            
        Steps:
            1. Append to _latency_samples
            2. Keep only last _max_latency_samples
            3. Log warning if latency > 50ms
        """
        # TODO: Implement latency recording
        pass
    
    def _log_latency_stats(self):
        """
        Log latency statistics on shutdown (INF-110).
        
        TODO [INF-110]: Implement this method
        
        Should log:
            - Average latency
            - Max latency
            - % of samples > 50ms
        """
        # TODO: Implement latency stats logging
        pass
            
    def cleanup(self):
        """Clean up resources."""
        if self.udp_listener:
            self.udp_listener.close()
        if self.driver:
            self.driver.close()
        logger.info("Cleanup complete.")


def main():
    parser = argparse.ArgumentParser(description="F1 Motion Simulator")
    parser.add_argument(
        "--hardware", 
        choices=["smc", "moog"],
        default="smc",
        help="Hardware type to use (default: smc)"
    )
    args = parser.parse_args()
    
    simulator = F1MotionSimulator(hardware_type=args.hardware)
    simulator.setup()
    simulator.run()


if __name__ == "__main__":
    main()