"""Log Raspberry Pi system and GHOST-process resource use during hardware trials."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

FIELDS = [
    "elapsed_s",
    "utc",
    "system_cpu_percent",
    "load_1m",
    "memory_used_mb",
    "memory_available_mb",
    "temperature_c",
    "matching_process_count",
    "matching_process_cpu_percent",
    "matching_process_rss_mb",
]


def log_resources(
    out_dir: Path,
    *,
    duration_s: float,
    interval_s: float = 1.0,
    process_patterns: tuple[str, ...] = ("ghost", "apriltag", "ros2"),
    snapshot_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if duration_s <= 0.0 or interval_s <= 0.0:
        raise ValueError("duration_s and interval_s must be > 0")
    out = out_dir.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "runtime_resources.csv"
    snapshot_fn = snapshot_fn or system_snapshot
    start = time.monotonic()
    previous = None
    samples = []

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        next_sample = start
        while True:
            now = time.monotonic()
            if now < next_sample:
                time.sleep(next_sample - now)
                now = time.monotonic()
            elapsed = now - start
            raw = snapshot_fn(previous=previous, process_patterns=process_patterns)
            previous = raw.get("counter_state")
            row = {
                "elapsed_s": elapsed,
                "utc": utc_now(),
                "system_cpu_percent": raw.get("system_cpu_percent"),
                "load_1m": raw.get("load_1m"),
                "memory_used_mb": raw.get("memory_used_mb"),
                "memory_available_mb": raw.get("memory_available_mb"),
                "temperature_c": raw.get("temperature_c"),
                "matching_process_count": raw.get("matching_process_count", 0),
                "matching_process_cpu_percent": raw.get("matching_process_cpu_percent"),
                "matching_process_rss_mb": raw.get("matching_process_rss_mb"),
            }
            samples.append(row)
            writer.writerow(row)
            f.flush()
            if elapsed >= duration_s:
                break
            next_sample += interval_s

    summary = summarize_samples(samples)
    summary.update(
        {
            "created_at_utc": utc_now(),
            "duration_requested_s": duration_s,
            "interval_requested_s": interval_s,
            "process_patterns": list(process_patterns),
            "source_csv": str(csv_path),
            "claims_boundary": "RUNTIME_CHARACTERIZATION_FOR_THIS_PI_SESSION_NOT_WORST_CASE_QUALIFICATION",
        }
    )
    (out / "runtime_resources_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "runtime_resources_summary.md").write_text(
        format_markdown(summary), encoding="utf-8"
    )
    return summary


def system_snapshot(
    *,
    previous: dict[str, Any] | None,
    process_patterns: tuple[str, ...],
    proc_root: Path = Path("/proc"),
    sys_root: Path = Path("/sys"),
) -> dict[str, Any]:
    cpu_total, cpu_idle = read_cpu_ticks(proc_root / "stat")
    processes = read_processes(proc_root, process_patterns)
    process_ticks = sum(process["cpu_ticks"] for process in processes)
    system_cpu = None
    process_cpu = None
    if previous:
        delta_total = cpu_total - float(previous.get("cpu_total", cpu_total))
        delta_idle = cpu_idle - float(previous.get("cpu_idle", cpu_idle))
        delta_proc = process_ticks - float(previous.get("process_ticks", process_ticks))
        if delta_total > 0.0:
            system_cpu = 100.0 * max(0.0, min(1.0, 1.0 - delta_idle / delta_total))
            process_cpu = 100.0 * max(0.0, delta_proc / delta_total) * (os.cpu_count() or 1)

    memory = read_memory(proc_root / "meminfo")
    load = read_load(proc_root / "loadavg")
    temperature = read_temperature(sys_root)
    return {
        "system_cpu_percent": system_cpu,
        "load_1m": load,
        "memory_used_mb": memory["used_mb"],
        "memory_available_mb": memory["available_mb"],
        "temperature_c": temperature,
        "matching_process_count": len(processes),
        "matching_process_cpu_percent": process_cpu,
        "matching_process_rss_mb": sum(process["rss_mb"] for process in processes),
        "processes": processes,
        "counter_state": {
            "cpu_total": cpu_total,
            "cpu_idle": cpu_idle,
            "process_ticks": process_ticks,
        },
    }


def read_cpu_ticks(path: Path) -> tuple[float, float]:
    first = path.read_text(encoding="utf-8").splitlines()[0].split()
    if not first or first[0] != "cpu":
        raise ValueError(f"invalid /proc/stat CPU row: {path}")
    values = [float(value) for value in first[1:]]
    total = sum(values)
    idle = values[3] + (values[4] if len(values) > 4 else 0.0)
    return total, idle


def read_memory(path: Path) -> dict[str, float]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        token = raw.strip().split()[0]
        values[key] = float(token) / 1024.0
    total = values.get("MemTotal", 0.0)
    available = values.get("MemAvailable", values.get("MemFree", 0.0))
    return {"used_mb": max(0.0, total - available), "available_mb": available}


def read_load(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return None


def read_temperature(sys_root: Path) -> float | None:
    values = []
    thermal_root = sys_root / "class" / "thermal"
    for path in thermal_root.glob("thermal_zone*/temp") if thermal_root.exists() else []:
        try:
            value = float(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if value > 1000.0:
            value /= 1000.0
        if -20.0 <= value <= 150.0:
            values.append(value)
    return max(values) if values else None


def read_processes(proc_root: Path, patterns: tuple[str, ...]) -> list[dict[str, Any]]:
    lowered = tuple(pattern.lower() for pattern in patterns if pattern)
    page_mb = os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0)
    rows = []
    for directory in proc_root.iterdir():
        if not directory.name.isdigit():
            continue
        try:
            cmdline = (directory / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8").strip()
            stat = (directory / "stat").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if lowered and not any(pattern in cmdline.lower() for pattern in lowered):
            continue
        closing = stat.rfind(")")
        if closing < 0:
            continue
        fields = stat[closing + 2 :].split()
        if len(fields) <= 21:
            continue
        try:
            ticks = float(fields[11]) + float(fields[12])
            rss_mb = float(fields[21]) * page_mb
        except ValueError:
            continue
        rows.append(
            {
                "pid": int(directory.name),
                "cmdline": cmdline,
                "cpu_ticks": ticks,
                "rss_mb": max(0.0, rss_mb),
            }
        )
    return rows


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sample_count": len(samples),
        "elapsed_s": max([float(row["elapsed_s"]) for row in samples] or [0.0]),
        "system_cpu_percent": metric_summary(samples, "system_cpu_percent"),
        "matching_process_cpu_percent": metric_summary(samples, "matching_process_cpu_percent"),
        "matching_process_rss_mb": metric_summary(samples, "matching_process_rss_mb"),
        "memory_used_mb": metric_summary(samples, "memory_used_mb"),
        "temperature_c": metric_summary(samples, "temperature_c"),
        "load_1m": metric_summary(samples, "load_1m"),
        "max_matching_process_count": max(
            [int(row.get("matching_process_count") or 0) for row in samples] or [0]
        ),
    }


def metric_summary(samples: list[dict[str, Any]], field: str) -> dict[str, float | None]:
    values = [float(row[field]) for row in samples if finite(row.get(field))]
    if not values:
        return {"available": False, "median": None, "mean": None, "p95": None, "max": None}
    return {
        "available": True,
        "median": statistics.median(values),
        "mean": statistics.fmean(values),
        "p95": percentile(values, 95.0),
        "max": max(values),
    }


def format_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# GHOST Raspberry Pi Runtime Resource Summary",
        "",
        f"- Samples: `{summary['sample_count']}`",
        f"- Elapsed: `{summary['elapsed_s']:.6g} s`",
        f"- Process patterns: `{', '.join(summary['process_patterns'])}`",
        f"- Claims boundary: `{summary['claims_boundary']}`",
        "",
        "| metric | median | p95 | maximum |",
        "|---|---:|---:|---:|",
    ]
    for field, label in (
        ("system_cpu_percent", "System CPU (%)"),
        ("matching_process_cpu_percent", "Matching process CPU (%)"),
        ("matching_process_rss_mb", "Matching process RSS (MB)"),
        ("memory_used_mb", "System memory used (MB)"),
        ("temperature_c", "Temperature (°C)"),
        ("load_1m", "1-minute load"),
    ):
        metric = summary[field]
        lines.append(
            f"| {label} | {_fmt(metric['median'])} | {_fmt(metric['p95'])} | {_fmt(metric['max'])} |"
        )
    lines.extend(
        [
            "",
            "> This is runtime characterization for the recorded Raspberry Pi session. It is not worst-case qualification, thermal certification or flight-computer validation.",
            "",
        ]
    )
    return "\n".join(lines)


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100.0
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _fmt(value: Any) -> str:
    return "NA" if not finite(value) else f"{float(value):.6g}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log Raspberry Pi and GHOST-process resources.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, required=True)
    parser.add_argument("--interval-s", type=float, default=1.0)
    parser.add_argument("--process-patterns", default="ghost,apriltag,ros2")
    args = parser.parse_args(argv)
    patterns = tuple(value.strip() for value in args.process_patterns.split(",") if value.strip())
    summary = log_resources(
        args.out_dir,
        duration_s=args.duration_s,
        interval_s=args.interval_s,
        process_patterns=patterns,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
