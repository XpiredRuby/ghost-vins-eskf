"""Validate GHOST physical-session phase order, status and artifact declarations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_STATUS = {"pending", "in_progress", "passed", "rejected", "skipped_with_reason"}
SCHEMA_VERSION = 1


def validate_session(
    session: dict[str, Any],
    *,
    require_ready_for: str | None = None,
    require_complete: bool = False,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if session.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")
    if not isinstance(session.get("session_id"), str) or not session["session_id"].strip():
        errors.append("session_id must be a non-empty string")
    phases_raw = session.get("phases")
    if not isinstance(phases_raw, list) or not phases_raw:
        errors.append("phases must be a non-empty list")
        phases_raw = []

    phases: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, phase in enumerate(phases_raw):
        where = f"phases[{index}]"
        if not isinstance(phase, dict):
            errors.append(f"{where} must be an object")
            continue
        phase_id = phase.get("phase_id")
        if not isinstance(phase_id, str) or not phase_id.strip():
            errors.append(f"{where}.phase_id must be non-empty")
            continue
        if phase_id in phases:
            errors.append(f"duplicate phase_id: {phase_id}")
            continue
        status = phase.get("status")
        if status not in ALLOWED_STATUS:
            errors.append(f"{where}.status must be one of {sorted(ALLOWED_STATUS)}")
        depends = phase.get("depends_on")
        if not isinstance(depends, list) or not all(isinstance(item, str) for item in depends):
            errors.append(f"{where}.depends_on must be a list of phase ids")
            depends = []
        artifacts = phase.get("required_artifacts")
        if not isinstance(artifacts, list) or not all(
            isinstance(item, str) and item.strip() for item in artifacts
        ):
            errors.append(f"{where}.required_artifacts must be a list of non-empty strings")
            artifacts = []
        if status == "skipped_with_reason" and not str(phase.get("notes", "")).strip():
            errors.append(f"{phase_id}: skipped_with_reason requires notes")
        phases[phase_id] = phase
        order.append(phase_id)

    for phase_id, phase in phases.items():
        for dependency in phase.get("depends_on", []):
            if dependency not in phases:
                errors.append(f"{phase_id}: unknown dependency {dependency}")
            elif order.index(dependency) >= order.index(phase_id):
                errors.append(f"{phase_id}: dependency {dependency} must appear earlier")
        if phase.get("status") in {"in_progress", "passed"}:
            for dependency in phase.get("depends_on", []):
                if dependency in phases and phases[dependency].get("status") not in {
                    "passed",
                    "skipped_with_reason",
                }:
                    errors.append(
                        f"{phase_id}: cannot be {phase.get('status')} while dependency "
                        f"{dependency} is {phases[dependency].get('status')}"
                    )

    missing_artifacts: dict[str, list[str]] = {}
    if artifact_root is not None:
        root = artifact_root.expanduser().resolve()
        for phase_id, phase in phases.items():
            if phase.get("status") != "passed":
                continue
            missing = [
                artifact
                for artifact in phase.get("required_artifacts", [])
                if not _artifact_exists(root, artifact)
            ]
            if missing:
                missing_artifacts[phase_id] = missing
                errors.append(f"{phase_id}: passed but required artifacts are missing: {missing}")

    ready = None
    if require_ready_for is not None:
        if require_ready_for not in phases:
            errors.append(f"unknown --require-ready-for phase: {require_ready_for}")
            ready = False
        else:
            unmet = [
                dependency
                for dependency in phases[require_ready_for].get("depends_on", [])
                if phases[dependency].get("status") not in {"passed", "skipped_with_reason"}
            ]
            ready = not unmet
            if unmet:
                errors.append(f"{require_ready_for}: unmet dependencies: {unmet}")

    if require_complete:
        incomplete = [
            phase_id
            for phase_id, phase in phases.items()
            if phase.get("status") not in {"passed", "skipped_with_reason"}
        ]
        if incomplete:
            errors.append(f"session is incomplete: {incomplete}")

    status_counts = {
        status: sum(phase.get("status") == status for phase in phases.values())
        for status in sorted(ALLOWED_STATUS)
    }
    return {
        "valid": not errors,
        "session_id": session.get("session_id"),
        "phase_count": len(phases),
        "status_counts": status_counts,
        "require_ready_for": require_ready_for,
        "ready": ready,
        "require_complete": require_complete,
        "missing_artifacts": missing_artifacts,
        "errors": errors,
        "warnings": warnings,
    }


def _artifact_exists(root: Path, artifact: str) -> bool:
    direct = root / artifact
    return direct.exists() or any(root.rglob(artifact))


def load_session(path: Path) -> dict[str, Any]:
    value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("session checklist root must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a GHOST physical-validation session checklist.")
    parser.add_argument("checklist", type=Path)
    parser.add_argument("--require-ready-for")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = validate_session(
        load_session(args.checklist),
        require_ready_for=args.require_ready_for,
        require_complete=args.require_complete,
        artifact_root=args.artifact_root,
    )
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.expanduser().write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
