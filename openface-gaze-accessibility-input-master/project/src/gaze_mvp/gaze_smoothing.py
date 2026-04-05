from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class EmaSmoother2D:
    """
    Lightweight 2D exponential moving average smoother.
    """

    alpha: float = 0.4

    def __post_init__(self) -> None:
        if self.alpha <= 0.0 or self.alpha > 1.0:
            raise ValueError("EMA alpha must be in (0, 1].")
        self._x: float | None = None
        self._y: float | None = None

    def update(self, timestamp_ms: int, x: float, y: float) -> tuple[float, float]:
        del timestamp_ms  # Kept for interface consistency.
        if self._x is None or self._y is None:
            self._x = x
            self._y = y
            return x, y

        self._x = (self.alpha * x) + ((1.0 - self.alpha) * self._x)
        self._y = (self.alpha * y) + ((1.0 - self.alpha) * self._y)
        return self._x, self._y


class _LowPass1D:
    def __init__(self) -> None:
        self._initialized = False
        self._value = 0.0

    def filter(self, value: float, alpha: float) -> float:
        if not self._initialized:
            self._initialized = True
            self._value = value
            return value
        self._value = (alpha * value) + ((1.0 - alpha) * self._value)
        return self._value


class _OneEuro1D:
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float):
        if min_cutoff <= 0.0:
            raise ValueError("min_cutoff must be > 0.")
        if d_cutoff <= 0.0:
            raise ValueError("d_cutoff must be > 0.")
        if beta < 0.0:
            raise ValueError("beta must be >= 0.")

        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff

        self._prev_t_ms: int | None = None
        self._prev_raw = 0.0
        self._x_filter = _LowPass1D()
        self._dx_filter = _LowPass1D()

    @staticmethod
    def _alpha(delta_seconds: float, cutoff_hz: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff_hz)
        return 1.0 / (1.0 + (tau / delta_seconds))

    def update(self, timestamp_ms: int, value: float) -> float:
        if self._prev_t_ms is None:
            self._prev_t_ms = timestamp_ms
            self._prev_raw = value
            return self._x_filter.filter(value, alpha=1.0)

        delta_s = max(1e-3, (timestamp_ms - self._prev_t_ms) / 1000.0)
        self._prev_t_ms = timestamp_ms

        dx = (value - self._prev_raw) / delta_s
        self._prev_raw = value

        alpha_d = self._alpha(delta_s, self.d_cutoff)
        dx_hat = self._dx_filter.filter(dx, alpha_d)

        cutoff = self.min_cutoff + (self.beta * abs(dx_hat))
        alpha_x = self._alpha(delta_s, cutoff)
        return self._x_filter.filter(value, alpha_x)


@dataclass
class OneEuroSmoother2D:
    """
    Adaptive 2D One Euro smoother suitable for gaze trajectories.
    """

    min_cutoff: float = 1.0
    beta: float = 0.01
    d_cutoff: float = 1.0

    def __post_init__(self) -> None:
        self._fx = _OneEuro1D(min_cutoff=self.min_cutoff, beta=self.beta, d_cutoff=self.d_cutoff)
        self._fy = _OneEuro1D(min_cutoff=self.min_cutoff, beta=self.beta, d_cutoff=self.d_cutoff)

    def update(self, timestamp_ms: int, x: float, y: float) -> tuple[float, float]:
        return self._fx.update(timestamp_ms, x), self._fy.update(timestamp_ms, y)
