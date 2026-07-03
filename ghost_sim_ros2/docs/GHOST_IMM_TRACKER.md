# GHOST IMM Tracker Runbook

This software-only module adds an Interacting Multiple Model (IMM) tracker reference implementation for GHOST maneuver simulation.

It does not require the Raspberry Pi, camera, AprilTag, or ROS runtime.

## Why This Exists

A single constant-velocity Kalman filter is weak when the target changes motion during occlusion. A multi-hypothesis tracker keeps several explicit futures, while an IMM tracker keeps a compact probability distribution over several motion models.

This gives GHOST a cleaner mathematical bridge between:

- single-model CV tracking,
- mode probability estimation,
- maneuver detection,
- and later multi-future occlusion prediction.

## Current IMM Model

The current implementation uses the shared state:

```text
[x, y, vx, vy]
```

with two same-dimension CV-style process models:

- `smooth_cv`: low process acceleration noise,
- `maneuver_cv`: high process acceleration noise.

The Markov transition matrix controls how likely the tracker is to stay in one mode or switch to another.

## Run

From the repository root:

```bash
cd ghost_sim_ros2
PYTHONPATH="$PWD" python3 analysis/imm_tracker.py
```

Example output:

```text
final maneuver_prob=0.719 smooth_prob=0.281 estimate_x=10.113 truth_x=10.100
```

Export a CSV:

```bash
cd ghost_sim_ros2
PYTHONPATH="$PWD" python3 analysis/imm_tracker.py --out ~/ghost_logs/imm_maneuver.csv
```

CSV fields include:

- time,
- truth position,
- estimated position,
- smooth-mode probability,
- maneuver-mode probability.

## Interpretation

IMM mode probabilities are not object classes. They are probabilities assigned to motion assumptions. A rising `maneuver_cv` probability means the measurements are better explained by a higher-process-noise maneuver model than by the smooth model.

This is useful for GHOST because occlusion prediction should not rely on one hidden-path assumption. The tracker should know whether it is in a smooth, turning, braking, or maneuvering regime before visual contact is lost.

## Current Tests

CI verifies that:

- mode probabilities remain normalized after updates,
- maneuver-mode probability increases after a scripted acceleration,
- combined covariance remains positive semidefinite,
- missing measurements still preserve valid probabilities,
- invalid transition matrices are rejected.

## Next Research Step

The next software-only step is to compare CV, IMM, and multi-hypothesis prediction on the same scripted occlusion benchmark. That will show where compact mode probabilities are enough and where explicit top-k future branches are still needed.
