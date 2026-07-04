"""Mode-probability-weighted parallel filters for GHOST IMM step 4b.

This module is an intermediate validation checkpoint. It predicts and updates
mode probabilities around the independent Step 4a Kalman filters, but it does
not implement mixed initial conditions. Therefore it is not yet an IMM.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np

from analysis.mode_matched_kf import (
    INVALID_IF_NOISE_IS_COLORED,
    KalmanEstimate,
    ModeMatchedKalmanFilter,
)

MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM = "MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM"


@dataclass(frozen=True)
class ModeProbabilityStep:
    step_index: int
    mode_probabilities: dict[str, float]
    predicted_mode_probabilities: dict[str, float]
    likelihoods: dict[str, float]
    estimates: dict[str, KalmanEstimate]
    estimator_status: str = MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM
    covariance_validity_status: str = INVALID_IF_NOISE_IS_COLORED


@dataclass(frozen=True)
class ModeProbabilitySelfCheck:
    true_mode: str
    steps: int
    initial_probability: float
    final_probability: float
    competing_final_probabilities: dict[str, float]
    trajectory_samples: list[dict[str, float]]
    estimator_status: str = MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM

    def to_dict(self) -> dict:
        return asdict(self)


class ModeProbabilityFilterBank:
    """Parallel mode-matched filters with probability prediction/update only.

    This is deliberately not an IMM: mode probabilities are updated from each
    filter's likelihood, but each filter continues from its own state history.
    No mixed initial condition is computed.
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

    def step(self, measurement: Iterable[float] | None) -> ModeProbabilityStep:
        predicted = predict_mode_probabilities(self.mode_probabilities, self.transition)
        estimates: dict[str, KalmanEstimate] = {}
        likelihoods = np.ones(len(self.filters), dtype=float)

        for i, filt in enumerate(self.filters):
            estimate, diagnostics = filt.step(measurement)
            estimates[filt.model.name] = estimate
            if diagnostics is not None:
                likelihoods[i] = diagnostics.likelihood

        if measurement is None:
            posterior = predicted
        else:
            posterior = update_mode_probabilities_from_likelihoods(predicted, likelihoods)
        self.mode_probabilities = posterior
        result = ModeProbabilityStep(
            step_index=self.step_index,
            mode_probabilities=_named(self.mode_names, posterior),
            predicted_mode_probabilities=_named(self.mode_names, predicted),
            likelihoods=_named(self.mode_names, likelihoods),
            estimates=estimates,
        )
        self.step_index += 1
        return result


def predict_mode_probabilities(mode_probabilities: Iterable[float], transition: np.ndarray) -> np.ndarray:
    """Predict mode probabilities with Pi[i,j] = P(mode_j at k | mode_i at k-1)."""
    pi = _transition_matrix(transition)
    mu = _probability_vector("mode_probabilities", mode_probabilities, pi.shape[0])
    return _normalize(mu @ pi)


def update_mode_probabilities_from_likelihoods(predicted: Iterable[float], likelihoods: Iterable[float]) -> np.ndarray:
    """Apply Gaussian-likelihood mode probability update."""
    mu_pred = _probability_vector("predicted", predicted)
    ll = np.asarray(list(likelihoods), dtype=float)
    if ll.shape != mu_pred.shape:
        raise ValueError("likelihoods must match mode probability length")
    if np.any(ll < 0.0) or not np.isfinite(ll).all():
        raise ValueError("likelihoods must be finite and nonnegative")
    weights = mu_pred * ll
    if float(np.sum(weights)) <= 0.0:
        return np.ones_like(mu_pred) / len(mu_pred)
    return _normalize(weights)


def run_unambiguous_cv_probability_self_check(
    bank: ModeProbabilityFilterBank,
    measurement_std_m: float,
    steps: int = 50,
    seed: int = 7,
    true_velocity_mps: tuple[float, float] = (0.35, 0.0),
    true_mode: str = "smooth_cv",
) -> ModeProbabilitySelfCheck:
    """Run an obviously constant-velocity scenario for Step 4b validation."""
    if steps <= 0:
        raise ValueError("steps must be positive")
    if measurement_std_m <= 0.0:
        raise ValueError("measurement_std_m must be positive")
    if true_mode not in bank.mode_names:
        raise ValueError("true_mode must be one of the bank modes")

    rng = np.random.default_rng(seed)
    dt = _infer_dt_from_first_filter(bank)
    truth = np.array([0.0, 0.0, true_velocity_mps[0], true_velocity_mps[1]], dtype=float)
    samples: list[dict[str, float]] = []
    initial_probability = float(bank.mode_probabilities[bank.mode_names.index(true_mode)])

    for k in range(steps):
        truth[0] += truth[2] * dt
        truth[1] += truth[3] * dt
        measurement = truth[:2] + rng.normal(0.0, measurement_std_m, size=2)
        result = bank.step(measurement)
        if k in {0, 1, 2, 4, 9, 19, steps - 1}:
            row = {"step": float(k)}
            row.update(result.mode_probabilities)
            samples.append(row)

    final_prob = float(bank.mode_probabilities[bank.mode_names.index(true_mode)])
    competitors = {
        name: float(prob)
        for name, prob in zip(bank.mode_names, bank.mode_probabilities)
        if name != true_mode
    }
    return ModeProbabilitySelfCheck(
        true_mode=true_mode,
        steps=int(steps),
        initial_probability=initial_probability,
        final_probability=final_prob,
        competing_final_probabilities=competitors,
        trajectory_samples=samples,
    )


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
    return _normalize(vector)


def _normalize(values: np.ndarray) -> np.ndarray:
    total = float(np.sum(values))
    if total <= 0.0:
        raise ValueError("cannot normalize nonpositive probabilities")
    return np.asarray(values, dtype=float) / total


def _named(names: list[str], values: Iterable[float]) -> dict[str, float]:
    return {name: float(value) for name, value in zip(names, values)}


def _infer_dt_from_first_filter(bank: ModeProbabilityFilterBank) -> float:
    f = bank.filters[0].f
    if f.shape[0] < 4:
        raise ValueError("self-check expects a CV-like state with velocity")
    return float(f[0, 2])
