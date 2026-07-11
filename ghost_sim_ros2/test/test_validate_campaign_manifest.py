import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.validate_campaign_manifest import validate_manifest  # noqa: E402


def _manifest():
    return {
        "schema_version": 1,
        "campaign_id": "ghost_imm_mh_v1",
        "protocol_commit": "1234abc",
        "randomization_seed": 260710,
        "conditions": [
            {
                "condition_id": "endpoint_occ_1s",
                "planned_repetitions": 5,
                "target_occlusion_duration_s": 1.0,
                "motion_profile": "measured_endpoint_straight_line",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "endpoint_prediction_error_m",
            },
            {
                "condition_id": "endpoint_occ_2s",
                "planned_repetitions": 5,
                "target_occlusion_duration_s": 2.0,
                "motion_profile": "measured_endpoint_straight_line",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "endpoint_prediction_error_m",
            },
        ],
        "trials": [],
    }


def test_validate_planned_manifest_reports_expected_counts():
    result = validate_manifest(_manifest())

    assert result["valid"] is True
    assert result["n_conditions"] == 2
    assert result["planned_trials"] == 10
    assert result["recorded_trials"] == 0
    assert len(result["missing_trial_slots"]) == 10


def test_validate_manifest_accepts_complete_accepted_and_rejected_slots():
    manifest = _manifest()
    trials = []
    for condition in manifest["conditions"]:
        for repetition in range(1, condition["planned_repetitions"] + 1):
            status = "rejected" if repetition == 5 else "accepted"
            trial = {
                "trial_id": f"{condition['condition_id']}_{repetition:02d}",
                "condition_id": condition["condition_id"],
                "repetition": repetition,
                "status": status,
                "trial_dir": f"/tmp/{condition['condition_id']}_{repetition:02d}",
                "endpoint_truth_m": {"x": 1.0, "y": 0.5},
            }
            if status == "rejected":
                trial["rejection_reason"] = "camera bumped"
            trials.append(trial)
    manifest["trials"] = trials

    result = validate_manifest(manifest, require_complete=True)

    assert result["valid"] is True
    assert result["status_counts"] == {"planned": 0, "accepted": 8, "rejected": 2}
    assert result["missing_trial_slots"] == []


def test_validate_manifest_rejects_duplicate_slot_and_missing_rejection_reason():
    manifest = _manifest()
    manifest["trials"] = [
        {
            "trial_id": "trial_a",
            "condition_id": "endpoint_occ_1s",
            "repetition": 1,
            "status": "accepted",
            "trial_dir": "/tmp/trial_a",
        },
        {
            "trial_id": "trial_b",
            "condition_id": "endpoint_occ_1s",
            "repetition": 1,
            "status": "rejected",
        },
    ]

    result = validate_manifest(manifest)

    assert result["valid"] is False
    assert any("duplicate condition/repetition slot" in error for error in result["errors"])
    assert any("rejection_reason is required" in error for error in result["errors"])


def test_validate_manifest_require_complete_rejects_missing_slots():
    result = validate_manifest(_manifest(), require_complete=True)

    assert result["valid"] is False
    assert any("planned trial slots are missing" in error for error in result["errors"])


def test_validate_manifest_warns_for_zero_commit_placeholder():
    manifest = _manifest()
    manifest["protocol_commit"] = "0000000"

    result = validate_manifest(manifest)

    assert result["valid"] is True
    assert any("placeholder" in warning for warning in result["warnings"])
