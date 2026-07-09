import argparse
import csv
import math
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Summarize GHOST-MH no-camera CSV results")
    parser.add_argument("--point-csv", default=str(Path.home() / "ghost_logs" / "ghost_mh_research_benchmark.csv"))
    parser.add_argument("--future-csv", default=str(Path.home() / "ghost_logs" / "ghost_mh_multi_future.csv"))
    parser.add_argument("--out", default=str(Path.home() / "ghost_logs" / "ghost_mh_summary.md"))
    return parser.parse_args()


def read_rows(path: str) -> list[dict[str, str]]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(p)
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


def fnum(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return math.nan


def mean(values: list[float]) -> float:
    vals = [v for v in values if math.isfinite(v)]
    if not vals:
        return math.nan
    return sum(vals) / len(vals)


def count_true(rows: list[dict[str, str]], key: str) -> int:
    return sum(1 for row in rows if row.get(key) in {"1", "True", "true"})


def format_pct(value: float) -> str:
    if not math.isfinite(value):
        return "NA"
    return f"{100.0 * value:.2f}%"


def summarize(point_rows: list[dict[str, str]], future_rows: list[dict[str, str]]) -> str:
    point_cases = len(point_rows)
    future_cases = len(future_rows)
    point_wins = count_true(point_rows, "mode_bank_mh_wins_occlusion")
    best_wins = count_true(future_rows, "mh_best_future_beats_cv")
    top3_wins = count_true(future_rows, "mh_top3_future_beats_cv")

    point_improvement = mean(
        [fnum(row, "mode_bank_mh_vs_cv_occlusion_improvement_frac") for row in point_rows]
    )
    coverage = mean([fnum(row, "mh_future_coverage_frac") for row in future_rows])
    cv_point_rmse = mean([fnum(row, "cv_point_rmse_m") for row in future_rows])
    mh_mean_rmse = mean([fnum(row, "mh_weighted_mean_rmse_m") for row in future_rows])
    mh_best_rmse = mean([fnum(row, "mh_best_future_rmse_m") for row in future_rows])
    mh_top3_rmse = mean([fnum(row, "mh_top3_future_rmse_m") for row in future_rows])

    return f"""# GHOST-MH No-Camera Summary

## Point Estimate

| Metric | Value |
|---|---:|
| Cases | {point_cases} |
| Mode-bank MH point-estimate wins | {point_wins}/{point_cases} |
| Mean mode-bank vs CV point improvement | {format_pct(point_improvement)} |

## Multi-Future Prediction

| Metric | Value |
|---|---:|
| Cases | {future_cases} |
| Best carried future beats CV | {best_wins}/{future_cases} |
| Top-3 carried future beats CV | {top3_wins}/{future_cases} |
| Mean future coverage | {format_pct(coverage)} |
| Mean CV point RMSE | {cv_point_rmse:.4f} m |
| Mean MH weighted-mean RMSE | {mh_mean_rmse:.4f} m |
| Mean MH best-future RMSE | {mh_best_rmse:.4f} m |
| Mean MH top-3-future RMSE | {mh_top3_rmse:.4f} m |

## Interpretation

The current GHOST-MH mode bank is more compelling as a multi-future predictor
than as a single averaged point estimate. The next research step is relative-weight
calibration: the system should make the correct future rise into the top-ranked
hypotheses before reacquisition.
"""


def main():
    args = parse_args()
    point_rows = read_rows(args.point_csv)
    future_rows = read_rows(args.future_csv)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(summarize(point_rows, future_rows))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
