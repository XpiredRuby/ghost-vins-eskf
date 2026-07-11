"""Create and verify a GHOST formal-campaign parameter/file lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_REPO_FILES = (
    "ghost_sim_ros2/ghost_sim_ros2/formal_imm_tracker.py",
    "ghost_sim_ros2/ghost_sim_ros2/mh_tracker.py",
    "ghost_sim_ros2/analysis/imm_cycle.py",
    "ghost_sim_ros2/analysis/imm_mixing.py",
    "ghost_sim_ros2/analysis/mode_matched_kf.py",
    "docs/CONTROLLED_R_COLLECTION_PROTOCOL.md",
    "ghost_sim_ros2/docs/GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md",
    "ghost_sim_ros2/docs/IMM_MH_HARDWARE_CAMPAIGN_PROTOCOL.md",
    "ghost_sim_ros2/docs/IMM_MH_CAMPAIGN_MANIFEST.example.json",
    "ghost_sim_ros2/tools/collect_controlled_r_trial.sh",
)


def create_lock(
    repo_root: Path,
    out_path: Path,
    *,
    repo_files: list[str] | None = None,
    external_files: dict[str, Path] | None = None,
    runtime_parameters: Path | None = None,
    notes: str = "",
) -> dict[str, Any]:
    repo = repo_root.expanduser().resolve()
    out = out_path.expanduser().resolve()
    if out.exists():
        raise FileExistsError(f"refusing to overwrite parameter lock: {out}")
    if not (repo / ".git").exists():
        raise ValueError(f"repo_root is not a Git working tree: {repo}")

    selected = list(repo_files or DEFAULT_REPO_FILES)
    repo_entries = []
    for relative in selected:
        path = (repo / relative).resolve()
        if repo not in path.parents:
            raise ValueError(f"repo file escapes repository root: {relative}")
        if not path.is_file():
            raise ValueError(f"required repository file does not exist: {relative}")
        repo_entries.append(file_entry(path, relative, scope="repository"))

    external_entries = []
    for label, raw_path in sorted((external_files or {}).items()):
        if not label.strip():
            raise ValueError("external file labels must be non-empty")
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"external file does not exist for {label}: {path}")
        external_entries.append(file_entry(path, label, scope="external_local"))

    runtime_entry = None
    if runtime_parameters is not None:
        path = runtime_parameters.expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"runtime parameter snapshot does not exist: {path}")
        runtime_entry = file_entry(path, path.name, scope="runtime_parameter_snapshot")

    lock = {
        "schema_version": 1,
        "created_at_utc": utc_now(),
        "lock_status": "FORMAL_CAMPAIGN_PARAMETERS_PINNED_BEFORE_OUTCOME_REVIEW",
        "repo_root_name": repo.name,
        "git_head": git(repo, ["rev-parse", "HEAD"]),
        "git_branch": git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]),
        "git_status_porcelain": git(repo, ["status", "--porcelain"]),
        "repository_files": repo_entries,
        "external_files": external_entries,
        "runtime_parameters": runtime_entry,
        "notes": notes,
        "mutation_rule": (
            "Any change to a locked file, runtime parameter snapshot, camera calibration or camera-control "
            "configuration creates a new campaign configuration ID and blocks pooling without explicit review."
        ),
        "claims_boundary": "LOCK_PROVES_BYTE_AND_GIT_IDENTITY_NOT_PHYSICAL_CORRECTNESS",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return lock


def verify_lock(lock_path: Path, repo_root: Path, external_overrides: dict[str, Path] | None = None) -> dict[str, Any]:
    lock_path = lock_path.expanduser().resolve()
    repo = repo_root.expanduser().resolve()
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    warnings: list[str] = []

    current_head = git(repo, ["rev-parse", "HEAD"])
    if current_head != lock.get("git_head"):
        errors.append(f"git HEAD mismatch: locked={lock.get('git_head')} current={current_head}")
    current_status = git(repo, ["status", "--porcelain"])
    if current_status:
        warnings.append("current repository working tree is not clean")

    for entry in lock.get("repository_files", []):
        path = repo / entry["label"]
        check_entry(path, entry, errors)

    overrides = external_overrides or {}
    for entry in lock.get("external_files", []):
        label = entry["label"]
        override = overrides.get(label)
        path = override.expanduser().resolve() if override is not None else Path(entry["local_path"])
        check_entry(path, entry, errors)

    runtime_entry = lock.get("runtime_parameters")
    if isinstance(runtime_entry, dict):
        path = Path(runtime_entry["local_path"])
        check_entry(path, runtime_entry, errors)

    return {
        "valid": not errors,
        "lock": str(lock_path),
        "verified_at_utc": utc_now(),
        "locked_git_head": lock.get("git_head"),
        "current_git_head": current_head,
        "errors": errors,
        "warnings": warnings,
    }


def file_entry(path: Path, label: str, *, scope: str) -> dict[str, Any]:
    return {
        "label": label,
        "scope": scope,
        "local_path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def check_entry(path: Path, entry: dict[str, Any], errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"missing locked file {entry.get('label')}: {path}")
        return
    if path.stat().st_size != entry.get("size_bytes"):
        errors.append(f"size mismatch for {entry.get('label')}")
    if sha256(path) != entry.get("sha256"):
        errors.append(f"SHA-256 mismatch for {entry.get('label')}")


def parse_external(values: list[str]) -> dict[str, Path]:
    out = {}
    for value in values:
        if "=" not in value:
            raise ValueError("external files must use LABEL=PATH")
        label, path = value.split("=", 1)
        if not label.strip() or not path.strip():
            raise ValueError("external files must use non-empty LABEL=PATH")
        if label in out:
            raise ValueError(f"duplicate external file label: {label}")
        out[label] = Path(path)
    return out


def git(repo: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify a GHOST formal-campaign parameter lock.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--repo-root", type=Path, required=True)
    create.add_argument("--out", type=Path, required=True)
    create.add_argument("--repo-file", action="append", default=[])
    create.add_argument("--external", action="append", default=[])
    create.add_argument("--runtime-parameters", type=Path)
    create.add_argument("--notes", default="")
    verify = sub.add_parser("verify")
    verify.add_argument("--lock", type=Path, required=True)
    verify.add_argument("--repo-root", type=Path, required=True)
    verify.add_argument("--external", action="append", default=[])
    verify.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    if args.command == "create":
        result = create_lock(
            args.repo_root,
            args.out,
            repo_files=(args.repo_file or None),
            external_files=parse_external(args.external),
            runtime_parameters=args.runtime_parameters,
            notes=args.notes,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    result = verify_lock(args.lock, args.repo_root, parse_external(args.external))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.expanduser().write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
