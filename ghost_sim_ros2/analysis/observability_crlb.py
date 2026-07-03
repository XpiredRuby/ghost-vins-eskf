"""Observability and CRLB utilities for GHOST tracking models.

This module is hardware-independent. It answers two questions that matter before
running a real camera trial:

1. Is a chosen state/measurement model observable over a finite horizon?
2. What covariance lower bound is implied by the measurement model and R?

The CRLB here is a deterministic linear-Gaussian reference bound for the initial
state over a measurement horizon. It is not a replacement for empirical colored
noise validation; it is a design sanity check.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass

import numpy as np


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
class CrlbResult:
    state_dim: int
    horizon_steps: int
    fisher_information: list[list[float]]
    crlb_covariance: list[list[float]]
    std: list[float]
    rank: int
    singular: bool
    assumptions: list[str]


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


def position_measurement_matrix() -> np.ndarray:
    """Return an x/y position measurement matrix for [x, y, vx, vy]."""
    return np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)


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
    condition = math.inf if min_sv <= 0.0 else max_sv / min_sv
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


def fisher_information_matrix(
    f: np.ndarray,
    h: np.ndarray,
    r: np.ndarray,
    horizon_steps: int,
) -> np.ndarray:
    """Fisher information for initial state from linear measurements.

    Measurements follow z_k = H F^k x_0 + noise, noise covariance R.
    """
    f = _matrix("f", f)
    h = _matrix("h", h)
    r = _matrix("r", r)
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

    fim = np.zeros((f.shape[0], f.shape[0]), dtype=float)
    power = np.eye(f.shape[0])
    for _ in range(horizon_steps):
        hk = h @ power
        fim += hk.T @ r_inv @ hk
        power = f @ power
    return fim


def crlb_from_fisher(fim: np.ndarray, rank_tol: float = 1e-10) -> CrlbResult:
    """Invert Fisher information with a pseudo-inverse for singular cases."""
    fim = _matrix("fim", fim)
    if fim.shape[0] != fim.shape[1]:
        raise ValueError("fim must be square")
    singular_values = np.linalg.svd(fim, compute_uv=False)
    rank = int(np.sum(singular_values > rank_tol))
    singular = rank < fim.shape[0]
    crlb = np.linalg.pinv(fim, rcond=rank_tol)
    diag = np.clip(np.diag(crlb), 0.0, None)
    return CrlbResult(
        state_dim=int(fim.shape[0]),
        horizon_steps=0,
        fisher_information=_to_list(fim),
        crlb_covariance=_to_list(crlb),
        std=[float(math.sqrt(v)) for v in diag],
        rank=rank,
        singular=singular,
        assumptions=[
            "linearized measurement model",
            "unbiased estimator reference bound",
            "independent Gaussian measurement residuals with covariance R",
            "pseudo-inverse used if Fisher information is singular",
        ],
    )


def linear_crlb(
    f: np.ndarray,
    h: np.ndarray,
    r: np.ndarray,
    horizon_steps: int,
    rank_tol: float = 1e-10,
) -> CrlbResult:
    """Compute finite-horizon CRLB for a linear measurement model."""
    fim = fisher_information_matrix(f, h, r, horizon_steps)
    result = crlb_from_fisher(fim, rank_tol=rank_tol)
    return CrlbResult(
        state_dim=result.state_dim,
        horizon_steps=int(horizon_steps),
        fisher_information=result.fisher_information,
        crlb_covariance=result.crlb_covariance,
        std=result.std,
        rank=result.rank,
        singular=result.singular,
        assumptions=result.assumptions,
    )


def cv_position_crlb(dt: float, position_std_m: float, horizon_steps: int) -> tuple[ObservabilityResult, CrlbResult]:
    """Convenience wrapper for 2D CV state observed by x/y measurements."""
    _require_positive("position_std_m", position_std_m)
    f = cv_state_transition(dt)
    h = position_measurement_matrix()
    r = np.eye(2) * position_std_m**2
    return observability_report(f, h, horizon_steps), linear_crlb(f, h, r, horizon_steps)


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
    parser.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    args = parser.parse_args()

    obs, crlb = cv_position_crlb(args.dt, args.position_std, args.steps)
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
