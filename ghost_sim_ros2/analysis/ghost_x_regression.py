"""Deterministic replay hashing and acceptance-band validation for GHOST-X."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import yaml


def load_acceptance(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("G10 acceptance configuration must be a mapping")
    required = {"canonical", "acceptance_bands", "replay", "ci"}
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"G10 acceptance configuration missing: {missing}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def deterministic_manifest(
    campaign_dir: Path,
    subtrees: Iterable[str],
    root_files: Iterable[str],
) -> dict[str, Any]:
    root = campaign_dir.resolve()
    files: dict[str, str] = {}
    for subtree in subtrees:
        directory = root / str(subtree)
        if not directory.is_dir():
            raise ValueError(f"deterministic subtree missing: {directory}")
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            files[str(path.relative_to(root))] = sha256_file(path)
    for name in root_files:
        path = root / str(name)
        if not path.is_file():
            raise ValueError(f"deterministic root file missing: {path}")
        files[str(path.relative_to(root))] = sha256_file(path)
    combined = hashlib.sha256()
    for relative, digest in sorted(files.items()):
        combined.update(relative.encode("utf-8"))
        combined.update(b"\0")
        combined.update(digest.encode("ascii"))
        combined.update(b"\n")
    return {
        "campaign_dir": str(root),
        "file_count": len(files),
        "tree_sha256": f"sha256:{combined.hexdigest()}",
        "files": files,
    }


def compare_manifests(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    first_files = dict(first.get("files", {}))
    second_files = dict(second.get("files", {}))
    names = sorted(set(first_files) | set(second_files))
    differences = []
    for name in names:
        left = first_files.get(name)
        right = second_files.get(name)
        if left != right:
            differences.append({"path": name, "first": left, "second": right})
    return {
        "identical": not differences,
        "first_tree_sha256": first.get("tree_sha256"),
        "second_tree_sha256": second.get("tree_sha256"),
        "difference_count": len(differences),
        "differences": differences,
    }


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _check(condition: bool, check_id: str, actual: Any, expected: Any, details: str = "") -> dict[str, Any]:
    return {
        "id": check_id,
        "passed": bool(condition),
        "actual": actual,
        "expected": expected,
        "details": details,
    }


def validate_g4_manifest(manifest: dict[str, Any], acceptance: dict[str, Any]) -> list[dict[str, Any]]:
    canonical = acceptance["canonical"]
    bands = acceptance["acceptance_bands"]
    checks = [
        _check(int(manifest.get("planned_trials", -1)) == int(canonical["planned_trials"]), "G4_PLANNED_TRIALS", manifest.get("planned_trials"), canonical["planned_trials"]),
        _check(int(manifest.get("accepted_trials", -1)) == int(canonical["accepted_trials"]), "G4_ACCEPTED_TRIALS", manifest.get("accepted_trials"), canonical["accepted_trials"]),
        _check(int(manifest.get("invalid_trials", -1)) == int(canonical["invalid_trials"]), "G4_INVALID_TRIALS", manifest.get("invalid_trials"), canonical["invalid_trials"]),
        _check(len(manifest.get("scenario_families", [])) == int(canonical["scenario_families"]), "G4_SCENARIO_FAMILIES", len(manifest.get("scenario_families", [])), canonical["scenario_families"]),
        _check(len(manifest.get("estimators", [])) == int(canonical["estimators"]), "G4_ESTIMATORS", len(manifest.get("estimators", [])), canonical["estimators"]),
    ]
    overall = manifest.get("aggregate", {}).get("overall", {}).get("estimators", {})
    for estimator, maximum in bands["overall_position_rmse_m_max"].items():
        actual = overall.get(estimator, {}).get("position_rmse_m", {}).get("mean")
        checks.append(
            _check(
                _finite(actual) and float(actual) <= float(maximum),
                f"G4_{estimator.upper()}_POSITION_RMSE",
                actual,
                {"max": maximum},
            )
        )
    for estimator, maximum in bands["overall_hidden_position_rmse_m_max"].items():
        actual = overall.get(estimator, {}).get("hidden_position_rmse_m", {}).get("mean")
        checks.append(
            _check(
                _finite(actual) and float(actual) <= float(maximum),
                f"G4_{estimator.upper()}_HIDDEN_RMSE",
                actual,
                {"max": maximum},
            )
        )
    identical = True
    for trial in manifest.get("trials", []):
        hashes = list((trial.get("estimator_input_sha256") or {}).values())
        if trial.get("status") == "accepted" and (not hashes or len(set(hashes)) != 1):
            identical = False
            break
    checks.append(_check(identical, "G4_IDENTICAL_ESTIMATOR_INPUTS", identical, True))
    return checks


def validate_g5(report: dict[str, Any], acceptance: dict[str, Any]) -> list[dict[str, Any]]:
    bands = acceptance["acceptance_bands"]
    checks = [
        _check(report.get("passed") is True, "G5_REPORT_PASS", report.get("passed"), True),
        _check(int(report.get("canonical_trials", 0)) >= int(acceptance["canonical"]["planned_trials"]), "G5_CANONICAL_TRIALS", report.get("canonical_trials"), {"min": acceptance["canonical"]["planned_trials"]}),
    ]
    for estimator, result in report.get("estimators", {}).items():
        state = result.get("max_state_absolute_difference")
        covariance = result.get("max_covariance_absolute_difference")
        checks.append(_check(_finite(state) and float(state) <= float(bands["g5_max_state_absolute_difference"]), f"G5_{estimator.upper()}_STATE_EQUIVALENCE", state, {"max": bands["g5_max_state_absolute_difference"]}))
        checks.append(_check(_finite(covariance) and float(covariance) <= float(bands["g5_max_covariance_absolute_difference"]), f"G5_{estimator.upper()}_COVARIANCE_EQUIVALENCE", covariance, {"max": bands["g5_max_covariance_absolute_difference"]}))
    return checks


def validate_pinned_reports(docs_dir: Path, acceptance: dict[str, Any]) -> list[dict[str, Any]]:
    bands = acceptance["acceptance_bands"]
    g6 = load_json(docs_dir / "GHOST_X_G6_CONSISTENCY.json")
    g7 = load_json(docs_dir / "GHOST_X_G7_TRADE_STUDY.json")
    g8 = load_json(docs_dir / "GHOST_X_G8_FAULT_REPORT.json")
    g9 = load_json(docs_dir / "GHOST_X_G9_RUNTIME_REPORT.json")
    g11 = load_json(docs_dir / "GHOST_X_G11_FIXED_LAG.json")
    checks = [
        _check(int(g6.get("canonical_trials", 0)) == int(bands["g6_canonical_trials"]), "G6_CANONICAL_TRIALS", g6.get("canonical_trials"), bands["g6_canonical_trials"]),
        _check(g6.get("pooled", {}).get("ghost_mh", {}).get("nis", {}).get("valid") is False, "G6_MH_NIS_VALIDITY_BOUNDARY", g6.get("pooled", {}).get("ghost_mh", {}).get("nis"), {"valid": False}),
        _check(int(g7.get("imm", {}).get("candidate_count", 0)) == int(bands["g7_imm_candidates"]), "G7_IMM_CANDIDATES", g7.get("imm", {}).get("candidate_count"), bands["g7_imm_candidates"]),
        _check(int(g7.get("ghost_mh", {}).get("candidate_count", 0)) == int(bands["g7_mh_candidates"]), "G7_MH_CANDIDATES", g7.get("ghost_mh", {}).get("candidate_count"), bands["g7_mh_candidates"]),
        _check(g7.get("imm", {}).get("selected", {}).get("valid") is True, "G7_IMM_SELECTION_VALID", g7.get("imm", {}).get("selected", {}).get("valid"), True),
        _check(g7.get("ghost_mh", {}).get("selected", {}).get("valid") is True, "G7_MH_SELECTION_VALID", g7.get("ghost_mh", {}).get("selected", {}).get("valid"), True),
        _check(int(g8.get("fault_count", 0)) == int(bands["g8_faults"]), "G8_FAULT_COUNT", g8.get("fault_count"), bands["g8_faults"]),
        _check(int(g8.get("passed_faults", 0)) == int(bands["g8_passed_faults"]), "G8_PASSED_FAULTS", g8.get("passed_faults"), bands["g8_passed_faults"]),
        _check(g8.get("passed") is True, "G8_REPORT_PASS", g8.get("passed"), True),
        _check(len(g9.get("qos_scenarios", [])) == int(bands["g9_qos_scenarios"]), "G9_QOS_SCENARIOS", len(g9.get("qos_scenarios", [])), bands["g9_qos_scenarios"]),
        _check(int(g9.get("qos_passed_count", 0)) == int(bands["g9_qos_passed"]), "G9_QOS_PASSED", g9.get("qos_passed_count"), bands["g9_qos_passed"]),
        _check(g9.get("campaign_completed") is True, "G9_CAMPAIGN_COMPLETED", g9.get("campaign_completed"), True),
        _check(
            isinstance(g9.get("estimator_deadline", {}).get("all_max_below_deadline"), bool)
            and abs(float(g9.get("estimator_deadline", {}).get("deadline_ms", 0.0)) - float(bands["g9_estimator_deadline_ms"])) <= 1.0e-6
            and bool(g9.get("estimator_deadline", {}).get("rows")),
            "G9_ESTIMATOR_DEADLINE_REPORTED",
            {
                "all_max_below_deadline": g9.get("estimator_deadline", {}).get("all_max_below_deadline"),
                "deadline_ms": g9.get("estimator_deadline", {}).get("deadline_ms"),
                "row_count": len(g9.get("estimator_deadline", {}).get("rows", [])),
            },
            {"deadline_ms": bands["g9_estimator_deadline_ms"], "result_may_pass_or_fail_but_must_be_reported": True},
        ),
        _check(g9.get("requirements", {}).get("RT-003", {}).get("passed") is True, "G9_RESOURCE_THERMAL_REQUIREMENT", g9.get("requirements", {}).get("RT-003", {}).get("passed"), True),
        _check(
            (g9.get("requirements_all_passed") is True and str(g9.get("real_time_claim_status", "")).startswith("BENCH_REQUIREMENTS_MET"))
            or (g9.get("requirements_all_passed") is False and str(g9.get("real_time_claim_status", "")).startswith("HARD_REAL_TIME_NOT_CLAIMED")),
            "G9_CLAIM_STATUS_MATCHES_REQUIREMENTS",
            {"requirements_all_passed": g9.get("requirements_all_passed"), "claim_status": g9.get("real_time_claim_status")},
            "Claim status must withhold hard-real-time wording whenever a runtime requirement fails.",
        ),
        _check(int(g11.get("ablation_count", 0)) == int(bands["g11_ablation_candidates"]), "G11_ABLATION_COUNT", g11.get("ablation_count"), bands["g11_ablation_candidates"]),
        _check(g11.get("classical_baseline_retained") is True, "G11_CLASSICAL_BASELINE", g11.get("classical_baseline_retained"), True),
        _check(bool(g11.get("frozen_evaluation", {}).get("fixed_lag", {}).get("valid")), "G11_FROZEN_EVALUATION_VALID", g11.get("frozen_evaluation", {}).get("fixed_lag", {}).get("valid"), True),
        _check(bool(g11.get("out_of_distribution", {}).get("fixed_lag", {}).get("valid")), "G11_OOD_VALID", g11.get("out_of_distribution", {}).get("fixed_lag", {}).get("valid"), True),
    ]
    return checks


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [check for check in checks if not check["passed"]]
    return {
        "passed": not failed,
        "check_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "failed_checks": failed,
        "checks": checks,
    }
