"""Measurement covariance utilities for GHOST AprilTag pose logs.

This module compares three covariance estimates:

1. first-order pinhole reference from calibration and standoff distance,
2. empirical covariance from a stationary pose log, and
3. optional Jacobian-propagated covariance from a PnP/projectPoints residual model.

The empirical stationary logs observed so far are colored/drift-dominated, so
white-noise assumptions are explicitly warned where they are used.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


WHITE_NOISE_WARNING = (
    "This covariance calculation treats residuals as independent white noise. "
    "Existing GHOST stationary AprilTag logs indicate colored low-frequency drift, "
    "so this result is a reference model, not a validated live measurement R."
)


@dataclass(frozen=True)
class CovarianceEstimate:
    """Labeled covariance estimate with assumptions."""

    method: str
    covariance_m2: list[list[float]]
    std_m: list[float]
    assumptions: list[str]
    includes_colored_noise: bool
    sample_count: int | None = None


def pinhole_position_covariance(
    fx_px: float,
    fy_px: float,
    reprojection_rms_px: float,
    standoff_m: float,
    depth_std_m: float | None = None,
    warn_white_assumption: bool = True,
) -> CovarianceEstimate:
    """First-order position covariance from pinhole projection.

    Lateral small-angle model:
        sigma_x ~= z * sigma_px / fx
        sigma_y ~= z * sigma_px / fy

    Depth is not observable from a single bearing measurement alone. If no
    explicit depth standard deviation is provided, this function uses the same
    angular scale with the mean focal length as a reference placeholder and
    labels that assumption in the output.
    """
    _require_positive("fx_px", fx_px)
    _require_positive("fy_px", fy_px)
    _require_nonnegative("reprojection_rms_px", reprojection_rms_px)
    _require_positive("standoff_m", standoff_m)

    if warn_white_assumption:
        warnings.warn(WHITE_NOISE_WARNING, RuntimeWarning, stacklevel=2)

    sigma_x = standoff_m * reprojection_rms_px / fx_px
    sigma_y = standoff_m * reprojection_rms_px / fy_px
    assumptions = [
        "small-angle pinhole lateral propagation",
        "reprojection RMS used as pixel noise scale",
        "does not model low-frequency pose drift or temporal correlation",
    ]

    if depth_std_m is None:
        f_mean = 0.5 * (fx_px + fy_px)
        sigma_z = standoff_m * reprojection_rms_px / f_mean
        assumptions.append("depth standard deviation approximated using mean focal length reference scale")
    else:
        _require_nonnegative("depth_std_m", depth_std_m)
        sigma_z = depth_std_m
        assumptions.append("depth standard deviation supplied externally")

    covariance = np.diag([sigma_x**2, sigma_y**2, sigma_z**2])
    return _estimate(
        method="pinhole_first_order",
        covariance=covariance,
        assumptions=assumptions,
        includes_colored_noise=False,
    )


def empirical_covariance_from_pose_log(path: str | Path, detrend: bool = False) -> CovarianceEstimate:
    """Compute empirical x/y/z covariance from a stationary CSV log.

    Input CSV columns must include ``t,x,y,z``. The result may include colored
    drift, lighting changes, camera auto-control drift, and setup vibration.
    That is useful for live-system characterization but should not be confused
    with white sensor covariance.
    """
    t, xyz = load_pose_log(path)
    values = xyz.copy()
    assumptions = [
        "stationary target log",
        "sample covariance over measured pose samples",
        "may include colored noise, drift, bias wander, and setup motion",
    ]

    if detrend:
        values = detrend_linear_xyz(t, values)
        assumptions.append("linear trend removed before covariance calculation")
    else:
        assumptions.append("no detrending applied")

    covariance = np.cov(values, rowvar=False, ddof=1)
    return _estimate(
        method="empirical_stationary_log_detrended" if detrend else "empirical_stationary_log_raw",
        covariance=covariance,
        assumptions=assumptions,
        includes_colored_noise=True,
        sample_count=int(values.shape[0]),
    )


def jacobian_propagated_pose_covariance(
    residual_jacobian: np.ndarray,
    pixel_sigma_px: float,
    parameter_indices: list[int] | None = None,
    warn_white_assumption: bool = True,
) -> CovarianceEstimate:
    """Approximate pose covariance from a residual Jacobian.

    For a least-squares residual model with residual Jacobian J and IID pixel
    residual variance sigma^2, parameter covariance is approximated as:

        Cov(theta) ~= sigma^2 * pinv(J.T @ J)

    If ``parameter_indices`` is provided, the returned covariance is sliced to
    those parameters. For solvePnP/projectPoints workflows, callers should pass
    the indices corresponding to the desired pose components.
    """
    jacobian = np.asarray(residual_jacobian, dtype=float)
    if jacobian.ndim != 2:
        raise ValueError("residual_jacobian must be a 2D array")
    if jacobian.shape[0] < jacobian.shape[1]:
        raise ValueError("residual_jacobian should have at least as many residual rows as parameter columns")
    _require_nonnegative("pixel_sigma_px", pixel_sigma_px)

    if warn_white_assumption:
        warnings.warn(WHITE_NOISE_WARNING, RuntimeWarning, stacklevel=2)

    normal = jacobian.T @ jacobian
    covariance = (pixel_sigma_px**2) * np.linalg.pinv(normal)
    assumptions = [
        "linearized residual model",
        "IID white pixel residuals",
        "covariance computed as sigma^2 * pinv(J.T @ J)",
        "does not model colored temporal pose drift",
    ]

    if parameter_indices is not None:
        idx = np.asarray(parameter_indices, dtype=int)
        covariance = covariance[np.ix_(idx, idx)]
        assumptions.append(f"sliced to parameter indices {list(map(int, idx))}")

    return _estimate(
        method="jacobian_propagated",
        covariance=covariance,
        assumptions=assumptions,
        includes_colored_noise=False,
    )


def compare_covariance_estimates(estimates: list[CovarianceEstimate]) -> dict[str, dict]:
    """Return estimates side by side as a JSON-serializable dictionary."""
    return {estimate.method: asdict(estimate) for estimate in estimates}


def format_markdown(estimates: list[CovarianceEstimate]) -> str:
    """Format covariance estimates as a Markdown report block."""
    lines = [
        "## Measurement Covariance Comparison",
        "",
        "> Caveat: pinhole and Jacobian covariance estimates use white-residual reference assumptions. "
        "Empirical stationary covariance can include colored drift and should be interpreted separately.",
        "",
    ]
    for estimate in estimates:
        lines.extend(
            [
                f"### {estimate.method}",
                "",
                f"- Standard deviations: `{_fmt_vector(estimate.std_m)} m`",
                f"- Includes colored/noise drift terms: `{estimate.includes_colored_noise}`",
            ]
        )
        if estimate.sample_count is not None:
            lines.append(f"- Samples: `{estimate.sample_count}`")
        lines.append("- Assumptions:")
        for assumption in estimate.assumptions:
            lines.append(f"  - {assumption}")
        lines.append("- Covariance matrix m^2:")
        for row in estimate.covariance_m2:
            lines.append(f"  - `{_fmt_vector(row)}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_pose_log(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    rows: list[tuple[float, float, float, float]] = []
    with Path(path).expanduser().open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"t", "x", "y", "z"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValueError(f"CSV must contain columns {sorted(required)}; got {reader.fieldnames}")
        for row in reader:
            rows.append((float(row["t"]), float(row["x"]), float(row["y"]), float(row["z"])))

    if len(rows) < 2:
        raise ValueError("Need at least two pose samples for empirical covariance")

    rows.sort(key=lambda r: r[0])
    t = np.asarray([r[0] for r in rows], dtype=float)
    t = t - t[0]
    xyz = np.asarray([[r[1], r[2], r[3]] for r in rows], dtype=float)
    return t, xyz


def detrend_linear_xyz(t: np.ndarray, xyz: np.ndarray) -> np.ndarray:
    out = np.empty_like(xyz, dtype=float)
    for col in range(xyz.shape[1]):
        coeff = np.polyfit(t, xyz[:, col], 1)
        out[:, col] = xyz[:, col] - np.polyval(coeff, t)
    return out


def _estimate(
    method: str,
    covariance: np.ndarray,
    assumptions: list[str],
    includes_colored_noise: bool,
    sample_count: int | None = None,
) -> CovarianceEstimate:
    covariance = np.asarray(covariance, dtype=float)
    if covariance.ndim != 2 or covariance.shape[0] != covariance.shape[1]:
        raise ValueError("covariance must be square")
    std = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    return CovarianceEstimate(
        method=method,
        covariance_m2=covariance.tolist(),
        std_m=std.tolist(),
        assumptions=assumptions,
        includes_colored_noise=includes_colored_noise,
        sample_count=sample_count,
    )


def _require_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be positive and finite")


def _require_nonnegative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be non-negative and finite")


def _fmt_vector(values: list[float]) -> str:
    return "[" + ", ".join(f"{float(v):.6e}" for v in values) + "]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare GHOST AprilTag measurement covariance estimates.")
    parser.add_argument("--csv", type=Path, help="Stationary pose CSV with columns t,x,y,z.")
    parser.add_argument("--fx", type=float, default=487.694, help="Camera fx in pixels.")
    parser.add_argument("--fy", type=float, default=489.393, help="Camera fy in pixels.")
    parser.add_argument("--rms", type=float, default=0.648, help="Reprojection RMS in pixels.")
    parser.add_argument("--standoff", type=float, required=True, help="Tag standoff distance in meters.")
    parser.add_argument("--depth-std", type=float, default=None, help="Optional external depth std in meters.")
    parser.add_argument("--detrend", action="store_true", help="Also report detrended empirical covariance.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown instead of JSON.")
    args = parser.parse_args(argv)

    estimates = [
        pinhole_position_covariance(
            fx_px=args.fx,
            fy_px=args.fy,
            reprojection_rms_px=args.rms,
            standoff_m=args.standoff,
            depth_std_m=args.depth_std,
        )
    ]
    if args.csv is not None:
        estimates.append(empirical_covariance_from_pose_log(args.csv, detrend=False))
        if args.detrend:
            estimates.append(empirical_covariance_from_pose_log(args.csv, detrend=True))

    if args.markdown:
        print(format_markdown(estimates))
    else:
        print(json.dumps(compare_covariance_estimates(estimates), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
