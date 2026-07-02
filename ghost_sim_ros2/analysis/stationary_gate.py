"""Windowed stationary-target gate for GHOST V1.

The gate is intentionally independent of ROS so it can be validated with
synthetic trajectories before being integrated into ``mh_tracker.py``.

It estimates apparent target speed using a least-squares line fit over a rolling
position window and applies enter/exit hysteresis. This is designed for the V1
AprilTag tracker where stationary pose logs showed colored low-frequency drift;
the gate does not assume white Gaussian measurement noise.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class StationaryGateConfig:
    """Configuration for the windowed stationary gate.

    Thresholds are deliberately supplied by configuration because final values
    must be derived from controlled hardware noise characterization, not baked
    into the estimator.
    """

    window_s: float = 1.5
    enter_speed_mps: float = 0.08
    exit_speed_mps: float = 0.14
    min_samples: int = 5
    min_span_fraction: float = 0.50
    history_duration_s: float | None = None

    def validate(self) -> None:
        if self.window_s <= 0.0:
            raise ValueError("window_s must be positive")
        if self.enter_speed_mps < 0.0:
            raise ValueError("enter_speed_mps must be non-negative")
        if self.exit_speed_mps <= self.enter_speed_mps:
            raise ValueError("exit_speed_mps must be greater than enter_speed_mps")
        if self.min_samples < 2:
            raise ValueError("min_samples must be at least 2")
        if not (0.0 < self.min_span_fraction <= 1.0):
            raise ValueError("min_span_fraction must be in (0, 1]")
        if self.history_duration_s is not None and self.history_duration_s < self.window_s:
            raise ValueError("history_duration_s must be >= window_s when provided")


@dataclass(frozen=True)
class StationaryGateState:
    """Current stationary-gate output."""

    active: bool
    speed_mps: float
    vx_mps: float
    vy_mps: float
    sample_count: int
    span_s: float
    reason: str

    @property
    def initialized(self) -> bool:
        return math.isfinite(self.speed_mps)

    @property
    def suppress_dynamic_hypotheses(self) -> bool:
        """True when dynamic hidden-motion hypotheses should be suppressed."""
        return self.active


class WindowedVelocityGate:
    """Hysteretic stationary detector using rolling least-squares velocity."""

    def __init__(self, config: StationaryGateConfig | None = None) -> None:
        self.config = config or StationaryGateConfig()
        self.config.validate()
        self._history: deque[tuple[float, float, float]] = deque()
        self._active = False
        self._last_state = StationaryGateState(
            active=False,
            speed_mps=math.inf,
            vx_mps=math.inf,
            vy_mps=math.inf,
            sample_count=0,
            span_s=0.0,
            reason="insufficient_samples",
        )

    @property
    def active(self) -> bool:
        return self._active

    @property
    def state(self) -> StationaryGateState:
        return self._last_state

    def reset(self) -> None:
        self._history.clear()
        self._active = False
        self._last_state = StationaryGateState(
            active=False,
            speed_mps=math.inf,
            vx_mps=math.inf,
            vy_mps=math.inf,
            sample_count=0,
            span_s=0.0,
            reason="reset",
        )

    def update(self, stamp_s: float, x_m: float, y_m: float) -> StationaryGateState:
        """Add a measurement and return the updated gate state."""
        self._validate_measurement(stamp_s, x_m, y_m)

        if self._history and stamp_s < self._history[-1][0]:
            raise ValueError("stationary gate timestamps must be nondecreasing")
        if self._history and stamp_s == self._history[-1][0]:
            self._history[-1] = (stamp_s, x_m, y_m)
        else:
            self._history.append((stamp_s, x_m, y_m))

        self._trim_history(stamp_s)
        vx, vy, speed, sample_count, span_s = self._least_squares_velocity(stamp_s)

        if not math.isfinite(speed):
            self._last_state = StationaryGateState(
                active=self._active,
                speed_mps=math.inf,
                vx_mps=math.inf,
                vy_mps=math.inf,
                sample_count=sample_count,
                span_s=span_s,
                reason="insufficient_window",
            )
            return self._last_state

        reason = "hold_active" if self._active else "hold_inactive"
        if self._active:
            if speed > self.config.exit_speed_mps:
                self._active = False
                reason = "exit_speed_exceeded"
        else:
            if speed < self.config.enter_speed_mps:
                self._active = True
                reason = "enter_speed_below_threshold"

        self._last_state = StationaryGateState(
            active=self._active,
            speed_mps=speed,
            vx_mps=vx,
            vy_mps=vy,
            sample_count=sample_count,
            span_s=span_s,
            reason=reason,
        )
        return self._last_state

    def _trim_history(self, stamp_s: float) -> None:
        keep_s = self.config.history_duration_s
        if keep_s is None:
            keep_s = max(5.0, 3.0 * self.config.window_s)
        keep_after = stamp_s - keep_s
        while self._history and self._history[0][0] < keep_after:
            self._history.popleft()

    def _least_squares_velocity(self, stamp_s: float) -> tuple[float, float, float, int, float]:
        window_start = stamp_s - self.config.window_s
        points = [p for p in self._history if p[0] >= window_start]
        sample_count = len(points)
        if sample_count < self.config.min_samples:
            return math.inf, math.inf, math.inf, sample_count, 0.0

        span_s = points[-1][0] - points[0][0]
        min_span_s = self.config.min_span_fraction * self.config.window_s
        if span_s < min_span_s:
            return math.inf, math.inf, math.inf, sample_count, span_s

        ts = np.array([p[0] - points[0][0] for p in points], dtype=float)
        xs = np.array([p[1] for p in points], dtype=float)
        ys = np.array([p[2] for p in points], dtype=float)

        vx = _least_squares_slope(ts, xs)
        vy = _least_squares_slope(ts, ys)
        speed = math.hypot(vx, vy)
        return vx, vy, speed, sample_count, span_s

    @staticmethod
    def _validate_measurement(stamp_s: float, x_m: float, y_m: float) -> None:
        if not math.isfinite(stamp_s):
            raise ValueError("stamp_s must be finite")
        if not math.isfinite(x_m) or not math.isfinite(y_m):
            raise ValueError("x_m and y_m must be finite")


def _least_squares_slope(times_s: np.ndarray, values: np.ndarray) -> float:
    """Return slope from ordinary least-squares line fit."""
    mt = float(np.mean(times_s))
    mv = float(np.mean(values))
    centered_t = times_s - mt
    denominator = float(np.sum(centered_t**2))
    if denominator <= 1e-12:
        return 0.0
    return float(np.sum(centered_t * (values - mv)) / denominator)
