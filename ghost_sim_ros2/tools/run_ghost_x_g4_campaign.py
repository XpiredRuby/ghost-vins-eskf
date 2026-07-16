#!/usr/bin/env python3
"""Run the deterministic GHOST-X G4 controlled-truth campaign."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_x_controlled_truth import load_config, run_campaign


def git_provenance(repo_root: Path) -> dict[str, object]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    status = run("status", "--porcelain")
    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
        "working_tree_clean": not bool(status),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PACKAGE_ROOT / "config" / "ghost_x_g4_controlled_truth.yaml",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=PACKAGE_ROOT.parent)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)

    provenance = git_provenance(args.repo_root)
    if not provenance["working_tree_clean"] and not args.allow_dirty:
        raise SystemExit("refusing report-grade G4 run from a dirty working tree; use --allow-dirty only for development")
    config = load_config(args.config)
    manifest = run_campaign(config, args.out, code_provenance=provenance)
    summary = {
        "out": str(args.out.expanduser().resolve()),
        "planned_trials": manifest["planned_trials"],
        "accepted_trials": manifest["accepted_trials"],
        "invalid_trials": manifest["invalid_trials"],
        "identical_input_hashes": all(
            len(set(row.get("estimator_input_sha256", {}).values())) <= 1
            for row in manifest["trials"]
            if row["status"] == "accepted"
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if manifest["accepted_trials"] == manifest["planned_trials"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
