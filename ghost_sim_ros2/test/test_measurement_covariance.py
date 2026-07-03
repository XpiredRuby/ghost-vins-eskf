import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.measurement_covariance import (  # noqa: E402
    ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE,
    ASSUMES_WHITE_NOISE,
    DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R,
    MAY_INCLUDE_COLORED_COMPONENTS,
    estimate_empirical_stationary_r,
    estimate_jacobian_from_projection_fn,
    estimate_jacobian_propagated_r,
    estimate_pinhole_lateral_r,
    finite_difference_projection_jacobian,
    main,
)


def write_pose_csv(path, t, xyz):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "x", "y", "z"])
        for ti, row in zip(t, xyz):
            writer.writerow([ti, row[0], row[1], row[2]])


def test_pinhole_lateral_covariance_matches_first_order_formula():
    estimate = estimate_pinhole_lateral_r(
        fx_px=500.0,
        fy_px=250.0,
        reprojection_rms_px=1.0,
        standoff_m=2.0,
    )
    cov = estimate.matrix()

    assert estimate.estimator == "pinhole_first_order"
    assert estimate.dimensions == ("x", "y")
    assert estimate.assumption_label == ASSUMES_WHITE_NOISE
    assert estimate.status == "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R"
    assert math.isclose(cov[0, 0], (2.0 / 500.0) ** 2)
    assert math.isclose(cov[1, 1], (2.0 / 250.0) ** 2)
    assert cov.shape == (2, 2)
    assert "Does not estimate depth covariance" in estimate.provenance


def test_empirical_covariance_from_stationary_log_uses_raw_by_default(tmp_path):
    rng = np.random.default_rng(12)
    t = np.arange(2000, dtype=float) * 0.05
    true_cov = np.array([[0.002**2, 0.4 * 0.002 * 0.003], [0.4 * 0.002 * 0.003, 0.003**2]])
    xy = rng.multivariate_normal(mean=[1.0, 2.0], cov=true_cov, size=len(t))
    z = rng.normal(3.0, 0.004, len(t))
    xyz = np.column_stack([xy, z])
    path = tmp_path / "pose.csv"
    write_pose_csv(path, t, xyz)

    estimate = estimate_empirical_stationary_r(path)
    cov = estimate.matrix()

    assert estimate.estimator == "empirical_stationary_log"
    assert estimate.sample_mode == "raw"
    assert estimate.dimensions == ("x", "y")
    assert estimate.assumption_label == MAY_INCLUDE_COLORED_COMPONENTS
    assert estimate.sample_count == len(t)
    assert "RAW stationary-log samples" in estimate.provenance
    assert np.allclose(cov, true_cov, rtol=0.20, atol=5e-7)


def test_empirical_raw_covariance_preserves_drift_that_detrending_removes(tmp_path):
    rng = np.random.default_rng(13)
    t = np.arange(1200, dtype=float) * 0.05
    drift = np.column_stack([0.002 * t, -0.001 * t, 0.0005 * t])
    noise = rng.normal(0.0, [0.001, 0.001, 0.001], size=(len(t), 3))
    xyz = drift + noise
    path = tmp_path / "drift.csv"
    write_pose_csv(path, t, xyz)

    raw = estimate_empirical_stationary_r(path, sample_mode="raw", dimensions=("x", "y", "z"))
    detrended = estimate_empirical_stationary_r(path, sample_mode="detrended", dimensions=("x", "y", "z"))

    assert raw.assumption_label == MAY_INCLUDE_COLORED_COMPONENTS
    assert detrended.assumption_label == DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R
    assert np.trace(detrended.matrix()) < 0.05 * np.trace(raw.matrix())
    assert "not the default filter R" in detrended.provenance


def test_jacobian_covariance_matches_pinhole_lateral_case():
    fx = 500.0
    fy = 250.0
    z = 2.0
    sigma_px = 1.0
    jacobian = np.array([[fx / z, 0.0], [0.0, fy / z]], dtype=float)

    estimate = estimate_jacobian_propagated_r(
        jacobian,
        pixel_sigma_px=sigma_px,
        dimensions=("x", "y"),
    )
    cov = estimate.matrix()

    assert estimate.assumption_label == ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE
    assert np.allclose(cov, np.diag([(z * sigma_px / fx) ** 2, (z * sigma_px / fy) ** 2]))
    assert "invalid as a complete noise model if pose residuals remain colored" in estimate.provenance


def test_jacobian_rank_deficiency_is_rejected():
    jacobian = np.array([[1.0, 0.0], [2.0, 0.0]])

    try:
        estimate_jacobian_propagated_r(jacobian, pixel_sigma_px=1.0, dimensions=("x", "y"))
    except ValueError as exc:
        assert "rank-deficient" in str(exc)
    else:
        raise AssertionError("rank-deficient Jacobian should be rejected")


def test_finite_difference_projection_jacobian_and_covariance():
    def projection(state):
        x, y = state
        return np.array([3.0 * x + 2.0 * y, -1.0 * x + 4.0 * y])

    jacobian = finite_difference_projection_jacobian(projection, [0.5, -0.2], step=1e-6)
    expected_j = np.array([[3.0, 2.0], [-1.0, 4.0]])

    assert np.allclose(jacobian, expected_j, atol=1e-8)

    estimate = estimate_jacobian_from_projection_fn(
        projection,
        state=[0.5, -0.2],
        pixel_sigma_px=0.25,
        dimensions=("x", "y"),
    )
    expected_cov = np.linalg.inv((expected_j.T @ expected_j) / (0.25**2))
    assert np.allclose(estimate.matrix(), expected_cov, atol=1e-10)


def test_cli_outputs_json_with_raw_empirical_default(tmp_path):
    rng = np.random.default_rng(15)
    t = np.arange(300, dtype=float) * 0.05
    xyz = rng.normal(0.0, [0.001, 0.002, 0.003], size=(len(t), 3))
    path = tmp_path / "pose.csv"
    out = tmp_path / "r_summary.json"
    write_pose_csv(path, t, xyz)

    rc = main(["--csv", str(path), "--standoff", "0.5", "--json-out", str(out)])

    assert rc == 0
    summary = json.loads(out.read_text())
    assert "pinhole_first_order" in summary
    assert "empirical_stationary_log_raw" in summary
    assert summary["empirical_stationary_log_raw"]["sample_mode"] == "raw"
    assert summary["empirical_stationary_log_raw"]["assumption_label"] == MAY_INCLUDE_COLORED_COMPONENTS


def test_cli_keeps_raw_and_detrended_empirical_reports_separate(tmp_path):
    rng = np.random.default_rng(16)
    t = np.arange(300, dtype=float) * 0.05
    drift = np.column_stack([0.001 * t, -0.001 * t, np.zeros_like(t)])
    xyz = drift + rng.normal(0.0, [0.001, 0.001, 0.001], size=(len(t), 3))
    path = tmp_path / "pose.csv"
    out = tmp_path / "r_summary.json"
    write_pose_csv(path, t, xyz)

    rc = main([
        "--csv",
        str(path),
        "--standoff",
        "0.5",
        "--include-detrended",
        "--json-out",
        str(out),
    ])

    assert rc == 0
    summary = json.loads(out.read_text())
    assert "empirical_stationary_log_raw" in summary
    assert "empirical_stationary_log_detrended" in summary
    assert summary["empirical_stationary_log_raw"]["assumption_label"] == MAY_INCLUDE_COLORED_COMPONENTS
    assert summary["empirical_stationary_log_detrended"]["assumption_label"] == DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R
