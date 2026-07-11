"""Update mutable campaign trial state without modifying the pinned campaign plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_RAW_LOGS = ("vision_pose.jsonl", "imm_futures.jsonl", "mh_futures.jsonl")
STATE_SCHEMA_VERSION = 1


def update_trial_state(
    campaign_dir: Path,
    trial_id: str,
    *,
    action: str,
    endpoint_x: float | None = None,
    endpoint_y: float | None = None,
    actual_gap_s: float | None = None,
    reason: str | None = None,
    notes: str = "",
    amend_reason: str | None = None,
) -> dict[str, Any]:
    root = campaign_dir.expanduser().resolve()
    manifest, lock = verify_pinned_plan(root)
    conditions = {str(item["condition_id"]): item for item in manifest.get("conditions", [])}
    planned_trials = {str(item["trial_id"]): item for item in manifest.get("trials", [])}
    if trial_id not in planned_trials:
        raise ValueError(f"unknown trial_id: {trial_id}")
    planned = planned_trials[trial_id]
    condition = conditions.get(str(planned.get("condition_id")))
    if condition is None:
        raise ValueError(f"trial {trial_id} references an unknown condition")

    state_path = root / "campaign_state.json"
    state = load_or_initialize_state(manifest, lock, state_path)
    current = next(item for item in state["trials"] if item["trial_id"] == trial_id)
    prior = deepcopy(current)
    if current["status"] != "planned" and not amend_reason:
        raise ValueError(
            f"trial {trial_id} is already {current['status']}; an explicit --amend-reason is required"
        )
    if amend_reason is not None and not amend_reason.strip():
        raise ValueError("amend_reason must be non-empty when provided")

    if action == "accept":
        endpoint = _validated_endpoint(endpoint_x, endpoint_y)
        expected_gap = float(condition.get("target_occlusion_duration_s") or 0.0)
        if expected_gap > 0.0:
            if not _finite_nonnegative(actual_gap_s):
                raise ValueError("accepted occlusion trials require finite --actual-gap-s")
            if abs(float(actual_gap_s) - expected_gap) > 0.25:
                raise ValueError(
                    f"actual gap {float(actual_gap_s):.3f}s is outside the ±0.25s protocol tolerance "
                    f"for target {expected_gap:.3f}s; reject the trial instead"
                )
        elif actual_gap_s is not None and not _finite_nonnegative(actual_gap_s):
            raise ValueError("actual_gap_s must be finite and >= 0 when provided")
        trial_dir = resolve_trial_dir(root, planned)
        raw_logs = verify_required_logs(trial_dir)
        current.update(
            {
                "status": "accepted",
                "endpoint_truth_m": endpoint,
                "actual_measurement_gap_s": float(actual_gap_s or 0.0),
                "gap_tolerance_status": "PASS" if expected_gap > 0.0 else "NOT_APPLICABLE",
                "rejection_reason": None,
                "verified_raw_logs": raw_logs,
            }
        )
    elif action == "reject":
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("rejected trials require a non-empty reason")
        current.update(
            {
                "status": "rejected",
                "rejection_reason": reason.strip(),
                "endpoint_truth_m": (
                    _validated_endpoint(endpoint_x, endpoint_y)
                    if endpoint_x is not None or endpoint_y is not None
                    else None
                ),
                "actual_measurement_gap_s": (
                    float(actual_gap_s) if _finite_nonnegative(actual_gap_s) else None
                ),
                "gap_tolerance_status": "REJECTED_NOT_USED_IN_PAIRED_METRICS",
                "verified_raw_logs": find_existing_logs(resolve_trial_dir(root, planned)),
            }
        )
    else:
        raise ValueError("action must be 'accept' or 'reject'")

    current["operator_notes"] = str(notes or "")
    current["updated_at_utc"] = utc_now()
    current["update_count"] = int(current.get("update_count", 0)) + 1
    state["updated_at_utc"] = utc_now()
    state["campaign_collection_status"] = collection_status(state)
    state["status_counts"] = status_counts(state)

    atomic_write_json(state_path, state)
    audit = {
        "schema_version": 1,
        "recorded_at_utc": utc_now(),
        "campaign_id": state["campaign_id"],
        "trial_id": trial_id,
        "action": action,
        "amendment": prior["status"] != "planned",
        "amend_reason": amend_reason,
        "prior": prior,
        "updated": deepcopy(current),
        "pinned_manifest_sha256": state["pinned_manifest_sha256"],
    }
    append_jsonl(root / "campaign_amendments.jsonl", audit)
    effective = write_effective_manifest(root, manifest, state)
    write_trial_metadata(root, planned, current)
    return {
        "campaign_id": state["campaign_id"],
        "trial_id": trial_id,
        "status": current["status"],
        "status_counts": state["status_counts"],
        "campaign_collection_status": state["campaign_collection_status"],
        "effective_manifest": str(root / "campaign_manifest_effective.json"),
        "validation": effective["validation"],
    }


def finalize_campaign(campaign_dir: Path) -> dict[str, Any]:
    root = campaign_dir.expanduser().resolve()
    manifest, lock = verify_pinned_plan(root)
    state = load_or_initialize_state(manifest, lock, root / "campaign_state.json")
    counts = status_counts(state)
    if counts["planned"]:
        raise ValueError(f"cannot finalize: {counts['planned']} trial slots remain planned")
    state["campaign_collection_status"] = "COLLECTION_COMPLETE_PENDING_ANALYSIS"
    state["finalized_at_utc"] = utc_now()
    state["status_counts"] = counts
    atomic_write_json(root / "campaign_state.json", state)
    result = write_effective_manifest(root, manifest, state, require_complete=True)
    append_jsonl(
        root / "campaign_amendments.jsonl",
        {
            "schema_version": 1,
            "recorded_at_utc": utc_now(),
            "campaign_id": state["campaign_id"],
            "action": "finalize_campaign",
            "status_counts": counts,
            "pinned_manifest_sha256": state["pinned_manifest_sha256"],
        },
    )
    return {
        "campaign_id": state["campaign_id"],
        "campaign_collection_status": state["campaign_collection_status"],
        "status_counts": counts,
        "validation": result["validation"],
    }


def verify_pinned_plan(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = root / "campaign_manifest.json"
    lock_path = root / "campaign_lock.json"
    manifest = load_json(manifest_path)
    lock = load_json(lock_path)
    locked_files = lock.get("files")
    if not isinstance(locked_files, dict):
        raise ValueError("campaign_lock.json is missing its files hash table")
    for relative, expected in locked_files.items():
        path = root / relative
        if not path.is_file():
            raise ValueError(f"pinned campaign file is missing: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"pinned campaign file hash mismatch: {relative}")
    if lock.get("campaign_id") != manifest.get("campaign_id"):
        raise ValueError("campaign lock and manifest campaign_id do not match")
    return manifest, lock


def load_or_initialize_state(
    manifest: dict[str, Any], lock: dict[str, Any], state_path: Path
) -> dict[str, Any]:
    manifest_hash = sha256(state_path.parent / "campaign_manifest.json")
    if state_path.exists():
        state = load_json(state_path)
        if state.get("pinned_manifest_sha256") != manifest_hash:
            raise ValueError("campaign_state.json does not match the pinned manifest hash")
        return state
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "campaign_id": manifest["campaign_id"],
        "protocol_commit": manifest["protocol_commit"],
        "pinned_manifest_sha256": manifest_hash,
        "campaign_lock_sha256": sha256(state_path.parent / "campaign_lock.json"),
        "created_at_utc": utc_now(),
        "updated_at_utc": utc_now(),
        "campaign_collection_status": "INITIALIZED_NOT_STARTED",
        "status_counts": {"planned": len(manifest.get("trials", [])), "accepted": 0, "rejected": 0},
        "trials": [
            {
                "trial_id": trial["trial_id"],
                "condition_id": trial["condition_id"],
                "repetition": trial["repetition"],
                "status": "planned",
                "endpoint_truth_m": None,
                "actual_measurement_gap_s": None,
                "gap_tolerance_status": "PENDING",
                "rejection_reason": None,
                "operator_notes": "",
                "verified_raw_logs": [],
                "update_count": 0,
                "updated_at_utc": None,
            }
            for trial in manifest.get("trials", [])
        ],
        "mutation_boundary": "PINNED_MANIFEST_AND_RANDOMIZED_ORDER_REMAIN_IMMUTABLE; OUTCOMES_LIVE_HERE",
    }
    atomic_write_json(state_path, state)
    return state


def write_effective_manifest(
    root: Path,
    manifest: dict[str, Any],
    state: dict[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    outcomes = {item["trial_id"]: item for item in state["trials"]}
    effective = deepcopy(manifest)
    for trial in effective.get("trials", []):
        outcome = outcomes[trial["trial_id"]]
        trial.update(
            {
                "status": outcome["status"],
                "endpoint_truth_m": outcome["endpoint_truth_m"],
                "rejection_reason": outcome["rejection_reason"],
                "actual_measurement_gap_s": outcome["actual_measurement_gap_s"],
                "gap_tolerance_status": outcome["gap_tolerance_status"],
                "collection_notes": outcome["operator_notes"],
            }
        )
    effective["campaign_collection_status"] = state["campaign_collection_status"]
    effective["campaign_state_file"] = "campaign_state.json"
    effective["pinned_manifest_sha256"] = state["pinned_manifest_sha256"]
    validation = validate_effective(effective, require_complete=require_complete)
    atomic_write_json(root / "campaign_manifest_effective.json", effective)
    atomic_write_json(root / "campaign_validation_current.json", validation)
    if not validation.get("valid"):
        raise ValueError(f"effective campaign manifest failed validation: {validation.get('errors')}")
    return {"manifest": effective, "validation": validation}


def validate_effective(manifest: dict[str, Any], *, require_complete: bool) -> dict[str, Any]:
    try:
        from analysis.validate_campaign_manifest import validate_manifest
    except ImportError:
        planned = sum(trial.get("status") == "planned" for trial in manifest.get("trials", []))
        return {
            "valid": not (require_complete and planned),
            "validator": "STRUCTURAL_FALLBACK_ONLY",
            "errors": ([f"{planned} trial slots remain planned"] if require_complete and planned else []),
            "warnings": ["repository manifest validator import unavailable"],
        }
    result = validate_manifest(manifest, require_complete=require_complete)
    result["validator"] = "validate_campaign_manifest.py"
    return result


def verify_required_logs(trial_dir: Path) -> list[str]:
    found = find_existing_logs(trial_dir)
    missing = [name for name in REQUIRED_RAW_LOGS if name not in found]
    if missing:
        raise ValueError(f"accepted trial is missing required raw logs: {missing}")
    return found


def find_existing_logs(trial_dir: Path) -> list[str]:
    found = []
    for filename in REQUIRED_RAW_LOGS:
        direct = trial_dir / filename
        matches = [direct] if direct.is_file() else list(trial_dir.rglob(filename))
        if len(matches) == 1:
            found.append(filename)
        elif len(matches) > 1:
            raise ValueError(f"ambiguous duplicate {filename} files under {trial_dir}")
    return found


def resolve_trial_dir(root: Path, planned: dict[str, Any]) -> Path:
    path = Path(str(planned.get("trial_dir", "")))
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_dir():
        raise ValueError(f"trial directory does not exist: {path}")
    return path


def write_trial_metadata(root: Path, planned: dict[str, Any], outcome: dict[str, Any]) -> None:
    trial_dir = resolve_trial_dir(root, planned)
    path = trial_dir / "trial_metadata.json"
    metadata = load_json(path) if path.is_file() else {"trial_id": planned["trial_id"]}
    metadata.update(
        {
            "status": outcome["status"],
            "endpoint_truth_m": outcome["endpoint_truth_m"],
            "actual_measurement_gap_s": outcome["actual_measurement_gap_s"],
            "gap_tolerance_status": outcome["gap_tolerance_status"],
            "rejection_reason": outcome["rejection_reason"],
            "operator_notes": outcome["operator_notes"],
            "updated_at_utc": outcome["updated_at_utc"],
        }
    )
    atomic_write_json(path, metadata)


def collection_status(state: dict[str, Any]) -> str:
    counts = status_counts(state)
    if counts["accepted"] + counts["rejected"] == 0:
        return "INITIALIZED_NOT_STARTED"
    if counts["planned"]:
        return "COLLECTION_IN_PROGRESS"
    return "ALL_SLOTS_RECORDED_PENDING_FINALIZATION"


def status_counts(state: dict[str, Any]) -> dict[str, int]:
    return {
        key: sum(item.get("status") == key for item in state.get("trials", []))
        for key in ("planned", "accepted", "rejected")
    }


def _validated_endpoint(x: float | None, y: float | None) -> dict[str, float]:
    if not _finite(x) or not _finite(y):
        raise ValueError("accepted trials require finite endpoint x and y coordinates")
    return {"x": float(x), "y": float(y)}


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _finite_nonnegative(value: Any) -> bool:
    return _finite(value) and float(value) >= 0.0


def load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return obj


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(value, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update GHOST campaign outcomes without changing the pinned plan.")
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--trial-id")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--accept", action="store_true")
    actions.add_argument("--reject")
    parser.add_argument("--endpoint-x", type=float)
    parser.add_argument("--endpoint-y", type=float)
    parser.add_argument("--actual-gap-s", type=float)
    parser.add_argument("--notes", default="")
    parser.add_argument("--amend-reason")
    args = parser.parse_args(argv)

    if args.finalize:
        if args.trial_id or args.accept or args.reject:
            parser.error("--finalize cannot be combined with a trial update")
        result = finalize_campaign(args.campaign_dir)
    else:
        if not args.trial_id or not (args.accept or args.reject):
            parser.error("trial updates require --trial-id and exactly one of --accept or --reject")
        result = update_trial_state(
            args.campaign_dir,
            args.trial_id,
            action="accept" if args.accept else "reject",
            endpoint_x=args.endpoint_x,
            endpoint_y=args.endpoint_y,
            actual_gap_s=args.actual_gap_s,
            reason=args.reject,
            notes=args.notes,
            amend_reason=args.amend_reason,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
