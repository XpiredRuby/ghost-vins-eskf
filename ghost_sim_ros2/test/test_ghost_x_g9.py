from __future__ import annotations

import math
from pathlib import Path

from analysis.ghost_x_runtime import (
    cpu_stress,
    evaluate_estimator_deadline,
    load_runtime_design,
    summarize_resources,
    summarize_samples,
)


def test_runtime_design_covers_required_qos_axes() -> None:
    design = load_runtime_design(Path("config/ghost_x_g9_runtime.yaml"))
    scenarios = design["scenarios"]
    assert any(item["publisher_reliability"] == "best_effort" for item in scenarios)
    assert any(item["publisher_reliability"] == "reliable" for item in scenarios)
    assert {int(item["depth"]) for item in scenarios} >= {1, 10, 100}
    assert any("deadline_ms" in item for item in scenarios)
    assert any("liveliness_lease_ms" in item for item in scenarios)
    assert any(int(item.get("cpu_stress_workers", 0)) > 0 for item in scenarios)
    assert any(item.get("expected_compatible") is False for item in scenarios)


def test_sample_summary_and_resources() -> None:
    summary = summarize_samples([1.0, 2.0, 3.0, 4.0])
    assert summary["count"] == 4
    assert math.isclose(summary["mean"], 2.5)
    assert summary["max"] == 4.0
    resources = summarize_resources(
        [
            {
                "temperature_c": 50.0,
                "cpu_frequency_mhz": 1500.0,
                "load_1m": 1.0,
                "memory_available_mb": 1000.0,
                "process_rss_mb": 50.0,
            },
            {
                "temperature_c": 55.0,
                "cpu_frequency_mhz": 1200.0,
                "load_1m": 2.0,
                "memory_available_mb": 900.0,
                "process_rss_mb": 60.0,
            },
        ]
    )
    assert resources["sample_count"] == 2
    assert resources["temperature_c"]["max"] == 55.0
    assert resources["cpu_frequency_mhz"]["min"] == 1200.0


def test_deadline_evaluation() -> None:
    benchmarks = [
        {
            "implementation": "python_reference",
            "stress_workers": 0,
            "execution_us": {
                "cv": {"max": 100.0, "p99": 90.0},
                "imm": {"max": 200.0, "p99": 180.0},
            },
        },
        {
            "implementation": "cpp_production",
            "stress_workers": 2,
            "execution_us_per_step": {"imm": {"max": 300.0, "p99": 250.0}},
        },
    ]
    report = evaluate_estimator_deadline(benchmarks, 1.0)
    assert report["all_max_below_deadline"] is True
    assert len(report["rows"]) == 3


def test_cpu_stress_context_zero_workers() -> None:
    with cpu_stress(0):
        value = sum(range(100))
    assert value == 4950
