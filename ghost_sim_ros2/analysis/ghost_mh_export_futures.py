import argparse
import csv
from pathlib import Path

import numpy as np

from analysis.ghost_mh_benchmark import BaselineState, cv_predict, cv_update
from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.ghost_mh_scenarios import in_occlusion, scenario_names, truth_state


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Export GHOST-MH future hypotheses for visualization")
    parser.add_argument("--scenario", default="turn_left", choices=scenario_names())
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.035)
    parser.add_argument("--occlusion-start", type=float, default=5.5)
    parser.add_argument("--occlusion-duration", type=float, default=2.5)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_mh_futures.csv"))
    return parser.parse_args(argv)


def run_export(args) -> list[dict[str, float | int | str]]:
    rng = np.random.default_rng(args.seed)
    dt = 1.0 / args.rate
    times = np.arange(0.0, args.duration, dt)
    cv = BaselineState(np.zeros((4, 1)), np.eye(4) * 1e3)
    tracker = CalibratedModeBankTracker(measurement_std_m=args.noise_std)
    rows = []

    for t in times:
        truth = truth_state(float(t), args.scenario)
        visible = not in_occlusion(float(t), args.occlusion_start, args.occlusion_duration)
        measurement = None
        if visible:
            measurement = truth[:2] + rng.normal(0.0, args.noise_std, size=(2, 1))

        if cv.initialized:
            cv_predict(cv, dt)
        if measurement is not None:
            cv_update(cv, measurement, args.noise_std)

        meas_arg = None if measurement is None else [measurement[0, 0], measurement[1, 0]]
        tracker.step(dt, meas_arg)
        est = tracker.estimate()

        base = {
            "t_s": float(t),
            "scenario": args.scenario,
            "visible": int(visible),
            "truth_x_m": float(truth[0, 0]),
            "truth_y_m": float(truth[1, 0]),
            "cv_x_m": float(cv.x[0, 0]) if cv.initialized else float("nan"),
            "cv_y_m": float(cv.x[1, 0]) if cv.initialized else float("nan"),
            "mh_mean_x_m": float(est.x[0, 0]) if est.initialized else float("nan"),
            "mh_mean_y_m": float(est.x[1, 0]) if est.initialized else float("nan"),
        }
        for rank, hyp in enumerate(tracker.top_hypotheses(args.top_n), start=1):
            err = float(np.linalg.norm(hyp.x[:2] - truth[:2]))
            rows.append(
                {
                    **base,
                    "rank": rank,
                    "model": hyp.model,
                    "weight": float(hyp.weight),
                    "hyp_x_m": float(hyp.x[0, 0]),
                    "hyp_y_m": float(hyp.x[1, 0]),
                    "hyp_vx_mps": float(hyp.x[2, 0]),
                    "hyp_vy_mps": float(hyp.x[3, 0]),
                    "hyp_cov_xx": float(hyp.p[0, 0]),
                    "hyp_cov_xy": float(hyp.p[0, 1]),
                    "hyp_cov_yy": float(hyp.p[1, 1]),
                    "hyp_error_m": err,
                }
            )
    return rows


def main():
    args = parse_args()
    rows = run_export(args)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"saved: {out}")
    print(f"rows: {len(rows)}")


if __name__ == "__main__":
    main()
