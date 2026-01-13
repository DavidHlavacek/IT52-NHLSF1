# src/motion/filters.py
"""
Filters used by the motion algorithm.

This module was extracted from algorithm.py to keep the algorithm code clean.
No behavior should change compared to the original implementation.
"""

import math


class HighPassFilter:
    """
    Second-order Butterworth high-pass filter.

    Used for onset cues in the washout algorithm.
    """

    def __init__(self, cutoff_hz: float, sample_rate: float):
        omega = 2.0 * math.pi * cutoff_hz / sample_rate
        alpha = math.sin(omega) / (2.0 * 0.707)  # Butterworth Q = 0.707
        cos_omega = math.cos(omega)

        a0 = 1.0 + alpha
        self.b0 = ((1.0 + cos_omega) / 2.0) / a0
        self.b1 = (-(1.0 + cos_omega)) / a0
        self.b2 = ((1.0 + cos_omega) / 2.0) / a0
        self.a1 = (-2.0 * cos_omega) / a0
        self.a2 = (1.0 - alpha) / a0

        self.x1 = self.x2 = 0.0
        self.y1 = self.y2 = 0.0

    def process(self, x: float) -> float:
        y = (self.b0 * x + self.b1 * self.x1 + self.b2 * self.x2
             - self.a1 * self.y1 - self.a2 * self.y2)
        self.x2, self.x1 = self.x1, x
        self.y2, self.y1 = self.y1, y
        return y

    def reset(self):
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0


class LowPassFilter:
    """
    First-order low-pass filter.

    Used for the sustained component of washout.
    """

    def __init__(self, cutoff_hz: float, sample_rate: float):
        rc = 1.0 / (2.0 * math.pi * cutoff_hz)
        dt = 1.0 / sample_rate
        self.alpha = dt / (rc + dt)
        self.y = 0.0

    def process(self, x: float) -> float:
        self.y += self.alpha * (x - self.y)
        return self.y

    def reset(self):
        self.y = 0.0


class SlewRateLimiter:
    """
    Slew rate limiter.

    Limits the change per update step to avoid impossible jumps.
    """

    def __init__(self, max_delta: float):
        self.max_delta = max_delta

    def limit(self, prev: float, target: float) -> float:
        delta = target - prev
        if abs(delta) > self.max_delta:
            delta = math.copysign(self.max_delta, delta)
        return prev + delta
