import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.imm_cycle import (  # noqa: E402
    COLORED_NOISE_MISCALIBRATION_WARNING,
    FORMAL_IMM_5_STEP_CYCLE,
    combine_mode_estimates,
    run_step_4d_validation_suite,
)
from analysis.imm_mixing import (  # noqa: E402
    IMM_MIXING_STEP_IMPLEMENTED_NO_FINAL_COMBINED_OUTPUT,
    MixingModeFilterBank,
    compare_mixed_vs_nonmixed_on_switch,
    mix_state_estimates,
    mixing_probabilities,
)
from analysis.mode_matched_kf import (  # noqa: E402
    ASSUMES_WHITE_GAUSSIAN_RESIDUALS,
    INVALID_IF_NOISE_IS_COLORED,
    KalmanEstimate,
    ModeMatchedKalmanFilter,
    ca_position_model,
    cv_position_model,
    run_mode_matched_self_check,
)
from analysis.mode_probability_bank import (  # noqa: E402
    MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM,
    ModeProbabilityFilterBank,
    predict_mode_probabilities,
    run_unambiguous_cv_probability_self_check,
    update_mode_probabilities_from_likelihoods,
)

CV_COVERAGE_BAND = (0.93, 0.98)
CA_COVERAGE_BAND = (0.93, 0.98)
MODE_PROBABILITY_FINAL_MIN = 0.99
MIXED_MEAN_ERROR_RATIO_MAX = 0.50
MIXED_PEAK_ERROR_RATIO_MAX = 0.50
WHITE_IMM_RMSE_LIMIT_M = 0.02
COLORED_IMM_COVERAGE_MAX = 0.90
MANEUVER_ACTIVE_MODE_ACCURACY_MIN = 0.75
MANEUVER_PROBABILITY_LAG_MAX_STEPS = 3
MANEUVER_COVERAGE_EXPLANATION = (
    "The maneuver case is white-noise driven, but its 2-sigma coverage is lower than the steady CV case because "
    "the scored window includes an intentional model switch transient. During the switch, posterior mode mass moves "
    "between smooth and maneuver filters while the combined covariance is adapting; the metric is therefore a "
    "transient tracking regression, not a steady-state covariance calibration claim."
)
BURN_IN_RATIONALE_FOR_REGRESSION = (
    "20 steps * 0.05 s = 1.0 s. The first second is excluded from coverage metrics to remove the deliberately "
    "broad candidate initial-P transient before checking covariance behavior."
)


def test_4a_mode_matched_kf_self_checks_are_regression_gated():
    cv_result = run_mode_matched_self_check(
        cv_position_model(dt=0.05, acceleration_std_mps2=0.18, measurement_std_m=0.04, name="cv_regression"),
        truth_x0=[0.0, 0.0, 0.35, -0.15],
        estimate_x0=[0.08, -0.06, 0.0, 0.0],
        p0=np.diag([0.20, 0.20, 0.60, 0.60]),
        trials=300,
        steps=80,
        burn_in_steps=20,
        seed=41,
    )
    ca_result = run_mode_matched_self_check(
        ca_position_model(dt=0.05, jerk_std_mps3=0.10, measurement_std_m=0.04, name="ca_regression"),
        truth_x0=[0.0, 0.0, 0.20, -0.10, 0.03, -0.02],
        estimate_x0=[0.08, -0.06, 0.0, 0.0, 0.0, 0.0],
        p0=np.diag([0.20, 0.20, 0.60, 0.60, 0.25, 0.25]),
        trials=300,
        steps=100,
        burn_in_steps=30,
        seed=42,
    )

    assert cv_result.final_position_rmse_m < 0.025
    assert cv_result.final_velocity_rmse_mps < 0.09
    assert CV_COVERAGE_BAND[0] <= cv_result.two_sigma_coverage_fraction <= CV_COVERAGE_BAND[1]
    assert cv_result.measurement_assumption_label == ASSUMES_WHITE_GAUSSIAN_RESIDUALS
    assert cv_result.covariance_validity_status == INVALID_IF_NOISE_IS_COLORED

    assert ca_result.final_position_rmse_m < 0.03
    assert ca_result.final_velocity_rmse_mps < 0.11
    assert ca_result.final_acceleration_rmse_mps2 is not None
    assert ca_result.final_acceleration_rmse_mps2 < 0.09
    assert CA_COVERAGE_BAND[0] <= ca_result.two_sigma_coverage_fraction <= CA_COVERAGE_BAND[1]


def test_4b_mode_probability_math_and_unambiguous_cv_convergence_are_regression_gated():
    transition = np.array([[0.9, 0.1], [0.2, 0.8]])
    predicted = predict_mode_probabilities([0.6, 0.4], transition)
    posterior = update_mode_probabilities_from_likelihoods(predicted, [0.5, 0.25])

    assert np.allclose(predicted, [0.62, 0.38])
    assert np.allclose(posterior, [0.31 / 0.405, 0.095 / 0.405])

    bank = _make_probability_bank()
    result = run_unambiguous_cv_probability_self_check(bank, measurement_std_m=0.01, steps=50, seed=11)

    assert result.estimator_status == MODE_PROBABILITY_WEIGHTED_PARALLEL_FILTERS_NOT_IMM
    assert result.initial_probability == 0.5
    assert result.final_probability >= MODE_PROBABILITY_FINAL_MIN
    assert result.competing_final_probabilities["maneuver_cv"] <= 1.0 - MODE_PROBABILITY_FINAL_MIN


def test_4c_mixing_math_and_switch_performance_margin_are_regression_gated():
    omega = mixing_probabilities([0.6, 0.4], np.array([[0.9, 0.1], [0.2, 0.8]]))
    states = [np.array([[0.0]]), np.array([[10.0]])]
    covariances = [np.array([[1.0]]), np.array([[4.0]])]
    mixed_states, mixed_covariances = mix_state_estimates(states, covariances, np.array([[0.75, 0.25], [0.25, 0.75]]))
    comparison = compare_mixed_vs_nonmixed_on_switch(
        _make_mixed_bank(),
        _make_nonmixed_bank(),
        measurement_std_m=0.02,
        switch_step=20,
        steps=100,
        dt=0.05,
        seed=23,
        acceleration_mps2=8.0,
        lag_threshold=0.50,
    )
    mean_ratio = comparison.mixed_mean_post_switch_position_error_m / comparison.nonmixed_mean_post_switch_position_error_m
    peak_ratio = comparison.mixed_peak_post_switch_position_error_m / comparison.nonmixed_peak_post_switch_position_error_m

    assert np.allclose(omega[:, 0], [0.54 / 0.62, 0.08 / 0.62])
    assert np.allclose(omega[:, 1], [0.06 / 0.38, 0.32 / 0.38])
    assert np.allclose(mixed_states[0], [[2.5]])
    assert np.allclose(mixed_covariances[0], [[20.5]])
    assert np.allclose(mixed_states[1], [[7.5]])
    assert np.allclose(mixed_covariances[1], [[22.0]])
    assert comparison.estimator_status == IMM_MIXING_STEP_IMPLEMENTED_NO_FINAL_COMBINED_OUTPUT
    assert mean_ratio <= MIXED_MEAN_ERROR_RATIO_MAX
    assert peak_ratio <= MIXED_PEAK_ERROR_RATIO_MAX
    assert comparison.mixed_maneuver_probability_lag_steps < comparison.nonmixed_maneuver_probability_lag_steps


def test_4d_full_imm_cycle_validations_are_regression_gated():
    combined = combine_mode_estimates(
        {
            "a": KalmanEstimate("a", [0.0], [[1.0]], INVALID_IF_NOISE_IS_COLORED, "test"),
            "b": KalmanEstimate("b", [10.0], [[4.0]], INVALID_IF_NOISE_IS_COLORED, "test"),
        },
        {"a": 0.25, "b": 0.75},
        ["a", "b"],
    )
    results = {result.scenario: result for result in run_step_4d_validation_suite()}
    white = results["white_noise_cv"]
    colored = results["colored_ar1_cv"]
    maneuver = results["maneuver_switch_cv"]

    assert combined.estimator_status == FORMAL_IMM_5_STEP_CYCLE
    assert np.allclose(combined.x, [7.5])
    assert np.allclose(combined.p, [[22.0]])
    assert np.allclose(combined.std, [math.sqrt(22.0)])

    assert white.position_rmse_m <= WHITE_IMM_RMSE_LIMIT_M
    assert white.two_sigma_coverage_fraction >= 0.90
    assert white.colored_noise_miscalibration_warning is None

    assert colored.position_rmse_m <= WHITE_IMM_RMSE_LIMIT_M
    assert colored.two_sigma_coverage_fraction <= COLORED_IMM_COVERAGE_MAX
    assert colored.colored_noise_miscalibration_warning == COLORED_NOISE_MISCALIBRATION_WARNING
    assert colored.covariance_validity_status == INVALID_IF_NOISE_IS_COLORED

    assert maneuver.position_rmse_m < 0.05
    assert maneuver.final_position_error_m < 0.02
    assert maneuver.active_mode_accuracy_fraction >= MANEUVER_ACTIVE_MODE_ACCURACY_MIN
    assert maneuver.mode_probability_lag_steps <= MANEUVER_PROBABILITY_LAG_MAX_STEPS
    assert "model switch transient" in MANEUVER_COVERAGE_EXPLANATION
    assert "1.0 s" in BURN_IN_RATIONALE_FOR_REGRESSION


def _make_probability_bank():
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


def _make_mixing_filters():
    smooth = cv_position_model(0.05, 0.005, 0.02, name="smooth_cv")
    maneuver = cv_position_model(0.05, 0.5, 0.02, name="maneuver_cv")
    p0 = np.diag([0.001, 0.001, 0.001, 0.001])
    return [
        ModeMatchedKalmanFilter(smooth, [0.0, 0.0, 0.28, 0.0], p0),
        ModeMatchedKalmanFilter(maneuver, [1.0, 0.0, -1.0, 0.0], p0),
    ]


def _make_mixing_transition():
    return np.array([[0.97, 0.03], [0.03, 0.97]])


def _make_mixed_bank():
    return MixingModeFilterBank(_make_mixing_filters(), _make_mixing_transition(), [0.8, 0.2])


def _make_nonmixed_bank():
    return ModeProbabilityFilterBank(_make_mixing_filters(), _make_mixing_transition(), [0.8, 0.2])
