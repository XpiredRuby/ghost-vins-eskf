# GHOST Portfolio Packet

## One-sentence summary

GHOST is a Raspberry Pi and ROS 2 target-estimation system that uses AprilTag measurements to compare a formal Interacting Multiple Model estimator with a bounded heuristic multi-hypothesis tracker during temporary target occlusion.

## Why the project exists

A detector only reports a target while the target is visible. A tracking system must maintain a state estimate, represent uncertainty, distinguish live measurement updates from prediction-only propagation, and recover cleanly after observations return.

GHOST was built to demonstrate that complete engineering chain:

```text
camera measurement
        ->
state estimation
        ->
dropout-aware prediction
        ->
ROS 2 telemetry
        ->
recorded evidence
        ->
replay and analysis
```

## What is implemented

- Raspberry Pi AprilTag pose measurements published into ROS 2.
- Formal IMM state estimation with valid mode probabilities and covariance propagation.
- GHOST-MH bounded future hypotheses with relative hypothesis weights.
- Explicit visible, prediction-only, and degraded-dropout status telemetry.
- Full symmetric `2 x 2` measurement covariance plumbing.
- Split IMM/MH trial recording to prevent evidence loss.
- Hardware-bag plotting and a dependency-free replay dashboard.
- Controlled covariance, ground-truth grid, and paired statistical analysis tooling.
- Automated Python and portable C++ tests through GitHub Actions.

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

The evidence demonstrates live pipeline operation, real-time publication, target-loss state transitions, prediction-only propagation, and reacquisition. It does not establish ground-truth tracking accuracy.

## Technical differentiators

### Formal estimator, not only a visual effect

The IMM executes model-conditioned filtering, model mixing, probability updates, and combined state/covariance output. Tracker status makes the distinction between measurement-backed tracking and open-loop prediction explicit.

### Honest comparison baseline

GHOST-MH is retained as a heuristic contextual tracker. Its candidate rankings are called relative hypothesis weights rather than probabilities. The repository does not present the heuristic output as formal Bayesian certainty.

### Validation designed before data collection

The controlled covariance protocol fixes the collection duration and analysis window before new data are observed. The ground-truth protocol specifies measured grid points and required metrics. This prevents selecting favorable windows or metrics after seeing results.

### Reviewable without ROS

The final hardware bag is converted into plots, Markdown reports, exported JSON, and a static HTML replay. A reviewer can inspect the engineering evidence without installing the full runtime stack.

## GNC relevance and current boundary

GHOST demonstrates the navigation/estimation portion of GNC:

- measurement and covariance modeling;
- target state estimation;
- motion-model interaction;
- uncertainty propagation;
- sensor dropout handling;
- estimator health/status telemetry;
- downstream state and setpoint interfaces.

A validated guidance law and closed-loop controller are not part of the current hardware evidence. The repository therefore does not claim full autonomous vehicle control or flight readiness.

## Validation status

| Question | Current answer |
|---|---|
| Does the camera-to-ROS-to-tracker pipeline run on hardware? | Yes |
| Do both trackers publish at real-time rates? | Yes |
| Are dropout and stale-measurement states exposed? | Yes |
| Is full covariance metadata wired through the live trackers? | Yes |
| Is controlled stationary covariance finalized? | No — collection pending |
| Is position accuracy measured against physical truth? | No — grid trial pending |
| Is IMM statistically superior to MH? | No claim — harness exists, real paired trials pending |
| Is the system closed-loop on a vehicle? | No |

## Reviewer paths

- Root overview: [`../../README.md`](../../README.md)
- Full technical report: [`GHOST_PROJECT_REPORT.md`](GHOST_PROJECT_REPORT.md)
- Hardware plots: [`GHOST_LIVE_BAG_PLOTS.md`](GHOST_LIVE_BAG_PLOTS.md)
- Replay dashboard: [`GHOST_LIVE_REPLAY_DASHBOARD.html`](GHOST_LIVE_REPLAY_DASHBOARD.html)
- Career snippets: [`GHOST_CAREER_SNIPPETS.md`](GHOST_CAREER_SNIPPETS.md)
- Controlled covariance protocol: [`../../docs/CONTROLLED_R_COLLECTION_PROTOCOL.md`](../../docs/CONTROLLED_R_COLLECTION_PROTOCOL.md)
- Ground-truth grid protocol: [`GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md`](GROUND_TRUTH_GRID_VALIDATION_PROTOCOL.md)

## Current portfolio statement

> Built a Raspberry Pi/ROS 2 intermittent-visibility target-estimation pipeline with a formal IMM estimator, a bounded heuristic MH comparison tracker, explicit dropout-state telemetry, full measurement-covariance plumbing, and reproducible hardware replay artifacts; controlled covariance and ground-truth accuracy validation are predeclared and pending physical collection.
