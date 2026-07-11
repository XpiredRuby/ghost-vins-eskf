# GHOST Portfolio Packet

## One-sentence summary

GHOST is a Raspberry Pi and ROS 2 target-estimation system that compares a formal Interacting Multiple Model estimator with a bounded heuristic multi-hypothesis tracker during temporary AprilTag occlusion, then connects the formal IMM to a deterministic software-in-the-loop guidance, control, and safe-hold chain.

## Why the project exists

A detector only reports a target while the target is visible. A useful tracking and autonomy stack must maintain state, represent uncertainty, distinguish measurement-backed updates from prediction-only propagation, constrain stale estimates, and recover cleanly after observations return.

GHOST was built to demonstrate that engineering chain:

```text
real camera measurement
        ->
formal and heuristic target estimation
        ->
dropout supervision
        ->
ROS 2 telemetry and evidence
```

and, separately in deterministic simulation:

```text
formal IMM estimate
        ->
relative-standoff guidance
        ->
bounded velocity control
        ->
actuator lag and follower dynamics
        ->
tracking / prediction / safe hold
```

## What is implemented

- Raspberry Pi AprilTag pose measurements published into ROS 2.
- Formal IMM state estimation with valid mode probabilities and covariance propagation.
- GHOST-MH bounded future hypotheses with relative hypothesis weights.
- Explicit visible, prediction-only, and degraded-dropout status telemetry.
- Full symmetric `2 x 2` measurement covariance plumbing.
- Split IMM/MH trial recording to prevent evidence loss.
- Hardware-bag plotting, exported JSON, and a dependency-free replay dashboard.
- Public GitHub Pages showcase for one-click review.
- Deterministic formal-IMM closed-loop GNC software-in-the-loop harness.
- Bounded acceleration, actuator lag, follower dynamics, prediction horizon, safe hold, and reacquisition in SIL.
- Hardened controlled covariance collection with V4L2 readbacks, timing gates, fixed-window analysis, and physical-integrity attestation.
- Measured-grid accuracy analysis and a predeclared 55-trial paired IMM/MH hardware campaign.
- Automated Python, portable C++, GNC SIL, and collection-pipeline tests through GitHub Actions.

## Preserved hardware evidence

The run `live_camera_calibrated_R_01` contains real AprilTag measurements and simultaneous IMM/MH outputs.

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

The dedicated Actions workflow executes three fixed-seed scenarios through the repository's actual formal IMM.

| Scenario | Final standoff error | RMS standoff error after 5 s | Maximum estimator error | Safe-hold time |
|---|---:|---:|---:|---:|
| `nominal_visible` | `0.00114 m` | `0.05319 m` | `0.02673 m` | `0.0 s` |
| `short_dropout` | `0.000353 m` | `0.05535 m` | `0.16357 m` | `0.0 s` |
| `long_dropout_safe_hold` | `0.00986 m` | `0.31648 m` | `0.41683 m` | `2.0 s` |

The long-dropout scenario enters safe hold after the `2.0 s` prediction horizon and reacquires after measurements return. Command acceleration remains bounded by `2.5 m/s²`.

These are deterministic synthetic-truth software-in-the-loop results. They are not PX4, HIL, hardware-controller, vehicle, or flight results.

## Technical differentiators

### Formal estimator, not only a visual effect

The IMM executes model-conditioned filtering, state/covariance mixing, likelihood-based mode-probability updates, and combined state/covariance output. Tracker status exposes whether the estimate is measurement-backed, prediction-only, or degraded.

### Honest comparison baseline

GHOST-MH is retained as a heuristic contextual tracker. Its candidate rankings are relative hypothesis weights rather than probabilities. The repository does not present heuristic output as formal Bayesian certainty.

### Closed-loop integration with explicit scope

The same formal IMM is used in a deterministic guidance-controller-plant loop with acceleration saturation, actuator lag, prediction-horizon supervision, safe hold, and reacquisition. The project calls this software-in-the-loop evidence and does not inflate it into a flight-control claim.

### Validation designed before data collection

The controlled covariance protocol fixes duration and the `15–75 s` analysis window before new data are observed. The hardened helper records physical setup, camera controls, timing criteria, sample gaps, fixed subwindows, and operator attestation. The paired campaign predeclares 55 trial slots, rejection handling, metrics, bootstrap seed, and condition-specific analysis.

### Reviewable without ROS

The hardware bag is converted into plots, Markdown reports, JSON, and a static HTML replay. Recruiters can use the public GitHub Pages site; engineers can inspect the reports, protocols, tests, and source.

## GNC relevance and current boundary

GHOST now demonstrates:

- hardware-integrated navigation/estimation;
- measurement and covariance handling;
- formal multiple-model state estimation;
- uncertainty and stale-measurement supervision;
- deterministic software-only guidance and control;
- acceleration limits and actuator lag;
- safe hold after prolonged dropout;
- estimator-driven reacquisition.

It does not demonstrate:

- PX4 SITL or hardware-in-the-loop;
- real vehicle command;
- validated real vehicle dynamics;
- flight control or flight test;
- production safety or certification.

## Validation status

| Question | Current answer |
|---|---|
| Does the camera-to-ROS-to-tracker pipeline run on hardware? | Yes |
| Do both trackers publish at real-time rates? | Yes |
| Are dropout and stale-measurement states exposed? | Yes |
| Is full covariance metadata wired through the live trackers? | Yes |
| Is there a closed-loop estimator-guidance-controller-plant demonstration? | Yes — deterministic SIL |
| Does prolonged dropout trigger safe hold in SIL? | Yes |
| Is controlled stationary covariance finalized? | No — hardened collection pending physical run |
| Is position accuracy measured against physical truth? | No — grid trial pending |
| Is IMM statistically superior to MH? | No claim — 55-trial campaign pending |
| Does the system command a real vehicle? | No |
| Has it been flight tested? | No |

## Reviewer paths

- Public showcase: [GHOST GitHub Pages](https://xpiredruby.github.io/ghost-vins-eskf/)
- Root overview: [`../../README.md`](../../README.md)
- Full technical report: [`GHOST_PROJECT_REPORT.md`](GHOST_PROJECT_REPORT.md)
- Hardware plots: [`GHOST_LIVE_BAG_PLOTS.md`](GHOST_LIVE_BAG_PLOTS.md)
- Replay dashboard: [`GHOST_LIVE_REPLAY_DASHBOARD.html`](GHOST_LIVE_REPLAY_DASHBOARD.html)
- Closed-loop GNC SIL: [`GHOST_CLOSED_LOOP_GNC_SIL.md`](GHOST_CLOSED_LOOP_GNC_SIL.md)
- Career snippets: [`GHOST_CAREER_SNIPPETS.md`](GHOST_CAREER_SNIPPETS.md)
- Controlled covariance protocol: [`../../docs/CONTROLLED_R_COLLECTION_PROTOCOL.md`](../../docs/CONTROLLED_R_COLLECTION_PROTOCOL.md)
- Controlled collection runbook: [`CONTROLLED_R_COLLECTION_RUNBOOK.md`](CONTROLLED_R_COLLECTION_RUNBOOK.md)
- Ground-truth grid protocol: [`GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md`](GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md)
- Paired campaign protocol: [`IMM_MH_HARDWARE_CAMPAIGN_PROTOCOL.md`](IMM_MH_HARDWARE_CAMPAIGN_PROTOCOL.md)

## Current portfolio statement

> Built a Raspberry Pi/ROS 2 intermittent-visibility target-estimation system with a formal IMM, heuristic MH comparison tracker, explicit dropout telemetry, full covariance plumbing, reproducible hardware replay, and a deterministic formal-IMM closed-loop GNC software-in-the-loop harness with bounded control and long-dropout safe hold; physical covariance, ground-truth accuracy, and paired hardware validation remain predeclared and pending collection.
