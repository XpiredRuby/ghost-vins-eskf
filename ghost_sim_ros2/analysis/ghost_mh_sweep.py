import argparse
import csv
import math
from pathlib import Path
from types import SimpleNamespace

from analysis.ghost_mh_benchmark import run_benchmark, summarize


def parse_args():
    parser = argparse.ArgumentParser(description="Sweep no-camera GHOST-MH occlusion cases")
    parser.add_argument("--duration", type=float, default=16.0)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--noise-std", type=float, default=0.035)
    parser.add_argument("--seeds", default="7,11,19")
    parser.add_argument("--occlusion-starts", default="6.0,7.0,8.0,9.0,9.5")
    parser.add_argument("--occlusion-durations", default="0.5,1.5,2.5,3.0")
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_mh_sweep.csv"))
    return parser.parse_args()


def parse_float_list(text: str) -> list[float]:
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def parse_int_list(text: str) -> list[int]:
    return [int(item.strip()) for item in text.split(",") if item.strip()]


def run_sweep(args):
    rows = []
    for seed in parse_int_list(args.seeds):
        for start in parse_float_list(args.occlusion_starts):
            for duration in parse_float_list(args.occlusion_durations):
                trial_args = SimpleNamespace(
                    duration=args.duration,
                    rate=args.rate,
                    noise_std=args.noise_std,
                    occlusion_start=start,
                    occlusion_duration=duration,
                    seed=seed,
                    out="",
                )
                summary = summarize(run_benchmark(trial_args), trial_args)
                cv = summary["occlusion_cv_rmse_m"]
                mh = summary["occlusion_mh_rmse_m"]
                improvement = math.nan
                if math.isfinite(cv) and cv > 0.0 and math.isfinite(mh):
                    improvement = (cv - mh) / cv

                rows.append(
                    {
                        "seed": seed,
                        "occlusion_start_s": start,
                        "occlusion_duration_s": duration,
                        **summary,
                        "mh_vs_cv_occlusion_improvement_frac": improvement,
                        "mh_wins_occlusion": int(math.isfinite(improvement) and improvement > 0.0),
                    }
                )
    return rows


def main():
    args = parse_args()
    rows = run_sweep(args)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    wins = sum(row["mh_wins_occlusion"] for row in rows)
    valid = len(rows)
    finite_improvements = [
        row["mh_vs_cv_occlusion_improvement_frac"]
        for row in rows
        if math.isfinite(row["mh_vs_cv_occlusion_improvement_frac"])
    ]
    mean_improvement = sum(finite_improvements) / len(finite_improvements)
    print(f"saved: {out}")
    print(f"cases: {valid}")
    print(f"mh occlusion wins: {wins}/{valid}")
    print(f"mean mh-vs-cv occlusion improvement: {100.0 * mean_improvement:.2f}%")


if __name__ == "__main__":
    main()
