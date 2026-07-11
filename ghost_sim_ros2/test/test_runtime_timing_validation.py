import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for item in (ROOT, TOOLS):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from analysis.camera_timing_analysis import analyze_vision_timing, percentile  # noqa: E402
from runtime_resource_logger import metric_summary, summarize_samples, system_snapshot  # noqa: E402


def test_camera_timing_detects_rate_latency_and_long_interval(tmp_path: Path):
    path = tmp_path / "vision_pose.jsonl"
    rows = []
    t = 0.0
    for index in range(60):
        if index == 30:
            t += 0.12
        else:
            t += 1.0 / 30.0
        stamp = 1000.0 + t - 0.020
        rows.append(
            {
                "t_rel_s": t,
                "ros_time_s": 1000.0 + t,
                "stamp": {
                    "sec": int(stamp),
                    "nanosec": int(round((stamp - int(stamp)) * 1e9)),
                },
                "position": {"x_m": 1.0, "y_m": 0.2, "z_m": 0.0},
            }
        )
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    out = tmp_path / "timing"
    summary = analyze_vision_timing(path, out)

    assert summary["sample_count"] == 60
    assert 27.0 < summary["effective_rate_hz"] < 30.5
    assert summary["interarrival"]["drop_proxy_interval_count"] == 1
    assert abs(summary["receive_latency"]["median_s"] - 0.020) < 1e-6
    assert summary["clock_diagnostics"]["negative_latency_count"] == 0
    for name in (
        "camera_timing_summary.json",
        "camera_timing_summary.md",
        "camera_interarrival_timeline.png",
        "camera_receive_latency.png",
    ):
        assert (out / name).exists(), name


def test_percentile_interpolates_known_values():
    assert percentile([0.0, 10.0], 50.0) == 5.0
    assert percentile([1.0], 95.0) == 1.0


def _write_process_stat(path: Path, pid: int, utime: int, stime: int, rss_pages: int):
    fields = ["S"] + ["0"] * 21
    fields[11] = str(utime)
    fields[12] = str(stime)
    fields[21] = str(rss_pages)
    path.write_text(f"{pid} (ghost node) " + " ".join(fields) + "\n", encoding="utf-8")


def test_system_snapshot_reads_proc_memory_temperature_and_matching_process(tmp_path: Path):
    proc = tmp_path / "proc"
    sys_root = tmp_path / "sys"
    proc.mkdir()
    (proc / "stat").write_text("cpu  100 0 50 850 0 0 0 0 0 0\n", encoding="utf-8")
    (proc / "meminfo").write_text(
        "MemTotal:       4096000 kB\nMemAvailable:   3072000 kB\n", encoding="utf-8"
    )
    (proc / "loadavg").write_text("0.42 0.30 0.20 1/100 1\n", encoding="utf-8")
    process = proc / "123"
    process.mkdir()
    (process / "cmdline").write_bytes(b"python\x00ghost_formal_imm_tracker\x00")
    _write_process_stat(process / "stat", 123, 30, 10, 100)
    thermal = sys_root / "class" / "thermal" / "thermal_zone0"
    thermal.mkdir(parents=True)
    (thermal / "temp").write_text("52340\n", encoding="utf-8")

    first = system_snapshot(previous=None, process_patterns=("ghost",), proc_root=proc, sys_root=sys_root)
    assert first["matching_process_count"] == 1
    assert first["memory_used_mb"] == 1000.0
    assert first["memory_available_mb"] == 3000.0
    assert first["temperature_c"] == 52.34
    assert first["load_1m"] == 0.42

    (proc / "stat").write_text("cpu  150 0 70 880 0 0 0 0 0 0\n", encoding="utf-8")
    _write_process_stat(process / "stat", 123, 45, 15, 120)
    second = system_snapshot(
        previous=first["counter_state"],
        process_patterns=("ghost",),
        proc_root=proc,
        sys_root=sys_root,
    )
    assert second["system_cpu_percent"] is not None
    assert second["matching_process_cpu_percent"] is not None
    assert second["matching_process_rss_mb"] > first["matching_process_rss_mb"]


def test_runtime_summary_reports_available_and_missing_metrics():
    samples = [
        {
            "elapsed_s": 0.0,
            "system_cpu_percent": None,
            "matching_process_cpu_percent": None,
            "matching_process_rss_mb": 100.0,
            "memory_used_mb": 900.0,
            "temperature_c": 50.0,
            "load_1m": 0.2,
            "matching_process_count": 2,
        },
        {
            "elapsed_s": 1.0,
            "system_cpu_percent": 40.0,
            "matching_process_cpu_percent": 70.0,
            "matching_process_rss_mb": 110.0,
            "memory_used_mb": 920.0,
            "temperature_c": 54.0,
            "load_1m": 0.4,
            "matching_process_count": 3,
        },
    ]
    summary = summarize_samples(samples)
    assert summary["sample_count"] == 2
    assert summary["system_cpu_percent"]["median"] == 40.0
    assert summary["matching_process_rss_mb"]["max"] == 110.0
    assert summary["max_matching_process_count"] == 3
    assert metric_summary([{"x": None}], "x")["available"] is False
