# GHOST Software-Regime Audit

## Verdict

The Pi/live prototype can stay frozen. The next valid engineering step is offline software validation.

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

## What this package implements

### 1. Stationary gate

A rolling least-squares velocity classifier over a 1.5 s window.

Why not adjacent-frame differencing? Because pose noise is temporally correlated and low-frequency. A best-fit window is less fragile.

Parameters:

| Parameter | Value |
|---|---:|
| stationary_window_s | 1.5 |
| stationary_enter_speed_mps | 0.08 |
| stationary_exit_speed_mps | 0.14 |
| stationary_min_samples | 5 |

The enter/exit thresholds are intentionally hysteretic. They are based on the measured stationary apparent-speed noise, not the earlier theoretical 0.015–0.030 m/s values.

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
constant_velocity_hide_reveal
move_then_stop_behind_wall
lateral_hidden_motion
long_occlusion_reset
false_measurement_jump
```

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
```

The most important metric is `stationary_false_motion_mps`.

For stationary occlusion, this should be near zero.

## Acceptance gates

Before Pi testing resumes:

| Gate | Required result |
|---|---|
| stationary_hide_reveal | PASS |
| constant_velocity_hide_reveal | PASS |
| move_then_stop_behind_wall | PASS |
| lateral_hidden_motion | PASS |
| long_occlusion_reset | PASS |
| false_measurement_jump | PASS |
| replay.html generated | PASS |
| summary.md generated | PASS |

## Engineering wording for the repo

Use this wording:

> GHOST V1 is a calibrated vision-only AprilTag occlusion tracker with a heuristic multi-hypothesis motion bank. During visual occlusion it maintains bounded, ranked beliefs and explicitly distinguishes measurement, prediction, and unknown hidden state.

Avoid this wording:

> GHOST tracks hidden targets perfectly.

Avoid claiming formal MHT/IMM until V2 has likelihood-weighted model transition/update math and a formal model probability recursion.

Avoid claiming ESKF/VINS/IMU fusion until V3 actually consumes IMU data.
