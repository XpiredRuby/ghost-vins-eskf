import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.campaign_analysis_runner import run_audited_analysis  # noqa: E402
from analysis.campaign_public_visuals import choose_representative, generate_public_visuals  # noqa: E402


def write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def build_audited_campaign(root: Path):
    condition = {
        "condition_id": "endpoint_occ_1s",
        "planned_repetitions": 3,
        "target_occlusion_duration_s": 1.0,
        "motion_profile": "measured_endpoint_straight_line",
        "ground_truth_method": "measured_stationary_endpoint",
        "primary_metric": "endpoint_prediction_error_m",
    }
    planned = []
    state_trials = []
    for repetition, raw_gap in enumerate((1.0, 1.1, 1.5), start=1):
        trial_id = f"endpoint_occ_1s_{repetition:02d}"
        relative = f"trial_directories/{trial_id}"
        trial_dir = root / relative
        trial_dir.mkdir(parents=True)
        planned.append(
            {
                "trial_id": trial_id,
                "condition_id": condition["condition_id"],
                "repetition": repetition,
                "status": "planned",
                "trial_dir": relative,
                "endpoint_truth_m": None,
                "rejection_reason": None,
            }
        )
        state_trials.append(
            {
                "trial_id": trial_id,
                "condition_id": condition["condition_id"],
                "repetition": repetition,
                "status": "accepted",
                "endpoint_truth_m": {"x": 1.0, "y": 0.5},
                "actual_measurement_gap_s": raw_gap,
                "gap_tolerance_status": "PASS" if raw_gap <= 1.25 else "INVALID_FIXTURE",
                "rejection_reason": None,
                "operator_notes": "fixture",
            }
        )

        vision = []
        t = 0.0
        first_post = 1.0 + raw_gap
        while t <= 3.5:
            if t <= 1.0 or t >= first_post:
                vision.append({"t_rel_s": round(t, 5), "position": {"x_m": min(1.0, t / 2), "y_m": 0.5}})
            t += 0.1
        write_jsonl(trial_dir / "vision_pose.jsonl", vision)

        for tracker, bias in (("imm", 0.01 * repetition), ("mh", 0.03 * repetition)):
            rows = []
            t = 0.0
            while t <= 3.5:
                visible = t <= 1.0 or t >= first_post
                rows.append(
                    {
                        "t_rel_s": round(t, 5),
                        "payload": {
                            "visible": visible,
                            "initialized": True,
                            "measurement_age_s": 0.0 if visible else t - 1.0,
                            "estimate": {
                                "x_m": min(1.0, t / 2) + bias,
                                "y_m": 0.5,
                                "cov_xx": 0.001,
                                "cov_yy": 0.002,
                            },
                        },
                    }
                )
                t += 0.05
            write_jsonl(trial_dir / f"{tracker}_futures.jsonl", rows)

    manifest = {
        "schema_version": 1,
        "campaign_id": "audited_fixture",
        "protocol_commit": "abc1234",
        "conditions": [condition],
        "trials": planned,
    }
    state = {
        "schema_version": 1,
        "campaign_id": "audited_fixture",
        "campaign_collection_status": "ALL_SLOTS_RECORDED_PENDING_FINALIZATION",
        "pinned_manifest_sha256": "fixture",
        "trials": state_trials,
    }
    (root / "campaign_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "campaign_state.json").write_text(json.dumps(state), encoding="utf-8")


def test_audited_runner_merges_state_and_filters_gap_violation(tmp_path: Path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    build_audited_campaign(campaign)
    out = tmp_path / "analysis"
    summary = run_audited_analysis(campaign, out, n_boot=200, seed=7)

    assert summary["analysis_manifest_source"] == "campaign_manifest.json + campaign_state.json"
    assert summary["analyzed_trials"] == 3
    condition = summary["conditions"][0]
    assert condition["accepted_analyzed"] == 3
    assert condition["protocol_compliant_valid_pairs"] == 2
    assert condition["gap_tolerance_failures"] == 1
    assert condition["paired_statistics"]["n_trials"] == 2
    assert all("estimated_missing_duration_s" in trial["measured_gap"] for trial in summary["trials"])
    persisted = json.loads((out / "campaign_summary.json").read_text())
    assert persisted["conditions"][0]["valid_paired_metrics"] == 2


def test_public_visuals_label_trackers_and_choose_median_like_trial(tmp_path: Path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    build_audited_campaign(campaign)
    analysis = tmp_path / "analysis"
    summary = run_audited_analysis(campaign, analysis, n_boot=200, seed=7)
    public = tmp_path / "public"
    report = generate_public_visuals(analysis / "campaign_summary.json", public)

    condition = summary["conditions"][0]
    representative = choose_representative(summary, condition)
    assert representative is not None
    assert representative["gap_within_protocol_tolerance"] is True
    assert "paired_trial_errors.png" in report["generated_files"]
    assert "tracker_error_distributions.png" in report["generated_files"]
    assert any(name.startswith("representative_endpoint_occ_1s") for name in report["generated_files"])
    for name in report["generated_files"]:
        assert (public / name).exists(), name
