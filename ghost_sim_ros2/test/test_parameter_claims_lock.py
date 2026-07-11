import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for item in (ROOT, TOOLS):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from analysis.validate_release_claims import validate_claims  # noqa: E402
from parameter_lock import create_lock, parse_external, verify_lock  # noqa: E402


def git_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True)
    (repo / "estimator.py").write_text("Q = 1.0\n", encoding="utf-8")
    (repo / "protocol.md").write_text("# Protocol\n", encoding="utf-8")
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)
    return repo


def test_parameter_lock_verifies_and_detects_file_change(tmp_path: Path):
    repo = git_repo(tmp_path)
    calibration = tmp_path / "calibration.json"
    calibration.write_text('{"rms":0.5}', encoding="utf-8")
    lock_path = tmp_path / "parameter_lock.json"
    lock = create_lock(
        repo,
        lock_path,
        repo_files=["estimator.py", "protocol.md"],
        external_files={"camera_calibration": calibration},
    )
    assert lock["lock_status"] == "FORMAL_CAMPAIGN_PARAMETERS_PINNED_BEFORE_OUTCOME_REVIEW"
    assert verify_lock(lock_path, repo)["valid"] is True

    (repo / "estimator.py").write_text("Q = 2.0\n", encoding="utf-8")
    result = verify_lock(lock_path, repo)
    assert result["valid"] is False
    assert any("SHA-256 mismatch" in error for error in result["errors"])


def test_parameter_lock_refuses_overwrite_and_missing_file(tmp_path: Path):
    repo = git_repo(tmp_path)
    lock_path = tmp_path / "lock.json"
    create_lock(repo, lock_path, repo_files=["estimator.py"])
    with pytest.raises(FileExistsError):
        create_lock(repo, lock_path, repo_files=["estimator.py"])
    with pytest.raises(ValueError, match="does not exist"):
        create_lock(repo, tmp_path / "other.json", repo_files=["missing.py"])


def test_external_parser_requires_unique_label_path_pairs():
    parsed = parse_external(["calibration=/tmp/camera.json", "params=/tmp/params.yaml"])
    assert parsed["calibration"] == Path("/tmp/camera.json")
    with pytest.raises(ValueError, match="LABEL=PATH"):
        parse_external(["bad"])
    with pytest.raises(ValueError, match="duplicate"):
        parse_external(["x=/a", "x=/b"])


def claims_template():
    return {
        "schema_version": 1,
        "project": "GHOST",
        "claims": [
            {
                "claim_id": "hardware",
                "public_statement": "The preserved hardware run shows dropout state transitions.",
                "classification": "hardware_behavior_only",
                "public_ready": True,
                "evidence": ["status timeline"],
                "limitations": ["Not accuracy validation."],
            },
            {
                "claim_id": "accuracy",
                "public_statement": "Measured grid RMSE is <PENDING>.",
                "classification": "pending",
                "public_ready": False,
                "evidence": [],
                "limitations": ["Grid collection pending."],
            },
            {
                "claim_id": "flight",
                "public_statement": "GHOST is flight-ready.",
                "classification": "prohibited",
                "public_ready": False,
                "evidence": [],
                "limitations": ["No flight test."],
            },
        ],
    }


def test_claims_template_is_release_safe_with_pending_claims_disabled():
    result = validate_claims(claims_template())
    assert result["valid"] is True
    assert result["public_ready_count"] == 1
    assert result["pending_claims"] == ["accuracy"]


def test_pending_or_prohibited_claim_cannot_be_public_ready():
    matrix = claims_template()
    matrix["claims"][1]["public_ready"] = True
    result = validate_claims(matrix)
    assert result["valid"] is False
    assert any("pending claim cannot be public_ready" in error for error in result["errors"])

    matrix = claims_template()
    matrix["claims"][2]["public_ready"] = True
    result = validate_claims(matrix)
    assert result["valid"] is False
    assert any("prohibited claim cannot be public_ready" in error for error in result["errors"])


def test_high_risk_wording_requires_validated_classification_and_resolution_gate():
    matrix = claims_template()
    risky = deepcopy(matrix["claims"][0])
    risky["claim_id"] = "risky"
    risky["public_statement"] = "GHOST is production-ready."
    matrix["claims"].append(risky)
    result = validate_claims(matrix)
    assert result["valid"] is False
    assert any("high-risk wording" in error for error in result["errors"])

    unresolved = validate_claims(claims_template(), require_all_resolved=True)
    assert unresolved["valid"] is False
    assert any("unresolved pending claims" in error for error in unresolved["errors"])
