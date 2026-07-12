"""Shared measurement covariance configuration helpers for GHOST live trackers."""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np

CONTROLLED_R_CANDIDATE_STABLE_60S_PENDING_ENGINEER_REVIEW = "CONTROLLED_R_CANDIDATE_STABLE_60S_PENDING_ENGINEER_REVIEW"
SCALAR_MEASUREMENT_STD_FALLBACK = "SCALAR_MEASUREMENT_STD_FALLBACK"
DOES_NOT_VALIDATE_ESTIMATOR_ACCURACY = "DOES_NOT_VALIDATE_ESTIMATOR_ACCURACY"
CONTROLLED_R_CANDIDATE_XY_M2 = (
    (1.1285530537472441e-06, 9.517042606937477e-08),
    (9.517042606937477e-08, 1.396619108865118e-08),
)
CONTROLLED_R_CANDIDATE_DATASET = "controlled_R_direct_01_fixed_15_75_s_n885"
CONTROLLED_R_CANDIDATE_PROVENANCE = (
    "Candidate empirical raw R_xy from the direct calibrated camera -> AprilTag -> solvePnP "
    "stationary dataset controlled_R_direct_01, using the predeclared fixed t=15..75 s window "
    "(n=885, 14.7489 Hz). The source bypasses ROS DDS. It estimates stationary measurement "
    "covariance only, does not prove white noise, and does not validate estimator accuracy or "
    "dynamic performance."
)
SCALAR_R_PROVENANCE = (
    "Isotropic position R from measurement_std_m scalar fallback. Backward-compatible live default; "
    "not report-grade estimator accuracy validation."
)


def _finite(name: str, value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def validate_measurement_r_xy(matrix: Iterable[Iterable[float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    arr = np.asarray([[float(v) for v in row] for row in matrix], dtype=float)
    if arr.shape != (2, 2):
        raise ValueError("measurement R_xy must be 2x2")
    if not np.isfinite(arr).all():
        raise ValueError("measurement R_xy contains nonfinite values")
    if not np.allclose(arr, arr.T, rtol=0.0, atol=1e-18):
        raise ValueError("measurement R_xy must be symmetric")
    if arr[0, 0] <= 0.0 or arr[1, 1] <= 0.0:
        raise ValueError("measurement R_xy xx and yy must be positive")
    eigvals = np.linalg.eigvalsh(arr)
    if float(np.min(eigvals)) < -1e-18:
        raise ValueError("measurement R_xy must be positive semidefinite")
    return ((float(arr[0, 0]), float(arr[0, 1])), (float(arr[1, 0]), float(arr[1, 1])))


def build_measurement_r_xy(
    measurement_std_m: float,
    measurement_r_xx_m2: float | None = None,
    measurement_r_xy_m2: float = 0.0,
    measurement_r_yy_m2: float | None = None,
) -> tuple[tuple[float, float], tuple[float, float]]:
    if measurement_r_xx_m2 is not None and measurement_r_yy_m2 is not None:
        xx = _finite("measurement_r_xx_m2", measurement_r_xx_m2)
        yy = _finite("measurement_r_yy_m2", measurement_r_yy_m2)
        xy = _finite("measurement_r_xy_m2", measurement_r_xy_m2)
        if xx > 0.0 and yy > 0.0:
            return validate_measurement_r_xy(((xx, xy), (xy, yy)))
    std = _finite("measurement_std_m", measurement_std_m)
    if std <= 0.0:
        raise ValueError("measurement_std_m must be positive for scalar fallback")
    var = std * std
    return ((float(var), 0.0), (0.0, float(var)))


def measurement_r_source(
    measurement_covariance_xy: Iterable[Iterable[float]] | None,
    measurement_std_m: float,
) -> str:
    return CONTROLLED_R_CANDIDATE_STABLE_60S_PENDING_ENGINEER_REVIEW if measurement_covariance_xy is not None else SCALAR_MEASUREMENT_STD_FALLBACK


def measurement_r_status(measurement_covariance_xy: Iterable[Iterable[float]] | None) -> str:
    return DOES_NOT_VALIDATE_ESTIMATOR_ACCURACY if measurement_covariance_xy is not None else "BACKWARD_COMPATIBLE_SCALAR_FALLBACK"


def measurement_r_provenance(measurement_covariance_xy: Iterable[Iterable[float]] | None) -> str:
    return CONTROLLED_R_CANDIDATE_PROVENANCE if measurement_covariance_xy is not None else SCALAR_R_PROVENANCE


def covariance_to_list(matrix: Iterable[Iterable[float]]) -> list[list[float]]:
    r = validate_measurement_r_xy(matrix)
    return [[r[0][0], r[0][1]], [r[1][0], r[1][1]]]
