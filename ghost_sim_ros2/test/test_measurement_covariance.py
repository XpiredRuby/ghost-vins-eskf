import csv
import math
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.measurement_covariance import (  # noqa: E402
    WHITE_NOISE_WARNING,
    empirical_covariance_from_pose_log,
    jacobian_propagated_pose_covariance,
    pinhole_position_covariance,
)


def write_pose_csv(path, t, xyz):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "x", "y", "z"])
        for ti, row in zip(t, xyz):
            writer.writerow([ti, row[0], row[1], row[2]])


def test_pinhole_covariance_matches_first_order_lateral_formula():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        estimate = pinhole_position_covariance(
            fx_px=500.0,
            fy_px=250.0,
            reprojection_rms_px=1.0,
            standoff_m=2.0,
            depth_std_m=0.10,
        )

    assert any(WHITE_NOISE_WARNING in str(w.message) for w in caught)
    assert estimate.method == "pinhole_first_order"
    assert math.isclose(estimate.std_m[0], 2.0 / 500.0)
    assert math.isclose(estimate.std_m[1], 2.0 / 250.0)
    assert math.isclose(estimate.std_m[2], 0.10)
    assert not estimate.includes_colored_noise


def test_empirical_covariance_from_stationary_log(tmp_path):
    rng = np.random.default_rng(12)
    t = np.arange(500, dtype=float) * 0.05
    true_cov = np.diag([0.002**2, 0.003**2, 0.004**2])
    xyz = rng.multivariate_normal(mean=[1.0, 2.0, 3.0], cov=true_cov, size=len(t))
    path = tmp_path / "pose.csv"
    write_pose_csv(path, t, xyz)

    estimate = empirical_covariance_from_pose_log(path)

    assert estimate.sample_count == len(t)
    assert estimate.includes_colored_noise
    assert np.allclose(np.asarray(estimate.covariance_m2), true_cov, rtol=0.35, atol=1e-8)


def test_empirical_detrending_reduces_linear_drift_variance(tmp_path):
    rng = np.random.default_rng(13)
    t = np.arange(600, dtype=float) * 0.05
    drift = np.column_stack([0.002 * t, -0.001 * t, 0.0005 * t])
    noise = rng.normal(0.0, [0.001, 0.001, 0.001], size=(len(t), 3))
    xyz = drift + noise
    path = tmp_path / "drift.csv"
    write_pose_csv(path, t, xyz)

    raw = empirical_covariance_from_pose_log(path, detrend=False)
    detrended = empirical_covariance_from_pose_log(path, detrend=True)

    assert np.trace(np.asarray(detrended.covariance_m2)) < np.trace(np.asarray(raw.covariance_m2))
    assert "linear trend removed" in " ".join(detrended.assumptions)


def test_jacobian_covariance_identity_case():
    jacobian = np.eye(3)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        estimate = jacobian_propagated_pose_covariance(jacobian, pixel_sigma_px=2.0)

    assert any(WHITE_NOISE_WARNING in str(w.message) for w in caught)
    assert np.allclose(np.asarray(estimate.covariance_m2), 4.0 * np.eye(3))
    assert np.allclose(np.asarray(estimate.std_m), [2.0, 2.0, 2.0])
    assert not estimate.includes_colored_noise


def test_jacobian_covariance_slice():
    jacobian = np.eye(4)
    estimate = jacobian_propagated_pose_covariance(
        jacobian,
        pixel_sigma_px=0.5,
        parameter_indices=[1, 3],
        warn_white_assumption=False,
    )

    assert np.asarray(estimate.covariance_m2).shape == (2, 2)
    assert np.allclose(np.asarray(estimate.covariance_m2), 0.25 * np.eye(2))
