import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.imm_cycle import (  # noqa: E402
    AR1_DRIFT_GENERATOR_PROVENANCE,
    BURN_IN_RATIONALE,
    COLORED_NOISE_MISCALIBRATION_WARNING,
    FORMAL_IMM_5_STEP_CYCLE,
    NONMIXED_PROBABILITY_COLLAPSE_NOTE,
    P0_STRESS_CASE_CAVEAT,
    TRANSITION_MATRIX_INVARIANTS,
    InteractingMultipleModelEstimator,
    combine_mode_estimates,
    make_smooth_maneuver_cv_imm,
    run_step_4d_validation_suite,
    validate_colored_ar1_case,
    validate_maneuver_switch_case,
    validate_white_noise_case,
)
from analysis.mode_matched_kf import KalmanEstimate  # noqa: E402


def test_combined_state_and_covariance_match_hand_computable_1d_case():
    estimates = {
        "a": KalmanEstimate("a", [0.0], [[1.0]], "INVALID_IF_NOISE_IS_COLORED", "test"),
        "b": KalmanEstimate("b", [10.0], [[4.0]], "INVALID_IF_NOISE_IS_COLORED", "test"),
    }

    combined = combine_mode_estimates(estimates, {"a": 0.25, "b": 0.75}, ["a", "b"])

    expected_x = 0.25 * 0.0 + 0.75 * 10.0
    expected_p = 0.25 * (1.0 + (0.0 - expected_x) ** 2) + 0.75 * (4.0 + (10.0 - expected_x) ** 2)
    assert np.allclose(combined.x, [expected_x])
    assert np.allclose(combined.p, [[expected_p]])
    assert np.allclose(combined.std, [np.sqrt(expected_p)])
    assert combined.estimator_status == FORMAL_IMM_5_STEP_CYCLE
    assert combined.covariance_validity_status == "INVALID_IF_NOISE_IS_COLORED"


def test_full_imm_cycle_exposes_five_step_status_and_combined_output():
    imm = make_smooth_maneuver_cv_imm()
    step = imm.step([0.01, -0.02])

    assert isinstance(imm, InteractingMultipleModelEstimator)
    assert step.estimator_status == FORMAL_IMM_5_STEP_CYCLE
    assert step.combined_estimate.estimator_status == FORMAL_IMM_5_STEP_CYCLE
    assert step.cycle_order == (
        "predict_mode_probabilities",
        "mix_initial_conditions",
        "mode_matched_filter_predict_update",
        "gaussian_likelihood_mode_probability_update",
        "combine_mode_conditioned_output",
    )
    assert len(step.combined_estimate.x) == 4
    assert np.asarray(step.combined_estimate.p).shape == (4, 4)
    assert abs(sum(step.mode_probabilities.values()) - 1.0) < 1e-12


def test_white_noise_validation_has_low_position_error_and_reasonable_coverage():
    result = validate_white_noise_case()

    assert result.scenario == "white_noise_cv"
    assert result.position_rmse_m < 0.02
    assert result.final_position_error_m < 0.02
    assert 0.90 <= result.two_sigma_coverage_fraction <= 1.0
    assert result.colored_noise_miscalibration_warning is None


def test_colored_ar1_validation_carries_miscalibration_warning_and_caveat():
    result = validate_colored_ar1_case()

    assert result.scenario == "colored_ar1_cv"
    assert result.position_rmse_m < 0.02
    assert result.two_sigma_coverage_fraction < 0.90
    assert result.colored_noise_miscalibration_warning == COLORED_NOISE_MISCALIBRATION_WARNING
    assert result.covariance_validity_status == "INVALID_IF_NOISE_IS_COLORED"
    assert "rho=0.985" in AR1_DRIFT_GENERATOR_PROVENANCE
    assert "process_std=0.0012" in AR1_DRIFT_GENERATOR_PROVENANCE
    assert "white_std=0.0025" in AR1_DRIFT_GENERATOR_PROVENANCE


def test_maneuver_switch_validation_tracks_active_mode_with_stated_lag():
    result = validate_maneuver_switch_case()

    assert result.scenario == "maneuver_switch_cv"
    assert result.position_rmse_m < 0.05
    assert result.final_position_error_m < 0.02
    assert result.mode_probability_lag_steps == 3
    assert result.active_mode_accuracy_fraction >= 0.75
    assert any(sample["maneuver_cv_probability"] > 0.90 for sample in result.samples)


def test_step_4d_suite_contains_all_three_required_cases():
    results = run_step_4d_validation_suite()

    assert [r.scenario for r in results] == ["white_noise_cv", "colored_ar1_cv", "maneuver_switch_cv"]
    assert all(r.covariance_validity_status == "INVALID_IF_NOISE_IS_COLORED" for r in results)
    assert all(r.burn_in_steps == 20 for r in results)


def test_carry_forward_documentation_constants_are_present():
    assert "1.0 s at dt=0.05 s" in BURN_IN_RATIONALE
    assert "collapse" in NONMIXED_PROBABILITY_COLLAPSE_NOTE
    assert "tight P0" in P0_STRESS_CASE_CAVEAT
    assert TRANSITION_MATRIX_INVARIANTS == (
        "transition must be square",
        "transition rows must sum to 1",
        "transition probabilities must be finite and nonnegative",
        "transition shape must match filter count",
    )


def test_invalid_transition_invariants_are_enforced():
    bad_cases = [
        (np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]), "square"),
        (np.array([[0.8, 0.3], [0.1, 0.9]]), "sum"),
        (np.array([[0.9, -0.1], [0.1, 0.9]]), "nonnegative"),
        (np.eye(3), "shape"),
    ]
    for transition, message in bad_cases:
        try:
            make_smooth_maneuver_cv_imm(transition=transition)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"invalid transition should fail: {message}")


def test_smooth_maneuver_imm_passes_full_r_to_both_mode_filters():
    r = ((2.17492633008e-06, 6.31889067707e-07), (6.31889067707e-07, 1.98048863448e-07))
    imm = make_smooth_maneuver_cv_imm(measurement_std_m=0.005, measurement_covariance_xy=r)

    for filt in imm.mixed_bank.filters:
        assert np.allclose(filt.r, np.asarray(r))
