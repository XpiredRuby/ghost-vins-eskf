import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
for item in (ROOT, TOOLS):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from campaign_operations import (  # noqa: E402
    balanced_randomized_order,
    cue_plan_for_condition,
    initialize_campaign,
)
from trial_conductor import load_plan  # noqa: E402


def template():
    return {
        "schema_version": 1,
        "campaign_id": "test_campaign",
        "protocol_commit": "0000000",
        "randomization_seed": 260710,
        "coordinate_frame": "camera",
        "conditions": [
            {
                "condition_id": "static_visible",
                "planned_repetitions": 5,
                "target_occlusion_duration_s": 0.0,
                "motion_profile": "stationary_visible",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "steady_state_position_error_m",
            },
            {
                "condition_id": "endpoint_no_occlusion",
                "planned_repetitions": 10,
                "target_occlusion_duration_s": 0.0,
                "motion_profile": "measured_endpoint_straight_line",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "endpoint_prediction_error_m",
            },
            {
                "condition_id": "endpoint_occ_1s",
                "planned_repetitions": 10,
                "target_occlusion_duration_s": 1.0,
                "motion_profile": "measured_endpoint_straight_line",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "endpoint_prediction_error_m",
            },
            {
                "condition_id": "endpoint_occ_2s",
                "planned_repetitions": 10,
                "target_occlusion_duration_s": 2.0,
                "motion_profile": "measured_endpoint_straight_line",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "endpoint_prediction_error_m",
            },
            {
                "condition_id": "endpoint_occ_3s",
                "planned_repetitions": 10,
                "target_occlusion_duration_s": 3.0,
                "motion_profile": "measured_endpoint_straight_line",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "endpoint_prediction_error_m",
            },
            {
                "condition_id": "maneuver_occ_2s",
                "planned_repetitions": 10,
                "target_occlusion_duration_s": 2.0,
                "motion_profile": "measured_endpoint_single_turn",
                "ground_truth_method": "measured_stationary_endpoint",
                "primary_metric": "endpoint_prediction_error_m",
            },
        ],
        "trials": [],
        "protocol_commit_status": "PLACEHOLDER_REPLACE_BEFORE_COLLECTION",
    }


def test_balanced_order_is_deterministic_complete_and_unique():
    first = balanced_randomized_order(template()["conditions"], seed=260710)
    second = balanced_randomized_order(template()["conditions"], seed=260710)
    assert first == second
    assert len(first) == 55
    assert len({item.trial_id for item in first}) == 55
    assert [item.sequence for item in first] == list(range(1, 56))
    assert {item.condition_id for item in first[:6]} == {
        "static_visible",
        "endpoint_no_occlusion",
        "endpoint_occ_1s",
        "endpoint_occ_2s",
        "endpoint_occ_3s",
        "maneuver_occ_2s",
    }


def test_initialize_campaign_creates_pinned_plan_and_trial_directories(tmp_path: Path):
    out = tmp_path / "campaign"
    lock = initialize_campaign(template(), out, "abc1234")

    manifest = json.loads((out / "campaign_manifest.json").read_text())
    assert manifest["protocol_commit"] == "abc1234"
    assert manifest["protocol_commit_status"] == "PINNED_BEFORE_COLLECTION"
    assert len(manifest["trials"]) == 55
    assert lock["planned_trials"] == 55
    assert lock["lock_status"] == "PRECOLLECTION_PLAN_PINNED"
    assert len(list((out / "trial_directories").iterdir())) == 55
    assert (out / "campaign_validation_before.json").exists()
    assert (out / "campaign_lock.json").exists()

    with (out / "randomized_trial_order.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 55
    assert {row["trial_id"] for row in rows} == {trial["trial_id"] for trial in manifest["trials"]}


def test_initialize_campaign_rejects_zero_or_invalid_commit(tmp_path: Path):
    for value in ("0000000", "not-a-commit", "123"):
        with pytest.raises(ValueError, match="protocol_commit"):
            initialize_campaign(template(), tmp_path / value.replace("/", "_"), value)


def test_initialize_campaign_refuses_nonempty_existing_directory(tmp_path: Path):
    out = tmp_path / "campaign"
    out.mkdir()
    (out / "existing.txt").write_text("do not overwrite")
    with pytest.raises(FileExistsError):
        initialize_campaign(template(), out, "abc1234", overwrite_empty=True)


def test_cue_plans_cover_static_straight_occlusion_and_maneuver():
    by_id = {item["condition_id"]: item for item in template()["conditions"]}
    static = cue_plan_for_condition(by_id["static_visible"])
    no_occ = cue_plan_for_condition(by_id["endpoint_no_occlusion"])
    occ3 = cue_plan_for_condition(by_id["endpoint_occ_3s"])
    maneuver = cue_plan_for_condition(by_id["maneuver_occ_2s"])

    assert [phase["cue"] for phase in static] == ["HOLD START", "STATIONARY SAMPLE", "POST-ROLL", "DONE"]
    assert "OCCLUDE NOW" not in [phase["cue"] for phase in no_occ]
    occ_phase = next(phase for phase in occ3 if phase["cue"] == "OCCLUDE NOW")
    assert occ_phase["duration_s"] == 3.0
    assert [phase["cue"] for phase in maneuver].count("TURN") == 1
    assert [phase["cue"] for phase in maneuver].count("OCCLUDE NOW") == 1


def test_trial_conductor_loads_selected_sequence(tmp_path: Path):
    out = tmp_path / "campaign"
    initialize_campaign(template(), out, "abc1234")
    plan = load_plan(out, 1)
    assert plan["sequence"] == 1
    assert plan["trial_id"]
    assert plan["phases"][-1]["cue"] == "DONE"
    with pytest.raises(ValueError, match="not present"):
        load_plan(out, 999)
