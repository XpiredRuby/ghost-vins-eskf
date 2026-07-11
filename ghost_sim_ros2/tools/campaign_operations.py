"""Initialize and operate the predeclared GHOST IMM/MH hardware campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import subprocess
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
CAMPAIGN_LOCK_VERSION = 1


@dataclass(frozen=True)
class OrderedTrial:
    sequence: int
    trial_id: str
    condition_id: str
    repetition: int


def cue_plan_for_condition(condition: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the predeclared visual/audio cue phases for one condition."""

    condition_id = str(condition["condition_id"])
    occlusion_s = float(condition.get("target_occlusion_duration_s") or 0.0)
    motion_profile = str(condition.get("motion_profile", ""))

    if condition_id == "static_visible" or motion_profile == "stationary_visible":
        return [
            _phase("HOLD START", 3.0, "Keep the tag visible and motionless at the measured point.", "hold"),
            _phase("STATIONARY SAMPLE", 10.0, "Do not touch the tag, camera, table or lighting.", "sample"),
            _phase("POST-ROLL", 2.0, "Remain stationary while recording finishes.", "post"),
            _phase("DONE", 0.0, "Trial cue sequence complete.", "done"),
        ]

    phases = [
        _phase("HOLD START", 3.0, "Tag visible and stationary on the measured start mark.", "hold"),
    ]

    if motion_profile == "measured_endpoint_single_turn":
        phases.extend(
            [
                _phase("MOVE TO TURN", 2.0, "Move along the first marked segment toward the turn point.", "move"),
                _phase("TURN", 1.0, "Execute the single predeclared direction change. Do not add another turn.", "turn"),
            ]
        )
    else:
        phases.append(
            _phase("MOVE", 2.0, "Move along the marked straight path toward the endpoint.", "move")
        )

    if occlusion_s > 0.0:
        phases.append(
            _phase(
                "OCCLUDE NOW",
                occlusion_s,
                "Fully hide the AprilTag while continuing the predeclared motion to the endpoint.",
                "occlude",
            )
        )
        phases.append(
            _phase("REVEAL", 0.0, "Reveal the tag at the measured endpoint and stop it before the next phase.", "reveal")
        )
    else:
        phases.append(
            _phase("ENDPOINT", 1.0, "Reach the measured endpoint without intentionally hiding the tag.", "endpoint")
        )

    phases.extend(
        [
            _phase("HOLD END", 5.0, "Keep the revealed tag stationary on the measured endpoint.", "hold"),
            _phase("POST-ROLL", 2.0, "Remain stationary while recording finishes.", "post"),
            _phase("DONE", 0.0, "Trial cue sequence complete.", "done"),
        ]
    )
    return phases


def initialize_campaign(
    template: dict[str, Any],
    output_dir: Path,
    protocol_commit: str,
    *,
    campaign_id: str | None = None,
    seed: int | None = None,
    overwrite_empty: bool = False,
) -> dict[str, Any]:
    """Create a pinned campaign directory and return its lock summary."""

    protocol_commit = protocol_commit.strip()
    if not COMMIT_RE.fullmatch(protocol_commit) or set(protocol_commit) == {"0"}:
        raise ValueError("protocol_commit must be a non-zero 7-40 character hexadecimal commit id")

    out = output_dir.expanduser().resolve()
    if out.exists():
        if not overwrite_empty or any(out.iterdir()):
            raise FileExistsError(f"campaign directory already exists and is not safely replaceable: {out}")
        out.rmdir()
    out.mkdir(parents=True)

    manifest = deepcopy(template)
    if not isinstance(manifest, dict):
        raise ValueError("template root must be a JSON object")
    manifest["protocol_commit"] = protocol_commit
    manifest["protocol_commit_status"] = "PINNED_BEFORE_COLLECTION"
    if campaign_id:
        manifest["campaign_id"] = campaign_id
    if seed is not None:
        manifest["randomization_seed"] = int(seed)

    conditions = manifest.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        raise ValueError("template conditions must be a non-empty list")
    actual_seed = int(manifest.get("randomization_seed"))

    trials: list[dict[str, Any]] = []
    for condition in conditions:
        condition_id = _required_text(condition, "condition_id")
        repetitions = condition.get("planned_repetitions")
        if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 1:
            raise ValueError(f"{condition_id}: planned_repetitions must be an integer >= 1")
        for repetition in range(1, repetitions + 1):
            trial_id = f"{condition_id}_{repetition:02d}"
            trials.append(
                {
                    "trial_id": trial_id,
                    "condition_id": condition_id,
                    "repetition": repetition,
                    "status": "planned",
                    "trial_dir": f"trial_directories/{trial_id}",
                    "endpoint_truth_m": None,
                    "rejection_reason": None,
                    "collection_notes": "",
                }
            )
    manifest["trials"] = trials
    manifest["campaign_initialized_at_utc"] = _utc_now()
    manifest["campaign_collection_status"] = "INITIALIZED_NOT_STARTED"

    order = balanced_randomized_order(conditions, seed=actual_seed)
    if {item.trial_id for item in order} != {trial["trial_id"] for trial in trials}:
        raise RuntimeError("randomized order does not contain exactly the planned trial ids")

    manifest_path = out / "campaign_manifest.json"
    order_path = out / "randomized_trial_order.csv"
    trial_root = out / "trial_directories"
    trial_root.mkdir()

    _write_json(manifest_path, manifest)
    _write_order_csv(order_path, order, conditions)

    condition_map = {str(item["condition_id"]): item for item in conditions}
    for ordered in order:
        trial_dir = trial_root / ordered.trial_id
        trial_dir.mkdir()
        condition = condition_map[ordered.condition_id]
        _write_json(
            trial_dir / "conductor_plan.json",
            {
                "schema_version": 1,
                "campaign_id": manifest["campaign_id"],
                "protocol_commit": protocol_commit,
                "sequence": ordered.sequence,
                "trial_id": ordered.trial_id,
                "condition_id": ordered.condition_id,
                "repetition": ordered.repetition,
                "target_occlusion_duration_s": condition.get("target_occlusion_duration_s"),
                "motion_profile": condition.get("motion_profile"),
                "phases": cue_plan_for_condition(condition),
                "acceptance_note": "Measured vision gap, not cue duration alone, determines acceptance.",
            },
        )
        _write_json(
            trial_dir / "trial_metadata.json",
            {
                "schema_version": 1,
                "campaign_id": manifest["campaign_id"],
                "trial_id": ordered.trial_id,
                "sequence": ordered.sequence,
                "condition_id": ordered.condition_id,
                "repetition": ordered.repetition,
                "status": "planned",
                "endpoint_truth_m": None,
                "operator_notes": "",
                "created_at_utc": _utc_now(),
            },
        )

    validation = _validate_with_optional_import(manifest)
    _write_json(out / "campaign_validation_before.json", validation)
    if not validation.get("valid"):
        raise ValueError(f"initialized manifest failed validation: {validation.get('errors')}")

    lock = {
        "lock_version": CAMPAIGN_LOCK_VERSION,
        "campaign_id": manifest["campaign_id"],
        "protocol_commit": protocol_commit,
        "randomization_seed": actual_seed,
        "planned_trials": len(trials),
        "conditions": len(conditions),
        "created_at_utc": _utc_now(),
        "files": {
            "campaign_manifest.json": _sha256(manifest_path),
            "randomized_trial_order.csv": _sha256(order_path),
            "campaign_validation_before.json": _sha256(out / "campaign_validation_before.json"),
        },
        "lock_status": "PRECOLLECTION_PLAN_PINNED",
        "mutation_rule": "Do not edit the pinned manifest or trial order after collection begins; record amendments separately.",
    }
    _write_json(out / "campaign_lock.json", lock)
    (out / "CAMPAIGN_README.md").write_text(_campaign_readme(manifest, lock), encoding="utf-8")
    return lock


def balanced_randomized_order(conditions: list[dict[str, Any]], *, seed: int) -> list[OrderedTrial]:
    """Interleave one repetition per condition per round and shuffle within each round."""

    rng = random.Random(seed)
    max_repetitions = max(int(condition["planned_repetitions"]) for condition in conditions)
    ordered: list[OrderedTrial] = []
    sequence = 1
    for repetition in range(1, max_repetitions + 1):
        block = [
            (str(condition["condition_id"]), repetition)
            for condition in conditions
            if repetition <= int(condition["planned_repetitions"])
        ]
        rng.shuffle(block)
        for condition_id, rep in block:
            ordered.append(
                OrderedTrial(
                    sequence=sequence,
                    trial_id=f"{condition_id}_{rep:02d}",
                    condition_id=condition_id,
                    repetition=rep,
                )
            )
            sequence += 1
    return ordered


def resolve_protocol_commit(repo_root: Path, protocol_path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "log", "-n", "1", "--format=%H", "--", protocol_path],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if not COMMIT_RE.fullmatch(commit) or set(commit) == {"0"}:
        raise ValueError(f"could not resolve a valid protocol commit for {protocol_path}")
    return commit


def load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return obj


def _phase(cue: str, duration_s: float, instruction: str, phase_type: str) -> dict[str, Any]:
    return {
        "cue": cue,
        "duration_s": float(duration_s),
        "instruction": instruction,
        "phase_type": phase_type,
        "speak": cue,
    }


def _write_order_csv(path: Path, order: list[OrderedTrial], conditions: list[dict[str, Any]]) -> None:
    condition_map = {str(item["condition_id"]): item for item in conditions}
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "sequence",
                "trial_id",
                "condition_id",
                "repetition",
                "target_occlusion_duration_s",
                "motion_profile",
                "primary_metric",
            ]
        )
        for item in order:
            condition = condition_map[item.condition_id]
            writer.writerow(
                [
                    item.sequence,
                    item.trial_id,
                    item.condition_id,
                    item.repetition,
                    condition.get("target_occlusion_duration_s"),
                    condition.get("motion_profile"),
                    condition.get("primary_metric"),
                ]
            )


def _validate_with_optional_import(manifest: dict[str, Any]) -> dict[str, Any]:
    try:
        from analysis.validate_campaign_manifest import validate_manifest
    except ImportError:
        return {
            "valid": True,
            "validator": "STRUCTURAL_FALLBACK_ONLY",
            "planned_trials": len(manifest.get("trials", [])),
            "errors": [],
            "warnings": ["validate_campaign_manifest import unavailable; run repository validator before collection"],
        }
    result = validate_manifest(manifest)
    result["validator"] = "validate_campaign_manifest.py"
    return result


def _required_text(mapping: dict[str, Any], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _campaign_readme(manifest: dict[str, Any], lock: dict[str, Any]) -> str:
    return f"""# GHOST Hardware Campaign Instance

- Campaign: `{manifest['campaign_id']}`
- Protocol commit: `{manifest['protocol_commit']}`
- Randomization seed: `{manifest['randomization_seed']}`
- Planned trials: `{lock['planned_trials']}`
- Lock status: `{lock['lock_status']}`

## Collection rule

Do not edit `campaign_manifest.json` or `randomized_trial_order.csv` after collection begins. Record any deviation as a separate amendment and preserve rejected trials.

## Start one cue sequence

```bash
python3 ghost_sim_ros2/tools/trial_conductor.py \
  --campaign-dir <this-directory> \
  --sequence 1
```

The browser cue duration does not determine acceptance by itself. The measured `/ghost/vision/target_pose` gap remains the source of truth.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a pinned GHOST IMM/MH hardware campaign.")
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--protocol-commit")
    group.add_argument("--resolve-protocol-commit", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--protocol-path",
        default="ghost_sim_ros2/docs/IMM_MH_HARDWARE_CAMPAIGN_PROTOCOL.md",
    )
    parser.add_argument("--campaign-id")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--overwrite-empty", action="store_true")
    args = parser.parse_args(argv)

    protocol_commit = args.protocol_commit
    if args.resolve_protocol_commit:
        protocol_commit = resolve_protocol_commit(args.repo_root, args.protocol_path)
    lock = initialize_campaign(
        load_json(args.template),
        args.out,
        str(protocol_commit),
        campaign_id=args.campaign_id,
        seed=args.seed,
        overwrite_empty=args.overwrite_empty,
    )
    print(json.dumps(lock, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
