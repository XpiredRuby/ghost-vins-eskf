import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from analysis.ghost_mh_engine import MultiHypothesisTracker


@dataclass
class BaselineState:
    x: np.ndarray
    p: np.ndarray
    initialized: bool = False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="No-camera GHOST-MH occlusion benchmark")
    parser.add_argument("--duration", type=float, default=24.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.035)
    parser.add_argument("--occlusion-start", type=float, default=8.0)
    parser.add_argument("--occlusion-duration", type=float, default=2.5)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_mh_benchmark.csv"))
    return parser.parse_args(argv)


def truth_state(t: float) -> np.ndarray:
    """Scripted target with acceleration and a turn before occlusion."""

    if t < 5.0:
        x = 0.35 + 0.32 * t
        y = -0.25 + 0.05 * t
        vx, vy = 0.32, 0.05
    elif t < 11.0:
        tau = t - 5.0
        x = 1.95 + 0.30 * tau - 0.035 * tau * tau
        y = 0.00 + 0.05 * tau + 0.055 * tau * tau
        vx = 0.30 - 0.07 * tau
        vy = 0.05 + 0.11 * tau
    else:
        tau = t - 11.0
        x = 2.49 - 0.12 * tau
        y = 2.28 + 0.58 * tau
        vx, vy = -0.12, 0.58
    return np.array([[x], [y], [vx], [vy]], dtype=float)


def in_occlusion(t: float, start: float, duration: float) -> bool:
    return start <= t < start + duration


def cv_predict(state: BaselineState, dt: float, accel_std: float = 1.2) -> None:
    f = np.array(
        [[1.0, 0.0, dt, 0.0], [0.0, 1.0, 0.0, dt], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]],
        dtype=float,
    )
    q = accel_std * accel_std
    q_mat = q * np.array(
        [[dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0], [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0], [dt**3 / 2.0, 0.0, dt**2, 0.0], [0.0, dt**3 / 2.0, 0.0, dt**2]],
        dtype=float,
    )
    state.x = f @ state.x
    state.p = f @ state.p @ f.T + q_mat


def cv_update(state: BaselineState, measurement: np.ndarray, meas_std: float) -> None:
    if not state.initialized:
        state.x[:] = 0.0
        state.x[0, 0] = measurement[0, 0]
        state.x[1, 0] = measurement[1, 0]
        state.p = np.diag([0.05, 0.05, 1.0, 1.0])
        state.initialized = True
        return

    h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    r = np.eye(2) * meas_std * meas_std
    innovation = measurement - h @ state.x
    s = h @ state.p @ h.T + r
    k = state.p @ h.T @ np.linalg.inv(s)
    eye = np.eye(4)
    state.x = state.x + k @ innovation
    state.p = (eye - k @ h) @ state.p @ (eye - k @ h).T + k @ r @ k.T


def run_benchmark(args):
    rng = np.random.default_rng(args.seed)
    dt = 1.0 / args.rate
    times = np.arange(0.0, args.duration, dt)
    mh = MultiHypothesisTracker(measurement_std_m=args.noise_std)
    cv = BaselineState(np.zeros((4, 1)), np.eye(4) * 1e3)
    last_seen = None
    rows = []

    for t in times:
        truth = truth_state(float(t))
        measurement = None
        visible = not in_occlusion(float(t), args.occlusion_start, args.occlusion_duration)
        if visible:
            measurement = truth[:2] + rng.normal(0.0, args.noise_std, size=(2, 1))
            last_seen = measurement.copy()

        if cv.initialized:
            cv_predict(cv, dt)
        if measurement is not None:
            cv_update(cv, measurement, args.noise_std)

        mh.step(dt, None if measurement is None else [measurement[0, 0], measurement[1, 0]])
        mh_est = mh.estimate()

        hold_err = math.nan if last_seen is None else float(np.linalg.norm(last_seen - truth[:2]))
        cv_err = math.nan if not cv.initialized else float(np.linalg.norm(cv.x[:2] - truth[:2]))
        mh_err = math.nan if not mh_est.initialized else float(np.linalg.norm(mh_est.x[:2] - truth[:2]))
        top = mh.top_hypotheses(1)

        rows.append(
            {
                "t": float(t),
                "visible": int(visible),
                "truth_x": float(truth[0, 0]),
                "truth_y": float(truth[1, 0]),
                "hold_error_m": hold_err,
                "cv_error_m": cv_err,
                "mh_error_m": mh_err,
                "mh_hypotheses": len(mh.hypotheses),
                "mh_top_model": "" if not top else top[0].model,
                "mh_top_weight": math.nan if not top else top[0].weight,
            }
        )
    return rows


def summarize(rows, args) -> dict[str, float]:
    occlusion_rows = [
        r for r in rows if in_occlusion(r["t"], args.occlusion_start, args.occlusion_duration)
    ]
    reacq_window = [
        r
        for r in rows
        if args.occlusion_start + args.occlusion_duration
        <= r["t"]
        < args.occlusion_start + args.occlusion_duration + 1.0
    ]

    def rmse(key: str, sample_rows) -> float:
        vals = [r[key] for r in sample_rows if math.isfinite(r[key])]
        if not vals:
            return math.nan
        return float(math.sqrt(sum(v * v for v in vals) / len(vals)))

    return {
        "occlusion_hold_rmse_m": rmse("hold_error_m", occlusion_rows),
        "occlusion_cv_rmse_m": rmse("cv_error_m", occlusion_rows),
        "occlusion_mh_rmse_m": rmse("mh_error_m", occlusion_rows),
        "reacq_cv_rmse_m": rmse("cv_error_m", reacq_window),
        "reacq_mh_rmse_m": rmse("mh_error_m", reacq_window),
    }


def main():
    args = parse_args()
    rows = run_benchmark(args)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = summarize(rows, args)
    print(f"saved: {out}")
    for key, value in summary.items():
        print(f"{key}: {value:.4f}")


if __name__ == "__main__":
    main()
