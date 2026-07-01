import argparse
import csv
import math
from pathlib import Path
from types import SimpleNamespace

from analysis.ghost_mh_final_no_camera_benchmark import run_benchmark
from analysis.ghost_mh_scenarios import scenario_names


def parse_args():
    parser = argparse.ArgumentParser(description="Sweep GHOST-MH calibration temperatures")
    parser.add_argument("--temperatures", default="0.20,0.30,0.45,0.65,0.90")
    parser.add_argument("--duration", type=float, default=16.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.035)
    parser.add_argument("--seeds", default="7,11,19")
    parser.add_argument("--scenarios", default=",".join(scenario_names()))
    parser.add_argument("--occlusion-starts", default="4.5,5.5,7.0,8.5,9.5")
    parser.add_argument("--occlusion-durations", default="0.5,1.5,2.5,3.0")
    parser.add_argument("--coverage-radius", type=float, default=0.25)
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_mh_calibration_sweep.csv"))
    return parser.parse_args()


def parse_float_list(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def benchmark_args(args, temperature: float):
    return SimpleNamespace(
        duration=args.duration,
        rate=args.rate,
        noise_std=args.noise_std,
        seeds=args.seeds,
        scenarios=args.scenarios,
        occlusion_starts=args.occlusion_starts,
        occlusion_durations=args.occlusion_durations,
        coverage_radius=args.coverage_radius,
        accel_temperature=temperature,
    )


def mean(values) -> float:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    return math.nan if not vals else sum(vals) / len(vals)


def summarize(rows: list[dict[str, float | str | int]], temperature: float) -> dict[str, float | int]:
    cases = len(rows)
    return {
        "accel_temperature": temperature,
        "cases": cases,
        "best_future_wins": sum(int(row["calibrated_best_beats_cv"]) for row in rows),
        "top3_future_wins": sum(int(row["calibrated_top3_beats_cv"]) for row in rows),
        "top1_coverage_frac": mean(row["calibrated_top1_coverage_frac"] for row in rows),
        "top3_coverage_frac": mean(row["calibrated_top3_coverage_frac"] for row in rows),
        "any_future_coverage_frac": mean(row["calibrated_future_coverage_frac"] for row in rows),
        "cv_point_rmse_m": mean(row["cv_point_rmse_m"] for row in rows),
        "calibrated_mean_rmse_m": mean(row["calibrated_mean_rmse_m"] for row in rows),
        "calibrated_top3_future_rmse_m": mean(row["calibrated_top3_future_rmse_m"] for row in rows),
    }


def main():
    args = parse_args()
    summaries = []
    for temperature in parse_float_list(args.temperatures):
        rows = run_benchmark(benchmark_args(args, temperature))
        summary = summarize(rows, temperature)
        summaries.append(summary)
        print(
            "temp={temp:.2f} top3_wins={top3}/{cases} top3_cov={cov:.2f}% "
            "any_cov={any_cov:.2f}%".format(
                temp=temperature,
                top3=summary["top3_future_wins"],
                cases=summary["cases"],
                cov=100.0 * summary["top3_coverage_frac"],
                any_cov=100.0 * summary["any_future_coverage_frac"],
            )
        )

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summaries[0].keys()))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
