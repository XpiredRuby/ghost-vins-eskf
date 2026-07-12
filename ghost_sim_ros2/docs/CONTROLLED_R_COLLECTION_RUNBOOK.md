# Controlled R Collection Runbook

## Purpose

Collect one predeclared 90-second stationary AprilTag dataset for empirical measurement covariance `R`.

This estimates camera/AprilTag measurement noise under one controlled setup. It does **not** validate tracker accuracy.

## Before the physical session

The collection helper now performs the full evidence path in one terminal:

- records the committed protocol hash and current repository head;
- requires a calibrated camera file and `v4l2-ctl`;
- prompts for measured camera-to-tag standoff and setup notes;
- records camera controls before setting, after setting, after opening the camera, and after the trial;
- verifies supported controls against requested values;
- treats a rejected redundant control write as acceptable only when immediate readback already equals the requested value;
- uses an existing AprilTag publisher or starts one automatically;
- requires a live `/ghost/vision/target_pose` sample before the 90-second clock;
- resolves the recorder's timestamped child directory automatically;
- includes a predeclared recorder startup margin so the retained pose span can still cover the required 90 seconds;
- uses the first received vision sample as the controlled-R relative-time origin, excluding ROS discovery latency from the evidence clock;
- validates fixed-window coverage, sample rate, and maximum sample gap;
- exports the raw pose CSV;
- computes raw covariance and correlation over seconds `15–75`;
- computes the required `15–35`, `35–55`, and `55–75 s` diagnostics;
- preserves rejected collections and writes an explicit final status.

The formal IMM and GHOST-MH trackers are not required for this stationary measurement-noise trial. The raw vision topic is the source of record.

## Physical setup

Before pressing Enter in the helper:

1. Rigidly mount the camera.
2. Rigidly mount or tape the AprilTag.
3. Keep the tag clearly visible and approximately fronto-parallel.
4. Measure the camera-to-tag standoff in meters.
5. Keep the table, camera, tag, cable, and lighting unchanged.
6. Do not hold either object by hand.

## Run

From the repository root:

```bash
cd ~/ghost_ws/src/ghost-vins-eskf
DEVICE=/dev/video0 ghost_sim_ros2/tools/collect_controlled_r_trial.sh
```

Default predeclared collection-quality criteria recorded before the trial:

```text
record duration: 90 s
primary analysis window: 15-75 s
minimum fixed-window rate: 10.0 Hz
maximum fixed-window sample gap: 0.25 s
```

Override values only before collection and preserve them in the trial metadata:

```bash
MIN_ANALYSIS_RATE_HZ=10.0 \
MAX_ANALYSIS_GAP_S=0.25 \
DEVICE=/dev/video0 \
ghost_sim_ros2/tools/collect_controlled_r_trial.sh
```

Do not modify thresholds after seeing the data.

## AprilTag publisher behavior

The helper first checks for a live sample.

- If `/ghost/vision/target_pose` is already publishing, it uses that source.
- Otherwise, with `AUTO_START_PUBLISHER=1` (default), it starts:

```bash
~/ghost_venv/bin/python \
  ghost_sim_ros2/ghost_sim_ros2/apriltag_ros_only.py \
  --device /dev/video0 \
  --tag-size 0.10 \
  --calib ~/ghost_camera_calibration.json
```

The old `--use-controlled-r-candidate` flag is intentionally not used during empirical `R` collection. The covariance metadata published with each pose does not determine the raw position samples used to estimate empirical `R`.

Set `AUTO_START_PUBLISHER=0` only when an externally managed publisher must be used.

## Required and additional artifacts

The helper creates:

```text
~/ghost_trials/controlled_R_<UTC timestamp>/
├── protocol_metadata.txt
├── git_status.txt
├── camera_control_lock_log.txt
├── camera_control_readbacks.tsv
├── camera_controls_before.txt
├── camera_controls_after_set.txt
├── camera_controls_pre_record.txt
├── camera_controls_after_trial.txt
├── operator_attestation.txt
├── preflight_vision_sample.txt
├── apriltag_publisher.log
├── trial_recorder.log
├── recorder_child_dir.txt
├── vision_pose.jsonl -> recorder/<trial id>/vision_pose.jsonl
├── vision_pose_log.csv
├── collection_quality.json
├── collection_quality.md
├── noise_summary.json
├── noise_summary.md
└── final_collection_status.txt
```

Tracker-related recorder files may exist but can be empty because the trackers are not required for this trial.

## Acceptance logic

The helper rejects and preserves the trial when:

- a supported camera control cannot be set or read back;
- the operator does not explicitly attest that the physical setup and lighting remained unchanged;
- a supported control changes after camera open or during the trial;
- no live vision sample is available;
- the recorder child directory or vision log is missing;
- timestamps are malformed or non-monotonic;
- the first/last samples do not cover the 90-second record within tolerance;
- fixed-window rate falls below the declared minimum;
- a fixed-window sample gap exceeds the declared maximum.

Physical movement or lighting changes cannot be inferred perfectly from software. After recording, the helper requires the operator to type exactly `NO` to attest that no physical setup or lighting change occurred; any other response rejects and preserves the run.

Accepted status:

```text
ACCEPTABLE_FOR_ENGINEER_REVIEW_DOES_NOT_VALIDATE_TRACKER_ACCURACY
```

Rejected status:

```text
REJECT_COLLECTION_PRESERVE_ALL_ARTIFACTS
```

## Analysis output

`noise_summary.json` and `noise_summary.md` report:

- `R_xx`
- `R_xy`
- `R_yy`
- x/y correlation
- x/y standard deviation
- linear drift slopes
- sample count and sample rate
- all three fixed sub-window covariance matrices
- relative covariance variation and centroid drift diagnostics

Protocol v1 did not predeclare a numerical stability pass/fail threshold. Sub-window stability is therefore reported for engineering review and must not be converted into a post-hoc acceptance threshold.

## Claims boundary

Safe statement after an accepted collection:

> A predeclared 90-second controlled stationary trial produced an empirical raw AprilTag position covariance over the fixed 15–75 second window, with camera-control readbacks and sub-window stability diagnostics.

Unsafe statements:

- validated tracker accuracy;
- production-grade covariance;
- white-noise proof;
- general robustness;
- final estimator tuning without engineering review.
