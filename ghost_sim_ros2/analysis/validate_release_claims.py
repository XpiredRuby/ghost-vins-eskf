"""Validate GHOST public claims against evidence classification and release readiness."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
CLASSIFICATIONS = {
    "validated",
    "hardware_behavior_only",
    "software_only",
    "pending",
    "prohibited",
}
PLACEHOLDER = re.compile(r"(?i)(<PENDING[^>]*>|\bTBD\b|\bTO BE DETERMINED\b)")
HIGH_RISK = re.compile(
    r"(?i)(flight[- ]?ready|production[- ]?ready|validated (tracking )?accuracy|centimeter[- ]level|statistically proven|outperforms)"
)


def validate_claims(matrix: dict[str, Any], *, require_all_resolved: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if matrix.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")
    claims_raw = matrix.get("claims")
    if not isinstance(claims_raw, list) or not claims_raw:
        errors.append("claims must be a non-empty list")
        claims_raw = []

    claims = {}
    ready_count = 0
    for index, claim in enumerate(claims_raw):
        where = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{where} must be an object")
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            errors.append(f"{where}.claim_id must be non-empty")
            continue
        if claim_id in claims:
            errors.append(f"duplicate claim_id: {claim_id}")
            continue
        claims[claim_id] = claim

        statement = claim.get("public_statement")
        if not isinstance(statement, str) or not statement.strip():
            errors.append(f"{claim_id}: public_statement must be non-empty")
            statement = ""
        classification = claim.get("classification")
        if classification not in CLASSIFICATIONS:
            errors.append(f"{claim_id}: unknown classification {classification!r}")
        public_ready = claim.get("public_ready")
        if not isinstance(public_ready, bool):
            errors.append(f"{claim_id}: public_ready must be boolean")
            public_ready = False
        evidence = claim.get("evidence")
        if not isinstance(evidence, list) or not all(isinstance(item, str) and item.strip() for item in evidence):
            errors.append(f"{claim_id}: evidence must be a list of non-empty strings")
            evidence = []
        limitations = claim.get("limitations")
        if not isinstance(limitations, list) or not all(
            isinstance(item, str) and item.strip() for item in limitations
        ):
            errors.append(f"{claim_id}: limitations must be a list of non-empty strings")
            limitations = []

        if public_ready:
            ready_count += 1
            if classification in {"pending", "prohibited"}:
                errors.append(f"{claim_id}: {classification} claim cannot be public_ready")
            if not evidence:
                errors.append(f"{claim_id}: public-ready claim requires evidence")
            if not limitations:
                errors.append(f"{claim_id}: public-ready claim requires limitations")
            if PLACEHOLDER.search(statement):
                errors.append(f"{claim_id}: public-ready statement contains a placeholder")
            if HIGH_RISK.search(statement) and classification != "validated":
                errors.append(
                    f"{claim_id}: high-risk wording requires validated classification and direct evidence"
                )
        else:
            if classification not in {"pending", "prohibited"}:
                warnings.append(f"{claim_id}: evidence-classified claim is not yet marked public_ready")

        if classification == "prohibited" and evidence:
            warnings.append(f"{claim_id}: prohibited claim carries evidence entries that must not promote it")
        if classification == "pending" and not PLACEHOLDER.search(statement) and evidence:
            warnings.append(f"{claim_id}: pending claim already contains evidence; review for promotion")
        if classification == "software_only" and not re.search(r"(?i)(software|simulation|SIL)", statement):
            warnings.append(f"{claim_id}: software-only statement should identify its software boundary")
        if classification == "hardware_behavior_only" and re.search(r"(?i)(RMSE|accuracy|error rate)", statement):
            errors.append(f"{claim_id}: hardware-behavior-only claim uses accuracy language")

    unresolved = [
        claim_id
        for claim_id, claim in claims.items()
        if claim.get("classification") == "pending"
    ]
    if require_all_resolved and unresolved:
        errors.append(f"unresolved pending claims remain: {unresolved}")

    return {
        "valid": not errors,
        "project": matrix.get("project"),
        "claim_count": len(claims),
        "public_ready_count": ready_count,
        "pending_claims": unresolved,
        "require_all_resolved": require_all_resolved,
        "errors": errors,
        "warnings": warnings,
    }


def load_matrix(path: Path) -> dict[str, Any]:
    value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("claims matrix root must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate GHOST evidence-bounded public claims.")
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--require-all-resolved", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = validate_claims(load_matrix(args.matrix), require_all_resolved=args.require_all_resolved)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.expanduser().write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
