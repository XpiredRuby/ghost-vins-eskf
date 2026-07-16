#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_x_controlled_truth import ESTIMATORS, SCENARIO_FAMILIES, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=PACKAGE_ROOT / "config" / "ghost_x_g4_controlled_truth.yaml")
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--out", type=Path, default=PACKAGE_ROOT / "docs" / "GHOST_X_G4_VALIDATION.json")
    args = parser.parse_args(argv)
    errors: list[str] = []
    config = load_config(args.config)
    if config.trial_count < 24:
        errors.append("fewer than 24 trials")
    if set(SCENARIO_FAMILIES) != {
        "stationary", "constant_velocity", "acceleration_deceleration", "coordinated_arc",
        "stop_and_go", "abrupt_maneuver", "complete_occlusion", "repeated_reentry"
    }:
        errors.append("scenario coverage mismatch")
    campaign_summary = None
    if args.campaign:
        manifest_path = args.campaign / "campaign_manifest.json"
        if not manifest_path.is_file():
            errors.append(f"missing campaign manifest: {manifest_path}")
        else:
            manifest = json.loads(manifest_path.read_text())
            accepted = [row for row in manifest.get("trials", []) if row.get("status") == "accepted"]
            for row in accepted:
                hashes = row.get("estimator_input_sha256", {})
                if set(hashes) != set(ESTIMATORS) or len(set(hashes.values())) != 1:
                    errors.append(f"{row.get('trial_id')}: estimator inputs are not identical")
            campaign_summary = {
                "planned_trials": manifest.get("planned_trials"),
                "accepted_trials": manifest.get("accepted_trials"),
                "invalid_trials": manifest.get("invalid_trials"),
                "identical_input_trials": len(accepted),
            }
    report = {
        "schema_version": 1,
        "phase": "G4_CONTROLLED_TRUTH",
        "passed": not errors,
        "errors": errors,
        "planned_trials": config.trial_count,
        "scenario_families": list(SCENARIO_FAMILIES),
        "estimators": list(ESTIMATORS),
        "campaign": campaign_summary,
        "status": "READY_OR_VALIDATED" if not errors else "FAILED",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
