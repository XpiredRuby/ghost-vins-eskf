import sys
from types import SimpleNamespace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.imm_tracker import (  # noqa: E402
    IMMTracker,
    cv_model,
    default_cv_imm,
    simulate_maneuver,
)


def test_imm_probabilities_stay_normalized_after_updates():
    tracker = default_cv_imm(0.1, measurement_std_m=0.05)
    for k in range(20):
        estimate = tracker.step([0.04 * k, 0.0])
        assert abs(sum(estimate.mode_probabilities.values()) - 1.0) < 1e-9


def test_imm_maneuver_mode_gains_probability_after_acceleration():
    args = SimpleNamespace(
        dt=0.05,
        steps=180,
        measurement_std=0.03,
        maneuver_start=3.0,
        ax_mps2=1.2,
        seed=4,
    )
    rows = simulate_maneuver(args)

    before = [row for row in rows if 2.0 <= row["t_s"] < 3.0]
    after = [row for row in rows if row["t_s"] > 6.0]

    assert before and after
    assert after[-1]["maneuver_prob"] > before[-1]["maneuver_prob"]
    assert after[-1]["maneuver_prob"] > 0.35


def test_imm_combined_covariance_is_positive_semidefinite():
    tracker = default_cv_imm(0.1, measurement_std_m=0.05)
    for k in range(10):
        estimate = tracker.step([0.05 * k, 0.01 * k])
    eigvals = np.linalg.eigvalsh(np.asarray(estimate.p))

    assert np.min(eigvals) > -1e-9


def test_imm_predict_without_measurement_keeps_probabilities_normalized():
    tracker = default_cv_imm(0.1, measurement_std_m=0.05)
    for _ in range(8):
        estimate = tracker.step(None)

    assert abs(sum(estimate.mode_probabilities.values()) - 1.0) < 1e-9


def test_imm_rejects_invalid_transition_matrix():
    models = [cv_model(0.1, "a", 0.2), cv_model(0.1, "b", 1.0)]
    transition = np.array([[0.9, 0.2], [0.1, 0.9]])
    h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    r = np.eye(2) * 0.05**2

    try:
        IMMTracker(models, transition, h, r, [0, 0, 0, 0], np.eye(4))
    except ValueError as exc:
        assert "row" in str(exc)
    else:
        raise AssertionError("invalid transition matrix should fail")
