#!/usr/bin/env python3
"""Freeze GHOST-X hardware calibration and validation partitions before collection."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def git_value(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def load_plan(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("hardware calibration plan must be a mapping")
    return value


def g3_rows(trial_order_csv: Path, plan: dict[str, Any]) -> list[dict[str, Any]]:
    section = plan["g3_measurement_characterization"]
    calibration = {int(value) for value in section["calibration_repeats"]}
    validation = {int(value) for value in section["frozen_validation_repeats"]}
    if calibration & validation:
        raise ValueError("G3 calibration and validation repeats overlap")
    rows: list[dict[str, Any]] = []
    with trial_order_csv.open(newline="", encoding="utf-8") as stream:
        for raw in csv.DictReader(stream):
            repeat_value = raw.get("repeat", raw.get("repetition"))
            if repeat_value is None:
                raise ValueError("G3 trial order requires repeat or repetition column")
            repeat = int(repeat_value)
            role = "calibration" if repeat in calibration else "frozen_validation" if repeat in validation else None
            if role is None:
                raise ValueError(f"G3 repeat {repeat} has no declared role")
            rows.append(
                {
                    "sequence": int(raw["sequence"]),
                    "trial_id": raw["trial_id"],
                    "range_m": float(raw["range_m"]),
                    "yaw_deg": float(raw["yaw_deg"]),
                    "repeat": repeat,
                    "role": role,
                }
            )
    expected = int(section["planned_trials"])
    if len(rows) != expected:
        raise ValueError(f"G3 trial order has {len(rows)} rows; expected {expected}")
    return rows


def g4_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    section = plan["g4_physical_controlled_truth"]
    calibration = {int(value) for value in section["calibration_repeats"]}
    validation = {int(value) for value in section["frozen_validation_repeats"]}
    if calibration & validation:
        raise ValueError("G4 calibration and validation repeats overlap")
    rows: list[dict[str, Any]] = []
    sequence = 0
    repeats = int(section["repeats_per_family"])
    for family in section["scenario_families"]:
        for repeat in range(1, repeats + 1):
            sequence += 1
            role = "calibration" if repeat in calibration else "frozen_validation" if repeat in validation else None
            if role is None:
                raise ValueError(f"G4 repeat {repeat} has no declared role")
            rows.append(
                {
                    "sequence": sequence,
                    "trial_id": f"g4p_{family}_rep{repeat:02d}",
                    "scenario_family": family,
                    "repeat": repeat,
                    "role": role,
                }
            )
    expected = int(section["planned_trials"])
    if len(rows) != expected:
        raise ValueError(f"G4 allocation has {len(rows)} rows; expected {expected}")
    return rows


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def write_markdown(manifest: dict[str, Any], path: Path) -> None:
    lines = [
        "# GHOST-X Hardware Calibration Partition",
        "",
        f"- Software baseline: `{manifest['software_baseline']['tag']}` / `{manifest['software_baseline']['commit']}`",
        f"- Partition hash: `{manifest['partition_sha256']}`",
        "- Parameter changes during formal collection: **prohibited**",
        "- Frozen validation data may not be used for tuning.",
        "",
        "## G3 allocation",
        "",
        "| Sequence | Trial | Range | Yaw | Repeat | Role |",
        "|---:|---|---:|---:|---:|---|",
    ]
    for row in manifest["g3_trials"]:
        lines.append(
            f"| {row['sequence']} | `{row['trial_id']}` | {row['range_m']:.2f} m | {row['yaw_deg']:+.0f}° | {row['repeat']} | `{row['role']}` |"
        )
    lines.extend(
        [
            "",
            "## G4 physical controlled-truth allocation",
            "",
            "| Sequence | Trial | Scenario | Repeat | Role |",
            "|---:|---|---|---:|---|",
        ]
    )
    for row in manifest["g4_trials"]:
        lines.append(
            f"| {row['sequence']} | `{row['trial_id']}` | `{row['scenario_family']}` | {row['repeat']} | `{row['role']}` |"
        )
    lines.extend(
        [
            "",
            "## Release rule",
            "",
            "Hardware-informed parameter changes are made only on `ghost-x-hardware-calibration`. The immutable `ghost-x-software-v1` tag remains the pre-hardware baseline. A final validated release is permitted only after the frozen validation partition is evaluated without additional tuning.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan",
        type=Path,
        default=PACKAGE_ROOT / "config" / "ghost_x_hardware_calibration_plan.yaml",
    )
    parser.add_argument(
        "--g3-trial-order",
        type=Path,
        default=Path("/home/xpired/ghost_trials/ghost_x_g3_measurement_v1/trial_order.csv"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/home/xpired/ghost_trials/ghost_x_hardware_calibration_v1"),
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()

    plan = load_plan(args.plan)
    baseline = plan["software_baseline"]
    tag_commit = git_value(args.repo_root, "rev-list", "-n", "1", baseline["tag"])
    if tag_commit != baseline["commit"]:
        raise SystemExit("software baseline tag no longer matches the frozen commit")

    current_branch = git_value(args.repo_root, "branch", "--show-current")
    if current_branch != plan["working_branch"]:
        raise SystemExit(f"run from {plan['working_branch']}; current branch is {current_branch}")

    g3 = g3_rows(args.g3_trial_order, plan)
    g4 = g4_rows(plan)
    partition_payload = {"g3_trials": g3, "g4_trials": g4}
    manifest = {
        "schema_version": 1,
        "project": "GHOST-X",
        "phase": "HARDWARE_CALIBRATION_PARTITION_FREEZE",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "software_baseline": baseline,
        "working_branch": current_branch,
        "plan_path": str(args.plan.resolve()),
        "plan_sha256": sha256_file(args.plan),
        "g3_trial_order_path": str(args.g3_trial_order.resolve()),
        "g3_trial_order_sha256": sha256_file(args.g3_trial_order),
        "partition_sha256": stable_hash(partition_payload),
        "policy": plan["policy"],
        "g3_trials": g3,
        "g4_trials": g4,
        "counts": {
            "g3_calibration": sum(row["role"] == "calibration" for row in g3),
            "g3_frozen_validation": sum(row["role"] == "frozen_validation" for row in g3),
            "g4_calibration": sum(row["role"] == "calibration" for row in g4),
            "g4_frozen_validation": sum(row["role"] == "frozen_validation" for row in g4),
        },
        "release_sequence": plan["release_sequence"],
        "claim_boundary": plan["claim_boundary"],
        "status": "FROZEN_BEFORE_PHYSICAL_COLLECTION",
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "hardware_partition_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(manifest, args.out_dir / "HARDWARE_PARTITION.md")
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "partition_sha256": manifest["partition_sha256"],
                "counts": manifest["counts"],
                "status": manifest["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
