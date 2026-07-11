# GHOST Portfolio Packet

## One-sentence summary

GHOST is a USB-webcam, Raspberry Pi, and ROS 2 intermittent-visibility target-estimation system that compares a formal Interacting Multiple Model estimator with a bounded heuristic multi-hypothesis tracker, then connects the same formal IMM to a deterministic software-in-the-loop guidance, control, and long-dropout safe-hold chain.

## What the project demonstrates

A detector only reports a target while it is visible. A useful estimation and autonomy stack must maintain state, represent uncertainty, distinguish measurement-backed updates from open-loop prediction, constrain stale estimates, recover after observations return, and preserve enough telemetry to audit the behavior.

GHOST demonstrates that chain in real hardware:

```text
AprilTag target
        ->
standard USB UVC webcam + V4L2
        ->
Raspberry Pi / ROS 2 pose measurement
        ->
formal IMM and heuristic GHOST-MH tracking
        ->
dropout supervision and reacquisition
        ->
recorded evidence and public replay
```

and separately in deterministic simulation:

```text
formal IMM estimate
        ->
relative-standoff guidance
        ->
acceleration-limited control
        ->
actuator lag and follower dynamics
        ->
TRACKING / PREDICTION / SAFE_HOLD supervision
```

## What is implemented

### Hardware estimation

- Standard USB UVC webcam through Linux V4L2; CSI is not the active sensor path.
- Calibrated AprilTag pose measurements published into ROS 2.
- Formal IMM state estimation with valid mode probabilities and covariance propagation.
- GHOST-MH bounded future hypotheses with relative hypothesis weights.
- Explicit visible, prediction-only, degraded-dropout, measurement-age, and reacquisition telemetry.
- Full symmetric `2 x 2` measurement covariance plumbing.
- Split IMM/MH trial recording and preserved hardware replay.

### GNC software-in-the-loop

- The repository's actual formal IMM drives relative-standoff guidance.
- Acceleration-limited velocity control.
- First-order actuator lag and follower dynamics.
- Bounded prediction horizon.
- Long-dropout safe hold and reacquisition.
- Deterministic fixed-seed CI evidence.

### Validation and evidence infrastructure

- Hardened controlled covariance collection with V4L2 readbacks, fixed windows, rate/gap gates, and physical-integrity attestation.
- Six-point measured-grid bias/RMSE analysis and discrete spatial-error visuals.
- Predeclared 55-slot paired IMM/MH campaign.
- Balanced randomized campaign initialization and local visual/audio conductor.
- Immutable precollection plan plus separately audited accepted/rejected outcomes.
- Condition-specific paired analysis, confidence intervals, failures, and mechanically selected representative runs.
- USB timing and Raspberry Pi resource characterization tools.
- SHA-256 evidence packaging and tamper verification.
- Formal parameter/file lock and machine-readable public claims gate.
- Dependency-gated physical-session runbook and three-take hero protocol.
- Public GitHub Pages showcase and USB hardware/BOM page.

## Preserved hardware evidence

The run `live_camera_calibrated_R_01` contains real USB-webcam AprilTag measurements and simultaneous formal IMM / GHOST-MH outputs.

| Metric | Value |
|---|---:|
| Duration | `48.28 s` |
| Vision measurements | `655` |
| Camera pose rate | `13.57 Hz` |
| IMM odometry rate | `30.01 Hz` |
| MH odometry rate | `29.99 Hz` |
| Maximum IMM prediction-only steps | `77` |
| Maximum IMM measurement age | `2.849 s` |

The evidence demonstrates live pipeline operation, real-time publication, target-loss state transitions, prediction-only propagation, degraded-dropout labeling, and reacquisition. It does not establish ground-truth tracking accuracy.

## Formal-IMM closed-loop GNC SIL evidence

| Scenario | Final standoff error | RMS standoff error after 5 s | Maximum estimator error | Safe-hold time |
|---|---:|---:|---:|---:|
| `nominal_visible` | `0.00114 m` | `0.05319 m` | `0.02673 m` | `0.0 s` |
| `short_dropout` | `0.000353 m` | `0.05535 m` | `0.16357 m` | `0.0 s` |
| `long_dropout_safe_hold` | `0.00986 m` | `0.31648 m` | `0.41683 m` | `2.0 s` |

The long-dropout scenario enters safe hold after the `2.0 s` prediction horizon and reacquires after measurements return. Command acceleration remains bounded by `2.5 m/s²`.

These are deterministic synthetic-truth software-in-the-loop results—not PX4, HIL, vehicle, or flight results.

## Technical differentiators

### Formal estimator rather than a visual effect

The IMM executes model-conditioned filtering, state/covariance mixing, likelihood-based mode-probability updates, and combined state/covariance output. Status exposes whether the estimate is measurement-backed, prediction-only, or degraded.

### Honest heuristic comparison

GHOST-MH is retained as a transparent operational baseline. Its candidate rankings are relative hypothesis weights rather than probabilities; the project does not present them as formal Bayesian certainty.

### The same estimator drives the GNC loop

The deterministic guidance-controller-plant harness uses the actual formal IMM implementation instead of a separate mock. The software boundary is explicit and does not inflate SIL into flight-control evidence.

### Experimental design before data

Collection duration, fixed covariance windows, physical grid metrics, trial conditions, randomization, rejection rules, paired statistics, representative-run selection, and release claims were defined before the decisive physical data exist.

### Immutable intent and auditable outcomes

The formal campaign's manifest and randomized order are hash-locked. Accepted/rejected outcomes live in a separate mutable state with append-only amendments, preventing post-hoc rewriting of what was planned.

### Reproducible and reviewable

Recruiters can open the public replay and hardware page without ROS. Engineers can inspect raw-data schemas, tests, protocols, checksums, parameter locks, analysis definitions, and explicit limitations.

## Current validation status

| Question | Current answer |
|---|---|
| Is the active camera a USB UVC webcam? | Yes; exact manufacturer/model pending physical inventory |
| Does the USB-camera-to-ROS-to-tracker pipeline run on hardware? | Yes |
| Do both trackers publish at real-time rates? | Yes |
| Are dropout and stale-measurement states exposed? | Yes |
| Is full covariance metadata wired through both live trackers? | Yes |
| Is there a closed-loop estimator-guidance-controller-plant demonstration? | Yes—deterministic SIL |
| Does prolonged dropout trigger safe hold in SIL? | Yes |
| Is all meaningful hardware-free preparation complete? | Yes |
| Is controlled stationary covariance finalized? | No—physical collection pending |
| Is position accuracy measured against physical truth? | No—six-point grid pending |
| Is IMM statistically superior to MH? | No claim—55-slot campaign pending |
| Does the system command a real vehicle? | No |
| Has it been flight tested? | No |

## Reviewer paths

- [Public showcase](https://xpiredruby.github.io/ghost-vins-eskf/)
- [Interactive hardware replay](https://xpiredruby.github.io/ghost-vins-eskf/demo.html)
- [Hardware & BOM](https://xpiredruby.github.io/ghost-vins-eskf/hardware.html)
- [Root README](../../README.md)
- [Full technical report](GHOST_PROJECT_REPORT.md)
- [Hardware-free completion status](GHOST_HARDWARE_FREE_COMPLETION.md)
- [Closed-loop GNC SIL](GHOST_CLOSED_LOOP_GNC_SIL.md)
- [Master physical-validation runbook](GHOST_PHYSICAL_VALIDATION_MASTER_RUNBOOK.md)
- [Campaign analysis](GHOST_CAMPAIGN_ANALYSIS.md)
- [Evidence integrity](GHOST_EVIDENCE_INTEGRITY.md)
- [Public claims review](GHOST_RELEASE_CLAIMS_REVIEW.md)

## Current portfolio statement

> Built a USB UVC webcam/Raspberry Pi/ROS 2 intermittent-visibility target-estimation system with a formal IMM, heuristic GHOST-MH comparison tracker, full covariance plumbing, explicit dropout telemetry, reproducible hardware replay, and a deterministic formal-IMM closed-loop GNC software-in-the-loop harness with bounded control and long-dropout safe hold; also predeclared and automated the covariance, physical-grid, 55-slot paired-trial, timing, integrity, parameter-lock, and release-claims workflows required for defensible hardware validation.
