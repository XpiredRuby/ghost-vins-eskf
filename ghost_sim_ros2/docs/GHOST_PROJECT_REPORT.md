# GHOST Project Report

## 1. Executive Summary

GHOST is a ROS 2 vision-tracking project that estimates and predicts the motion of a target from AprilTag camera measurements. The system was developed through staged integration work: synthetic tracking, measurement-noise analysis, observability/CRLB checks, heuristic multi-hypothesis tracking, formal IMM estimation, and final Raspberry Pi hardware pipeline replay evidence.

The final hardware run demonstrates a live AprilTag measurement stream feeding two real-time trackers side by side: the heuristic MH tracker and the formal IMM tracker. The calibrated run produced camera poses at 13.57 Hz while both trackers published near 30 Hz, including valid status transitions through temporary target dropout and recovery.

This report summarizes the engineering problem, system architecture, estimation methods, hardware calibration status, live pipeline evidence, limitations, and reproducibility steps.

**Evidence caveat:** Current hardware evidence validates live ROS 2 pipeline operation, topic rates, dropout/status telemetry, and replay tooling. It does not yet constitute report-grade real-world estimator accuracy validation because controlled hardware measurement covariance R is pending verified stationary noise characterization.

## 2. Problem Statement

Vision-based target tracking becomes difficult when the target is temporarily hidden, poorly detected, or moving unpredictably. A detector alone can only report the current visible position; it cannot maintain a physically reasonable estimate during occlusion or predict where the target may reappear.

The engineering problem for GHOST is to convert intermittent 2D target measurements into a stable real-time state estimate with uncertainty-aware prediction. The system must continue publishing useful tracker output when measurements disappear, clearly label degraded open-loop prediction, and recover cleanly when the target becomes visible again.

The project focuses on estimator behavior, hardware replay evidence, and reproducible ROS 2 integration rather than only visual detection.

## 3. System Architecture

GHOST is organized as a ROS 2 pipeline. The AprilTag publisher outputs the vision measurement topic. The heuristic MH tracker and formal IMM tracker subscribe to that same measurement stream and publish separate odometry, status, and future-trajectory topics.

Live path:

camera + AprilTag -> /ghost/vision/target_pose -> /ghost/tracker_mh/* and /ghost/tracker_imm/*

Keeping the two trackers separate allows side-by-side qualitative replay without replacing the existing tracker before a statistical comparison harness is built.

## 4. Estimation Methods

GHOST uses state-estimation methods instead of treating detection as the final answer. The tracker state represents 2D position and velocity, while the camera measurement provides observed 2D target position.

The heuristic MH tracker maintains practical live behavior for visible tracking, stationary hidden hold, and future prediction messages. It is useful for operational behavior and intuitive multi-future output.

The formal IMM tracker runs a bank of motion models with mode probabilities. In the current live configuration, it compares smooth constant-velocity behavior against higher-process-noise maneuver behavior. During measurement loss, the IMM continues prediction-only propagation and labels the output as prediction-only or dropout-degraded depending on measurement age.

Both trackers consume the same live measurement stream, which allows side-by-side qualitative replay under identical input. Statistical baseline comparison remains pending a dedicated harness.

## 5. Hardware Calibration Status

Initial stationary-tag recordings were analyzed to choose a conservative live measurement-noise candidate. Controlled hardware measurement covariance R characterization is still pending before report-grade real-world estimator accuracy validation. Two stationary bags were analyzed:

- `stationary_tag_R_02`
- `stationary_tag_R_03`

Initial stationary noise estimates were approximately millimeter scale in these recordings:

- R_02: std_x = 0.001181 m, std_y = 0.000499 m
- R_03: std_x = 0.001222 m, std_y = 0.000330 m

For live tracking, GHOST uses `measurement_std_m = 0.005 m` as a conservative candidate value. It is intentionally larger than the initial stationary estimates to avoid overconfidence during motion, tag-angle changes, lighting changes, and handheld demonstration conditions.

This does not close the measurement-noise gap for report-grade estimator accuracy claims. Controlled stationary noise characterization and covariance R documentation remain pending.

## 6. Live Hardware Pipeline Evidence

The final calibrated live hardware run was recorded as `live_camera_calibrated_R_01`. During the run, the AprilTag target was visible, moved, temporarily hidden, and then revealed again.

The recorded bag included the live vision measurements, heuristic MH tracker outputs, and formal IMM tracker outputs. This validates live ROS 2 pipeline operation: the camera measurement source and both trackers ran together in real time and emitted reviewable telemetry. It does not validate estimator accuracy against controlled ground truth.

The most important behavior observed was clean dropout handling. The IMM entered prediction-only and dropout-degraded states when measurements disappeared, then returned to tracking after the tag was visible again. The MH tracker also reported visible measurement lock and hidden stationary hold states.

## 7. Results

Final calibrated live bag: `live_camera_calibrated_R_01`

| Metric | Result |
|---|---:|
| Duration | 48.280 s |
| Total messages | 6810 |
| Camera pose rate | 13.57 Hz |
| IMM odom rate | 30.01 Hz |
| MH odom rate | 29.99 Hz |
| IMM tracking samples | 169 |
| IMM prediction-only samples | 2 |
| IMM dropout-degraded samples | 10 |
| MH visible-lock samples | 168 |
| MH hidden-hold samples | 13 |
| Max IMM prediction-only steps | 77 |
| Max IMM measurement age | 2.849 s |

The result shows that the live camera stream and both trackers operated at real-time rates. The system also produced explicit status evidence for visible tracking, temporary hidden prediction, degraded dropout, and recovery.

## 8. Engineering Significance

The main engineering value of GHOST is the complete integration and evidence chain. The project does not stop at a visual demo; it connects estimator design, ROS integration, measurement-noise candidate selection, live bag recording, topic-rate analysis, status telemetry, and replay tooling.

The system demonstrates that a live camera measurement stream can drive two independent real-time trackers while preserving explicit status information during visibility loss. This makes the project useful as evidence of robotics software integration, estimation theory implementation, hardware pipeline testing, and disciplined replay packaging.

The final result is stronger than a basic AprilTag demo because it shows live tracker telemetry through dropout and recovery, not just tag detection. Accuracy validation remains future work until controlled R characterization and ground-truth comparison are complete.

## 9. Limitations and Future Work

GHOST has hardware-integrated AprilTag replay evidence, but it is not yet report-grade estimator accuracy validation and is not a general object tracker. The current live perception source depends on a visible AprilTag target and calibrated camera geometry.

Initial stationary recordings informed a conservative measurement-noise candidate, but verified controlled covariance R characterization is still needed, along with aggressive motion, motion blur, lighting changes, longer occlusions, and non-AprilTag target tests.

Future work should include verified stationary covariance R characterization, a statistical IMM/MH comparison harness, larger hardware trial sets, NIS/innovation consistency checks, real object detection beyond AprilTags, and drone/PX4 integration behind safety gates.

## 10. Reproducibility

The committed hardware pipeline evidence state is available on GitHub main at commit 9c7873f.

Build command:

cd ~/ghost_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select ghost_sim_ros2
source install/setup.bash

Key evidence files and tools:

- HARDWARE_CALIBRATION_EVIDENCE.md
- tools/analyze_stationary_R.py
- tools/analyze_live_bag.py
- ghost_sim_ros2/apriltag_ros_only.py
- launch/pi_only_synthetic_imm.launch.py

Final live-bag analysis command:

python3 tools/analyze_live_bag.py ~/ghost_ws/bags/live_camera_calibrated_R_01

The report should be read together with the committed evidence markdown and the ROS bag summaries from the calibrated hardware run.
