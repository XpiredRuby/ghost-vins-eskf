#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterator

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DOCS = PACKAGE_ROOT / "docs"
DATA_DIR = DOCS / "data"
DEFAULT_RAW_TRIAL = Path(
    "/home/xpired/ghost_trials/physical_validation_20260711T183400Z/"
    "browser_guided_runs/20260716T014453Z/recorder_trials/20260715_194502"
)

SHOWCASE_OUT = DATA_DIR / "GHOST_INTERACTIVE_SHOWCASE_DATA_V2.json"
REPLAY_OUT = DATA_DIR / "GHOST_HARDWARE_REPLAY_20260716.json"
CHECKLIST_OUT = DOCS / "GHOST_INTERACTIVE_EVIDENCE_CHECKLIST.md"


def load_json(name: str) -> dict[str, Any]:
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jsonl_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="strict") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path.name}:{line_number}: invalid JSONL: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path.name}:{line_number}: expected object")
            yield value


def check_values(report: dict[str, Any]) -> dict[str, Any]:
    return {
        str(row["id"]): row.get("actual")
        for row in report["summary"]["checks"]
    }


def find_runtime_row(
    report: dict[str, Any],
    estimator: str,
    implementation: str,
    stress_workers: int,
) -> dict[str, Any]:
    matches = [
        row
        for row in report["estimator_deadline"]["rows"]
        if row["estimator"] == estimator
        and row["implementation"] == implementation
        and int(row["stress_workers"]) == stress_workers
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one runtime row for {estimator}/{implementation}/stress={stress_workers}, "
            f"found {len(matches)}"
        )
    return matches[0]


def parse_live_rates() -> dict[str, float]:
    text = (DOCS / "GHOST_PROJECT_REPORT.md").read_text(encoding="utf-8")
    patterns = {
        "camera_pose_hz": r"\| Camera pose rate \| `([0-9.]+) Hz` \|",
        "imm_output_hz": r"\| IMM odometry rate \| `([0-9.]+) Hz` \|",
        "mh_output_hz": r"\| MH odometry rate \| `([0-9.]+) Hz` \|",
    }
    output: dict[str, float] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if not match:
            raise ValueError(f"Could not find {key} in GHOST_PROJECT_REPORT.md")
        output[key] = float(match.group(1))
    return output


def load_traceability_count() -> int:
    with (DOCS / "GHOST_X_FINAL_TRACEABILITY.csv").open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    return len(rows)


def source_link(path: str, label: str | None = None) -> dict[str, str]:
    return {"path": path, "label": label or path}


def high_level_status(raw: str) -> str:
    prefix = raw.split(" cal=", 1)[0].strip()
    mappings = [
        ("VISIBLE - MEASUREMENT LOCK", "VISIBLE_MEASUREMENT_LOCK"),
        ("HIDDEN - STATIONARY HOLD", "HIDDEN_STATIONARY_HOLD"),
        ("DEGRADED - NO BOUNDED HYPOTHESES", "DEGRADED_NO_BOUNDED_HYPOTHESES"),
        ("WAITING_FOR_TARGET", "WAITING_FOR_TARGET"),
    ]
    for needle, value in mappings:
        if prefix.startswith(needle):
            return value
    return prefix.upper().replace(" ", "_").replace("-", "_")


def source_meta(path: Path, logical_name: str) -> dict[str, Any]:
    return {
        "logical_name": logical_name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def in_window(row: dict[str, Any], start: float, end: float) -> bool:
    t = row.get("wall_time_s")
    return isinstance(t, (int, float)) and start <= float(t) <= end


def relative_time(row: dict[str, Any], start: float) -> float:
    return float(row["wall_time_s"]) - start


def extract_estimates(
    path: Path,
    start: float,
    end: float,
    min_spacing_s: float = 0.10,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    last_time: float | None = None
    for row in jsonl_records(path):
        if not in_window(row, start, end):
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        estimate = payload.get("estimate")
        if not isinstance(estimate, dict):
            continue
        t_rel = relative_time(row, start)
        if last_time is not None and t_rel - last_time < min_spacing_s:
            continue
        validity = payload.get("validity") or {}
        selected.append(
            {
                "t_s": t_rel,
                "source_wall_time_s": float(row["wall_time_s"]),
                "visible": bool(payload.get("visible", False)),
                "validity_state": validity.get("state"),
                "x_m": estimate.get("x_m"),
                "y_m": estimate.get("y_m"),
                "vx_mps": estimate.get("vx_mps"),
                "vy_mps": estimate.get("vy_mps"),
                "cov_xx_m2": estimate.get("cov_xx"),
                "cov_xy_m2": estimate.get("cov_xy"),
                "cov_yy_m2": estimate.get("cov_yy"),
                "hypothesis_count": len(payload.get("hypotheses") or []),
            }
        )
        last_time = t_rel
    return selected


def build_replay(raw_trial_dir: Path) -> dict[str, Any]:
    sequence = load_json(
        "guided_hardware_evidence/20260716_guided_sequence_summary.json"
    )
    cue_start = float(sequence["sequence_start_wall_time_s"])
    cue_end = float(sequence["sequence_end_wall_time_s"])
    start = cue_start - 1.0
    end = cue_end + 1.0
    source_paths = {
        "vision_pose": raw_trial_dir / "vision_pose.jsonl",
        "events": raw_trial_dir / "events.jsonl",
        "status": raw_trial_dir / "status.jsonl",
        "imm_futures": raw_trial_dir / "imm_futures.jsonl",
        "mh_futures": raw_trial_dir / "mh_futures.jsonl",
    }
    missing = [str(path) for path in source_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing raw replay sources: " + ", ".join(missing))

    measurements: list[dict[str, Any]] = []
    for row in jsonl_records(source_paths["vision_pose"]):
        if not in_window(row, start, end):
            continue
        pos = row.get("position") or {}
        measurements.append(
            {
                "t_s": relative_time(row, start),
                "source_wall_time_s": float(row["wall_time_s"]),
                "x_m": pos.get("x_m"),
                "y_m": pos.get("y_m"),
                "z_m": pos.get("z_m"),
            }
        )

    events: list[dict[str, Any]] = []
    for row in jsonl_records(source_paths["events"]):
        if not in_window(row, start, end):
            continue
        events.append(
            {
                "t_s": relative_time(row, start),
                "source_wall_time_s": float(row["wall_time_s"]),
                "event": row.get("event"),
                "message": row.get("message"),
                "details": row.get("details") or {},
            }
        )

    statuses: list[dict[str, Any]] = []
    previous_state: str | None = None
    for row in jsonl_records(source_paths["status"]):
        if not in_window(row, start, end):
            continue
        raw = str(row.get("status", ""))
        state = high_level_status(raw)
        if state == previous_state:
            continue
        statuses.append(
            {
                "t_s": relative_time(row, start),
                "source_wall_time_s": float(row["wall_time_s"]),
                "state": state,
                "raw_status": raw,
            }
        )
        previous_state = state

    replay = {
        "schema_version": 1,
        "title": "Guided hardware browser-sequence replay",
        "data_class": "MEASURED_HARDWARE",
        "trial_id": "20260715_194502",
        "sequence_scope": "BROWSER_CUE_WINDOW_ONLY",
        "sequence_start_wall_time_s": cue_start,
        "sequence_end_wall_time_s": cue_end,
        "replay_start_wall_time_s": start,
        "replay_end_wall_time_s": end,
        "cue_window_start_t_s": cue_start - start,
        "cue_window_end_t_s": cue_end - start,

        "duration_s": end - start,
        "window_note": "The replay includes the reviewed analyzer padding of 1.0 s before and after the browser cue window.",
        "measurement_note": (
            "All measurement points are recorded vision_pose samples. No smoothing, "
            "interpolation, or synthetic filler frames are used."
        ),
        "tracker_note": (
            "IMM and GHOST-MH points are deterministic downselections of actual recorded "
            "tracker records using a minimum 0.10 s spacing. They are not interpolated."
        ),
        "video_available": False,
        "video_note": "No approved camera frames or video were retained for this trial.",
        "provenance": {
            key: source_meta(path, f"recorder_trials/20260715_194502/{path.name}")
            for key, path in source_paths.items()
        },
        "source_summary": source_link(
            "guided_hardware_evidence/20260716_guided_sequence_summary.json"
        ),
        "event_counts": sequence["sequence_event_counts"],
        "measurements": measurements,
        "events": events,
        "status_changes": statuses,
        "imm_estimates": extract_estimates(source_paths["imm_futures"], start, end),
        "mh_estimates": extract_estimates(source_paths["mh_futures"], start, end),
    }
    if len(measurements) != int(sequence["vision_sample_count"]):
        raise ValueError(
            f"Replay measurement count {len(measurements)} does not match "
            f"summary count {sequence['vision_sample_count']}"
        )
    return replay


def build_showcase() -> dict[str, Any]:
    hardware = load_json("GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json")
    mission = load_json("GHOST_DRONE_MISSION_VALIDATION.json")
    g4 = load_json("GHOST_X_G4_VALIDATION.json")
    g7 = load_json("GHOST_X_G7_TRADE_STUDY.json")
    g8 = load_json("GHOST_X_G8_FAULT_REPORT.json")
    g9 = load_json("GHOST_X_G9_RUNTIME_REPORT.json")
    g10 = load_json("GHOST_X_G10_CI_REPORT.json")
    baseline = load_json("GHOST_X_BASELINE_MANIFEST.json")
    status = load_json("GHOST_X_SOFTWARE_STATUS.json")
    public_summary = load_json("GHOST_PUBLIC_RESULTS_SUMMARY.json")
    checks = check_values(g10)
    rates = parse_live_rates()

    runtime_basis = {
        "implementation": "python_reference",
        "stress_workers": 0,
        "platform": "Raspberry Pi 4 Model B Rev 1.5",
    }
    runtime_rows = {
        "cv_kalman": find_runtime_row(g9, "cv_kalman", "python_reference", 0),
        "formal_imm": find_runtime_row(g9, "formal_imm", "python_reference", 0),
        "ghost_mh": find_runtime_row(g9, "ghost_mh", "python_reference", 0),
    }

    estimator_specs = [
        (
            "cv_kalman",
            "CV Kalman",
            checks["G4_CV_KALMAN_POSITION_RMSE"],
            checks["G4_CV_KALMAN_HIDDEN_RMSE"],
            (
                "Under the 24-trial deterministic software campaign, CV had higher overall "
                "and hidden-period RMSE than formal IMM but lower RMSE than GHOST-MH, while "
                "recording the lowest Python-reference runtime in the matched no-stress rows."
            ),
        ),
        (
            "formal_imm",
            "Formal IMM",
            checks["G4_FORMAL_IMM_POSITION_RMSE"],
            checks["G4_FORMAL_IMM_HIDDEN_RMSE"],
            (
                "Under the same 24-trial deterministic software campaign, formal IMM had "
                "the lowest overall and hidden-period RMSE, with the highest Python-reference "
                "runtime cost of the three matched rows."
            ),
        ),
        (
            "ghost_mh",
            "GHOST-MH",
            checks["G4_GHOST_MH_POSITION_RMSE"],
            checks["G4_GHOST_MH_HIDDEN_RMSE"],
            (
                "Under the 24-trial deterministic software campaign, GHOST-MH had the highest "
                "overall and hidden-period RMSE. In the one measured stationary short-dropout "
                "proxy it beat constant velocity but not the last-seen hold."
            ),
        ),
    ]
    estimators = []
    for key, name, overall, hidden, observation in estimator_specs:
        row = runtime_rows[key]
        estimators.append(
            {
                "id": key,
                "name": name,
                "overall_rmse_m": overall,
                "hidden_rmse_m": hidden,
                "p99_runtime_ms": float(row["p99_execution_us"]) / 1000.0,
                "max_runtime_ms": float(row["max_execution_us"]) / 1000.0,
                "reacquisition_time_s": None,
                "reacquisition_time_unavailable_reason": (
                    "No symmetric retained reacquisition-time metric exists for all three "
                    "estimators on the same campaign."
                ),
                "reset_count": None,
                "reset_count_unavailable_reason": (
                    "No symmetric retained reset-count metric exists for all three estimators "
                    "on the same final comparison campaign."
                ),
                "observation": observation,
            }
        )

    dropout = hardware["accepted_results"]["short_dropout_reacquisition"]
    lateral = hardware["accepted_results"]["lateral_relative_response"]
    farther = hardware["accepted_results"]["farther_relative_response"]
    closer = hardware["accepted_results"]["closer_relative_response"]
    rt2 = g9["requirements"]["RT-002"]
    traceability_count = load_traceability_count()
    if traceability_count != 34:
        raise ValueError(f"Expected 34 traceability rows, found {traceability_count}")

    max_temperature = max(
        float(scenario["resource_summary"]["temperature_c"]["max"])
        for scenario in g9["qos_scenarios"]
        if scenario.get("resource_summary", {}).get("temperature_c", {}).get("max") is not None
    )
    max_estimator_benchmark_rss_mb = max(
        float(row["resource_summary"]["process_rss_mb"]["max"])
        for row in g9["estimator_benchmarks"]
    )

    hero = [
        {
            "id": "hardware_dropout",
            "value": dropout["measured_occlusion_duration_s"],
            "display": f"{float(dropout['measured_occlusion_duration_s']):.4f} s",
            "label": "Measured tag occlusion; reacquired without reset",
            "badge": "MEASURED_HARDWARE",
            "sample_basis": "N=1 intended hardware dropout",
            "source": "GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json",
            "status": "PASS_UNDER_TESTED_CONDITIONS",
        },
        {
            "id": "controlled_trials",
            "value": g4["campaign"]["accepted_trials"],
            "display": "24 / 24",
            "label": "Accepted deterministic controlled-truth trials",
            "badge": "SYNTHETIC_SOFTWARE",
            "sample_basis": "N=24 trials across 8 scenario families",
            "source": "GHOST_X_G4_VALIDATION.json",
            "status": "PASS",
        },
        {
            "id": "fault_cases",
            "value": g8["passed_faults"],
            "display": "12 / 12",
            "label": "Software-injected fault cases passed",
            "badge": "SYNTHETIC_SOFTWARE",
            "sample_basis": "N=12 distinct fault cases",
            "source": "GHOST_X_G8_FAULT_REPORT.json",
            "status": "PASS",
        },
        {
            "id": "rt002",
            "value": rt2["publication_rate_hz"],
            "display": f"{float(rt2['publication_rate_hz']):.4f} Hz",
            "label": "Observed publication rate vs 29.7 Hz minimum",
            "badge": "MEASURED_HARDWARE",
            "sample_basis": f"N={rt2['interarrival_ms']['count']} interarrival intervals",
            "source": "GHOST_X_G9_RUNTIME_REPORT.json",
            "status": "NOT_MET",
            "threshold": rt2["limits"]["minimum_rate_hz"],
        },
    ]

    occlusion_scenarios = {
        "short_hide": {
            "title": "Short stationary-target tag hide",
            "badge": "MEASURED_HARDWARE",
            "sample_basis": "N=1 intended hardware dropout",
            "source": "GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json",
            "metrics": {
                "occlusion_duration_s": dropout["measured_occlusion_duration_s"],
                "reacquisition_time_s": dropout["measured_occlusion_duration_s"],
                "first_frame_errors_m": {
                    "ghost_mh_top1": dropout["ghost_top1_error_m"],
                    "constant_velocity": dropout["constant_velocity_error_m"],
                    "last_seen_hold": dropout["last_seen_hold_error_m"],
                },
                "hidden_drift_m": None,
                "hidden_drift_unavailable_reason": (
                    "A reviewed hidden-period drift metric was not retained for this event."
                ),
                "reset_during_occlusion": dropout["reset_during_occlusion"],
            },
            "conclusion": (
                "This is the single stationary-target hardware dropout event; it is not counted "
                "again under a second scenario label. GHOST-MH beat constant velocity in this "
                "event but did not beat the last-seen hold."
            ),
        },
        "long_hide": {
            "title": "Obstacle occlusions in drone-follow simulation",
            "badge": "SYNTHETIC_SOFTWARE",
            "sample_basis": "N=2 simulated obstacle occlusions in one mission execution",
            "source": "GHOST_DRONE_MISSION_VALIDATION.json",
            "metrics": {
                "occlusion_durations_s": mission["occlusion_durations_s"],
                "reacquisition_count": mission["reacquisition_count"],
                "first_frame_errors_m": None,
                "first_frame_errors_unavailable_reason": (
                    "First-frame post-reacquisition errors were not retained in the mission summary."
                ),
                "hidden_drift_m": None,
                "hidden_drift_unavailable_reason": (
                    "A common hidden-period drift metric was not retained in the mission summary."
                ),
            },
            "conclusion": (
                "The deterministic local-frame software mission reacquired after two obstacle "
                "occlusions. It does not represent physical flight or GPS-denied self-localization."
            ),
        },
    }

    response_scenarios = {
        "lateral_motion": {
            "title": "Guided lateral response",
            "badge": "MEASURED_HARDWARE",
            "sample_basis": "One guided browser sequence; correlated video samples",
            "source": "GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json",
            "metrics": {
                "baseline_y_m": lateral["baseline_y_m"],
                "left_hold_y_m": lateral["left_hold_y_m"],
                "right_hold_y_m": lateral["right_hold_y_m"],
            },
            "conclusion": (
                "Measured left and right holds moved in opposite camera-frame directions. "
                "The result supports directional relative response only; it is not an occlusion test."
            ),
        },
        "range_change": {
            "title": "Guided closer and farther response",
            "badge": "MEASURED_HARDWARE",
            "sample_basis": (
                "One focused closer retest with 32 correlated pose samples and one focused "
                "farther run with 89 correlated pose samples"
            ),
            "source": "GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json",
            "metrics": {
                "closer_delta_x_m": closer["delta_x_m"],
                "closer_valid_samples": closer["valid_samples"],
                "closer_reset_count": closer["reset_count"],
                "farther_delta_x_m": farther["delta_x_m"],
                "farther_valid_samples": farther["valid_samples"],
            },
            "conclusion": (
                "The focused retests produced the expected camera-frame range direction. "
                "These are guided relative-response results, not occlusion or absolute-accuracy trials."
            ),
        },
    }

    system_stages = [
        {
            "id": "tag",
            "number": "01",
            "name": "AprilTag target",
            "summary": "Printed tag36h11, ID 0, nominal 0.1 m target geometry.",
            "inputs": ["Target object motion", "Lighting and line of sight"],
            "outputs": ["High-contrast fiducial corners", "Known tag family, ID, and nominal size"],
            "failure_modes": ["Occlusion", "Blur", "Extreme viewing angle", "Print deformation"],
            "badge": "MEASURED_HARDWARE",
            "evidence": ["GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json"],
        },
        {
            "id": "camera",
            "number": "02",
            "name": "USB camera",
            "summary": "eMeet C960 through Linux V4L2/UVC on Raspberry Pi 4B.",
            "inputs": ["Optical image of tagged target"],
            "outputs": ["Timestamped image frames", "Software/arrival timing"],
            "failure_modes": ["Frame loss", "Latency", "USB disconnect", "Lighting degradation"],
            "badge": "MEASURED_HARDWARE",
            "evidence": ["GHOST_X_BASELINE_MANIFEST.json", "GHOST_PROJECT_REPORT.md"],
        },
        {
            "id": "pose",
            "number": "03",
            "name": "Pose estimation",
            "summary": "Calibrated AprilTag detection and solvePnP camera-frame pose.",
            "inputs": ["Image frame", "Camera intrinsics", "Nominal tag size"],
            "outputs": ["Position measurement", "Timestamp", "Covariance metadata"],
            "failure_modes": ["No detection", "Invalid geometry", "Calibration error", "Outlier pose"],
            "badge": "MEASURED_HARDWARE",
            "evidence": ["GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json"],
        },
        {
            "id": "tracker",
            "number": "04",
            "name": "Tracking layer",
            "summary": "CV Kalman, formal IMM, and GHOST-MH consume a common measurement contract.",
            "inputs": ["Pose measurements", "Timestamps", "Covariance", "Validity"],
            "outputs": ["Estimated state", "Prediction-only state", "Status", "Future hypotheses"],
            "failure_modes": ["Long dropout", "Model mismatch", "Stale/out-of-sequence data", "Reset"],
            "badge": "MIXED_EVIDENCE",
            "evidence": ["GHOST_X_G4_VALIDATION.json", "GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json"],
        },
        {
            "id": "follow",
            "number": "05",
            "name": "Drone-follow interface",
            "summary": "Software output suitable for downstream follow/navigation logic.",
            "inputs": ["Estimated relative target state", "Visibility/validity", "Prediction status"],
            "outputs": ["Navigation/follow command inputs", "Reposition request in simulation"],
            "failure_modes": ["No bounded target estimate", "Unknown vehicle pose", "Unsafe command"],
            "badge": "SYNTHETIC_SOFTWARE",
            "evidence": ["GHOST_DRONE_MISSION_VALIDATION.json"],
        },
    ]

    fault_rows = [
        {
            "fault": row["fault"],
            "passed": row["passed"],
            "detected": row["detected"],
            "isolated": row["isolated"],
            "recovery_ok": row["recovery_ok"],
            "detected_at_s": row["detected_at_s"],
            "recovery_time_s": row["recovery_time_s"],
            "position_error_rmse_m": row["position_error_rmse_m"],
            "expected_status": row["expected_status"],
        }
        for row in g8["trials"]
    ]

    recovery_groups: dict[float, list[str]] = {}
    rmse_groups: dict[tuple[float, float, float], list[str]] = {}
    for row in g8["trials"]:
        recovery_groups.setdefault(float(row["recovery_time_s"]), []).append(row["fault"])
        rmse = row["position_error_rmse_m"]
        rmse_key = (float(rmse["cv_kalman"]), float(rmse["formal_imm"]), float(rmse["ghost_mh"]))
        rmse_groups.setdefault(rmse_key, []).append(row["fault"])

    fault_recovery_groups = [
        {"recovery_time_s": value, "count": len(faults), "faults": faults}
        for value, faults in sorted(recovery_groups.items())
    ]
    fault_rmse_groups = [
        {
            "position_error_rmse_m": {
                "cv_kalman": values[0],
                "formal_imm": values[1],
                "ghost_mh": values[2],
            },
            "count": len(faults),
            "faults": faults,
        }
        for values, faults in sorted(rmse_groups.items())
    ]

    deadline_rows = g9["estimator_deadline"]["rows"]
    deadline_rows_met = sum(1 for row in deadline_rows if row["max_below_deadline"])
    deadline_rows_not_met = [row for row in deadline_rows if not row["max_below_deadline"]]
    if len(deadline_rows_not_met) != 1:
        raise ValueError(f"Expected one estimator deadline miss, found {len(deadline_rows_not_met)}")

    limitations = [
        "No physical closed-loop drone flight was performed.",
        "The follower-drone mission result is deterministic local-frame software simulation with a known observer pose and map.",
        "No independent metrology-grade ground truth was available for the guided hardware movements.",
        "The original floor-grid capture was rejected because the camera/tag geometry was not moved between nominal grid positions.",
        "The intended measured hardware dropout result is one event (N=1).",
        "The lateral and range results are guided sequences with correlated video samples, not large sets of independent trials.",
        "No universal CV, formal IMM, or GHOST-MH superiority claim is supported.",
        "RT-001 latency and RT-002 publication-rate requirements were not met.",
        "A C++ CV maximum execution-time row exceeded the declared 33.333 ms deadline.",
        "Hard-real-time certification, production readiness, flight worthiness, and autonomous-flight qualification are not claimed.",
        "No retained outdoor or adversarial visual-target hardware campaign was found.",
        "The lighting-degradation fault case was software-injected, not a physical outdoor lighting trial.",
        "No approved camera video or image frames were retained for the interactive replay.",
        "ICM-42688-P driver/interface code is implemented, but sensor identity, rate, and data validation were not captured in a retained campaign artifact.",
    ]

    evidence_map = {
        "hero.hardware_dropout": ["GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json"],
        "hero.controlled_trials": ["GHOST_X_G4_VALIDATION.json"],
        "hero.fault_cases": ["GHOST_X_G8_FAULT_REPORT.json"],
        "hero.rt002_failure": ["GHOST_X_G9_RUNTIME_REPORT.json"],
        "mission.drone_follow_simulation": ["GHOST_DRONE_MISSION_VALIDATION.json"],
        "architecture.hardware_identity": ["GHOST_X_BASELINE_MANIFEST.json"],
        "replay.measurements_and_events": [
            "data/GHOST_HARDWARE_REPLAY_20260716.json",
            "guided_hardware_evidence/20260716_guided_sequence_summary.json",
        ],
        "estimators.symmetric_rmse": ["GHOST_X_G10_CI_REPORT.json"],
        "estimators.symmetric_runtime": ["GHOST_X_G9_RUNTIME_REPORT.json"],
        "occlusion.hardware": ["GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json"],
        "occlusion.synthetic_long_hide": ["GHOST_DRONE_MISSION_VALIDATION.json"],
        "faults": ["GHOST_X_G8_FAULT_REPORT.json", "GHOST_X_G8_FAULT_REPORT.csv"],
        "runtime": ["GHOST_X_G9_RUNTIME_REPORT.json", "GHOST_X_G9_RUNTIME_REPORT.csv"],
        "traceability": ["GHOST_X_FINAL_TRACEABILITY.csv"],
        "claim_boundaries": [
            "GHOST_X_CLAIM_BOUNDARIES.md",
            "GHOST_X_APPROVED_CLAIMS.json",
            "GHOST_X_FAILURE_GALLERY.json",
        ],
    }

    downloads = [
        source_link("GHOST_PUBLIC_RESULTS_REPORT.md", "Engineering results report"),
        source_link("GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json", "Guided hardware validation JSON"),
        source_link("GHOST_X_G4_VALIDATION.json", "Controlled-truth validation JSON"),
        source_link("GHOST_X_G7_TRADE_STUDY.json", "Estimator trade-study JSON"),
        source_link("GHOST_X_G7_TRADE_STUDY.csv", "Estimator trade-study CSV"),
        source_link("GHOST_X_G8_FAULT_REPORT.json", "Fault report JSON"),
        source_link("GHOST_X_G8_FAULT_REPORT.csv", "Fault report CSV"),
        source_link("GHOST_X_G9_RUNTIME_REPORT.json", "Runtime report JSON"),
        source_link("GHOST_X_G9_RUNTIME_REPORT.csv", "Runtime report CSV"),
        source_link("GHOST_X_G10_CI_REPORT.json", "Regression report JSON"),
        source_link("GHOST_X_FINAL_TRACEABILITY.csv", "Requirements traceability CSV"),
        source_link("GHOST_X_RELEASE_MANIFEST.json", "Release manifest"),
        source_link("GHOST_INTERACTIVE_EVIDENCE_CHECKLIST.md", "Interactive evidence checklist"),
        source_link("data/GHOST_INTERACTIVE_SHOWCASE_DATA_V2.json", "Interactive page data"),
        source_link("data/GHOST_HARDWARE_REPLAY_20260716.json", "Compact hardware replay data"),
    ]

    return {
        "schema_version": 2,
        "page_title": "GHOST-X — Autonomous Object Tracking for Follower-Drone Applications",
        "framing": {
            "headline": "Autonomous Object Tracking for Follower-Drone Applications",
            "subheadline": (
                "An AprilTag-based perception and estimation backbone that detects a tagged "
                "target, estimates camera-frame pose, maintains tracker state through visibility "
                "loss, and exposes state suitable for downstream follow behavior."
            ),
            "scope_statement": (
                "Hardware validation covers the Raspberry Pi vision/tracking backbone under "
                "guided tabletop conditions. Drone following was evaluated only in deterministic "
                "local-frame software simulation; no physical drone was flown."
            ),
        },
        "hero_metrics": hero,
        "mission": {
            "badge": "SYNTHETIC_SOFTWARE",
            "source": "GHOST_DRONE_MISSION_VALIDATION.json",
            "passed": mission["passed"],
            "mission_completed": mission["mission_complete"],
            "elapsed_s": mission["elapsed_s"],
            "measurement_count": mission["measurement_count"],
            "observer_distance_traveled_m": mission["observer_distance_traveled_m"],
            "final_target_observer_separation_m": mission["final_target_observer_separation_m"],
            "obstacle_occlusion_count": mission["obstacle_occlusion_count"],
            "occlusion_durations_s": mission["occlusion_durations_s"],
            "reacquisition_count": mission["reacquisition_count"],
            "collision_count": mission["collision_count"],
            "out_of_bounds_count": mission["out_of_bounds_count"],
            "imm_rms_all_m": mission["errors_m"]["imm_rms_all"],
            "imm_rms_hidden_m": mission["errors_m"]["imm_rms_hidden"],
            "mh_rms_all_m": mission["errors_m"]["mh_rms_all"],
            "mh_rms_hidden_m": mission["errors_m"]["mh_rms_hidden"],
            "claim_boundary": mission["claim_boundary"],
        },
        "system_stages": system_stages,
        "imu_status": {
            "status": "IMPLEMENTED_NOT_PHYSICALLY_EVIDENCED",
            "statement": (
                "ICM-42688-P driver/interface implemented; sensor identity, data rate, and "
                "measurement validation were not captured in a retained campaign artifact."
            ),
            "implementation_evidence": [
                "../src/imu_driver/icm42688p.cpp",
                "../src/imu_driver/icm42688p.hpp",
                "../src/ros2_nodes/imu_node.cpp",
            ],
        },
        "replay": {
            "data_path": "data/GHOST_HARDWARE_REPLAY_20260716.json",
            "badge": "MEASURED_HARDWARE",
            "scope": "BROWSER_CUE_WINDOW_ONLY",
            "video_available": False,
        },
        "estimator_comparison": {
            "badge": "SYNTHETIC_SOFTWARE",
            "trial_basis": "N=24 deterministic analytic-truth trials across 8 scenario families",
            "input_fairness": "All three estimators received identical input streams in all 24 trials.",
            "runtime_basis": runtime_basis,
            "estimators": estimators,
            "selected_trade_study_status": g7["selection_status"],
            "unavailable_symmetric_metrics": [
                "Reacquisition time for CV, formal IMM, and GHOST-MH on one common retained campaign",
                "Reset count for CV, formal IMM, and GHOST-MH on one common retained final campaign",
            ],
        },
        "occlusion_scenarios": occlusion_scenarios,
        "response_scenarios": response_scenarios,
        "hardware": {
            "badge": "MEASURED_HARDWARE",
            "compute": baseline["hardware"]["compute"],
            "raspberry_pi_model": baseline["platform"]["raspberry_pi_model"],
            "os": baseline["platform"]["os_release"]["PRETTY_NAME"],
            "kernel": baseline["platform"]["kernel"],
            "machine": baseline["platform"]["machine"],
            "ros_distro": baseline["platform"]["ros_distro"],
            "camera": baseline["hardware"]["camera_name"],
            "camera_interface": baseline["hardware"]["camera_interface"],
            "tag_family": hardware["camera"]["tag_family"],
            "tag_id": hardware["camera"]["tag_id"],
            "tag_size_m": hardware["camera"]["tag_size_m"],
            "calibration_rms_reprojection_error_px": hardware["camera"]["calibration_rms_reprojection_error_px"],
            "camera_pose_hz": rates["camera_pose_hz"],
            "imm_output_hz": rates["imm_output_hz"],
            "mh_output_hz": rates["mh_output_hz"],
            "max_process_rss_mb": g9["environment"]["max_process_rss_mb"],
            "max_estimator_benchmark_rss_mb": max_estimator_benchmark_rss_mb,
            "max_temperature_c": max_temperature,
            "throttled_status_final": g9["environment"]["throttled_status_final"],
            "approved_photos_available": False,
            "photo_note": "No privacy-reviewed setup photographs were retained in the repository.",
        },
        "fault_testing": {
            "badge": "SYNTHETIC_SOFTWARE",
            "source": "GHOST_X_G8_FAULT_REPORT.json",
            "source_stream": "/".join(Path(g8["source_stream"]).parts[-2:]),
            "fault_count": g8["fault_count"],
            "passed_faults": g8["passed_faults"],
            "failed_faults": g8["failed_faults"],
            "pass_definition": (
                "Each case passed only when the injected fault was detected, isolated to the "
                "expected subsystem/status path, and returned to nominal or the predeclared "
                "accepted recovery state."
            ),
            "metric_interpretation": (
                "All twelve injections reuse one shared canonical evaluation stream. The RMSE and "
                "recovery-time columns are outputs of that shared-stream campaign and should not "
                "be interpreted as twelve independently measured physical degradation profiles."
            ),
            "unique_recovery_time_count": len(fault_recovery_groups),
            "recovery_time_groups": fault_recovery_groups,
            "unique_rmse_profile_count": len(fault_rmse_groups),
            "rmse_profile_groups": fault_rmse_groups,
            "faults": fault_rows,
            "claim_boundary": g8["claim_boundary"],
        },
        "runtime": {
            "badge": "MEASURED_HARDWARE",
            "source": "GHOST_X_G9_RUNTIME_REPORT.json",
            "requirements": g9["requirements"],
            "estimator_deadline": g9["estimator_deadline"],
            "deadline_rows_total": len(deadline_rows),
            "deadline_rows_met": deadline_rows_met,
            "deadline_rows_not_met": len(deadline_rows_not_met),
            "deadline_miss_rows": deadline_rows_not_met,
            "rt002_root_cause_status": "NOT_ESTABLISHED",
            "rt002_interpretation": (
                "The retained bench evidence establishes a severe publication-rate shortfall, "
                "but it does not establish the causal mechanism. No QoS, driver, scheduling, "
                "or startup explanation is claimed without a dedicated follow-up experiment."
            ),
            "deadline_anomaly_interpretation": (
                "Eleven of twelve measured maximum-execution rows met the 33.333 ms deadline. "
                "The only miss was C++ CV with zero stress workers; the C++ CV stress=2 row met "
                "the deadline. This counterintuitive ordering is retained as an unresolved "
                "benchmark anomaly and does not show that CPU stress improves execution time."
            ),
            "reporting_check_interpretation": (
                "The G10 reporting check passed because the deadline miss was reported and the "
                "hard-real-time claim was withheld. It does not mean the timing requirement passed."
            ),
            "environment": g9["environment"],
            "qos_scenarios": g9["qos_scenarios"],
            "qos_passed_count": g9["qos_passed_count"],
            "real_time_claim_status": g9["real_time_claim_status"],
            "requirements_all_passed": g9["requirements_all_passed"],
            "what_passed": [
                "RT-003 resource and thermal evidence collection passed.",
                "No throttling flag was reported in the retained runtime campaign.",
                "Eight QoS scenarios met their scenario-specific acceptance logic.",
                "Eleven of twelve measured estimator maximum-execution rows remained below the 33.333 ms deadline.",
            ],
            "what_did_not_pass": [
                "RT-001 nominal source-to-receipt latency exceeded the predeclared p95 and p99 limits.",
                "RT-002 publication rate was 3.4433 Hz versus a 29.7 Hz minimum.",
                "One of twelve rows—C++ CV with zero stress workers—exceeded 33.333 ms; its root cause is not established.",
                "The aggregate runtime requirements did not support a hard-real-time claim.",
            ],
        },
        "verification": {
            "requirements_traceable": status["requirements"]["traceable"],
            "requirements_total": status["requirements"]["total"],
            "traceability_csv_rows": traceability_count,
            "g10_checks_passed": g10["summary"]["passed_count"],
            "g10_checks_total": g10["summary"]["check_count"],
            "deterministic_files": public_summary["verification"]["deterministic_files"],
            "release": status["release_version"],
        },
        "limitations": limitations,
        "evidence_map": evidence_map,
        "downloads": downloads,
    }


def build_checklist() -> str:
    return """# GHOST-X Interactive Showcase Evidence Checklist

This checklist maps the interactive page's headline claims to retained evidence. The page must not publish a number or conclusion outside this map.

| Page claim or section | Evidence source | Data class | Sample basis / boundary |
|---|---|---|---|
| 2.4510 s intended hardware occlusion; reacquired without reset | `GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json` | Measured hardware | N=1 intended dropout |
| 24/24 controlled-truth trials accepted | `GHOST_X_G4_VALIDATION.json`, `GHOST_X_G10_CI_REPORT.json` | Synthetic software | N=24 trials, 8 scenario families |
| 12/12 software-injected faults passed | `GHOST_X_G8_FAULT_REPORT.json`, `.csv`, `g8_fault_evidence/*.jsonl` | Synthetic software | N=12 cases; pass means correct detection, isolation, and accepted recovery on one shared canonical stream |
| RT-002 observed 3.4433 Hz versus 29.7 Hz minimum | `GHOST_X_G9_RUNTIME_REPORT.json` | Measured hardware runtime | Requirement not met |
| Follower-drone navigation/reacquisition behavior | `GHOST_DRONE_MISSION_VALIDATION.json` | Synthetic software | One deterministic local-frame mission; no physical flight |
| Raspberry Pi 4B, eMeet C960, ROS 2 Jazzy, AprilTag identity | `GHOST_X_BASELINE_MANIFEST.json`, `GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json` | Measured hardware | Guided tabletop campaign |
| Interactive replay measurements, events, and tracker states | `data/GHOST_HARDWARE_REPLAY_20260716.json` plus embedded source hashes | Measured hardware | Browser cue window only; no interpolation or video |
| CV / formal IMM / GHOST-MH overall and hidden RMSE | `GHOST_X_G10_CI_REPORT.json` | Synthetic software | Identical inputs, N=24 |
| Matched Python-reference runtime rows | `GHOST_X_G9_RUNTIME_REPORT.json` | Measured hardware runtime | Raspberry Pi, no stress workers |
| Short-hide occlusion result | `GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json`, `guided_hardware_evidence/*.json` | Measured hardware | N=1 intended hardware dropout; not duplicated under another label |
| Lateral and range response results | `GHOST_GUIDED_HARDWARE_VALIDATION_20260716.json`, `guided_hardware_evidence/*.json` | Measured hardware | Directional/range response; correlated samples are not independent trials and are not occlusion tests |
| Long-hide mission occlusions | `GHOST_DRONE_MISSION_VALIDATION.json` | Synthetic software | N=2 occlusions in one mission |
| Runtime pass/fail and deadline evidence | `GHOST_X_G9_RUNTIME_REPORT.json`, `.csv` | Measured hardware runtime | RT-001 and RT-002 failed; RT-003 passed; 11/12 estimator max-time rows met the deadline |
| 34/34 requirement traceability | `GHOST_X_FINAL_TRACEABILITY.csv`, `GHOST_X_SOFTWARE_STATUS.json` | Verification | 34 mapped rows |
| Limitations and rejected evidence | `GHOST_X_CLAIM_BOUNDARIES.md`, `GHOST_X_APPROVED_CLAIMS.json`, `GHOST_X_FAILURE_GALLERY.json` | Claim governance | Permanent page section |

## Metrics intentionally shown as unavailable

- Symmetric reacquisition time for CV, formal IMM, and GHOST-MH on one common retained campaign.
- Symmetric reset count for all three estimators on one common retained final comparison campaign.
- Metrology-grade physical target truth.
- Physical closed-loop drone-flight results.
- Physical ICM-42688-P identity/rate/data validation for this campaign.
- Approved camera footage or setup photographs.
- Outdoor or adversarial visual-target hardware results.
- Hard-real-time certification or flight-worthiness evidence.

## Presentation rules

- Measured hardware, synthetic software, and verification evidence use visibly different badges.
- Null metrics render as “Not retained,” never as zero.
- Replay points are recorded samples only. Tracker points may be downselected from recorded samples but are never interpolated.
- Equal tracker comparison charts use identical scales and identical metric definitions.
- Failures and null results remain visible.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-trial-dir",
        type=Path,
        default=DEFAULT_RAW_TRIAL,
        help="External retained recorder trial directory used to build compact replay JSON.",
    )
    parser.add_argument(
        "--skip-replay-if-missing",
        action="store_true",
        help="Generate repository-only showcase data even when external replay sources are unavailable.",
    )
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_json(SHOWCASE_OUT, build_showcase())
    CHECKLIST_OUT.write_text(build_checklist(), encoding="utf-8")

    replay_written = False
    if args.raw_trial_dir.is_dir():
        write_json(REPLAY_OUT, build_replay(args.raw_trial_dir))
        replay_written = True
    elif not args.skip_replay_if_missing:
        raise FileNotFoundError(f"Raw trial directory not found: {args.raw_trial_dir}")

    print(
        json.dumps(
            {
                "showcase": str(SHOWCASE_OUT),
                "replay": str(REPLAY_OUT) if replay_written else None,
                "checklist": str(CHECKLIST_OUT),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
