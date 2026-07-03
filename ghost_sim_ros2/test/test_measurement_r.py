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


def test_pinhole_r_matches_lateral_formula():
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
    assert math.isclose(estimate.std_m[0], 2.0 / 500.0)
    assert math.isclose(estimate.std_m[1], 2.0 / 250.0)
    assert math.isclose(estimate.std_m[2], 0.10)
    assert not estimate.includes_colored_noise


def test_empirical_r_from_stationary_log(tmp_path):
    rng = np.random.default_rng(12)
    t = np.arange(500, dtype=float) * 0.05
    true_cov = np.diag([0.002**2, 0.003**2, 0.004**2])
    xyz = rng.multivariate_normal(mean=[1.0, 2.0, 3.0], cov=true_cov, size=len(t))
    path = tmp_path / "pose.csv"
    write_pose_csv(path, t, xyz)

    estimate = empirical_covariance_from_pose_log(path)
    cov = np.asarray(estimate.covariance_m2)

    assert estimate.sample_count == len(t)
    assert estimate.includes_colored_noise
    assert np.allclose(np.diag(cov), np.diag(true_cov), rtol=0.35)
    assert np.max(np.abs(cov - np.diag(np.diag(cov)))) < 1.0e-6


def test_jacobian_r_identity_case():
    estimate = jacobian_propagated_pose_covariance(np.eye(3), pixel_sigma_px=2.0, warn_white_assumption=False)

    assert np.allclose(np.asarray(estimate.covariance_m2), 4.0 * np.eye(3))
    assert np.allclose(np.asarray(estimate.std_m), [2.0, 2.0, 2.0])
