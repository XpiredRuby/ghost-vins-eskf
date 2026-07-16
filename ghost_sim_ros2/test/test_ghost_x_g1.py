from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent


def test_g1_configuration_is_traceable(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    traceability = tmp_path / "traceability.csv"
    command = [
        sys.executable,
        str(PACKAGE_ROOT / "tools" / "validate_ghost_x_g1.py"),
        "--requirements",
        str(PACKAGE_ROOT / "config" / "ghost_x_requirements.yaml"),
        "--tests",
        str(PACKAGE_ROOT / "config" / "ghost_x_test_catalog.yaml"),
        "--claims",
        str(PACKAGE_ROOT / "config" / "ghost_x_claims.yaml"),
        "--report",
        str(report),
        "--traceability",
        str(traceability),
    ]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["counts"]["requirements"] >= 30
    assert payload["counts"]["tests"] >= 30
    assert payload["counts"]["fault_scenarios"] >= 10
    assert payload["counts"]["nominal_scenarios"] >= 8

    with traceability.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == payload["counts"]["traceability_rows"]
    assert all(row["requirement_id"] for row in rows)
    assert all(row["test_id"] for row in rows)
    assert all(row["planned_evidence"] for row in rows)


def test_formal_claims_are_gated_or_evidenced() -> None:
    claims = yaml.safe_load(
        (PACKAGE_ROOT / "config" / "ghost_x_claims.yaml").read_text(encoding="utf-8")
    )["claims"]
    for claim in claims:
        assert claim["status"] in {"approved", "qualified", "future_gate"}
        assert claim["requirements"]
        assert claim["tests"]
        if claim["status"] in {"approved", "qualified"}:
            assert claim["evidence"]
        if claim["status"] in {"qualified", "future_gate"}:
            assert claim.get("limitation")
