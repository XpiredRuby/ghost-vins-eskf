# GHOST Career Snippets

Use these statements while physical covariance, measured-grid accuracy, paired hardware trials, USB timing, and Raspberry Pi runtime characterization remain pending. They distinguish hardware estimation evidence from deterministic software-in-the-loop GNC evidence and do not claim PX4, HIL, vehicle command, flight test, production readiness, or statistically proven tracker superiority.

## Resume bullets

### Concise

- Built a USB UVC webcam/Raspberry Pi/ROS 2 intermittent-visibility target-estimation system using AprilTag measurements, a formal IMM estimator, and a bounded heuristic multi-hypothesis comparison tracker.

### Technical

- Developed a hardware-integrated ROS 2 tracking pipeline with full `2 x 2` measurement-covariance plumbing, formal IMM mode probabilities, MH relative hypothesis weights, explicit prediction-only telemetry, split trial recording, and reproducible browser replay.

### Results-focused hardware bullet

- Recorded and analyzed a `48.28 s` USB-webcam AprilTag run with `655` vision measurements, `13.57 Hz` camera poses, near-`30 Hz` IMM/MH odometry, and dropout behavior reaching `77` IMM prediction-only steps and `2.849 s` measurement age.

### GNC software-in-the-loop bullet

- Connected the repository's formal IMM to relative-standoff guidance, acceleration-limited velocity control, actuator lag, follower dynamics, and a `TRACKING` / `PREDICTION` / `SAFE_HOLD` supervisor; deterministic CI scenarios capped acceleration at `2.5 m/s²`, entered safe hold after prolonged dropout, and reacquired after measurements returned.

### Validation-systems bullet

- Engineered an evidence-first physical-validation stack with a fixed-window controlled covariance protocol, six-point grid RMSE analysis, a balanced randomized 55-slot paired IMM/MH campaign, a local timed trial conductor, audited trial outcomes, bootstrap confidence intervals, and failure/reacquisition reporting.

### Reproducibility and integrity bullet

- Added privacy-separated USB hardware inventory, machine-readable BOM, Raspberry Pi timing/resource instrumentation, SHA-256 evidence packaging, immutable estimator/configuration locks, and a machine-readable public-claims gate to prevent post-hoc tuning or unsupported metrics.

## LinkedIn project description

GHOST is a USB UVC webcam, Raspberry Pi, and ROS 2 target-estimation project for intermittent vision. A live AprilTag measurement stream drives a formal Interacting Multiple Model estimator and a bounded heuristic multi-hypothesis tracker side by side. The preserved hardware run contains 48.28 seconds of real pipeline evidence with 655 vision measurements, camera poses at 13.57 Hz, tracker odometry near 30 Hz, and explicit prediction-only/dropout telemetry.

I also connected the repository's actual formal IMM to a deterministic software-in-the-loop guidance-controller-plant chain with relative-standoff guidance, acceleration-limited control, actuator lag, follower dynamics, a two-second prediction horizon, long-dropout safe hold, and reacquisition. The public GitHub Pages site provides one-click access to the hardware replay and a USB hardware/BOM record.

Before collecting the decisive validation data, I implemented the complete methodology and evidence pipeline: a hardened controlled covariance workflow, six-point measured-grid analysis, a predeclared 55-slot paired hardware campaign, deterministic balanced randomization, a local visual/audio conductor, immutable plan and audited outcome state, bootstrap confidence intervals, failure/reacquisition plots, USB timing and Pi resource tools, SHA-256 evidence packaging, a parameter/configuration lock, and a claims-release validator. Physical covariance, ground-truth accuracy, and real paired-trial results remain pending, so I do not claim validated real-world accuracy, tracker superiority, real vehicle control, or flight readiness.

## GitHub pinned-repository description

USB-webcam/Raspberry Pi ROS 2 target estimation with formal IMM tracking, bounded GHOST-MH futures, dropout telemetry, deterministic closed-loop GNC SIL, predeclared hardware validation, integrity tooling, BOM, and public replay.

## Interview talking points

- The active camera backend is a standard USB UVC webcam through V4L2, selected because it produced a reliable working measurement pipeline; the architecture keeps the sensor backend replaceable.
- I made target loss explicit: measurement age, prediction-only steps, degraded status, and safe-hold state are telemetry or supervisor outputs rather than hidden implementation details.
- The formal IMM publishes valid model probabilities; the heuristic MH tracker publishes relative hypothesis weights, not probabilities.
- Both live trackers consume the same measurement stream, enabling paired comparison under identical inputs.
- The full covariance path supports `R_xx`, `R_xy`, and `R_yy` rather than assuming independent measurement axes.
- I split IMM and MH future logs after identifying that a shared recorder path could silently lose one tracker's evidence.
- I used the same formal IMM in a deterministic guidance-controller-plant loop instead of creating a separate mock estimator.
- The SIL supervisor follows for bounded dropout, commands safe hold after the prediction horizon, and reacquires after measurements return.
- The closed-loop results are explicitly labeled software-in-the-loop, not PX4, HIL, vehicle, or flight results.
- The formal campaign plan and randomized order are immutable; accepted/rejected outcomes are recorded separately with append-only amendments.
- The local conductor provides precise cues, but measured vision gaps—not browser timing—determine acceptance.
- The paired campaign contains 55 predeclared slots and cannot support a superiority claim until protocol-compliant real hardware trials exist.
- I added parameter and release-claims gates so tuning and public wording cannot drift after outcomes are observed without an explicit audit failure.

## STAR story

**Situation:** I wanted GHOST to be more than a smooth AprilTag visualization or simulation-only Kalman filter.

**Task:** Build a hardware-integrated estimator workflow that remained auditable during target occlusion, demonstrate how the estimator could drive a bounded GNC loop, and prepare defensible physical validation without overstating software evidence as flight validation.

**Action:** I integrated a USB UVC webcam and Raspberry Pi AprilTag stream with ROS 2, implemented and replayed formal IMM and heuristic MH trackers, exposed dropout telemetry, added full covariance plumbing, fixed evidence-recorder separation, built a public replay and BOM site, connected the formal IMM to bounded guidance/control and safe hold in deterministic SIL, and predeclared/automated the covariance, grid, paired-trial, runtime, integrity, parameter-lock, and claims-review workflows before collection.

**Result:** The preserved hardware run produced `48.28 s` of pipeline evidence with `655` vision measurements, near-`30 Hz` tracker output, and prediction-only behavior through `2.849 s` maximum measurement age. The formal-IMM SIL maintained bounded control, entered `2.0 s` of safe hold in the long-dropout case, and reacquired afterward. All meaningful hardware-free preparation is now complete; the remaining gap is physical execution and evidence review.

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

## Claims to avoid until physical validation is complete

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

- “USB-webcam/Raspberry Pi hardware-integrated estimation pipeline evidence”;
- “formal IMM mode probabilities”;
- “MH relative hypothesis weights”;
- “deterministic formal-IMM closed-loop GNC software-in-the-loop”;
- “bounded safe-hold behavior in SIL”;
- “predeclared and automated physical validation pending execution”;
- “physical covariance, ground-truth accuracy, and paired validation pending.”
