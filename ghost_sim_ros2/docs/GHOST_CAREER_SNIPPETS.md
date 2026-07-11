# GHOST Career Snippets

Use these statements only while the controlled covariance and measured ground-truth trials remain pending. They describe the current evidence without claiming validated accuracy, tracker superiority, closed-loop control, flight test, or production readiness.

## Resume bullets

### Concise

- Built a Raspberry Pi/ROS 2 target-estimation pipeline using AprilTag measurements, a formal IMM estimator, and a bounded heuristic multi-hypothesis tracker for temporary target occlusion.

### Technical

- Developed a hardware-integrated ROS 2 tracking system with full `2 x 2` measurement-covariance plumbing, IMM mode probabilities, MH relative hypothesis weights, explicit prediction-only telemetry, split trial recording, and reproducible hardware-bag replay.

### Results-focused

- Recorded and analyzed a `48.28 s` Raspberry Pi AprilTag run with `655` vision measurements, `13.57 Hz` camera poses, near-`30 Hz` IMM/MH odometry, and documented dropout behavior reaching `77` IMM prediction-only steps and `2.849 s` measurement age.

### Validation-focused

- Predeclared controlled covariance and measured-grid validation protocols before collection, then implemented automated covariance, RMSE/bias, bootstrap confidence-interval, and paired Wilcoxon analysis tooling to prevent post-hoc metric selection.

## LinkedIn project description

GHOST is a Raspberry Pi and ROS 2 target-estimation project for intermittent vision. A live AprilTag measurement stream drives a formal Interacting Multiple Model estimator and a bounded heuristic multi-hypothesis tracker side by side. The preserved hardware run contains 48.28 seconds of real pipeline evidence with 655 vision measurements, camera poses at 13.57 Hz, tracker odometry near 30 Hz, and explicit prediction-only/dropout telemetry. I also built split trial recording, full measurement-covariance plumbing, hardware replay plots, a static interactive dashboard, a predeclared controlled covariance protocol, measured-grid accuracy analysis, and a paired statistical comparison harness. Controlled covariance and ground-truth accuracy collection are still pending, so I do not claim validated tracking accuracy or statistical superiority yet.

## GitHub pinned-repository description

Hardware-integrated ROS 2 target estimation with Raspberry Pi AprilTag sensing, formal IMM tracking, bounded MH futures, dropout telemetry, validation tooling, and static hardware replay.

## Interview talking points

- I made target loss explicit: measurement age, prediction-only steps, and degraded status are telemetry outputs rather than hidden implementation details.
- The formal IMM publishes valid model probabilities; the heuristic MH tracker publishes relative hypothesis weights, not probabilities.
- Both trackers consume the same measurement stream, which enables paired comparison under identical inputs.
- The full covariance path supports `R_xx`, `R_xy`, and `R_yy` rather than assuming independent measurement axes.
- I split IMM and MH future logs after identifying that a shared recorder path could silently lose one tracker's evidence.
- I committed the controlled covariance protocol before collecting the new data and fixed the analysis window at seconds 15–75.
- The paired statistical harness exists; the honest remaining gap is repeated measured-truth hardware trials.
- The current project is strong in navigation/estimation but does not yet claim validated guidance, control, vehicle command, or flight testing.

## STAR story

**Situation:** I wanted GHOST to be more than a smooth AprilTag visualization or simulation-only Kalman filter.

**Task:** Build a hardware-integrated estimator workflow that remained auditable during target occlusion and could later support defensible quantitative validation.

**Action:** I integrated Raspberry Pi AprilTag measurements with ROS 2, implemented and replayed formal IMM and heuristic MH trackers, exposed dropout-state telemetry, added full covariance plumbing, fixed evidence-recorder separation, generated plots and an interactive replay, and predeclared the next covariance and ground-truth experiments before collection.

**Result:** The preserved run produced `48.28 s` of hardware pipeline evidence with `655` vision measurements, near-`30 Hz` tracker output, and explicit prediction-only behavior through `2.849 s` maximum measurement age. The repository now has the tooling required to report covariance, bias, RMSE, confidence intervals, and paired tracker comparisons once the physical trials are collected.

## Current metrics that are safe to mention

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

## Claims to avoid until validation is complete

Do not say:

- “validated centimeter-level accuracy”;
- “IMM outperforms MH”;
- “production-ready”;
- “autonomous drone guidance and control”;
- “flight tested”;
- “probabilistic MH predictions.”

Use:

- “hardware-integrated pipeline evidence”;
- “formal IMM mode probabilities”;
- “MH relative hypothesis weights”;
- “controlled covariance and ground-truth validation pending.”
