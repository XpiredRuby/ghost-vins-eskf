# GHOST-MH Research Plan

GHOST-MH is the no-camera research core for the next project phase. The goal is
not AprilTag detection. The goal is probabilistic occlusion-survivable target
tracking for drone-like objects using physics-backed multiple hypotheses.

## Research Claim

During temporary visual loss, GHOST-MH should maintain several physically
plausible target futures, assign a relative hypothesis weight to each future, and collapse back
onto the most likely branch when the target is reacquired.

The tracker must beat these baselines on controlled occlusion trials:

1. Detector-only: no prediction while hidden.
2. Last-seen hold: freezes at the last measurement.
3. Single-model constant-velocity Kalman filter.
4. GHOST-MH: relative-weighted multiple physics hypotheses.

## Current No-Camera Implementation

The first research implementation is pure Python:

```bash
cd ghost_sim_ros2
python3 analysis/ghost_mh_benchmark.py
```

Outputs:

- CSV time history with truth, errors, hypothesis count, and top model.
- Occlusion RMSE for last-seen hold, CV Kalman, and GHOST-MH.
- Reacquisition-window RMSE after the target becomes visible again.

## GHOST-MH v1 Model Bank

State:

```text
x = [px, py, vx, vy]^T
```

Measurement:

```text
z = [px, py]^T
```

Motion hypotheses:

| Hypothesis | Purpose |
|---|---|
| constant_velocity | Nominal straight-line continuation |
| brake_or_hover | Drone slows or pauses during occlusion |
| coordinated_turn_left | Target decelerates forward while turning left |
| coordinated_turn_right | Target decelerates forward while turning right |
| accelerate_forward | Target increases downrange velocity |
| accelerate_left | Lateral left maneuver |
| accelerate_right | Lateral right maneuver |
| evasive_maneuver | High-process-noise fallback for unmodeled motion |

Prediction branches each surviving hypothesis through the model bank during
occlusion. Each branch carries a Gaussian state belief and a scalar relative hypothesis weight.
On reacquisition, each branch is scored by measurement likelihood and normalized.

## Acceptance Criteria For Strong Graduate-Level Milestone

GHOST-MH should not be considered graduate-research complete until it has:

1. Synthetic benchmark with repeatable random seeds.
2. At least three scripted trajectories: straight, turn, and evasive.
3. At least three occlusion durations: 0.5 s, 1.5 s, and 3.0 s.
4. Quantitative comparison against detector-only, last-seen hold, and CV Kalman.
5. Evidence that GHOST-MH reduces occlusion RMSE or reacquisition error on
   maneuvering targets.
6. Failure cases where GHOST-MH does not win, with explanation.
7. ROS2 node wrapping the same estimator after the no-camera benchmark is stable.
8. Hardware validation using the existing AprilTag camera measurement source.
9. Later replacement of AprilTag measurements with real object detections.

## PhD-Level Direction

Using an IMM or particle filter is not automatically novel. The PhD-level step is
to add a defensible contribution, such as:

- occlusion-aware branch weights learned from motion context,
- physics-constrained relative-weight pruning,
- explicit visibility/occluder likelihood,
- uncertainty visualization tied to real-time decision-making,
- a custom GHOST occlusion dataset and benchmark.

The near-term objective is a strong graduate research prototype. The long-term
objective is a new occlusion-aware target tracking method with measured
improvement over standard baselines.
