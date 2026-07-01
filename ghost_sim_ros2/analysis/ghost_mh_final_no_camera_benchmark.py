import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from analysis.ghost_mh_benchmark import BaselineState, cv_predict, cv_update
from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.ghost_mh_mode_bank import ModeBankTracker
from analysis.ghost_mh_scenarios import in_occlusion, scenario_names, truth_state


@dataclass(frozen=True)
class TrialConfig:
    scenario: str
    seed: int
    occlusion_start_s: float
    occlusion_duration_s: float


def parse_args():
    parser = argparse.ArgumentParser(description="Final no-camera GHOST-MH benchmark suite")
    parser.add_argument("--duration", type=float, default=16.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.035)
    parser.add_argument("--seeds", default="7,11,19")
    parser.add_argument("--scenarios", default=",".join(scenario_names()))
    parser.add_argument("--occlusion-starts", default="4.5,5.5,7.0,8.5,9.5")
    parser.add_argument("--occlusion-durations", default="0.5,1.5,2.5,3.0")
    parser.add_argument("--coverage-radius", type=float, default=0.25)
    parser.add_argument("--accel-temperature", type=float, default=0.30)
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_mh_final_no_camera.csv"))
    return parser.parse_args()


def parse_float_list(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def parse_str_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def run_trial(args, config: TrialConfig) -> dict[str, float | str | int]:
    rng = np.random.default_rng(config.seed)
    dt = 1.0 / args.rate
    times = np.arange(0.0, args.duration, dt)
    cv = BaselineState(np.zeros((4, 1)), np.eye(4) * 1e3)
    mode_bank = ModeBankTracker(measurement_std_m=args.noise_std)
    calibrated = CalibratedModeBankTracker(
        measurement_std_m=args.noise_std,
        accel_temperature=args.accel_temperature,
    )

    metrics = {
        "cv_point": [],
        "mode_mean": [],
        "cal_mean": [],
        "mode_best": [],
        "cal_best": [],
        "mode_top3": [],
        "cal_top3": [],
    }
    mode_coverage_hits = 0
    mode_coverage_total = 0
    cal_coverage_hits = 0
    cal_coverage_total = 0
    cal_top1_hits = 0
    cal_top3_hits = 0

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

        meas_arg = None if measurement is None else [measurement[0, 0], measurement[1, 0]]
        mode_bank.step(dt, meas_arg)
        calibrated.step(dt, meas_arg)

        if not in_occlusion(float(t), config.occlusion_start_s, config.occlusion_duration_s):
            continue

        if cv.initialized:
            metrics["cv_point"].append(float(np.linalg.norm(cv.x[:2] - truth[:2])))

        mode_est = mode_bank.estimate()
        if mode_est.initialized:
            metrics["mode_mean"].append(float(np.linalg.norm(mode_est.x[:2] - truth[:2])))
            mode_errors = sorted(
                [float(np.linalg.norm(h.x[:2] - truth[:2])) for h in mode_bank.hypotheses]
            )
            if mode_errors:
                metrics["mode_best"].append(mode_errors[0])
                metrics["mode_top3"].append(min(mode_errors[:3]))
                mode_coverage_hits += int(mode_errors[0] <= args.coverage_radius)
                mode_coverage_total += 1

        cal_est = calibrated.estimate()
        if cal_est.initialized:
            metrics["cal_mean"].append(float(np.linalg.norm(cal_est.x[:2] - truth[:2])))
            cal_all = sorted(
                [float(np.linalg.norm(h.x[:2] - truth[:2])) for h in calibrated.hypotheses]
            )
            cal_top = [
                float(np.linalg.norm(h.x[:2] - truth[:2]))
                for h in calibrated.top_hypotheses(3)
            ]
            if cal_all:
                metrics["cal_best"].append(cal_all[0])
                metrics["cal_top3"].append(min(cal_top))
                cal_coverage_hits += int(cal_all[0] <= args.coverage_radius)
                cal_top1_hits += int(cal_top[0] <= args.coverage_radius)
                cal_top3_hits += int(min(cal_top) <= args.coverage_radius)
                cal_coverage_total += 1

    cv_rmse = rmse(metrics["cv_point"])
    mode_best_rmse = rmse(metrics["mode_best"])
    cal_best_rmse = rmse(metrics["cal_best"])
    cal_top3_rmse = rmse(metrics["cal_top3"])
    return {
        "scenario": config.scenario,
        "seed": config.seed,
        "occlusion_start_s": config.occlusion_start_s,
        "occlusion_duration_s": config.occlusion_duration_s,
        "cv_point_rmse_m": cv_rmse,
        "mode_mean_rmse_m": rmse(metrics["mode_mean"]),
        "calibrated_mean_rmse_m": rmse(metrics["cal_mean"]),
        "mode_best_future_rmse_m": mode_best_rmse,
        "calibrated_best_future_rmse_m": cal_best_rmse,
        "calibrated_top3_future_rmse_m": cal_top3_rmse,
        "mode_future_coverage_frac": safe_frac(mode_coverage_hits, mode_coverage_total),
        "calibrated_future_coverage_frac": safe_frac(cal_coverage_hits, cal_coverage_total),
        "calibrated_top1_coverage_frac": safe_frac(cal_top1_hits, cal_coverage_total),
        "calibrated_top3_coverage_frac": safe_frac(cal_top3_hits, cal_coverage_total),
        "calibrated_best_beats_cv": int(math.isfinite(cal_best_rmse) and cal_best_rmse < cv_rmse),
        "calibrated_top3_beats_cv": int(math.isfinite(cal_top3_rmse) and cal_top3_rmse < cv_rmse),
    }


def rmse(values: list[float]) -> float:
    if not values:
        return math.nan
    return float(math.sqrt(sum(v * v for v in values) / len(values)))


def safe_frac(num: int, den: int) -> float:
    return math.nan if den <= 0 else num / den


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

    best_wins = sum(row["calibrated_best_beats_cv"] for row in rows)
    top3_wins = sum(row["calibrated_top3_beats_cv"] for row in rows)
    top1_cov = mean([row["calibrated_top1_coverage_frac"] for row in rows])
    top3_cov = mean([row["calibrated_top3_coverage_frac"] for row in rows])
    future_cov = mean([row["calibrated_future_coverage_frac"] for row in rows])
    print(f"saved: {out}")
    print(f"cases: {len(rows)}")
    print(f"calibrated best future beats CV: {best_wins}/{len(rows)}")
    print(f"calibrated top-3 future beats CV: {top3_wins}/{len(rows)}")
    print(f"calibrated top-1 coverage @ {args.coverage_radius:.2f}m: {100.0 * top1_cov:.2f}%")
    print(f"calibrated top-3 coverage @ {args.coverage_radius:.2f}m: {100.0 * top3_cov:.2f}%")
    print(f"calibrated any-future coverage @ {args.coverage_radius:.2f}m: {100.0 * future_cov:.2f}%")


def mean(values: list[float]) -> float:
    vals = [v for v in values if math.isfinite(v)]
    return math.nan if not vals else sum(vals) / len(vals)


if __name__ == "__main__":
    main()
