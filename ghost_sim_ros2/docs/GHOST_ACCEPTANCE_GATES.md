# GHOST Acceptance Gates

Acceptance gates convert benchmark CSV evidence into explicit pass/fail checks.
They are software-only and are meant to run before hardware validation.

## Why This Matters

For a strong graduate-level prototype, a plot or live demo is not enough. The
system needs criteria that can fail:

| Gate | Purpose |
| --- | --- |
| `mh_top3_win_frac` | verifies multi-future prediction beats CV often enough |
| `mh_top3_coverage` | verifies probability branches cover plausible hidden paths |
| `mean_cv_rmse_m` | rejects invalid benchmark runs with unbounded baseline drift |
| `mean_mh_top3_rmse_m` | rejects multi-hypothesis futures that are too inaccurate |

## Example

```bash
cd ghost_sim_ros2
PYTHONPATH="$PWD" python3 analysis/tracker_comparison.py \
  --out /tmp/ghost_tracker_comparison.csv

PYTHONPATH="$PWD" python3 analysis/acceptance_gate.py \
  --csv /tmp/ghost_tracker_comparison.csv \
  --min-mh-top3-win-frac 0.55 \
  --min-mh-top3-coverage 0.70 \
  --fail-on-violation
```

After package installation:

```bash
tracker_comparison --out /tmp/ghost_tracker_comparison.csv
acceptance_gate --csv /tmp/ghost_tracker_comparison.csv --fail-on-violation
```

## Interpretation

`PASS` means the offline benchmark met the current software acceptance criteria.
It does not prove real-camera performance. It proves the no-camera estimator
stack is healthy enough to justify hardware validation.

`FAIL` means do not move to Pi/camera validation yet. The software evidence is
not strong enough or the thresholds are stricter than the current model can meet.
