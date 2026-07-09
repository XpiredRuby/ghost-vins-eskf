# GHOST Tracker Comparison Harness

This software-only harness compares the current GHOST occlusion estimators on
identical synthetic truth, measurement noise, and occlusion schedules.

**Scope caveat:** this is a software-only exploratory/synthetic comparison harness. It is not the final report-grade hardware statistical comparison harness, does not validate real-world estimator accuracy, and should not be cited as proof that IMM or MH statistically outperforms another tracker on hardware.

## Purpose

The comparison explores a research question that single demos cannot:

> Given the same observations before disappearance, does the occlusion estimator
> reduce error relative to a constant-velocity baseline, and does it preserve
> plausible future branches instead of hallucinating one unbounded path?

## Compared Trackers

| Tracker | Output | Role |
| --- | --- | --- |
| CV Kalman | one point estimate | baseline |
| IMM | one probability-weighted point estimate | maneuver-adaptive baseline |
| Calibrated GHOST-MH | mean, best future, top-3 future, coverage | multi-future research candidate |

The harness does not use a camera, ROS graph, Pi, AprilTag detector, or hardware.

## Command

```bash
cd ghost_sim_ros2
PYTHONPATH="$PWD" python3 analysis/tracker_comparison.py \
  --out /tmp/ghost_tracker_comparison.csv
```

After package installation, the console entry point is:

```bash
tracker_comparison --out /tmp/ghost_tracker_comparison.csv
```

## Key Metrics

| Metric | Meaning |
| --- | --- |
| `cv_rmse_m` | CV point-estimate RMSE during occlusion |
| `imm_rmse_m` | IMM point-estimate RMSE during occlusion |
| `mh_mean_rmse_m` | relative-weighted GHOST-MH mean RMSE |
| `mh_best_future_rmse_m` | closest GHOST-MH branch RMSE |
| `mh_top3_future_rmse_m` | closest of the top-three relative-weight branches |
| `mh_top1_coverage_frac` | fraction where the top branch is within the coverage radius |
| `mh_top3_coverage_frac` | fraction where a top-three branch is within the coverage radius |
| `mh_any_coverage_frac` | fraction where any maintained branch is within the coverage radius |
| `mean_imm_maneuver_prob` | average IMM maneuver-mode probability during occlusion |

## Interpretation

The point-estimate scores (`cv_rmse_m`, `imm_rmse_m`, `mh_mean_rmse_m`) compare
single-path trackers within the same synthetic truth/noise/occlusion schedule.

The future-branch scores (`mh_best_future_rmse_m`, `mh_top3_future_rmse_m`, and
coverage) evaluate the actual GHOST research claim: during occlusion, the system
should maintain multiple physically plausible futures with relative hypothesis weights.

Strong software-only results should show expectations for this synthetic harness, not hardware accuracy claims:

1. bounded finite errors,
2. IMM reducing error relative to CV on maneuver cases,
3. top-three GHOST-MH futures covering more synthetic occlusion outcomes than a
   single point estimate,
4. repeatable CSV outputs that can be summarized by `stats_harness`.
