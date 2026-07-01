import argparse
import csv
import math
from pathlib import Path

import numpy as np

from analysis.ghost_mh_benchmark import BaselineState, cv_predict, cv_update
from analysis.ghost_mh_mode_bank import ModeBankTracker
from analysis.ghost_mh_research_benchmark import (
    TrialConfig,
    in_occlusion,
    parse_float_list,
    parse_int_list,
    parse_str_list,
    truth_state,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate GHOST-MH as a multi-future predictor")
    parser.add_argument("--duration", type=float, default=16.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.035)
    parser.add_argument("--seeds", default="7,11,19")
    parser.add_argument("--scenarios", default="straight,turn_left,turn_right,evasive_brake")
    parser.add_argument("--occlusion-starts", default="5.5,7.0,8.5,9.5")
    parser.add_argument("--occlusion-durations", default="0.5,1.5,2.5,3.0")
    parser.add_argument("--coverage-radius", type=float, default=0.25)
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_mh_multi_future.csv"))
    return parser.parse_args()


def run_trial(args, config: TrialConfig) -> dict[str, float | str | int]:
    rng = np.random.default_rng(config.seed)
    dt = 1.0 / args.rate
    times = np.arange(0.0, args.duration, dt)
    cv = BaselineState(np.zeros((4, 1)), np.eye(4) * 1e3)
    mh = ModeBankTracker(measurement_std_m=args.noise_std)
    cv_errors = []
    mh_mean_errors = []
    mh_best_errors = []
    mh_top3_errors = []
    coverage_hits = 0
    coverage_total = 0

    for t in times:
        truth = truth_state(float(t), config.scenario)
        visible = not in_occlusion(float(t), config.occlusion_start_s, config.occlusion_duration_s)
        measurement = None
        if visible:
            measurement = truth[:2] + rng.normal(0.0, args.noise_std, size=(2, 1))

        if cv.initialized:
            cv_predict(cv, dt)
        if measurement is not None:
            cv_update(cv, measurement, args.noise_std)

        mh.step(dt, None if measurement is None else [measurement[0, 0], measurement[1, 0]])

        if not in_occlusion(float(t), config.occlusion_start_s, config.occlusion_duration_s):
            continue

        if cv.initialized:
            cv_errors.append(float(np.linalg.norm(cv.x[:2] - truth[:2])))

        est = mh.estimate()
        if est.initialized:
            mh_mean_errors.append(float(np.linalg.norm(est.x[:2] - truth[:2])))
            all_errors = [
                float(np.linalg.norm(hyp.x[:2] - truth[:2]))
                for hyp in mh.hypotheses
            ]
            top3_errors = [
                float(np.linalg.norm(hyp.x[:2] - truth[:2]))
                for hyp in mh.top_hypotheses(3)
            ]
            if all_errors:
                best = min(all_errors)
                mh_best_errors.append(best)
                coverage_hits += int(best <= args.coverage_radius)
                coverage_total += 1
            if top3_errors:
                mh_top3_errors.append(min(top3_errors))

    cv_rmse = rmse(cv_errors)
    mean_rmse = rmse(mh_mean_errors)
    best_rmse = rmse(mh_best_errors)
    top3_rmse = rmse(mh_top3_errors)
    coverage = math.nan if coverage_total == 0 else coverage_hits / coverage_total

    return {
        "scenario": config.scenario,
        "seed": config.seed,
        "occlusion_start_s": config.occlusion_start_s,
        "occlusion_duration_s": config.occlusion_duration_s,
        "cv_point_rmse_m": cv_rmse,
        "mh_weighted_mean_rmse_m": mean_rmse,
        "mh_best_future_rmse_m": best_rmse,
        "mh_top3_future_rmse_m": top3_rmse,
        "mh_future_coverage_frac": coverage,
        "mh_best_future_beats_cv": int(math.isfinite(best_rmse) and best_rmse < cv_rmse),
        "mh_top3_future_beats_cv": int(math.isfinite(top3_rmse) and top3_rmse < cv_rmse),
    }


def rmse(values: list[float]) -> float:
    if not values:
        return math.nan
    return float(math.sqrt(sum(v * v for v in values) / len(values)))


def run_benchmark(args):
    rows = []
    for scenario in parse_str_list(args.scenarios):
        for seed in parse_int_list(args.seeds):
            for start in parse_float_list(args.occlusion_starts):
                for duration in parse_float_list(args.occlusion_durations):
                    rows.append(run_trial(args, TrialConfig(scenario, seed, start, duration)))
    return rows


def main():
    args = parse_args()
    rows = run_benchmark(args)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    best_wins = sum(row["mh_best_future_beats_cv"] for row in rows)
    top3_wins = sum(row["mh_top3_future_beats_cv"] for row in rows)
    coverages = [row["mh_future_coverage_frac"] for row in rows if math.isfinite(row["mh_future_coverage_frac"])]
    print(f"saved: {out}")
    print(f"cases: {len(rows)}")
    print(f"best future beats CV: {best_wins}/{len(rows)}")
    print(f"top-3 future beats CV: {top3_wins}/{len(rows)}")
    print(f"mean future coverage @ {args.coverage_radius:.2f}m: {100.0 * sum(coverages) / len(coverages):.2f}%")


if __name__ == "__main__":
    main()
