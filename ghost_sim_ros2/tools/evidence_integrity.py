"""Create and verify immutable GHOST evidence ZIP packages with SHA-256 manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = 1
MANIFEST_NAME = "EVIDENCE_MANIFEST.json"
MANIFEST_HASH_NAME = "EVIDENCE_MANIFEST.sha256"

PROFILE_REQUIRED = {
    "generic": [],
    "controlled_r": [
        "protocol_metadata.txt",
        "camera_control_readbacks.tsv",
        "camera_controls_before.txt",
        "camera_controls_after_trial.txt",
        "operator_attestation.txt",
        "vision_pose.jsonl",
        "collection_quality.json",
        "noise_summary.json",
        "noise_summary.md",
        "final_collection_status.txt",
    ],
    "campaign": [
        "campaign_manifest.json",
        "campaign_lock.json",
        "campaign_validation_before.json",
        "randomized_trial_order.csv",
        "trial_directories",
    ],
    "grid": [
        "grid_validation_summary.json",
        "grid_validation_summary.md",
    ],
}


def create_package(
    source_dir: Path,
    archive_path: Path,
    *,
    profile: str = "generic",
    repo_root: Path | None = None,
    allow_incomplete: bool = False,
) -> dict[str, Any]:
    source = source_dir.expanduser().resolve()
    archive = archive_path.expanduser().resolve()
    if profile not in PROFILE_REQUIRED:
        raise ValueError(f"unknown profile {profile!r}; choose from {sorted(PROFILE_REQUIRED)}")
    if not source.is_dir():
        raise ValueError(f"source directory does not exist: {source}")
    if archive.exists():
        raise FileExistsError(f"refusing to overwrite existing evidence archive: {archive}")
    if source == archive.parent or source in archive.parents:
        raise ValueError("archive must be written outside the source directory")

    missing = missing_required_artifacts(source, profile)
    if missing and not allow_incomplete:
        raise ValueError(f"missing required {profile} artifacts: {missing}")

    files = []
    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source).as_posix()
        if relative in {MANIFEST_NAME, MANIFEST_HASH_NAME}:
            continue
        files.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_path(path),
                "is_symlink": path.is_symlink(),
                "symlink_target": os.readlink(path) if path.is_symlink() else None,
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": utc_now(),
        "profile": profile,
        "source_directory_name": source.name,
        "source_path_recorded_for_operator": str(source),
        "archive_file": archive.name,
        "package_status": "COMPLETE" if not missing else "INCOMPLETE_ALLOWED",
        "missing_required_artifacts": missing,
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
        "environment": environment_snapshot(repo_root),
        "integrity_boundary": "SHA256_DETECTS_POST_PACKAGE_BYTE_CHANGES_BUT_DOES_NOT_PROVE_PHYSICAL_TRIAL_VALIDITY",
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for item in files:
            zf.write(source / item["path"], arcname=f"evidence/{item['path']}")
        zf.writestr(MANIFEST_NAME, manifest_bytes)
        zf.writestr(MANIFEST_HASH_NAME, manifest_hash + "  " + MANIFEST_NAME + "\n")
    manifest["archive_sha256"] = sha256_path(archive)
    manifest["manifest_sha256"] = manifest_hash
    return manifest


def verify_package(archive_path: Path) -> dict[str, Any]:
    archive = archive_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if not archive.is_file():
        return {"valid": False, "archive": str(archive), "errors": ["archive does not exist"], "warnings": []}
    manifest = None
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            names = set(zf.namelist())
            if MANIFEST_NAME not in names or MANIFEST_HASH_NAME not in names:
                return {
                    "valid": False,
                    "archive": str(archive),
                    "errors": ["archive is missing its evidence manifest or manifest hash"],
                    "warnings": [],
                }
            manifest_bytes = zf.read(MANIFEST_NAME)
            expected_manifest_hash = zf.read(MANIFEST_HASH_NAME).decode("utf-8").split()[0]
            actual_manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
            if actual_manifest_hash != expected_manifest_hash:
                errors.append("manifest SHA-256 does not match EVIDENCE_MANIFEST.sha256")
            manifest = json.loads(manifest_bytes)
            if manifest.get("schema_version") != SCHEMA_VERSION:
                errors.append(f"unsupported manifest schema_version: {manifest.get('schema_version')}")
            listed = manifest.get("files")
            if not isinstance(listed, list):
                errors.append("manifest files must be a list")
                listed = []
            expected_members = set()
            for item in listed:
                relative = str(item.get("path", ""))
                member = str(PurePosixPath("evidence") / PurePosixPath(relative))
                expected_members.add(member)
                if member not in names:
                    errors.append(f"missing archived member: {member}")
                    continue
                payload = zf.read(member)
                actual = hashlib.sha256(payload).hexdigest()
                if actual != item.get("sha256"):
                    errors.append(f"SHA-256 mismatch: {member}")
                if len(payload) != item.get("size_bytes"):
                    errors.append(f"size mismatch: {member}")
            unexpected = sorted(
                name for name in names if name.startswith("evidence/") and name not in expected_members
            )
            if unexpected:
                warnings.append(f"unlisted evidence members: {unexpected}")
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
        errors.append(str(exc))

    return {
        "valid": not errors,
        "archive": str(archive),
        "archive_sha256": sha256_path(archive),
        "profile": manifest.get("profile") if isinstance(manifest, dict) else None,
        "file_count": manifest.get("file_count") if isinstance(manifest, dict) else None,
        "errors": errors,
        "warnings": warnings,
        "verified_at_utc": utc_now(),
    }


def missing_required_artifacts(source: Path, profile: str) -> list[str]:
    missing = []
    for required in PROFILE_REQUIRED[profile]:
        direct = source / required
        if direct.exists():
            continue
        if not list(source.rglob(required)):
            missing.append(required)
    return missing


def environment_snapshot(repo_root: Path | None) -> dict[str, Any]:
    snapshot = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "command_line": sys.argv,
    }
    if repo_root is not None:
        repo = repo_root.expanduser().resolve()
        snapshot["git_repo"] = str(repo)
        snapshot["git_head"] = _git(repo, ["rev-parse", "HEAD"])
        snapshot["git_status_porcelain"] = _git(repo, ["status", "--porcelain"])
        snapshot["git_branch"] = _git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    return snapshot


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(repo: Path, args: list[str]) -> str | None:
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create or verify SHA-256 protected GHOST evidence archives."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    package = sub.add_parser("package")
    package.add_argument("--source", type=Path, required=True)
    package.add_argument("--archive", type=Path, required=True)
    package.add_argument("--profile", choices=sorted(PROFILE_REQUIRED), default="generic")
    package.add_argument("--repo-root", type=Path)
    package.add_argument("--allow-incomplete", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    if args.command == "package":
        result = create_package(
            args.source,
            args.archive,
            profile=args.profile,
            repo_root=args.repo_root,
            allow_incomplete=args.allow_incomplete,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    result = verify_package(args.archive)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.expanduser().write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
