from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ghost_sim_ros2.data_contract import CONTRACT_VERSION, validate_payload


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = PACKAGE_ROOT / "schemas"


def test_g2_phase_validator_passes(tmp_path: Path) -> None:
    report = tmp_path / "g2_validation.json"
    command = [
        sys.executable,
        str(PACKAGE_ROOT / "tools" / "validate_ghost_x_g2.py"),
        "--package-root",
        str(PACKAGE_ROOT),
        "--out",
        str(report),
    ]
    result = subprocess.run(command, cwd=PACKAGE_ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["checks"]["data_contract_version"] == CONTRACT_VERSION
    assert len(payload["checks"]["runtime_contract_probe"]["validated_topics"]) == 5


def test_committed_mission_validation_is_contract_compliant() -> None:
    mission = json.loads(
        (PACKAGE_ROOT / "docs" / "GHOST_DRONE_MISSION_VALIDATION.json").read_text(
            encoding="utf-8"
        )
    )
    validate_payload(mission, "mission_validation.schema.json", SCHEMA_DIR)
    assert mission["passed"] is True
    assert mission["contract_version"] == CONTRACT_VERSION
    assert mission["validity"]["state"] == "MISSION_COMPLETE"


def test_runtime_probe_validated_all_required_topics() -> None:
    runtime = json.loads(
        (PACKAGE_ROOT / "docs" / "GHOST_X_G2_RUNTIME_VALIDATION.json").read_text(
            encoding="utf-8"
        )
    )
    assert runtime["passed"] is True
    assert runtime["missing_topics"] == []
    assert runtime["errors"] == []
    assert set(runtime["validated_topics"]) == {
        "/ghost/evaluation/status_json",
        "/ghost/tracker_imm/futures_json",
        "/ghost/tracker_imm/status_json",
        "/ghost/tracker_mh/futures_json",
        "/ghost/tracker_mh/status_json",
    }
