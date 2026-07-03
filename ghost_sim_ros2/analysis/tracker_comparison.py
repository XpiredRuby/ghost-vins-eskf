"""Offline tracker comparison harness for GHOST.

This module runs the same no-camera scenario/occlusion trials through three
estimators:

* constant-velocity Kalman baseline
* same-dimension IMM tracker
* calibrated multi-hypothesis mode-bank tracker

The output is intentionally CSV-friendly so it can feed the statistics harness
and produce repeatable software-only evidence before hardware validation.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from analysis.ghost_mh_benchmark import BaselineState, cv_predict, cv_update
from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.ghost_mh_scenarios import in_occlusion, scenario_names, truth_state
from analysis.imm_tracker import default_cv_imm


@dataclass(frozen=True)
class TrialSpec:
    scenario: str
    seed: int
    occlusion_start_s: float
    occlusion_duration_s: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare GHOST trackers on shared no-camera trials")
    parser.add_argument("--duration", type=float, default=16.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.035)
    parser.add_argument("--seeds", default="7,11,19")
    parser.add_argument("--scenarios", default=",".join(scenario_names()))
    parser.add_argument("--occlusion-starts", default="4.5,5.5,7.0,8.5,9.5")
    parser.add_argument("--occlusion-durations", default="0.5,1.5,2.5,3.0")
    parser.add_argument("--coverage-radius", type=float, default=0.25)
    parser.add_argument("--accel-temperature", type=float, default=0.30)
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_tracker_comparison.csv"))
    return parser.parse_args()


def parse_float_list(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def parse_str_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def run_trial(args: argparse.Namespace, spec: TrialSpec) -> dict[str, float | int | str]:
    rng = np.random.default_rng(spec.seed)
    dt = 1.0 / args.rate
    times = np.arange(0.0, args.duration, dt)

    cv = BaselineState(np.zeros((4, 1)), np.eye(4) * 1e3)
    imm = default_cv_imm(dt, measurement_std_m=args.noise_std)
    mh = CalibratedModeBankTracker(
        measurement_std_m=args.noise_std,
        accel_temperature=args.accel_temperature,
    )

    errors = {
        "cv": [],
        "imm": [],
        "mh_mean": [],
        "mh_best": [],
        "mh_top3": [],
    }
    mh_top1_hits = 0
    mh_top3_hits = 0
    mh_any_hits = 0
    mh_samples = 0
    imm_maneuver_probs = []

    for t in times:
        truth = truth_state(float(t), spec.scenario)
        visible = not in_occlusion(float(t), spec.occlusion_start_s, spec.occlusion_duration_s)
        measurement = None
        if visible:
            measurement = truth[:2] + rng.normal(0.0, args.noise_std, size=(2, 1))

        if cv.initialized:
            cv_predict(cv, dt)
        if measurement is not None:
            cv_update(cv, measurement, args.noise_std)

        meas_arg = None
        if measurement is not None:
            meas_arg = [float(measurement[0, 0]), float(measurement[1, 0])]
        imm_est = imm.step(meas_arg)
        mh.step(dt, meas_arg)

        if not in_occlusion(float(t), spec.occlusion_start_s, spec.occlusion_duration_s):
            continue

        if cv.initialized:
            errors["cv"].append(float(np.linalg.norm(cv.x[:2] - truth[:2])))

        imm_xy = np.asarray(imm_est.x[:2], dtype=float).reshape(2, 1)
        errors["imm"].append(float(np.linalg.norm(imm_xy - truth[:2])))
        imm_maneuver_probs.append(float(imm_est.mode_probabilities.get("maneuver_cv", math.nan)))

        mh_est = mh.estimate()
        if not mh_est.initialized:
            continue
        errors["mh_mean"].append(float(np.linalg.norm(mh_est.x[:2] - truth[:2])))

        all_errors = sorted(float(np.linalg.norm(h.x[:2] - truth[:2])) for h in mh.hypotheses)
        top_errors = [
            float(np.linalg.norm(h.x[:2] - truth[:2]))
            for h in mh.top_hypotheses(3)
        ]
        if not all_errors or not top_errors:
            continue

        best_error = all_errors[0]
        top3_error = min(top_errors)
        errors["mh_best"].append(best_error)
        errors["mh_top3"].append(top3_error)
        mh_top1_hits += int(top_errors[0] <= args.coverage_radius)
        mh_top3_hits += int(top3_error <= args.coverage_radius)
        mh_any_hits += int(best_error <= args.coverage_radius)
        mh_samples += 1

    cv_rmse = rmse(errors["cv"])
    imm_rmse = rmse(errors["imm"])
    mh_mean_rmse = rmse(errors["mh_mean"])
    mh_best_rmse = rmse(errors["mh_best"])
    mh_top3_rmse = rmse(errors["mh_top3"])

    return {
        "scenario": spec.scenario,
        "seed": spec.seed,
        "occlusion_start_s": spec.occlusion_start_s,
        "occlusion_duration_s": spec.occlusion_duration_s,
        "cv_rmse_m": cv_rmse,
        "imm_rmse_m": imm_rmse,
        "mh_mean_rmse_m": mh_mean_rmse,
        "mh_best_future_rmse_m": mh_best_rmse,
        "mh_top3_future_rmse_m": mh_top3_rmse,
        "mh_top1_coverage_frac": safe_frac(mh_top1_hits, mh_samples),
        "mh_top3_coverage_frac": safe_frac(mh_top3_hits, mh_samples),
        "mh_any_coverage_frac": safe_frac(mh_any_hits, mh_samples),
        "mean_imm_maneuver_prob": mean(imm_maneuver_probs),
        "imm_beats_cv": int(math.isfinite(imm_rmse) and math.isfinite(cv_rmse) and imm_rmse < cv_rmse),
        "mh_mean_beats_cv": int(math.isfinite(mh_mean_rmse) and math.isfinite(cv_rmse) and mh_mean_rmse < cv_rmse),
        "mh_top3_beats_cv": int(math.isfinite(mh_top3_rmse) and math.isfinite(cv_rmse) and mh_top3_rmse < cv_rmse),
    }


def run_comparison(args: argparse.Namespace) -> list[dict[str, float | int | str]]:
    rows = []
    for scenario in parse_str_list(args.scenarios):
        for seed in parse_int_list(args.seeds):
            for start in parse_float_list(args.occlusion_starts):
                for duration in parse_float_list(args.occlusion_durations):
                    rows.append(run_trial(args, TrialSpec(scenario, seed, start, duration)))
    return rows


def rmse(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return math.nan
    return float(math.sqrt(sum(v * v for v in finite) / len(finite)))


def mean(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        return math.nan
    return float(sum(finite) / len(finite))


def safe_frac(num: int, den: int) -> float:
    return math.nan if den <= 0 else float(num) / float(den)


def write_rows(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, float | int | str]]) -> None:
    total = len(rows)
    imm_wins = sum(int(row["imm_beats_cv"]) for row in rows)
    mh_mean_wins = sum(int(row["mh_mean_beats_cv"]) for row in rows)
    mh_top3_wins = sum(int(row["mh_top3_beats_cv"]) for row in rows)
    print(f"cases: {total}")
    print(f"IMM point estimate beats CV: {imm_wins}/{total}")
    print(f"MH mean estimate beats CV: {mh_mean_wins}/{total}")
    print(f"MH top-3 future beats CV: {mh_top3_wins}/{total}")
    print(f"mean CV RMSE: {mean([float(row['cv_rmse_m']) for row in rows]):.4f} m")
    print(f"mean IMM RMSE: {mean([float(row['imm_rmse_m']) for row in rows]):.4f} m")
    print(f"mean MH top-3 RMSE: {mean([float(row['mh_top3_future_rmse_m']) for row in rows]):.4f} m")


def main() -> None:
    args = parse_args()
    rows = run_comparison(args)
    out = Path(args.out).expanduser()
    write_rows(out, rows)
    print(f"saved: {out}")
    print_summary(rows)


if __name__ == "__main__":
    main()
