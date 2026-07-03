"""CSV acceptance gates for GHOST benchmark evidence.

The benchmark harnesses produce repeatable CSV rows. This module converts those
rows into explicit pass/fail criteria so software claims can be checked in CI or
before a hardware validation session.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    value: float
    threshold: float
    comparator: str

    def format(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"{status} {self.name}: {self.value:.4f} {self.comparator} {self.threshold:.4f}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate GHOST benchmark CSV acceptance gates")
    parser.add_argument("--csv", required=True, help="benchmark CSV from tracker_comparison or MH benchmark")
    parser.add_argument("--min-mh-top3-win-frac", type=float, default=0.55)
    parser.add_argument("--min-mh-top3-coverage", type=float, default=0.70)
    parser.add_argument("--max-mean-cv-rmse", type=float, default=2.0)
    parser.add_argument("--max-mean-mh-top3-rmse", type=float, default=1.0)
    parser.add_argument("--fail-on-violation", action="store_true")
    return parser.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.expanduser().open(newline="") as f:
        return list(csv.DictReader(f))


def evaluate_tracker_comparison(
    rows: Iterable[dict[str, str]],
    *,
    min_mh_top3_win_frac: float = 0.55,
    min_mh_top3_coverage: float = 0.70,
    max_mean_cv_rmse: float = 2.0,
    max_mean_mh_top3_rmse: float = 1.0,
) -> list[GateResult]:
    materialized = list(rows)
    if not materialized:
        raise ValueError("benchmark CSV has no rows")

    mh_top3_win_frac = mean_indicator(materialized, "mh_top3_beats_cv")
    mh_top3_coverage = mean_metric(materialized, "mh_top3_coverage_frac")
    mean_cv_rmse = mean_metric(materialized, "cv_rmse_m")
    mean_mh_top3_rmse = mean_metric(materialized, "mh_top3_future_rmse_m")

    return [
        GateResult(
            "mh_top3_win_frac",
            mh_top3_win_frac >= min_mh_top3_win_frac,
            mh_top3_win_frac,
            min_mh_top3_win_frac,
            ">=",
        ),
        GateResult(
            "mh_top3_coverage",
            mh_top3_coverage >= min_mh_top3_coverage,
            mh_top3_coverage,
            min_mh_top3_coverage,
            ">=",
        ),
        GateResult(
            "mean_cv_rmse_m",
            mean_cv_rmse <= max_mean_cv_rmse,
            mean_cv_rmse,
            max_mean_cv_rmse,
            "<=",
        ),
        GateResult(
            "mean_mh_top3_rmse_m",
            mean_mh_top3_rmse <= max_mean_mh_top3_rmse,
            mean_mh_top3_rmse,
            max_mean_mh_top3_rmse,
            "<=",
        ),
    ]


def mean_indicator(rows: list[dict[str, str]], key: str) -> float:
    values = [parse_float(row.get(key, "")) for row in rows]
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        raise ValueError(f"no finite values for {key}")
    return float(sum(1.0 if v >= 0.5 else 0.0 for v in finite) / len(finite))


def mean_metric(rows: list[dict[str, str]], key: str) -> float:
    values = [parse_float(row.get(key, "")) for row in rows]
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        raise ValueError(f"no finite values for {key}")
    return float(sum(finite) / len(finite))


def parse_float(text: str | None) -> float:
    if text is None or text == "":
        return math.nan
    try:
        return float(text)
    except ValueError:
        return math.nan


def format_report(results: list[GateResult]) -> str:
    lines = ["# GHOST Acceptance Gate", ""]
    lines.extend(result.format() for result in results)
    lines.append("")
    lines.append("Overall: " + ("PASS" if all(result.passed for result in results) else "FAIL"))
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    rows = read_csv_rows(Path(args.csv))
    results = evaluate_tracker_comparison(
        rows,
        min_mh_top3_win_frac=args.min_mh_top3_win_frac,
        min_mh_top3_coverage=args.min_mh_top3_coverage,
        max_mean_cv_rmse=args.max_mean_cv_rmse,
        max_mean_mh_top3_rmse=args.max_mean_mh_top3_rmse,
    )
    print(format_report(results))
    if args.fail_on_violation and not all(result.passed for result in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
