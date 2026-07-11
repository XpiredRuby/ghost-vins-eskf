# GHOST Career Snippets

Use these statements while physical covariance, measured-grid accuracy, and paired hardware trials remain pending. They distinguish hardware estimation evidence from deterministic software-in-the-loop GNC evidence and do not claim PX4, HIL, vehicle command, flight test, production readiness, or statistically proven tracker superiority.

## Resume bullets

### Concise

- Built a Raspberry Pi/ROS 2 intermittent-visibility target-estimation system using AprilTag measurements, a formal IMM estimator, and a bounded heuristic multi-hypothesis comparison tracker.

### Technical

- Developed a hardware-integrated ROS 2 tracking pipeline with full `2 x 2` measurement-covariance plumbing, formal IMM mode probabilities, MH relative hypothesis weights, explicit prediction-only telemetry, split trial recording, and reproducible hardware replay.

### Results-focused hardware bullet

- Recorded and analyzed a `48.28 s` Raspberry Pi AprilTag run with `655` vision measurements, `13.57 Hz` camera poses, near-`30 Hz` IMM/MH odometry, and documented dropout behavior reaching `77` IMM prediction-only steps and `2.849 s` measurement age.

### GNC software-in-the-loop bullet

- Connected the formal IMM to relative-standoff guidance, acceleration-limited velocity control, actuator lag, follower dynamics, and a `TRACKING` / `PREDICTION` / `SAFE_HOLD` supervisor; deterministic CI scenarios maintained finite output, capped acceleration at `2.5 m/s²`, entered safe hold after prolonged dropout, and reacquired after measurements returned.

### Validation-focused bullet

- Hardened a predeclared 90-second covariance campaign with V4L2 readbacks, live-topic preflight, fixed `15–75 s` analysis, rate/gap quality gates, physical-integrity attestation, fixed sub-window diagnostics, and preserved rejected runs.

### Experimental-methodology bullet

- Designed a predeclared 55-trial paired IMM/MH hardware campaign with unique trial-slot validation, explicit rejection reasons, fixed-seed bootstrap confidence intervals, Wilcoxon reporting, and rules against pooling unlike occlusion durations.

## LinkedIn project description

GHOST is a Raspberry Pi and ROS 2 target-estimation project for intermittent vision. A live AprilTag measurement stream drives a formal Interacting Multiple Model estimator and a bounded heuristic multi-hypothesis tracker side by side. The preserved hardware run contains 48.28 seconds of real pipeline evidence with 655 vision measurements, camera poses at 13.57 Hz, tracker odometry near 30 Hz, and explicit prediction-only/dropout telemetry.

I also connected the repository's formal IMM to a deterministic software-in-the-loop guidance-controller-plant chain with relative-standoff guidance, acceleration-limited control, actuator lag, follower dynamics, a two-second prediction horizon, long-dropout safe hold, and reacquisition. The public GitHub Pages site provides one-click access to the real hardware replay and evidence.

For validation, I implemented a hardened controlled covariance workflow, measured-grid analysis, a predeclared 55-trial paired hardware campaign, bootstrap confidence intervals, Wilcoxon reporting, noisy-null statistical tests, and CI gates. Physical covariance, ground-truth accuracy, and real paired-trial results remain pending, so I do not claim validated real-world accuracy, tracker superiority, real vehicle control, or flight readiness.

## GitHub pinned-repository description

Hardware-integrated ROS 2 target estimation with Raspberry Pi AprilTag sensing, formal IMM tracking, bounded MH futures, dropout telemetry, deterministic closed-loop GNC SIL, validation tooling, and public hardware replay.

## Interview talking points

- I made target loss explicit: measurement age, prediction-only steps, degraded status, and safe-hold state are telemetry or supervisor outputs rather than hidden implementation details.
- The formal IMM publishes valid model probabilities; the heuristic MH tracker publishes relative hypothesis weights, not probabilities.
- Both live trackers consume the same measurement stream, enabling paired comparison under identical inputs.
- The full covariance path supports `R_xx`, `R_xy`, and `R_yy` rather than assuming independent measurement axes.
- I split IMM and MH future logs after identifying that a shared recorder path could silently lose one tracker's evidence.
- I used the same formal IMM in a deterministic guidance-controller-plant loop instead of creating a separate mock estimator.
- The SIL supervisor follows for bounded dropout, commands safe hold after the prediction horizon, and reacquires after measurements return.
- The closed-loop results are explicitly labeled software-in-the-loop, not PX4, HIL, vehicle, or flight results.
- The controlled covariance helper checks the live topic and camera controls before recording, resolves the recorder child directory, applies predeclared rate/gap gates, and preserves rejected runs.
- The paired campaign contains 55 predeclared slots and cannot support a superiority claim until accepted real hardware trials exist.

## STAR story

**Situation:** I wanted GHOST to be more than a smooth AprilTag visualization or simulation-only Kalman filter.

**Task:** Build a hardware-integrated estimator workflow that remained auditable during target occlusion, then demonstrate how the estimator could drive a bounded GNC loop without overstating software evidence as flight validation.

**Action:** I integrated Raspberry Pi AprilTag measurements with ROS 2, implemented and replayed formal IMM and heuristic MH trackers, exposed dropout telemetry, added full covariance plumbing, fixed evidence-recorder separation, built a public replay site, connected the formal IMM to bounded guidance/control and safe hold in deterministic SIL, and predeclared the covariance, grid, and paired-trial campaigns before collection.

**Result:** The preserved hardware run produced `48.28 s` of pipeline evidence with `655` vision measurements, near-`30 Hz` tracker output, and prediction-only behavior through `2.849 s` maximum measurement age. The formal-IMM SIL maintained bounded control, entered `2.0 s` of safe hold in the long-dropout case, and reacquired afterward. The repository now has the collection and statistical infrastructure required to report physical covariance, bias, RMSE, confidence intervals, reacquisition latency, and paired tracker comparisons once hardware trials are collected.

## Current metrics that are safe to mention

### Hardware pipeline

| Metric | Value |
|---|---:|
| Preserved run | `live_camera_calibrated_R_01` |
| Duration | `48.28 s` |
| Vision measurements | `655` |
| Camera pose rate | `13.57 Hz` |
| IMM odometry rate | `30.01 Hz` |
| MH odometry rate | `29.99 Hz` |
| Maximum IMM prediction-only steps | `77` |
| Maximum IMM measurement age | `2.849 s` |

### Deterministic formal-IMM SIL

| Scenario | Final standoff error | Maximum estimator error | Safe-hold time |
|---|---:|---:|---:|
| `nominal_visible` | `0.00114 m` | `0.02673 m` | `0.0 s` |
| `short_dropout` | `0.000353 m` | `0.16357 m` | `0.0 s` |
| `long_dropout_safe_hold` | `0.00986 m` | `0.41683 m` | `2.0 s` |

Always label the second table as deterministic synthetic-truth software-in-the-loop results.

## Claims to avoid until validation is complete

Do not say:

- “validated centimeter-level real-world accuracy”;
- “IMM outperforms MH”;
- “production-ready”;
- “PX4 integrated”;
- “hardware-in-the-loop”;
- “autonomous drone guidance and control”;
- “flight tested”;
- “probabilistic MH predictions.”

Use:

- “hardware-integrated estimation pipeline evidence”;
- “formal IMM mode probabilities”;
- “MH relative hypothesis weights”;
- “deterministic formal-IMM closed-loop GNC software-in-the-loop”;
- “bounded safe-hold behavior in SIL”;
- “physical covariance, ground-truth accuracy, and paired validation pending.”
