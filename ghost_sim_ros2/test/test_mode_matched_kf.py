import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.mode_matched_kf import (  # noqa: E402
    ASSUMES_WHITE_GAUSSIAN_RESIDUALS,
    CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
    INVALID_IF_NOISE_IS_COLORED,
    MODE_MATCHED_KF_BANK_NO_MIXING,
    KalmanModel,
    ModeMatchedKalmanFilter,
    ModeMatchedKalmanFilterBank,
    ca_position_model,
    cv_position_model,
    run_mode_matched_self_check,
)


def test_scalar_kf_update_matches_hand_computable_case():
    model = KalmanModel(
        name="scalar",
        f=[[1.0]],
        h=[[1.0]],
        q=[[0.0]],
        r=[[1.0]],
        state_labels=("x",),
        measurement_labels=("x",),
        process_noise_status=CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
        process_noise_provenance="test",
        measurement_noise_status=CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
        measurement_noise_provenance="test",
    )
    filt = ModeMatchedKalmanFilter(model, x0=[0.0], p0=np.array([[4.0]]))

    filt.predict()
    diagnostics = filt.update([2.0])
    estimate = filt.estimate()

    # Hand check: S=5, K=4/5=0.8, x+=1.6, Joseph P+=(0.2)^2*4 + 0.8^2*1 = 0.8.
    assert np.allclose(estimate.x, [1.6])
    assert np.allclose(estimate.p, [[0.8]])
    assert np.allclose(diagnostics.innovation, [2.0])
    assert np.allclose(diagnostics.innovation_covariance, [[5.0]])
    assert np.allclose(diagnostics.kalman_gain, [[0.8]])
    assert math.isclose(diagnostics.normalized_innovation_squared, 0.8)


def test_cv_mode_matched_filter_converges_and_covariance_is_calibrated():
    model = cv_position_model(dt=0.05, acceleration_std_mps2=0.18, measurement_std_m=0.04, name="cv_self_check")
    result = run_mode_matched_self_check(
        model,
        truth_x0=[0.0, 0.0, 0.35, -0.15],
        estimate_x0=[0.08, -0.06, 0.0, 0.0],
        p0=np.diag([0.20, 0.20, 0.60, 0.60]),
        trials=300,
        steps=80,
        burn_in_steps=20,
        seed=41,
    )

    assert result.final_position_rmse_m < 0.025
    assert result.final_velocity_rmse_mps < 0.09
    assert 0.93 <= result.two_sigma_coverage_fraction <= 0.98
    assert result.measurement_assumption_label == ASSUMES_WHITE_GAUSSIAN_RESIDUALS
    assert result.covariance_validity_status == INVALID_IF_NOISE_IS_COLORED


def test_ca_mode_matched_filter_converges_and_covariance_is_calibrated():
    model = ca_position_model(dt=0.05, jerk_std_mps3=0.10, measurement_std_m=0.04, name="ca_self_check")
    result = run_mode_matched_self_check(
        model,
        truth_x0=[0.0, 0.0, 0.20, -0.10, 0.03, -0.02],
        estimate_x0=[0.08, -0.06, 0.0, 0.0, 0.0, 0.0],
        p0=np.diag([0.20, 0.20, 0.60, 0.60, 0.25, 0.25]),
        trials=300,
        steps=100,
        burn_in_steps=30,
        seed=42,
    )

    assert result.final_position_rmse_m < 0.03
    assert result.final_velocity_rmse_mps < 0.11
    assert result.final_acceleration_rmse_mps2 is not None
    assert result.final_acceleration_rmse_mps2 < 0.09
    assert 0.93 <= result.two_sigma_coverage_fraction <= 0.98


def test_filter_bank_keeps_mode_states_independent_without_mixing():
    cv_model = cv_position_model(dt=0.1, acceleration_std_mps2=0.2, measurement_std_m=0.05, name="cv")
    alt_model = cv_position_model(dt=0.1, acceleration_std_mps2=0.8, measurement_std_m=0.05, name="alt_cv")
    bank = ModeMatchedKalmanFilterBank(
        [
            ModeMatchedKalmanFilter(cv_model, x0=[0.0, 0.0, 0.0, 0.0], p0=np.eye(4)),
            ModeMatchedKalmanFilter(alt_model, x0=[5.0, 0.0, 0.0, 0.0], p0=np.eye(4)),
        ]
    )

    estimates = bank.step({"cv": [0.1, 0.0], "alt_cv": [5.1, 0.0]})

    assert estimates["cv"].x[0] < 1.0
    assert estimates["alt_cv"].x[0] > 4.0
    assert estimates["cv"].estimator_status == MODE_MATCHED_KF_BANK_NO_MIXING
    assert estimates["alt_cv"].estimator_status == MODE_MATCHED_KF_BANK_NO_MIXING


def test_default_model_metadata_flags_candidate_noise_and_colored_noise_caveat():
    model = cv_position_model(dt=0.1, acceleration_std_mps2=0.2, measurement_std_m=0.05)

    assert model.process_noise_status == CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
    assert model.measurement_noise_status == CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
    assert model.measurement_assumption_label == ASSUMES_WHITE_GAUSSIAN_RESIDUALS
    assert model.covariance_validity_status == INVALID_IF_NOISE_IS_COLORED
    assert model.estimator_status == MODE_MATCHED_KF_BANK_NO_MIXING


def test_cv_position_model_uses_full_measurement_covariance_exactly():
    r = ((2.17492633008e-06, 6.31889067707e-07), (6.31889067707e-07, 1.98048863448e-07))
    model = cv_position_model(
        dt=0.05,
        acceleration_std_mps2=0.18,
        measurement_std_m=0.005,
        measurement_covariance_xy=r,
    )

    assert np.allclose(model.r_matrix(), np.asarray(r))
    assert "Candidate empirical raw R_xy" in model.measurement_noise_provenance
