from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from analysis.measurement_characterization import analyze_campaign


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent


def initialize_campaign(tmp_path: Path) -> Path:
    calibration = tmp_path / "calibration.json"
    calibration.write_text('{"camera_matrix":[[1,0,0],[0,1,0],[0,0,1]],"dist_coeffs":[0,0,0,0,0]}\n', encoding="utf-8")
    campaign = tmp_path / "g3_campaign"
    result = subprocess.run(
        [
            sys.executable,
            str(PACKAGE_ROOT / "tools" / "init_ghost_x_g3_campaign.py"),
            "--design",
            str(PACKAGE_ROOT / "config" / "ghost_x_g3_measurement_campaign.yaml"),
            "--out",
            str(campaign),
            "--calibration",
            str(calibration),
            "--repo-root",
            str(REPO_ROOT),
        ],
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return campaign


def write_synthetic_trials(campaign: Path) -> None:
    rng = np.random.default_rng(20260713)
    for trial_dir in sorted((campaign / "trials").iterdir()):
        manifest_path = trial_dir / "trial_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        attempt_dir = trial_dir / "attempt_01"
        attempt_dir.mkdir()
        times = np.arange(0.0, 90.0 + 1.0 / 15.0, 1.0 / 15.0)
        range_m = float(manifest["range_m"])
        yaw_rad = abs(np.deg2rad(float(manifest["yaw_deg"])))
        std_x = 0.0007 + 0.0008 * range_m + 0.0004 * yaw_rad
        std_y = 0.00015 + 0.0002 * range_m + 0.0001 * yaw_rad
        rho = 0.35
        covariance = np.asarray(
            [
                [std_x**2, rho * std_x * std_y],
                [rho * std_x * std_y, std_y**2],
            ]
        )
        noise = rng.multivariate_normal([0.0, 0.0], covariance, size=len(times))
        drift = np.column_stack([2.0e-6 * times, -1.0e-6 * times])
        positions = np.asarray([range_m, 0.0]) + noise + drift
        with (attempt_dir / "vision_pose_log.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["t", "x", "y", "z"])
            for t, (x, y) in zip(times, positions):
                writer.writerow([f"{t:.9f}", f"{x:.9f}", f"{y:.9f}", "0.0"])
        (attempt_dir / "direct_capture_summary.json").write_text(
            json.dumps(
                {
                    "brightness_mean": 120.0,
                    "brightness_min": 80.0,
                    "brightness_max": 160.0,
                    "decision_margin_mean": 80.0,
                    "decision_margin_min": 40.0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        manifest["accepted_attempt"] = 1
        manifest["status"] = "CAPTURED_ACCEPTED"
        manifest["attempts"] = [{"attempt": 1, "status": "CAPTURED_ACCEPTED"}]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def test_g3_design_is_predeclared_and_complete() -> None:
    design = yaml.safe_load(
        (PACKAGE_ROOT / "config" / "ghost_x_g3_measurement_campaign.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert design["protocol_version"] == "ghost-x-g3-v1"
    assert len(design["factors"]["range_m"]) == 3
    assert len(design["factors"]["yaw_deg"]) == 3
    assert design["collection"]["repeats_per_condition"] == 2
    assert design["exit_criteria"]["minimum_complete_trials"] == 18
    assert len(design["candidate_covariance_models"]) == 4


def test_initializer_creates_balanced_deterministic_slots(tmp_path: Path) -> None:
    campaign = initialize_campaign(tmp_path)
    manifest = json.loads((campaign / "campaign_manifest.json").read_text(encoding="utf-8"))
    assert manifest["planned_trial_count"] == 18
    assert manifest["condition_count"] == 9
    with (campaign / "trial_order.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 18
    assert len({row["trial_id"] for row in rows}) == 18
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["condition_id"]] = counts.get(row["condition_id"], 0) + 1
    assert set(counts.values()) == {2}


def test_complete_synthetic_campaign_selects_covariance_model(tmp_path: Path) -> None:
    campaign = initialize_campaign(tmp_path)
    write_synthetic_trials(campaign)
    out = tmp_path / "analysis"
    report = analyze_campaign(campaign, out)
    assert report["status"] == "COMPLETE"
    assert report["completed_acceptable_trials"] == 18
    assert report["completed_conditions"] == 9
    assert report["covariance_model_selection"]["status"] == "MODEL_SELECTED"
    assert report["covariance_model_selection"]["selected_model"] in {
        "constant_full",
        "range_logdiag_fixed_corr",
        "range_yaw_logdiag_fixed_corr",
        "condition_shrinkage",
    }
    assert len(report["covariance_model_selection"]["scores"]) == 4
    assert (out / "measurement_characterization.json").is_file()
    assert (out / "measurement_characterization.md").is_file()
    assert (out / "trial_summary.csv").is_file()
    first = report["trial_results"][0]
    assert "fixture_referenced_bias_m" in first
    assert "detrended_covariance_m2" in first
    assert "jarque_bera_p_value" in first["diagnostics"]["x"]["detrended"]
    assert len(first["diagnostics"]["x"]["detrended"]["ljung_box"]) == 3
