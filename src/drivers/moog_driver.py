"""
MOOG Driver - INF-108
Platform: MOOG 6DOF2000E
Implemented with docs from Engineering Team.
"""

import socket
import struct
import time
from enum import IntEnum

from src.shared.types import Position6DOF


# MOOG platform states
class MoogState(IntEnum):
    IDLE = 1
    ENGAGED = 3


# MOOG Motion Command Word (MCW) values
class MoogCommand(IntEnum):
    PARK = 210
    ENGAGE = 180
    DOF_MODE = 170
    NEW_POSITION = 130


class MOOGDriver:

    def __init__(self, config: dict):
        self.ip = config.get('ip', '192.168.1.100')
        self.port = config.get('port', 991)
        self.timeout = config.get('timeout_s', 0.1)

        # safety limits
        limits = config.get('limits', {})
        self.limit_surge_pos = limits.get('surge_pos_m', 0.259)
        self.limit_surge_neg = limits.get('surge_neg_m', 0.241)
        self.limit_sway = limits.get('sway_m', 0.259)
        self.limit_heave = limits.get('heave_m', 0.178)
        self.limit_roll = limits.get('roll_rad', 0.3665)
        self.limit_pitch = limits.get('pitch_rad', 0.3840)
        self.limit_yaw = limits.get('yaw_rad', 0.3840)

        self.socket = None
        self._connected = False
        self._engaged = False

    def connect(self) -> bool:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(self.timeout)

            self._send(MoogCommand.DOF_MODE, 0, 0, 0, 0, 0, 0)
            self._connected = True
            print(f"[MOOG] Connected to {self.ip}:{self.port}")
            return True

        except Exception as e:
            print(f"[MOOG] Connection error: {e}")
            return False

    def engage(self) -> bool:
        if not self._connected:
            return False

        self._send(MoogCommand.ENGAGE, 0, 0, 0, 0, 0, 0)

        # wait ENGAGE
        for _ in range(50):
            if self._get_state() == MoogState.ENGAGED:
                self._engaged = True
                print("[MOOG] Platform engaged")
                return True
            time.sleep(0.1)

        print("[MOOG] Failed to engage platform")
        return False

    def send_position(self, position: Position6DOF) -> bool:
        if not self._connected:
            return False

        # clamp to safety limits
        surge = self._clamp(position.x, -self.limit_surge_neg, self.limit_surge_pos)
        sway = self._clamp(position.y, -self.limit_sway, self.limit_sway)
        heave = -self._clamp(position.z, -self.limit_heave, self.limit_heave)
        roll = self._clamp(position.roll, -self.limit_roll, self.limit_roll)
        pitch = self._clamp(position.pitch, -self.limit_pitch, self.limit_pitch)
        yaw = self._clamp(position.yaw, -self.limit_yaw, self.limit_yaw)

        # send position
        self._send(MoogCommand.NEW_POSITION, roll, pitch, heave, surge, yaw, sway) # it needs to be this order!
        return True

    # PARK and IDLE
    def disengage(self) -> bool:
        if not self._connected:
            return False

        self._send(MoogCommand.PARK, 0, 0, 0, 0, 0, 0)

        # wait IDLE
        for _ in range(100):
            if self._get_state() == MoogState.IDLE:
                self._engaged = False
                print("[MOOG] Platform parked")
                return True
            time.sleep(0.1)

        print("[MOOG] Park timeout")
        return False

    def close(self):
        if self._engaged:
            self.disengage()

        if self.socket:
            self.socket.close()
            self.socket = None

        self._connected = False
        self._engaged = False
        print("[MOOG] Disconnected")

    def _send(self, mcw, roll, pitch, heave, surge, yaw, lateral):
        packet = struct.pack('>I6fI', mcw, roll, pitch, heave, surge, yaw, lateral, 0) 
        self.socket.sendto(packet, (self.ip, self.port))

    def _get_state(self) -> int:
        try:
            data, _ = self.socket.recvfrom(40)
            if len(data) < 12:
                return -1
            status = struct.unpack('>3I', data[:12])[2]
            return status & 0x0F
        except:
            return -1

    def _clamp(self, value, min_val, max_val):
        return max(min_val, min(max_val, value))


# standalone test
if __name__ == '__main__':

    config = {
        'ip': '192.168.1.100',
        'port': 991,
        'limits': {
            'surge_pos_m': 0.259,
            'surge_neg_m': 0.241,
            'sway_m': 0.259,
            'heave_m': 0.178,
            'roll_rad': 0.3665,
            'pitch_rad': 0.3840,
            'yaw_rad': 0.3840,
        }
    }

    driver = MOOGDriver(config)

    print("MOOG Driver Test")
    print("================")
    print(f"Target: {config['ip']}:{config['port']}")
    print("Note: requires actual MOOG platform to be connected")
