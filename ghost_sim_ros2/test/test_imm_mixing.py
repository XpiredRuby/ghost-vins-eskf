import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.imm_mixing import (  # noqa: E402
    GAUSSIAN_LIKELIHOOD_FORMULA,
    IMM_MIXING_STEP_IMPLEMENTED_NO_FINAL_COMBINED_OUTPUT,
    MixingModeFilterBank,
    compare_mixed_vs_nonmixed_on_switch,
    mix_state_estimates,
    mixing_probabilities,
)
from analysis.mode_matched_kf import ModeMatchedKalmanFilter, cv_position_model  # noqa: E402
from analysis.mode_probability_bank import ModeProbabilityFilterBank  # noqa: E402


def test_mixing_probabilities_match_hand_computable_case():
    transition = np.array([[0.9, 0.1], [0.2, 0.8]])
    omega = mixing_probabilities([0.6, 0.4], transition)

    assert np.allclose(omega[:, 0], [0.54 / 0.62, 0.08 / 0.62])
    assert np.allclose(omega[:, 1], [0.06 / 0.38, 0.32 / 0.38])
    assert np.allclose(np.sum(omega, axis=0), [1.0, 1.0])


def test_mixed_state_and_covariance_match_hand_computable_1d_case():
    omega = np.array([[0.75, 0.25], [0.25, 0.75]])
    states = [np.array([[0.0]]), np.array([[10.0]])]
    covariances = [np.array([[1.0]]), np.array([[4.0]])]

    mixed_states, mixed_covariances = mix_state_estimates(states, covariances, omega)

    expected_x0 = 0.75 * 0.0 + 0.25 * 10.0
    expected_p0 = 0.75 * (1.0 + (0.0 - expected_x0) ** 2) + 0.25 * (4.0 + (10.0 - expected_x0) ** 2)
    expected_x1 = 0.25 * 0.0 + 0.75 * 10.0
    expected_p1 = 0.25 * (1.0 + (0.0 - expected_x1) ** 2) + 0.75 * (4.0 + (10.0 - expected_x1) ** 2)

    assert np.allclose(mixed_states[0], [[expected_x0]])
    assert np.allclose(mixed_covariances[0], [[expected_p0]])
    assert np.allclose(mixed_states[1], [[expected_x1]])
    assert np.allclose(mixed_covariances[1], [[expected_p1]])


def test_mixing_bank_exposes_status_and_likelihood_formula():
    bank = make_mixed_bank()
    step = bank.step([0.02, 0.0])

    assert step.estimator_status == IMM_MIXING_STEP_IMPLEMENTED_NO_FINAL_COMBINED_OUTPUT
    assert step.likelihood_formula == GAUSSIAN_LIKELIHOOD_FORMULA
    assert len(step.mixing_probabilities) == 2
    assert np.allclose(np.sum(np.asarray(step.mixing_probabilities), axis=0), [1.0, 1.0])


def test_mixing_outperforms_nonmixed_parallel_filters_on_switch_case():
    result = compare_mixed_vs_nonmixed_on_switch(
        make_mixed_bank(),
        make_nonmixed_bank(),
        measurement_std_m=0.02,
        switch_step=20,
        steps=100,
        dt=0.05,
        seed=23,
        acceleration_mps2=8.0,
        lag_threshold=0.50,
    )

    assert result.mixed_mean_post_switch_position_error_m < result.nonmixed_mean_post_switch_position_error_m * 0.85
    assert result.mixed_peak_post_switch_position_error_m < result.nonmixed_peak_post_switch_position_error_m
    assert result.mixed_maneuver_probability_lag_steps < result.nonmixed_maneuver_probability_lag_steps


def test_mixed_bank_rejects_bad_transition_matrix():
    try:
        MixingModeFilterBank(make_filters(), np.array([[0.9, 0.2], [0.1, 0.9]]), [0.5, 0.5])
    except ValueError as exc:
        assert "sum" in str(exc)
    else:
        raise AssertionError("invalid transition should fail")


def make_filters():
    smooth = cv_position_model(0.05, 0.005, 0.02, name="smooth_cv")
    maneuver = cv_position_model(0.05, 0.5, 0.02, name="maneuver_cv")
    p0 = np.diag([0.001, 0.001, 0.001, 0.001])
    return [
        ModeMatchedKalmanFilter(smooth, [0.0, 0.0, 0.28, 0.0], p0),
        ModeMatchedKalmanFilter(maneuver, [1.0, 0.0, -1.0, 0.0], p0),
    ]


def make_transition():
    # Symmetric persistence is intentional for this validation gate: with no
    # hardware-derived dwell-time evidence yet, both modes get equal persistence.
    return np.array([[0.97, 0.03], [0.03, 0.97]])


def make_mixed_bank():
    return MixingModeFilterBank(make_filters(), make_transition(), [0.8, 0.2])


def make_nonmixed_bank():
    return ModeProbabilityFilterBank(make_filters(), make_transition(), [0.8, 0.2])
