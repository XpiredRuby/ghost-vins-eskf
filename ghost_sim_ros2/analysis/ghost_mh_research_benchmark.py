import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from analysis.ghost_mh_benchmark import BaselineState, cv_predict, cv_update
from analysis.ghost_mh_engine import MultiHypothesisTracker
from analysis.ghost_mh_mode_bank import ModeBankTracker


@dataclass(frozen=True)
class TrialConfig:
    scenario: str
    seed: int
    occlusion_start_s: float
    occlusion_duration_s: float


def parse_args():
    parser = argparse.ArgumentParser(description="Research-grade no-camera GHOST-MH benchmark")
    parser.add_argument("--duration", type=float, default=16.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.035)
    parser.add_argument("--seeds", default="7,11,19")
    parser.add_argument("--scenarios", default="straight,turn_left,turn_right,evasive_brake")
    parser.add_argument("--occlusion-starts", default="5.5,7.0,8.5,9.5")
    parser.add_argument("--occlusion-durations", default="0.5,1.5,2.5,3.0")
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_mh_research_benchmark.csv"))
    return parser.parse_args()


def parse_float_list(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def parse_str_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def truth_state(t: float, scenario: str) -> np.ndarray:
    if scenario == "straight":
        return np.array([[0.35 + 0.36 * t], [-0.18 + 0.03 * t], [0.36], [0.03]], dtype=float)

    if scenario == "turn_left":
        if t < 5.0:
            return np.array([[0.35 + 0.32 * t], [-0.25 + 0.05 * t], [0.32], [0.05]], dtype=float)
        tau = t - 5.0
        return np.array(
            [
                [1.95 + 0.30 * tau - 0.035 * tau * tau],
                [0.00 + 0.05 * tau + 0.055 * tau * tau],
                [0.30 - 0.07 * tau],
                [0.05 + 0.11 * tau],
            ],
            dtype=float,
        )

    if scenario == "turn_right":
        if t < 5.0:
            return np.array([[0.35 + 0.32 * t], [0.35 - 0.04 * t], [0.32], [-0.04]], dtype=float)
        tau = t - 5.0
        return np.array(
            [
                [1.95 + 0.30 * tau - 0.030 * tau * tau],
                [0.15 - 0.04 * tau - 0.060 * tau * tau],
                [0.30 - 0.06 * tau],
                [-0.04 - 0.12 * tau],
            ],
            dtype=float,
        )

    if scenario == "evasive_brake":
        if t < 4.0:
            return np.array([[0.35 + 0.42 * t], [-0.20 + 0.02 * t], [0.42], [0.02]], dtype=float)
        tau = t - 4.0
        vx = max(0.03, 0.42 - 0.16 * tau)
        vy = 0.02 + 0.18 * math.sin(1.2 * tau)
        x = 2.03 + 0.42 * tau - 0.08 * tau * tau
        y = -0.12 + 0.02 * tau + 0.15 * (1.0 - math.cos(1.2 * tau))
        return np.array([[x], [y], [vx], [vy]], dtype=float)

    raise ValueError(f"unknown scenario: {scenario}")


def in_occlusion(t: float, start: float, duration: float) -> bool:
    return start <= t < start + duration


def run_trial(args, config: TrialConfig) -> dict[str, float | str | int]:
    rng = np.random.default_rng(config.seed)
    dt = 1.0 / args.rate
    times = np.arange(0.0, args.duration, dt)
    cv = BaselineState(np.zeros((4, 1)), np.eye(4) * 1e3)
    static_mh = MultiHypothesisTracker(measurement_std_m=args.noise_std)
    mode_bank_mh = ModeBankTracker(measurement_std_m=args.noise_std)
    last_seen = None
    errors = {
        "hold": [],
        "cv": [],
        "static_mh": [],
        "mode_bank_mh": [],
        "reacq_cv": [],
        "reacq_static_mh": [],
        "reacq_mode_bank_mh": [],
    }

    reacq_start = config.occlusion_start_s + config.occlusion_duration_s
    reacq_end = reacq_start + 1.0

    for t in times:
        truth = truth_state(float(t), config.scenario)
        visible = not in_occlusion(float(t), config.occlusion_start_s, config.occlusion_duration_s)
        measurement = None
        if visible:
            measurement = truth[:2] + rng.normal(0.0, args.noise_std, size=(2, 1))
            last_seen = measurement.copy()

        if cv.initialized:
            cv_predict(cv, dt)
        if measurement is not None:
            cv_update(cv, measurement, args.noise_std)

        meas_arg = None if measurement is None else [measurement[0, 0], measurement[1, 0]]
        static_mh.step(dt, meas_arg)
        mode_bank_mh.step(dt, meas_arg)

        if in_occlusion(float(t), config.occlusion_start_s, config.occlusion_duration_s):
            if last_seen is not None:
                errors["hold"].append(float(np.linalg.norm(last_seen - truth[:2])))
            if cv.initialized:
                errors["cv"].append(float(np.linalg.norm(cv.x[:2] - truth[:2])))
            static_est = static_mh.estimate()
            if static_est.initialized:
                errors["static_mh"].append(float(np.linalg.norm(static_est.x[:2] - truth[:2])))
            mode_bank_est = mode_bank_mh.estimate()
            if mode_bank_est.initialized:
                errors["mode_bank_mh"].append(float(np.linalg.norm(mode_bank_est.x[:2] - truth[:2])))

        if reacq_start <= float(t) < reacq_end:
            if cv.initialized:
                errors["reacq_cv"].append(float(np.linalg.norm(cv.x[:2] - truth[:2])))
            static_est = static_mh.estimate()
            if static_est.initialized:
                errors["reacq_static_mh"].append(float(np.linalg.norm(static_est.x[:2] - truth[:2])))
            mode_bank_est = mode_bank_mh.estimate()
            if mode_bank_est.initialized:
                errors["reacq_mode_bank_mh"].append(float(np.linalg.norm(mode_bank_est.x[:2] - truth[:2])))

    row = {
        "scenario": config.scenario,
        "seed": config.seed,
        "occlusion_start_s": config.occlusion_start_s,
        "occlusion_duration_s": config.occlusion_duration_s,
        "hold_occlusion_rmse_m": rmse(errors["hold"]),
        "cv_occlusion_rmse_m": rmse(errors["cv"]),
        "static_mh_occlusion_rmse_m": rmse(errors["static_mh"]),
        "mode_bank_mh_occlusion_rmse_m": rmse(errors["mode_bank_mh"]),
        "cv_reacq_rmse_m": rmse(errors["reacq_cv"]),
        "static_mh_reacq_rmse_m": rmse(errors["reacq_static_mh"]),
        "mode_bank_mh_reacq_rmse_m": rmse(errors["reacq_mode_bank_mh"]),
    }
    row["mode_bank_mh_wins_occlusion"] = int(row["mode_bank_mh_occlusion_rmse_m"] < row["cv_occlusion_rmse_m"])
    row["mode_bank_mh_vs_cv_occlusion_improvement_frac"] = frac_improvement(
        row["cv_occlusion_rmse_m"], row["mode_bank_mh_occlusion_rmse_m"]
    )
    return row


def rmse(values: list[float]) -> float:
    if not values:
        return math.nan
    return float(math.sqrt(sum(v * v for v in values) / len(values)))


def frac_improvement(baseline: float, candidate: float) -> float:
    if not math.isfinite(baseline) or baseline <= 0.0 or not math.isfinite(candidate):
        return math.nan
    return (baseline - candidate) / baseline


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

    wins = sum(row["mode_bank_mh_wins_occlusion"] for row in rows)
    improvements = [
        row["mode_bank_mh_vs_cv_occlusion_improvement_frac"]
        for row in rows
        if math.isfinite(row["mode_bank_mh_vs_cv_occlusion_improvement_frac"])
    ]
    print(f"saved: {out}")
    print(f"cases: {len(rows)}")
    print(f"mode-bank MH occlusion wins: {wins}/{len(rows)}")
    print(f"mean mode-bank-vs-cv improvement: {100.0 * sum(improvements) / len(improvements):.2f}%")


if __name__ == "__main__":
    main()
