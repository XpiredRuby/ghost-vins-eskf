# Direct Controlled-R Collection

## Purpose

Collect the stationary AprilTag measurement covariance directly from the calibrated camera → AprilTag detector → `solvePnP` pipeline without using ROS DDS as the source of record.

This path exists because the physical camera pipeline can remain continuous while middleware receipt logs contain multi-second delivery gaps. The direct path measures sensor/pose-estimation noise rather than ROS transport timing.

## Claims boundary

Safe claim:

> A predeclared 90-second stationary direct-camera trial produced a fixed-window empirical AprilTag position covariance with camera-control readbacks, source-timestamp continuity checks, brightness diagnostics, tag-identity checks, and sub-window stability diagnostics.

This does **not** establish:

- tracker accuracy;
- production robustness;
- ROS live-stream continuity;
- residual whiteness;
- generalization to other cameras, lighting, tag poses, or target types;
- physical motion or occlusion performance.

Direct-source evidence must be labeled separately from ROS-received evidence. Do not silently pool the two sources.

## Run

```bash
cd ~/ghost_ws/src/ghost-vins-eskf
DEVICE=/dev/video0 \
TAG_SIZE_M=0.100 \
SETUP_NOTE="locked webcam and wall-mounted tag" \
ATTESTATION_SOURCE="operator statement recorded before run" \
ghost_sim_ros2/tools/collect_controlled_r_direct_trial.sh
```

Default fixed criteria:

```text
record duration: 90 s
analysis window: 15-75 s
minimum analysis rate: 10 Hz
maximum analysis gap: 0.25 s
```

## Source mapping

The direct recorder preserves the same 2D tracker mapping used by the ROS publisher:

```text
position.x = OpenCV camera tvec.z  # camera-forward range
position.y = OpenCV camera tvec.x  # camera-right offset
position.z = 0
```

## Evidence

The trial directory includes:

```text
vision_pose.jsonl
direct_capture_summary.json
vision_pose_log.csv
collection_quality.json
collection_quality.md
noise_summary.json
noise_summary.md
camera_controls_before.txt
camera_controls_after_set.txt
camera_controls_after_trial.txt
camera_control_readbacks.tsv
protocol_metadata.txt
operator_attestation.txt
final_collection_status.txt
```

The direct capture summary reports frame reads, detections, PnP success, valid-pose rate, maximum source gap, tag IDs, pose span, brightness range, and detector decision margin.

## Current engineering-review candidate

The first acceptable direct-source trial, `controlled_R_direct_01`, retained `885` samples in the fixed `15-75 s` window at `14.7489 Hz`, with a maximum fixed-window gap of `0.076186 s` and no collection warnings. Its raw stationary covariance candidate is:

```text
R_xx = 1.1285530537472441e-06 m^2
R_xy = 9.517042606937477e-08 m^2
R_yy = 1.396619108865118e-08 m^2
```

The three fixed 20-second subwindows showed a maximum relative covariance deviation of `0.1829769592` and maximum centroid offset of `0.000188339 m`. Because protocol v1 did not predeclare a numerical stability threshold, those values remain diagnostic rather than a post-hoc pass/fail rule. The candidate is approved for Phase 2 dry-run configuration, not as proof of accuracy, whiteness, or dynamic generalization.

The accepted run used automated stationarity checks and the pre-run operator statement already recorded for the locked setup, but it did not add a separate post-run human attestation. Its exact local status therefore retains `NO_POSTRUN_HUMAN_ATTESTATION`; this limitation is preserved and does not invalidate the objective fixed-window timing gate.

## Review status

A passing direct trial writes:

```text
ACCEPTABLE_FOR_ENGINEERING_REVIEW_DIRECT_SOURCE_DOES_NOT_VALIDATE_TRACKER_ACCURACY
```

This is an engineering-review status, not a claim that the complete physical validation campaign is finished.
