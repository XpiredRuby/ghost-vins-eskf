# GHOST Observability + CRLB Runbook

This software-only module checks whether a tracking model is mathematically observable and computes a finite-horizon Cramer-Rao lower bound (CRLB) reference covariance.

It does not require the Raspberry Pi, camera, AprilTag, or ROS runtime.

## Why This Exists

A tracker can look good in a demo while still being mathematically underconstrained. GHOST needs to know when a measurement model can actually infer the hidden state and when it is guessing.

This module provides two design checks:

- observability rank and conditioning for linear state/measurement models,
- Fisher-information and CRLB reference covariance for the initial state over a measurement horizon.

## Default Model

The default CLI uses the 2D constant-velocity state:

```text
[x, y, vx, vy]
```

with x/y position measurements:

```text
z = [x, y]
```

A single position measurement observes only position, not velocity. Two or more time-separated measurements can make the 4-state constant-velocity model observable.

## Run

From the repository root:

```bash
cd ghost_sim_ros2
PYTHONPATH="$PWD" python3 analysis/observability_crlb.py --dt 0.05 --steps 6 --position-std 0.05
```

Expected report fields:

- state dimension,
- measurement dimension,
- horizon steps,
- observability rank,
- observable true/false,
- minimum singular value,
- condition number,
- Fisher-information rank,
- CRLB standard deviations.

For JSON output:

```bash
cd ghost_sim_ros2
PYTHONPATH="$PWD" python3 analysis/observability_crlb.py --json
```

## Interpretation

Use this as a reference design bound, not as a claim that the real camera will hit the bound.

The CRLB assumes:

- a linearized measurement model,
- an unbiased estimator reference,
- independent Gaussian residuals with covariance R,
- and fixed model structure over the horizon.

Real AprilTag/camera measurements can include colored drift, lighting changes, calibration error, motion blur, and detector jitter. Those effects belong in empirical measurement-R validation and NIS testing.

## Research Use

This module supports the software-only GHOST research path by answering:

- How many measurements are needed before velocity is observable?
- How much does tighter measurement R improve the theoretical bound?
- Which states are weakly observable over short horizons?
- Is a candidate measurement model physically underconstrained before hardware testing?

## Current Tests

The CI tests verify that:

- one position step is not enough to observe `[x, y, vx, vy]`,
- two position steps make the CV model observable,
- longer horizons reduce the CRLB covariance trace,
- lower measurement noise reduces the CRLB,
- range/bearing Jacobians match reference values,
- singular geometry at the origin is rejected.
