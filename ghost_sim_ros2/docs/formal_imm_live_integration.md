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

## Dropout Behavior

The bridge does not reset on a short target dropout. After initialization, a
missing measurement advances the IMM with prediction only and publishes
`LIVE_IMM_PREDICTION_ONLY`.

The default degradation threshold is 10 consecutive prediction-only cycles. At
the default 30 Hz live rate, this is about 0.33 s. Once that threshold is
reached, the bridge keeps publishing but changes `live_status` to
`LIVE_IMM_DROPOUT_DEGRADED`. It does not silently trust long open-loop
propagation and it does not reset the estimator without an explicit future
policy.

A valid measurement after degraded dropout immediately returns `live_status` to
`LIVE_IMM_TRACKING` and resets `prediction_only_steps` to 0. The cumulative
dropout counters remain in the payload for trial scoring.

The live dropout metrics are split because short prediction-only gaps and
degraded open-loop propagation are operationally different:

- `prediction_only_rate = prediction_only_cycles / total_initialized_cycles`
- `degraded_dropout_rate = degraded_dropout_cycles / total_initialized_cycles`

`total_initialized_cycles` counts timer cycles after the bridge has received its
first valid measurement. `tracking_cycles`, `prediction_only_cycles`, and
`degraded_dropout_cycles` partition that initialized live time by status.

## Malformed Input Behavior

The ROS wrapper must not die on malformed live measurements. Invalid samples are
rejected, counted, and surfaced in the futures/status payloads while the node
continues running. The current rejection reasons are:

- `REJECT_NONFINITE_MEASUREMENT`
- `REJECT_BEHIND_CAMERA_MEASUREMENT`
- `REJECT_OUT_OF_WORKSPACE_MEASUREMENT`

A rejected sample does not reinitialize the IMM. The next timer cycle either
uses a fresh valid measurement or advances prediction-only status according to
the dropout threshold above.

## Workspace Range Guard

The default workspace range guard is `MAX_WORKSPACE_RANGE_M_DEFAULT = 5.0`.
This is a conservative candidate software guard for bench and room-scale
AprilTag tests. Its status is
`CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_WORKSPACE_RANGE`.

This default should be replaced or confirmed from measured camera geometry,
tag size, mounting, and actual live-trial workspace before report-grade runs.
The current guard prevents obviously impossible live x/y samples from entering
the IMM, but it is not a calibrated sensing-range claim.

## Default-Handoff Gate

The formal IMM should not become the default tracker until paired live evidence
beats or matches the heuristic path under the same trial conditions. The
candidate handoff gate is:

- at least 10 paired live runs per condition
- formal IMM median position RMSE no worse than heuristic MH median RMSE
- formal IMM 95% bootstrap confidence interval on RMSE difference excludes a
  regression larger than 5%
- no higher `degraded_dropout_rate` than the heuristic tracker under the same
  trial condition
- hardware-data 2-sigma coverage at or above 0.90 after R calibration and
  residual-color caveat review

These are candidate gates pending hardware characterization; they are meant to
make the default handoff auditable rather than automatic.

## Next Validation

Use the trial recorder or a paired comparison harness to collect matching
heuristic and formal-IMM outputs under the same trial conditions. The first live
decision gate should compare position error, dropouts, mode-probability behavior,
and covariance calibration separately rather than relying on a single aggregate
score.
