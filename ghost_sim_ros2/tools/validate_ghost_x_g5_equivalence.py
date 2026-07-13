#!/usr/bin/env python3
"""Validate standalone C++ GHOST-X estimators against independent NumPy references."""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_mh_mode_bank import ModeBankTracker  # noqa: E402
from analysis.ghost_x_offline_estimators import CvKalmanAdapter, FormalImmOfflineAdapter  # noqa: E402

FIELDS = ("x_m", "y_m", "vx_mps", "vy_mps", "cov_xx", "cov_xy", "cov_yy", "cov_vxvx", "cov_vyvy")
TOLERANCES = {
    "cv": {"state_abs": 1.0e-10, "covariance_abs": 1.0e-10},
    "imm": {"state_abs": 5.0e-8, "covariance_abs": 5.0e-8},
    "mh": {"state_abs": 5.0e-8, "covariance_abs": 5.0e-8},
}


@dataclass
class ReferenceRow:
    t_s: float
    initialized: bool
    values: dict[str, float]


def read_stream(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"non-object row in {path}")
            rows.append(value)
    if not rows:
        raise ValueError(f"empty stream: {path}")
    return rows


def write_input_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["t_s", "visible", "x_m", "y_m"])
        for row in rows:
            visible = bool(row["visible"])
            measurement = row.get("measurement_xy_m") if visible else None
            writer.writerow(
                [
                    f"{float(row['t_s']):.17g}",
                    1 if visible else 0,
                    "" if measurement is None else f"{float(measurement[0]):.17g}",
                    "" if measurement is None else f"{float(measurement[1]):.17g}",
                ]
            )


def read_cpp_csv(path: Path) -> list[ReferenceRow]:
    output = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            initialized = row["initialized"] == "1"
            values = {field: float(row[field]) for field in FIELDS if initialized}
            output.append(ReferenceRow(float(row["t_s"]), initialized, values))
    return output


def cv_reference(rows: list[dict[str, Any]]) -> list[ReferenceRow]:
    covariance = rows[0]["measurement_covariance_xy_m2"]
    adapter = CvKalmanAdapter(covariance, process_accel_std_mps2=0.65)
    result = []
    for row in rows:
        measurement = row.get("measurement_xy_m") if row["visible"] else None
        estimate = adapter.step(float(row["dt_s"]), measurement)
        result.append(convert_offline(float(row["t_s"]), estimate))
    return result


def imm_reference(rows: list[dict[str, Any]]) -> list[ReferenceRow]:
    covariance = rows[0]["measurement_covariance_xy_m2"]
    adapter = FormalImmOfflineAdapter(
        float(rows[0]["dt_s"]),
        covariance,
        smooth_acceleration_std_mps2=0.015,
        maneuver_acceleration_std_mps2=0.75,
        transition_probabilities=((0.97, 0.03), (0.08, 0.92)),
        p0_diag=(0.04, 0.04, 0.8, 0.8),
    )
    result = []
    for row in rows:
        measurement = row.get("measurement_xy_m") if row["visible"] else None
        estimate = adapter.step(float(row["dt_s"]), measurement)
        result.append(convert_offline(float(row["t_s"]), estimate))
    return result


def mh_reference(rows: list[dict[str, Any]]) -> list[ReferenceRow]:
    covariance = rows[0]["measurement_covariance_xy_m2"]
    tracker = ModeBankTracker(
        measurement_std_m=math.sqrt(float(covariance[0][0])),
        measurement_covariance_xy=covariance,
        gate_chi2=16.0,
        max_occlusion_s=20.0,
        max_workspace_range_m=100.0,
        allow_signed_local_coordinates=True,
    )
    result = []
    for row in rows:
        measurement = row.get("measurement_xy_m") if row["visible"] else None
        tracker.step(float(row["dt_s"]), measurement)
        estimate = tracker.estimate()
        if not estimate.initialized:
            result.append(ReferenceRow(float(row["t_s"]), False, {}))
            continue
        p = np.asarray(estimate.p, dtype=float)
        result.append(
            ReferenceRow(
                float(row["t_s"]),
                True,
                {
                    "x_m": float(estimate.x[0, 0]),
                    "y_m": float(estimate.x[1, 0]),
                    "vx_mps": float(estimate.x[2, 0]),
                    "vy_mps": float(estimate.x[3, 0]),
                    "cov_xx": float(p[0, 0]),
                    "cov_xy": float(p[0, 1]),
                    "cov_yy": float(p[1, 1]),
                    "cov_vxvx": float(p[2, 2]),
                    "cov_vyvy": float(p[3, 3]),
                },
            )
        )
    return result


def convert_offline(t_s: float, estimate: Any) -> ReferenceRow:
    if not estimate.initialized or estimate.state is None or estimate.covariance is None:
        return ReferenceRow(t_s, False, {})
    state = estimate.state
    p = estimate.covariance
    return ReferenceRow(
        t_s,
        True,
        {
            "x_m": float(state[0]),
            "y_m": float(state[1]),
            "vx_mps": float(state[2]),
            "vy_mps": float(state[3]),
            "cov_xx": float(p[0][0]),
            "cov_xy": float(p[0][1]),
            "cov_yy": float(p[1][1]),
            "cov_vxvx": float(p[2][2]),
            "cov_vyvy": float(p[3][3]),
        },
    )


def compare(name: str, reference: list[ReferenceRow], actual: list[ReferenceRow]) -> dict[str, Any]:
    if len(reference) != len(actual):
        return {"passed": False, "reason": "row_count_mismatch", "reference": len(reference), "actual": len(actual)}
    state_fields = {"x_m", "y_m", "vx_mps", "vy_mps"}
    max_state = 0.0
    max_covariance = 0.0
    init_mismatches = 0
    compared = 0
    worst: dict[str, Any] | None = None
    for expected, observed in zip(reference, actual):
        if expected.initialized != observed.initialized:
            init_mismatches += 1
            continue
        if not expected.initialized:
            continue
        compared += 1
        for field in FIELDS:
            delta = abs(expected.values[field] - observed.values[field])
            if field in state_fields:
                max_state = max(max_state, delta)
            else:
                max_covariance = max(max_covariance, delta)
            if worst is None or delta > worst["absolute_difference"]:
                worst = {"t_s": expected.t_s, "field": field, "absolute_difference": delta}
    limits = TOLERANCES[name]
    passed = (
        init_mismatches == 0
        and compared > 0
        and max_state <= limits["state_abs"]
        and max_covariance <= limits["covariance_abs"]
    )
    return {
        "passed": passed,
        "rows": len(reference),
        "compared_initialized_rows": compared,
        "initialization_mismatches": init_mismatches,
        "max_state_absolute_difference": max_state,
        "max_covariance_absolute_difference": max_covariance,
        "tolerance": limits,
        "worst": worst,
    }


def validate(build_dir: Path, campaign_dir: Path, out_path: Path) -> dict[str, Any]:
    cli = build_dir / "ghost_x_estimator_cli"
    if not cli.is_file():
        raise FileNotFoundError(cli)
    config = PACKAGE_ROOT / "cpp" / "ghost_x_estimators" / "config" / "default_estimator.cfg"
    streams = sorted((campaign_dir / "canonical_streams").glob("*.jsonl"))
    if len(streams) < 20:
        raise ValueError("G5 equivalence requires the complete >=20-trial canonical G4 set")
    references = {"cv": cv_reference, "imm": imm_reference, "mh": mh_reference}
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="ghost_x_g5_") as temp_text:
        temp = Path(temp_text)
        for estimator, reference_function in references.items():
            estimator_rows = []
            for stream in streams:
                rows = read_stream(stream)
                input_csv = temp / f"{stream.stem}.csv"
                output_csv = temp / f"{stream.stem}_{estimator}.csv"
                write_input_csv(rows, input_csv)
                completed = subprocess.run(
                    [str(cli), estimator, str(input_csv), str(output_csv), str(config)],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode != 0:
                    raise RuntimeError(f"C++ {estimator} failed for {stream.name}: {completed.stderr}")
                trial = compare(estimator, reference_function(rows), read_cpp_csv(output_csv))
                trial["trial_id"] = stream.stem
                estimator_rows.append(trial)
            results[estimator] = {
                "passed": all(row["passed"] for row in estimator_rows),
                "trials": estimator_rows,
                "max_state_absolute_difference": max(row.get("max_state_absolute_difference", math.inf) for row in estimator_rows),
                "max_covariance_absolute_difference": max(
                    row.get("max_covariance_absolute_difference", math.inf) for row in estimator_rows
                ),
            }
    report = {
        "schema_version": 1,
        "phase": "G5_CPP_PYTHON_EQUIVALENCE",
        "passed": all(value["passed"] for value in results.values()),
        "canonical_trials": len(streams),
        "estimators": results,
        "configuration": str(config),
        "configuration_sha256": __import__("hashlib").sha256(config.read_bytes()).hexdigest(),
        "claims_boundary": "Equivalence is established only for the pinned canonical streams, configuration, and declared elementwise tolerances.",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.build_dir, args.campaign_dir, args.out)
    print(json.dumps({"passed": report["passed"], "canonical_trials": report["canonical_trials"]}, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
