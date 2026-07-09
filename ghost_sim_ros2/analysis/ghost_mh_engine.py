import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from analysis.measurement_covariance_config import (
    build_measurement_r_xy,
    covariance_to_list,
    measurement_r_provenance,
    measurement_r_source,
    measurement_r_status,
)


STATE_DIM = 4
MEAS_DIM = 2


@dataclass(frozen=True)
class MotionModel:
    """Physics hypothesis for one prediction branch."""

    name: str
    ax_mps2: float = 0.0
    ay_mps2: float = 0.0
    speed_scale: float = 1.0
    process_accel_std_mps2: float = 1.0
    prior: float = 1.0


@dataclass
class Hypothesis:
    """One probabilistic target future."""

    model: str
    weight: float
    x: np.ndarray
    p: np.ndarray
    age_s: float = 0.0


@dataclass
class Estimate:
    initialized: bool
    x: np.ndarray
    p: np.ndarray
    hypotheses: list[Hypothesis]


def default_drone_models() -> list[MotionModel]:
    """Return a small motion bank for low-speed indoor target tracking."""

    return [
        MotionModel("constant_velocity", process_accel_std_mps2=0.7, prior=0.24),
        MotionModel("brake_or_hover", speed_scale=0.82, process_accel_std_mps2=0.5, prior=0.14),
        MotionModel("coordinated_turn_left", ax_mps2=-0.08, ay_mps2=0.12, process_accel_std_mps2=0.65, prior=0.20),
        MotionModel("coordinated_turn_right", ax_mps2=-0.08, ay_mps2=-0.12, process_accel_std_mps2=0.65, prior=0.14),
        MotionModel("accelerate_forward", ax_mps2=0.35, process_accel_std_mps2=1.0, prior=0.10),
        MotionModel("accelerate_left", ay_mps2=0.35, process_accel_std_mps2=1.0, prior=0.08),
        MotionModel("accelerate_right", ay_mps2=-0.35, process_accel_std_mps2=1.0, prior=0.06),
        MotionModel("evasive_maneuver", process_accel_std_mps2=2.0, prior=0.04),
    ]


def _as_col(values: Iterable[float], rows: int) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float).reshape(rows, 1)
    if not np.isfinite(arr).all():
        raise ValueError("state contains non-finite values")
    return arr


def _cv_matrix(dt: float) -> np.ndarray:
    return np.array(
        [
            [1.0, 0.0, dt, 0.0],
            [0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _process_noise(dt: float, accel_std: float) -> np.ndarray:
    q = accel_std * accel_std
    return q * np.array(
        [
            [dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0],
            [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0],
            [dt**3 / 2.0, 0.0, dt**2, 0.0],
            [0.0, dt**3 / 2.0, 0.0, dt**2],
        ],
        dtype=float,
    )


def _gaussian_likelihood(innovation: np.ndarray, s: np.ndarray) -> float:
    try:
        inv_s = np.linalg.inv(s)
        det_s = float(np.linalg.det(s))
    except np.linalg.LinAlgError:
        return 0.0

    if det_s <= 0.0 or not math.isfinite(det_s):
        return 0.0

    exponent = float(-0.5 * (innovation.T @ inv_s @ innovation)[0, 0])
    norm = 1.0 / (2.0 * math.pi * math.sqrt(det_s))
    return float(norm * math.exp(max(exponent, -80.0)))


class MultiHypothesisTracker:
    """No-camera GHOST-MH v1 tracker.

    State is [x, y, vx, vy]. During visual occlusion, the tracker branches each
    surviving target future through a bank of physics hypotheses. When a
    measurement returns, each branch receives a Bayesian likelihood score and the
    posterior is pruned back to the most plausible futures.
    """

    def __init__(
        self,
        models: list[MotionModel] | None = None,
        max_hypotheses: int = 24,
        max_occlusion_s: float = 3.0,
        max_workspace_range_m: float = 8.0,
        measurement_std_m: float = 0.05,
        gate_chi2: float = 16.0,
        measurement_covariance_xy: Iterable[Iterable[float]] | None = None,
    ):
        self.models = models if models is not None else default_drone_models()
        self.max_hypotheses = int(max_hypotheses)
        self.max_occlusion_s = float(max_occlusion_s)
        self.max_workspace_range_m = float(max_workspace_range_m)
        self.measurement_std_m = float(measurement_std_m)
        self.measurement_covariance_xy = (
            tuple(tuple(float(v) for v in row) for row in measurement_covariance_xy)
            if measurement_covariance_xy is not None
            else None
        )
        self.gate_chi2 = float(gate_chi2)
        self.h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)
        self.r = np.asarray(
            build_measurement_r_xy(
                self.measurement_std_m,
                self.measurement_covariance_xy[0][0] if self.measurement_covariance_xy is not None else None,
                self.measurement_covariance_xy[0][1] if self.measurement_covariance_xy is not None else 0.0,
                self.measurement_covariance_xy[1][1] if self.measurement_covariance_xy is not None else None,
            ),
            dtype=float,
        )
        self.measurement_r_xy = covariance_to_list(self.r)
        self.measurement_r_source = measurement_r_source(self.measurement_covariance_xy, self.measurement_std_m)
        self.measurement_r_status = measurement_r_status(self.measurement_covariance_xy)
        self.measurement_r_provenance = measurement_r_provenance(self.measurement_covariance_xy)
        self.hypotheses: list[Hypothesis] = []

    @property
    def initialized(self) -> bool:
        return bool(self.hypotheses)

    def initialize(
        self,
        z_xy: Iterable[float],
        velocity_xy: Iterable[float] = (0.0, 0.0),
        position_var_m2: float = 0.05,
        velocity_var_m2ps2: float = 1.0,
    ) -> None:
        z = _as_col(z_xy, MEAS_DIM)
        v = _as_col(velocity_xy, MEAS_DIM)
        x = np.array([[z[0, 0]], [z[1, 0]], [v[0, 0]], [v[1, 0]]], dtype=float)
        p = np.diag([position_var_m2, position_var_m2, velocity_var_m2ps2, velocity_var_m2ps2])
        self.hypotheses = [Hypothesis("initial", 1.0, x, p, 0.0)]

    def reset(self) -> None:
        self.hypotheses = []

    def _predict_one(self, hyp: Hypothesis, model: MotionModel, dt: float) -> Hypothesis:
        f = _cv_matrix(dt)
        x = f @ hyp.x
        x[0, 0] += 0.5 * model.ax_mps2 * dt * dt
        x[1, 0] += 0.5 * model.ay_mps2 * dt * dt
        x[2, 0] = model.speed_scale * (x[2, 0] + model.ax_mps2 * dt)
        x[3, 0] = model.speed_scale * (x[3, 0] + model.ay_mps2 * dt)
        p = f @ hyp.p @ f.T + _process_noise(dt, model.process_accel_std_mps2)
        return Hypothesis(model.name, hyp.weight * model.prior, x, p, hyp.age_s + dt)

    def predict(self, dt: float, visible: bool = False) -> None:
        if not self.hypotheses:
            return
        if dt <= 0.0:
            return

        predicted = []
        for hyp in self.hypotheses:
            models = self.models if not visible else [self.models[0]]
            for model in models:
                child = self._predict_one(hyp, model, dt)
                if self._is_reasonable(child):
                    predicted.append(child)

        if not predicted:
            self.reset()
            return

        self.hypotheses = self._normalize_and_prune(predicted)

    def update(self, z_xy: Iterable[float]) -> bool:
        z = _as_col(z_xy, MEAS_DIM)
        if not self.hypotheses:
            self.initialize([z[0, 0], z[1, 0]])
            return True

        updated = []
        for hyp in self.hypotheses:
            innovation = z - self.h @ hyp.x
            s = self.h @ hyp.p @ self.h.T + self.r
            try:
                nis = float((innovation.T @ np.linalg.inv(s) @ innovation)[0, 0])
            except np.linalg.LinAlgError:
                continue
            if nis > self.gate_chi2:
                continue

            k = hyp.p @ self.h.T @ np.linalg.inv(s)
            eye = np.eye(STATE_DIM)
            x = hyp.x + k @ innovation
            p = (eye - k @ self.h) @ hyp.p @ (eye - k @ self.h).T + k @ self.r @ k.T
            likelihood = _gaussian_likelihood(innovation, s)
            updated.append(Hypothesis(hyp.model, hyp.weight * likelihood, x, p, 0.0))

        if not updated:
            return False

        self.hypotheses = self._normalize_and_prune(updated)
        return True

    def step(self, dt: float, measurement_xy: Iterable[float] | None) -> bool:
        self.predict(dt, visible=measurement_xy is not None)
        if measurement_xy is None:
            self.hypotheses = [
                hyp for hyp in self.hypotheses if hyp.age_s <= self.max_occlusion_s
            ]
            if not self.hypotheses:
                self.reset()
            return False
        return self.update(measurement_xy)

    def estimate(self) -> Estimate:
        if not self.hypotheses:
            return Estimate(False, np.zeros((STATE_DIM, 1)), np.eye(STATE_DIM), [])

        weights = np.array([hyp.weight for hyp in self.hypotheses], dtype=float)
        x = sum(hyp.weight * hyp.x for hyp in self.hypotheses)
        p = np.zeros((STATE_DIM, STATE_DIM), dtype=float)
        for hyp in self.hypotheses:
            dx = hyp.x - x
            p += hyp.weight * (hyp.p + dx @ dx.T)
        if abs(float(np.sum(weights)) - 1.0) > 1e-6:
            raise RuntimeError("hypothesis weights are not normalized")
        return Estimate(True, x, p, list(self.hypotheses))

    def top_hypotheses(self, n: int = 5) -> list[Hypothesis]:
        return sorted(self.hypotheses, key=lambda hyp: hyp.weight, reverse=True)[:n]

    def _is_reasonable(self, hyp: Hypothesis) -> bool:
        if hyp.age_s > self.max_occlusion_s:
            return False
        px = float(hyp.x[0, 0])
        py = float(hyp.x[1, 0])
        return px >= -0.25 and math.hypot(px, py) <= self.max_workspace_range_m

    def _normalize_and_prune(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        hypotheses = sorted(hypotheses, key=lambda hyp: hyp.weight, reverse=True)
        hypotheses = hypotheses[: self.max_hypotheses]
        total = sum(max(0.0, hyp.weight) for hyp in hypotheses)
        if total <= 0.0 or not math.isfinite(total):
            uniform = 1.0 / len(hypotheses)
            for hyp in hypotheses:
                hyp.weight = uniform
            return hypotheses
        for hyp in hypotheses:
            hyp.weight = max(0.0, hyp.weight) / total
        return hypotheses
