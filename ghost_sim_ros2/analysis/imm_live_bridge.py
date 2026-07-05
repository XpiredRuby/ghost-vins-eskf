"""Live adapter for the regression-hardened formal IMM cycle.

This module is ROS-free. It converts live x/y pose measurements into the
validated Step 4d IMM cycle and formats combined and per-mode outputs for ROS
wrappers. It intentionally does not replace the existing heuristic hypothesis
bank; live node selection remains a separate integration concern.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np

from analysis.imm_cycle import (
    ASSUMES_WHITE_GAUSSIAN_RESIDUALS,
    COMBINED_COVARIANCE_CAVEAT,
    FORMAL_IMM_5_STEP_CYCLE,
    InteractingMultipleModelEstimator,
    make_smooth_maneuver_cv_imm,
)
from analysis.mode_matched_kf import (
    CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
    INVALID_IF_NOISE_IS_COLORED,
)

FORMAL_IMM_LIVE_BRIDGE_OPTIONAL_NOT_DEFAULT = "FORMAL_IMM_LIVE_BRIDGE_OPTIONAL_NOT_DEFAULT"
LIVE_IMM_NOT_HARDWARE_CALIBRATED = "LIVE_IMM_NOT_HARDWARE_CALIBRATED"
LIVE_IMM_INTEGRATION_CAVEAT = (
    "Formal IMM live output uses candidate Q/R values and assumes white Gaussian residuals. "
    "It is wired for side-by-side live trials, not report-grade covariance claims, until hardware R and "
    "residual whiteness are validated."
)
LIVE_IMM_WAITING_FOR_TARGET = "LIVE_IMM_WAITING_FOR_TARGET"
LIVE_IMM_TRACKING = "LIVE_IMM_TRACKING"
LIVE_IMM_PREDICTION_ONLY = "LIVE_IMM_PREDICTION_ONLY"
LIVE_IMM_DROPOUT_DEGRADED = "LIVE_IMM_DROPOUT_DEGRADED"
DROPOUT_DEGRADED_AFTER_STEPS_DEFAULT = 10
DROPOUT_DEGRADED_RATIONALE = (
    "At the default 30 Hz live rate, 10 consecutive prediction-only cycles is about 0.33 s. "
    "The bridge keeps publishing but marks output degraded instead of silently trusting long open-loop propagation."
)
REJECT_NONFINITE_MEASUREMENT = "REJECT_NONFINITE_MEASUREMENT"
REJECT_BEHIND_CAMERA_MEASUREMENT = "REJECT_BEHIND_CAMERA_MEASUREMENT"
REJECT_OUT_OF_WORKSPACE_MEASUREMENT = "REJECT_OUT_OF_WORKSPACE_MEASUREMENT"


@dataclass(frozen=True)
class FormalImmLiveConfig:
    dt_s: float = 1.0 / 30.0
    measurement_std_m: float = 0.04
    smooth_acceleration_std_mps2: float = 0.015
    maneuver_acceleration_std_mps2: float = 0.75
    initial_mode_probabilities: tuple[float, float] = (0.8, 0.2)
    p0_diag: tuple[float, float, float, float] = (0.04, 0.04, 0.25, 0.25)
    future_horizon_s: float = 1.5
    future_dt_s: float = 0.10
    dropout_degraded_after_steps: int = DROPOUT_DEGRADED_AFTER_STEPS_DEFAULT
    parameter_status: str = CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
    integration_status: str = FORMAL_IMM_LIVE_BRIDGE_OPTIONAL_NOT_DEFAULT
    covariance_validity_status: str = INVALID_IF_NOISE_IS_COLORED

    def validate(self) -> None:
        _require_positive("dt_s", self.dt_s)
        _require_positive("measurement_std_m", self.measurement_std_m)
        _require_positive("smooth_acceleration_std_mps2", self.smooth_acceleration_std_mps2)
        _require_positive("maneuver_acceleration_std_mps2", self.maneuver_acceleration_std_mps2)
        _require_positive("future_horizon_s", self.future_horizon_s)
        _require_positive("future_dt_s", self.future_dt_s)
        if self.future_dt_s > self.future_horizon_s:
            raise ValueError("future_dt_s must be <= future_horizon_s")
        if self.dropout_degraded_after_steps < 1:
            raise ValueError("dropout_degraded_after_steps must be >= 1")
        if len(self.initial_mode_probabilities) != 2:
            raise ValueError("initial_mode_probabilities must contain smooth and maneuver probabilities")
        if any(v < 0.0 or not math.isfinite(v) for v in self.initial_mode_probabilities):
            raise ValueError("initial mode probabilities must be finite and nonnegative")
        if sum(self.initial_mode_probabilities) <= 0.0:
            raise ValueError("initial mode probabilities must sum positive")
        if len(self.p0_diag) != 4 or any(v <= 0.0 or not math.isfinite(v) for v in self.p0_diag):
            raise ValueError("p0_diag must contain four finite positive entries")


@dataclass(frozen=True)
class FormalImmLiveOutput:
    initialized: bool
    sequence: int
    estimate: dict[str, float] | None
    mode_probabilities: dict[str, float]
    hypotheses: list[dict[str, object]]
    live_status: str
    prediction_only_steps: int
    dropout_degraded_after_steps: int
    estimator_status: str
    integration_status: str
    parameter_status: str
    measurement_assumption_label: str
    covariance_validity_status: str
    covariance_caveat: str
    integration_caveat: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class FormalImmLiveAdapter:
    """Lazy-initialized live adapter for x/y position measurements."""

    def __init__(self, config: FormalImmLiveConfig | None = None) -> None:
        self.config = config or FormalImmLiveConfig()
        self.config.validate()
        self.imm: InteractingMultipleModelEstimator | None = None
        self.sequence = 0
        self.prediction_only_steps = 0
        self.last_output = FormalImmLiveOutput(
            initialized=False,
            sequence=0,
            estimate=None,
            mode_probabilities={},
            hypotheses=[],
            live_status=LIVE_IMM_WAITING_FOR_TARGET,
            prediction_only_steps=0,
            dropout_degraded_after_steps=self.config.dropout_degraded_after_steps,
            estimator_status=FORMAL_IMM_5_STEP_CYCLE,
            integration_status=self.config.integration_status,
            parameter_status=self.config.parameter_status,
            measurement_assumption_label=ASSUMES_WHITE_GAUSSIAN_RESIDUALS,
            covariance_validity_status=self.config.covariance_validity_status,
            covariance_caveat=COMBINED_COVARIANCE_CAVEAT,
            integration_caveat=LIVE_IMM_INTEGRATION_CAVEAT,
        )

    @property
    def initialized(self) -> bool:
        return self.imm is not None

    def step(self, measurement_xy: Iterable[float] | None) -> FormalImmLiveOutput:
        self.sequence += 1
        measurement = None if measurement_xy is None else _measurement(measurement_xy)
        if self.imm is None:
            if measurement is None:
                self.prediction_only_steps = 0
                self.last_output = FormalImmLiveOutput(
                    initialized=False,
                    sequence=self.sequence,
                    estimate=None,
                    mode_probabilities={},
                    hypotheses=[],
                    live_status=LIVE_IMM_WAITING_FOR_TARGET,
                    prediction_only_steps=0,
                    dropout_degraded_after_steps=self.config.dropout_degraded_after_steps,
                    estimator_status=FORMAL_IMM_5_STEP_CYCLE,
                    integration_status=self.config.integration_status,
                    parameter_status=self.config.parameter_status,
                    measurement_assumption_label=ASSUMES_WHITE_GAUSSIAN_RESIDUALS,
                    covariance_validity_status=self.config.covariance_validity_status,
                    covariance_caveat=COMBINED_COVARIANCE_CAVEAT,
                    integration_caveat=LIVE_IMM_INTEGRATION_CAVEAT,
                )
                return self.last_output
            self.imm = make_smooth_maneuver_cv_imm(
                dt=self.config.dt_s,
                measurement_std_m=self.config.measurement_std_m,
                smooth_acceleration_std_mps2=self.config.smooth_acceleration_std_mps2,
                maneuver_acceleration_std_mps2=self.config.maneuver_acceleration_std_mps2,
                initial_mode_probabilities=self.config.initial_mode_probabilities,
                initial_state=[measurement[0], measurement[1], 0.0, 0.0],
                p0_diag=self.config.p0_diag,
            )

        if measurement is None:
            self.prediction_only_steps += 1
        else:
            self.prediction_only_steps = 0
        cycle_step = self.imm.step(None if measurement is None else measurement)
        combined = cycle_step.combined_estimate
        estimate = _estimate_dict(combined.x, combined.p)
        hypotheses = []
        for name in cycle_step.mode_probabilities:
            mode_estimate = cycle_step.mode_estimates[name]
            hypotheses.append(
                {
                    **_estimate_dict(mode_estimate.x, mode_estimate.p),
                    "model": name,
                    "probability": float(cycle_step.mode_probabilities[name]),
                    "path": self.project_path(mode_estimate.x),
                }
            )
        hypotheses.sort(key=lambda row: float(row["probability"]), reverse=True)
        for rank, row in enumerate(hypotheses, start=1):
            row["rank"] = rank

        self.last_output = FormalImmLiveOutput(
            initialized=True,
            sequence=self.sequence,
            estimate=estimate,
            mode_probabilities=combined.mode_probabilities,
            hypotheses=hypotheses,
            live_status=self._live_status(measurement is not None),
            prediction_only_steps=self.prediction_only_steps,
            dropout_degraded_after_steps=self.config.dropout_degraded_after_steps,
            estimator_status=cycle_step.estimator_status,
            integration_status=self.config.integration_status,
            parameter_status=self.config.parameter_status,
            measurement_assumption_label=combined.measurement_assumption_label,
            covariance_validity_status=combined.covariance_validity_status,
            covariance_caveat=combined.covariance_caveat,
            integration_caveat=LIVE_IMM_INTEGRATION_CAVEAT,
        )
        return self.last_output

    def _live_status(self, has_measurement: bool) -> str:
        if has_measurement:
            return LIVE_IMM_TRACKING
        if self.prediction_only_steps >= self.config.dropout_degraded_after_steps:
            return LIVE_IMM_DROPOUT_DEGRADED
        return LIVE_IMM_PREDICTION_ONLY

    def project_path(self, state: Iterable[float]) -> list[dict[str, float]]:
        values = np.asarray(list(state), dtype=float)
        if values.shape != (4,) or not np.isfinite(values).all():
            raise ValueError("state must be a finite 4-vector")
        points = []
        t = 0.0
        while t <= self.config.future_horizon_s + 1e-9:
            points.append(
                {
                    "t_s": round(t, 3),
                    "x_m": float(values[0] + values[2] * t),
                    "y_m": float(values[1] + values[3] * t),
                }
            )
            step = min(self.config.future_dt_s, self.config.future_horizon_s - t)
            if step <= 1e-9:
                break
            t += step
        return points


@dataclass(frozen=True)
class LiveMeasurementValidation:
    valid: bool
    measurement_xy: list[float] | None
    rejection_reason: str | None


def validate_live_measurement_xy(x: float, y: float, max_workspace_range_m: float) -> LiveMeasurementValidation:
    """Validate live x/y measurements without throwing inside the ROS callback."""
    _require_positive("max_workspace_range_m", max_workspace_range_m)
    x = float(x)
    y = float(y)
    if not math.isfinite(x) or not math.isfinite(y):
        return LiveMeasurementValidation(False, None, REJECT_NONFINITE_MEASUREMENT)
    if x < 0.0:
        return LiveMeasurementValidation(False, None, REJECT_BEHIND_CAMERA_MEASUREMENT)
    if math.hypot(x, y) > max_workspace_range_m:
        return LiveMeasurementValidation(False, None, REJECT_OUT_OF_WORKSPACE_MEASUREMENT)
    return LiveMeasurementValidation(True, [x, y], None)


def _estimate_dict(state: Iterable[float], covariance: Iterable[Iterable[float]]) -> dict[str, float]:
    x = np.asarray(list(state), dtype=float)
    p = np.asarray(covariance, dtype=float)
    if x.shape != (4,) or p.shape != (4, 4):
        raise ValueError("formal IMM live output expects a 4-state covariance")
    return {
        "x_m": float(x[0]),
        "y_m": float(x[1]),
        "vx_mps": float(x[2]),
        "vy_mps": float(x[3]),
        "cov_xx": float(p[0, 0]),
        "cov_xy": float(p[0, 1]),
        "cov_yy": float(p[1, 1]),
        "cov_vxvx": float(p[2, 2]),
        "cov_vyvy": float(p[3, 3]),
    }


def _measurement(values: Iterable[float]) -> list[float]:
    arr = np.asarray(list(values), dtype=float)
    if arr.shape != (2,) or not np.isfinite(arr).all():
        raise ValueError("measurement_xy must contain finite x/y values")
    return [float(arr[0]), float(arr[1])]


def _require_positive(name: str, value: float) -> None:
    if value <= 0.0 or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and positive")
