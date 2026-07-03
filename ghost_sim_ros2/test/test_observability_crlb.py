import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.measurement_covariance import (  # noqa: E402
    DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R,
    MAY_INCLUDE_COLORED_COMPONENTS,
    estimate_empirical_stationary_r,
    estimate_pinhole_lateral_r,
)
from analysis.observability_crlb import (  # noqa: E402
    ANALYTICAL_WHITE_R_REFERENCE,
    CRLB_ASSUMPTION_LABEL,
    CRLB_INVALID_IF_COLORED,
    DETRENDED_R_DIAGNOSTIC,
    RAW_EMPIRICAL_R_DEFAULT,
    ca_state_transition,
    cv_position_crlb,
    cv_position_crlb_from_covariance_estimate,
    cv_state_transition,
    empirical_raw_cv_crlb,
    format_markdown,
    gramian_report,
    linear_crlb,
    linear_crlb_from_covariance_estimate,
    observability_report,
    pinhole_cv_crlb,
    position_measurement_matrix,
    range_bearing_jacobian_xy,
    weighted_observability_gramian,
)


def write_pose_csv(path, t, xyz):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "x", "y", "z"])
        for ti, row in zip(t, xyz):
            writer.writerow([ti, row[0], row[1], row[2]])


def test_cv_position_model_observable_after_two_steps():
    f = cv_state_transition(0.1)
    h = position_measurement_matrix()

    one_step = observability_report(f, h, horizon_steps=1)
    two_steps = observability_report(f, h, horizon_steps=2)

    assert one_step.rank == 2
    assert not one_step.observable
    assert two_steps.rank == 4
    assert two_steps.observable


def test_ca_position_model_observable_after_three_steps():
    f = ca_state_transition(0.1)
    h = position_measurement_matrix(state_dim=6)

    two_steps = observability_report(f, h, horizon_steps=2)
    three_steps = observability_report(f, h, horizon_steps=3)

    assert two_steps.rank == 4
    assert not two_steps.observable
    assert three_steps.rank == 6
    assert three_steps.observable


def test_r_weighted_gramian_matches_hand_computable_1d_cv_case():
    dt = 0.25
    sigma = 0.5
    f = np.array([[1.0, dt], [0.0, 1.0]])
    h = np.array([[1.0, 0.0]])
    r = np.array([[sigma**2]])

    gramian = weighted_observability_gramian(f, h, r, horizon_steps=2)
    expected = np.array([[2.0, dt], [dt, dt**2]]) / (sigma**2)

    assert np.allclose(gramian, expected)
    report = gramian_report(f, h, r, horizon_steps=2)
    assert report.rank == 2
    assert report.observable
    assert math.isfinite(report.condition_number)


def test_cv_position_crlb_improves_with_longer_horizon():
    _, short = cv_position_crlb(dt=0.1, position_std_m=0.05, horizon_steps=2)
    _, long = cv_position_crlb(dt=0.1, position_std_m=0.05, horizon_steps=8)

    assert not short.singular
    assert not long.singular
    assert np.trace(np.asarray(long.crlb_covariance)) < np.trace(np.asarray(short.crlb_covariance))
    assert long.std[0] < short.std[0]
    assert short.assumption_label == CRLB_ASSUMPTION_LABEL
    assert short.validity_status == CRLB_INVALID_IF_COLORED


def test_lower_measurement_noise_gives_lower_crlb():
    f = cv_state_transition(0.1)
    h = position_measurement_matrix()
    loose = linear_crlb(f, h, np.eye(2) * 0.10**2, horizon_steps=5)
    tight = linear_crlb(f, h, np.eye(2) * 0.02**2, horizon_steps=5)

    assert np.trace(np.asarray(tight.crlb_covariance)) < np.trace(np.asarray(loose.crlb_covariance))


def test_raw_empirical_r_is_default_for_crlb_and_carries_colored_caveat(tmp_path):
    rng = np.random.default_rng(17)
    t = np.arange(500, dtype=float) * 0.05
    drift = np.column_stack([0.001 * t, -0.0005 * t, np.zeros_like(t)])
    noise = rng.normal(0.0, [0.001, 0.002, 0.001], size=(len(t), 3))
    xyz = drift + noise
    path = tmp_path / "pose.csv"
    write_pose_csv(path, t, xyz)

    r_est = estimate_empirical_stationary_r(path)
    obs, crlb = cv_position_crlb_from_covariance_estimate(dt=0.05, r_estimate=r_est, horizon_steps=5)

    assert obs.observable
    assert r_est.sample_mode == "raw"
    assert crlb.r_sample_mode == "raw"
    assert crlb.r_assumption_label == MAY_INCLUDE_COLORED_COMPONENTS
    assert crlb.validity_status == CRLB_INVALID_IF_COLORED
    assert RAW_EMPIRICAL_R_DEFAULT in crlb.caveat
    assert "invalid" in crlb.caveat.lower()


def test_empirical_raw_cv_crlb_helper_uses_raw_mode(tmp_path):
    rng = np.random.default_rng(18)
    t = np.arange(400, dtype=float) * 0.05
    xyz = rng.normal(0.0, [0.001, 0.002, 0.001], size=(len(t), 3))
    path = tmp_path / "pose.csv"
    write_pose_csv(path, t, xyz)

    _obs, crlb = empirical_raw_cv_crlb(str(path), dt=0.05, horizon_steps=5)

    assert crlb.r_sample_mode == "raw"
    assert crlb.r_assumption_label == MAY_INCLUDE_COLORED_COMPONENTS
    assert RAW_EMPIRICAL_R_DEFAULT in crlb.caveat


def test_detrended_empirical_r_is_labeled_diagnostic_not_default(tmp_path):
    rng = np.random.default_rng(19)
    t = np.arange(500, dtype=float) * 0.05
    drift = np.column_stack([0.001 * t, -0.001 * t, np.zeros_like(t)])
    xyz = drift + rng.normal(0.0, [0.001, 0.001, 0.001], size=(len(t), 3))
    path = tmp_path / "pose.csv"
    write_pose_csv(path, t, xyz)

    r_est = estimate_empirical_stationary_r(path, sample_mode="detrended")
    _obs, crlb = cv_position_crlb_from_covariance_estimate(dt=0.05, r_estimate=r_est, horizon_steps=5)

    assert r_est.assumption_label == DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R
    assert crlb.r_sample_mode == "detrended"
    assert crlb.r_assumption_label == DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R
    assert DETRENDED_R_DIAGNOSTIC in crlb.caveat
    assert "not the default filter R" in crlb.caveat


def test_pinhole_covariance_estimate_crlb_gets_analytical_white_reference_caveat():
    r_est = estimate_pinhole_lateral_r(fx_px=500.0, fy_px=250.0, reprojection_rms_px=1.0, standoff_m=2.0)
    _obs, crlb = cv_position_crlb_from_covariance_estimate(dt=0.1, r_estimate=r_est, horizon_steps=4)

    assert crlb.r_source == "pinhole_first_order"
    assert ANALYTICAL_WHITE_R_REFERENCE in crlb.caveat
    assert crlb.r_sample_mode is None


def test_pinhole_cv_crlb_convenience_wrapper():
    obs, crlb = pinhole_cv_crlb(
        dt=0.1,
        fx_px=500.0,
        fy_px=500.0,
        reprojection_rms_px=1.0,
        standoff_m=1.0,
        horizon_steps=4,
    )

    assert obs.observable
    assert crlb.r_source == "pinhole_first_order"
    assert all(math.isfinite(v) for v in crlb.std)


def test_range_bearing_jacobian_xy_matches_reference_values():
    jacobian = range_bearing_jacobian_xy(3.0, 4.0)

    assert jacobian.shape == (2, 2)
    assert np.allclose(jacobian[0], [0.6, 0.8])
    assert np.allclose(jacobian[1], [-4.0 / 25.0, 3.0 / 25.0])


def test_range_bearing_jacobian_rejects_origin():
    try:
        range_bearing_jacobian_xy(0.0, 0.0)
    except ValueError as exc:
        assert "origin" in str(exc)
    else:
        raise AssertionError("origin should be singular")


def test_markdown_report_contains_core_fields_and_caveats():
    obs, crlb = cv_position_crlb(dt=0.05, position_std_m=0.05, horizon_steps=4)
    text = format_markdown(obs, crlb)

    assert "Observable" in text
    assert "CRLB standard deviations" in text
    assert "ASSUMES_WHITE_NOISE" in text
    assert "INVALID_IF_NOISE_IS_COLORED" in text
    assert str(obs.rank) in text
    assert all(math.isfinite(v) for v in crlb.std)
