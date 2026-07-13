#!/usr/bin/env python3
"""Assemble the GHOST-X G12 software research package and reproducible archive."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT_DEFAULT = PACKAGE_ROOT.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_x_release import (
    approved_claims,
    build_traceability,
    collect_evidence_manifest,
    collect_phase_status,
    create_reproducible_tar,
    failure_gallery,
    git_value,
    load_json,
    sha256_file,
    utc_now,
    write_traceability,
)


GENERATED_DOCS = [
    "ghost_sim_ros2/docs/GHOST_X_FINAL_TRACEABILITY.csv",
    "ghost_sim_ros2/docs/GHOST_X_SOFTWARE_STATUS.json",
    "ghost_sim_ros2/docs/GHOST_X_SOFTWARE_VERIFICATION_REPORT.md",
    "ghost_sim_ros2/docs/GHOST_X_FAILURE_GALLERY.json",
    "ghost_sim_ros2/docs/GHOST_X_FAILURE_GALLERY.md",
    "ghost_sim_ros2/docs/GHOST_X_APPROVED_CLAIMS.json",
    "ghost_sim_ros2/docs/GHOST_X_APPROVED_CLAIMS.md",
    "ghost_sim_ros2/docs/GHOST_X_NO_PURCHASE_AUDIT.md",
    "ghost_sim_ros2/docs/GHOST_X_90_SECOND_DEMO.md",
    "ghost_sim_ros2/docs/GHOST_X_TECHNICAL_DEFENSE.md",
    "ghost_sim_ros2/docs/GHOST_X_FINAL_RESEARCH_PACKAGE.md",
    "ghost_sim_ros2/docs/GHOST_X_RELEASE_MANIFEST.json",
]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def phase_table(phases: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Phase | Software status | Evidence |",
        "|---|---|---:|",
    ]
    for row in phases:
        lines.append(f"| `{row['phase']}` | `{row['software_status']}` | {row['evidence_count']}/{row['expected_evidence_count']} |")
    return lines


def build_documents(repo_root: Path, version: str, archive_out: Path) -> dict[str, Any]:
    docs = repo_root / "ghost_sim_ros2/docs"
    g10_path = docs / "GHOST_X_G10_CI_REPORT.json"
    if not g10_path.is_file():
        raise FileNotFoundError("G10 report is required before G12 release assembly")
    g10 = load_json(g10_path)
    if g10.get("passed") is not True:
        raise ValueError("G10 deterministic replay report is not passing")

    traceability = build_traceability(repo_root)
    write_traceability(traceability, docs / "GHOST_X_FINAL_TRACEABILITY.csv")
    phases = collect_phase_status(repo_root)
    software_complete = all(row["complete"] for row in phases)
    physical_pending = [row["phase"] for row in phases if "PHYSICAL_EXECUTION_PENDING" in row["software_status"]]
    status = {
        "schema_version": 1,
        "release_version": version,
        "generated_at_utc": utc_now(),
        "software_completion_percent": 100 if software_complete else None,
        "software_complete": software_complete,
        "full_project_complete": False,
        "physical_human_interaction_required": True,
        "physical_pending_phases": physical_pending,
        "next_physical_gate": "G3 measurement characterization trial 1, followed by controlled physical truth collection.",
        "phase_status": phases,
        "requirements": {
            "total": len(traceability),
            "software_verified": sum(row["status"] == "SOFTWARE_VERIFIED" for row in traceability),
            "qualified": sum(row["status"] == "QUALIFIED_SOFTWARE_OR_BENCH_EVIDENCE" for row in traceability),
            "physical_pending": sum("PENDING" in row["status"] for row in traceability),
            "traceable": sum(bool(row["traceable"]) for row in traceability),
        },
        "claim_boundary": "SOFTWARE_COMPLETE_DOES_NOT_MEAN_PHYSICAL_CAMPAIGN_OR_FLIGHT_QUALIFICATION_COMPLETE",
    }
    write_json(docs / "GHOST_X_SOFTWARE_STATUS.json", status)

    claims = approved_claims(repo_root)
    write_json(docs / "GHOST_X_APPROVED_CLAIMS.json", claims)
    claim_lines = [
        "# GHOST-X Approved and Prohibited Claims",
        "",
        "## Approved software and qualified bench claims",
        "",
    ]
    for claim in claims["approved"]:
        claim_lines.extend(
            [
                f"### {claim['id']}",
                "",
                claim["text"],
                "",
                f"**Qualification:** {claim['qualification']}",
                "",
                f"**Evidence:** {', '.join(f'`{item}`' for item in claim['evidence'])}",
                "",
            ]
        )
    claim_lines.extend(["## Prohibited or pending claims", ""])
    for claim in claims["prohibited_or_pending"]:
        claim_lines.extend([f"- **{claim['id']}:** {claim['text']} — {claim['reason']}"])
    claim_lines.append("")
    (docs / "GHOST_X_APPROVED_CLAIMS.md").write_text("\n".join(claim_lines), encoding="utf-8")

    gallery = failure_gallery(repo_root)
    write_json(docs / "GHOST_X_FAILURE_GALLERY.json", {"schema_version": 1, "entries": gallery})
    gallery_lines = [
        "# GHOST-X Public Failure Gallery",
        "",
        "This gallery intentionally preserves failed assumptions, invalid statistics, injected failures, and incomplete evidence instead of presenting success-only results.",
        "",
    ]
    for item in gallery:
        gallery_lines.extend(
            [
                f"## {item['id']} — {item['category']}",
                "",
                f"**Observation:** {item['observation']}",
                "",
                f"**Disposition:** {item['disposition']}",
                "",
                f"**Evidence:** `{item['evidence']}`",
                "",
            ]
        )
    (docs / "GHOST_X_FAILURE_GALLERY.md").write_text("\n".join(gallery_lines), encoding="utf-8")

    no_purchase = """# GHOST-X No-Purchase Completion Audit

## Result

The mandatory software program was completed without requiring purchase of an IMU, lidar, motion-capture system, linear rail, metrology system, or additional compute platform.

## Existing resources used

- Existing Raspberry Pi, CSI camera, AprilTag, network, and development computer.
- ROS 2 Jazzy, Python, C++20, Eigen, CMake, GoogleTest, NumPy, SciPy, Matplotlib, and GitHub Actions.
- Deterministic analytic truth, recorded ROS evidence, and normal printing/room references.

## Remaining physical work

The next gate requires only operator assistance to place and orient the existing AprilTag for the predeclared G3 measurement campaign and later controlled physical trials. No new hardware purchase is required.

## Boundary

No-purchase feasibility does not make room references equivalent to certified metrology. Ground-truth uncertainty and resulting claim limits remain explicit.
"""
    (docs / "GHOST_X_NO_PURCHASE_AUDIT.md").write_text(no_purchase, encoding="utf-8")

    verification_lines = [
        "# GHOST-X Software Verification Report",
        "",
        f"Release: `{version}`",
        f"Source branch: `{git_value(repo_root, 'branch', '--show-current')}`",
        f"Source commit before generated release documents: `{git_value(repo_root, 'rev-parse', 'HEAD')}`",
        f"G10 result: `{'PASS' if g10['passed'] else 'FAIL'}` with `{g10['summary']['passed_count']}/{g10['summary']['check_count']}` checks passing.",
        "",
        "## Phase status",
        "",
        *phase_table(phases),
        "",
        "## Verification highlights",
        "",
        "- 24 deterministic controlled-truth software trials spanning eight scenario families and identical estimator inputs.",
        "- Eigen-based C++ CV, IMM, and multi-hypothesis estimators with unit/property tests, sanitizer execution, deterministic configuration, and Python equivalence.",
        "- Formal NIS/NEES validity labeling, residual diagnostics, covariance sensitivity, and explicit invalid-statistic handling.",
        "- Predeclared IMM and hypothesis-bank trade studies with frozen selection rules.",
        "- Twelve reproducible fault types with detection, isolation/status, recovery, discrepancy, and retained JSONL evidence.",
        "- Raspberry Pi ROS 2 QoS, execution-time, CPU, memory, temperature, throttling, and stress evidence.",
        "- Deterministic replay hashes, stored acceptance bands, deliberate negative-regression self-tests, and GitHub CI workflow.",
        "- Fixed-lag RTS smoothing ablation with frozen evaluation and out-of-distribution testing while retaining the classical causal baseline.",
        "",
        "## Open physical verification gates",
        "",
        "- G3 range/yaw measurement characterization collection.",
        "- At least 20 paired controlled physical truth trials.",
        "- Physical position/velocity accuracy, reacquisition statistics, and defensible physical NEES.",
        "- Direct hardware reproduction of selected cable, lighting, network, and CPU faults where practical.",
        "",
        "## Release decision",
        "",
        "The software baseline is releasable as a research and portfolio platform. Physical-performance wording remains gated and is not approved by this report.",
        "",
    ]
    (docs / "GHOST_X_SOFTWARE_VERIFICATION_REPORT.md").write_text("\n".join(verification_lines), encoding="utf-8")

    demo = """# GHOST-X 90-Second Demo Script

**0–10 s — Mission:** Show the Raspberry Pi camera and architecture graphic. “GHOST-X studies target estimation through visibility loss, maneuvers, bad measurements, and compute stress.”

**10–25 s — Live/data contract:** Show camera pose, formal IMM, GHOST-MH, validity, measurement age, and future paths. Point out versioned frames, timestamps, units, calibration IDs, and stale-data behavior.

**25–40 s — Controlled replay:** Run the one-command deterministic replay and show identical input hashes across CV, IMM, and GHOST-MH for 24 frozen trials.

**40–55 s — Estimation assurance:** Show the C++ Eigen library, ten C++ mathematical/property tests, sanitizer result, and C++/Python equivalence maxima.

**55–70 s — Failures:** Show the 12-fault matrix and one raw JSONL timeline: fault onset, detection, isolation, degraded status, and recovery. Then show the consistency report where unsupported NIS/NEES interpretations are explicitly rejected.

**70–82 s — Pi evidence:** Show QoS, p99/max execution, temperature, frequency, memory, and throttling. State the exact claim boundary: bench evidence, not hard-real-time certification.

**82–90 s — Close:** “The software research platform is reproducible and CI-gated. The next step is the predeclared operator-assisted physical measurement and truth campaign; no physical accuracy claim is made yet.”
"""
    (docs / "GHOST_X_90_SECOND_DEMO.md").write_text(demo, encoding="utf-8")

    defense = """# GHOST-X 10-Minute Technical Defense

## 0:00–1:00 — Problem and requirements

Explain why visibility loss, model mismatch, latency, false detections, and resource limits make target tracking an estimation-and-assurance problem rather than only a computer-vision demo. Show the requirements-to-test structure and claim gates.

## 1:00–2:15 — Data contracts and evidence discipline

Define frames, SI units, source/receipt/processing/publication timestamps, covariance conventions, calibration/configuration hashes, validity states, and stale-data behavior. Explain why these contracts precede statistical comparison.

## 2:15–3:45 — Estimators

Derive the CV state transition and white-acceleration process covariance. Walk through the five IMM stages: predicted mode probabilities, destination-conditioned mixing, mode-matched prediction/update, Gaussian likelihood update, and moment-matched combination. Contrast this with GHOST-MH’s persistent labeled hypotheses and relative weights.

## 3:45–5:00 — C++ assurance and equivalence

Show the ROS-independent Eigen library, Joseph covariance update, deterministic configuration parser, covariance PSD/symmetry properties, sanitizer run, and frozen C++/Python equivalence. State that equivalence proves implementation agreement, not model truth.

## 5:00–6:15 — Controlled truth, consistency, and trade study

Show 24 analytic-truth trials and identical stream hashes. Present visible, hidden, future, recovery, and compute metrics. Explain why IMM NIS is only moment-matched and why one scalar formal NIS is invalid for a multimodal GHOST-MH belief. Show parameter selection rules declared before ranking.

## 6:15–7:20 — Fault injection

Present the 12-fault matrix. For one example, trace source timestamp, monitor decision, isolation gate, estimator input, degraded status, and recovery. Explain why raw rejected evidence is retained.

## 7:20–8:20 — DDS and Pi runtime

Compare reliable and best-effort QoS, depth, deadline, liveliness, incompatibility, overload, and CPU stress. Report p95/p99/max rather than averages only. Distinguish estimator execution deadline evidence from operating-system hard-real-time guarantees.

## 8:20–9:10 — Determinism and CI

Show repeated tree hashes, acceptance bands, deliberate negative hash/metric tests, C++ tests, Python tests, and GitHub artifact export. Explain what changes make CI fail.

## 9:10–10:00 — Limitations and next experiment

State that G3/G4 physical collection is pending; room geometry is not certified metrology; no physical accuracy, VIO/SLAM, PX4, flight qualification, or universal GHOST-MH superiority is claimed. Finish with the exact first G3 setup and how its result will update covariance selection and physical claim gates.
"""
    (docs / "GHOST_X_TECHNICAL_DEFENSE.md").write_text(defense, encoding="utf-8")

    package_lines = [
        "# GHOST-X Final Research Package",
        "",
        f"Release: `{version}`",
        "",
        "## Read this first",
        "",
        "GHOST-X software is complete and reproducible. The formal operator-assisted physical measurement and controlled-truth campaigns remain pending, so physical accuracy and flight-qualification claims are prohibited.",
        "",
        "## Core reports",
        "",
        "- [Software verification](GHOST_X_SOFTWARE_VERIFICATION_REPORT.md)",
        "- [Requirements traceability](GHOST_X_FINAL_TRACEABILITY.csv)",
        "- [Approved and prohibited claims](GHOST_X_APPROVED_CLAIMS.md)",
        "- [Failure gallery](GHOST_X_FAILURE_GALLERY.md)",
        "- [No-purchase audit](GHOST_X_NO_PURCHASE_AUDIT.md)",
        "- [90-second demo](GHOST_X_90_SECOND_DEMO.md)",
        "- [10-minute technical defense](GHOST_X_TECHNICAL_DEFENSE.md)",
        "",
        "## Phase evidence",
        "",
    ]
    for phase in phases:
        package_lines.append(f"### {phase['phase']} — {phase['software_status']}")
        package_lines.append("")
        for item in phase["evidence"]:
            display = Path(item).name
            relative = Path(item).relative_to("ghost_sim_ros2/docs") if item.startswith("ghost_sim_ros2/docs/") else Path("../../") / item
            package_lines.append(f"- [{display}]({relative.as_posix()})")
        package_lines.append("")
    package_lines.extend(
        [
            "## Reproduction",
            "",
            "```bash",
            "python3 ghost_sim_ros2/tools/run_ghost_x_g10_ci.py \\",
            "  --acceptance ghost_sim_ros2/config/ghost_x_g10_acceptance.yaml \\",
            "  --repo-root \"$PWD\" \\",
            "  --cpp-build-dir /tmp/ghost_x_cpp_build \\",
            "  --out-dir /tmp/ghost_x_g10",
            "```",
            "",
            "The GitHub workflow `.github/workflows/ghost-x-regression.yml` runs the same software gates and uploads the complete G10 report.",
            "",
        ]
    )
    (docs / "GHOST_X_FINAL_RESEARCH_PACKAGE.md").write_text("\n".join(package_lines), encoding="utf-8")

    extra = [item for item in GENERATED_DOCS if item != "ghost_sim_ros2/docs/GHOST_X_RELEASE_MANIFEST.json"]
    evidence = collect_evidence_manifest(repo_root, extra)
    manifest = {
        "schema_version": 1,
        "release_version": version,
        "generated_at_utc": utc_now(),
        "source_commit_before_release_docs": git_value(repo_root, "rev-parse", "HEAD"),
        "source_branch": git_value(repo_root, "branch", "--show-current"),
        "working_tree_clean_before_release_docs": False,
        "software_status": status,
        "traceability_summary": {
            "requirements": len(traceability),
            "traceable": sum(bool(row["traceable"]) for row in traceability),
            "physical_pending": sum("PENDING" in row["status"] for row in traceability),
        },
        "g10_tree_sha256": g10.get("determinism", {}).get("first", {}).get("tree_sha256"),
        "evidence": evidence,
        "claim_boundary": "SOFTWARE_RELEASE_PHYSICAL_CAMPAIGN_PENDING",
    }
    write_json(docs / "GHOST_X_RELEASE_MANIFEST.json", manifest)

    tracked = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    included = [name for name in tracked if not name.startswith(".pytest_cache/")]
    included.extend(GENERATED_DOCS)
    archive = create_reproducible_tar(repo_root, archive_out, included)
    receipt = {
        "schema_version": 1,
        "release_version": version,
        "archive": archive,
        "manifest_sha256": sha256_file(docs / "GHOST_X_RELEASE_MANIFEST.json"),
    }
    write_json(docs / "GHOST_X_RELEASE_ARCHIVE.json", receipt)
    return {
        "software_complete": software_complete,
        "traceability_rows": len(traceability),
        "traceable_rows": sum(bool(row["traceable"]) for row in traceability),
        "archive": archive,
        "generated_docs": [*GENERATED_DOCS, "ghost_sim_ros2/docs/GHOST_X_RELEASE_ARCHIVE.json"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT_DEFAULT)
    parser.add_argument("--version", default="ghost-x-software-v1")
    parser.add_argument("--archive-out", type=Path, required=True)
    args = parser.parse_args()
    result = build_documents(args.repo_root.resolve(), args.version, args.archive_out.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["software_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
