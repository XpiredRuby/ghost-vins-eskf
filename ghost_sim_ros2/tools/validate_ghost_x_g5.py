#!/usr/bin/env python3
"""Validate the GHOST-X C++ estimator library and Python equivalence evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def validate(repo_root: Path, build_dir: Path, sanitizer_log: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    eq_path = repo_root / "ghost_sim_ros2/docs/GHOST_X_G5_EQUIVALENCE.json"
    equivalence = load_json(eq_path)
    regular_test_binary = build_dir / "ghost_x_cpp_tests"
    cli = build_dir / "ghost_x_estimator_cli"
    config = repo_root / "ghost_sim_ros2/cpp/ghost_x_estimators/config/default_estimator.cfg"

    errors: list[str] = []
    if equivalence.get("passed") is not True:
        errors.append("Python/C++ equivalence report is not passing")
    if int(equivalence.get("canonical_trials", 0)) < 24:
        errors.append("equivalence report covers fewer than 24 canonical trials")
    for name in ("cv", "imm", "mh"):
        result = equivalence.get("estimators", {}).get(name, {})
        if result.get("passed") is not True:
            errors.append(f"{name} equivalence failed")
    if not regular_test_binary.is_file():
        errors.append("C++ test binary missing")
    if not cli.is_file():
        errors.append("C++ replay CLI missing")
    if not config.is_file():
        errors.append("deterministic configuration missing")

    sanitizer_text = sanitizer_log.read_text(encoding="utf-8", errors="replace") if sanitizer_log.is_file() else ""
    sanitizer_summary = {
        "log": str(sanitizer_log),
        "present": sanitizer_log.is_file(),
        "all_tests_passed": "[  PASSED  ] 10 tests." in sanitizer_text,
        "asan_error": bool(re.search(r"ERROR: AddressSanitizer|AddressSanitizer:DEADLYSIGNAL", sanitizer_text)),
        "ubsan_error": "runtime error:" in sanitizer_text,
    }
    if not sanitizer_summary["present"]:
        errors.append("sanitizer test log missing")
    elif not sanitizer_summary["all_tests_passed"]:
        errors.append("sanitizer test suite did not finish with 10 passing tests")
    if sanitizer_summary["asan_error"]:
        errors.append("AddressSanitizer reported an error")
    if sanitizer_summary["ubsan_error"]:
        errors.append("UndefinedBehaviorSanitizer reported an error")

    maxima = {
        key: {
            "state_abs": float(value.get("max_state_absolute_difference", float("inf"))),
            "covariance_abs": float(value.get("max_covariance_absolute_difference", float("inf"))),
        }
        for key, value in equivalence.get("estimators", {}).items()
    }
    report = {
        "schema_version": 1,
        "phase": "G5_MODERN_CPP_ESTIMATOR_LIBRARY",
        "passed": not errors,
        "errors": errors,
        "cpp_tests": 10,
        "canonical_trials": int(equivalence.get("canonical_trials", 0)),
        "estimators": sorted(equivalence.get("estimators", {}).keys()),
        "equivalence_maxima": maxima,
        "sanitizers": sanitizer_summary,
        "configuration": str(config),
        "claims_boundary": (
            "Numerical equivalence is limited to the pinned canonical streams, deterministic configuration, "
            "compiler/toolchain, and declared elementwise tolerances. It is not physical validation."
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--sanitizer-log", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.repo_root, args.build_dir, args.sanitizer_log)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "cpp_tests": report["cpp_tests"], "canonical_trials": report["canonical_trials"]}))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
