import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.validate_physical_session import load_session, validate_session  # noqa: E402


def template():
    return {
        "schema_version": 1,
        "session_id": "test_session",
        "phases": [
            {
                "phase_id": "inventory",
                "title": "Inventory",
                "depends_on": [],
                "status": "pending",
                "required_artifacts": ["inventory.json"],
                "notes": "",
            },
            {
                "phase_id": "controlled_r",
                "title": "Controlled R",
                "depends_on": ["inventory"],
                "status": "pending",
                "required_artifacts": ["noise_summary.json"],
                "notes": "",
            },
            {
                "phase_id": "grid",
                "title": "Grid",
                "depends_on": ["controlled_r"],
                "status": "pending",
                "required_artifacts": ["grid_validation_summary.json"],
                "notes": "",
            },
        ],
    }


def test_pending_template_is_structurally_valid():
    result = validate_session(template())
    assert result["valid"] is True
    assert result["phase_count"] == 3
    assert result["status_counts"]["pending"] == 3


def test_phase_cannot_pass_before_dependency():
    session = template()
    session["phases"][1]["status"] = "passed"
    result = validate_session(session)
    assert result["valid"] is False
    assert any("dependency inventory" in error for error in result["errors"])


def test_ready_for_checks_direct_dependencies():
    session = template()
    session["phases"][0]["status"] = "passed"
    result = validate_session(session, require_ready_for="controlled_r")
    assert result["valid"] is True
    assert result["ready"] is True
    blocked = validate_session(session, require_ready_for="grid")
    assert blocked["valid"] is False
    assert blocked["ready"] is False


def test_passed_phase_requires_declared_artifacts_when_root_is_supplied(tmp_path: Path):
    session = template()
    session["phases"][0]["status"] = "passed"
    missing = validate_session(session, artifact_root=tmp_path)
    assert missing["valid"] is False
    assert missing["missing_artifacts"]["inventory"] == ["inventory.json"]
    (tmp_path / "inventory.json").write_text("{}")
    complete = validate_session(session, artifact_root=tmp_path)
    assert complete["valid"] is True


def test_complete_mode_rejects_pending_and_accepts_all_passed():
    session = template()
    result = validate_session(session, require_complete=True)
    assert result["valid"] is False
    for phase in session["phases"]:
        phase["status"] = "passed"
    result = validate_session(session, require_complete=True)
    assert result["valid"] is True


def test_unknown_or_forward_dependency_is_rejected(tmp_path: Path):
    session = template()
    session["phases"][0]["depends_on"] = ["grid"]
    result = validate_session(session)
    assert result["valid"] is False
    assert any("must appear earlier" in error for error in result["errors"])

    path = tmp_path / "session.json"
    path.write_text(json.dumps(template()))
    assert load_session(path)["session_id"] == "test_session"
