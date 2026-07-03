"""Interacting Multiple Model tracker utilities for GHOST.

The IMM tracker keeps several Kalman filters with shared state dimension and
different process models/noise levels. Each step mixes mode-conditioned states,
predicts each mode, scores each mode by measurement likelihood, and recombines
the posterior into a single estimate plus mode probabilities.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class ImmModel:
    name: str
    f: np.ndarray
    q: np.ndarray


@dataclass(frozen=True)
class ImmEstimate:
    x: list[float]
    p: list[list[float]]
    mode_probabilities: dict[str, float]


class IMMTracker:
    """Same-dimension interacting multiple model Kalman tracker."""

    def __init__(
        self,
        models: list[ImmModel],
        transition: np.ndarray,
        h: np.ndarray,
        r: np.ndarray,
        x0: Iterable[float],
        p0: np.ndarray,
        mode_probabilities: Iterable[float] | None = None,
    ):
        if not models:
            raise ValueError("at least one IMM model is required")
        self.models = models
        self.n_modes = len(models)
        self.transition = _matrix("transition", transition)
        self.h = _matrix("h", h)
        self.r = _matrix("r", r)
        self.mode_states = [_col(x0) for _ in models]
        self.mode_covariances = [_matrix("p0", p0).copy() for _ in models]
        self.mode_probabilities = self._initial_probabilities(mode_probabilities)
        self._validate_shapes()

    def predict(self) -> None:
        mixed_states, mixed_covariances, predicted_probs = self._mix()
        next_states = []
        next_covariances = []
        for model, x, p in zip(self.models, mixed_states, mixed_covariances):
            x_pred = model.f @ x
            p_pred = model.f @ p @ model.f.T + model.q
            next_states.append(x_pred)
            next_covariances.append(_symmetrize(p_pred))
        self.mode_states = next_states
        self.mode_covariances = next_covariances
        self.mode_probabilities = predicted_probs

    def update(self, measurement: Iterable[float]) -> None:
        z = _col(measurement)
        updated_states = []
        updated_covariances = []
        likelihoods = []
        eye = np.eye(self.mode_states[0].shape[0])

        for x, p in zip(self.mode_states, self.mode_covariances):
            innovation = z - self.h @ x
            s = self.h @ p @ self.h.T + self.r
            try:
                inv_s = np.linalg.inv(s)
            except np.linalg.LinAlgError as exc:
                raise ValueError("innovation covariance is singular") from exc
            k = p @ self.h.T @ inv_s
            updated_states.append(x + k @ innovation)
            updated_covariances.append(_symmetrize((eye - k @ self.h) @ p @ (eye - k @ self.h).T + k @ self.r @ k.T))
            likelihoods.append(_gaussian_likelihood(innovation, s))

        weights = self.mode_probabilities * np.asarray(likelihoods, dtype=float)
        total = float(np.sum(weights))
        if total <= 0.0 or not math.isfinite(total):
            weights = np.ones(self.n_modes, dtype=float) / self.n_modes
        else:
            weights = weights / total

        self.mode_states = updated_states
        self.mode_covariances = updated_covariances
        self.mode_probabilities = weights

    def step(self, measurement: Iterable[float] | None) -> ImmEstimate:
        self.predict()
        if measurement is not None:
            self.update(measurement)
        return self.estimate()

    def estimate(self) -> ImmEstimate:
        x, p = self._combined_state()
        return ImmEstimate(
            x=[float(v) for v in x[:, 0]],
            p=_to_list(p),
            mode_probabilities={
                model.name: float(prob)
                for model, prob in zip(self.models, self.mode_probabilities)
            },
        )

    def _mix(self) -> tuple[list[np.ndarray], list[np.ndarray], np.ndarray]:
        # transition[i, j] = probability of previous mode i switching to mode j.
        predicted_probs = self.mode_probabilities @ self.transition
        if np.any(predicted_probs <= 0.0):
            predicted_probs = np.maximum(predicted_probs, 1e-12)
            predicted_probs = predicted_probs / np.sum(predicted_probs)

        mixed_states = []
        mixed_covariances = []
        for j in range(self.n_modes):
            weights = self.mode_probabilities * self.transition[:, j] / predicted_probs[j]
            x_mix = sum(weights[i] * self.mode_states[i] for i in range(self.n_modes))
            p_mix = np.zeros_like(self.mode_covariances[0])
            for i in range(self.n_modes):
                dx = self.mode_states[i] - x_mix
                p_mix += weights[i] * (self.mode_covariances[i] + dx @ dx.T)
            mixed_states.append(x_mix)
            mixed_covariances.append(_symmetrize(p_mix))
        return mixed_states, mixed_covariances, predicted_probs

    def _combined_state(self) -> tuple[np.ndarray, np.ndarray]:
        x = sum(self.mode_probabilities[i] * self.mode_states[i] for i in range(self.n_modes))
        p = np.zeros_like(self.mode_covariances[0])
        for i in range(self.n_modes):
            dx = self.mode_states[i] - x
            p += self.mode_probabilities[i] * (self.mode_covariances[i] + dx @ dx.T)
        return x, _symmetrize(p)

    def _initial_probabilities(self, mode_probabilities: Iterable[float] | None) -> np.ndarray:
        if mode_probabilities is None:
            return np.ones(self.n_modes, dtype=float) / self.n_modes
        probs = np.asarray(list(mode_probabilities), dtype=float)
        if probs.shape != (self.n_modes,):
            raise ValueError("mode_probabilities length must match model count")
        total = float(np.sum(probs))
        if total <= 0.0 or not np.isfinite(probs).all():
            raise ValueError("mode_probabilities must be finite and sum positive")
        return probs / total

    def _validate_shapes(self) -> None:
        state_dim = self.mode_states[0].shape[0]
        if self.transition.shape != (self.n_modes, self.n_modes):
            raise ValueError("transition must be an N x N mode matrix")
        if np.any(self.transition < 0.0):
            raise ValueError("transition probabilities must be nonnegative")
        if not np.allclose(np.sum(self.transition, axis=1), 1.0):
            raise ValueError("each transition row must sum to 1")
        if self.h.shape[1] != state_dim:
            raise ValueError("h columns must match state dimension")
        if self.r.shape != (self.h.shape[0], self.h.shape[0]):
            raise ValueError("r must match measurement dimension")
        for model in self.models:
            if model.f.shape != (state_dim, state_dim):
                raise ValueError("all model F matrices must match state dimension")
            if model.q.shape != (state_dim, state_dim):
                raise ValueError("all model Q matrices must match state dimension")


def cv_model(dt: float, name: str, accel_std_mps2: float) -> ImmModel:
    _require_positive("dt", dt)
    _require_positive("accel_std_mps2", accel_std_mps2)
    f = np.array(
        [
            [1.0, 0.0, dt, 0.0],
            [0.0, 1.0, 0.0, dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )
    q = accel_std_mps2**2 * np.array(
        [
            [dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0],
            [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0],
            [dt**3 / 2.0, 0.0, dt**2, 0.0],
            [0.0, dt**3 / 2.0, 0.0, dt**2],
        ],
        dtype=float,
    )
    return ImmModel(name=name, f=f, q=q)


def default_cv_imm(dt: float, measurement_std_m: float = 0.05) -> IMMTracker:
    models = [
        cv_model(dt, "smooth_cv", accel_std_mps2=0.25),
        cv_model(dt, "maneuver_cv", accel_std_mps2=2.0),
    ]
    transition = np.array([[0.94, 0.06], [0.08, 0.92]], dtype=float)
    h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=float)
    r = np.eye(2) * measurement_std_m**2
    x0 = [0.0, 0.0, 0.0, 0.0]
    p0 = np.diag([0.10, 0.10, 1.0, 1.0])
    return IMMTracker(models, transition, h, r, x0, p0, mode_probabilities=[0.8, 0.2])


def simulate_maneuver(args) -> list[dict[str, float]]:
    rng = np.random.default_rng(args.seed)
    tracker = default_cv_imm(args.dt, measurement_std_m=args.measurement_std)
    x = np.array([[0.0], [0.0], [0.35], [0.0]], dtype=float)
    rows = []
    for k in range(args.steps):
        t = k * args.dt
        ax = args.ax_mps2 if t >= args.maneuver_start else 0.0
        x[0, 0] += x[2, 0] * args.dt + 0.5 * ax * args.dt * args.dt
        x[2, 0] += ax * args.dt
        measurement = x[:2, 0] + rng.normal(0.0, args.measurement_std, size=2)
        estimate = tracker.step(measurement)
        rows.append(
            {
                "t_s": t,
                "truth_x_m": float(x[0, 0]),
                "truth_y_m": float(x[1, 0]),
                "estimate_x_m": estimate.x[0],
                "estimate_y_m": estimate.x[1],
                "smooth_prob": estimate.mode_probabilities["smooth_cv"],
                "maneuver_prob": estimate.mode_probabilities["maneuver_cv"],
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a no-camera IMM maneuver simulation")
    parser.add_argument("--dt", type=float, default=0.05)
    parser.add_argument("--steps", type=int, default=240)
    parser.add_argument("--measurement-std", type=float, default=0.04)
    parser.add_argument("--maneuver-start", type=float, default=4.0)
    parser.add_argument("--ax-mps2", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    rows = simulate_maneuver(args)
    if args.out:
        out = Path(args.out).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"saved: {out}")
    else:
        final = rows[-1]
        print(
            "final maneuver_prob={maneuver_prob:.3f} smooth_prob={smooth_prob:.3f} "
            "estimate_x={estimate_x_m:.3f} truth_x={truth_x_m:.3f}".format(**final)
        )


def _matrix(name: str, value: np.ndarray) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"{name} must be a 2D matrix")
    if not np.isfinite(arr).all():
        raise ValueError(f"{name} contains non-finite values")
    return arr


def _col(values: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float).reshape(-1, 1)
    if not np.isfinite(arr).all():
        raise ValueError("state/measurement contains non-finite values")
    return arr


def _gaussian_likelihood(innovation: np.ndarray, s: np.ndarray) -> float:
    det_s = float(np.linalg.det(s))
    if det_s <= 0.0 or not math.isfinite(det_s):
        return 0.0
    inv_s = np.linalg.inv(s)
    exponent = float(-0.5 * (innovation.T @ inv_s @ innovation)[0, 0])
    norm = 1.0 / (math.sqrt((2.0 * math.pi) ** innovation.shape[0] * det_s))
    return float(norm * math.exp(max(exponent, -80.0)))


def _symmetrize(p: np.ndarray) -> np.ndarray:
    return 0.5 * (p + p.T)


def _require_positive(name: str, value: float) -> None:
    if value <= 0.0 or not math.isfinite(value):
        raise ValueError(f"{name} must be finite and positive")


def _to_list(matrix: np.ndarray) -> list[list[float]]:
    return [[float(v) for v in row] for row in np.asarray(matrix, dtype=float)]


if __name__ == "__main__":
    main()
