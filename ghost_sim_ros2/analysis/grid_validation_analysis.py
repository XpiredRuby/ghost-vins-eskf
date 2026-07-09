"""Ground-truth grid validation analysis for GHOST AprilTag pose logs."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_TIME_FIELDS = ("t_rel_s", "t", "time_s", "timestamp_s", "stamp_s")
DEFAULT_X_FIELDS = ("x_m", "x", "position.x_m", "position.x", "measured.x_m")
DEFAULT_Y_FIELDS = ("y_m", "y", "position.y_m", "position.y", "measured.y_m")


@dataclass(frozen=True)
class PoseSample:
    t_s: float
    x_m: float
    y_m: float


@dataclass(frozen=True)
class GridPoint:
    point_id: str
    x_true_m: float
    y_true_m: float
    t_start_s: float
    t_end_s: float


def analyze_grid(
    pose_log: Path,
    grid_csv: Path,
    out_dir: Path,
    time_field: str | None = None,
    x_field: str | None = None,
    y_field: str | None = None,
) -> dict[str, Any]:
    samples = read_pose_log(pose_log, time_field=time_field, x_field=x_field, y_field=y_field)
    points = read_grid_csv(grid_csv)
    per_point = [_analyze_point(point, samples) for point in points]
    valid = [row for row in per_point if row["n_samples"] > 0]
    if not valid:
        raise ValueError("No pose samples fell inside any grid point time window")

    bias_x = _mean([row["dx_m"] for row in valid])
    bias_y = _mean([row["dy_m"] for row in valid])
    rmse = math.sqrt(_mean([row["error_m"] ** 2 for row in valid]))
    mean_error = _mean([row["error_m"] for row in valid])
    max_error = max(row["error_m"] for row in valid)

    summary: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pose_log": str(pose_log),
        "grid_csv": str(grid_csv),
        "n_points": len(points),
        "n_points_with_samples": len(valid),
        "aggregate": {
            "bias_x_m": bias_x,
            "bias_y_m": bias_y,
            "rmse_m": rmse,
            "mean_error_m": mean_error,
            "max_error_m": max_error,
        },
        "points": per_point,
        "caveat": (
            "One measured grid trial gives initial accuracy evidence only; it is not full production "
            "validation across lighting, tag pose, calibration drift, occlusion, or target types."
        ),
    }
    write_outputs(summary, out_dir)
    return summary


def read_pose_log(
    path: Path,
    time_field: str | None = None,
    x_field: str | None = None,
    y_field: str | None = None,
) -> list[PoseSample]:
    path = path.expanduser()
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            return [_sample_from_mapping(row, time_field, x_field, y_field) for row in csv.DictReader(f)]

    samples: list[PoseSample] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{lineno}: {exc}") from exc
            samples.append(_sample_from_mapping(obj, time_field, x_field, y_field))
    return samples


def read_grid_csv(path: Path) -> list[GridPoint]:
    required = {"point_id", "x_true_m", "y_true_m", "t_start_s", "t_end_s"}
    with path.expanduser().open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Grid CSV missing required columns: {sorted(missing)}")
        points = [
            GridPoint(
                point_id=str(row["point_id"]),
                x_true_m=_finite_float(row["x_true_m"], "x_true_m"),
                y_true_m=_finite_float(row["y_true_m"], "y_true_m"),
                t_start_s=_finite_float(row["t_start_s"], "t_start_s"),
                t_end_s=_finite_float(row["t_end_s"], "t_end_s"),
            )
            for row in reader
        ]
    for point in points:
        if point.t_end_s <= point.t_start_s:
            raise ValueError(f"Point {point.point_id} has non-positive time window")
    return points


def write_outputs(summary: dict[str, Any], out_dir: Path) -> None:
    out_dir = out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "grid_validation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "grid_validation_summary.md").write_text(format_markdown(summary), encoding="utf-8")


def format_markdown(summary: dict[str, Any]) -> str:
    agg = summary["aggregate"]
    lines = [
        "# Ground Truth Grid Validation Summary",
        "",
        summary["caveat"],
        "",
        "## Aggregate",
        "",
        f"- Points with samples: {summary['n_points_with_samples']} / {summary['n_points']}",
        f"- Bias x: {agg['bias_x_m']:.6g} m",
        f"- Bias y: {agg['bias_y_m']:.6g} m",
        f"- RMSE: {agg['rmse_m']:.6g} m",
        f"- Mean error: {agg['mean_error_m']:.6g} m",
        f"- Max error: {agg['max_error_m']:.6g} m",
        "",
        "## Per-Point Metrics",
        "",
        "| point | n | rate Hz | x true | y true | x mean | y mean | x std | y std | dx | dy | error |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["points"]:
        lines.append(
            "| {point_id} | {n_samples} | {sample_rate_hz:.6g} | {x_true_m:.6g} | {y_true_m:.6g} | "
            "{x_mean_m:.6g} | {y_mean_m:.6g} | {x_std_m:.6g} | {y_std_m:.6g} | "
            "{dx_m:.6g} | {dy_m:.6g} | {error_m:.6g} |".format(**row)
        )
    return "\n".join(lines) + "\n"


def _analyze_point(point: GridPoint, samples: list[PoseSample]) -> dict[str, Any]:
    selected = [sample for sample in samples if point.t_start_s <= sample.t_s <= point.t_end_s]
    xs = [sample.x_m for sample in selected]
    ys = [sample.y_m for sample in selected]
    n = len(selected)
    x_mean = _mean(xs) if xs else math.nan
    y_mean = _mean(ys) if ys else math.nan
    dx = x_mean - point.x_true_m if xs else math.nan
    dy = y_mean - point.y_true_m if ys else math.nan
    duration = point.t_end_s - point.t_start_s
    return {
        **asdict(point),
        "n_samples": n,
        "sample_rate_hz": n / duration if duration > 0 else math.nan,
        "x_mean_m": x_mean,
        "y_mean_m": y_mean,
        "x_std_m": _std(xs),
        "y_std_m": _std(ys),
        "dx_m": dx,
        "dy_m": dy,
        "error_m": math.hypot(dx, dy) if xs and ys else math.nan,
    }


def _sample_from_mapping(
    row: dict[str, Any],
    time_field: str | None,
    x_field: str | None,
    y_field: str | None,
) -> PoseSample:
    return PoseSample(
        t_s=_finite_float(_first_value(row, (time_field,) if time_field else DEFAULT_TIME_FIELDS), "time"),
        x_m=_finite_float(_first_value(row, (x_field,) if x_field else DEFAULT_X_FIELDS), "x"),
        y_m=_finite_float(_first_value(row, (y_field,) if y_field else DEFAULT_Y_FIELDS), "y"),
    )


def _first_value(row: dict[str, Any], fields: tuple[str | None, ...]) -> Any:
    for field in fields:
        if not field:
            continue
        value = _nested_get(row, field)
        if value is not None:
            return value
    raise ValueError(f"None of the fields were found: {[field for field in fields if field]}")


def _nested_get(row: dict[str, Any], field: str) -> Any:
    if field in row:
        return row[field]
    current: Any = row
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _finite_float(value: Any, field: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric; got {value!r}") from exc
    if not math.isfinite(out):
        raise ValueError(f"{field} must be finite; got {value!r}")
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0 if values else math.nan
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze measured grid-point AprilTag pose accuracy.")
    parser.add_argument("--pose-log", required=True, type=Path)
    parser.add_argument("--grid-csv", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--time-field", default=None)
    parser.add_argument("--x-field", default=None)
    parser.add_argument("--y-field", default=None)
    args = parser.parse_args(argv)

    summary = analyze_grid(
        args.pose_log,
        args.grid_csv,
        args.out_dir,
        time_field=args.time_field,
        x_field=args.x_field,
        y_field=args.y_field,
    )
    print(f"points: {summary['n_points_with_samples']} / {summary['n_points']}")
    print(f"wrote: {args.out_dir.expanduser() / 'grid_validation_summary.json'}")
    print(f"wrote: {args.out_dir.expanduser() / 'grid_validation_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
