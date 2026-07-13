#!/usr/bin/env python3
"""Validate GHOST-X G2 contracts, schemas, source integration, and runtime evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghost_sim_ros2.data_contract import CONTRACT_VERSION, load_schema, validate_payload


SCHEMAS = [
    "formal_imm_futures.schema.json",
    "ghost_mh_futures.schema.json",
    "tracker_status.schema.json",
    "mission_validation.schema.json",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    package = args.package_root.resolve()
    schema_dir = package / "schemas"
    errors: list[str] = []
    checks: dict[str, Any] = {}

    contract_path = package / "config/ghost_x_data_contract.yaml"
    try:
        contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
        checks["data_contract_version"] = contract.get("contract_version")
        if contract.get("contract_version") != CONTRACT_VERSION:
            errors.append("data contract version mismatch")
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
            if key not in contract:
                errors.append(f"data contract missing section {key}")
    except Exception as exc:
        errors.append(f"data contract load failed: {exc}")

    schema_results: dict[str, bool] = {}
    for schema_name in SCHEMAS:
        try:
            load_schema(schema_name, schema_dir)
            schema_results[schema_name] = True
        except Exception as exc:
            schema_results[schema_name] = False
            errors.append(f"schema invalid {schema_name}: {exc}")
    checks["schemas"] = schema_results

    mission_path = package / "docs/GHOST_DRONE_MISSION_VALIDATION.json"
    try:
        mission = read_json(mission_path)
        validate_payload(mission, "mission_validation.schema.json", schema_dir)
        checks["mission_validation"] = {
            "passed": mission.get("passed"),
            "contract_version": mission.get("contract_version"),
            "frame_id": mission.get("frame_id"),
            "validity": mission.get("validity"),
            "provenance": mission.get("provenance"),
        }
        if not mission.get("passed"):
            errors.append("committed mission validation did not pass")
    except Exception as exc:
        errors.append(f"mission validation failed: {exc}")

    runtime_path = package / "docs/GHOST_X_G2_RUNTIME_VALIDATION.json"
    try:
        runtime = read_json(runtime_path)
        checks["runtime_contract_probe"] = {
            "passed": runtime.get("passed"),
            "validated_topics": runtime.get("validated_topics", []),
            "missing_topics": runtime.get("missing_topics", []),
            "errors": runtime.get("errors", []),
        }
        if not runtime.get("passed"):
            errors.append("runtime contract probe did not pass")
        if len(runtime.get("validated_topics", [])) != 5:
            errors.append("runtime contract probe did not validate all five required topics")
    except Exception as exc:
        errors.append(f"runtime contract report failed: {exc}")

    source_requirements = {
        "ghost_sim_ros2/formal_imm_tracker.py": [
            "status_json_topic",
            "build_run_identity",
            "contract_envelope",
            '"tracker": "formal_imm"',
        ],
        "ghost_sim_ros2/mh_tracker.py": [
            "status_json_topic",
            "build_run_identity",
            "contract_envelope",
            '"tracker": "ghost_mh"',
        ],
        "ghost_sim_ros2/mission_evaluator.py": [
            "build_run_identity",
            "contract_envelope",
            '"frame_id"',
        ],
    }
    source_checks: dict[str, dict[str, bool]] = {}
    for relative, tokens in source_requirements.items():
        source = (package / relative).read_text(encoding="utf-8")
        source_checks[relative] = {token: token in source for token in tokens}
        for token, present in source_checks[relative].items():
            if not present:
                errors.append(f"{relative} missing integration token {token}")
    checks["source_integration"] = source_checks

    report = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "project": "GHOST-X",
        "phase": "G2_FRAMES_TIMING_DATA_CONTRACTS",
        "passed": not errors,
        "checks": checks,
        "errors": errors,
        "historical_bag_policy": (
            "Pre-G2 bags remain immutable baseline-v0 evidence and are identified by the G0 manifest; "
            "their raw messages are never retroactively modified."
        ),
        "formal_hardware_gate": (
            "Future formal hardware bags must contain non-UNSPECIFIED calibration_id and configuration_id "
            "in recorded tracker futures/status JSON payloads."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "passed": report["passed"],
        "schema_count": len(SCHEMAS),
        "runtime_topics": len(checks.get("runtime_contract_probe", {}).get("validated_topics", [])),
        "errors": errors,
    }, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
