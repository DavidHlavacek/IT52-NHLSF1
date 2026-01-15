"""
F1 Motion Simulator - Main Entry Point (INF-110)

Pipeline: UDP Telemetry -> Parser -> Motion Algorithm -> Hardware Driver

Usage:
    python -m src.main --hardware smc
    python -m src.main --hardware moog
"""

import argparse
import logging
import time
from typing import Optional

from src.telemetry.udp_listener import UDPListener
from src.telemetry.packet_parser import PacketParser
from src.motion.algorithm import MotionAlgorithm
from src.drivers.smc_driver import SMCDriver
from src.drivers.moog_driver import MOOGDriver
from src.utils.config import load_config
from src.utils.safety import SafetyModule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class F1MotionSimulator:
    """Orchestrates the motion simulator pipeline."""

    def __init__(self, hardware_type: str = "smc"):
        self.config = load_config()
        self.hardware_type = hardware_type

        self.udp_listener: Optional[UDPListener] = None
        self.packet_parser: Optional[PacketParser] = None
        self.motion_algorithm: Optional[MotionAlgorithm] = None
        self.safety: Optional[SafetyModule] = None
        self.driver = None

        self._latency_samples: list = []
        self._max_latency_samples = 100
        self._current_position = None  # Track current position for speed limiting
        self._last_update_time = None  # Track time of last position update
        
    def setup(self):
        """Initialize all components."""
        logger.info("Setting up F1 Motion Simulator...")

        self.udp_listener = UDPListener(port=self.config["telemetry"]["port"])
        self.packet_parser = PacketParser()
        self.motion_algorithm = MotionAlgorithm(config=self.config["motion"])
        self.safety = SafetyModule()

        if self.hardware_type == "smc":
            self.driver = SMCDriver(config=self.config["hardware"]["smc"])
            self._current_position = 450.0  # SMC center position
            self._last_update_time = time.perf_counter()
        elif self.hardware_type == "moog":
            self.driver = MOOGDriver(config=self.config["hardware"]["moog"])
            self._current_position = None  # MOOG doesn't need speed limiting
            self._last_update_time = None
        else:
            raise ValueError(f"Unknown hardware type: {self.hardware_type}")

        logger.info(f"Setup complete. Using {self.hardware_type.upper()} hardware with safety limits.")
        
    def run(self):
        """Main loop: receive telemetry, process, send to hardware."""
        logger.info("Starting main loop...")

        try:
            while True:
                start_time = time.perf_counter()

                # Check emergency stop
                if self.safety.is_estopped():
                    logger.warning("E-stop active, skipping commands")
                    time.sleep(0.1)
                    continue

                # Step 1: Receive UDP packet
                raw_packet = self.udp_listener.receive()
                if raw_packet is None:
                    continue

                # Step 2: Parse the packet
                telemetry_data = self.packet_parser.parse_motion_packet(raw_packet)
                if telemetry_data is None:
                    continue

                # Step 3: Calculate actuator positions
                positions = self.motion_algorithm.calculate(telemetry_data)

                # Step 4: Apply safety limits
                if self.hardware_type == "smc":
                    # Clamp SMC position
                    safe_position = self.safety.clamp_smc_position(positions)
                    # Apply speed limiting
                    current_time = time.perf_counter()
                    dt = current_time - self._last_update_time
                    safe_position = self.safety.limit_speed(self._current_position, safe_position, dt)
                    self._current_position = safe_position
                    self._last_update_time = current_time
                    positions = safe_position
                elif self.hardware_type == "moog":
                    # Clamp MOOG 6-DOF position
                    positions = self.safety.clamp_moog_position(positions)

                # Step 5: Send to hardware
                self.driver.send_position(positions)

                latency_ms = (time.perf_counter() - start_time) * 1000
                self._record_latency(latency_ms)

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self._log_latency_stats()
            self._log_safety_stats()
            self.cleanup()
    
    def _record_latency(self, latency_ms: float):
        """Record latency sample for monitoring."""
        self._latency_samples.append(latency_ms)
        if len(self._latency_samples) > self._max_latency_samples:
            self._latency_samples.pop(0)
        if latency_ms > 20:
            logger.warning(f"High latency: {latency_ms:.1f}ms")
    
    def _log_latency_stats(self):
        """Log latency statistics on shutdown."""
        if not self._latency_samples:
            return
        avg = sum(self._latency_samples) / len(self._latency_samples)
        max_lat = max(self._latency_samples)
        over_threshold = sum(1 for s in self._latency_samples if s > 20)
        pct = (over_threshold / len(self._latency_samples)) * 100
        logger.info(f"Latency stats: avg={avg:.1f}ms, max={max_lat:.1f}ms, >{20}ms: {pct:.1f}%")

    def _log_safety_stats(self):
        """Log safety statistics on shutdown."""
        if self.safety:
            logger.info(f"Safety stats: warning_count={self.safety.warning_count}, state={self.safety.state.value}")
            
    def cleanup(self):
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