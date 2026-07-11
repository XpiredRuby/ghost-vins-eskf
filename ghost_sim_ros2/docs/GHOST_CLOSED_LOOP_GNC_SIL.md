# GHOST Closed-Loop GNC Software-in-the-Loop Harness

## Purpose

Connect the existing formal IMM estimator to a bounded guidance law, an acceleration-limited controller, and a simulated follower plant.

This closes a deterministic software loop:

```text
synthetic target truth
        |
        v
noisy / intermittent position measurements
        |
        v
formal GHOST IMM estimator
        |
        v
relative-standoff guidance
        |
        v
velocity controller + acceleration saturation
        |
        v
first-order actuator model + follower dynamics
        |
        +-------------------- closed-loop state feedback
```

The harness is implemented in:

```text
ghost_sim_ros2/analysis/closed_loop_gnc_sil.py
```

## Evidence boundary

Required status:

```text
Integration status: SOFTWARE_IN_THE_LOOP_ONLY
Claims boundary: NO_FLIGHT_OR_HARDWARE_CONTROL_CLAIM
```

The harness demonstrates:

- formal IMM output driving guidance;
- a separate guidance and control layer;
- acceleration and speed limiting;
- simulated actuator lag;
- nominal closed-loop following;
- bounded prediction through short measurement dropout;
- safe hold after the prediction horizon;
- reacquisition after measurement return;
- deterministic replay and machine-readable evidence.

It does not demonstrate:

- PX4 SITL integration;
- hardware-in-the-loop;
- real vehicle dynamics;
- flight control;
- actuator identification;
- safety certification;
- hardware estimator accuracy.

## Why relative-standoff guidance

The current GHOST mission is target following and state supervision, not terminal interception. The harness therefore uses a relative-standoff velocity law rather than the repository's legacy True Proportional Navigation component.

The desired velocity is:

```text
r      = p_target_est - p_follower
e_r    = ||r|| - r_standoff
v_des  = v_target_est + sat(k_r * e_r) * r / ||r||
```

The velocity controller is:

```text
a_cmd = sat(k_v * (v_des - v_follower))
```

The simulated actuator uses a first-order response:

```text
a_dot = (a_cmd - a_achieved) / tau
```

The follower plant then integrates achieved acceleration and applies a small linear drag term.

This is intentionally simple enough to audit. It separates:

1. **Navigation/estimation:** the formal IMM state estimate;
2. **Guidance:** desired relative motion and standoff;
3. **Control:** acceleration-limited velocity tracking;
4. **Plant:** follower kinematics and actuator lag;
5. **Supervision:** tracking, prediction, and safe-hold states.

## Dropout supervisor

The supervisor has three states.

### `TRACKING`

A valid measurement is available. Guidance uses the measurement-updated IMM estimate.

### `PREDICTION`

No measurement is available, but measurement age is within the configured prediction horizon. Guidance uses the formal IMM prediction-only state.

### `SAFE_HOLD`

Measurement age exceeds the prediction horizon. Desired velocity becomes zero and the acceleration-limited controller decelerates the follower.

When measurements return, the supervisor transitions back to `TRACKING` and records a reacquisition.

## Default deterministic scenarios

| Scenario | Measurement dropout | Expected supervisory behavior |
|---|---:|---|
| `nominal_visible` | none | tracking only |
| `short_dropout` | `6.0–7.5 s` | prediction, then reacquisition |
| `long_dropout_safe_hold` | `6.0–10.0 s` | prediction, safe hold, then reacquisition |

Each scenario uses:

- `dt = 0.05 s`;
- `18 s` duration;
- fixed random seed `260710`;
- `0.02 m` candidate measurement standard deviation;
- `2.0 s` prediction horizon;
- `1.5 m` desired target standoff;
- `2.5 m/s²` command-acceleration limit;
- first-order actuator lag;
- the same predeclared target maneuver profile.

The measurement-noise value remains a software-scenario parameter. It is not a replacement for the pending controlled hardware covariance trial.

## Metrics

Each scenario reports:

- final standoff error;
- RMS standoff error after five seconds;
- visible-measurement estimator RMSE;
- maximum estimator error;
- maximum measurement age;
- total safe-hold time;
- reacquisition count;
- maximum commanded and achieved acceleration;
- maximum follower speed;
- minimum target/follower separation;
- command-saturation fraction;
- finite-output check.

The metrics validate deterministic software behavior. They are not hardware performance claims.

## Run

From the repository root:

```bash
python3 ghost_sim_ros2/analysis/closed_loop_gnc_sil.py \
  --out ghost_gnc_sil/manual
```

Expected artifacts:

```text
ghost_gnc_sil/manual/
├── closed_loop_gnc_summary.json
├── closed_loop_gnc_summary.md
├── nominal_visible.csv
├── short_dropout.csv
└── long_dropout_safe_hold.csv
```

## Test

```bash
PYTHONPATH=ghost_sim_ros2 \
python3 -m pytest -q \
  ghost_sim_ros2/test/test_closed_loop_gnc_sil.py
```

The focused tests check:

- nominal closed-loop convergence to a bounded standoff;
- short-dropout prediction without premature safe hold;
- long-dropout safe-hold entry;
- command and speed bounds;
- reacquisition;
- deterministic fixed-seed replay;
- human- and machine-readable artifact export.

## Relationship to the existing ProNav code

The repository's portable C++ `ProNav` component remains part of the historical/legacy guidance architecture and has isolated unit tests. This new harness does not claim that ProNav or its MAVLink wrapper has been closed-loop validated.

A later, separate study may compare:

- relative-standoff following;
- proportional navigation interception;
- truth-fed guidance;
- IMM-fed guidance;
- PX4 SITL control.

Those are future extensions and must retain separate claims and acceptance criteria.
