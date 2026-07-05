import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.imm_cycle import FORMAL_IMM_5_STEP_CYCLE  # noqa: E402
from analysis.imm_live_bridge import (  # noqa: E402
    FORMAL_IMM_LIVE_BRIDGE_OPTIONAL_NOT_DEFAULT,
    LIVE_IMM_INTEGRATION_CAVEAT,
    FormalImmLiveAdapter,
    FormalImmLiveConfig,
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
    assert abs(sum(predicted.mode_probabilities.values()) - 1.0) < 1e-12


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


def test_live_bridge_future_path_uses_velocity_projection():
    bridge = FormalImmLiveAdapter(FormalImmLiveConfig(dt_s=0.05, future_horizon_s=0.2, future_dt_s=0.1))

    path = bridge.project_path([1.0, 2.0, 0.5, -0.25])

    assert [p["t_s"] for p in path] == [0.0, 0.1, 0.2]
    assert np.allclose([p["x_m"] for p in path], [1.0, 1.05, 1.1])
    assert np.allclose([p["y_m"] for p in path], [2.0, 1.975, 1.95])
