import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analysis.measurement_covariance import (  # noqa: E402
    ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE,
    ASSUMES_WHITE_NOISE,
    MAY_INCLUDE_COLORED_COMPONENTS,
    estimate_empirical_stationary_r,
    estimate_jacobian_propagated_r,
    estimate_pinhole_lateral_r,
)


def write_pose_csv(path, t, xyz):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "x", "y", "z"])
        for ti, row in zip(t, xyz):
            writer.writerow([ti, row[0], row[1], row[2]])


def test_pinhole_r_matches_lateral_formula():
    estimate = estimate_pinhole_lateral_r(
        fx_px=500.0,
        fy_px=250.0,
        reprojection_rms_px=1.0,
        standoff_m=2.0,
    )
    cov = estimate.matrix()

    assert estimate.estimator == "pinhole_first_order"
    assert estimate.assumption_label == ASSUMES_WHITE_NOISE
    assert math.isclose(math.sqrt(cov[0, 0]), 2.0 / 500.0)
    assert math.isclose(math.sqrt(cov[1, 1]), 2.0 / 250.0)
    assert cov.shape == (2, 2)


def test_empirical_r_from_stationary_log_defaults_raw(tmp_path):
    rng = np.random.default_rng(12)
    t = np.arange(2000, dtype=float) * 0.05
    true_cov = np.diag([0.002**2, 0.003**2])
    xy = rng.multivariate_normal(mean=[1.0, 2.0], cov=true_cov, size=len(t))
    z = rng.normal(3.0, 0.004, len(t))
    xyz = np.column_stack([xy, z])
    path = tmp_path / "pose.csv"
    write_pose_csv(path, t, xyz)

    estimate = estimate_empirical_stationary_r(path)
    cov = estimate.matrix()

    assert estimate.sample_count == len(t)
    assert estimate.sample_mode == "raw"
    assert estimate.assumption_label == MAY_INCLUDE_COLORED_COMPONENTS
    assert np.allclose(cov, true_cov, rtol=0.20, atol=5e-7)
    assert "RAW stationary-log samples" in estimate.provenance


def test_jacobian_r_identity_case():
    estimate = estimate_jacobian_propagated_r(np.eye(3), pixel_sigma_px=2.0, dimensions=("x", "y", "z"))

    assert estimate.assumption_label == ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE
    assert np.allclose(estimate.matrix(), 4.0 * np.eye(3))
