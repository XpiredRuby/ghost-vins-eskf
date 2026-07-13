from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jsonschema import ValidationError

from ghost_sim_ros2.data_contract import (
    CONTRACT_VERSION,
    SCHEMA_VERSION,
    SI_UNITS,
    UNSPECIFIED_ID,
    artifact_sha256,
    build_run_identity,
    build_timestamps,
    build_validity,
    canonical_sha256,
    contract_envelope,
    load_schema,
    validate_payload,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = PACKAGE_ROOT / "schemas"


def envelope(frame_id: str = "ghost_local") -> dict:
    return contract_envelope(
        frame_id=frame_id,
        provenance={
            "calibration_id": UNSPECIFIED_ID,
            "configuration_id": canonical_sha256({"test": 1}),
            "configuration_label": "unit-test",
        },
        timestamps=build_timestamps(
            source_time_s=1.0,
            receipt_time_s=1.01,
            processing_time_s=1.02,
            publication_time_s=1.03,
        ),
        validity=build_validity(is_valid=True, state="VALID_TRACKING"),
    )


def test_canonical_configuration_hash_is_deterministic() -> None:
    left = canonical_sha256({"b": [2, 3], "a": 1})
    right = canonical_sha256({"a": 1, "b": [2, 3]})
    assert left == right
    assert left.startswith("sha256:")
    assert len(left) == 71


def test_artifact_hash_and_missing_calibration(tmp_path: Path) -> None:
    artifact = tmp_path / "calibration.json"
    artifact.write_text('{"fx":487.0}\n', encoding="utf-8")
    identifier = artifact_sha256(artifact)
    assert identifier.startswith("sha256:")
    assert artifact_sha256("") == UNSPECIFIED_ID
    assert artifact_sha256(tmp_path / "missing.json") == UNSPECIFIED_ID


def test_run_identity_uses_effective_configuration(tmp_path: Path) -> None:
    calibration = tmp_path / "cal.json"
    calibration.write_text("calibration-v1", encoding="utf-8")
    first = build_run_identity(
        node_name="tracker",
        frame_id="camera",
        configuration_label="formal-imm-v1",
        configuration={"rate_hz": 30.0, "timeout_s": 0.3},
        calibration_artifact_path=calibration,
    )
    second = build_run_identity(
        node_name="tracker",
        frame_id="camera",
        configuration_label="formal-imm-v1",
        configuration={"timeout_s": 0.3, "rate_hz": 30.0},
        calibration_artifact_path=calibration,
    )
    assert first == second
    assert first["calibration_id"] != UNSPECIFIED_ID


def test_all_schemas_are_valid_draft7() -> None:
    for name in [
        "formal_imm_futures.schema.json",
        "ghost_mh_futures.schema.json",
        "tracker_status.schema.json",
        "mission_validation.schema.json",
    ]:
        assert load_schema(name, SCHEMA_DIR)["$schema"].endswith("draft-07/schema#")


def test_representative_payloads_validate() -> None:
    formal = {
        **envelope("camera"),
        "tracker": "formal_imm",
        "sequence": 1,
        "visible": True,
        "initialized": True,
        "live_status": "LIVE_IMM_TRACKING",
        "measurement_age_s": 0.02,
        "estimate": {"x_m": 1.0, "y_m": 0.1},
        "mode_probabilities": {"smooth_cv": 0.8, "maneuver_cv": 0.2},
        "hypotheses": [],
    }
    mh = {
        **envelope("camera"),
        "tracker": "ghost_mh",
        "sequence": 1,
        "visible": False,
        "initialized": True,
        "measurement_age_s": 0.5,
        "estimate": {"x_m": 1.1, "y_m": 0.1},
        "hypotheses": [{"model": "constant_velocity", "relative_hypothesis_weight": 1.0}],
    }
    status = {
        **envelope("camera"),
        "tracker": "ghost_mh",
        "sequence": 1,
        "visible": False,
        "status_text": "OCCLUDED - HYPOTHESIS BANK",
        "live_status": "OCCLUDED_HYPOTHESIS_BANK",
        "measurement_age_s": 0.5,
    }
    mission = {
        **envelope("ghost_local"),
        "system": "GHOST-X mission",
        "passed": True,
        "mission_complete": True,
        "acceptance": {"target_reacquired": True},
    }
    validate_payload(formal, "formal_imm_futures.schema.json", SCHEMA_DIR)
    validate_payload(mh, "ghost_mh_futures.schema.json", SCHEMA_DIR)
    validate_payload(status, "tracker_status.schema.json", SCHEMA_DIR)
    validate_payload(mission, "mission_validation.schema.json", SCHEMA_DIR)


def test_schema_rejects_missing_contract_envelope() -> None:
    with pytest.raises(ValidationError):
        validate_payload(
            {"tracker": "formal_imm", "sequence": 1},
            "formal_imm_futures.schema.json",
            SCHEMA_DIR,
        )


def test_contract_yaml_has_required_sections() -> None:
    contract = yaml.safe_load(
        (PACKAGE_ROOT / "config" / "ghost_x_data_contract.yaml").read_text(encoding="utf-8")
    )
    assert contract["contract_version"] == CONTRACT_VERSION
    assert contract["schema_version"] == SCHEMA_VERSION
    for key in [
        "frames",
        "units",
        "covariance",
        "timestamps",
        "measurement_handling",
        "validity_states",
        "provenance",
        "json_outputs",
        "historical_evidence",
    ]:
        assert key in contract
    assert contract["units"]["position"] == SI_UNITS["position"]
