# Formal IMM Live Integration

This document records the first live integration slice for the regression-hardened
formal IMM estimator.

## Scope

The live integration is additive. It introduces a side-by-side formal IMM node
that consumes the same vision target pose stream as the existing heuristic
tracker and publishes under a separate namespace:

- input: `/ghost/vision/target_pose`
- odometry output: `/ghost/tracker_imm/target_odom`
- futures JSON output: `/ghost/tracker_imm/futures_json`
- status output: `/ghost/tracker_imm/status`

The existing heuristic tracker topics under `/ghost/tracker_mh/*` are left
unchanged. This lets the formal IMM run during live trials without making it the
default control or reporting path.

## Claim Discipline

This integration still uses candidate process and measurement noise parameters.
The reported payload carries the same caveats as the validated IMM modules:

- `ASSUMES_WHITE_GAUSSIAN_RESIDUALS`
- `INVALID_IF_NOISE_IS_COLORED`
- `CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R`
- `FORMAL_IMM_LIVE_BRIDGE_OPTIONAL_NOT_DEFAULT`

The live formal IMM output is suitable for side-by-side collection and
comparison. It is not yet a hardware-calibrated covariance claim, and it should
not replace the heuristic tracker until real Pi/camera residuals have been
checked for R calibration and temporal whiteness.

## Next Validation

Use the trial recorder or a paired comparison harness to collect matching
heuristic and formal-IMM outputs under the same trial conditions. The first live
decision gate should compare position error, dropouts, mode-probability behavior,
and covariance calibration separately rather than relying on a single aggregate
score.
