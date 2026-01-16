"""
F1 Motion Simulator - Main Entry Point

Complete pipeline orchestration for single-axis motion simulation.

Pipeline:
    F1 2024 (Xbox) → UDP Listener → Packet Parser → Motion Algorithm → SMC Driver → Actuator

Startup Sequence:
    1. Load configuration
    2. Connect to SMC controller
    3. Perform homing sequence
    4. Move actuator to center position
    5. Wait for stabilization
    6. Begin accepting game telemetry
    7. Indicate ready state

Features:
    - Dimension selection via CLI or config (surge/sway/heave/pitch/roll)
    - Rate-limited actuator commands (30Hz)
    - Latency tracking (<1ms processing target)
    - Graceful shutdown with return to center
    - Comprehensive logging and statistics

Usage:
    # Default (surge mode)
    python -m src.main

    # With dimension selection
    python -m src.main --dimension surge
    python -m src.main --dimension sway
    python -m src.main --dimension heave

    # Dry run (no hardware)
    python -m src.main --dry-run
"""

import argparse
import logging
import signal
import sys
import time
from typing import Optional
from dataclasses import dataclass

from src.telemetry.udp_listener import UDPListener
from src.telemetry.packet_parser import PacketParser
from src.motion.algorithm import (
    MotionAlgorithm,
    MotionConfig,
    MotionDimension,
    create_motion_config_from_dict
)
from src.drivers.smc_driver import SMCDriver
from src.utils.config import load_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Statistics for the motion pipeline."""
    packets_received: int = 0
    motion_packets_processed: int = 0
    commands_sent: int = 0
    total_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    start_time: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.motion_packets_processed == 0:
            return 0.0
        return self.total_latency_ms / self.motion_packets_processed

    @property
    def runtime_seconds(self) -> float:
        if self.start_time == 0:
            return 0.0
        return time.time() - self.start_time

    def update_latency(self, latency_ms: float):
        """Update latency statistics."""
        self.total_latency_ms += latency_ms
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)
        self.min_latency_ms = min(self.min_latency_ms, latency_ms)


class F1MotionSimulator:
    """
    Main application class that orchestrates all components.

    Flow:
        F1 Game → UDP Listener → Packet Parser → Motion Algorithm → SMC Driver

    The pipeline runs at the rate telemetry is received (up to 60Hz) but
    commands to the actuator are rate-limited (30Hz) to prevent oscillation.
    """

    def __init__(
        self,
        dimension: str = "surge",
        dry_run: bool = False,
        config_path: Optional[str] = None
    ):
        """
        Initialize the motion simulator.

        Args:
            dimension: Motion dimension (surge/sway/heave/pitch/roll)
            dry_run: If True, don't connect to hardware (simulation mode)
            config_path: Optional path to config file
        """
        self.dimension = dimension
        self.dry_run = dry_run

        # Load configuration
        self.config = load_config(config_path)

        # Override dimension from CLI argument
        if 'motion' not in self.config:
            self.config['motion'] = {}
        self.config['motion']['dimension'] = dimension

        # Initialize components (created in setup())
        self.udp_listener: Optional[UDPListener] = None
        self.packet_parser: Optional[PacketParser] = None
        self.motion_algorithm: Optional[MotionAlgorithm] = None
        self.driver: Optional[SMCDriver] = None

        # State
        self._running = False
        self._ready = False
        self._stats = PipelineStats()

        # Signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._running = False

    def setup(self) -> bool:
        """
        Initialize all components.

        Returns:
            True if setup successful
        """
        logger.info("=" * 60)
        logger.info("F1 Motion Simulator - Setup")
        logger.info("=" * 60)

        try:
            # 1. Initialize telemetry components
            logger.info("Setting up telemetry receiver...")
            telemetry_config = self.config.get('telemetry', {})
            self.udp_listener = UDPListener(
                port=telemetry_config.get('port', 20777),
                timeout=0.05  # 50ms timeout for responsive shutdown
            )
            self.packet_parser = PacketParser()
            logger.info(f"  UDP listener on port {telemetry_config.get('port', 20777)}")

            # 2. Initialize motion algorithm (DIRECT PROPORTIONAL - not washout!)
            logger.info("Setting up motion algorithm (DIRECT PROPORTIONAL)...")
            motion_config = create_motion_config_from_dict(self.config.get('motion', {}))
            self.motion_algorithm = MotionAlgorithm(motion_config)
            logger.info(f"  Dimension: {motion_config.dimension.value}")
            logger.info(f"  Gain: {motion_config.gain} mm/G")
            logger.info(f"  Smoothing: {motion_config.smoothing}")
            logger.info(f"  Center: {motion_config.center_mm}mm")
            logger.info(f"  Formula: position = {motion_config.center_mm} + (G * {motion_config.gain})")

            # 3. Initialize hardware driver (unless dry run)
            if not self.dry_run:
                logger.info("Setting up SMC driver...")
                smc_config = self.config.get('hardware', {}).get('smc', {})
                self.driver = SMCDriver(config=smc_config)

                if not self.driver.connect():
                    logger.error("Failed to connect to SMC controller")
                    return False

                logger.info("Initializing actuator (homing + center)...")
                if not self.driver.initialize(home_first=True):
                    logger.error("Failed to initialize actuator")
                    return False

                logger.info("Actuator ready at center position")
            else:
                logger.info("DRY RUN MODE - No hardware connection")

            self._ready = True
            logger.info("=" * 60)
            logger.info("Setup complete. Ready to receive telemetry.")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"Setup failed: {e}")
            return False

    def run(self):
        """
        Main loop: receive telemetry → process → send to hardware.

        Processing target: <1ms latency
        """
        if not self._ready:
            logger.error("Setup not complete. Call setup() first.")
            return

        logger.info("\nStarting main loop...")
        logger.info("Waiting for F1 telemetry on port 20777...")
        logger.info("Press Ctrl+C to stop\n")

        self._running = True
        self._stats.start_time = time.time()

        try:
            while self._running:
                # Start latency measurement
                loop_start = time.perf_counter()

                # Step 1: Receive UDP packet
                raw_packet = self.udp_listener.receive()

                if raw_packet is None:
                    continue

                self._stats.packets_received += 1

                # Step 2: Parse the packet
                telemetry = self.packet_parser.parse_motion_packet(raw_packet)

                if telemetry is None:
                    continue  # Not a motion packet or invalid

                # Step 3: Calculate actuator position
                target_position = self.motion_algorithm.calculate(telemetry)

                # Log first few telemetry values to verify data flow
                if self._stats.motion_packets_processed < 5:
                    logger.info(
                        f"[{self._stats.motion_packets_processed+1}] "
                        f"g_long={telemetry.g_force_longitudinal:+.2f}, "
                        f"g_lat={telemetry.g_force_lateral:+.2f} -> "
                        f"target={target_position:.1f}mm"
                    )

                # Step 4: Send to hardware (or log in dry run)
                if not self.dry_run and self.driver:
                    self.driver.send_position(target_position)
                    self._stats.commands_sent += 1

                # End latency measurement
                loop_end = time.perf_counter()
                latency_ms = (loop_end - loop_start) * 1_000

                self._stats.motion_packets_processed += 1
                self._stats.update_latency(latency_ms)

                # Periodic logging (every ~10 seconds at 60Hz)
                if self._stats.motion_packets_processed % 600 == 0:
                    self._log_stats()

        except Exception as e:
            logger.error(f"Error in main loop: {e}")

        finally:
            self._log_final_stats()
            self.cleanup()

    def _log_stats(self):
        """Log periodic statistics."""
        stats = self._stats
        logger.info(
            f"Stats: {stats.motion_packets_processed} packets, "
            f"latency avg={stats.avg_latency_ms:.3f}ms "
            f"max={stats.max_latency_ms:.3f}ms, "
            f"pos={self.motion_algorithm.current_position:.1f}mm"
        )

    def _log_final_stats(self):
        """Log final statistics on shutdown."""
        stats = self._stats
        logger.info("\n" + "=" * 60)
        logger.info("Final Statistics")
        logger.info("=" * 60)
        logger.info(f"Runtime: {stats.runtime_seconds:.1f} seconds")
        logger.info(f"Total packets received: {stats.packets_received}")
        logger.info(f"Motion packets processed: {stats.motion_packets_processed}")
        logger.info(f"Commands sent to actuator: {stats.commands_sent}")
        logger.info(f"Processing latency:")
        logger.info(f"  Average: {stats.avg_latency_ms:.3f} ms")
        logger.info(f"  Maximum: {stats.max_latency_ms:.3f} ms")
        logger.info(f"  Minimum: {stats.min_latency_ms:.3f} ms")

        # Check latency target
        if stats.avg_latency_ms < 1.0:
            logger.info(f"  ✓ Target <1ms achieved ({stats.avg_latency_ms:.3f}ms)")
        else:
            logger.warning(f"  ✗ Target <1ms NOT achieved ({stats.avg_latency_ms:.3f}ms)")

        logger.info("=" * 60)

    def cleanup(self):
        """Clean up resources and shutdown gracefully."""
        logger.info("\nCleaning up...")

        if self.udp_listener:
            self.udp_listener.close()

        if self.driver and not self.dry_run:
            logger.info("Returning actuator to center...")
            self.driver.shutdown()
            self.driver.close()

        logger.info("Cleanup complete.")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="F1 Motion Simulator - Single-Axis Motion Platform Control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Dimension Options:
  surge   - Longitudinal G-force (braking/acceleration feel)
  sway    - Lateral G-force (cornering feel)
  heave   - Vertical G-force (bump/kerb feel)
  pitch   - Pitch angle from game
  roll    - Roll angle from game

Examples:
  python -m src.main                    # Default surge mode
  python -m src.main --dimension sway   # Cornering feel
  python -m src.main --dry-run          # Test without hardware
        """
    )

    parser.add_argument(
        "--dimension", "-d",
        choices=["surge", "sway", "heave", "pitch", "roll"],
        default="surge",
        help="Motion dimension to simulate (default: surge)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without connecting to hardware (simulation mode)"
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to configuration file"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n" + "=" * 60)
    print("  F1 Motion Simulator")
    print("  Single-Axis Motion Platform Control")
    print("=" * 60)
    print(f"  Dimension: {args.dimension}")
    print(f"  Dry run:   {args.dry_run}")
    print("=" * 60 + "\n")

    # Create and run simulator
    simulator = F1MotionSimulator(
        dimension=args.dimension,
        dry_run=args.dry_run,
        config_path=args.config
    )

    if not simulator.setup():
        logger.error("Setup failed. Exiting.")
        sys.exit(1)

    simulator.run()


if __name__ == "__main__":
    main()
