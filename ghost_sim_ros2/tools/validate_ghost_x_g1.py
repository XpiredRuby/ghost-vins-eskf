#!/usr/bin/env python3
"""Validate GHOST-X G1 requirements, tests, claims, and traceability."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping in {path}")
    return value


def unique_index(rows: list[dict[str, Any]], kind: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        row_id = str(row.get("id", "")).strip()
        if not row_id:
            errors.append(f"{kind} missing id")
            continue
        if row_id in index:
            errors.append(f"duplicate {kind} id: {row_id}")
            continue
        index[row_id] = row
    return index, errors


def validate(
    requirements_doc: dict[str, Any],
    tests_doc: dict[str, Any],
    claims_doc: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    errors: list[str] = []
    warnings: list[str] = []

    requirements, req_errors = unique_index(requirements_doc.get("requirements", []), "requirement")
    tests, test_errors = unique_index(tests_doc.get("tests", []), "test")
    claims, claim_errors = unique_index(claims_doc.get("claims", []), "claim")
    errors.extend(req_errors + test_errors + claim_errors)

    test_to_requirements: dict[str, list[str]] = defaultdict(list)
    req_to_claims: dict[str, list[str]] = defaultdict(list)
    test_to_claims: dict[str, list[str]] = defaultdict(list)

    required_req_fields = ["title", "text", "verification", "tests", "phase"]
    for req_id, req in requirements.items():
        for field in required_req_fields:
            if field not in req or req[field] in (None, "", []):
                errors.append(f"{req_id} missing required field {field}")
        for test_id in req.get("tests", []):
            if test_id not in tests:
                errors.append(f"{req_id} references unknown test {test_id}")
            else:
                test_to_requirements[test_id].append(req_id)

    for test_id, test in tests.items():
        for field in ["title", "phase", "method", "evidence"]:
            if field not in test or test[field] in (None, "", []):
                errors.append(f"{test_id} missing required field {field}")
        if test_id not in test_to_requirements:
            warnings.append(f"{test_id} is not referenced by a requirement")

    allowed_claim_status = {"approved", "qualified", "future_gate"}
    for claim_id, claim in claims.items():
        status = claim.get("status")
        if status not in allowed_claim_status:
            errors.append(f"{claim_id} has invalid status {status}")
        if not claim.get("text"):
            errors.append(f"{claim_id} missing text")
        claim_requirements = claim.get("requirements", [])
        claim_tests = claim.get("tests", [])
        if not claim_requirements:
            errors.append(f"{claim_id} has no requirement mapping")
        if not claim_tests:
            errors.append(f"{claim_id} has no test mapping")
        for req_id in claim_requirements:
            if req_id not in requirements:
                errors.append(f"{claim_id} references unknown requirement {req_id}")
            else:
                req_to_claims[req_id].append(claim_id)
        for test_id in claim_tests:
            if test_id not in tests:
                errors.append(f"{claim_id} references unknown test {test_id}")
            else:
                test_to_claims[test_id].append(claim_id)
        if status in {"approved", "qualified"} and not claim.get("evidence"):
            errors.append(f"{claim_id} is {status} but has no evidence")
        if status in {"qualified", "future_gate"} and not claim.get("limitation"):
            errors.append(f"{claim_id} requires an explicit limitation")

    traceability_rows: list[dict[str, str]] = []
    for req_id in sorted(requirements):
        req = requirements[req_id]
        mapped_claims = sorted(req_to_claims.get(req_id, []))
        for test_id in req.get("tests", []):
            test = tests.get(test_id, {})
            traceability_rows.append(
                {
                    "requirement_id": req_id,
                    "requirement_title": str(req.get("title", "")),
                    "phase": str(req.get("phase", "")),
                    "verification_method": str(req.get("verification", "")),
                    "test_id": str(test_id),
                    "test_title": str(test.get("title", "")),
                    "planned_evidence": str(test.get("evidence", "")),
                    "mapped_claims": ";".join(mapped_claims),
                    "status": "PLANNED",
                }
            )

    report = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "project": "GHOST-X",
        "phase": "G1_REQUIREMENTS_AND_VNV",
        "passed": not errors,
        "counts": {
            "requirements": len(requirements),
            "tests": len(tests),
            "claims": len(claims),
            "traceability_rows": len(traceability_rows),
            "nominal_scenarios": len(tests_doc.get("nominal_scenarios", [])),
            "fault_scenarios": len(tests_doc.get("fault_scenarios", [])),
        },
        "errors": errors,
        "warnings": warnings,
        "unmapped_requirements_to_claims": sorted(
            req_id for req_id in requirements if req_id not in req_to_claims
        ),
        "claim_status_counts": {
            status: sum(1 for claim in claims.values() if claim.get("status") == status)
            for status in sorted(allowed_claim_status)
        },
    }
    return report, traceability_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--traceability", type=Path, required=True)
    args = parser.parse_args()

    report, rows = validate(
        load_yaml(args.requirements), load_yaml(args.tests), load_yaml(args.claims)
    )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    args.traceability.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "requirement_id",
        "requirement_title",
        "phase",
        "verification_method",
        "test_id",
        "test_title",
        "planned_evidence",
        "mapped_claims",
        "status",
    ]
    with args.traceability.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(report["counts"], sort_keys=True))
    print(f"passed={report['passed']}")
    if report["errors"]:
        for error in report["errors"]:
            print(f"ERROR: {error}")
        return 1
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
