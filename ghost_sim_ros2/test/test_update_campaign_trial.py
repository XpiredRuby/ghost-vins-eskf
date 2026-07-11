import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for item in (ROOT, TOOLS):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from campaign_operations import initialize_campaign  # noqa: E402
from update_campaign_trial import finalize_campaign, sha256, update_trial_state  # noqa: E402


def template(repetitions=1):
    return {
        "schema_version": 1,
        "campaign_id": "state_test",
        "protocol_commit": "0000000",
        "randomization_seed": 260710,
        "coordinate_frame": "camera",
        "conditions": [
            {
                "condition_id": "endpoint_occ_1s",
                "planned_repetitions": repetitions,
                "target_occlusion_duration_s": 1.0,
                "motion_profile": "measured_endpoint_straight_line",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "endpoint_prediction_error_m",
            }
        ],
        "trials": [],
        "protocol_commit_status": "PLACEHOLDER_REPLACE_BEFORE_COLLECTION",
    }


def make_campaign(tmp_path: Path, repetitions=1):
    root = tmp_path / "campaign"
    initialize_campaign(template(repetitions), root, "abc1234")
    return root


def add_raw_logs(root: Path, trial_id="endpoint_occ_1s_01"):
    trial_dir = root / "trial_directories" / trial_id
    for name in ("vision_pose.jsonl", "imm_futures.jsonl", "mh_futures.jsonl"):
        (trial_dir / name).write_text('{"sample":true}\n', encoding="utf-8")


def test_accept_writes_mutable_state_without_changing_pinned_manifest(tmp_path: Path):
    root = make_campaign(tmp_path)
    add_raw_logs(root)
    pinned_hash = sha256(root / "campaign_manifest.json")

    result = update_trial_state(
        root,
        "endpoint_occ_1s_01",
        action="accept",
        endpoint_x=1.2,
        endpoint_y=0.4,
        actual_gap_s=1.05,
        notes="clean trial",
    )

    assert sha256(root / "campaign_manifest.json") == pinned_hash
    state = json.loads((root / "campaign_state.json").read_text())
    assert state["status_counts"] == {"planned": 0, "accepted": 1, "rejected": 0}
    assert state["trials"][0]["endpoint_truth_m"] == {"x": 1.2, "y": 0.4}
    effective = json.loads((root / "campaign_manifest_effective.json").read_text())
    assert effective["trials"][0]["status"] == "accepted"
    assert result["validation"]["valid"] is True
    assert (root / "campaign_amendments.jsonl").exists()


def test_accept_rejects_gap_outside_predeclared_tolerance(tmp_path: Path):
    root = make_campaign(tmp_path)
    add_raw_logs(root)
    with pytest.raises(ValueError, match="outside the ±0.25s protocol tolerance"):
        update_trial_state(
            root,
            "endpoint_occ_1s_01",
            action="accept",
            endpoint_x=1.0,
            endpoint_y=0.5,
            actual_gap_s=1.4,
        )


def test_accept_requires_raw_logs_and_endpoint_truth(tmp_path: Path):
    root = make_campaign(tmp_path)
    with pytest.raises(ValueError, match="finite endpoint"):
        update_trial_state(root, "endpoint_occ_1s_01", action="accept", actual_gap_s=1.0)
    with pytest.raises(ValueError, match="missing required raw logs"):
        update_trial_state(
            root,
            "endpoint_occ_1s_01",
            action="accept",
            endpoint_x=1.0,
            endpoint_y=0.5,
            actual_gap_s=1.0,
        )


def test_rejection_requires_reason_and_preserves_slot(tmp_path: Path):
    root = make_campaign(tmp_path)
    with pytest.raises(ValueError, match="non-empty reason"):
        update_trial_state(root, "endpoint_occ_1s_01", action="reject", reason="")
    update_trial_state(
        root,
        "endpoint_occ_1s_01",
        action="reject",
        reason="camera mount was bumped",
        actual_gap_s=0.8,
    )
    state = json.loads((root / "campaign_state.json").read_text())
    assert state["trials"][0]["status"] == "rejected"
    assert state["trials"][0]["rejection_reason"] == "camera mount was bumped"
    assert (root / "trial_directories" / "endpoint_occ_1s_01").exists()


def test_amendment_requires_reason_and_finalization_requires_no_planned_slots(tmp_path: Path):
    root = make_campaign(tmp_path, repetitions=2)
    update_trial_state(root, "endpoint_occ_1s_01", action="reject", reason="invalid gap")
    with pytest.raises(ValueError, match="explicit --amend-reason"):
        update_trial_state(root, "endpoint_occ_1s_01", action="reject", reason="better wording")
    update_trial_state(
        root,
        "endpoint_occ_1s_01",
        action="reject",
        reason="measured gap outside tolerance",
        amend_reason="clarify the original rejection reason",
    )
    with pytest.raises(ValueError, match="remain planned"):
        finalize_campaign(root)
    update_trial_state(root, "endpoint_occ_1s_02", action="reject", reason="lighting changed")
    result = finalize_campaign(root)
    assert result["campaign_collection_status"] == "COLLECTION_COMPLETE_PENDING_ANALYSIS"
    assert result["validation"]["valid"] is True
