"""IMM mixing checkpoint for GHOST formal IMM step 4c.

This module implements the "interacting" part of IMM: destination-conditioned
mixing probabilities and mixed initial state/covariance for each mode. It builds
on the Step 4a Kalman filters and Step 4b probability update, but still avoids
claiming the final assembled IMM output path from Step 4d.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np

from analysis.mode_matched_kf import (
    INVALID_IF_NOISE_IS_COLORED,
    KalmanEstimate,
    ModeMatchedKalmanFilter,
)
from analysis.mode_probability_bank import (
    ModeProbabilityFilterBank,
    predict_mode_probabilities,
    update_mode_probabilities_from_likelihoods,
)

IMM_MIXING_STEP_IMPLEMENTED_NO_FINAL_COMBINED_OUTPUT = "IMM_MIXING_STEP_IMPLEMENTED_NO_FINAL_COMBINED_OUTPUT"
GAUSSIAN_LIKELIHOOD_FORMULA = "N(nu; 0, S) = exp(-0.5*nu.T@inv(S)@nu) / sqrt((2*pi)^m * det(S))"


@dataclass(frozen=True)
class MixedModeStep:
    step_index: int
    mode_probabilities: dict[str, float]
    predicted_mode_probabilities: dict[str, float]
    mixing_probabilities: list[list[float]]
    likelihoods: dict[str, float]
    estimates: dict[str, KalmanEstimate]
    estimator_status: str = IMM_MIXING_STEP_IMPLEMENTED_NO_FINAL_COMBINED_OUTPUT
    covariance_validity_status: str = INVALID_IF_NOISE_IS_COLORED
    likelihood_formula: str = GAUSSIAN_LIKELIHOOD_FORMULA


@dataclass(frozen=True)
class MixingComparisonResult:
    switch_step: int
    steps: int
    mixed_peak_post_switch_position_error_m: float
    nonmixed_peak_post_switch_position_error_m: float
    mixed_mean_post_switch_position_error_m: float
    nonmixed_mean_post_switch_position_error_m: float
    mixed_maneuver_probability_lag_steps: int
    nonmixed_maneuver_probability_lag_steps: int
    lag_threshold: float
    samples: list[dict[str, float]]
    estimator_status: str = IMM_MIXING_STEP_IMPLEMENTED_NO_FINAL_COMBINED_OUTPUT

    def to_dict(self) -> dict:
        return asdict(self)


class MixingModeFilterBank:
    """Mode probability bank with IMM mixed initial conditions.

    For destination mode j, this computes:

    c_j = sum_i mu_i * Pi[i,j]
    mu_i|j = mu_i * Pi[i,j] / c_j
    x0_j = sum_i mu_i|j * x_i
    P0_j = sum_i mu_i|j * (P_i + (x_i - x0_j)(x_i - x0_j)^T)

    The mixed (x0_j, P0_j) is assigned to filter j before its standard
    predict/update step. Formal final combined IMM output is left to Step 4d.
    """

    def __init__(
        self,
        filters: Iterable[ModeMatchedKalmanFilter],
        transition: np.ndarray,
        mode_probabilities: Iterable[float] | None = None,
    ):
        self.filters = list(filters)
        if not self.filters:
            raise ValueError("at least one filter is required")
        self.mode_names = [f.model.name for f in self.filters]
        self.transition = _transition_matrix(transition, len(self.filters))
        self.mode_probabilities = _probability_vector(
            "mode_probabilities",
            np.ones(len(self.filters), dtype=float) / len(self.filters) if mode_probabilities is None else mode_probabilities,
            len(self.filters),
        )
        self.step_index = 0
        self._validate_same_state_dimension()

    def step(self, measurement: Iterable[float] | None) -> MixedModeStep:
        prior_states = [f.x.copy() for f in self.filters]
        prior_covariances = [f.p.copy() for f in self.filters]
        predicted = predict_mode_probabilities(self.mode_probabilities, self.transition)
        mixing = mixing_probabilities(self.mode_probabilities, self.transition)
        mixed_states, mixed_covariances = mix_state_estimates(prior_states, prior_covariances, mixing)

        estimates: dict[str, KalmanEstimate] = {}
        likelihoods = np.ones(len(self.filters), dtype=float)
        for i, filt in enumerate(self.filters):
            filt.x = mixed_states[i]
            filt.p = mixed_covariances[i]
            estimate, diagnostics = filt.step(measurement)
            estimates[filt.model.name] = estimate
            if diagnostics is not None:
                likelihoods[i] = diagnostics.likelihood

        posterior = predicted if measurement is None else update_mode_probabilities_from_likelihoods(predicted, likelihoods)
        self.mode_probabilities = posterior
        result = MixedModeStep(
            step_index=self.step_index,
            mode_probabilities=_named(self.mode_names, posterior),
            predicted_mode_probabilities=_named(self.mode_names, predicted),
            mixing_probabilities=_to_list(mixing),
            likelihoods=_named(self.mode_names, likelihoods),
            estimates=estimates,
        )
        self.step_index += 1
        return result

    def _validate_same_state_dimension(self) -> None:
        dim = self.filters[0].x.shape[0]
        for filt in self.filters:
            if filt.x.shape[0] != dim:
                raise ValueError("all mixed filters must have the same state dimension")


def mixing_probabilities(mode_probabilities: Iterable[float], transition: np.ndarray) -> np.ndarray:
    """Return omega[i,j] = P(previous mode i | destination mode j)."""
    pi = _transition_matrix(transition)
    mu = _probability_vector("mode_probabilities", mode_probabilities, pi.shape[0])
    predicted = predict_mode_probabilities(mu, pi)
    omega = np.zeros_like(pi, dtype=float)
    for j in range(pi.shape[1]):
        if predicted[j] <= 0.0:
            raise ValueError("predicted mode probability must be positive for mixing")
        omega[:, j] = mu * pi[:, j] / predicted[j]
    return omega


def mix_state_estimates(
    states: Iterable[np.ndarray],
    covariances: Iterable[np.ndarray],
    omega: np.ndarray,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Mix prior state/covariance estimates for each destination mode."""
    state_list = [_col("state", state) for state in states]
    covariance_list = [_matrix("covariance", cov) for cov in covariances]
    weights = _matrix("omega", omega)
    mode_count = len(state_list)
    if weights.shape != (mode_count, mode_count):
        raise ValueError("omega must be mode_count x mode_count")
    if not np.allclose(np.sum(weights, axis=0), 1.0):
        raise ValueError("each omega destination column must sum to 1")

    mixed_states: list[np.ndarray] = []
    mixed_covariances: list[np.ndarray] = []
    for j in range(mode_count):
        x_mix = sum(weights[i, j] * state_list[i] for i in range(mode_count))
        p_mix = np.zeros_like(covariance_list[0])
        for i in range(mode_count):
            dx = state_list[i] - x_mix
            p_mix += weights[i, j] * (covariance_list[i] + dx @ dx.T)
        mixed_states.append(x_mix)
        mixed_covariances.append(_symmetrize(p_mix))
    return mixed_states, mixed_covariances


def compare_mixed_vs_nonmixed_on_switch(
    mixed_bank: MixingModeFilterBank,
    nonmixed_bank: ModeProbabilityFilterBank,
    measurement_std_m: float,
    switch_step: int = 60,
    steps: int = 140,
    dt: float = 0.05,
    seed: int = 23,
    acceleration_mps2: float = 1.4,
    lag_threshold: float = 0.75,
) -> MixingComparisonResult:
    """Compare mixed and non-mixed banks on one deterministic mode switch."""
    if not (0 < switch_step < steps):
        raise ValueError("switch_step must be inside the run")
    if measurement_std_m <= 0.0 or dt <= 0.0:
        raise ValueError("measurement_std_m and dt must be positive")

    rng = np.random.default_rng(seed)
    truth = np.array([0.0, 0.0, 0.28, 0.0], dtype=float)
    mixed_errors: list[float] = []
    nonmixed_errors: list[float] = []
    mixed_probs: list[float] = []
    nonmixed_probs: list[float] = []
    samples: list[dict[str, float]] = []

    for k in range(steps):
        ax = acceleration_mps2 if k >= switch_step else 0.0
        truth[0] += truth[2] * dt + 0.5 * ax * dt * dt
        truth[2] += ax * dt
        measurement = truth[:2] + rng.normal(0.0, measurement_std_m, size=2)

        mixed_step = mixed_bank.step(measurement)
        nonmixed_step = nonmixed_bank.step(measurement)
        mixed_x = _weighted_state(mixed_step.estimates, mixed_step.mode_probabilities, mixed_bank.mode_names)
        nonmixed_x = _weighted_state(nonmixed_step.estimates, nonmixed_step.mode_probabilities, nonmixed_bank.mode_names)
        mixed_err = _position_error(mixed_x, truth)
        nonmixed_err = _position_error(nonmixed_x, truth)
        mixed_errors.append(mixed_err)
        nonmixed_errors.append(nonmixed_err)
        mixed_maneuver = mixed_step.mode_probabilities["maneuver_cv"]
        nonmixed_maneuver = nonmixed_step.mode_probabilities["maneuver_cv"]
        mixed_probs.append(mixed_maneuver)
        nonmixed_probs.append(nonmixed_maneuver)

        if k in {switch_step - 1, switch_step, switch_step + 2, switch_step + 5, switch_step + 10, steps - 1}:
            samples.append(
                {
                    "step": float(k),
                    "mixed_error_m": float(mixed_err),
                    "nonmixed_error_m": float(nonmixed_err),
                    "mixed_maneuver_probability": float(mixed_maneuver),
                    "nonmixed_maneuver_probability": float(nonmixed_maneuver),
                }
            )

    window = slice(switch_step, min(steps, switch_step + 40))
    mixed_post = np.asarray(mixed_errors[window], dtype=float)
    nonmixed_post = np.asarray(nonmixed_errors[window], dtype=float)
    return MixingComparisonResult(
        switch_step=int(switch_step),
        steps=int(steps),
        mixed_peak_post_switch_position_error_m=float(np.max(mixed_post)),
        nonmixed_peak_post_switch_position_error_m=float(np.max(nonmixed_post)),
        mixed_mean_post_switch_position_error_m=float(np.mean(mixed_post)),
        nonmixed_mean_post_switch_position_error_m=float(np.mean(nonmixed_post)),
        mixed_maneuver_probability_lag_steps=_first_crossing_lag(mixed_probs, switch_step, lag_threshold),
        nonmixed_maneuver_probability_lag_steps=_first_crossing_lag(nonmixed_probs, switch_step, lag_threshold),
        lag_threshold=float(lag_threshold),
        samples=samples,
    )


def _first_crossing_lag(values: list[float], switch_step: int, threshold: float) -> int:
    for k in range(switch_step, len(values)):
        if values[k] >= threshold:
            return int(k - switch_step)
    return int(len(values) - switch_step)


def _weighted_state(
    estimates: dict[str, KalmanEstimate],
    probabilities: dict[str, float],
    names: list[str],
) -> np.ndarray:
    state = None
    for name in names:
        x = np.asarray(estimates[name].x, dtype=float).reshape(-1, 1)
        state = probabilities[name] * x if state is None else state + probabilities[name] * x
    if state is None:
        raise ValueError("no estimates supplied")
    return state


def _position_error(estimate: np.ndarray, truth: np.ndarray) -> float:
    dx = estimate[0, 0] - truth[0]
    dy = estimate[1, 0] - truth[1]
    return float(math.sqrt(dx * dx + dy * dy))


def _transition_matrix(value: np.ndarray, expected_modes: int | None = None) -> np.ndarray:
    matrix = np.asarray(value, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("transition must be a square matrix")
    if expected_modes is not None and matrix.shape != (expected_modes, expected_modes):
        raise ValueError("transition shape must match filter count")
    if np.any(matrix < 0.0) or not np.isfinite(matrix).all():
        raise ValueError("transition probabilities must be finite and nonnegative")
    if not np.allclose(np.sum(matrix, axis=1), 1.0):
        raise ValueError("transition rows must sum to 1")
    return matrix


def _probability_vector(name: str, values: Iterable[float], expected_modes: int | None = None) -> np.ndarray:
    vector = np.asarray(list(values), dtype=float)
    if vector.ndim != 1:
        raise ValueError(f"{name} must be a vector")
    if expected_modes is not None and vector.shape != (expected_modes,):
        raise ValueError(f"{name} length must match mode count")
    if np.any(vector < 0.0) or not np.isfinite(vector).all() or float(np.sum(vector)) <= 0.0:
        raise ValueError(f"{name} must be finite, nonnegative, and sum positive")
    return vector / float(np.sum(vector))


def _matrix(name: str, value: np.ndarray) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be a 2D matrix")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _col(name: str, value: np.ndarray) -> np.ndarray:
    arr = np.asarray(value, dtype=float).reshape(-1, 1)
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _symmetrize(p: np.ndarray) -> np.ndarray:
    return 0.5 * (p + p.T)


def _named(names: list[str], values: Iterable[float]) -> dict[str, float]:
    return {name: float(value) for name, value in zip(names, values)}


def _to_list(matrix: np.ndarray) -> list[list[float]]:
    return [[float(v) for v in row] for row in np.asarray(matrix, dtype=float)]
