"""Fixed-window controlled-R analysis with predeclared sub-window diagnostics."""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

R_STATUS = "CONTROLLED_R_COLLECTED_PENDING_ENGINEER_REVIEW"
ACCURACY_STATUS = "DOES_NOT_VALIDATE_TRACKER_ACCURACY"
PRIMARY_SOURCE = "RAW_RESIDUAL_COVARIANCE_FIXED_15_75"


@dataclass(frozen=True)
class CsvSample:
    t_s: float
    x_m: float
    y_m: float
    z_m: float


def load_pose_csv(path: Path) -> list[CsvSample]:
    rows: list[CsvSample] = []
    with path.expanduser().open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not {"t", "x", "y", "z"}.issubset(reader.fieldnames):
            raise ValueError("CSV must contain t,x,y,z columns")
        for lineno, row in enumerate(reader, start=2):
            rows.append(
                CsvSample(
                    t_s=_finite(row.get("t"), f"line {lineno} t"),
                    x_m=_finite(row.get("x"), f"line {lineno} x"),
                    y_m=_finite(row.get("y"), f"line {lineno} y"),
                    z_m=_finite(row.get("z"), f"line {lineno} z"),
                )
            )
    if not rows:
        raise ValueError("CSV contains no samples")
    return rows


def analyze_controlled_r(
    samples: list[CsvSample],
    *,
    analysis_start_s: float = 15.0,
    analysis_end_s: float = 75.0,
    subwindows: tuple[tuple[float, float], ...] = (
        (15.0, 35.0),
        (35.0, 55.0),
        (55.0, 75.0),
    ),
) -> dict[str, Any]:
    if not analysis_start_s < analysis_end_s:
        raise ValueError("analysis_start_s must be less than analysis_end_s")
    _validate_subwindows(subwindows, analysis_start_s, analysis_end_s)

    primary_rows = _select(samples, analysis_start_s, analysis_end_s, include_end=True)
    primary = _window_stats(primary_rows, analysis_start_s, analysis_end_s)

    window_results = []
    for index, (start, end) in enumerate(subwindows):
        rows = _select(samples, start, end, include_end=index == len(subwindows) - 1)
        stats = _window_stats(rows, start, end)
        stats["window_index"] = index
        window_results.append(stats)

    covariance = np.asarray(primary["covariance_xy_m2"], dtype=float)
    deviations = []
    centroid_offsets = []
    for stats in window_results:
        window_cov = np.asarray(stats["covariance_xy_m2"], dtype=float)
        denom = max(float(np.linalg.norm(covariance, ord="fro")), 1e-18)
        deviations.append(float(np.linalg.norm(window_cov - covariance, ord="fro") / denom))
        centroid_offsets.append(
            math.hypot(
                float(stats["mean_x_m"]) - float(primary["mean_x_m"]),
                float(stats["mean_y_m"]) - float(primary["mean_y_m"]),
            )
        )

    rxx = [float(stats["r_xx_m2"]) for stats in window_results]
    ryy = [float(stats["r_yy_m2"]) for stats in window_results]
    stability = {
        "subwindow_count": len(window_results),
        "max_relative_frobenius_deviation_from_primary": max(deviations),
        "mean_relative_frobenius_deviation_from_primary": float(np.mean(deviations)),
        "max_subwindow_centroid_offset_m": max(centroid_offsets),
        "r_xx_max_to_min_ratio": _max_min_ratio(rxx),
        "r_yy_max_to_min_ratio": _max_min_ratio(ryy),
        "acceptance_threshold_status": "DIAGNOSTIC_ONLY_NO_PREDECLARED_PASS_FAIL_THRESHOLD",
    }

    return {
        "r_status": R_STATUS,
        "accuracy_status": ACCURACY_STATUS,
        "primary_r_source": PRIMARY_SOURCE,
        "analysis_rule": {
            "primary_window_s": [analysis_start_s, analysis_end_s],
            "subwindow_interval_rule": "half-open [start,end), except final window includes end",
            "post_hoc_trimming": False,
        },
        "primary_window": primary,
        "subwindows": window_results,
        "stability_diagnostics": stability,
        "caveats": [
            "This is empirical raw position covariance under one controlled stationary setup.",
            "Sub-window stability is reported diagnostically because protocol v1 did not predeclare a numerical pass/fail threshold.",
            "This result does not validate estimator accuracy or prove white residual noise.",
        ],
    }


def write_outputs(summary: dict[str, Any], json_out: Path, md_out: Path) -> None:
    json_out = json_out.expanduser()
    md_out = md_out.expanduser()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_out.write_text(format_markdown(summary), encoding="utf-8")


def format_markdown(summary: dict[str, Any]) -> str:
    primary = summary["primary_window"]
    lines = [
        "# Controlled R Fixed-Window Analysis",
        "",
        f"- R status: `{summary['r_status']}`",
        f"- Accuracy status: `{summary['accuracy_status']}`",
        f"- Primary source: `{summary['primary_r_source']}`",
        f"- Analysis window: `{primary['start_s']:.1f}-{primary['end_s']:.1f} s`",
        f"- Samples: `{primary['sample_count']}`",
        f"- Sample rate: `{primary['sample_rate_hz']:.6g} Hz`",
        "",
        "## Primary raw covariance",
        "",
        "| quantity | value |",
        "|---|---:|",
        f"| `R_xx` | `{primary['r_xx_m2']:.12g} m²` |",
        f"| `R_xy` | `{primary['r_xy_m2']:.12g} m²` |",
        f"| `R_yy` | `{primary['r_yy_m2']:.12g} m²` |",
        f"| correlation | `{primary['correlation_xy']:.8g}` |",
        f"| std x | `{primary['std_x_m']:.8g} m` |",
        f"| std y | `{primary['std_y_m']:.8g} m` |",
        f"| drift slope x | `{primary['slope_x_m_per_s']:.8g} m/s` |",
        f"| drift slope y | `{primary['slope_y_m_per_s']:.8g} m/s` |",
        "",
        "## Fixed sub-window diagnostics",
        "",
        "| window (s) | n | rate (Hz) | R_xx (m²) | R_xy (m²) | R_yy (m²) | corr |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in summary["subwindows"]:
        lines.append(
            f"| `{item['start_s']:.0f}-{item['end_s']:.0f}` | {item['sample_count']} | "
            f"{item['sample_rate_hz']:.4g} | {item['r_xx_m2']:.6g} | "
            f"{item['r_xy_m2']:.6g} | {item['r_yy_m2']:.6g} | "
            f"{item['correlation_xy']:.5g} |"
        )

    stability = summary["stability_diagnostics"]
    lines.extend(
        [
            "",
            "## Stability diagnostics",
            "",
            f"- Maximum relative covariance deviation: `{stability['max_relative_frobenius_deviation_from_primary']:.6g}`",
            f"- Mean relative covariance deviation: `{stability['mean_relative_frobenius_deviation_from_primary']:.6g}`",
            f"- Maximum sub-window centroid offset: `{stability['max_subwindow_centroid_offset_m']:.6g} m`",
            f"- `R_xx` max/min ratio: `{_fmt_optional(stability['r_xx_max_to_min_ratio'])}`",
            f"- `R_yy` max/min ratio: `{_fmt_optional(stability['r_yy_max_to_min_ratio'])}`",
            f"- Threshold status: `{stability['acceptance_threshold_status']}`",
            "",
            "> This result estimates measurement covariance only. It does not validate tracker accuracy, "
            "production performance, or residual whiteness.",
            "",
        ]
    )
    return "\n".join(lines)


def _window_stats(rows: list[CsvSample], start_s: float, end_s: float) -> dict[str, Any]:
    if len(rows) < 2:
        raise ValueError(f"window {start_s}-{end_s}s contains fewer than two samples")

    t = np.asarray([row.t_s for row in rows], dtype=float)
    xy = np.asarray([[row.x_m, row.y_m] for row in rows], dtype=float)
    if np.any(np.diff(t) <= 0.0):
        raise ValueError(f"window {start_s}-{end_s}s timestamps are not strictly increasing")

    covariance = np.cov(xy.T, ddof=1)
    std_x = math.sqrt(max(float(covariance[0, 0]), 0.0))
    std_y = math.sqrt(max(float(covariance[1, 1]), 0.0))
    denominator = std_x * std_y
    correlation = float(covariance[0, 1] / denominator) if denominator > 0.0 else 0.0
    centered_t = t - float(np.mean(t))
    slopes = np.polyfit(centered_t, xy, 1)[0]
    span = float(t[-1] - t[0])

    return {
        "start_s": start_s,
        "end_s": end_s,
        "first_sample_s": float(t[0]),
        "last_sample_s": float(t[-1]),
        "sample_count": len(rows),
        "sample_rate_hz": (len(rows) - 1) / span,
        "mean_x_m": float(np.mean(xy[:, 0])),
        "mean_y_m": float(np.mean(xy[:, 1])),
        "std_x_m": std_x,
        "std_y_m": std_y,
        "r_xx_m2": float(covariance[0, 0]),
        "r_xy_m2": float(covariance[0, 1]),
        "r_yy_m2": float(covariance[1, 1]),
        "correlation_xy": correlation,
        "covariance_xy_m2": covariance.tolist(),
        "slope_x_m_per_s": float(slopes[0]),
        "slope_y_m_per_s": float(slopes[1]),
    }


def _select(
    rows: list[CsvSample],
    start_s: float,
    end_s: float,
    *,
    include_end: bool,
) -> list[CsvSample]:
    if include_end:
        return [row for row in rows if start_s <= row.t_s <= end_s]
    return [row for row in rows if start_s <= row.t_s < end_s]


def _validate_subwindows(
    subwindows: tuple[tuple[float, float], ...],
    analysis_start_s: float,
    analysis_end_s: float,
) -> None:
    if not subwindows:
        raise ValueError("at least one subwindow is required")
    expected = analysis_start_s
    for start, end in subwindows:
        if not math.isclose(start, expected, abs_tol=1e-12) or not start < end:
            raise ValueError("subwindows must be contiguous, ordered, and positive length")
        expected = end
    if not math.isclose(expected, analysis_end_s, abs_tol=1e-12):
        raise ValueError("subwindows must exactly cover the primary analysis window")


def _max_min_ratio(values: list[float]) -> float | None:
    minimum = min(values)
    if minimum <= 0.0:
        return None
    return max(values) / minimum


def _finite(value: Any, label: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric; got {value!r}") from exc
    if not math.isfinite(out):
        raise ValueError(f"{label} must be finite; got {value!r}")
    return out


def _fmt_optional(value: float | None) -> str:
    return "NA" if value is None else f"{value:.6g}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze the predeclared controlled-R fixed window.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--md-out", required=True, type=Path)
    args = parser.parse_args(argv)

    summary = analyze_controlled_r(load_pose_csv(args.csv))
    summary["source_csv"] = str(args.csv.expanduser())
    write_outputs(summary, args.json_out, args.md_out)
    print(f"R_xx={summary['primary_window']['r_xx_m2']:.12g}")
    print(f"R_xy={summary['primary_window']['r_xy_m2']:.12g}")
    print(f"R_yy={summary['primary_window']['r_yy_m2']:.12g}")
    print(f"correlation={summary['primary_window']['correlation_xy']:.8g}")
    print(f"wrote_json={args.json_out.expanduser()}")
    print(f"wrote_md={args.md_out.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
