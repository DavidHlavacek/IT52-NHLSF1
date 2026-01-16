"""
F1 Motion Simulator v2.0 - Optimized for single-axis motion

Pipeline: F1 Game -> UDP -> Parser -> Algorithm -> Driver -> Actuator
"""

import time
import signal
from src.telemetry.udp_listener_v2 import UDPListenerV2
from src.telemetry.packet_parser import PacketParser
from src.motion.algorithm_v2 import MotionAlgorithmV2
from src.drivers.smc_driver_v2 import SMCDriverV2


class Simulator:
    def __init__(self):
        self.running = True
        self.listener = UDPListenerV2()
        self.parser = PacketParser()
        self.algorithm = MotionAlgorithmV2()
        self.driver = SMCDriverV2()

        self.packets = 0
        self.total_latency = 0.0
        self.max_latency = 0.0

        # ctrl+c
        signal.signal(signal.SIGINT, self.stop)

    def run(self):
        print("F1 Motion Simulator v2.0")
        print("=========================")

        if not self.driver.connect():
            print("Failed to connect to SMC")
            return

        print("Waiting for F1 telemetry...")
        print("Press Ctrl+C to stop\n")

        while self.running:
            data = self.listener.receive()
            if not data:
                continue

            telemetry = self.parser.parse_motion_packet(data)
            if not telemetry:
                continue

            # latency
            start = time.perf_counter()
            position = self.algorithm.calculate(telemetry)
            self.driver.send_position(position)
            latency = (time.perf_counter() - start) * 1000  # ms

            # packets
            self.packets += 1
            self.total_latency += latency
            self.max_latency = max(self.max_latency, latency)

            # stats
            if self.packets % 600 == 0:
                avg = self.total_latency / self.packets
                print(f"Packets: {self.packets}, Latency: {avg:.2f}ms avg, {self.max_latency:.2f}ms max")

        self.shutdown()

    def shutdown(self):
        self.listener.close()
        self.driver.close()

        if self.packets > 0:
            avg = self.total_latency / self.packets
            print(f"\nFinal stats: {self.packets} packets, {avg:.2f}ms avg latency")

        print("Done.")

    def stop(self, *args):
        print("\nShutting down...")
        self.running = False


def main():
    sim = Simulator()
    sim.run()


if __name__ == "__main__":
    main()
