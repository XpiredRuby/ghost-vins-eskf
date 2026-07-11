import sys
import zipfile
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from evidence_integrity import create_package, missing_required_artifacts, verify_package  # noqa: E402


def _controlled_r_fixture(root: Path):
    required = {
        "protocol_metadata.txt": "protocol_commit_hash=abc1234\n",
        "camera_control_readbacks.tsv": "stage\tcontrol\texpected\tactual\tstatus\n",
        "camera_controls_before.txt": "controls before\n",
        "camera_controls_after_trial.txt": "controls after\n",
        "operator_attestation.txt": "response=NO\n",
        "vision_pose.jsonl": '{"t_rel_s":0.0,"position":{"x_m":1,"y_m":0,"z_m":0}}\n',
        "collection_quality.json": '{"acceptable":true}\n',
        "noise_summary.json": '{"r_xx_m2":1e-6}\n',
        "noise_summary.md": "# Noise\n",
        "final_collection_status.txt": "ACCEPTABLE_FOR_ENGINEER_REVIEW_DOES_NOT_VALIDATE_TRACKER_ACCURACY\n",
    }
    root.mkdir()
    for name, content in required.items():
        (root / name).write_text(content, encoding="utf-8")


def test_complete_controlled_r_package_verifies(tmp_path: Path):
    source = tmp_path / "controlled_r"
    _controlled_r_fixture(source)
    archive = tmp_path / "controlled_r_evidence.zip"
    manifest = create_package(source, archive, profile="controlled_r")
    result = verify_package(archive)

    assert manifest["package_status"] == "COMPLETE"
    assert manifest["missing_required_artifacts"] == []
    assert result["valid"] is True
    assert result["profile"] == "controlled_r"
    assert result["file_count"] == 10


def test_package_refuses_missing_required_artifacts(tmp_path: Path):
    source = tmp_path / "bad"
    source.mkdir()
    (source / "protocol_metadata.txt").write_text("partial")
    with pytest.raises(ValueError, match="missing required"):
        create_package(source, tmp_path / "bad.zip", profile="controlled_r")
    assert "vision_pose.jsonl" in missing_required_artifacts(source, "controlled_r")


def test_allow_incomplete_records_missing_artifacts(tmp_path: Path):
    source = tmp_path / "partial"
    source.mkdir()
    (source / "notes.txt").write_text("partial")
    archive = tmp_path / "partial.zip"
    manifest = create_package(source, archive, profile="campaign", allow_incomplete=True)
    result = verify_package(archive)

    assert manifest["package_status"] == "INCOMPLETE_ALLOWED"
    assert manifest["missing_required_artifacts"]
    assert result["valid"] is True


def test_verify_detects_tampered_member(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "evidence.txt").write_text("original", encoding="utf-8")
    archive = tmp_path / "original.zip"
    create_package(source, archive)

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive, "r") as old, zipfile.ZipFile(tampered, "w") as new:
        for info in old.infolist():
            payload = old.read(info.filename)
            if info.filename == "evidence/evidence.txt":
                payload = b"tampered"
            new.writestr(info, payload)
    result = verify_package(tampered)
    assert result["valid"] is False
    assert any("SHA-256 mismatch" in error for error in result["errors"])


def test_archive_is_not_overwritten(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("a")
    archive = tmp_path / "evidence.zip"
    create_package(source, archive)
    with pytest.raises(FileExistsError):
        create_package(source, archive)
