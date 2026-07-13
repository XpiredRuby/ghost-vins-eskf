"""GHOST-X G12 research-package assembly and claim-traceability helpers."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


PHYSICAL_PENDING_REQUIREMENTS = {
    "VNV-002",
    "VNV-003",
    "VNV-004",
    "VNV-005",
}
PROTOCOL_READY_REQUIREMENTS = {"VNV-001"}
QUALIFIED_BENCH_REQUIREMENTS = {"RT-001", "RT-002", "RT-003", "CON-001", "CON-002", "VNV-007"}

PHASE_EVIDENCE = {
    "G0": [
        "ghost_sim_ros2/docs/GHOST_X_G0_BASELINE.md",
        "ghost_sim_ros2/docs/GHOST_X_BASELINE_MANIFEST.json",
    ],
    "G1": [
        "ghost_sim_ros2/docs/GHOST_X_G1_REQUIREMENTS_AND_VNV.md",
        "ghost_sim_ros2/docs/GHOST_X_G1_VALIDATION.json",
    ],
    "G2": [
        "ghost_sim_ros2/docs/GHOST_X_G2_DATA_CONTRACTS.md",
        "ghost_sim_ros2/docs/GHOST_X_G2_VALIDATION.json",
        "ghost_sim_ros2/docs/GHOST_X_G2_RUNTIME_VALIDATION.json",
    ],
    "G3": [
        "ghost_sim_ros2/docs/GHOST_X_G3_MEASUREMENT_PROTOCOL.md",
        "ghost_sim_ros2/docs/GHOST_X_G3_READINESS.json",
    ],
    "G4": [
        "ghost_sim_ros2/docs/GHOST_X_G4_CONTROLLED_TRUTH.md",
        "ghost_sim_ros2/docs/GHOST_X_G4_VALIDATION.json",
    ],
    "G5": [
        "ghost_sim_ros2/docs/GHOST_X_G5_CPP_LIBRARY.md",
        "ghost_sim_ros2/docs/GHOST_X_G5_EQUIVALENCE.json",
        "ghost_sim_ros2/docs/GHOST_X_G5_VALIDATION.json",
    ],
    "G6": [
        "ghost_sim_ros2/docs/GHOST_X_G6_CONSISTENCY.md",
        "ghost_sim_ros2/docs/GHOST_X_G6_CONSISTENCY.json",
    ],
    "G7": [
        "ghost_sim_ros2/docs/GHOST_X_G7_TRADE_STUDY.md",
        "ghost_sim_ros2/docs/GHOST_X_G7_TRADE_STUDY.json",
    ],
    "G8": [
        "ghost_sim_ros2/docs/GHOST_X_G8_FAULT_REPORT.md",
        "ghost_sim_ros2/docs/GHOST_X_G8_FAULT_REPORT.json",
    ],
    "G9": [
        "ghost_sim_ros2/docs/GHOST_X_G9_RUNTIME_REPORT.md",
        "ghost_sim_ros2/docs/GHOST_X_G9_RUNTIME_REPORT.json",
    ],
    "G10": [
        "ghost_sim_ros2/docs/GHOST_X_G10_CI_REPORT.md",
        "ghost_sim_ros2/docs/GHOST_X_G10_CI_REPORT.json",
        ".github/workflows/ghost-x-regression.yml",
    ],
    "G11": [
        "ghost_sim_ros2/docs/GHOST_X_G11_FIXED_LAG.md",
        "ghost_sim_ros2/docs/GHOST_X_G11_FIXED_LAG.json",
    ],
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def git_value(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def requirement_status(requirement_id: str, phase: str) -> tuple[str, str]:
    if requirement_id in PHYSICAL_PENDING_REQUIREMENTS:
        return (
            "PHYSICAL_CAMPAIGN_PENDING",
            "The digital protocol, capture tooling, and synthetic campaign are complete; the required controlled physical trials have not been collected.",
        )
    if requirement_id in PROTOCOL_READY_REQUIREMENTS:
        return (
            "PROTOCOL_VERIFIED_EXECUTION_PENDING",
            "Truth method and uncertainty contracts exist, but formal physical execution remains pending.",
        )
    if requirement_id in QUALIFIED_BENCH_REQUIREMENTS:
        return (
            "QUALIFIED_SOFTWARE_OR_BENCH_EVIDENCE",
            "Evidence exists with explicit assumption and bench boundaries; physical truth or hard-real-time certification is not implied.",
        )
    if phase == "G3":
        return (
            "SOFTWARE_READY_PHYSICAL_COLLECTION_PENDING",
            "Measurement-campaign software is complete; collection requires operator positioning of the tag.",
        )
    return "SOFTWARE_VERIFIED", "Mapped software tests and immutable repository evidence are present."


def build_traceability(repo_root: Path) -> list[dict[str, Any]]:
    requirements_doc = load_yaml(repo_root / "ghost_sim_ros2/config/ghost_x_requirements.yaml")
    tests_doc = load_yaml(repo_root / "ghost_sim_ros2/config/ghost_x_test_catalog.yaml")
    tests = {str(item["id"]): item for item in tests_doc["tests"]}
    rows = []
    for requirement in requirements_doc["requirements"]:
        requirement_id = str(requirement["id"])
        phase = str(requirement["phase"])
        status, qualification = requirement_status(requirement_id, phase)
        mapped_tests = [str(item) for item in requirement.get("tests", [])]
        missing_tests = [test_id for test_id in mapped_tests if test_id not in tests]
        evidence = list(PHASE_EVIDENCE.get(phase, []))
        if phase == "G12":
            evidence = [
                "ghost_sim_ros2/docs/GHOST_X_FINAL_RESEARCH_PACKAGE.md",
                "ghost_sim_ros2/docs/GHOST_X_FAILURE_GALLERY.md",
                "ghost_sim_ros2/docs/GHOST_X_APPROVED_CLAIMS.md",
            ]
        existing = [item for item in evidence if (repo_root / item).is_file()]
        rows.append(
            {
                "requirement_id": requirement_id,
                "title": str(requirement["title"]),
                "phase": phase,
                "verification": str(requirement["verification"]),
                "tests": mapped_tests,
                "missing_tests": missing_tests,
                "evidence": evidence,
                "evidence_present": existing,
                "status": status,
                "qualification": qualification,
                "traceable": not missing_tests and bool(existing or phase == "G12"),
            }
        )
    return rows


def write_traceability(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "requirement_id",
                "title",
                "phase",
                "verification",
                "tests",
                "status",
                "traceable",
                "qualification",
                "evidence",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["requirement_id"],
                    row["title"],
                    row["phase"],
                    row["verification"],
                    ";".join(row["tests"]),
                    row["status"],
                    row["traceable"],
                    row["qualification"],
                    ";".join(row["evidence"]),
                ]
            )


def collect_phase_status(repo_root: Path) -> list[dict[str, Any]]:
    rows = []
    for number in range(0, 12):
        phase = f"G{number}"
        evidence = PHASE_EVIDENCE.get(phase, [])
        present = [item for item in evidence if (repo_root / item).is_file()]
        physical_pending = phase in {"G3", "G4"}
        status = "SOFTWARE_COMPLETE"
        if physical_pending:
            status = "SOFTWARE_COMPLETE_PHYSICAL_EXECUTION_PENDING"
        rows.append(
            {
                "phase": phase,
                "software_status": status,
                "evidence_count": len(present),
                "expected_evidence_count": len(evidence),
                "evidence": present,
                "complete": len(present) == len(evidence),
            }
        )
    return rows


def collect_evidence_manifest(repo_root: Path, extra_paths: Iterable[str]) -> dict[str, Any]:
    names = set(extra_paths)
    for evidence in PHASE_EVIDENCE.values():
        names.update(evidence)
    files = []
    missing = []
    for name in sorted(names):
        path = repo_root / name
        if not path.is_file():
            missing.append(name)
            continue
        files.append(
            {
                "path": name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    combined = hashlib.sha256()
    for item in files:
        combined.update(item["path"].encode("utf-8"))
        combined.update(b"\0")
        combined.update(item["sha256"].encode("ascii"))
        combined.update(b"\n")
    return {
        "files": files,
        "missing": missing,
        "file_count": len(files),
        "combined_sha256": f"sha256:{combined.hexdigest()}",
    }


def approved_claims(repo_root: Path) -> dict[str, Any]:
    g4 = load_json(repo_root / "ghost_sim_ros2/docs/GHOST_X_G4_VALIDATION.json")
    g5 = load_json(repo_root / "ghost_sim_ros2/docs/GHOST_X_G5_VALIDATION.json")
    g8 = load_json(repo_root / "ghost_sim_ros2/docs/GHOST_X_G8_FAULT_REPORT.json")
    g9 = load_json(repo_root / "ghost_sim_ros2/docs/GHOST_X_G9_RUNTIME_REPORT.json")
    g10 = load_json(repo_root / "ghost_sim_ros2/docs/GHOST_X_G10_CI_REPORT.json")
    return {
        "approved": [
            {
                "id": "CLM-SW-001",
                "text": "Built a ROS 2 Raspberry Pi tracking and autonomy platform with formal IMM, multi-hypothesis tracking, deterministic replay, and machine-readable evidence contracts.",
                "evidence": ["GHOST_X_G2_VALIDATION.json", "GHOST_X_G10_CI_REPORT.json"],
                "qualification": "Platform claim; not a flight-qualified system.",
            },
            {
                "id": "CLM-SW-002",
                "text": f"Implemented an Eigen-based C++ estimator library and matched C++ and Python outputs across {g5.get('canonical_trials', 0)} frozen synthetic trials within declared numerical tolerances.",
                "evidence": ["GHOST_X_G5_VALIDATION.json", "GHOST_X_G5_EQUIVALENCE.json"],
                "qualification": "Numerical equivalence on pinned vectors, not independent physical accuracy.",
            },
            {
                "id": "CLM-SW-003",
                "text": f"Executed a {g4.get('planned_trials', 24)}-trial deterministic controlled-truth software campaign across eight motion and visibility-loss families using identical estimator inputs.",
                "evidence": ["GHOST_X_G4_VALIDATION.json", "GHOST_X_G10_CI_REPORT.json"],
                "qualification": "Synthetic analytic truth; controlled physical truth remains pending.",
            },
            {
                "id": "CLM-SW-004",
                "text": f"Implemented and verified detection, isolation, status, recovery, and retained evidence for {g8.get('fault_count', 0)} reproducible software-injected faults.",
                "evidence": ["GHOST_X_G8_FAULT_REPORT.json"],
                "qualification": "Deterministic software injection; selected faults still require direct hardware/runtime reproduction.",
            },
            {
                "id": "CLM-SW-005",
                "text": f"Benchmarked ROS 2 QoS behavior, estimator execution, CPU, memory, temperature, and throttling on a Raspberry Pi using {len(g9.get('qos_scenarios', []))} declared runtime scenarios.",
                "evidence": ["GHOST_X_G9_RUNTIME_REPORT.json"],
                "qualification": str(g9.get("real_time_claim_status", "HARD_REAL_TIME_NOT_CLAIMED")),
            },
            {
                "id": "CLM-SW-006",
                "text": f"Added one-command deterministic regression gates with {g10.get('summary', {}).get('check_count', 0)} requirements and evidence checks plus CI artifact export.",
                "evidence": ["GHOST_X_G10_CI_REPORT.json", ".github/workflows/ghost-x-regression.yml"],
                "qualification": "Synthetic and stored-evidence regression protection; physical campaign data will be added after collection.",
            },
        ],
        "prohibited_or_pending": [
            {
                "id": "CLM-PENDING-001",
                "text": "Hardware-validated room-scale position or velocity accuracy across the formal campaign.",
                "reason": "G3 measurement collection and at least 20 paired controlled physical trials are not complete.",
            },
            {
                "id": "CLM-PENDING-002",
                "text": "GHOST-MH statistically outperforms formal IMM.",
                "reason": "No physical paired statistics support this claim, and frozen synthetic results do not justify a universal superiority statement.",
            },
            {
                "id": "CLM-PENDING-003",
                "text": "Hard-real-time, flight-qualified, or safety-certified operation.",
                "reason": "Bench timing and resource evidence does not establish operating-system hard-real-time bounds or certification.",
            },
            {
                "id": "CLM-PENDING-004",
                "text": "Autonomous flight with VIO, SLAM, PX4, or independent observer-pose estimation.",
                "reason": "The mission simulation assumes a known local observer pose and map.",
            },
        ],
    }


def failure_gallery(repo_root: Path) -> list[dict[str, Any]]:
    g6 = load_json(repo_root / "ghost_sim_ros2/docs/GHOST_X_G6_CONSISTENCY.json")
    g8 = load_json(repo_root / "ghost_sim_ros2/docs/GHOST_X_G8_FAULT_REPORT.json")
    g9 = load_json(repo_root / "ghost_sim_ros2/docs/GHOST_X_G9_RUNTIME_REPORT.json")
    gallery = [
        {
            "id": "FAIL-CONSISTENCY-001",
            "category": "covariance_consistency",
            "observation": "The CV and estimator position NEES means are outside the pooled textbook mean interval on the frozen campaign.",
            "evidence": "GHOST_X_G6_CONSISTENCY.json",
            "disposition": "Reported as model mismatch/qualification rather than tuning the result away; physical NEES remains invalid until defensible truth exists.",
            "values": {
                "cv_position_nees_mean": g6.get("pooled", {}).get("cv", {}).get("position_nees", {}).get("mean"),
                "imm_position_nees_mean": g6.get("pooled", {}).get("formal_imm", {}).get("position_nees", {}).get("mean"),
                "mh_position_nees_mean": g6.get("pooled", {}).get("ghost_mh", {}).get("position_nees", {}).get("mean"),
            },
        },
        {
            "id": "FAIL-MULTIMODAL-NIS-001",
            "category": "invalid_statistic",
            "observation": "A single formal NIS is not valid for the non-Gaussian GHOST-MH mixture during multimodal intervals.",
            "evidence": "GHOST_X_G6_CONSISTENCY.json",
            "disposition": "The report emits INVALID_WITH_REASON and uses only qualified moment-matched diagnostics.",
        },
        {
            "id": "FAIL-PHYSICAL-CAMPAIGN-001",
            "category": "incomplete_evidence",
            "observation": "The formal measurement-characterization and controlled physical truth campaigns are not yet collected.",
            "evidence": "GHOST_X_G3_READINESS.json",
            "disposition": "Software is frozen and ready; public physical-accuracy claims remain prohibited until operator-assisted collection is complete.",
        },
    ]
    for trial in g8.get("trials", []):
        gallery.append(
            {
                "id": f"FAULT-{str(trial.get('fault', '')).upper().replace('_', '-')}",
                "category": "fault_injection",
                "observation": f"Injected {trial.get('fault')} produced {trial.get('expected_status')}.",
                "evidence": f"g8_fault_evidence/{trial.get('fault')}.jsonl",
                "disposition": "Detection, isolation, recovery, and raw evidence retained; hardware reproduction remains qualified where applicable.",
                "recovery_time_s": trial.get("recovery_time_s"),
            }
        )
    requirements = g9.get("requirements", {})
    if requirements:
        for requirement_id, result in requirements.items():
            if not result.get("passed", False):
                gallery.append(
                    {
                        "id": f"FAIL-{requirement_id}",
                        "category": "runtime_requirement",
                        "observation": result.get("summary", "Runtime requirement not met on the bench run."),
                        "evidence": "GHOST_X_G9_RUNTIME_REPORT.json",
                        "disposition": "Hard-real-time/performance wording is withheld; raw worst-case evidence remains public.",
                    }
                )
    return gallery


def create_reproducible_tar(repo_root: Path, output_path: Path, include_paths: Iterable[str]) -> dict[str, Any]:
    names = sorted(set(str(name) for name in include_paths))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name in names:
            path = repo_root / name
            if not path.is_file():
                continue
            data = path.read_bytes()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    raw.seek(0)
    with output_path.open("wb") as destination:
        with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as compressed:
            compressed.write(raw.getvalue())
    return {
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "sha256": sha256_file(output_path),
        "included_paths": names,
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
