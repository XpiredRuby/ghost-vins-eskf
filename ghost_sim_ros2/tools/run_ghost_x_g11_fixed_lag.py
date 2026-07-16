#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from analysis.ghost_x_fixed_lag import run_study, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the GHOST-X G11 fixed-lag smoother study.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--selected-config", type=Path, required=True)
    args = parser.parse_args()
    report = run_study(args.config, args.campaign_dir)
    write_outputs(report, args.out_dir, args.selected_config)
    print(
        json.dumps(
            {
                "ablation_count": report["ablation_count"],
                "selected_parameters": report["selected_parameters"],
                "frozen_eval_baseline_rmse_m": report["frozen_evaluation"]["baseline"]["position_rmse_m"],
                "frozen_eval_fixed_lag_rmse_m": report["frozen_evaluation"]["fixed_lag"]["position_rmse_m"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
