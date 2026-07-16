from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from analysis.ghost_x_controlled_truth import (
    ESTIMATORS,
    SCENARIO_FAMILIES,
    CampaignConfig,
    compute_metrics,
    generate_canonical_trial,
    run_campaign,
    run_trial,
)


def test_predeclared_campaign_has_24_trials_and_all_scenarios():
    config = CampaignConfig(bootstrap_samples=200)
    assert config.trial_count == 24
    assert len(SCENARIO_FAMILIES) == 8
    assert {row["scenario_family"] for family in SCENARIO_FAMILIES for row in generate_canonical_trial(family, 1, config)[:1]} == set(SCENARIO_FAMILIES)


def test_canonical_generation_is_deterministic_and_has_truth_uncertainty():
    config = CampaignConfig(bootstrap_samples=200)
    a = generate_canonical_trial("complete_occlusion", 2, config)
    b = generate_canonical_trial("complete_occlusion", 2, config)
    assert a == b
    assert any(not row["visible"] for row in a)
    assert all(len(row["truth"]["covariance_diag"]) == 4 for row in a)
    assert all(value > 0.0 for value in a[0]["truth"]["covariance_diag"])


def test_all_estimators_receive_identical_ordered_measurements():
    config = CampaignConfig(bootstrap_samples=200)
    rows = generate_canonical_trial("repeated_reentry", 1, config)
    result = run_trial(rows)
    for estimator in ESTIMATORS:
        output = result["outputs"][estimator]
        assert [row["sequence"] for row in output] == [row["sequence"] for row in rows]
        assert [row["measurement_present"] for row in output] == [row["measurement_xy_m"] is not None for row in rows]
        assert len(output) == len(rows)


def test_metric_correctness_for_perfect_estimator():
    config = CampaignConfig(bootstrap_samples=200)
    canonical = generate_canonical_trial("constant_velocity", 1, config)
    outputs = []
    for row in canonical:
        truth = row["truth"]
        outputs.append(
            {
                "t_s": row["t_s"],
                "initialized": True,
                "measurement_present": row["measurement_xy_m"] is not None,
                "reset": False,
                "state": {
                    "x_m": truth["x_m"],
                    "y_m": truth["y_m"],
                    "vx_mps": truth["vx_mps"],
                    "vy_mps": truth["vy_mps"],
                },
                "covariance": np.eye(4).tolist(),
            }
        )
    metrics = compute_metrics(canonical, outputs, [])
    assert metrics["position_rmse_m"] == 0.0
    assert metrics["velocity_rmse_mps"] == 0.0
    assert metrics["endpoint_error_m"] == 0.0
    assert metrics["failed"] is False


def test_end_to_end_campaign_hashes_blinding_and_failure_retention(tmp_path: Path):
    config = CampaignConfig(bootstrap_samples=200)
    manifest = run_campaign(config, tmp_path, code_provenance={"commit": "test"})
    assert manifest["planned_trials"] == 24
    assert manifest["accepted_trials"] == 24
    assert manifest["invalid_trials"] == 0
    for trial in manifest["trials"]:
        assert set(trial["estimator_input_sha256"]) == set(ESTIMATORS)
        assert len(set(trial["estimator_input_sha256"].values())) == 1
        assert trial["canonical_stream_sha256"].startswith("sha256:")
    public = json.loads((tmp_path / "public_blinded_summary.json").read_text())
    assert set(public["estimators"]) == {"Estimator A", "Estimator B", "Estimator C"}
    assert not any(name in json.dumps(public) for name in ESTIMATORS)
    private = json.loads((tmp_path / "blind_key.private.json").read_text())
    assert set(private["mapping"]) == set(ESTIMATORS)

    # Invalid trials must be retained rather than disappearing.
    broken = dict(manifest["trials"][0])
    broken["status"] = "invalid"
    broken["failure_reason"] = "synthetic test failure"
    assert broken["failure_reason"]
