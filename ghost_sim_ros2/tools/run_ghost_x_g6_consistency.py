#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_x_consistency import analyze_campaign, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GHOST-X formal consistency diagnostics.")
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_campaign(args.campaign_dir)
    write_outputs(report, args.out_dir)
    pooled = report["pooled"]
    summary = {
        "canonical_trials": report["canonical_trials"],
        "cv_nis_mean_inside_95": pooled["cv"]["nis"]["mean_inside_95"],
        "cv_nees_mean_inside_95": pooled["cv"]["position_nees"]["mean_inside_95"],
        "imm_nis_interpretation": pooled["formal_imm"]["nis_validity"],
        "mh_nis_valid": pooled["ghost_mh"]["nis"]["valid"],
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
