#!/usr/bin/env python3
"""Initialize the predeclared GHOST-X G3 stationary measurement campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def slug_range(value: float) -> str:
    return f"r{int(round(value * 100)):03d}cm"


def slug_yaw(value: float) -> str:
    sign = "p" if value > 0 else "m" if value < 0 else "z"
    return f"yaw{sign}{int(round(abs(value))):02d}deg"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()

    design_path = args.design.expanduser().resolve()
    calibration_path = args.calibration.expanduser().resolve()
    repo = args.repo_root.expanduser().resolve()
    out = args.out.expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"Refusing to overwrite nonempty campaign directory: {out}")
    if not calibration_path.is_file():
        raise SystemExit(f"Calibration artifact not found: {calibration_path}")

    design = yaml.safe_load(design_path.read_text(encoding="utf-8"))
    ranges = [float(v) for v in design["factors"]["range_m"]]
    yaws = [float(v) for v in design["factors"]["yaw_deg"]]
    repeats = int(design["collection"]["repeats_per_condition"])
    seed = int(design["randomization_seed"])

    slots: list[dict[str, Any]] = []
    for range_m in ranges:
        for yaw_deg in yaws:
            condition_id = f"{slug_range(range_m)}_{slug_yaw(yaw_deg)}"
            for repetition in range(1, repeats + 1):
                trial_id = f"g3_{condition_id}_rep{repetition:02d}"
                slots.append(
                    {
                        "trial_id": trial_id,
                        "condition_id": condition_id,
                        "range_m": range_m,
                        "lateral_m": float(design["truth"]["expected_lateral_m"]),
                        "yaw_deg": yaw_deg,
                        "repetition": repetition,
                    }
                )

    random.Random(seed).shuffle(slots)
    out.mkdir(parents=True, exist_ok=True)
    trial_root = out / "trials"
    trial_root.mkdir()

    commit = __import__("subprocess").run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
    ).stdout.strip()

    campaign_manifest = {
        "schema_version": 1,
        "project": "GHOST-X",
        "phase": "G3_MEASUREMENT_CHARACTERIZATION",
        "campaign_id": out.name,
        "created_at_utc": utc_now(),
        "protocol_version": design["protocol_version"],
        "protocol_commit": commit,
        "design_path": str(design_path),
        "design_sha256": sha256(design_path),
        "calibration_path": str(calibration_path),
        "calibration_sha256": sha256(calibration_path),
        "randomization_seed": seed,
        "planned_trial_count": len(slots),
        "condition_count": len(ranges) * len(yaws),
        "analysis_window_s": design["collection"]["analysis_window_s"],
        "status": "INITIALIZED_NOT_COLLECTED",
    }
    (out / "campaign_manifest.json").write_text(
        json.dumps(campaign_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "design_snapshot.yaml").write_text(
        design_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    fieldnames = [
        "sequence",
        "trial_id",
        "condition_id",
        "range_m",
        "lateral_m",
        "yaw_deg",
        "repetition",
        "status",
        "reason",
    ]
    with (out / "trial_order.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for sequence, slot in enumerate(slots, start=1):
            row = {
                "sequence": sequence,
                **slot,
                "status": "PLANNED",
                "reason": "",
            }
            writer.writerow(row)
            trial_dir = trial_root / slot["trial_id"]
            trial_dir.mkdir()
            trial_manifest = {
                "schema_version": 1,
                "campaign_id": out.name,
                "sequence": sequence,
                **slot,
                "frame_id": design["truth"]["frame_id"],
                "truth_uncertainty": {
                    "range_m": design["truth"]["range_uncertainty_m"],
                    "lateral_m": design["truth"]["lateral_uncertainty_m"],
                    "yaw_deg": design["truth"]["yaw_uncertainty_deg"],
                },
                "capture": {
                    "requested_valid_pose_duration_s": design["collection"][
                        "requested_valid_pose_duration_s"
                    ],
                    "analysis_window_s": design["collection"]["analysis_window_s"],
                    "camera_device": design["hardware"]["camera_device"],
                    "tag_size_m": design["hardware"]["tag_size_m"],
                },
                "protocol_commit": commit,
                "design_sha256": campaign_manifest["design_sha256"],
                "calibration_sha256": campaign_manifest["calibration_sha256"],
                "status": "PLANNED",
                "attempts": [],
            }
            (trial_dir / "trial_manifest.json").write_text(
                json.dumps(trial_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    instructions = [
        "# GHOST-X G3 Collection Order",
        "",
        f"Campaign: `{out.name}`",
        f"Trials: `{len(slots)}` across `{len(ranges) * len(yaws)}` conditions",
        "",
        "For each sequence, place the AprilTag center at the declared range/lateral mark, set the declared yaw, keep pitch/roll nominally zero, and do not touch the setup during capture.",
        "",
        "| Seq | Trial | Range | Yaw | Repeat |",
        "|---:|---|---:|---:|---:|",
    ]
    for sequence, slot in enumerate(slots, start=1):
        instructions.append(
            f"| {sequence} | `{slot['trial_id']}` | {slot['range_m']:.2f} m | {slot['yaw_deg']:+.0f}° | {slot['repetition']} |"
        )
    (out / "COLLECTION_ORDER.md").write_text("\n".join(instructions) + "\n", encoding="utf-8")

    print(json.dumps({
        "campaign_dir": str(out),
        "planned_trials": len(slots),
        "conditions": len(ranges) * len(yaws),
        "protocol_commit": commit,
        "calibration_sha256": campaign_manifest["calibration_sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
