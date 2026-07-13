"""Runtime, resource, and deterministic timing utilities for GHOST-X G9."""

from __future__ import annotations

import csv
import json
import math
import multiprocessing as mp
import os
import resource
import statistics
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import yaml

from analysis.ghost_x_offline_estimators import make_default_adapters


def load_runtime_design(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("runtime design must be a mapping")
    if not isinstance(value.get("scenarios"), list) or not value["scenarios"]:
        raise ValueError("runtime design requires scenarios")
    ids = [str(item["id"]) for item in value["scenarios"]]
    if len(ids) != len(set(ids)):
        raise ValueError("runtime scenario ids must be unique")
    return value


def summarize_samples(values: Iterable[float]) -> dict[str, Any]:
    clean = np.asarray([float(value) for value in values if math.isfinite(float(value))], dtype=float)
    if clean.size == 0:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }
    return {
        "count": int(clean.size),
        "mean": float(np.mean(clean)),
        "std": float(np.std(clean, ddof=1)) if clean.size > 1 else 0.0,
        "min": float(np.min(clean)),
        "p50": float(np.percentile(clean, 50.0)),
        "p90": float(np.percentile(clean, 90.0)),
        "p95": float(np.percentile(clean, 95.0)),
        "p99": float(np.percentile(clean, 99.0)),
        "max": float(np.max(clean)),
    }


def read_temperature_c() -> float | None:
    candidates = sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    for path in candidates:
        try:
            value = float(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        if value > 1000.0:
            value /= 1000.0
        if -20.0 <= value <= 150.0:
            return value
    return None


def read_cpu_frequency_mhz() -> float | None:
    paths = [
        Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"),
        Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq"),
    ]
    for path in paths:
        try:
            value = float(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            continue
        return value / 1000.0 if value > 10000.0 else value
    return None


def read_memory_available_mb() -> float | None:
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("MemAvailable:"):
            return float(line.split()[1]) / 1024.0
    return None


def read_process_rss_mb() -> float | None:
    try:
        lines = Path("/proc/self/status").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            return float(line.split()[1]) / 1024.0
    return None


def read_throttled_status() -> str | None:
    try:
        completed = subprocess.run(
            ["vcgencmd", "get_throttled"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text or None


class ResourceSampler:
    def __init__(self, sample_hz: float = 10.0) -> None:
        if not math.isfinite(sample_hz) or sample_hz <= 0.0:
            raise ValueError("sample_hz must be finite and positive")
        self.period_s = 1.0 / sample_hz
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.start_monotonic = 0.0

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("resource sampler already started")
        self.start_monotonic = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> list[dict[str, Any]]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, 2.0 * self.period_s))
        return list(self.samples)

    def _run(self) -> None:
        while not self._stop.is_set():
            load = os.getloadavg() if hasattr(os, "getloadavg") else (None, None, None)
            self.samples.append(
                {
                    "t_s": time.monotonic() - self.start_monotonic,
                    "temperature_c": read_temperature_c(),
                    "cpu_frequency_mhz": read_cpu_frequency_mhz(),
                    "load_1m": load[0],
                    "load_5m": load[1],
                    "load_15m": load[2],
                    "memory_available_mb": read_memory_available_mb(),
                    "process_rss_mb": read_process_rss_mb(),
                }
            )
            self._stop.wait(self.period_s)


def summarize_resources(samples: list[dict[str, Any]]) -> dict[str, Any]:
    fields = [
        "temperature_c",
        "cpu_frequency_mhz",
        "load_1m",
        "memory_available_mb",
        "process_rss_mb",
    ]
    result = {field: summarize_samples(sample[field] for sample in samples if sample.get(field) is not None) for field in fields}
    result["sample_count"] = len(samples)
    return result


def _burn_cpu(stop: mp.Event) -> None:
    value = 0.123456789
    while not stop.is_set():
        for index in range(20000):
            value = math.sin(value + index * 1.0e-7) ** 2 + math.cos(value) ** 2


@contextmanager
def cpu_stress(workers: int) -> Iterator[None]:
    count = max(0, int(workers))
    if count == 0:
        yield
        return
    stop = mp.Event()
    processes = [mp.Process(target=_burn_cpu, args=(stop,), daemon=True) for _ in range(count)]
    for process in processes:
        process.start()
    try:
        yield
    finally:
        stop.set()
        for process in processes:
            process.join(timeout=3.0)
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=1.0)


def load_canonical_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"canonical row is not an object: {path}")
            rows.append(value)
    if not rows:
        raise ValueError(f"canonical stream is empty: {path}")
    return rows


def benchmark_python_estimators(
    stream_path: Path,
    *,
    repeats: int = 8,
    stress_workers: int = 0,
) -> dict[str, Any]:
    rows = load_canonical_rows(stream_path)
    dt = float(rows[0]["dt_s"])
    covariance = np.asarray(rows[0]["measurement_covariance_xy_m2"], dtype=float)
    samples: dict[str, list[float]] = {"cv_kalman": [], "formal_imm": [], "ghost_mh": []}
    sampler = ResourceSampler(10.0)
    throttled_before = read_throttled_status()
    sampler.start()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    with cpu_stress(stress_workers):
        for _ in range(repeats):
            adapters = make_default_adapters(dt, covariance, mh_max_occlusion_s=20.0)
            for row in rows:
                measurement = row.get("measurement_xy_m") if bool(row.get("visible")) else None
                for name, adapter in adapters.items():
                    start_ns = time.perf_counter_ns()
                    adapter.step(float(row["dt_s"]), measurement)
                    samples[name].append((time.perf_counter_ns() - start_ns) / 1000.0)
    process_cpu_s = time.process_time() - cpu_start
    wall_s = time.perf_counter() - wall_start
    resources = sampler.stop()
    return {
        "implementation": "python_reference",
        "stream": str(stream_path),
        "repeats": repeats,
        "steps_per_repeat": len(rows),
        "stress_workers": stress_workers,
        "execution_us": {name: summarize_samples(values) for name, values in samples.items()},
        "wall_s": wall_s,
        "process_cpu_s": process_cpu_s,
        "process_cpu_fraction_of_one_core": process_cpu_s / wall_s if wall_s > 0.0 else None,
        "resource_summary": summarize_resources(resources),
        "throttled_before": throttled_before,
        "throttled_after": read_throttled_status(),
    }


def write_cli_input(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["t_s", "visible", "x_m", "y_m"])
        for row in rows:
            measurement = row.get("measurement_xy_m") if bool(row.get("visible")) else None
            writer.writerow(
                [
                    row["t_s"],
                    1 if measurement is not None else 0,
                    "" if measurement is None else measurement[0],
                    "" if measurement is None else measurement[1],
                ]
            )


def benchmark_cpp_estimators(
    stream_path: Path,
    cli_path: Path,
    config_path: Path,
    *,
    repeats: int = 20,
    stress_workers: int = 0,
) -> dict[str, Any]:
    rows = load_canonical_rows(stream_path)
    samples: dict[str, list[float]] = {"cv": [], "imm": [], "mh": []}
    sampler = ResourceSampler(10.0)
    throttled_before = read_throttled_status()
    sampler.start()
    cpu_start = time.process_time()
    wall_start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="ghost_x_g9_") as temp:
        temp_dir = Path(temp)
        input_path = temp_dir / "input.csv"
        write_cli_input(rows, input_path)
        with cpu_stress(stress_workers):
            for estimator in samples:
                output_path = temp_dir / f"{estimator}.csv"
                for _ in range(repeats):
                    start_ns = time.perf_counter_ns()
                    completed = subprocess.run(
                        [str(cli_path), estimator, str(input_path), str(output_path), str(config_path)],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=30.0,
                    )
                    elapsed_us = (time.perf_counter_ns() - start_ns) / 1000.0 / len(rows)
                    if completed.returncode != 0:
                        raise RuntimeError(f"C++ {estimator} benchmark failed: {completed.stderr}")
                    samples[estimator].append(elapsed_us)
    process_cpu_s = time.process_time() - cpu_start
    wall_s = time.perf_counter() - wall_start
    resources = sampler.stop()
    return {
        "implementation": "cpp_production",
        "stream": str(stream_path),
        "repeats": repeats,
        "steps_per_repeat": len(rows),
        "stress_workers": stress_workers,
        "execution_us_per_step": {name: summarize_samples(values) for name, values in samples.items()},
        "wall_s": wall_s,
        "driver_process_cpu_s": process_cpu_s,
        "resource_summary": summarize_resources(resources),
        "throttled_before": throttled_before,
        "throttled_after": read_throttled_status(),
    }


def evaluate_estimator_deadline(benchmarks: list[dict[str, Any]], deadline_ms: float) -> dict[str, Any]:
    deadline_us = float(deadline_ms) * 1000.0
    rows = []
    for benchmark in benchmarks:
        key = "execution_us" if benchmark["implementation"] == "python_reference" else "execution_us_per_step"
        for estimator, summary in benchmark[key].items():
            maximum = summary.get("max")
            rows.append(
                {
                    "implementation": benchmark["implementation"],
                    "stress_workers": benchmark["stress_workers"],
                    "estimator": estimator,
                    "max_execution_us": maximum,
                    "p99_execution_us": summary.get("p99"),
                    "deadline_us": deadline_us,
                    "max_below_deadline": bool(maximum is not None and maximum < deadline_us),
                }
            )
    return {
        "deadline_ms": deadline_ms,
        "rule": "MAX_EXECUTION_TIME_BELOW_DEADLINE",
        "all_max_below_deadline": all(row["max_below_deadline"] for row in rows),
        "rows": rows,
    }


def max_rss_mb() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports KiB; macOS reports bytes. Pi is Linux.
    return value / 1024.0
