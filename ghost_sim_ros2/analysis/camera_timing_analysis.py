"""Analyze USB-camera-derived ROS vision timing from GHOST trial recorder JSONL."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

TIMING_STATUS = "USB_UVC_SOFTWARE_ARRIVAL_TIMING_CHARACTERIZATION"
CLAIMS_BOUNDARY = "DOES_NOT_PROVE_SHUTTER_OPEN_HARDWARE_TIMESTAMP_ACCURACY"


def analyze_vision_timing(
    vision_jsonl: Path,
    out_dir: Path,
    *,
    drop_interval_multiplier: float = 1.5,
) -> dict[str, Any]:
    rows = read_vision_rows(vision_jsonl)
    if len(rows) < 3:
        raise ValueError("vision log requires at least three timestamped rows")
    times = [row["t_rel_s"] for row in rows]
    intervals = [times[i] - times[i - 1] for i in range(1, len(times))]
    if any(value <= 0.0 for value in intervals):
        raise ValueError("vision t_rel_s values must be strictly increasing")

    median_interval = statistics.median(intervals)
    threshold = drop_interval_multiplier * median_interval
    dropped_proxy = [value for value in intervals if value > threshold]
    estimated_missed = sum(max(0, round(value / median_interval) - 1) for value in dropped_proxy)
    latency_rows = [row for row in rows if row["rx_latency_s"] is not None]
    latencies = [row["rx_latency_s"] for row in latency_rows]
    negative_latency_count = sum(value < 0.0 for value in latencies)

    summary = {
        "timing_status": TIMING_STATUS,
        "claims_boundary": CLAIMS_BOUNDARY,
        "source": str(vision_jsonl.expanduser()),
        "sample_count": len(rows),
        "duration_s": times[-1] - times[0],
        "effective_rate_hz": (len(times) - 1) / (times[-1] - times[0]),
        "interarrival": {
            "median_s": median_interval,
            "mean_s": statistics.fmean(intervals),
            "std_s": _sample_std(intervals),
            "min_s": min(intervals),
            "p05_s": percentile(intervals, 5.0),
            "p95_s": percentile(intervals, 95.0),
            "max_s": max(intervals),
            "median_absolute_jitter_s": statistics.median(
                abs(value - median_interval) for value in intervals
            ),
            "drop_proxy_threshold_s": threshold,
            "drop_proxy_interval_count": len(dropped_proxy),
            "estimated_missed_frame_intervals": estimated_missed,
        },
        "receive_latency": latency_summary(latencies),
        "clock_diagnostics": {
            "rows_with_ros_and_header_stamp": len(latency_rows),
            "negative_latency_count": negative_latency_count,
            "interpretation": (
                "ROS receive time minus message header stamp. Values are meaningful only when both "
                "timestamps use compatible clocks and the publisher stamp approximates measurement time."
            ),
        },
        "caveats": [
            "USB UVC webcam timestamps are software/arrival based unless independent hardware timestamp support is proven.",
            "Long inter-sample intervals are dropped-interval proxies, not direct proof of a camera hardware frame drop.",
            "Receive latency includes publisher, scheduling, ROS transport and clock-definition effects.",
        ],
        "series": {
            "t_s": times[1:],
            "interarrival_s": intervals,
            "latency_t_s": [row["t_rel_s"] for row in latency_rows],
            "rx_latency_s": latencies,
        },
    }
    write_outputs(summary, out_dir)
    return summary


def read_vision_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.expanduser().open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {lineno}: {exc}") from exc
            if not isinstance(obj, dict):
                continue
            t_rel = finite_or_none(obj.get("t_rel_s"))
            if t_rel is None:
                continue
            ros_time = finite_or_none(obj.get("ros_time_s"))
            stamp = obj.get("stamp")
            stamp_s = None
            if isinstance(stamp, dict):
                sec = finite_or_none(stamp.get("sec"))
                nanosec = finite_or_none(stamp.get("nanosec"))
                if sec is not None and nanosec is not None:
                    stamp_s = sec + nanosec * 1e-9
            latency = ros_time - stamp_s if ros_time is not None and stamp_s is not None else None
            rows.append(
                {
                    "t_rel_s": t_rel,
                    "ros_time_s": ros_time,
                    "header_stamp_s": stamp_s,
                    "rx_latency_s": latency,
                }
            )
    return sorted(rows, key=lambda row: row["t_rel_s"])


def latency_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "available": False,
            "sample_count": 0,
            "mean_s": None,
            "median_s": None,
            "std_s": None,
            "p05_s": None,
            "p95_s": None,
            "min_s": None,
            "max_s": None,
        }
    return {
        "available": True,
        "sample_count": len(values),
        "mean_s": statistics.fmean(values),
        "median_s": statistics.median(values),
        "std_s": _sample_std(values),
        "p05_s": percentile(values, 5.0),
        "p95_s": percentile(values, 95.0),
        "min_s": min(values),
        "max_s": max(values),
    }


def write_outputs(summary: dict[str, Any], out_dir: Path) -> None:
    out = out_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    (out / "camera_timing_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "camera_timing_summary.md").write_text(format_markdown(summary), encoding="utf-8")
    plot_interarrival(summary, out / "camera_interarrival_timeline.png")
    plot_latency(summary, out / "camera_receive_latency.png")


def format_markdown(summary: dict[str, Any]) -> str:
    interval = summary["interarrival"]
    latency = summary["receive_latency"]
    lines = [
        "# GHOST USB Vision Timing Summary",
        "",
        f"- Timing status: `{summary['timing_status']}`",
        f"- Claims boundary: `{summary['claims_boundary']}`",
        f"- Samples: `{summary['sample_count']}`",
        f"- Duration: `{summary['duration_s']:.6g} s`",
        f"- Effective rate: `{summary['effective_rate_hz']:.6g} Hz`",
        "",
        "## Interarrival",
        "",
        f"- Median interval: `{interval['median_s']:.8g} s`",
        f"- Standard deviation: `{interval['std_s']:.8g} s`",
        f"- 5th–95th percentile: `{interval['p05_s']:.8g}–{interval['p95_s']:.8g} s`",
        f"- Maximum interval: `{interval['max_s']:.8g} s`",
        f"- Drop-proxy intervals: `{interval['drop_proxy_interval_count']}`",
        f"- Estimated missed frame intervals: `{interval['estimated_missed_frame_intervals']}`",
        "",
        "## Receive latency",
        "",
    ]
    if latency["available"]:
        lines.extend(
            [
                f"- Samples: `{latency['sample_count']}`",
                f"- Median: `{latency['median_s']:.8g} s`",
                f"- Mean: `{latency['mean_s']:.8g} s`",
                f"- 5th–95th percentile: `{latency['p05_s']:.8g}–{latency['p95_s']:.8g} s`",
                f"- Minimum/maximum: `{latency['min_s']:.8g}/{latency['max_s']:.8g} s`",
            ]
        )
    else:
        lines.append("- Unavailable because compatible ROS receive and message header timestamps were not recorded.")
    lines.extend(
        [
            "",
            "> These are software-arrival and ROS timing diagnostics for a USB UVC pipeline. They do not establish shutter-open hardware timestamp accuracy.",
            "",
        ]
    )
    return "\n".join(lines)


def plot_interarrival(summary: dict[str, Any], path: Path) -> None:
    series = summary["series"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(series["t_s"], series["interarrival_s"], linewidth=1)
    ax.axhline(summary["interarrival"]["median_s"], linestyle="--", label="Median interval")
    ax.axhline(
        summary["interarrival"]["drop_proxy_threshold_s"],
        linestyle=":",
        label="Drop-proxy threshold",
    )
    ax.set_xlabel("Trial time (s)")
    ax.set_ylabel("Interarrival interval (s)")
    ax.set_title("USB vision interarrival timing")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_latency(summary: dict[str, Any], path: Path) -> None:
    series = summary["series"]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    if series["rx_latency_s"]:
        ax.plot(series["latency_t_s"], series["rx_latency_s"], linewidth=1)
        ax.axhline(summary["receive_latency"]["median_s"], linestyle="--", label="Median")
        ax.legend()
    else:
        ax.text(0.5, 0.5, "Compatible latency timestamps unavailable", ha="center", va="center")
    ax.set_xlabel("Trial time (s)")
    ax.set_ylabel("ROS receive time - header stamp (s)")
    ax.set_title("Vision receive-latency diagnostic")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def percentile(values: list[float], percent: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def finite_or_none(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _sample_std(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) >= 2 else 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze GHOST USB vision timing and ROS receive latency.")
    parser.add_argument("--vision-jsonl", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--drop-interval-multiplier", type=float, default=1.5)
    args = parser.parse_args(argv)
    summary = analyze_vision_timing(
        args.vision_jsonl,
        args.out_dir,
        drop_interval_multiplier=args.drop_interval_multiplier,
    )
    print(f"samples={summary['sample_count']}")
    print(f"rate_hz={summary['effective_rate_hz']:.6g}")
    print(f"drop_proxy_intervals={summary['interarrival']['drop_proxy_interval_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
