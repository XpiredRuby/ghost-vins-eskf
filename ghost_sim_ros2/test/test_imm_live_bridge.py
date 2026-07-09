import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.imm_cycle import FORMAL_IMM_5_STEP_CYCLE  # noqa: E402
from analysis.imm_live_bridge import (  # noqa: E402
    DROPOUT_DEGRADED_AFTER_STEPS_DEFAULT,
    FORMAL_IMM_LIVE_BRIDGE_OPTIONAL_NOT_DEFAULT,
    LIVE_IMM_DROPOUT_DEGRADED,
    LIVE_IMM_INTEGRATION_CAVEAT,
    LIVE_IMM_PREDICTION_ONLY,
    LIVE_IMM_TRACKING,
    MAX_WORKSPACE_RANGE_M_DEFAULT,
    MAX_WORKSPACE_RANGE_STATUS,
    DEGRADED_DROPOUT_RATE_FORMULA,
    PREDICTION_ONLY_RATE_FORMULA,
    REJECT_BEHIND_CAMERA_MEASUREMENT,
    REJECT_NONFINITE_MEASUREMENT,
    REJECT_OUT_OF_WORKSPACE_MEASUREMENT,
    FormalImmLiveAdapter,
    FormalImmLiveConfig,
    validate_live_measurement_xy,
)
from analysis.mode_matched_kf import (  # noqa: E402
    CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R,
    INVALID_IF_NOISE_IS_COLORED,
)


def test_live_bridge_stays_uninitialized_until_first_measurement():
    bridge = FormalImmLiveAdapter()

    output = bridge.step(None)

    assert not output.initialized
    assert output.estimate is None
    assert output.mode_probabilities == {}
    assert output.hypotheses == []
    assert output.live_status != LIVE_IMM_TRACKING
    assert output.prediction_only_steps == 0
    assert output.estimator_status == FORMAL_IMM_5_STEP_CYCLE
    assert output.integration_status == FORMAL_IMM_LIVE_BRIDGE_OPTIONAL_NOT_DEFAULT


def test_live_bridge_initializes_from_first_measurement_and_emits_payload_schema():
    bridge = FormalImmLiveAdapter(FormalImmLiveConfig(dt_s=0.05, measurement_std_m=0.02))

    output = bridge.step([1.0, -0.2])

    assert output.initialized
    assert output.estimate is not None
    assert set(output.mode_probabilities) == {"smooth_cv", "maneuver_cv"}
    assert abs(sum(output.mode_probabilities.values()) - 1.0) < 1e-12
    assert len(output.hypotheses) == 2
    assert output.hypotheses[0]["rank"] == 1
    assert output.hypotheses[0]["path"]
    assert output.live_status == LIVE_IMM_TRACKING
    assert output.prediction_only_steps == 0
    assert output.total_initialized_cycles == 1
    assert output.tracking_cycles == 1
    assert output.prediction_only_rate == 0.0
    assert output.degraded_dropout_rate == 0.0
    assert output.dropout_degraded_after_steps == DROPOUT_DEGRADED_AFTER_STEPS_DEFAULT
    assert output.parameter_status == CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
    assert output.covariance_validity_status == INVALID_IF_NOISE_IS_COLORED
    assert output.integration_caveat == LIVE_IMM_INTEGRATION_CAVEAT


def test_live_bridge_predicts_through_missing_measurements_after_initialization():
    bridge = FormalImmLiveAdapter(FormalImmLiveConfig(dt_s=0.05, measurement_std_m=0.02))
    first = bridge.step([0.0, 0.0])

    predicted = bridge.step(None)

    assert first.initialized
    assert predicted.initialized
    assert predicted.sequence == first.sequence + 1
    assert predicted.estimate is not None
    assert predicted.live_status == LIVE_IMM_PREDICTION_ONLY
    assert predicted.prediction_only_steps == 1
    assert abs(sum(predicted.mode_probabilities.values()) - 1.0) < 1e-12


def test_live_bridge_flags_degraded_after_named_dropout_threshold():
    bridge = FormalImmLiveAdapter(
        FormalImmLiveConfig(dt_s=0.05, measurement_std_m=0.02, dropout_degraded_after_steps=2)
    )
    bridge.step([0.0, 0.0])

    first_dropout = bridge.step(None)
    second_dropout = bridge.step(None)
    recovered = bridge.step([0.01, 0.0])

    assert first_dropout.live_status == LIVE_IMM_PREDICTION_ONLY
    assert first_dropout.prediction_only_steps == 1
    assert second_dropout.live_status == LIVE_IMM_DROPOUT_DEGRADED
    assert second_dropout.prediction_only_steps == 2
    assert second_dropout.total_initialized_cycles == 3
    assert second_dropout.prediction_only_cycles == 1
    assert second_dropout.degraded_dropout_cycles == 1
    assert recovered.live_status == LIVE_IMM_TRACKING
    assert recovered.prediction_only_steps == 0
    assert recovered.total_initialized_cycles == 4
    assert recovered.tracking_cycles == 2
    assert recovered.prediction_only_cycles == 1
    assert recovered.degraded_dropout_cycles == 1
    assert recovered.prediction_only_rate == 0.25
    assert recovered.degraded_dropout_rate == 0.25


def test_live_bridge_exposes_dropout_metric_formulas():
    assert PREDICTION_ONLY_RATE_FORMULA == "prediction_only_rate = prediction_only_cycles / total_initialized_cycles"
    assert DEGRADED_DROPOUT_RATE_FORMULA == "degraded_dropout_rate = degraded_dropout_cycles / total_initialized_cycles"


def test_live_bridge_rejects_invalid_measurements_and_bad_config():
    bridge = FormalImmLiveAdapter()

    try:
        bridge.step([1.0])
    except ValueError as exc:
        assert "measurement_xy" in str(exc)
    else:
        raise AssertionError("bad measurement dimension should fail")

    try:
        FormalImmLiveConfig(dt_s=0.0).validate()
    except ValueError as exc:
        assert "dt_s" in str(exc)
    else:
        raise AssertionError("bad dt should fail")

    try:
        FormalImmLiveConfig(dropout_degraded_after_steps=0).validate()
    except ValueError as exc:
        assert "dropout_degraded_after_steps" in str(exc)
    else:
        raise AssertionError("bad dropout threshold should fail")


def test_live_measurement_validation_returns_rejection_reason_without_throwing():
    assert MAX_WORKSPACE_RANGE_M_DEFAULT == 5.0
    assert MAX_WORKSPACE_RANGE_STATUS == "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_WORKSPACE_RANGE"
    assert validate_live_measurement_xy(1.0, 0.1, MAX_WORKSPACE_RANGE_M_DEFAULT).measurement_xy == [1.0, 0.1]

    nonfinite = validate_live_measurement_xy(float("nan"), 0.0, MAX_WORKSPACE_RANGE_M_DEFAULT)
    behind = validate_live_measurement_xy(-0.1, 0.0, MAX_WORKSPACE_RANGE_M_DEFAULT)
    out_of_workspace = validate_live_measurement_xy(6.0, 0.0, MAX_WORKSPACE_RANGE_M_DEFAULT)

    assert not nonfinite.valid
    assert nonfinite.rejection_reason == REJECT_NONFINITE_MEASUREMENT
    assert behind.rejection_reason == REJECT_BEHIND_CAMERA_MEASUREMENT
    assert out_of_workspace.rejection_reason == REJECT_OUT_OF_WORKSPACE_MEASUREMENT


def test_live_bridge_future_path_uses_velocity_projection():
    bridge = FormalImmLiveAdapter(FormalImmLiveConfig(dt_s=0.05, future_horizon_s=0.2, future_dt_s=0.1))

    path = bridge.project_path([1.0, 2.0, 0.5, -0.25])

    assert [p["t_s"] for p in path] == [0.0, 0.1, 0.2]
    assert np.allclose([p["x_m"] for p in path], [1.0, 1.05, 1.1])
    assert np.allclose([p["y_m"] for p in path], [2.0, 1.975, 1.95])


def test_live_bridge_accepts_full_r_and_emits_candidate_metadata():
    r = ((2.17492633008e-06, 6.31889067707e-07), (6.31889067707e-07, 1.98048863448e-07))
    bridge = FormalImmLiveAdapter(FormalImmLiveConfig(dt_s=0.05, measurement_std_m=0.005, measurement_covariance_xy=r))

    output = bridge.step([1.0, 0.1])

    assert output.initialized
    assert output.measurement_r_xy == [[r[0][0], r[0][1]], [r[1][0], r[1][1]]]
    assert output.measurement_r_source == "CONTROLLED_R_CANDIDATE_STABLE_60S_PENDING_ENGINEER_REVIEW"
    assert output.measurement_r_status == "DOES_NOT_VALIDATE_ESTIMATOR_ACCURACY"
    assert "does not validate estimator accuracy" in output.measurement_r_provenance
