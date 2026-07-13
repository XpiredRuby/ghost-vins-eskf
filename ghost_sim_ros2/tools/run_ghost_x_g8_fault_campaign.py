#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_x_fault_injection import run_campaign, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic GHOST-X G8 fault injection.")
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = run_campaign(args.design)
    write_outputs(report, args.out_dir)
    print(json.dumps({"faults": report["fault_count"], "passed_faults": report["passed_faults"], "passed": report["passed"]}, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
