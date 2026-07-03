# GHOST Software-Regime Audit

## Verdict

The Pi/live prototype can stay frozen while the software-regime harness is reviewed and hardened.

This PR should be read as a **candidate offline harness**, not final report-grade validation.

The current known problem is not camera bring-up. It is tracker honesty:

```text
stationary visible target -> target hidden -> dashboard should not invent dominant motion
```

Correct V1 behavior:

```text
HIDDEN - STATIONARY HOLD
last measured position held
uncertainty grows
dynamic hypotheses suppressed
no claim of true hidden-state measurement
```

## Critical caveat

A generated `PASS` from this harness currently means:

```text
the candidate implementation passed synthetic known-truth regression gates
```

It does **not** yet mean:

```text
the real hardware tracker is validated under measured camera noise
```

The generated `summary.md`, `summary.json`, and `replay.html` carry the status string:

```text
CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R
```

That caveat is intentionally embedded into the artifacts so it cannot be separated from the results.

## What this package implements

### 1. Stationary gate

A rolling least-squares velocity classifier over a 1.5 s window.

Why not adjacent-frame differencing? Because pose noise is temporally correlated and low-frequency. A best-fit window is less fragile.

Candidate parameters:

| Parameter | Value | Status |
|---|---:|---|
| stationary_window_s | 1.5 | candidate |
| stationary_enter_speed_mps | 0.065 | from reviewed empirical range, pending committed calibration artifact |
| stationary_exit_speed_mps | 0.090 | from reviewed empirical range, pending committed calibration artifact |
| stationary_min_samples | 5 | candidate |

The enter/exit thresholds are intentionally hysteretic. The numbers are now aligned with the reviewed empirical stationary-noise range discussed earlier, but they are still not final until backed by committed hardware-calibration data.

### 2. Stationary-hold behavior

When the target was stationary before occlusion:

```text
rank 1: stationary_hold, P=0.95
rank 2: brake_hover, P=0.03
rank 3: constant_velocity_suppressed, P=0.02
```

The path remains at the last visible position. Only uncertainty grows.

### 3. Dynamic hypothesis bank

When the target was moving before occlusion:

```text
constant_velocity
brake_hover
accelerate_forward
lateral_left
lateral_right
turn_left
turn_right
```

This remains a heuristic bank, not formal IMM/MHT.

### 4. Known-truth simulation

Scenarios included:

```text
stationary_hide_reveal
stationary_colored_noise_hide_reveal
constant_velocity_hide_reveal
move_then_stop_behind_wall
lateral_hidden_motion
long_occlusion_reset
single_outlier_white_noise
```

`single_outlier_white_noise` is deliberately named narrowly. It is not a general false-measurement robustness claim.

`stationary_colored_noise_hide_reveal` uses synthetic AR(1) drift. It is a useful placeholder regression, but it is not yet the real Allan/PSD hardware replay.

### 5. Metrics

The offline validator reports:

```text
RMSE
95th percentile error
top-1 future terminal error
top-3 best future terminal error
stationary_false_motion_mps
stationary_hold_fraction_hidden
reset_count
threshold_status
threshold_provenance
```

The most important metric is `stationary_false_motion_mps`.

For stationary occlusion, this should be near zero.

### 6. Explicit acceptance gates

The pass/fail gates are now centralized in `RegimeConfig` rather than hidden as bare magic numbers inside scoring logic:

```text
stationary_false_motion_limit_mps = 0.01
stationary_prior_min = 0.90
stationary_hold_fraction_min = 0.80
stop_wall_top3_limit_m = 0.40
lateral_top3_limit_m = 0.60
visible_rmse_limit_m = 0.10
```

These are explicit candidate V1 requirements/placeholders. They still need formal traceability to the design report before a PASS is used as report-grade evidence.

## Acceptance gates

Before citing this harness in the project report:

| Gate | Required result |
|---|---|
| stationary_hide_reveal | PASS |
| stationary_colored_noise_hide_reveal | PASS |
| constant_velocity_hide_reveal | PASS |
| move_then_stop_behind_wall | PASS |
| lateral_hidden_motion | PASS |
| long_occlusion_reset | PASS |
| single_outlier_white_noise | PASS |
| pytest all-scenario gate | PASS |
| replay.html generated | PASS |
| summary.md generated with caveat | PASS |

## Remaining work before report-grade validation

1. Commit the real hardware noise-calibration artifact or parameter file.
2. Replace or supplement synthetic AR(1) drift with measured colored-noise replay.
3. Trace each acceptance gate to a stated engineering requirement.
4. Port the reviewed stationary-hold behavior into the live ROS tracker in a separate PR.
5. Keep the claim limited to calibrated vision-only heuristic hypothesis tracking until formal IMM/MHT/ESKF/VINS work exists.

## Engineering wording for the repo

Use this wording:

> GHOST V1 is a calibrated vision-only AprilTag occlusion tracker with a heuristic multi-hypothesis motion bank. During visual occlusion it maintains bounded, ranked beliefs and explicitly distinguishes measurement, prediction, and unknown hidden state.

Avoid this wording:

> GHOST tracks hidden targets perfectly.

Avoid claiming formal MHT/IMM until V2 has likelihood-weighted model transition/update math and a formal model probability recursion.

Avoid claiming ESKF/VINS/IMU fusion until V3 actually consumes IMU data.
