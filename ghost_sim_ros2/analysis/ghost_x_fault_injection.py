"""Deterministic software fault injection and monitor validation for GHOST-X."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from analysis.ghost_x_offline_estimators import make_default_adapters


EXPECTED_STATUS = {
    "camera_disconnect": "FAULT_CAMERA_DISCONNECTED",
    "frozen_measurement": "FAULT_FROZEN_MEASUREMENT",
    "duplicate_measurement": "FAULT_DUPLICATE_MEASUREMENT",
    "false_detection": "FAULT_FALSE_DETECTION_REJECTED",
    "covariance_corruption": "FAULT_COVARIANCE_INVALID_FALLBACK",
    "latency": "FAULT_STALE_MEASUREMENT_REJECTED",
    "out_of_sequence_data": "FAULT_OUT_OF_SEQUENCE_REJECTED",
    "node_restart": "FAULT_NODE_RESTART",
    "cpu_saturation": "FAULT_DEADLINE_MISS",
    "network_degradation": "FAULT_NETWORK_DEGRADED",
    "parameter_mismatch": "FAULT_CONFIGURATION_MISMATCH",
    "lighting_degradation": "FAULT_LOW_VISUAL_QUALITY",
}


@dataclass(frozen=True)
class FaultDesign:
    seed: int
    source_campaign: Path
    representative_trial: str
    start_s: float
    end_s: float
    faults: tuple[str, ...]
    monitors: dict[str, float]
    maximum_recovery_s: float
    allow_no_recovery: tuple[str, ...]


def load_design(path: Path) -> FaultDesign:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("fault campaign design must be a mapping")
    start_s, end_s = [float(item) for item in value["fault_window_s"]]
    if not 0.0 <= start_s < end_s:
        raise ValueError("invalid fault window")
    faults = tuple(str(item) for item in value["faults"])
    unknown = sorted(set(faults) - set(EXPECTED_STATUS))
    if unknown:
        raise ValueError(f"unknown faults: {unknown}")
    monitors = {str(key): float(item) for key, item in value["monitors"].items()}
    return FaultDesign(
        seed=int(value["seed"]),
        source_campaign=Path(str(value["source_campaign"])),
        representative_trial=str(value["representative_trial"]),
        start_s=start_s,
        end_s=end_s,
        faults=faults,
        monitors=monitors,
        maximum_recovery_s=float(value["acceptance"]["maximum_recovery_s"]),
        allow_no_recovery=tuple(str(item) for item in value["acceptance"].get("allow_no_recovery", [])),
    )


def load_stream(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"row {number} is not an object")
        rows.append(value)
    if not rows:
        raise ValueError(f"empty stream: {path}")
    return rows


def inject_fault(rows: list[dict[str, Any]], fault: str, design: FaultDesign) -> list[dict[str, Any]]:
    if fault not in EXPECTED_STATUS:
        raise ValueError(f"unknown fault: {fault}")
    seed_material = f"{design.seed}:{fault}".encode()
    seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    result: list[dict[str, Any]] = []
    pre_fault_measurement: list[float] | None = None
    delayed_queue: list[tuple[float, list[float] | None]] = []
    for index, original in enumerate(rows):
        row = json.loads(json.dumps(original))
        t_s = float(row["t_s"])
        active = design.start_s <= t_s < design.end_s
        measurement = row.get("measurement_xy_m") if bool(row.get("visible")) else None
        if t_s < design.start_s and measurement is not None:
            pre_fault_measurement = [float(measurement[0]), float(measurement[1])]
        metadata: dict[str, Any] = {
            "fault": fault,
            "fault_active": active,
            "source_timestamp_s": t_s,
            "receipt_timestamp_s": t_s,
            "processing_delay_s": 0.0,
            "camera_link_up": True,
            "quality": 1.0,
            "configuration_id": "GHOST_X_NOMINAL",
            "restart_event": False,
            "network_drop": False,
        }

        if active and fault == "camera_disconnect":
            row["visible"] = False
            row["measurement_xy_m"] = None
            metadata["camera_link_up"] = False
        elif active and fault == "frozen_measurement":
            if pre_fault_measurement is not None:
                row["visible"] = True
                row["measurement_xy_m"] = list(pre_fault_measurement)
        elif active and fault == "duplicate_measurement":
            if result:
                prior = result[-1]
                row["visible"] = bool(prior["visible"])
                row["measurement_xy_m"] = prior.get("measurement_xy_m")
                metadata["source_timestamp_s"] = prior["fault_metadata"]["source_timestamp_s"]
        elif active and fault == "false_detection":
            # Sparse gross outliers rather than an unrealistically persistent offset track.
            if measurement is not None and (abs(t_s - design.start_s) < 0.5 * float(row["dt_s"]) or index % 17 == 0):
                row["measurement_xy_m"] = [float(measurement[0]) + 1.20, float(measurement[1]) - 0.80]
                row["visible"] = True
        elif active and fault == "covariance_corruption":
            row["measurement_covariance_xy_m2"] = [[-1.0, 2.0], [0.0, -1.0]]
        elif fault == "latency":
            delayed_queue.append((t_s, None if measurement is None else [float(measurement[0]), float(measurement[1])]))
            if active:
                delay_steps = 5
                source_index = max(0, len(delayed_queue) - 1 - delay_steps)
                source_time, delayed = delayed_queue[source_index]
                row["measurement_xy_m"] = delayed
                row["visible"] = delayed is not None
                metadata["source_timestamp_s"] = source_time
                metadata["receipt_timestamp_s"] = t_s
        elif active and fault == "out_of_sequence_data":
            metadata["source_timestamp_s"] = max(0.0, t_s - 0.6)
        elif active and fault == "node_restart":
            if abs(t_s - design.start_s) < 0.5 * float(row["dt_s"]):
                metadata["restart_event"] = True
        elif active and fault == "cpu_saturation":
            metadata["processing_delay_s"] = 0.25
        elif active and fault == "network_degradation":
            if index % 3 != 0:
                row["visible"] = False
                row["measurement_xy_m"] = None
                metadata["network_drop"] = True
        elif active and fault == "parameter_mismatch":
            metadata["configuration_id"] = "UNAPPROVED_CONFIG_HASH"
        elif active and fault == "lighting_degradation":
            metadata["quality"] = 0.15
            if measurement is not None:
                noisy = np.asarray(measurement, dtype=float) + rng.normal(0.0, 0.25, size=2)
                row["measurement_xy_m"] = [float(noisy[0]), float(noisy[1])]
            if index % 5 in {1, 2}:
                row["visible"] = False
                row["measurement_xy_m"] = None
        row["fault_metadata"] = metadata
        result.append(row)
    return result


class FaultMonitor:
    def __init__(self, design: FaultDesign, nominal_covariance: np.ndarray):
        self.design = design
        self.nominal_covariance = np.asarray(nominal_covariance, dtype=float)
        self.last_source_timestamp: float | None = None
        self.last_observed_source_timestamp: float | None = None
        self.last_accepted_measurement: np.ndarray | None = None
        self.last_raw_measurement: np.ndarray | None = None
        self.reacquisition_candidates: list[np.ndarray] = []
        self.identical_count = 0
        self.missing_count = 0
        self.total_count = 0
        self.events: list[dict[str, Any]] = []

    def inspect(self, row: dict[str, Any]) -> dict[str, Any]:
        metadata = row["fault_metadata"]
        t_s = float(row["t_s"])
        self.total_count += 1
        status = "NOMINAL"
        accepted = bool(row.get("visible")) and row.get("measurement_xy_m") is not None
        isolation = "NONE"
        reason = None

        if not bool(metadata["camera_link_up"]):
            status, accepted, isolation = "FAULT_CAMERA_DISCONNECTED", False, "CAMERA_LINK"
        elif bool(metadata["restart_event"]):
            status, isolation = "FAULT_NODE_RESTART", "PROCESS_LIFECYCLE"
        elif float(metadata["processing_delay_s"]) > self.design.monitors["deadline_s"]:
            status, isolation = "FAULT_DEADLINE_MISS", "EXECUTION_TIMING"
        elif str(metadata["configuration_id"]) != "GHOST_X_NOMINAL":
            status, accepted, isolation = "FAULT_CONFIGURATION_MISMATCH", False, "CONFIGURATION_GATE"
        elif float(metadata["quality"]) < self.design.monitors["minimum_quality"]:
            status, accepted, isolation = "FAULT_LOW_VISUAL_QUALITY", False, "VISION_QUALITY_GATE"
        elif bool(metadata["network_drop"]):
            status, accepted, isolation = "FAULT_NETWORK_DEGRADED", False, "TRANSPORT_LOSS"

        source_timestamp = float(metadata["source_timestamp_s"])
        receipt_timestamp = float(metadata["receipt_timestamp_s"])
        if status == "NOMINAL" and self.last_observed_source_timestamp is not None and source_timestamp < self.last_observed_source_timestamp - 1e-12:
            status, accepted, isolation = "FAULT_OUT_OF_SEQUENCE_REJECTED", False, "MONOTONIC_TIMESTAMP_GATE"
        elif status == "NOMINAL" and self.last_observed_source_timestamp is not None and abs(source_timestamp - self.last_observed_source_timestamp) <= 1e-12:
            status, accepted, isolation = "FAULT_DUPLICATE_MEASUREMENT", False, "DUPLICATE_TIMESTAMP_GATE"
        elif status == "NOMINAL" and receipt_timestamp - source_timestamp > self.design.monitors["maximum_latency_s"]:
            status, accepted, isolation = "FAULT_STALE_MEASUREMENT_REJECTED", False, "TIMESTAMP_AGE_GATE"
        if self.last_observed_source_timestamp is None or source_timestamp > self.last_observed_source_timestamp:
            self.last_observed_source_timestamp = source_timestamp

        covariance = np.asarray(row.get("measurement_covariance_xy_m2"), dtype=float)
        if status == "NOMINAL" and not _spd(covariance):
            status, isolation = "FAULT_COVARIANCE_INVALID_FALLBACK", "COVARIANCE_VALIDATOR"
            row["measurement_covariance_xy_m2"] = self.nominal_covariance.tolist()

        measurement = None
        if bool(row.get("visible")) and row.get("measurement_xy_m") is not None:
            measurement = np.asarray(row["measurement_xy_m"], dtype=float)
            if self.last_raw_measurement is not None and np.array_equal(measurement, self.last_raw_measurement):
                self.identical_count += 1
            else:
                self.identical_count = 1
            self.last_raw_measurement = measurement.copy()
            if status == "NOMINAL" and self.identical_count >= int(self.design.monitors["frozen_repeat_threshold"]):
                status, accepted, isolation = "FAULT_FROZEN_MEASUREMENT", False, "FROZEN_SAMPLE_MONITOR"
            if status == "NOMINAL" and self.last_accepted_measurement is not None:
                jump = float(np.linalg.norm(measurement - self.last_accepted_measurement))
                if jump > self.design.monitors["innovation_gate_m"]:
                    if self.reacquisition_candidates and float(np.linalg.norm(measurement - self.reacquisition_candidates[-1])) <= 0.25:
                        self.reacquisition_candidates.append(measurement.copy())
                    else:
                        self.reacquisition_candidates = [measurement.copy()]
                    if len(self.reacquisition_candidates) >= 3:
                        status, accepted, isolation = "RECOVERY_REACQUISITION_ACCEPTED", True, "CONSISTENT_CLUSTER_REACQUISITION"
                        self.reacquisition_candidates.clear()
                    else:
                        status, accepted, isolation = "FAULT_FALSE_DETECTION_REJECTED", False, "INNOVATION_MAGNITUDE_GATE"
                else:
                    self.reacquisition_candidates.clear()
        else:
            self.missing_count += 1

        if accepted and measurement is not None:
            self.last_accepted_measurement = measurement.copy()
            self.last_source_timestamp = source_timestamp
        elif self.last_source_timestamp is None or source_timestamp > self.last_source_timestamp:
            # Advance timestamp for explicitly missing data, but not duplicates/OOS samples.
            if status in {"FAULT_CAMERA_DISCONNECTED", "FAULT_NETWORK_DEGRADED", "FAULT_LOW_VISUAL_QUALITY"}:
                self.last_source_timestamp = source_timestamp

        if status != "NOMINAL":
            reason = isolation
            self.events.append({"t_s": t_s, "status": status, "isolation": isolation})
        return {
            "status": status,
            "accepted": accepted,
            "isolation": isolation,
            "reason": reason,
            "measurement": measurement.tolist() if accepted and measurement is not None else None,
        }


def run_fault_trial(rows: list[dict[str, Any]], fault: str, design: FaultDesign) -> dict[str, Any]:
    faulted = inject_fault(rows, fault, design)
    nominal_covariance = np.asarray(rows[0]["measurement_covariance_xy_m2"], dtype=float)
    monitor = FaultMonitor(design, nominal_covariance)
    adapters = make_default_adapters(float(rows[0]["dt_s"]), nominal_covariance, mh_max_occlusion_s=20.0)
    initialized_once = {name: False for name in adapters}
    output_rows: list[dict[str, Any]] = []
    errors: dict[str, list[float]] = {name: [] for name in adapters}
    nonfinite_count = 0
    fault_end = design.end_s
    recovery_time: float | None = None
    detected_at: float | None = None
    observed_statuses: set[str] = set()
    restart_applied = False

    for row in faulted:
        t_s = float(row["t_s"])
        decision = monitor.inspect(row)
        status = str(decision["status"])
        observed_statuses.add(status)
        if status != "NOMINAL" and detected_at is None:
            detected_at = t_s
        if bool(row["fault_metadata"]["restart_event"]):
            adapters = make_default_adapters(float(row["dt_s"]), nominal_covariance, mh_max_occlusion_s=20.0)
            restart_applied = True
        estimates = {}
        all_initialized = True
        for name, adapter in adapters.items():
            output = adapter.step(float(row["dt_s"]), decision["measurement"])
            payload = output.to_dict()
            estimates[name] = payload
            initialized = bool(payload.get("initialized"))
            initialized_once[name] = initialized_once[name] or initialized
            all_initialized = all_initialized and initialized
            state = payload.get("state")
            if initialized and isinstance(state, dict):
                values = [state.get("x_m"), state.get("y_m"), state.get("vx_mps"), state.get("vy_mps")]
                if not all(_finite(value) for value in values):
                    nonfinite_count += 1
                truth = row["truth"]
                errors[name].append(math.hypot(float(state["x_m"]) - float(truth["x_m"]), float(state["y_m"]) - float(truth["y_m"])))
        if t_s >= fault_end and recovery_time is None and decision["accepted"] and all_initialized:
            recovery_time = max(0.0, t_s - fault_end)
        output_rows.append(
            {
                "sequence": int(row["sequence"]),
                "t_s": t_s,
                "fault_active": bool(row["fault_metadata"]["fault_active"]),
                "raw_measurement": row.get("measurement_xy_m"),
                "monitor": {key: value for key, value in decision.items() if key != "measurement"},
                "accepted_measurement": decision["measurement"],
                "estimates": estimates,
            }
        )

    expected = EXPECTED_STATUS[fault]
    detected = expected in observed_statuses
    isolated = any(event["status"] == expected and event["isolation"] != "NONE" for event in monitor.events)
    if fault == "node_restart":
        isolated = detected and restart_applied
    recovery_allowed_missing = fault in design.allow_no_recovery
    recovery_ok = recovery_time is not None and recovery_time <= design.maximum_recovery_s
    if recovery_allowed_missing and recovery_time is None:
        recovery_ok = True
    passed = detected and isolated and recovery_ok and nonfinite_count == 0 and all(initialized_once.values())
    return {
        "fault": fault,
        "expected_status": expected,
        "detected": detected,
        "detected_at_s": detected_at,
        "isolated": isolated,
        "observed_statuses": sorted(observed_statuses),
        "recovery_time_s": recovery_time,
        "recovery_ok": recovery_ok,
        "nonfinite_count": nonfinite_count,
        "all_estimators_initialized": all(initialized_once.values()),
        "position_error_rmse_m": {
            name: (float(math.sqrt(statistics.fmean(value * value for value in values))) if values else None)
            for name, values in errors.items()
        },
        "monitor_events": monitor.events,
        "passed": passed,
        "evidence_rows": output_rows,
        "discrepancy": None if passed else "EXPECTED_DETECTION_ISOLATION_RECOVERY_CONTRACT_NOT_MET",
    }


def run_campaign(design_path: Path) -> dict[str, Any]:
    design = load_design(design_path)
    stream_path = design.source_campaign / "canonical_streams" / f"{design.representative_trial}.jsonl"
    rows = load_stream(stream_path)
    trials = [run_fault_trial(rows, fault, design) for fault in design.faults]
    passed_count = sum(bool(trial["passed"]) for trial in trials)
    return {
        "schema_version": 1,
        "phase": "G8_FAULT_INJECTION",
        "source_stream": str(stream_path),
        "fault_count": len(trials),
        "passed_faults": passed_count,
        "failed_faults": len(trials) - passed_count,
        "passed": passed_count == len(trials) and len(trials) >= 10,
        "trials": trials,
        "claim_boundary": "DETERMINISTIC_SOFTWARE_FAULT_INJECTION_ACTUAL_HARDWARE_AND_DDS_FAULT_EVIDENCE_PENDING",
    }


def write_outputs(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    compact = dict(report)
    compact["trials"] = [{key: value for key, value in trial.items() if key != "evidence_rows"} for trial in report["trials"]]
    (out_dir / "GHOST_X_G8_FAULT_REPORT.json").write_text(json.dumps(compact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence_root = out_dir / "g8_fault_evidence"
    evidence_root.mkdir(exist_ok=True)
    for trial in report["trials"]:
        path = evidence_root / f"{trial['fault']}.jsonl"
        with path.open("w", encoding="utf-8") as stream:
            for row in trial["evidence_rows"]:
                stream.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
    with (out_dir / "GHOST_X_G8_FAULT_REPORT.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["fault", "expected_status", "detected", "isolated", "recovery_time_s", "recovery_ok", "passed", "discrepancy"])
        for trial in report["trials"]:
            writer.writerow(
                [
                    trial["fault"],
                    trial["expected_status"],
                    trial["detected"],
                    trial["isolated"],
                    trial["recovery_time_s"],
                    trial["recovery_ok"],
                    trial["passed"],
                    trial["discrepancy"],
                ]
            )
    lines = [
        "# GHOST-X G8 Fault-Injection Report",
        "",
        f"Faults: `{report['fault_count']}`",
        f"Passed: `{report['passed_faults']}`",
        f"Overall: `{'PASS' if report['passed'] else 'FAIL'}`",
        "",
        "| Fault | Detection | Isolation | Recovery (s) | Result |",
        "|---|---|---|---:|---|",
    ]
    for trial in report["trials"]:
        recovery = "NA" if trial["recovery_time_s"] is None else f"{trial['recovery_time_s']:.3f}"
        lines.append(
            f"| `{trial['fault']}` | {trial['detected']} | {trial['isolated']} | {recovery} | {'PASS' if trial['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This campaign verifies deterministic software monitors, status propagation, isolation gates, recovery logic, and retained evidence. Actual cable disconnects, DDS impairment, CPU stress, and lighting tests remain separate hardware/runtime evidence.",
            "",
        ]
    )
    (out_dir / "GHOST_X_G8_FAULT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def _spd(matrix: np.ndarray) -> bool:
    if matrix.shape != (2, 2) or not np.isfinite(matrix).all() or not np.allclose(matrix, matrix.T, atol=1e-12):
        return False
    try:
        np.linalg.cholesky(matrix)
    except np.linalg.LinAlgError:
        return False
    return True


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
