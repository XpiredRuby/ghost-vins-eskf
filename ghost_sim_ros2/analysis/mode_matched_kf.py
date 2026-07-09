"""Mode-matched Kalman filter bank for GHOST formal IMM bring-up.

Step 4a intentionally implements independent mode-conditioned Kalman filters
only. There is no mode probability update and no IMM mixing in this module.
Those steps are validation-gated follow-on PRs.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

import numpy as np

from analysis import observability_crlb as model_defs
from analysis.measurement_covariance_config import (
    build_measurement_r_xy,
    measurement_r_provenance,
)

ASSUMES_WHITE_GAUSSIAN_RESIDUALS = "ASSUMES_WHITE_GAUSSIAN_RESIDUALS"
INVALID_IF_NOISE_IS_COLORED = "INVALID_IF_NOISE_IS_COLORED"
CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R = "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R"
MODE_MATCHED_KF_BANK_NO_MIXING = "MODE_MATCHED_KF_BANK_NO_MIXING"


@dataclass(frozen=True)
class KalmanModel:
    """Linear Gaussian model for one independent mode-matched KF."""

    name: str
    f: list[list[float]]
    h: list[list[float]]
    q: list[list[float]]
    r: list[list[float]]
    state_labels: tuple[str, ...]
    measurement_labels: tuple[str, ...]
    process_noise_status: str
    process_noise_provenance: str
    measurement_noise_status: str
    measurement_noise_provenance: str
    measurement_assumption_label: str = ASSUMES_WHITE_GAUSSIAN_RESIDUALS
    covariance_validity_status: str = INVALID_IF_NOISE_IS_COLORED
    estimator_status: str = MODE_MATCHED_KF_BANK_NO_MIXING

    def f_matrix(self) -> np.ndarray:
        return _matrix("f", self.f)

    def h_matrix(self) -> np.ndarray:
        return _matrix("h", self.h)

    def q_matrix(self) -> np.ndarray:
        return _matrix("q", self.q)

    def r_matrix(self) -> np.ndarray:
        return _matrix("r", self.r)


@dataclass(frozen=True)
class KalmanEstimate:
    model_name: str
    x: list[float]
    p: list[list[float]]
    covariance_validity_status: str
    estimator_status: str


@dataclass(frozen=True)
class KalmanUpdateDiagnostics:
    innovation: list[float]
    innovation_covariance: list[list[float]]
    kalman_gain: list[list[float]]
    normalized_innovation_squared: float
    likelihood: float
    measurement_assumption_label: str
    covariance_validity_status: str


@dataclass(frozen=True)
class ModeSelfCheckResult:
    model_name: str
    trials: int
    steps: int
    burn_in_steps: int
    final_position_rmse_m: float
    final_velocity_rmse_mps: float
    final_acceleration_rmse_mps2: float | None
    two_sigma_coverage_fraction: float
    expected_two_sigma_fraction: float
    coverage_sample_count: int
    measurement_assumption_label: str
    covariance_validity_status: str

    def to_dict(self) -> dict:
        return asdict(self)


class ModeMatchedKalmanFilter:
    """Standard linear KF for one mode, with no interaction or mixing."""

    def __init__(self, model: KalmanModel, x0: Iterable[float], p0: np.ndarray):
        self.model = model
        self.f = model.f_matrix()
        self.h = model.h_matrix()
        self.q = model.q_matrix()
        self.r = model.r_matrix()
        self.x = _col("x0", x0)
        self.p = _matrix("p0", p0).copy()
        self._validate_shapes()

    def predict(self) -> KalmanEstimate:
        self.x = self.f @ self.x
        self.p = _symmetrize(self.f @ self.p @ self.f.T + self.q)
        return self.estimate()

    def update(self, measurement: Iterable[float]) -> KalmanUpdateDiagnostics:
        z = _col("measurement", measurement)
        if z.shape[0] != self.h.shape[0]:
            raise ValueError("measurement dimension must match H rows")

        innovation = z - self.h @ self.x
        s = _symmetrize(self.h @ self.p @ self.h.T + self.r)
        try:
            inv_s = np.linalg.inv(s)
        except np.linalg.LinAlgError as exc:
            raise ValueError("innovation covariance is singular") from exc

        k = self.p @ self.h.T @ inv_s
        eye = np.eye(self.x.shape[0])
        self.x = self.x + k @ innovation
        self.p = _symmetrize((eye - k @ self.h) @ self.p @ (eye - k @ self.h).T + k @ self.r @ k.T)
        nis = float((innovation.T @ inv_s @ innovation)[0, 0])
        return KalmanUpdateDiagnostics(
            innovation=_vector(innovation),
            innovation_covariance=_to_list(s),
            kalman_gain=_to_list(k),
            normalized_innovation_squared=nis,
            likelihood=_gaussian_likelihood(innovation, s),
            measurement_assumption_label=self.model.measurement_assumption_label,
            covariance_validity_status=self.model.covariance_validity_status,
        )

    def step(self, measurement: Iterable[float] | None) -> tuple[KalmanEstimate, KalmanUpdateDiagnostics | None]:
        self.predict()
        diagnostics = None
        if measurement is not None:
            diagnostics = self.update(measurement)
        return self.estimate(), diagnostics

    def estimate(self) -> KalmanEstimate:
        return KalmanEstimate(
            model_name=self.model.name,
            x=_vector(self.x),
            p=_to_list(self.p),
            covariance_validity_status=self.model.covariance_validity_status,
            estimator_status=self.model.estimator_status,
        )

    def _validate_shapes(self) -> None:
        state_dim = self.x.shape[0]
        if self.f.shape != (state_dim, state_dim):
            raise ValueError("F must be state_dim x state_dim")
        if self.q.shape != (state_dim, state_dim):
            raise ValueError("Q must be state_dim x state_dim")
        if self.h.shape[1] != state_dim:
            raise ValueError("H columns must match state dimension")
        if self.r.shape != (self.h.shape[0], self.h.shape[0]):
            raise ValueError("R must be measurement_dim x measurement_dim")
        if self.p.shape != (state_dim, state_dim):
            raise ValueError("P0 must be state_dim x state_dim")
        _require_symmetric_psd("P0", self.p)
        _require_symmetric_psd("Q", self.q)
        _require_symmetric_psd("R", self.r)


class ModeMatchedKalmanFilterBank:
    """Collection of independent mode-matched KFs.

    This is deliberately a parallel filter bank, not an IMM. States, covariance,
    and updates are per-mode only; no mode can read or mix another mode's state.
    """

    def __init__(self, filters: Iterable[ModeMatchedKalmanFilter]):
        self.filters = {f.model.name: f for f in filters}
        if not self.filters:
            raise ValueError("at least one filter is required")

    def step(
        self,
        measurement: Iterable[float] | Mapping[str, Iterable[float]] | None,
    ) -> dict[str, KalmanEstimate]:
        estimates = {}
        for name, filt in self.filters.items():
            z = measurement.get(name) if isinstance(measurement, Mapping) else measurement
            estimate, _diagnostics = filt.step(z)
            estimates[name] = estimate
        return estimates

    def estimates(self) -> dict[str, KalmanEstimate]:
        return {name: filt.estimate() for name, filt in self.filters.items()}


def cv_position_model(
    dt: float,
    acceleration_std_mps2: float,
    measurement_std_m: float,
    name: str = "cv",
    status: str = CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
    measurement_covariance_xy: Iterable[Iterable[float]] | None = None,
) -> KalmanModel:
    """Create a CV position-measurement KF model for [x, y, vx, vy]."""
    _require_positive("dt", dt)
    _require_positive("acceleration_std_mps2", acceleration_std_mps2)
    _require_positive("measurement_std_m", measurement_std_m)
    f = model_defs.cv_state_transition(dt)
    h = _position_h(4)
    q = _cv_white_acceleration_q(dt, acceleration_std_mps2)
    r = np.asarray(
        build_measurement_r_xy(
            measurement_std_m,
            measurement_covariance_xy[0][0] if measurement_covariance_xy is not None else None,
            measurement_covariance_xy[0][1] if measurement_covariance_xy is not None else 0.0,
            measurement_covariance_xy[1][1] if measurement_covariance_xy is not None else None,
        ),
        dtype=float,
    )
    return KalmanModel(
        name=name,
        f=_to_list(f),
        h=_to_list(h),
        q=_to_list(q),
        r=_to_list(r),
        state_labels=("x", "y", "vx", "vy"),
        measurement_labels=("x", "y"),
        process_noise_status=status,
        process_noise_provenance=(
            "CV white-acceleration spectral approximation. Candidate value pending hardware trajectory validation."
        ),
        measurement_noise_status=status,
        measurement_noise_provenance=measurement_r_provenance(measurement_covariance_xy),
    )


def ca_position_model(
    dt: float,
    jerk_std_mps3: float,
    measurement_std_m: float,
    name: str = "ca",
    status: str = CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
    measurement_covariance_xy: Iterable[Iterable[float]] | None = None,
) -> KalmanModel:
    """Create a CA position-measurement KF model for [x, y, vx, vy, ax, ay]."""
    _require_positive("dt", dt)
    _require_positive("jerk_std_mps3", jerk_std_mps3)
    _require_positive("measurement_std_m", measurement_std_m)
    f = model_defs.ca_state_transition(dt)
    h = _position_h(6)
    q = _ca_white_jerk_q(dt, jerk_std_mps3)
    r = np.asarray(
        build_measurement_r_xy(
            measurement_std_m,
            measurement_covariance_xy[0][0] if measurement_covariance_xy is not None else None,
            measurement_covariance_xy[0][1] if measurement_covariance_xy is not None else 0.0,
            measurement_covariance_xy[1][1] if measurement_covariance_xy is not None else None,
        ),
        dtype=float,
    )
    return KalmanModel(
        name=name,
        f=_to_list(f),
        h=_to_list(h),
        q=_to_list(q),
        r=_to_list(r),
        state_labels=("x", "y", "vx", "vy", "ax", "ay"),
        measurement_labels=("x", "y"),
        process_noise_status=status,
        process_noise_provenance=(
            "CA white-jerk spectral approximation. Candidate value pending hardware maneuver validation."
        ),
        measurement_noise_status=status,
        measurement_noise_provenance=measurement_r_provenance(measurement_covariance_xy),
    )


def run_mode_matched_self_check(
    model: KalmanModel,
    truth_x0: Iterable[float],
    estimate_x0: Iterable[float],
    p0: np.ndarray,
    trials: int = 300,
    steps: int = 80,
    burn_in_steps: int = 20,
    seed: int = 0,
) -> ModeSelfCheckResult:
    """Monte Carlo convergence and marginal 2-sigma coverage check."""
    if trials <= 0 or steps <= 0 or burn_in_steps < 0 or burn_in_steps >= steps:
        raise ValueError("invalid self-check trial/step counts")

    rng = np.random.default_rng(seed)
    f = model.f_matrix()
    h = model.h_matrix()
    q = model.q_matrix()
    r = model.r_matrix()
    truth_initial = _col("truth_x0", truth_x0)
    estimate_initial = _col("estimate_x0", estimate_x0)
    final_errors = []
    coverage_hits = 0
    coverage_count = 0

    for _ in range(trials):
        truth = truth_initial.copy()
        filt = ModeMatchedKalmanFilter(model, estimate_initial[:, 0], p0)
        for k in range(steps):
            truth = f @ truth + _sample_noise(rng, q)
            measurement = h @ truth + _sample_noise(rng, r)
            estimate, _diagnostics = filt.step(measurement[:, 0])
            err = np.asarray(estimate.x, dtype=float).reshape(-1, 1) - truth
            if k >= burn_in_steps:
                std = np.sqrt(np.maximum(np.diag(np.asarray(estimate.p, dtype=float)), 0.0)).reshape(-1, 1)
                coverage_hits += int(np.sum(np.abs(err) <= 2.0 * std))
                coverage_count += int(err.shape[0])
        final_errors.append((np.asarray(filt.estimate().x, dtype=float).reshape(-1, 1) - truth)[:, 0])

    errors = np.asarray(final_errors, dtype=float)
    position_rmse = _rmse(errors[:, [0, 1]])
    velocity_rmse = _rmse(errors[:, [2, 3]])
    acceleration_rmse = _rmse(errors[:, [4, 5]]) if errors.shape[1] >= 6 else None
    return ModeSelfCheckResult(
        model_name=model.name,
        trials=int(trials),
        steps=int(steps),
        burn_in_steps=int(burn_in_steps),
        final_position_rmse_m=float(position_rmse),
        final_velocity_rmse_mps=float(velocity_rmse),
        final_acceleration_rmse_mps2=None if acceleration_rmse is None else float(acceleration_rmse),
        two_sigma_coverage_fraction=float(coverage_hits / coverage_count),
        expected_two_sigma_fraction=0.9545,
        coverage_sample_count=int(coverage_count),
        measurement_assumption_label=model.measurement_assumption_label,
        covariance_validity_status=model.covariance_validity_status,
    )


def _cv_white_acceleration_q(dt: float, acceleration_std_mps2: float) -> np.ndarray:
    q1 = acceleration_std_mps2**2 * np.array(
        [[dt**4 / 4.0, dt**3 / 2.0], [dt**3 / 2.0, dt**2]],
        dtype=float,
    )
    return _interleaved_block_diag(q1, state_dim=4)


def _ca_white_jerk_q(dt: float, jerk_std_mps3: float) -> np.ndarray:
    q1 = jerk_std_mps3**2 * np.array(
        [
            [dt**6 / 36.0, dt**5 / 12.0, dt**4 / 6.0],
            [dt**5 / 12.0, dt**4 / 4.0, dt**3 / 2.0],
            [dt**4 / 6.0, dt**3 / 2.0, dt**2],
        ],
        dtype=float,
    )
    return _interleaved_block_diag(q1, state_dim=6)


def _interleaved_block_diag(axis_q: np.ndarray, state_dim: int) -> np.ndarray:
    q = np.zeros((state_dim, state_dim), dtype=float)
    axis_count = 2
    per_axis = state_dim // axis_count
    for axis in range(axis_count):
        indices = [axis + axis_count * k for k in range(per_axis)]
        for row_i, row in enumerate(indices):
            for col_i, col in enumerate(indices):
                q[row, col] = axis_q[row_i, col_i]
    return q


def _position_h(state_dim: int) -> np.ndarray:
    try:
        return model_defs.position_measurement_matrix(state_dim)
    except TypeError:
        if state_dim == 4:
            return model_defs.position_measurement_matrix()
        raise


def _sample_noise(rng: np.random.Generator, covariance: np.ndarray) -> np.ndarray:
    if np.allclose(covariance, 0.0):
        return np.zeros((covariance.shape[0], 1), dtype=float)
    sample = rng.multivariate_normal(np.zeros(covariance.shape[0]), covariance, check_valid="ignore")
    return sample.reshape(-1, 1)


def _gaussian_likelihood(innovation: np.ndarray, s: np.ndarray) -> float:
    det_s = float(np.linalg.det(s))
    if det_s <= 0.0 or not math.isfinite(det_s):
        return 0.0
    inv_s = np.linalg.inv(s)
    exponent = float(-0.5 * (innovation.T @ inv_s @ innovation)[0, 0])
    norm = 1.0 / math.sqrt((2.0 * math.pi) ** innovation.shape[0] * det_s)
    return float(norm * math.exp(max(exponent, -80.0)))


def _matrix(name: str, value: Iterable[Iterable[float]] | np.ndarray) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be a 2D matrix")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _col(name: str, values: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float).reshape(-1, 1)
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _require_positive(name: str, value: float) -> None:
    if value <= 0.0 or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and positive")


def _require_symmetric_psd(name: str, matrix: np.ndarray) -> None:
    if not np.allclose(matrix, matrix.T, atol=1e-10):
        raise ValueError(f"{name} must be symmetric")
    if np.min(np.linalg.eigvalsh(matrix)) < -1e-10:
        raise ValueError(f"{name} must be positive semidefinite")


def _symmetrize(p: np.ndarray) -> np.ndarray:
    return 0.5 * (p + p.T)


def _to_list(matrix: np.ndarray) -> list[list[float]]:
    return [[float(v) for v in row] for row in np.asarray(matrix, dtype=float)]


def _vector(col: np.ndarray) -> list[float]:
    return [float(v) for v in np.asarray(col, dtype=float).reshape(-1)]


def _rmse(errors: np.ndarray) -> float:
    return float(math.sqrt(float(np.mean(np.asarray(errors, dtype=float) ** 2))))
