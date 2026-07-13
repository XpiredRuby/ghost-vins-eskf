from __future__ import annotations

from pathlib import Path

from analysis.ghost_x_fault_injection import EXPECTED_STATUS, inject_fault, load_design, load_stream, run_campaign


def test_fault_catalog_has_at_least_ten() -> None:
    design = load_design(Path("config/ghost_x_g8_fault_campaign.yaml"))
    assert len(design.faults) >= 10
    assert set(design.faults) == set(EXPECTED_STATUS)


def test_injection_is_deterministic() -> None:
    design = load_design(Path("config/ghost_x_g8_fault_campaign.yaml"))
    stream_path = design.source_campaign / "canonical_streams" / f"{design.representative_trial}.jsonl"
    rows = load_stream(stream_path)
    first = inject_fault(rows, "lighting_degradation", design)
    second = inject_fault(rows, "lighting_degradation", design)
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
