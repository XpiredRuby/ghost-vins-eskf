import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.campaign_analysis import analyze_campaign, find_measurement_gap, paired_summary  # noqa: E402
from analysis.grid_validation_visuals import generate_grid_visuals  # noqa: E402


def _write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _campaign_fixture(root: Path):
    conditions = [
        {
            "condition_id": "endpoint_occ_1s",
            "planned_repetitions": 3,
            "target_occlusion_duration_s": 1.0,
            "motion_profile": "measured_endpoint_straight_line",
            "ground_truth_method": "measured_stationary_endpoint",
            "primary_metric": "endpoint_prediction_error_m",
        }
    ]
    trials = []
    for rep in range(1, 4):
        trial_id = f"endpoint_occ_1s_{rep:02d}"
        trial_dir = root / "trial_directories" / trial_id
        trial_dir.mkdir(parents=True)
        trials.append(
            {
                "trial_id": trial_id,
                "condition_id": "endpoint_occ_1s",
                "repetition": rep,
                "status": "accepted",
                "trial_dir": f"trial_directories/{trial_id}",
                "endpoint_truth_m": {"x": 1.0, "y": 0.5},
                "rejection_reason": None,
            }
        )
        vision = []
        t = 0.0
        while t <= 3.0:
            if not (1.0 < t < 2.0):
                vision.append({"t_rel_s": round(t, 4), "position": {"x_m": t / 3, "y_m": 0.5}})
            t += 0.1
        _write_jsonl(trial_dir / "vision_pose.jsonl", vision)
        for tracker, bias in (("imm", 0.01 * rep), ("mh", 0.03 * rep)):
            rows = []
            t = 0.0
            while t <= 3.0:
                visible = not (1.0 < t < 2.0)
                x = min(1.0, t / 2.0) + bias
                payload = {
                    "visible": visible,
                    "initialized": True,
                    "measurement_age_s": 0.0 if visible else t - 1.0,
                    "estimate": {
                        "x_m": x,
                        "y_m": 0.5,
                        "cov_xx": 0.001,
                        "cov_yy": 0.002,
                    },
                }
                rows.append({"t_rel_s": round(t, 4), "payload": payload})
                t += 0.05
            _write_jsonl(trial_dir / f"{tracker}_futures.jsonl", rows)
    manifest = {
        "campaign_id": "fixture_campaign",
        "protocol_commit": "abc1234",
        "conditions": conditions,
        "trials": trials,
    }
    (root / "campaign_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_find_measurement_gap_selects_longest_interval():
    gap = find_measurement_gap([0.0, 0.1, 0.2, 1.3, 1.4], 1.0)
    assert abs(gap["duration_s"] - 1.1) < 1e-12
    assert gap["start_s"] == 0.2
    assert gap["end_s"] == 1.3


def test_paired_summary_reports_expected_direction_and_interval():
    result = paired_summary([0.02, 0.03, 0.04], [0.05, 0.06, 0.07], n_boot=300, seed=7)
    assert result["median_mh_minus_imm_m"] > 0
    assert result["bootstrap_ci_95_mh_minus_imm_m"]["low"] > 0


def test_campaign_analysis_writes_metrics_plots_and_report(tmp_path: Path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    _campaign_fixture(campaign)
    out = tmp_path / "results"
    summary = analyze_campaign(campaign, out, n_boot=200, seed=7)

    assert summary["analyzed_trials"] == 3
    assert summary["issues"] == []
    condition = summary["conditions"][0]
    assert condition["valid_paired_metrics"] == 3
    assert condition["paired_statistics"]["median_mh_minus_imm_m"] > 0
    for name in (
        "campaign_summary.json",
        "campaign_summary.md",
        "campaign_report.html",
        "endpoint_error_by_condition.png",
        "paired_difference_by_condition.png",
        "error_vs_measurement_gap.png",
        "reacquisition_latency_by_condition.png",
        "failure_rate_by_condition.png",
        "trajectory_overlay_endpoint_occ_1s.png",
    ):
        assert (out / name).exists(), name


def test_grid_visuals_generate_four_plots_and_dashboard(tmp_path: Path):
    points = []
    for index, (x, y) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1), (0.5, 0.4)), start=1):
        dx, dy = 0.01 * index, -0.005 * index
        points.append(
            {
                "point_id": f"P{index}",
                "x_true_m": x,
                "y_true_m": y,
                "x_mean_m": x + dx,
                "y_mean_m": y + dy,
                "dx_m": dx,
                "dy_m": dy,
                "error_m": (dx * dx + dy * dy) ** 0.5,
            }
        )
    summary = {
        "aggregate": {
            "rmse_m": 0.03,
            "mean_error_m": 0.025,
            "max_error_m": 0.05,
            "bias_x_m": 0.02,
            "bias_y_m": -0.01,
        },
        "points": points,
    }
    path = tmp_path / "grid_validation_summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    out = tmp_path / "grid_visuals"
    report = generate_grid_visuals(path, out)

    assert report["n_points"] == 5
    assert len(report["plots"]) == 4
    for name in report["plots"] + ["grid_visuals_summary.json", "grid_validation_dashboard.html"]:
        assert (out / name).exists(), name
