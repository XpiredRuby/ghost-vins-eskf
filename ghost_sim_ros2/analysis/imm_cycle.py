"""Full five-step IMM cycle assembly for GHOST formal IMM step 4d.

This module assembles the validated checkpoints from steps 4a-4c:

1. predict mode probabilities
2. compute mixed initial conditions
3. run each mode-matched Kalman filter
4. update mode probabilities from Gaussian likelihoods
5. combine mode-conditioned state/covariance into one IMM output

It remains a pure Python/NumPy analysis module. It does not modify the live
heuristic hypothesis bank in ``mh_tracker.py`` or ``stationary_gate.py``.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np

from analysis.imm_mixing import (
    GAUSSIAN_LIKELIHOOD_FORMULA,
    MixingModeFilterBank,
)
from analysis.mode_matched_kf import (
    CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
    INVALID_IF_NOISE_IS_COLORED,
    KalmanEstimate,
    ModeMatchedKalmanFilter,
    cv_position_model,
)

FORMAL_IMM_5_STEP_CYCLE = "FORMAL_IMM_5_STEP_CYCLE"
ASSUMES_WHITE_GAUSSIAN_RESIDUALS = "ASSUMES_WHITE_GAUSSIAN_RESIDUALS"
COLORED_NOISE_MISCALIBRATION_WARNING = (
    "White-noise Kalman covariance is expected to be miscalibrated under colored/AR(1) residuals; "
    "treat combined covariance as diagnostic only unless residual whiteness is verified."
)
COMBINED_COVARIANCE_CAVEAT = (
    "Combined IMM covariance is a posterior mode-probability-weighted blend of mode covariances. "
    "Each mode update assumes independent white Gaussian residuals and remains INVALID_IF_NOISE_IS_COLORED."
)
AR1_DRIFT_GENERATOR_PROVENANCE = (
    "Matches ghost_software_regime.py colored_ar1 pattern: rho=0.985, process_std=0.0012 m, "
    "white_std=0.0025 m."
)
BURN_IN_RATIONALE = (
    "Coverage metrics exclude the first 20 steps, equal to 1.0 s at dt=0.05 s. "
    "That removes the deliberately broad/candidate initial-P transient before using covariance calibration metrics; "
    "maneuver mode-switch lag is reported from the switch instant instead of burn-in filtered."
)
NONMIXED_PROBABILITY_COLLAPSE_NOTE = (
    "In the 4c non-mixed reference, the maneuver probability can collapse after the early acceleration response because "
    "the stale maneuver filter is never reinitialized from other modes; once the trajectory becomes locally smoother, "
    "the likelihood ratio can swing back toward the smooth model."
)
P0_STRESS_CASE_CAVEAT = (
    "The 4c mixed-vs-non-mixed stress validation intentionally used tight P0 and a stale/wrong inactive maneuver state; "
    "its large improvement factor is a mechanism-isolation stress result, not hardware tuning evidence."
)
TRANSITION_MATRIX_INVARIANTS = (
    "transition must be square",
    "transition rows must sum to 1",
    "transition probabilities must be finite and nonnegative",
    "transition shape must match filter count",
)


@dataclass(frozen=True)
class ImmCombinedEstimate:
    x: list[float]
    p: list[list[float]]
    std: list[float]
    mode_probabilities: dict[str, float]
    estimator_status: str = FORMAL_IMM_5_STEP_CYCLE
    measurement_assumption_label: str = ASSUMES_WHITE_GAUSSIAN_RESIDUALS
    covariance_validity_status: str = INVALID_IF_NOISE_IS_COLORED
    covariance_caveat: str = COMBINED_COVARIANCE_CAVEAT


@dataclass(frozen=True)
class ImmCycleStep:
    step_index: int
    combined_estimate: ImmCombinedEstimate
    mode_probabilities: dict[str, float]
    predicted_mode_probabilities: dict[str, float]
    mixing_probabilities: list[list[float]]
    likelihoods: dict[str, float]
    mode_estimates: dict[str, KalmanEstimate]
    estimator_status: str = FORMAL_IMM_5_STEP_CYCLE
    cycle_order: tuple[str, ...] = (
        "predict_mode_probabilities",
        "mix_initial_conditions",
        "mode_matched_filter_predict_update",
        "gaussian_likelihood_mode_probability_update",
        "combine_mode_conditioned_output",
    )
    likelihood_formula: str = GAUSSIAN_LIKELIHOOD_FORMULA
    covariance_validity_status: str = INVALID_IF_NOISE_IS_COLORED


@dataclass(frozen=True)
class ImmScenarioValidation:
    scenario: str
    steps: int
    burn_in_steps: int
    position_rmse_m: float
    final_position_error_m: float
    two_sigma_coverage_fraction: float
    expected_two_sigma_fraction: float
    active_mode_accuracy_fraction: float | None
    mode_probability_lag_steps: int | None
    covariance_validity_status: str
    colored_noise_miscalibration_warning: str | None
    samples: list[dict[str, float]]

    def to_dict(self) -> dict:
        return asdict(self)


class InteractingMultipleModelEstimator:
    """Formal IMM cycle wrapper around the validated Step 4c mixed bank."""

    def __init__(self, mixed_bank: MixingModeFilterBank):
        self.mixed_bank = mixed_bank
        self.mode_names = list(mixed_bank.mode_names)

    def step(self, measurement: Iterable[float] | None) -> ImmCycleStep:
        mixed_step = self.mixed_bank.step(measurement)
        combined = combine_mode_estimates(mixed_step.estimates, mixed_step.mode_probabilities, self.mode_names)
        return ImmCycleStep(
            step_index=mixed_step.step_index,
            combined_estimate=combined,
            mode_probabilities=mixed_step.mode_probabilities,
            predicted_mode_probabilities=mixed_step.predicted_mode_probabilities,
            mixing_probabilities=mixed_step.mixing_probabilities,
            likelihoods=mixed_step.likelihoods,
            mode_estimates=mixed_step.estimates,
        )


def combine_mode_estimates(
    estimates: dict[str, KalmanEstimate],
    mode_probabilities: dict[str, float],
    mode_order: Iterable[str],
) -> ImmCombinedEstimate:
    """Combine mode-conditioned estimates with posterior mode probabilities."""
    names = list(mode_order)
    if not names:
        raise ValueError("at least one mode is required")
    probabilities = np.asarray([mode_probabilities[name] for name in names], dtype=float)
    if np.any(probabilities < 0.0) or not np.isfinite(probabilities).all() or float(np.sum(probabilities)) <= 0.0:
        raise ValueError("mode probabilities must be finite, nonnegative, and sum positive")
    probabilities = probabilities / float(np.sum(probabilities))
    states = [np.asarray(estimates[name].x, dtype=float).reshape(-1, 1) for name in names]
    covariances = [np.asarray(estimates[name].p, dtype=float) for name in names]
    state_dim = states[0].shape[0]
    if any(x.shape != (state_dim, 1) for x in states):
        raise ValueError("all mode states must have the same dimension")
    if any(p.shape != (state_dim, state_dim) for p in covariances):
        raise ValueError("all mode covariances must have state_dim x state_dim shape")

    x_combined = sum(probabilities[i] * states[i] for i in range(len(names)))
    p_combined = np.zeros((state_dim, state_dim), dtype=float)
    for i in range(len(names)):
        dx = states[i] - x_combined
        p_combined += probabilities[i] * (covariances[i] + dx @ dx.T)
    p_combined = _symmetrize(p_combined)
    diag = np.clip(np.diag(p_combined), 0.0, None)
    return ImmCombinedEstimate(
        x=_vector(x_combined),
        p=_to_list(p_combined),
        std=[float(math.sqrt(v)) for v in diag],
        mode_probabilities={name: float(prob) for name, prob in zip(names, probabilities)},
    )


def make_smooth_maneuver_cv_imm(
    dt: float = 0.05,
    measurement_std_m: float = 0.02,
    measurement_covariance_xy: Iterable[Iterable[float]] | None = None,
    smooth_acceleration_std_mps2: float = 0.015,
    maneuver_acceleration_std_mps2: float = 0.75,
    transition: np.ndarray | None = None,
    initial_mode_probabilities: Iterable[float] = (0.8, 0.2),
    initial_state: Iterable[float] = (0.0, 0.0, 0.28, 0.0),
    p0_diag: Iterable[float] = (0.04, 0.04, 0.25, 0.25),
) -> InteractingMultipleModelEstimator:
    """Create the default same-state CV IMM used by Step 4d validation."""
    smooth = cv_position_model(
        dt,
        smooth_acceleration_std_mps2,
        measurement_std_m,
        name="smooth_cv",
        measurement_covariance_xy=measurement_covariance_xy,
        status=CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
    )
    maneuver = cv_position_model(
        dt,
        maneuver_acceleration_std_mps2,
        measurement_std_m,
        name="maneuver_cv",
        measurement_covariance_xy=measurement_covariance_xy,
        status=CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
    )
    p0 = np.diag(np.asarray(list(p0_diag), dtype=float))
    filters = [
        ModeMatchedKalmanFilter(smooth, initial_state, p0),
        ModeMatchedKalmanFilter(maneuver, initial_state, p0),
    ]
    pi = np.array([[0.97, 0.03], [0.03, 0.97]], dtype=float) if transition is None else transition
    return InteractingMultipleModelEstimator(MixingModeFilterBank(filters, pi, initial_mode_probabilities))


def validate_white_noise_case() -> ImmScenarioValidation:
    """Validate the assembled IMM on a white-noise-only constant-velocity case."""
    dt = 0.05
    steps = 120
    burn_in = 20
    measurement_std = 0.02
    rng = np.random.default_rng(101)
    truth = np.array([0.0, 0.0, 0.28, -0.04], dtype=float)
    imm = make_smooth_maneuver_cv_imm(dt=dt, measurement_std_m=measurement_std, initial_state=[0.0, 0.0, 0.20, 0.0])
    errors, hits, count, samples = _run_case(
        imm,
        truth,
        steps,
        burn_in,
        dt,
        lambda _k, _truth: (0.0, 0.0),
        lambda: rng.normal(0.0, measurement_std, size=2),
    )
    return _validation_result("white_noise_cv", steps, burn_in, errors, hits, count, None, None, None, samples)


def validate_colored_ar1_case() -> ImmScenarioValidation:
    """Validate the assembled IMM under synthetic AR(1) colored measurement drift."""
    dt = 0.05
    steps = 160
    burn_in = 20
    rng = random.Random(202)
    drift = [0.0, 0.0]
    truth = np.array([0.0, 0.0, 0.18, 0.0], dtype=float)
    imm = make_smooth_maneuver_cv_imm(dt=dt, measurement_std_m=0.004, initial_state=[0.0, 0.0, 0.12, 0.0])

    def colored_noise() -> np.ndarray:
        rho = 0.985
        process_std = 0.0012
        white_std = 0.0025
        drift[0] = rho * drift[0] + rng.gauss(0.0, process_std)
        drift[1] = rho * drift[1] + rng.gauss(0.0, process_std)
        return np.array(
            [
                drift[0] + rng.gauss(0.0, white_std),
                drift[1] + rng.gauss(0.0, white_std),
            ],
            dtype=float,
        )

    errors, hits, count, samples = _run_case(imm, truth, steps, burn_in, dt, lambda _k, _truth: (0.0, 0.0), colored_noise)
    return _validation_result(
        "colored_ar1_cv",
        steps,
        burn_in,
        errors,
        hits,
        count,
        None,
        None,
        COLORED_NOISE_MISCALIBRATION_WARNING,
        samples,
    )


def validate_maneuver_switch_case() -> ImmScenarioValidation:
    """Validate mode-probability tracking on a smooth -> maneuver -> smooth case."""
    dt = 0.05
    steps = 140
    burn_in = 20
    switch_step = 45
    maneuver_end = 85
    measurement_std = 0.02
    rng = np.random.default_rng(303)
    truth = np.array([0.0, 0.0, 0.25, 0.0], dtype=float)
    imm = make_smooth_maneuver_cv_imm(dt=dt, measurement_std_m=measurement_std, initial_state=[0.0, 0.0, 0.20, 0.0])
    active_modes: list[str] = []
    probs: list[dict[str, float]] = []

    def acceleration(k: int, _truth: np.ndarray) -> tuple[float, float]:
        return (2.5, 0.0) if switch_step <= k < maneuver_end else (0.0, 0.0)

    def white_noise() -> np.ndarray:
        return rng.normal(0.0, measurement_std, size=2)

    errors, hits, count, samples = _run_case(
        imm,
        truth,
        steps,
        burn_in,
        dt,
        acceleration,
        white_noise,
        active_mode_fn=lambda k: "maneuver_cv" if switch_step <= k < maneuver_end else "smooth_cv",
        active_modes=active_modes,
        probabilities=probs,
    )
    lag = _first_threshold_lag(probs, switch_step, maneuver_end, "maneuver_cv", 0.55)
    accuracy = _mode_accuracy(active_modes, probs)
    return _validation_result("maneuver_switch_cv", steps, burn_in, errors, hits, count, accuracy, lag, None, samples)


def run_step_4d_validation_suite() -> list[ImmScenarioValidation]:
    """Return all required Step 4d synthetic validation cases."""
    return [validate_white_noise_case(), validate_colored_ar1_case(), validate_maneuver_switch_case()]


def _run_case(
    imm: InteractingMultipleModelEstimator,
    truth: np.ndarray,
    steps: int,
    burn_in: int,
    dt: float,
    acceleration_fn,
    noise_fn,
    active_mode_fn=None,
    active_modes: list[str] | None = None,
    probabilities: list[dict[str, float]] | None = None,
) -> tuple[list[float], int, int, list[dict[str, float]]]:
    errors: list[float] = []
    hits = 0
    count = 0
    samples: list[dict[str, float]] = []
    for k in range(steps):
        ax, ay = acceleration_fn(k, truth)
        truth[0] += truth[2] * dt + 0.5 * ax * dt * dt
        truth[1] += truth[3] * dt + 0.5 * ay * dt * dt
        truth[2] += ax * dt
        truth[3] += ay * dt
        measurement = truth[:2] + noise_fn()
        step = imm.step(measurement)
        est = np.asarray(step.combined_estimate.x, dtype=float)
        p = np.asarray(step.combined_estimate.p, dtype=float)
        err_xy = est[:2] - truth[:2]
        errors.append(float(np.linalg.norm(err_xy)))
        if k >= burn_in:
            std = np.sqrt(np.maximum(np.diag(p)[:2], 0.0))
            hits += int(np.sum(np.abs(err_xy) <= 2.0 * std))
            count += 2
        if active_mode_fn is not None and active_modes is not None and probabilities is not None:
            active_modes.append(active_mode_fn(k))
            probabilities.append(step.mode_probabilities)
        if k in {0, 1, 2, burn_in, steps // 2, steps - 1}:
            samples.append(
                {
                    "step": float(k),
                    "truth_x_m": float(truth[0]),
                    "estimate_x_m": float(est[0]),
                    "position_error_m": float(errors[-1]),
                    "smooth_cv_probability": float(step.mode_probabilities.get("smooth_cv", math.nan)),
                    "maneuver_cv_probability": float(step.mode_probabilities.get("maneuver_cv", math.nan)),
                }
            )
    return errors, hits, count, samples


def _validation_result(
    scenario: str,
    steps: int,
    burn_in: int,
    errors: list[float],
    coverage_hits: int,
    coverage_count: int,
    active_mode_accuracy: float | None,
    lag: int | None,
    colored_warning: str | None,
    samples: list[dict[str, float]],
) -> ImmScenarioValidation:
    arr = np.asarray(errors[burn_in:], dtype=float)
    return ImmScenarioValidation(
        scenario=scenario,
        steps=int(steps),
        burn_in_steps=int(burn_in),
        position_rmse_m=float(math.sqrt(float(np.mean(arr * arr)))),
        final_position_error_m=float(errors[-1]),
        two_sigma_coverage_fraction=float(coverage_hits / coverage_count),
        expected_two_sigma_fraction=0.9545,
        active_mode_accuracy_fraction=active_mode_accuracy,
        mode_probability_lag_steps=lag,
        covariance_validity_status=INVALID_IF_NOISE_IS_COLORED,
        colored_noise_miscalibration_warning=colored_warning,
        samples=samples,
    )


def _first_threshold_lag(
    probabilities: list[dict[str, float]],
    start: int,
    stop: int,
    mode: str,
    threshold: float,
) -> int:
    for k in range(start, min(stop, len(probabilities))):
        if probabilities[k][mode] >= threshold:
            return int(k - start)
    return int(stop - start)


def _mode_accuracy(active_modes: list[str], probabilities: list[dict[str, float]]) -> float:
    correct = 0
    for active, prob in zip(active_modes, probabilities):
        predicted = max(prob, key=prob.get)
        correct += int(predicted == active)
    return float(correct / len(active_modes))


def _symmetrize(p: np.ndarray) -> np.ndarray:
    return 0.5 * (p + p.T)


def _to_list(matrix: np.ndarray) -> list[list[float]]:
    return [[float(v) for v in row] for row in np.asarray(matrix, dtype=float)]


def _vector(col: np.ndarray) -> list[float]:
    return [float(v) for v in np.asarray(col, dtype=float).reshape(-1)]
