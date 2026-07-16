# GHOST-X G4 — Controlled-Truth Campaign

## Purpose

G4 supplies a deterministic, time-synchronized software truth campaign before physical controlled-truth collection. It compares the constant-velocity Kalman baseline, formal IMM, and GHOST-MH using the exact same timestamped measurements.

## Predeclared campaign

- 8 trajectory families
- 3 repetitions per family
- 24 paired trials
- fixed 0.1 s sampling
- analytic position and velocity truth
- declared nonzero truth covariance
- correlated two-axis measurement covariance
- deterministic per-trial seeds

Families: stationary, constant velocity, acceleration/deceleration, coordinated arc, stop-and-go, abrupt maneuver, complete occlusion, and repeated re-entry.

## Identical-input control

One canonical JSONL stream is generated per trial. Its SHA-256 hash is stored once and repeated under every estimator input record. Noise is never regenerated per estimator. Estimator outputs are stored separately and also hashed.

## Metrics

Each estimator receives position/velocity RMSE, hidden-interval RMSE, endpoint error, covariance trace and hidden growth, reacquisition time, initialized fraction, resets, and explicit failure state. Aggregate reports include paired differences, bootstrap confidence intervals, and Wilcoxon signed-rank results where valid.

## Blinding and failures

The public aggregate uses `Estimator A/B/C`; the private unblinding key is stored separately. Invalid trials remain in the manifest with a failure reason and are never silently deleted.

## Run

```bash
python3 ghost_sim_ros2/tools/run_ghost_x_g4_campaign.py \
  --out ~/ghost_trials/ghost_x_g4_controlled_truth_v1
```

For development from a dirty tree, add `--allow-dirty`. Report-grade output requires a clean checkout.

Validate:

```bash
python3 ghost_sim_ros2/tools/validate_ghost_x_g4.py \
  --campaign ~/ghost_trials/ghost_x_g4_controlled_truth_v1
```

## Claim boundary

This is deterministic software controlled-truth evidence. It does not establish physical tracking accuracy, real-flight performance, or universal estimator superiority. The separate physical campaign remains required.
