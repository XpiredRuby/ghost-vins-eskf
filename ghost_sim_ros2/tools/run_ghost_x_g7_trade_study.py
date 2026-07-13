#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_x_trade_study import run_trade_study, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the GHOST-X G7 parameter trade study.")
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--selected-config", type=Path, required=True)
    args = parser.parse_args()
    report = run_trade_study(args.design, args.campaign_dir)
    write_outputs(report, args.out_dir, args.selected_config)
    print(
        json.dumps(
            {
                "canonical_trials": report["canonical_trials"],
                "imm_candidates": report["imm"]["candidate_count"],
                "mh_candidates": report["ghost_mh"]["candidate_count"],
                "status": report["selection_status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
