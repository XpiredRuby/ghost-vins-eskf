"""Observability and CRLB utilities for GHOST tracking models.

This module is hardware-independent and pure Python/NumPy. It implements
finite-horizon observability and R-weighted Gramians for linear CV/CA models,
plus a simplified CRLB for observed linear measurements.

Critical caveat:
The CRLB is a white, independent Gaussian measurement-noise reference bound. It
is useful as a design sanity check, but it is invalid as a final performance
claim if the live pose residuals remain colored. GHOST's empirical logs have
shown colored low-frequency drift, so every CRLB result carries runtime-visible
assumption labels and R-source caveats.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from analysis.measurement_covariance import (
    ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE,
    ASSUMES_WHITE_NOISE as R_ASSUMES_WHITE_NOISE,
    DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R,
    MAY_INCLUDE_COLORED_COMPONENTS,
    CovarianceEstimate,
    estimate_empirical_stationary_r,
    estimate_pinhole_lateral_r,
)

CRLB_ASSUMPTION_LABEL = "ASSUMES_WHITE_NOISE"
CRLB_INVALID_IF_COLORED = "INVALID_IF_NOISE_IS_COLORED"
RAW_EMPIRICAL_R_DEFAULT = "RAW_EMPIRICAL_R_DEFAULT_MAY_INCLUDE_COLORED_COMPONENTS"
DETRENDED_R_DIAGNOSTIC = "DETRENDED_R_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R"
ANALYTICAL_WHITE_R_REFERENCE = "ANALYTICAL_WHITE_R_REFERENCE"


@dataclass(frozen=True)
class ObservabilityResult:
    state_dim: int
    measurement_dim: int
    horizon_steps: int
    rank: int
    observable: bool
    singular_values: list[float]
    min_singular_value: float
    condition_number: float


@dataclass(frozen=True)
class GramianResult:
    state_dim: int
    measurement_dim: int
    horizon_steps: int
    gramian: list[list[float]]
    rank: int
    observable: bool
    singular_values: list[float]
    min_singular_value: float
    condition_number: float
    r_assumption_label: str | None
    r_source_status: str | None
    caveat: str


@dataclass(frozen=True)
class CrlbResult:
    state_dim: int
    horizon_steps: int
    fisher_information: list[list[float]]
    crlb_covariance: list[list[float]]
    std: list[float]
    rank: int
    singular: bool
    assumptions: list[str]
    assumption_label: str = CRLB_ASSUMPTION_LABEL
    validity_status: str = CRLB_INVALID_IF_COLORED
    r_assumption_label: str | None = None
    r_source_status: str | None = None
    r_source: str | None = None
    r_sample_mode: str | None = None
    caveat: str = "CRLB assumes independent white Gaussian residuals; invalid if live residuals are colored."


def cv_state_transition(dt: float) -> np.ndarray:
    """Return a 2D constant-velocity transition for [x, y, vx, vy]."""
    _require_positive("dt", dt)
    return np.array(
        [
            [1.0, 0.0, dt, 0.0],
            [0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def ca_state_transition(dt: float) -> np.ndarray:
    """Return a 2D constant-acceleration transition for [x, y, vx, vy, ax, ay]."""
    _require_positive("dt", dt)
    half_dt2 = 0.5 * dt * dt
    return np.array(
        [
            [1.0, 0.0, dt, 0.0, half_dt2, 0.0],
            [0.0, 1.0, 0.0, dt, 0.0, half_dt2],
            [0.0, 0.0, 1.0, 0.0, dt, 0.0],
            [0.0, 0.0, 0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def position_measurement_matrix(state_dim: int = 4) -> np.ndarray:
    """Return an x/y position measurement matrix for CV or CA state layouts.

    ``state_dim=4`` is [x, y, vx, vy]. ``state_dim=6`` is [x, y, vx, vy, ax, ay].
    """
    if state_dim not in {4, 6}:
        raise ValueError("position_measurement_matrix supports state_dim 4 or 6")
    h = np.zeros((2, state_dim), dtype=float)
    h[0, 0] = 1.0
    h[1, 1] = 1.0
    return h


def observability_matrix(f: np.ndarray, h: np.ndarray, horizon_steps: int | None = None) -> np.ndarray:
    """Stack [H; H F; H F^2; ...] over the requested horizon."""
    f = _matrix("f", f)
    h = _matrix("h", h)
    if f.shape[0] != f.shape[1]:
        raise ValueError("f must be square")
    if h.shape[1] != f.shape[0]:
        raise ValueError("h column count must match f state dimension")
    steps = f.shape[0] if horizon_steps is None else int(horizon_steps)
    if steps <= 0:
        raise ValueError("horizon_steps must be positive")

    blocks = []
    power = np.eye(f.shape[0])
    for _ in range(steps):
        blocks.append(h @ power)
        power = f @ power
    return np.vstack(blocks)


def observability_report(
    f: np.ndarray,
    h: np.ndarray,
    horizon_steps: int | None = None,
    rank_tol: float = 1e-9,
) -> ObservabilityResult:
    """Return finite-horizon observability rank and conditioning."""
    obs = observability_matrix(f, h, horizon_steps)
    singular_values = np.linalg.svd(obs, compute_uv=False)
    state_dim = obs.shape[1]
    rank = int(np.sum(singular_values > rank_tol))
    min_sv = float(singular_values[-1]) if singular_values.size else 0.0
    max_sv = float(singular_values[0]) if singular_values.size else 0.0
    condition = math.inf if min_sv <= rank_tol else max_sv / min_sv
    return ObservabilityResult(
        state_dim=state_dim,
        measurement_dim=int(h.shape[0]),
        horizon_steps=int(horizon_steps or state_dim),
        rank=rank,
        observable=rank == state_dim,
        singular_values=[float(v) for v in singular_values],
        min_singular_value=min_sv,
        condition_number=float(condition),
    )


def r_from_covariance_estimate(estimate: CovarianceEstimate) -> np.ndarray:
    """Extract R from a measurement covariance estimate."""
    return estimate.matrix()


def r_caveat_from_estimate(estimate: CovarianceEstimate | None) -> tuple[str | None, str | None, str | None, str]:
    """Return runtime-visible R caveats for Gramian/CRLB reports."""
    if estimate is None:
        return None, None, None, "R supplied directly; CRLB still assumes independent white Gaussian residuals."

    label = estimate.assumption_label
    status = estimate.status
    mode = estimate.sample_mode
    if label == MAY_INCLUDE_COLORED_COMPONENTS and mode == "raw":
        caveat = (
            f"{RAW_EMPIRICAL_R_DEFAULT}: raw empirical R preserves drift/colored components for filter uncertainty, "
            "but CRLB still assumes independent white Gaussian residuals and is invalid as a final bound if temporal correlation remains."
        )
    elif label == DETRENDED_DIAGNOSTIC_NOT_DEFAULT_FOR_FILTER_R or mode == "detrended":
        caveat = (
            f"{DETRENDED_R_DIAGNOSTIC}: detrended R suppresses linear drift and is not the default filter R. "
            "CRLB remains a white-noise diagnostic reference, not a validated live-data bound."
        )
    elif label in {R_ASSUMES_WHITE_NOISE, ASSUMES_LOCAL_LINEARIZATION_AND_WHITE_PIXEL_NOISE}:
        caveat = (
            f"{ANALYTICAL_WHITE_R_REFERENCE}: R source already assumes white/local residuals. "
            "CRLB is internally consistent only under that same assumption and remains invalid if actual pose residuals are colored."
        )
    else:
        caveat = "Unknown R assumption source; CRLB assumes white independent residuals and should be treated as diagnostic only."
    return label, status, mode, caveat


def weighted_observability_gramian(
    f: np.ndarray,
    h: np.ndarray,
    r: np.ndarray,
    horizon_steps: int,
) -> np.ndarray:
    """R-weighted finite-horizon observability Gramian.

    For measurements ``z_k = H F^k x0 + v_k`` with covariance ``R``, this is:

    ``G = sum_k (H F^k).T R^-1 (H F^k)``

    For the linear observed-measurement case, this equals the Fisher information
    matrix for the initial state under the white independent Gaussian residual
    assumption.
    """
    f = _matrix("f", f)
    h = _matrix("h", h)
    r = _matrix("r", r)
    if f.shape[0] != f.shape[1]:
        raise ValueError("f must be square")
    if h.shape[1] != f.shape[0]:
        raise ValueError("h column count must match f state dimension")
    if r.shape[0] != r.shape[1]:
        raise ValueError("r must be square")
    if r.shape[0] != h.shape[0]:
        raise ValueError("r dimension must match measurement dimension")
    if horizon_steps <= 0:
        raise ValueError("horizon_steps must be positive")

    try:
        r_inv = np.linalg.inv(r)
    except np.linalg.LinAlgError as exc:
        raise ValueError("r must be invertible") from exc

    gramian = np.zeros((f.shape[0], f.shape[0]), dtype=float)
    power = np.eye(f.shape[0])
    for _ in range(horizon_steps):
        hk = h @ power
        gramian += hk.T @ r_inv @ hk
        power = f @ power
    return gramian


def gramian_report(
    f: np.ndarray,
    h: np.ndarray,
    r: np.ndarray,
    horizon_steps: int,
    rank_tol: float = 1e-10,
    r_estimate: CovarianceEstimate | None = None,
) -> GramianResult:
    """Return R-weighted Gramian rank and conditioning."""
    gramian = weighted_observability_gramian(f, h, r, horizon_steps)
    singular_values = np.linalg.svd(gramian, compute_uv=False)
    state_dim = gramian.shape[0]
    rank = int(np.sum(singular_values > rank_tol))
    min_sv = float(singular_values[-1]) if singular_values.size else 0.0
    max_sv = float(singular_values[0]) if singular_values.size else 0.0
    condition = math.inf if min_sv <= rank_tol else max_sv / min_sv
    r_label, r_status, _mode, caveat = r_caveat_from_estimate(r_estimate)
    return GramianResult(
        state_dim=int(state_dim),
        measurement_dim=int(h.shape[0]),
        horizon_steps=int(horizon_steps),
        gramian=_to_list(gramian),
        rank=rank,
        observable=rank == state_dim,
        singular_values=[float(v) for v in singular_values],
        min_singular_value=min_sv,
        condition_number=float(condition),
        r_assumption_label=r_label,
        r_source_status=r_status,
        caveat=caveat,
    )


def fisher_information_matrix(
    f: np.ndarray,
    h: np.ndarray,
    r: np.ndarray,
    horizon_steps: int,
) -> np.ndarray:
    """Alias for the R-weighted Gramian in the linear observed-measurement case."""
    return weighted_observability_gramian(f, h, r, horizon_steps)


def crlb_from_fisher(
    fim: np.ndarray,
    rank_tol: float = 1e-10,
    r_estimate: CovarianceEstimate | None = None,
    horizon_steps: int = 0,
) -> CrlbResult:
    """Invert Fisher information with a pseudo-inverse for singular cases."""
    fim = _matrix("fim", fim)
    if fim.shape[0] != fim.shape[1]:
        raise ValueError("fim must be square")
    singular_values = np.linalg.svd(fim, compute_uv=False)
    rank = int(np.sum(singular_values > rank_tol))
    singular = rank < fim.shape[0]
    crlb = np.linalg.pinv(fim, rcond=rank_tol)
    diag = np.clip(np.diag(crlb), 0.0, None)
    r_label, r_status, r_mode, caveat = r_caveat_from_estimate(r_estimate)
    return CrlbResult(
        state_dim=int(fim.shape[0]),
        horizon_steps=int(horizon_steps),
        fisher_information=_to_list(fim),
        crlb_covariance=_to_list(crlb),
        std=[float(math.sqrt(v)) for v in diag],
        rank=rank,
        singular=singular,
        assumptions=[
            "linearized observed-measurement model",
            "unbiased estimator reference bound",
            "independent Gaussian measurement residuals with covariance R",
            "ASSUMES_WHITE_NOISE -- INVALID IF NOISE IS COLORED",
            "pseudo-inverse used if Fisher information is singular",
        ],
        assumption_label=CRLB_ASSUMPTION_LABEL,
        validity_status=CRLB_INVALID_IF_COLORED,
        r_assumption_label=r_label,
        r_source_status=r_status,
        r_source=r_estimate.estimator if r_estimate is not None else None,
        r_sample_mode=r_mode,
        caveat=caveat,
    )


def linear_crlb(
    f: np.ndarray,
    h: np.ndarray,
    r: np.ndarray,
    horizon_steps: int,
    rank_tol: float = 1e-10,
    r_estimate: CovarianceEstimate | None = None,
) -> CrlbResult:
    """Compute finite-horizon CRLB for a linear measurement model.

    This is a simplified observed-measurement CRLB. It assumes independent white
    Gaussian residuals and is invalid as a final claim if actual pose residuals
    are colored. The returned dataclass exposes this caveat at runtime.
    """
    fim = fisher_information_matrix(f, h, r, horizon_steps)
    return crlb_from_fisher(fim, rank_tol=rank_tol, r_estimate=r_estimate, horizon_steps=horizon_steps)


def linear_crlb_from_covariance_estimate(
    f: np.ndarray,
    h: np.ndarray,
    r_estimate: CovarianceEstimate,
    horizon_steps: int,
    rank_tol: float = 1e-10,
) -> CrlbResult:
    """Compute CRLB using a labeled CovarianceEstimate as R."""
    return linear_crlb(f, h, r_from_covariance_estimate(r_estimate), horizon_steps, rank_tol, r_estimate)


def cv_position_crlb(dt: float, position_std_m: float, horizon_steps: int) -> tuple[ObservabilityResult, CrlbResult]:
    """Convenience wrapper for 2D CV state observed by x/y measurements."""
    _require_positive("position_std_m", position_std_m)
    f = cv_state_transition(dt)
    h = position_measurement_matrix(4)
    r = np.eye(2) * position_std_m**2
    return observability_report(f, h, horizon_steps), linear_crlb(f, h, r, horizon_steps)


def cv_position_crlb_from_covariance_estimate(
    dt: float,
    r_estimate: CovarianceEstimate,
    horizon_steps: int,
) -> tuple[ObservabilityResult, CrlbResult]:
    """CV x/y CRLB using a labeled measurement covariance estimate.

    Use ``estimate_empirical_stationary_r(..., sample_mode='raw')`` by default
    for empirical logs. Passing a detrended estimate is allowed only as an
    explicitly labeled diagnostic.
    """
    f = cv_state_transition(dt)
    h = position_measurement_matrix(4)
    return observability_report(f, h, horizon_steps), linear_crlb_from_covariance_estimate(f, h, r_estimate, horizon_steps)


def ca_position_crlb_from_covariance_estimate(
    dt: float,
    r_estimate: CovarianceEstimate,
    horizon_steps: int,
) -> tuple[ObservabilityResult, CrlbResult]:
    """CA x/y CRLB using a labeled measurement covariance estimate."""
    f = ca_state_transition(dt)
    h = position_measurement_matrix(6)
    return observability_report(f, h, horizon_steps), linear_crlb_from_covariance_estimate(f, h, r_estimate, horizon_steps)


def empirical_raw_cv_crlb(csv_path: str, dt: float, horizon_steps: int) -> tuple[ObservabilityResult, CrlbResult]:
    """Default empirical path: raw stationary-log R feeds the CV CRLB.

    This function is intentionally raw by default. Raw R preserves actual
    single-measurement uncertainty. CRLB output still warns that the bound assumes
    white independent residuals and is invalid if the raw log is temporally colored.
    """
    r_estimate = estimate_empirical_stationary_r(csv_path, sample_mode="raw", dimensions=("x", "y"))
    return cv_position_crlb_from_covariance_estimate(dt, r_estimate, horizon_steps)


def pinhole_cv_crlb(
    dt: float,
    fx_px: float,
    fy_px: float,
    reprojection_rms_px: float,
    standoff_m: float,
    horizon_steps: int,
) -> tuple[ObservabilityResult, CrlbResult]:
    """CV CRLB using analytical pinhole lateral R."""
    r_estimate = estimate_pinhole_lateral_r(fx_px, fy_px, reprojection_rms_px, standoff_m)
    return cv_position_crlb_from_covariance_estimate(dt, r_estimate, horizon_steps)


def range_bearing_jacobian_xy(x: float, y: float) -> np.ndarray:
    """Jacobian of [range, bearing] with respect to [x, y].

    Bearing is atan2(y, x). The origin is singular and intentionally rejected.
    """
    r2 = float(x) * float(x) + float(y) * float(y)
    if r2 <= 0.0:
        raise ValueError("range-bearing Jacobian is singular at the origin")
    r = math.sqrt(r2)
    return np.array(
        [
            [x / r, y / r],
            [-y / r2, x / r2],
        ],
        dtype=float,
    )


def format_markdown(obs: ObservabilityResult, crlb: CrlbResult) -> str:
    lines = [
        "## Observability + CRLB Report",
        "",
        f"- State dimension: `{obs.state_dim}`",
        f"- Measurement dimension: `{obs.measurement_dim}`",
        f"- Horizon steps: `{obs.horizon_steps}`",
        f"- Observability rank: `{obs.rank}`",
        f"- Observable: `{obs.observable}`",
        f"- Minimum singular value: `{obs.min_singular_value:.6g}`",
        f"- Condition number: `{obs.condition_number:.6g}`",
        f"- CRLB rank: `{crlb.rank}`",
        f"- Fisher singular: `{crlb.singular}`",
        f"- CRLB standard deviations: `{_fmt_vector(crlb.std)}`",
        f"- CRLB assumption label: `{crlb.assumption_label}`",
        f"- CRLB validity status: `{crlb.validity_status}`",
        f"- R assumption label: `{crlb.r_assumption_label}`",
        f"- R sample mode: `{crlb.r_sample_mode}`",
        f"- Caveat: `{crlb.caveat}`",
        "",
        "### Assumptions",
    ]
    for assumption in crlb.assumptions:
        lines.append(f"- {assumption}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="GHOST observability and CRLB reference tool")
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--steps", type=int, default=6)
    parser.add_argument("--position-std", type=float, default=0.05)
    parser.add_argument("--model", choices=["cv", "ca"], default="cv")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    args = parser.parse_args()

    if args.model == "cv":
        obs, crlb = cv_position_crlb(args.dt, args.position_std, args.steps)
    else:
        r = np.eye(2) * args.position_std**2
        f = ca_state_transition(args.dt)
        h = position_measurement_matrix(6)
        obs, crlb = observability_report(f, h, args.steps), linear_crlb(f, h, r, args.steps)

    if args.json:
        print(json.dumps({"observability": asdict(obs), "crlb": asdict(crlb)}, indent=2))
    else:
        print(format_markdown(obs, crlb), end="")


def _matrix(name: str, value: np.ndarray) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be a 2D matrix")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _require_positive(name: str, value: float) -> None:
    if value <= 0.0 or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and positive")


def _to_list(matrix: np.ndarray) -> list[list[float]]:
    return [[float(v) for v in row] for row in np.asarray(matrix, dtype=float)]


def _fmt_vector(values: list[float]) -> str:
    return "[" + ", ".join(f"{float(v):.6g}" for v in values) + "]"


if __name__ == "__main__":
    main()
