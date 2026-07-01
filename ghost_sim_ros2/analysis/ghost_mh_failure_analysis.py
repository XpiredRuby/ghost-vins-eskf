import argparse
import csv
import math
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Analyze GHOST-MH no-camera failure cases")
    parser.add_argument(
        "--csv",
        default=str(Path.home() / "ghost_logs" / "ghost_mh_final_no_camera.csv"),
        help="Input CSV from ghost_mh_final_no_camera_benchmark.py",
    )
    parser.add_argument(
        "--out",
        default=str(Path.home() / "ghost_logs" / "ghost_mh_failure_cases.md"),
        help="Markdown report output path",
    )
    parser.add_argument("--limit", type=int, default=12)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def f(row: dict[str, str], key: str) -> float:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return math.nan


def failure_score(row: dict[str, str]) -> float:
    cv = f(row, "cv_point_rmse_m")
    top3 = f(row, "calibrated_top3_future_rmse_m")
    coverage = f(row, "calibrated_top3_coverage_frac")
    if not math.isfinite(cv) or not math.isfinite(top3):
        return math.inf
    coverage_penalty = 0.0 if math.isfinite(coverage) else 1.0
    if math.isfinite(coverage):
        coverage_penalty = max(0.0, 1.0 - coverage)
    return (top3 - cv) + 0.5 * coverage_penalty


def summarize(rows: list[dict[str, str]]) -> dict[str, float]:
    cases = len(rows)
    top3_wins = sum(int(f(row, "calibrated_top3_beats_cv") == 1.0) for row in rows)
    best_wins = sum(int(f(row, "calibrated_best_beats_cv") == 1.0) for row in rows)
    top3_cov = mean(f(row, "calibrated_top3_coverage_frac") for row in rows)
    any_cov = mean(f(row, "calibrated_future_coverage_frac") for row in rows)
    return {
        "cases": cases,
        "best_wins": best_wins,
        "top3_wins": top3_wins,
        "top3_coverage": top3_cov,
        "any_coverage": any_cov,
    }


def mean(values) -> float:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    return math.nan if not vals else sum(vals) / len(vals)


def make_report(rows: list[dict[str, str]], limit: int) -> str:
    summary = summarize(rows)
    failures = sorted(rows, key=failure_score, reverse=True)[:limit]
    lines = [
        "# GHOST-MH Failure Analysis",
        "",
        "This report intentionally focuses on the cases where the current calibrated",
        "multi-hypothesis tracker is weakest. It is meant to guide research work,",
        "not to hide failures behind aggregate metrics.",
        "",
        "## Summary",
        "",
        f"- Cases: {summary['cases']}",
        f"- Best future beats CV: {summary['best_wins']}/{summary['cases']}",
        f"- Top-3 future beats CV: {summary['top3_wins']}/{summary['cases']}",
        f"- Mean top-3 coverage: {100.0 * summary['top3_coverage']:.2f}%",
        f"- Mean any-future coverage: {100.0 * summary['any_coverage']:.2f}%",
        "",
        "## Hardest Cases",
        "",
        "| scenario | seed | start | duration | CV RMSE | top-3 RMSE | top-3 coverage | score |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in failures:
        lines.append(
            "| {scenario} | {seed} | {start:.1f} | {duration:.1f} | {cv:.3f} | "
            "{top3:.3f} | {coverage:.2f} | {score:.3f} |".format(
                scenario=row["scenario"],
                seed=int(float(row["seed"])),
                start=f(row, "occlusion_start_s"),
                duration=f(row, "occlusion_duration_s"),
                cv=f(row, "cv_point_rmse_m"),
                top3=f(row, "calibrated_top3_future_rmse_m"),
                coverage=f(row, "calibrated_top3_coverage_frac"),
                score=failure_score(row),
            )
        )
    lines.extend(
        [
            "",
            "## Research Interpretation",
            "",
            "A top-3 failure means the tracker did not keep a sufficiently accurate",
            "future among its three highest-probability branches. These are the cases",
            "to inspect when tuning priors, adding richer motion modes, or improving",
            "probability calibration.",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    args = parse_args()
    rows = read_rows(Path(args.csv).expanduser())
    report = make_report(rows, args.limit)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(f"saved: {out}")


if __name__ == "__main__":
    main()
