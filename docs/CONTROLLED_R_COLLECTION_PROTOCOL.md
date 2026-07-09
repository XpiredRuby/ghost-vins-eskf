# Controlled R Collection Protocol

## Purpose

Estimate the measurement covariance `R` for AprilTag position measurements under locked, controlled, stationary conditions.

This protocol estimates measurement noise only. It does not validate tracker accuracy.

## Git Pre-Declaration Rule

This file must be committed before data collection begins.

The analysis window is fixed before seeing data: record exactly 90 seconds and analyze seconds 15-75. The first and last 15 seconds are fixed settling buffers.

Do not change the analysis window after inspecting results. Do not edit this protocol after data collection begins. If the protocol must change, start a new protocol commit and collect a new trial under that new committed protocol.

## Camera-Control Lock and Readback

Use `/dev/video0` unless an override is recorded before collection.

Before collection, attempt to lock or set these camera controls if supported:

```bash
v4l2-ctl -d /dev/video0 --set-ctrl=exposure_auto=1
v4l2-ctl -d /dev/video0 --set-ctrl=exposure_absolute=<fixed_value>
v4l2-ctl -d /dev/video0 --set-ctrl=white_balance_temperature_auto=0
v4l2-ctl -d /dev/video0 --set-ctrl=white_balance_temperature=<fixed_value>
v4l2-ctl -d /dev/video0 --set-ctrl=focus_auto=0
v4l2-ctl -d /dev/video0 --set-ctrl=focus_absolute=<fixed_value>
```

Read back and log camera controls:

```bash
v4l2-ctl -d /dev/video0 --all
v4l2-ctl -d /dev/video0 --list-ctrls
```

Required readback logs:

- Before setting controls.
- After setting controls.
- After the 90 second trial.

If a camera control is unsupported, record that explicitly instead of pretending it was locked.

## Physical Setup

- Camera rigidly mounted.
- AprilTag rigidly mounted.
- Tag fronto-parallel to the camera if practical.
- Standoff distance measured and recorded.
- Lighting kept constant.
- No touching the table, camera, or tag during logging.

## Trial Rule

- Record exactly 90 seconds.
- Use seconds 15-75 for `R` analysis.
- First and last 15 seconds are fixed settling buffers.
- No post-hoc trimming.

## Analysis

Use raw `x`/`y` residual covariance from the fixed seconds 15-75 analysis window.

Report:

- `R_xx`
- `R_xy`
- `R_yy`
- Correlation coefficient
- Sub-window stability checks for seconds 15-35, 35-55, and 55-75

If detrending diagnostics exist, report raw and detrended diagnostics separately. The source used for `R` must be clearly declared, and the primary controlled `R` source is the raw residual covariance unless a later predeclared protocol says otherwise.

## Required Outputs

- `camera_controls_before.txt`
- `camera_controls_after_set.txt`
- `camera_controls_after_trial.txt`
- Raw stationary log, JSONL, or CSV
- `noise_summary.md`
- `noise_summary.json`
- Protocol file commit hash

## Failure Criteria

Reject the trial if any of these occur:

- Camera controls drift.
- Accidental movement occurs.
- The tag or camera is touched during logging.
- Logging drops below the acceptable rate declared in the run log.
- An unsupported camera lock is not documented.

## Status Language

R status: CONTROLLED_R_PREDECLARED_PENDING_COLLECTION

Accuracy status: DOES_NOT_VALIDATE_TRACKER_ACCURACY
