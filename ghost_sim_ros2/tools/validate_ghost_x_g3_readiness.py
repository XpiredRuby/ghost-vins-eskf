#!/usr/bin/env python3
"""Validate GHOST-X G3 software/protocol readiness before physical collection."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    package = args.package_root.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {}

    design_path = package / "config/ghost_x_g3_measurement_campaign.yaml"
    design = yaml.safe_load(design_path.read_text(encoding="utf-8"))
    ranges = design["factors"]["range_m"]
    yaws = design["factors"]["yaw_deg"]
    repeats = int(design["collection"]["repeats_per_condition"])
    planned_conditions = len(ranges) * len(yaws)
    planned_trials = planned_conditions * repeats
    checks["design"] = {
        "protocol_version": design.get("protocol_version"),
        "ranges": ranges,
        "yaws": yaws,
        "repeats": repeats,
        "planned_conditions": planned_conditions,
        "planned_trials": planned_trials,
        "analysis_window_s": design["collection"]["analysis_window_s"],
        "candidate_models": [row["id"] for row in design["candidate_covariance_models"]],
    }
    if planned_conditions < 9:
        errors.append("G3 requires at least nine range/yaw conditions")
    if planned_trials < 18:
        errors.append("G3 requires at least 18 planned trials")
    if design["collection"]["analysis_window_s"] != [15.0, 75.0]:
        errors.append("G3 v1 fixed analysis window must be [15.0, 75.0]")
    if len(design["candidate_covariance_models"]) < 3:
        errors.append("G3 requires multiple predeclared covariance candidates")
    if not design["truth"].get("camera_range_reference"):
        errors.append("G3 requires an explicit camera range reference plane")
    yaw_sign = design["truth"].get("yaw_sign_convention", {})
    if not all(key in yaw_sign for key in ("zero_deg", "positive_deg", "negative_deg")):
        errors.append("G3 requires an explicit physical yaw sign convention")

    required_files = [
        "tools/init_ghost_x_g3_campaign.py",
        "tools/collect_ghost_x_g3_trial.py",
        "analysis/measurement_characterization.py",
        "docs/GHOST_X_G3_MEASUREMENT_PROTOCOL.md",
        "test/test_ghost_x_g3.py",
    ]
    file_checks: dict[str, bool] = {}
    for relative in required_files:
        present = (package / relative).is_file()
        file_checks[relative] = present
        if not present:
            errors.append(f"missing required G3 file: {relative}")
    checks["required_files"] = file_checks

    source_expectations = {
        "tools/init_ghost_x_g3_campaign.py": ["randomization_seed", "calibration_sha256", "trial_order.csv"],
        "tools/collect_ghost_x_g3_trial.py": ["lock_uvc_camera_controls.sh", "collection_quality.json", "accepted_attempt"],
        "analysis/measurement_characterization.py": ["jarque_bera", "ljung_box", "condition_shrinkage", "fixture_referenced_bias_m"],
    }
    integration: dict[str, dict[str, bool]] = {}
    for relative, tokens in source_expectations.items():
        text = (package / relative).read_text(encoding="utf-8")
        integration[relative] = {token: token in text for token in tokens}
        for token, present in integration[relative].items():
            if not present:
                errors.append(f"{relative} missing expected behavior token {token}")
    checks["source_integration"] = integration

    legacy_quality_path = Path(
        "/home/xpired/ghost_trials/physical_validation_20260711T183400Z/controlled_R_direct_01/collection_quality.json"
    )
    if legacy_quality_path.is_file():
        legacy = json.loads(legacy_quality_path.read_text(encoding="utf-8"))
        checks["legacy_single_condition_baseline"] = {
            "available": True,
            "acceptable": legacy.get("acceptable"),
            "analysis_samples": legacy.get("analysis_samples"),
            "analysis_rate_hz": legacy.get("analysis_rate_hz"),
            "status": legacy.get("status"),
        }
        warnings.append(
            "Legacy controlled_R_direct_01 is one-condition baseline evidence only and does not complete G3."
        )
    else:
        checks["legacy_single_condition_baseline"] = {"available": False}
        warnings.append("Legacy controlled-R baseline not available on this machine.")

    report = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "project": "GHOST-X",
        "phase": "G3_MEASUREMENT_CHARACTERIZATION",
        "status": "READY_FOR_PHYSICAL_COLLECTION" if not errors else "NOT_READY",
        "passed": not errors,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "physical_exit_pending": {
            "accepted_trials": 18,
            "conditions": 9,
            "aggregate_analysis": "measurement_characterization.json",
            "covariance_model_selection": "required",
        },
        "claim_boundary": (
            "Readiness validation does not complete G3. Physical multi-condition capture and analysis remain required."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "status": report["status"],
        "planned_trials": planned_trials,
        "planned_conditions": planned_conditions,
        "errors": errors,
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
