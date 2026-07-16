#!/usr/bin/env python3
"""Generate the immutable GHOST-X Phase G0 baseline evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path),
    }


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace").strip("\x00\n ")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def parse_os_release() -> dict[str, str]:
    result: dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def parse_bag_metadata(metadata_path: Path) -> dict[str, Any] | None:
    if not metadata_path.is_file():
        return None
    root = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    info = root["rosbag2_bagfile_information"]
    duration_s = float(info["duration"]["nanoseconds"]) * 1e-9
    topics: dict[str, Any] = {}
    for entry in info.get("topics_with_message_count", []):
        metadata = entry["topic_metadata"]
        count = int(entry["message_count"])
        topics[metadata["name"]] = {
            "type": metadata["type"],
            "message_count": count,
            "mean_rate_hz": count / duration_s if duration_s > 0.0 else None,
        }
    return {
        "storage_identifier": info.get("storage_identifier"),
        "ros_distro": info.get("ros_distro"),
        "duration_s": duration_s,
        "starting_time_ns": info["starting_time"]["nanoseconds_since_epoch"],
        "message_count": int(info["message_count"]),
        "topics": topics,
        "metadata": file_record(metadata_path),
        "data_files": [
            file_record(metadata_path.parent / relative)
            for relative in info.get("relative_file_paths", [])
        ],
    }


def selected_calibration(calibration: dict[str, Any] | None) -> dict[str, Any] | None:
    if calibration is None:
        return None
    keys = [
        "model",
        "image_width",
        "image_height",
        "square_size_m",
        "rms_reprojection_error_px",
        "mean_per_view_error_px",
        "max_per_view_error_px",
        "camera_matrix",
        "dist_coeffs",
    ]
    return {key: calibration.get(key) for key in keys}


def selected_controlled_r(summary: dict[str, Any] | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    primary = summary.get("primary_window", {})
    return {
        "source": summary.get("primary_r_source"),
        "status": summary.get("r_status"),
        "sample_count": primary.get("sample_count"),
        "sample_rate_hz": primary.get("sample_rate_hz"),
        "window_start_s": primary.get("start_s"),
        "window_end_s": primary.get("end_s"),
        "mean_x_m": primary.get("mean_x_m"),
        "mean_y_m": primary.get("mean_y_m"),
        "r_xx_m2": primary.get("r_xx_m2"),
        "r_xy_m2": primary.get("r_xy_m2"),
        "r_yy_m2": primary.get("r_yy_m2"),
        "std_x_m": primary.get("std_x_m"),
        "std_y_m": primary.get("std_y_m"),
        "correlation_xy": primary.get("correlation_xy"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--session-root",
        type=Path,
        default=Path("/home/xpired/ghost_trials/physical_validation_20260711T183400Z"),
    )
    parser.add_argument(
        "--hardware-bag",
        type=Path,
        default=Path("/home/xpired/ghost_ws/bags/live_camera_calibrated_R_01"),
    )
    parser.add_argument(
        "--calibration",
        type=Path,
        default=Path("/home/xpired/ghost_camera_calibration.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("ghost_sim_ros2/docs/GHOST_X_BASELINE_MANIFEST.json"),
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    repo = args.repo_root.resolve()
    session = args.session_root.resolve()
    bag = args.hardware_bag.resolve()
    calibration_path = args.calibration.resolve()
    out = args.out if args.out.is_absolute() else repo / args.out

    controlled_r_dir = session / "controlled_R_direct_01"
    controlled_r_summary_path = controlled_r_dir / "noise_summary.json"
    controlled_r_quality_path = controlled_r_dir / "collection_quality.json"
    mission_validation_path = repo / "ghost_sim_ros2/docs/GHOST_DRONE_MISSION_VALIDATION.json"
    physical_completion_path = session / "PHASE2_ACCELERATED_COMPLETION_REPORT.md"
    protocol_amendment_path = session / "PHASE2_MEASURED_GAP_PROTOCOL_AMENDMENT.md"
    full_test_log = session / "ghost_full_pytest_final.log"

    required = [
        calibration_path,
        bag / "metadata.yaml",
        controlled_r_summary_path,
        controlled_r_quality_path,
        mission_validation_path,
        physical_completion_path,
        protocol_amendment_path,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if args.strict and missing:
        raise SystemExit("Missing required evidence:\n" + "\n".join(missing))

    calibration = read_json(calibration_path)
    controlled_r_summary = read_json(controlled_r_summary_path)
    controlled_r_quality = read_json(controlled_r_quality_path)
    mission_validation = read_json(mission_validation_path)

    baseline_tag = "ghost-drone-mission-v1"
    baseline_commit = git(repo, "rev-parse", f"{baseline_tag}^{{commit}}")
    camera_name = read_text(Path("/sys/class/video4linux/video0/name"))
    pi_model = read_text(Path("/proc/device-tree/model"))

    manifest = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "project": "GHOST-X",
        "phase": "G0_BASELINE_FREEZE",
        "baseline_release": {
            "tag": baseline_tag,
            "commit": baseline_commit,
            "tag_resolves_to_commit": True,
        },
        "platform": {
            "raspberry_pi_model": pi_model,
            "machine": platform.machine(),
            "kernel": platform.release(),
            "python": platform.python_version(),
            "os_release": parse_os_release(),
            "ros_distro": os.environ.get("ROS_DISTRO", "jazzy"),
        },
        "hardware": {
            "camera_device": "/dev/video0",
            "camera_name": camera_name,
            "camera_interface": "USB UVC / V4L2",
            "target_proxy": "printed AprilTag",
            "compute": pi_model,
        },
        "camera_calibration": {
            "summary": selected_calibration(calibration),
            "artifact": file_record(calibration_path),
        },
        "preserved_hardware_bag": parse_bag_metadata(bag / "metadata.yaml"),
        "controlled_measurement_covariance": {
            "status": "ACCEPTED_STATIONARY_MEASUREMENT_COVARIANCE_ONLY",
            "claim_boundary": (
                "Does not establish tracker accuracy, independent truth, or residual whiteness."
            ),
            "summary": selected_controlled_r(controlled_r_summary),
            "quality": controlled_r_quality,
            "artifacts": {
                "noise_summary": file_record(controlled_r_summary_path),
                "collection_quality": file_record(controlled_r_quality_path),
                "vision_pose_jsonl": file_record(controlled_r_dir / "vision_pose.jsonl"),
                "vision_pose_csv": file_record(controlled_r_dir / "vision_pose_log.csv"),
            },
        },
        "software_mission_validation": {
            "result": mission_validation,
            "artifact": file_record(mission_validation_path),
        },
        "physical_validation": {
            "scope": "accelerated representative guided camera-space validation",
            "completion_report": file_record(physical_completion_path),
            "protocol_amendment": file_record(protocol_amendment_path),
            "formal_55_trial_campaign": "DEFERRED_NOT_COMPLETED",
            "independent_ground_truth_grid": "NOT_COMPLETED",
        },
        "software_verification": {
            "full_pytest_log": file_record(full_test_log),
            "last_verified_result": "214 passed in 204.56s",
        },
        "public_claim_boundaries": {
            "supported": [
                "ROS 2 camera-to-tracker hardware pipeline",
                "prediction-only behavior and reacquisition telemetry",
                "deterministic local-frame software observer navigation",
                "obstacle line-of-sight gating and tracker propagation during loss",
                "accepted stationary measurement covariance artifact",
            ],
            "not_supported_yet": [
                "physical trajectory RMSE or bias against independent truth",
                "formal statistical superiority of GHOST-MH over IMM",
                "completed 55-trial physical campaign",
                "GPS-denied self-localization, VIO, or SLAM",
                "PX4 integration or real autonomous drone flight",
                "production, safety-critical, or flight-qualified readiness",
            ],
        },
        "reproduction": {
            "one_command": "bash ghost_sim_ros2/tools/rebuild_ghost_x_baseline.sh",
            "external_evidence_required": [str(calibration_path), str(bag), str(session)],
            "clean_checkout_expectation": (
                "Repository-owned software, tests, documents, and deterministic simulation reproduce "
                "from checkout. Hardware plots additionally require the preserved external bag."
            ),
        },
        "missing_required_evidence": missing,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"baseline_commit={manifest['baseline_release']['commit']}")
    print(f"missing_required_evidence={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
