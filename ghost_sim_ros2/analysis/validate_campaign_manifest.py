"""Validate predeclared GHOST IMM/MH hardware campaign manifests."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ALLOWED_TRIAL_STATUS = {"planned", "accepted", "rejected"}
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def validate_manifest(manifest: dict[str, Any], require_complete: bool = False) -> dict[str, Any]:
    """Return a machine-readable validation summary without mutating *manifest*."""

    errors: list[str] = []
    warnings: list[str] = []

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")

    campaign_id = manifest.get("campaign_id")
    if not isinstance(campaign_id, str) or not campaign_id.strip():
        errors.append("campaign_id must be a non-empty string")

    protocol_commit = manifest.get("protocol_commit")
    if not isinstance(protocol_commit, str) or not COMMIT_RE.fullmatch(protocol_commit):
        errors.append("protocol_commit must be a 7-40 character hexadecimal commit id")
    elif set(protocol_commit) == {"0"}:
        warnings.append("protocol_commit is a placeholder and must be replaced before collection")

    randomization_seed = manifest.get("randomization_seed")
    if not isinstance(randomization_seed, int):
        errors.append("randomization_seed must be an integer")

    conditions_raw = manifest.get("conditions")
    if not isinstance(conditions_raw, list) or not conditions_raw:
        errors.append("conditions must be a non-empty list")
        conditions_raw = []

    conditions: dict[str, dict[str, Any]] = {}
    planned_total = 0
    for index, condition in enumerate(conditions_raw):
        where = f"conditions[{index}]"
        if not isinstance(condition, dict):
            errors.append(f"{where} must be an object")
            continue

        condition_id = condition.get("condition_id")
        if not isinstance(condition_id, str) or not condition_id.strip():
            errors.append(f"{where}.condition_id must be a non-empty string")
            continue
        if condition_id in conditions:
            errors.append(f"duplicate condition_id: {condition_id}")
            continue

        repetitions = condition.get("planned_repetitions")
        if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1:
            errors.append(f"{where}.planned_repetitions must be an integer >= 1")
            repetitions = 0
        elif repetitions < 5:
            warnings.append(
                f"{condition_id}: planned_repetitions={repetitions} is below the recommended minimum of 5"
            )

        duration = condition.get("target_occlusion_duration_s")
        if duration is not None and not _finite_nonnegative(duration):
            errors.append(f"{where}.target_occlusion_duration_s must be null or finite and >= 0")

        for field in ("motion_profile", "ground_truth_method", "primary_metric"):
            value = condition.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{where}.{field} must be a non-empty string")

        conditions[condition_id] = condition
        planned_total += repetitions

    trials_raw = manifest.get("trials", [])
    if not isinstance(trials_raw, list):
        errors.append("trials must be a list")
        trials_raw = []

    seen_trial_ids: set[str] = set()
    seen_slots: set[tuple[str, int]] = set()
    status_counts: Counter[str] = Counter()
    condition_counts: Counter[str] = Counter()

    for index, trial in enumerate(trials_raw):
        where = f"trials[{index}]"
        if not isinstance(trial, dict):
            errors.append(f"{where} must be an object")
            continue

        trial_id = trial.get("trial_id")
        if not isinstance(trial_id, str) or not trial_id.strip():
            errors.append(f"{where}.trial_id must be a non-empty string")
        elif trial_id in seen_trial_ids:
            errors.append(f"duplicate trial_id: {trial_id}")
        else:
            seen_trial_ids.add(trial_id)

        condition_id = trial.get("condition_id")
        if condition_id not in conditions:
            errors.append(f"{where}.condition_id references unknown condition: {condition_id!r}")
            condition = None
        else:
            condition = conditions[condition_id]
            condition_counts[condition_id] += 1

        repetition = trial.get("repetition")
        if not isinstance(repetition, int) or isinstance(repetition, bool) or repetition < 1:
            errors.append(f"{where}.repetition must be an integer >= 1")
        elif condition is not None:
            planned_repetitions = condition.get("planned_repetitions", 0)
            if repetition > planned_repetitions:
                errors.append(
                    f"{where}.repetition={repetition} exceeds planned_repetitions={planned_repetitions}"
                )
            slot = (condition_id, repetition)
            if slot in seen_slots:
                errors.append(f"duplicate condition/repetition slot: {condition_id} #{repetition}")
            else:
                seen_slots.add(slot)

        status = trial.get("status")
        if status not in ALLOWED_TRIAL_STATUS:
            errors.append(f"{where}.status must be one of {sorted(ALLOWED_TRIAL_STATUS)}")
        else:
            status_counts[status] += 1

        trial_dir = trial.get("trial_dir")
        if status == "accepted" and (not isinstance(trial_dir, str) or not trial_dir.strip()):
            errors.append(f"{where}.trial_dir is required for accepted trials")

        rejection_reason = trial.get("rejection_reason")
        if status == "rejected" and (
            not isinstance(rejection_reason, str) or not rejection_reason.strip()
        ):
            errors.append(f"{where}.rejection_reason is required for rejected trials")

        endpoint = trial.get("endpoint_truth_m")
        if endpoint is not None:
            if not isinstance(endpoint, dict):
                errors.append(f"{where}.endpoint_truth_m must be an object when provided")
            else:
                for axis in ("x", "y"):
                    if axis not in endpoint or not _finite_number(endpoint[axis]):
                        errors.append(f"{where}.endpoint_truth_m.{axis} must be finite")

    missing_slots = []
    for condition_id, condition in conditions.items():
        for repetition in range(1, int(condition.get("planned_repetitions", 0)) + 1):
            if (condition_id, repetition) not in seen_slots:
                missing_slots.append(f"{condition_id}#{repetition}")

    if require_complete:
        if missing_slots:
            errors.append(f"campaign is incomplete: {len(missing_slots)} planned trial slots are missing")
        planned_status = status_counts.get("planned", 0)
        if planned_status:
            errors.append(f"campaign is incomplete: {planned_status} trial entries still have status=planned")

    for condition_id, condition in conditions.items():
        recorded = condition_counts.get(condition_id, 0)
        planned = int(condition.get("planned_repetitions", 0))
        if recorded > planned:
            errors.append(f"{condition_id}: recorded trial count {recorded} exceeds planned count {planned}")

    return {
        "valid": not errors,
        "schema_version": manifest.get("schema_version"),
        "campaign_id": campaign_id,
        "require_complete": require_complete,
        "n_conditions": len(conditions),
        "planned_trials": planned_total,
        "recorded_trials": len(trials_raw),
        "status_counts": {
            "planned": status_counts.get("planned", 0),
            "accepted": status_counts.get("accepted", 0),
            "rejected": status_counts.get("rejected", 0),
        },
        "missing_trial_slots": missing_slots,
        "errors": errors,
        "warnings": warnings,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("campaign manifest root must be a JSON object")
    return data


def _finite_number(value: Any) -> bool:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(out)


def _finite_nonnegative(value: Any) -> bool:
    return _finite_number(value) and float(value) >= 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a GHOST IMM/MH campaign manifest.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    summary = validate_manifest(load_manifest(args.manifest), require_complete=args.require_complete)
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"

    if args.out:
        out = args.out.expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote: {out}")
    else:
        print(text, end="")

    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
