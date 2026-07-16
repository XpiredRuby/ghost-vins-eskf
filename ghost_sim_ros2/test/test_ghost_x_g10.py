from __future__ import annotations

import json
from pathlib import Path

from analysis.ghost_x_regression import (
    compare_manifests,
    deterministic_manifest,
    load_acceptance,
    summarize_checks,
)


def test_acceptance_configuration_loads() -> None:
    acceptance = load_acceptance(Path("config/ghost_x_g10_acceptance.yaml"))
    assert acceptance["canonical"]["planned_trials"] == 24
    assert acceptance["acceptance_bands"]["g8_faults"] >= 10


def test_deterministic_manifest_and_comparison(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "canonical_streams").mkdir(parents=True)
        (root / "canonical_streams/a.jsonl").write_text('{"x":1}\n', encoding="utf-8")
        (root / "trial_metrics.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    left = deterministic_manifest(first, ["canonical_streams"], ["trial_metrics.csv"])
    right = deterministic_manifest(second, ["canonical_streams"], ["trial_metrics.csv"])
    comparison = compare_manifests(left, right)
    assert comparison["identical"] is True
    assert comparison["difference_count"] == 0
    (second / "canonical_streams/a.jsonl").write_text('{"x":2}\n', encoding="utf-8")
    changed = deterministic_manifest(second, ["canonical_streams"], ["trial_metrics.csv"])
    assert compare_manifests(left, changed)["identical"] is False


def test_check_summary() -> None:
    checks = [
        {"id": "a", "passed": True, "actual": 1, "expected": 1, "details": ""},
        {"id": "b", "passed": False, "actual": 0, "expected": 1, "details": ""},
    ]
    summary = summarize_checks(checks)
    assert summary["passed"] is False
    assert summary["failed_count"] == 1
    assert summary["failed_checks"][0]["id"] == "b"
