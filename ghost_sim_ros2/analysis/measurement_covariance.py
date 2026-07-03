"""Measurement covariance estimators for GHOST-MH.

This module is intentionally pure Python/NumPy. It does not import ROS, rclpy,
OpenCV, camera drivers, or Pi-specific code.

Estimator scope:
- First-order pinhole lateral covariance from fx/fy/reprojection RMS/standoff.
- Empirical covariance from stationary ``t,x,y,z`` logs using the PR #20 noise
  analysis module. The default empirical R uses RAW samples, not detrended
  diagnostics, because R should model the actual single-measurement uncertainty
  seen by a Kalman-style filter.
- Generic Jacobian-propagated pose covariance for a local projection model. This
  is the pure-NumPy equivalent of using a solvePnP/projectPoints Jacobian if the
  AprilTag/PnP stack exposes one later.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Literal, Sequence

import numpy as np

from analysis.stationary_noise_analysis import (
    HARDWARE_STATUS,
    analyze_pose_csv,
    detrend_linear,
    load_pose_csv,
    uniform_resample,
)

ASSUMES_WHITE_NOISE = "ASSUMES_WHITE_NOISE"
MAY_INCLUDE_COLORED_COMPONENTS = "MAY_INCLUDE_COLORED_COMPONENTS"
DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R = "DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R"
ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE = "ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE"

EstimatorName = Literal["pinhole_first_order", "empirical_stationary_log", "jacobian_propagation"]
SampleMode = Literal["raw", "detrended"]


@dataclass(frozen=True)
class CovarianceEstimate:
    """Machine-readable measurement covariance estimate."""

    estimator: EstimatorName
    dimensions: tuple[str, ...]
    covariance: list[list[float]]
    assumption_label: str
    status: str
    provenance: str
    sample_mode: str | None = None
    source: str | None = None
    sample_count: int | None = None
    notes: str = ""

    def matrix(self) -> np.ndarray:
        return np.asarray(self.covariance, dtype=float)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _as_covariance_list(matrix: np.ndarray) -> list[list[float]]:
    m = np.asarray(matrix, dtype=float)
    if m.ndim != 2 or m.shape[0] != m.shape[1]:
        raise ValueError("covariance must be a square 2-D matrix")
    if not np.all(np.isfinite(m)):
        raise ValueError("covariance contains non-finite values")
    return [[float(v) for v in row] for row in m]


def _validate_positive(name: str, value: float) -> float:
    value = float(value)
    if value <= 0.0 or not math.isfinite(value):
        raise ValueError(f"{name} must be positive and finite")
    return value


def estimate_pinhole_lateral_r(
    fx_px: float,
    fy_px: float,
    reprojection_rms_px: float,
    standoff_m: float,
    status: str = HARDWARE_STATUS,
) -> CovarianceEstimate:
    """First-order lateral measurement covariance from a pinhole model.

    The lateral small-angle approximation is:

    ``sigma_x ~= z * sigma_u / fx``
    ``sigma_y ~= z * sigma_v / fy``

    This is a 2-D lateral ``R`` over ``x,y`` only. Depth/range covariance is not
    inferred from this estimator because fx/fy/reprojection RMS/standoff alone do
    not uniquely determine solvePnP depth uncertainty.

    White-noise assumption is explicit and runtime-visible.
    """
    fx = _validate_positive("fx_px", fx_px)
    fy = _validate_positive("fy_px", fy_px)
    rms = _validate_positive("reprojection_rms_px", reprojection_rms_px)
    z = _validate_positive("standoff_m", standoff_m)

    sigma_x_m = z * rms / fx
    sigma_y_m = z * rms / fy
    r = np.diag([sigma_x_m**2, sigma_y_m**2])

    return CovarianceEstimate(
        estimator="pinhole_first_order",
        dimensions=("x", "y"),
        covariance=_as_covariance_list(r),
        assumption_label=ASSUMES_WHITE_NOISE,
        status=status,
        provenance=(
            "First-order pinhole lateral propagation using fx/fy, reprojection RMS, "
            "and standoff distance. Assumes isotropic white pixel reprojection noise. "
            "Does not estimate depth covariance."
        ),
        notes="Use as an analytical starting point only; compare against empirical raw stationary-log R before filter tuning.",
    )


def estimate_empirical_stationary_r(
    csv_path: str | Path,
    sample_mode: SampleMode = "raw",
    dimensions: Sequence[str] = ("x", "y"),
    status: str = HARDWARE_STATUS,
) -> CovarianceEstimate:
    """Estimate empirical measurement covariance from a stationary pose CSV.

    Default ``sample_mode='raw'`` is intentional. A Kalman-style measurement R
    should model the actual single-measurement uncertainty seen by the filter,
    including colored/drift components if they are present in the pose pipeline.
    Detrended covariance is available only as an explicit diagnostic mode and is
    not the default for filter R.
    """
    dims = tuple(dimensions)
    if not dims:
        raise ValueError("dimensions must contain at least one axis")
    if any(d not in {"x", "y", "z"} for d in dims):
        raise ValueError("dimensions must be a subset of ('x', 'y', 'z')")
    if sample_mode not in {"raw", "detrended"}:
        raise ValueError("sample_mode must be 'raw' or 'detrended'")

    t, x, y, z = load_pose_csv(csv_path)
    t_uniform, x_uniform, dt_s = uniform_resample(t, x)
    _tu_y, y_uniform, _dt_y = uniform_resample(t, y, dt_s=dt_s)
    _tu_z, z_uniform, _dt_z = uniform_resample(t, z, dt_s=dt_s)
    axis_values = {"x": x_uniform, "y": y_uniform, "z": z_uniform}

    if sample_mode == "detrended":
        axis_values = {name: detrend_linear(t_uniform, values) for name, values in axis_values.items()}

    samples = np.vstack([axis_values[d] for d in dims]).T
    if samples.shape[0] < 2:
        raise ValueError("Need at least two samples for covariance")
    r = np.cov(samples, rowvar=False, ddof=1)
    if len(dims) == 1:
        r = np.asarray([[float(r)]], dtype=float)

    report = analyze_pose_csv(csv_path)
    if sample_mode == "raw":
        assumption = MAY_INCLUDE_COLORED_COMPONENTS
        provenance = (
            "Empirical covariance from RAW stationary-log samples. This is the default for filter R because it "
            "preserves actual single-measurement uncertainty, including drift/colored components if present. "
            f"Noise analysis status: {report.noise_assumption_status}; detrending status: {report.detrending_status}."
        )
    else:
        assumption = DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R
        provenance = (
            "Empirical covariance from linearly detrended stationary-log samples. This is a diagnostic option, "
            "not the default filter R, because detrending can remove drift that the filter would otherwise need to model. "
            f"Noise analysis status: {report.noise_assumption_status}; detrending status: {report.detrending_status}."
        )

    return CovarianceEstimate(
        estimator="empirical_stationary_log",
        dimensions=dims,
        covariance=_as_covariance_list(np.asarray(r, dtype=float)),
        assumption_label=assumption,
        status=status,
        provenance=provenance,
        sample_mode=sample_mode,
        source=str(csv_path),
        sample_count=int(samples.shape[0]),
        notes="Use raw_* noise-analysis diagnostics for baseline comparability; per-octave Allan slopes should be reviewed before final covariance tuning.",
    )


def estimate_jacobian_propagated_r(
    jacobian_px_per_state: np.ndarray,
    pixel_sigma_px: float,
    dimensions: Sequence[str],
    status: str = HARDWARE_STATUS,
) -> CovarianceEstimate:
    """Propagate white pixel noise through a local projection Jacobian.

    If a future AprilTag/PnP stack exposes the projectPoints/solvePnP Jacobian,
    pass that Jacobian here. For measurement model ``pixel = h(state)`` with
    local Jacobian ``J = dh/dstate`` and pixel covariance ``sigma_px^2 I``, the
    local pose covariance is approximated by:

    ``R_state = inv(J.T @ inv(R_pixel) @ J)``

    This assumes local linearization and white pixel noise; those assumptions are
    explicit in the output.
    """
    j = np.asarray(jacobian_px_per_state, dtype=float)
    if j.ndim != 2:
        raise ValueError("jacobian_px_per_state must be 2-D")
    if j.shape[1] != len(dimensions):
        raise ValueError("Jacobian column count must match dimensions")
    if not np.all(np.isfinite(j)):
        raise ValueError("Jacobian contains non-finite values")
    sigma = _validate_positive("pixel_sigma_px", pixel_sigma_px)
    if np.linalg.matrix_rank(j) < j.shape[1]:
        raise ValueError("Jacobian is rank-deficient; covariance is not observable for all requested dimensions")

    information = (j.T @ j) / (sigma**2)
    covariance = np.linalg.inv(information)

    return CovarianceEstimate(
        estimator="jacobian_propagation",
        dimensions=tuple(dimensions),
        covariance=_as_covariance_list(covariance),
        assumption_label=ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE,
        status=status,
        provenance=(
            "Local Jacobian propagation from pixel noise into state covariance. Equivalent to using a "
            "solvePnP/projectPoints Jacobian if exposed by the AprilTag/PnP stack. Assumes white pixel noise "
            "and local linearity; invalid as a complete noise model if pose residuals remain colored."
        ),
    )


def finite_difference_projection_jacobian(
    projection_fn: Callable[[np.ndarray], np.ndarray],
    state: Sequence[float],
    step: float = 1e-6,
) -> np.ndarray:
    """Numerically estimate a projection Jacobian for tests or adapter code.

    ``projection_fn`` must map a state vector to a flat pixel residual/vector. This
    helper does not call OpenCV and does not require AprilTag code.
    """
    x0 = np.asarray(state, dtype=float)
    y0 = np.asarray(projection_fn(x0), dtype=float).reshape(-1)
    if not np.all(np.isfinite(y0)):
        raise ValueError("projection_fn returned non-finite values")
    h = _validate_positive("step", step)
    j = np.zeros((len(y0), len(x0)), dtype=float)
    for k in range(len(x0)):
        xp = x0.copy()
        xm = x0.copy()
        xp[k] += h
        xm[k] -= h
        yp = np.asarray(projection_fn(xp), dtype=float).reshape(-1)
        ym = np.asarray(projection_fn(xm), dtype=float).reshape(-1)
        j[:, k] = (yp - ym) / (2.0 * h)
    return j


def estimate_jacobian_from_projection_fn(
    projection_fn: Callable[[np.ndarray], np.ndarray],
    state: Sequence[float],
    pixel_sigma_px: float,
    dimensions: Sequence[str],
    step: float = 1e-6,
    status: str = HARDWARE_STATUS,
) -> CovarianceEstimate:
    """Convenience wrapper around finite-difference projection Jacobian."""
    j = finite_difference_projection_jacobian(projection_fn, state, step=step)
    return estimate_jacobian_propagated_r(j, pixel_sigma_px, dimensions=dimensions, status=status)


def estimates_to_dict(estimates: Sequence[CovarianceEstimate]) -> dict[str, dict]:
    return {estimate.estimator: estimate.to_dict() for estimate in estimates}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estimate GHOST measurement covariance R without ROS/hardware dependencies.")
    parser.add_argument("--csv", type=Path, default=None, help="Optional stationary pose CSV with columns t,x,y,z")
    parser.add_argument("--fx", type=float, default=487.694, help="Camera fx in pixels")
    parser.add_argument("--fy", type=float, default=489.393, help="Camera fy in pixels")
    parser.add_argument("--rms", type=float, default=0.6484223428868449, help="Reprojection RMS in pixels")
    parser.add_argument("--standoff", type=float, required=True, help="Standoff distance in meters for pinhole estimate")
    parser.add_argument("--include-detrended", action="store_true", help="Also output detrended empirical covariance as diagnostic only")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional JSON output path")
    args = parser.parse_args(argv)

    estimates: list[CovarianceEstimate] = [
        estimate_pinhole_lateral_r(args.fx, args.fy, args.rms, args.standoff)
    ]
    if args.csv is not None:
        estimates.append(estimate_empirical_stationary_r(args.csv, sample_mode="raw"))
        if args.include_detrended:
            estimates.append(estimate_empirical_stationary_r(args.csv, sample_mode="detrended"))

    output = json.dumps(estimates_to_dict(estimates), indent=2) + "\n"
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
