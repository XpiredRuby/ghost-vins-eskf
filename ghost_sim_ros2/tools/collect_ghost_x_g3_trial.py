#!/usr/bin/env python3
"""Collect one predeclared GHOST-X G3 stationary measurement trial."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
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


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def run(argv: list[str], cwd: Path, log_path: Path) -> None:
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(argv, cwd=cwd, text=True, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}); see {log_path}: {' '.join(argv)}")


def update_order(order_path: Path, sequence: int, status: str, reason: str) -> None:
    with order_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
        fieldnames = list(rows[0].keys()) if rows else []
    matched = False
    for row in rows:
        if int(row["sequence"]) == sequence:
            row["status"] = status
            row["reason"] = reason
            matched = True
    if not matched:
        raise ValueError(f"sequence {sequence} not found in {order_path}")
    temporary = order_path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(order_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    args = parser.parse_args()

    campaign = args.campaign_dir.expanduser().resolve()
    repo = args.repo_root.expanduser().resolve()
    calibration = args.calibration.expanduser().resolve()
    order_path = campaign / "trial_order.csv"
    design = yaml.safe_load((campaign / "design_snapshot.yaml").read_text(encoding="utf-8"))

    with order_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    selected = next((row for row in rows if int(row["sequence"]) == args.sequence), None)
    if selected is None:
        raise SystemExit(f"sequence {args.sequence} not found")
    trial_dir = campaign / "trials" / selected["trial_id"]
    manifest_path = trial_dir / "trial_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    attempt_number = len(manifest.get("attempts", [])) + 1
    attempt_dir = trial_dir / f"attempt_{attempt_number:02d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)

    attempt = {
        "attempt": attempt_number,
        "started_at_utc": utc_now(),
        "status": "RUNNING",
        "operator_setup": {
            "range_m": float(selected["range_m"]),
            "lateral_m": float(selected["lateral_m"]),
            "yaw_deg": float(selected["yaw_deg"]),
        },
        "calibration_path": str(calibration),
        "calibration_sha256": sha256(calibration),
        "attempt_dir": str(attempt_dir),
    }
    manifest.setdefault("attempts", []).append(attempt)
    manifest["status"] = "RUNNING"
    atomic_json(manifest_path, manifest)
    update_order(order_path, args.sequence, "RUNNING", "")

    device = str(design["hardware"]["camera_device"])
    duration = float(design["collection"]["requested_valid_pose_duration_s"])
    tag_size = float(design["hardware"]["tag_size_m"])
    analysis_start, analysis_end = [float(v) for v in design["collection"]["analysis_window_s"]]
    try:
        run(
            ["bash", str(repo / "ghost_sim_ros2/tools/lock_uvc_camera_controls.sh"), device, str(attempt_dir)],
            repo,
            attempt_dir / "camera_lock_console.txt",
        )
        run(
            [
                "python3",
                str(repo / "ghost_sim_ros2/tools/direct_controlled_r_capture.py"),
                "--device",
                device,
                "--duration-s",
                str(duration),
                "--tag-size",
                str(tag_size),
                "--calib",
                str(calibration),
                "--out-dir",
                str(attempt_dir),
            ],
            repo,
            attempt_dir / "capture_console.txt",
        )
        run(
            [
                "python3",
                str(repo / "ghost_sim_ros2/tools/export_vision_pose_csv.py"),
                str(attempt_dir / "vision_pose.jsonl"),
                "--out",
                str(attempt_dir / "vision_pose_log.csv"),
            ],
            repo,
            attempt_dir / "export_console.txt",
        )
        run(
            [
                "python3",
                str(repo / "ghost_sim_ros2/analysis/controlled_r_collection_quality.py"),
                str(attempt_dir / "vision_pose.jsonl"),
                "--record-duration-s",
                str(duration),
                "--analysis-start-s",
                str(analysis_start),
                "--analysis-end-s",
                str(analysis_end),
                "--min-analysis-rate-hz",
                str(design["collection"]["minimum_analysis_rate_hz"]),
                "--max-analysis-gap-s",
                str(design["collection"]["maximum_analysis_gap_s"]),
                "--json-out",
                str(attempt_dir / "collection_quality.json"),
                "--md-out",
                str(attempt_dir / "collection_quality.md"),
            ],
            repo,
            attempt_dir / "quality_console.txt",
        )
        quality = json.loads((attempt_dir / "collection_quality.json").read_text(encoding="utf-8"))
        accepted = bool(quality.get("acceptable", False))
        status = "CAPTURED_ACCEPTED" if accepted else "CAPTURED_REJECTED"
        reason = "" if accepted else str(quality.get("status", "QUALITY_GATE_FAILED"))
    except Exception as exc:
        accepted = False
        status = "CAPTURE_FAILED"
        reason = str(exc)

    attempt.update(
        {
            "completed_at_utc": utc_now(),
            "status": status,
            "reason": reason,
            "artifacts": {
                name: {"path": str(attempt_dir / name), "sha256": sha256(attempt_dir / name)}
                for name in [
                    "vision_pose.jsonl",
                    "vision_pose_log.csv",
                    "direct_capture_summary.json",
                    "collection_quality.json",
                    "camera_lock_status.json",
                ]
                if (attempt_dir / name).is_file()
            },
        }
    )
    manifest["attempts"][-1] = attempt
    manifest["status"] = status
    manifest["accepted_attempt"] = attempt_number if accepted else manifest.get("accepted_attempt")
    atomic_json(manifest_path, manifest)
    update_order(order_path, args.sequence, status, reason)

    result = {
        "sequence": args.sequence,
        "trial_id": selected["trial_id"],
        "attempt": attempt_number,
        "status": status,
        "accepted": accepted,
        "reason": reason,
        "attempt_dir": str(attempt_dir),
    }
    print(json.dumps(result, indent=2))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
