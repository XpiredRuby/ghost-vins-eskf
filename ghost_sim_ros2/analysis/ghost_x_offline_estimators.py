"""Offline estimator adapters used by the GHOST-X controlled-truth campaign.

All adapters consume the same ordered timestamped measurement stream.  This
module is ROS-free so canonical streams can be replayed deterministically in CI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.imm_live_bridge import FormalImmLiveAdapter, FormalImmLiveConfig


@dataclass(frozen=True)
class OfflineEstimate:
    initialized: bool
    state: tuple[float, float, float, float] | None
    covariance: tuple[tuple[float, ...], ...] | None
    status: str
    reset: bool = False
    mode_probabilities: dict[str, float] | None = None
    hypothesis_weights: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        state = None
        if self.state is not None:
            state = {
                "x_m": self.state[0],
                "y_m": self.state[1],
                "vx_mps": self.state[2],
                "vy_mps": self.state[3],
            }
        return {
            "initialized": self.initialized,
            "state": state,
            "covariance": [list(row) for row in self.covariance] if self.covariance else None,
            "status": self.status,
            "reset": self.reset,
            "mode_probabilities": self.mode_probabilities or {},
            "hypothesis_weights": self.hypothesis_weights or {},
        }


class CvKalmanAdapter:
    """Independent constant-velocity Kalman baseline."""

    name = "cv_kalman"

    def __init__(
        self,
        measurement_covariance_xy: Iterable[Iterable[float]],
        process_accel_std_mps2: float = 0.65,
        initial_position_var_m2: float = 0.04,
        initial_velocity_var_m2ps2: float = 0.8,
    ) -> None:
        self.r = np.asarray(measurement_covariance_xy, dtype=float)
        if self.r.shape != (2, 2) or not np.isfinite(self.r).all():
            raise ValueError("measurement_covariance_xy must be a finite 2x2 matrix")
        self.q_accel = float(process_accel_std_mps2)
        self.p0 = np.diag(
            [initial_position_var_m2, initial_position_var_m2, initial_velocity_var_m2ps2, initial_velocity_var_m2ps2]
        )
        self.h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)
        self.x: np.ndarray | None = None
        self.p: np.ndarray | None = None
        self.was_initialized = False

    def step(self, dt_s: float, measurement_xy: Iterable[float] | None) -> OfflineEstimate:
        dt = _positive_dt(dt_s)
        reset = False
        if self.x is None:
            if measurement_xy is None:
                return OfflineEstimate(False, None, None, "WAITING_FOR_MEASUREMENT")
            z = _measurement(measurement_xy)
            self.x = np.array([z[0], z[1], 0.0, 0.0], dtype=float)
            self.p = self.p0.copy()
            self.was_initialized = True
            return self._output("TRACKING", reset)

        assert self.p is not None
        f = np.array(
            [[1.0, 0.0, dt, 0.0], [0.0, 1.0, 0.0, dt], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
            dtype=float,
        )
        q = _white_acceleration_q(dt, self.q_accel)
        self.x = f @ self.x
        self.p = _symmetrize(f @ self.p @ f.T + q)
        if measurement_xy is None:
            return self._output("PREDICTION_ONLY", reset)

        z = _measurement(measurement_xy)
        innovation = z - self.h @ self.x
        s = self.h @ self.p @ self.h.T + self.r
        try:
            k = np.linalg.solve(s.T, (self.p @ self.h.T).T).T
        except np.linalg.LinAlgError:
            self.x = None
            self.p = None
            reset = True
            return OfflineEstimate(False, None, None, "NUMERICAL_RESET", reset=True)
        eye = np.eye(4)
        self.x = self.x + k @ innovation
        joseph = eye - k @ self.h
        self.p = _symmetrize(joseph @ self.p @ joseph.T + k @ self.r @ k.T)
        if not np.isfinite(self.x).all() or not np.isfinite(self.p).all():
            self.x = None
            self.p = None
            return OfflineEstimate(False, None, None, "NONFINITE_RESET", reset=True)
        return self._output("TRACKING", reset)

    def _output(self, status: str, reset: bool) -> OfflineEstimate:
        assert self.x is not None and self.p is not None
        return OfflineEstimate(
            True,
            tuple(float(v) for v in self.x),
            tuple(tuple(float(v) for v in row) for row in self.p),
            status,
            reset=reset,
        )


class FormalImmOfflineAdapter:
    name = "formal_imm"

    def __init__(
        self,
        dt_s: float,
        measurement_covariance_xy: Iterable[Iterable[float]],
        smooth_acceleration_std_mps2: float = 0.015,
        maneuver_acceleration_std_mps2: float = 0.75,
        transition_probabilities: tuple[tuple[float, float], tuple[float, float]] = ((0.97, 0.03), (0.03, 0.97)),
        p0_diag: tuple[float, float, float, float] = (0.04, 0.04, 0.25, 0.25),
    ) -> None:
        matrix = np.asarray(measurement_covariance_xy, dtype=float)
        cov = tuple(tuple(float(v) for v in row) for row in matrix)
        self.bridge = FormalImmLiveAdapter(
            FormalImmLiveConfig(
                dt_s=float(dt_s),
                measurement_std_m=math.sqrt(max(float(matrix[0, 0]), 1e-12)),
                measurement_covariance_xy=cov,
                smooth_acceleration_std_mps2=float(smooth_acceleration_std_mps2),
                maneuver_acceleration_std_mps2=float(maneuver_acceleration_std_mps2),
                transition_probabilities=transition_probabilities,
                p0_diag=p0_diag,
                future_horizon_s=1.5,
                future_dt_s=min(0.1, float(dt_s)),
                dropout_degraded_after_steps=max(1, int(round(0.5 / float(dt_s)))),
            )
        )
        self.previous_initialized = False

    def step(self, dt_s: float, measurement_xy: Iterable[float] | None) -> OfflineEstimate:
        # Canonical G4 streams use fixed dt. Refuse accidental inconsistent replay.
        if abs(float(dt_s) - self.bridge.config.dt_s) > 1e-9:
            raise ValueError("Formal IMM offline replay requires the canonical fixed dt")
        output = self.bridge.step(measurement_xy)
        reset = self.previous_initialized and not output.initialized
        self.previous_initialized = output.initialized
        if not output.initialized or output.estimate is None:
            return OfflineEstimate(False, None, None, output.live_status, reset=reset)
        e = output.estimate
        p = np.array(
            [
                [e["cov_xx"], e["cov_xy"], 0.0, 0.0],
                [e["cov_xy"], e["cov_yy"], 0.0, 0.0],
                [0.0, 0.0, e["cov_vxvx"], 0.0],
                [0.0, 0.0, 0.0, e["cov_vyvy"]],
            ],
            dtype=float,
        )
        return OfflineEstimate(
            True,
            (float(e["x_m"]), float(e["y_m"]), float(e["vx_mps"]), float(e["vy_mps"])),
            tuple(tuple(float(v) for v in row) for row in p),
            output.live_status,
            reset=reset,
            mode_probabilities={k: float(v) for k, v in output.mode_probabilities.items()},
        )


class GhostMhOfflineAdapter:
    name = "ghost_mh"

    def __init__(
        self,
        measurement_covariance_xy: Iterable[Iterable[float]],
        max_occlusion_s: float = 20.0,
        max_workspace_range_m: float = 100.0,
        accel_temperature: float = 0.30,
    ) -> None:
        matrix = np.asarray(measurement_covariance_xy, dtype=float)
        self.tracker = CalibratedModeBankTracker(
            measurement_std_m=math.sqrt(max(float(matrix[0, 0]), 1e-12)),
            measurement_covariance_xy=matrix,
            max_occlusion_s=float(max_occlusion_s),
            max_workspace_range_m=float(max_workspace_range_m),
            accel_temperature=float(accel_temperature),
            allow_signed_local_coordinates=True,
        )
        self.previous_initialized = False

    def step(self, dt_s: float, measurement_xy: Iterable[float] | None) -> OfflineEstimate:
        self.tracker.step(_positive_dt(dt_s), measurement_xy)
        estimate = self.tracker.estimate()
        reset = self.previous_initialized and not estimate.initialized
        self.previous_initialized = estimate.initialized
        if not estimate.initialized:
            return OfflineEstimate(False, None, None, "WAITING_OR_EXPIRED", reset=reset)
        weights = {str(h.model): float(h.weight) for h in self.tracker.top_hypotheses(8)}
        status = "TRACKING" if measurement_xy is not None else "HYPOTHESIS_PREDICTION"
        return OfflineEstimate(
            True,
            tuple(float(estimate.x[i, 0]) for i in range(4)),
            tuple(tuple(float(v) for v in row) for row in estimate.p),
            status,
            reset=reset,
            hypothesis_weights=weights,
        )


def make_default_adapters(
    dt_s: float,
    measurement_covariance_xy: Iterable[Iterable[float]],
    *,
    imm_smooth_acceleration_std_mps2: float = 0.015,
    imm_maneuver_acceleration_std_mps2: float = 0.75,
    mh_accel_temperature: float = 0.30,
    mh_max_occlusion_s: float = 20.0,
) -> dict[str, Any]:
    return {
        "cv_kalman": CvKalmanAdapter(measurement_covariance_xy),
        "formal_imm": FormalImmOfflineAdapter(
            dt_s,
            measurement_covariance_xy,
            smooth_acceleration_std_mps2=imm_smooth_acceleration_std_mps2,
            maneuver_acceleration_std_mps2=imm_maneuver_acceleration_std_mps2,
        ),
        "ghost_mh": GhostMhOfflineAdapter(
            measurement_covariance_xy,
            max_occlusion_s=mh_max_occlusion_s,
            accel_temperature=mh_accel_temperature,
        ),
    }


def _measurement(values: Iterable[float]) -> np.ndarray:
    z = np.asarray(list(values), dtype=float)
    if z.shape != (2,) or not np.isfinite(z).all():
        raise ValueError("measurement must be a finite x/y pair")
    return z


def _positive_dt(value: float) -> float:
    dt = float(value)
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    return dt


def _white_acceleration_q(dt: float, sigma_a: float) -> np.ndarray:
    q = sigma_a * sigma_a
    return q * np.array(
        [
            [dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0],
            [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0],
            [dt**3 / 2.0, 0.0, dt**2, 0.0],
            [0.0, dt**3 / 2.0, 0.0, dt**2],
        ],
        dtype=float,
    )


def _symmetrize(matrix: np.ndarray) -> np.ndarray:
    return 0.5 * (matrix + matrix.T)
