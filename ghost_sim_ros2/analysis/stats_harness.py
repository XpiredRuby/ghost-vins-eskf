"""CSV statistics harness for GHOST benchmark evidence.

This module converts benchmark CSV rows into grouped mean/std/stderr/95% CI
summaries. It is intentionally generic so the same tool can summarize no-camera
simulation metrics, measurement-R trials, CRLB sweeps, or later camera logs.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class MetricSummary:
    group: dict[str, str]
    metric: str
    count: int
    mean: float
    std: float
    stderr: float
    ci95_low: float
    ci95_high: float


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).expanduser().open(newline="") as f:
        return list(csv.DictReader(f))


def summarize_rows(
    rows: list[dict[str, str]],
    metrics: list[str],
    group_by: list[str] | None = None,
) -> list[MetricSummary]:
    group_by = group_by or []
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in rows:
        key = tuple(row.get(column, "") for column in group_by)
        grouped.setdefault(key, []).append(row)

    summaries = []
    for key, group_rows in sorted(grouped.items()):
        group = {column: value for column, value in zip(group_by, key)}
        for metric in metrics:
            values = [_parse_float(row.get(metric, "")) for row in group_rows]
            finite = [value for value in values if math.isfinite(value)]
            if not finite:
                continue
            summaries.append(_summarize_metric(group, metric, finite))
    return summaries


def write_summary_csv(path: str | Path, summaries: list[MetricSummary]) -> None:
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["metric", "count", "mean", "std", "stderr", "ci95_low", "ci95_high", "group"]
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            row = asdict(summary)
            row["group"] = _format_group(summary.group)
            writer.writerow(row)


def format_markdown(summaries: list[MetricSummary]) -> str:
    lines = [
        "# GHOST Statistics Summary",
        "",
        "| group | metric | n | mean | std | stderr | 95% CI |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for summary in summaries:
        lines.append(
            "| {group} | {metric} | {n} | {mean:.6g} | {std:.6g} | {stderr:.6g} | "
            "[{low:.6g}, {high:.6g}] |".format(
                group=_format_group(summary.group),
                metric=summary.metric,
                n=summary.count,
                mean=summary.mean,
                std=summary.std,
                stderr=summary.stderr,
                low=summary.ci95_low,
                high=summary.ci95_high,
            )
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize GHOST benchmark CSV metrics")
    parser.add_argument("--csv", required=True, help="input benchmark CSV")
    parser.add_argument("--metrics", required=True, help="comma-separated numeric metric columns")
    parser.add_argument("--group-by", default="", help="comma-separated grouping columns")
    parser.add_argument("--out", default="", help="optional summary CSV output")
    args = parser.parse_args()

    rows = read_csv_rows(args.csv)
    metrics = _split_list(args.metrics)
    groups = _split_list(args.group_by)
    summaries = summarize_rows(rows, metrics, groups)
    if args.out:
        write_summary_csv(args.out, summaries)
        print(f"saved: {Path(args.out).expanduser()}")
    else:
        print(format_markdown(summaries), end="")


def _summarize_metric(group: dict[str, str], metric: str, values: list[float]) -> MetricSummary:
    count = len(values)
    mean = sum(values) / count
    if count > 1:
        variance = sum((value - mean) ** 2 for value in values) / (count - 1)
        std = math.sqrt(max(0.0, variance))
    else:
        std = 0.0
    stderr = std / math.sqrt(count) if count > 0 else math.nan
    half_width = 1.96 * stderr
    return MetricSummary(
        group=dict(group),
        metric=metric,
        count=count,
        mean=mean,
        std=std,
        stderr=stderr,
        ci95_low=mean - half_width,
        ci95_high=mean + half_width,
    )


def _parse_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _split_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def _format_group(group: dict[str, str]) -> str:
    if not group:
        return "all"
    return ", ".join(f"{key}={value}" for key, value in group.items())


if __name__ == "__main__":
    main()
