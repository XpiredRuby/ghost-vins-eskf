# GHOST-MH Final No-Camera Runbook

This runbook captures the camera-independent research workflow for GHOST-MH.
It is meant to be reproducible before any Raspberry Pi or real camera test.

## Current Claim

GHOST-MH is not just a single averaged position predictor. Its useful research
behavior is multi-future occlusion prediction: during visual loss, it maintains
several physically plausible target futures and ranks them by probability.

The current calibrated mode-bank tracker should be evaluated by:

- best-future error,
- top-3 future error,
- top-k coverage,
- failure-case structure,
- and only secondarily by the weighted mean point estimate.

The weighted mean can be worse than constant velocity when the belief is
genuinely multi-modal, because averaging separated futures can land between
physically plausible paths.

## Reproducible Commands

Run from the repository root:

```bash
PYTHONPATH=ghost_sim_ros2 python3 ghost_sim_ros2/analysis/ghost_mh_final_no_camera_benchmark.py
```

Expected default benchmark:

- scenarios: straight, turn_left, turn_right, evasive_brake, s_curve, accel_burst, hover_then_escape
- seeds: 7, 11, 19
- occlusion starts: 4.5, 5.5, 7.0, 8.5, 9.5 seconds
- occlusion durations: 0.5, 1.5, 2.5, 3.0 seconds
- total cases: 420
- calibrated acceleration temperature: 0.30
- coverage radius: 0.25 m

Observed result in the no-camera suite:

- calibrated best future beats CV: 387/420
- calibrated top-3 future beats CV: 321/420
- calibrated top-1 coverage at 0.25 m: 72.39%
- calibrated top-3 coverage at 0.25 m: 88.03%
- calibrated any-future coverage at 0.25 m: 95.85%

## Calibration Sweep

Use the sweep to retune branch priors without camera hardware:

```bash
PYTHONPATH=ghost_sim_ros2 python3 ghost_sim_ros2/analysis/ghost_mh_calibration_sweep.py
```

Recent sweep:

| accel temperature | top-3 wins | top-3 coverage | any-future coverage |
|---:|---:|---:|---:|
| 0.20 | 321/420 | 87.70% | 95.85% |
| 0.30 | 321/420 | 88.03% | 95.85% |
| 0.45 | 315/420 | 87.92% | 95.85% |
| 0.65 | 318/420 | 87.71% | 95.85% |
| 0.90 | 318/420 | 87.69% | 95.85% |

The current default is 0.30 because it gives the best top-3 coverage in this
sweep while preserving the best-future win rate.

## Failure Analysis

Generate a failure report:

```bash
PYTHONPATH=ghost_sim_ros2 python3 ghost_sim_ros2/analysis/ghost_mh_failure_analysis.py
```

The current hardest cases are late, long accel_burst occlusions. This is useful:
it identifies the next research target instead of hiding weakness behind a
single aggregate score.

## Future Export

Export ranked future branches for plotting or a later browser/camera overlay:

```bash
PYTHONPATH=ghost_sim_ros2 python3 ghost_sim_ros2/analysis/ghost_mh_export_futures.py \
  --scenario turn_left \
  --seed 7 \
  --occlusion-start 5.5 \
  --occlusion-duration 2.5 \
  --top-n 5
```

The CSV contains truth, CV state, weighted mean state, ranked hypotheses,
hypothesis weights, velocities, covariance entries, and per-hypothesis error.

## Next Research Work

The next no-camera improvements should focus on:

- richer acceleration-burst modes,
- probability calibration after long hidden intervals,
- top-k selection metrics instead of only weighted-mean metrics,
- visualization of branch weights and uncertainty ellipses,
- and real-camera validation only after the no-camera model behavior is stable.
