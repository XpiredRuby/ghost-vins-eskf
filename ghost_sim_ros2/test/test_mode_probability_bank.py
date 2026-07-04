import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.mode_matched_kf import ModeMatchedKalmanFilter, cv_position_model  # noqa: E402
from analysis.mode_probability_bank import (  # noqa: E402
    MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM,
    ModeProbabilityFilterBank,
    predict_mode_probabilities,
    run_unambiguous_cv_probability_self_check,
    update_mode_probabilities_from_likelihoods,
)


def test_mode_probability_prediction_matches_hand_computable_case():
    transition = np.array([[0.9, 0.1], [0.2, 0.8]])
    predicted = predict_mode_probabilities([0.6, 0.4], transition)

    assert np.allclose(predicted, [0.62, 0.38])


def test_likelihood_update_matches_hand_computable_case():
    posterior = update_mode_probabilities_from_likelihoods([0.62, 0.38], [0.5, 0.25])

    # Unnormalized weights are [0.31, 0.095], total 0.405.
    assert np.allclose(posterior, [0.31 / 0.405, 0.095 / 0.405])


def test_probability_filter_bank_converges_to_unambiguous_cv_mode():
    bank = make_smooth_vs_maneuver_bank()
    result = run_unambiguous_cv_probability_self_check(bank, measurement_std_m=0.01, steps=50, seed=11)

    assert result.true_mode == "smooth_cv"
    assert result.initial_probability == 0.5
    assert result.final_probability > 0.99
    assert result.competing_final_probabilities["maneuver_cv"] < 0.01
    assert result.estimator_status == MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM


def test_probability_filter_bank_is_labeled_not_imm_and_does_not_mix_states():
    bank = make_smooth_vs_maneuver_bank()
    first = bank.step([0.04, 0.0])

    assert first.estimator_status == MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM
    assert set(first.estimates) == {"smooth_cv", "maneuver_cv"}
    assert abs(first.mode_probabilities["smooth_cv"] + first.mode_probabilities["maneuver_cv"] - 1.0) < 1e-12
    assert first.estimates["smooth_cv"].estimator_status != "IMM"
    assert first.estimates["maneuver_cv"].estimator_status != "IMM"


def test_invalid_transition_matrix_is_rejected():
    smooth = cv_position_model(0.05, 0.02, 0.03, name="smooth_cv")
    maneuver = cv_position_model(0.05, 1.5, 0.03, name="maneuver_cv")

    try:
        ModeProbabilityFilterBank(
            [
                ModeMatchedKalmanFilter(smooth, [0.0, 0.0, 0.0, 0.0], np.eye(4)),
                ModeMatchedKalmanFilter(maneuver, [0.0, 0.0, 0.0, 0.0], np.eye(4)),
            ],
            np.array([[0.9, 0.2], [0.1, 0.9]]),
        )
    except ValueError as exc:
        assert "rows" in str(exc)
    else:
        raise AssertionError("invalid transition should fail")


def make_smooth_vs_maneuver_bank():
    smooth = cv_position_model(0.05, 0.01, 0.03, name="smooth_cv")
    maneuver = cv_position_model(0.05, 3.0, 0.03, name="maneuver_cv")
    transition = np.array([[0.995, 0.005], [0.02, 0.98]])
    p0 = np.diag([0.04, 0.04, 0.20, 0.20])
    return ModeProbabilityFilterBank(
        [
            ModeMatchedKalmanFilter(smooth, [0.0, 0.0, 0.20, 0.0], p0),
            ModeMatchedKalmanFilter(maneuver, [0.0, 0.0, 0.20, 0.0], p0),
        ],
        transition,
        mode_probabilities=[0.5, 0.5],
    )
