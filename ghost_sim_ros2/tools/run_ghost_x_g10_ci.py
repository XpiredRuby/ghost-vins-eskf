#!/usr/bin/env python3
"""Run deterministic GHOST-X replay and regression gates in one command."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT_DEFAULT = PACKAGE_ROOT.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_x_consistency import analyze_campaign as analyze_consistency
from analysis.ghost_x_consistency import write_outputs as write_consistency
from analysis.ghost_x_controlled_truth import load_config as load_g4_config
from analysis.ghost_x_controlled_truth import run_campaign as run_g4_campaign
from analysis.ghost_x_fault_injection import run_campaign as run_fault_campaign
from analysis.ghost_x_fault_injection import write_outputs as write_fault_outputs
from analysis.ghost_x_regression import (
    compare_manifests,
    deterministic_manifest,
    load_acceptance,
    load_json,
    summarize_checks,
    validate_g4_manifest,
    validate_g5,
    validate_pinned_reports,
)


def run_command(argv: list[str], cwd: Path, timeout_s: float = 600.0) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return {
        "argv": argv,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-20000:],
        "stderr": completed.stderr[-20000:],
        "passed": completed.returncode == 0,
    }


def git_provenance(repo_root: Path) -> dict[str, Any]:
    def call(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    return {
        "commit": call("rev-parse", "HEAD"),
        "branch": call("branch", "--show-current"),
        "working_tree_clean": not bool(call("status", "--porcelain")),
    }


def prepare_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def make_fault_design(source: Path, destination: Path, campaign_dir: Path) -> None:
    value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("G8 design is not a mapping")
    value["source_campaign"] = str(campaign_dir.resolve())
    destination.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def write_report(report: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "GHOST_X_G10_CI_REPORT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# GHOST-X G10 Deterministic Replay and CI",
        "",
        f"Overall: `{'PASS' if report['passed'] else 'FAIL'}`",
        f"Checks: `{report['summary']['passed_count']}/{report['summary']['check_count']}`",
        f"Deterministic files: `{report['determinism']['first']['file_count']}`",
        f"Deterministic tree hash: `{report['determinism']['first']['tree_sha256']}`",
        "",
        "## Regression gates",
        "",
        "| Gate | Result | Actual | Expected |",
        "|---|---|---|---|",
    ]
    for check in report["summary"]["checks"]:
        lines.append(
            f"| `{check['id']}` | {'PASS' if check['passed'] else 'FAIL'} | "
            f"`{json.dumps(check['actual'], sort_keys=True)}` | `{json.dumps(check['expected'], sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## Command gates",
            "",
        ]
    )
    for name, command in report["commands"].items():
        lines.append(f"- `{name}`: `{'PASS' if command['passed'] else 'FAIL'}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "These gates prevent silent regression in pinned synthetic scenarios and stored Pi evidence. They do not replace controlled physical truth, measurement characterization, or flight qualification.",
            "",
        ]
    )
    (out_dir / "GHOST_X_G10_CI_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT_DEFAULT)
    parser.add_argument("--cpp-build-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--skip-python-tests", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    package_root = repo_root / "ghost_sim_ros2"
    docs_dir = package_root / "docs"
    acceptance = load_acceptance(args.acceptance)
    provenance = git_provenance(repo_root)
    prepare_directory(args.out_dir)
    replay_root = args.out_dir / "replays"
    replay_root.mkdir()
    run_one = replay_root / "run_01"
    run_two = replay_root / "run_02"
    g4_config = load_g4_config(package_root / "config/ghost_x_g4_controlled_truth.yaml")
    manifest_one = run_g4_campaign(g4_config, run_one, code_provenance=provenance)
    manifest_two = run_g4_campaign(g4_config, run_two, code_provenance=provenance)

    deterministic = acceptance["canonical"]
    deterministic_one = deterministic_manifest(
        run_one,
        deterministic["deterministic_subtrees"],
        deterministic["deterministic_root_files"],
    )
    deterministic_two = deterministic_manifest(
        run_two,
        deterministic["deterministic_subtrees"],
        deterministic["deterministic_root_files"],
    )
    comparison = compare_manifests(deterministic_one, deterministic_two)
    deliberately_changed = copy.deepcopy(deterministic_two)
    first_name = sorted(deliberately_changed["files"])[0]
    deliberately_changed["files"][first_name] = "sha256:" + "0" * 64
    negative_hash_comparison = compare_manifests(deterministic_one, deliberately_changed)

    regressed_manifest = copy.deepcopy(manifest_one)
    metric_path = regressed_manifest["aggregate"]["overall"]["estimators"]["formal_imm"]["position_rmse_m"]
    metric_path["mean"] = float(acceptance["acceptance_bands"]["overall_position_rmse_m_max"]["formal_imm"]) * 10.0
    negative_metric_checks = validate_g4_manifest(regressed_manifest, acceptance)
    negative_metric_rejected = any(
        check["id"] == "G4_FORMAL_IMM_POSITION_RMSE" and not check["passed"]
        for check in negative_metric_checks
    )

    commands: dict[str, dict[str, Any]] = {}
    commands["cpp_tests"] = run_command(
        [str(args.cpp_build_dir / "ghost_x_cpp_tests")],
        repo_root,
        timeout_s=300.0,
    )
    g5_out = args.out_dir / "GHOST_X_G5_EQUIVALENCE_REPLAY.json"
    commands["g5_equivalence"] = run_command(
        [
            sys.executable,
            str(package_root / "tools/validate_ghost_x_g5_equivalence.py"),
            "--build-dir",
            str(args.cpp_build_dir),
            "--campaign-dir",
            str(run_one),
            "--out",
            str(g5_out),
        ],
        repo_root,
        timeout_s=600.0,
    )

    consistency = analyze_consistency(run_one)
    write_consistency(consistency, args.out_dir / "g6_replay")
    fault_design = args.out_dir / "g8_replay_design.yaml"
    make_fault_design(package_root / "config/ghost_x_g8_fault_campaign.yaml", fault_design, run_one)
    fault_report = run_fault_campaign(fault_design)
    write_fault_outputs(fault_report, args.out_dir / "g8_replay")

    if args.skip_python_tests:
        commands["python_ghost_x_tests"] = {
            "passed": True,
            "returncode": 0,
            "stdout": "SKIPPED_BY_REQUEST",
            "stderr": "",
            "argv": [],
            "cwd": str(package_root),
        }
    else:
        tests = sorted(str(path.relative_to(package_root)) for path in (package_root / "test").glob("test_ghost_x_g*.py"))
        commands["python_ghost_x_tests"] = run_command(
            [sys.executable, "-m", "pytest", "-q", *tests],
            package_root,
            timeout_s=1200.0,
        )

    checks = validate_g4_manifest(manifest_one, acceptance)
    checks.append(
        {
            "id": "G10_DETERMINISTIC_REPLAY_HASHES",
            "passed": comparison["identical"],
            "actual": {
                "difference_count": comparison["difference_count"],
                "first": comparison["first_tree_sha256"],
                "second": comparison["second_tree_sha256"],
            },
            "expected": {"difference_count": 0, "tree_hashes_identical": True},
            "details": "Only predeclared deterministic artifacts are compared; timestamps and run paths are excluded.",
        }
    )
    checks.extend(
        [
            {
                "id": "G10_NEGATIVE_HASH_REGRESSION_REJECTED",
                "passed": not negative_hash_comparison["identical"] and negative_hash_comparison["difference_count"] >= 1,
                "actual": negative_hash_comparison["difference_count"],
                "expected": {"minimum_detected_differences": 1},
                "details": f"Deliberately corrupted deterministic digest for {first_name}.",
            },
            {
                "id": "G10_NEGATIVE_METRIC_REGRESSION_REJECTED",
                "passed": negative_metric_rejected,
                "actual": negative_metric_rejected,
                "expected": True,
                "details": "Deliberately inflated formal-IMM RMSE must violate the stored acceptance band.",
            },
        ]
    )
    if g5_out.is_file():
        checks.extend(validate_g5(load_json(g5_out), acceptance))
    else:
        checks.append({"id": "G5_REPLAY_REPORT_PRESENT", "passed": False, "actual": False, "expected": True, "details": ""})
    checks.extend(validate_pinned_reports(docs_dir, acceptance))
    checks.extend(
        [
            {
                "id": "G6_REPLAY_TRIAL_COUNT",
                "passed": int(consistency.get("canonical_trials", 0)) == int(acceptance["acceptance_bands"]["g6_canonical_trials"]),
                "actual": consistency.get("canonical_trials"),
                "expected": acceptance["acceptance_bands"]["g6_canonical_trials"],
                "details": "",
            },
            {
                "id": "G8_REPLAY_PASS",
                "passed": fault_report.get("passed") is True,
                "actual": {"passed": fault_report.get("passed"), "passed_faults": fault_report.get("passed_faults")},
                "expected": {"passed": True, "passed_faults": acceptance["acceptance_bands"]["g8_passed_faults"]},
                "details": "",
            },
        ]
    )
    for name, command in commands.items():
        checks.append(
            {
                "id": f"COMMAND_{name.upper()}",
                "passed": bool(command["passed"]),
                "actual": command["returncode"],
                "expected": 0,
                "details": (command.get("stderr") or command.get("stdout") or "")[-1000:],
            }
        )
    summary = summarize_checks(checks)
    report = {
        "schema_version": 1,
        "phase": "G10_DETERMINISTIC_REPLAY_AND_CI",
        "passed": summary["passed"],
        "provenance": provenance,
        "acceptance_config": str(args.acceptance.resolve()),
        "determinism": {
            "first": deterministic_one,
            "second": deterministic_two,
            "comparison": comparison,
            "negative_hash_test": negative_hash_comparison,
            "negative_metric_test_rejected": negative_metric_rejected,
        },
        "commands": commands,
        "summary": summary,
        "replay_reports": {
            "g5": str(g5_out),
            "g6": str(args.out_dir / "g6_replay/GHOST_X_G6_CONSISTENCY.json"),
            "g8": str(args.out_dir / "g8_replay/GHOST_X_G8_FAULT_REPORT.json"),
        },
        "claim_boundary": "SOFTWARE_REGRESSION_GATES_DO_NOT_REPLACE_PHYSICAL_VALIDATION",
    }
    write_report(report, args.out_dir)
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "checks": summary["check_count"],
                "failed": summary["failed_count"],
                "tree_sha256": deterministic_one["tree_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
