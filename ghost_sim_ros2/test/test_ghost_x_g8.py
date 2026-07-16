from __future__ import annotations

import json
from pathlib import Path

from analysis.ghost_x_fault_injection import EXPECTED_STATUS, inject_fault, load_design, load_stream, run_campaign


def test_fault_catalog_has_at_least_ten() -> None:
    design = load_design(Path("config/ghost_x_g8_fault_campaign.yaml"))
    assert len(design.faults) >= 10
    assert set(design.faults) == set(EXPECTED_STATUS)


def test_injection_is_deterministic(tmp_path: Path) -> None:
    """Verify seeded injection without depending on a developer-local campaign path."""

    design = load_design(Path("config/ghost_x_g8_fault_campaign.yaml"))
    stream_path = tmp_path / "representative_stream.jsonl"
    rows = [
        {
            "sequence": index,
            "t_s": round(index * 0.1, 10),
            "dt_s": 0.1,
            "visible": True,
            "measurement_xy_m": [0.2 * index * 0.1, -0.05 * index * 0.1],
            "measurement_covariance_xy_m2": [[0.0004, 0.0], [0.0, 0.0004]],
            "truth": {
                "x_m": 0.2 * index * 0.1,
                "y_m": -0.05 * index * 0.1,
                "vx_mps": 0.2,
                "vy_mps": -0.05,
            },
        }
        for index in range(101)
    ]
    stream_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    loaded = load_stream(stream_path)
    first = inject_fault(loaded, "lighting_degradation", design)
    second = inject_fault(loaded, "lighting_degradation", design)
    assert first == second


def test_full_fault_campaign() -> None:
    design_path = Path("config/ghost_x_g8_fault_campaign.yaml")
    design = load_design(design_path)
    if not design.source_campaign.is_dir():
        return
    report = run_campaign(design_path)
    assert report["fault_count"] == 12
    assert report["passed"] is True
    assert all(trial["detected"] for trial in report["trials"])
    assert all(trial["isolated"] for trial in report["trials"])
