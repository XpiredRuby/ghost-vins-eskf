# GHOST Project Report

## 1. Executive Summary

GHOST is a ROS 2 vision-tracking project that estimates and predicts the motion of a target from AprilTag camera measurements. The system was developed through a staged validation path: synthetic tracking, measurement covariance analysis, observability/CRLB checks, heuristic multi-hypothesis tracking, formal IMM estimation, and final Raspberry Pi hardware validation.

The final hardware run demonstrates a live AprilTag measurement stream feeding two real-time trackers side by side: the heuristic MH tracker and the formal IMM tracker. The calibrated run produced camera poses at 13.57 Hz while both trackers published near 30 Hz, including valid status transitions through temporary target dropout and recovery.

This report summarizes the engineering problem, system architecture, estimation methods, hardware calibration, live validation results, limitations, and reproducibility steps.

## 2. Problem Statement

Vision-based target tracking becomes difficult when the target is temporarily hidden, poorly detected, or moving unpredictably. A detector alone can only report the current visible position; it cannot maintain a physically reasonable estimate during occlusion or predict where the target may reappear.

The engineering problem for GHOST is to convert intermittent 2D target measurements into a stable real-time state estimate with uncertainty-aware prediction. The system must continue publishing useful tracker output when measurements disappear, clearly label degraded open-loop prediction, and recover cleanly when the target becomes visible again.

The project focuses on estimator behavior, validation evidence, and reproducible ROS 2 integration rather than only visual detection.

## 3. System Architecture

GHOST is organized as a ROS 2 pipeline. The AprilTag publisher outputs the vision measurement topic. The heuristic MH tracker and formal IMM tracker subscribe to that same measurement stream and publish separate odometry, status, and future-trajectory topics.

Live path:

camera + AprilTag -> /ghost/vision/target_pose -> /ghost/tracker_mh/* and /ghost/tracker_imm/*

Keeping the two trackers separate allows side-by-side validation without replacing the existing tracker before hardware evidence is collected.

## 4. Estimation Methods

GHOST uses state-estimation methods instead of treating detection as the final answer. The tracker state represents 2D position and velocity, while the camera measurement provides observed 2D target position.

The heuristic MH tracker maintains practical live behavior for visible tracking, stationary hidden hold, and future prediction messages. It is useful for operational behavior and intuitive multi-future output.

The formal IMM tracker runs a bank of motion models with mode probabilities. In the current live configuration, it compares smooth constant-velocity behavior against higher-process-noise maneuver behavior. During measurement loss, the IMM continues prediction-only propagation and labels the output as prediction-only or dropout-degraded depending on measurement age.

Both trackers consume the same calibrated measurement stream, which allows direct comparison under identical live input.

## 5. Hardware Calibration

The live AprilTag measurement noise was characterized using stationary-tag recordings. Two stationary bags were analyzed:

- `stationary_tag_R_02`
- `stationary_tag_R_03`

Measured stationary noise was approximately millimeter scale:

- R_02: std_x = 0.001181 m, std_y = 0.000499 m
- R_03: std_x = 0.001222 m, std_y = 0.000330 m

For live tracking, GHOST uses a conservative measurement standard deviation of 0.005 m. This is larger than the stationary measured noise to avoid overconfidence during motion, tag-angle changes, lighting changes, and handheld demonstration conditions.

This calibration closed the earlier placeholder measurement-noise gap and connected the tracker defaults to hardware data.

## 6. Live Hardware Validation

The final calibrated live hardware run was recorded as `live_camera_calibrated_R_01`. During the run, the AprilTag target was visible, moved, temporarily hidden, and then revealed again.

The recorded bag included the live vision measurements, heuristic MH tracker outputs, and formal IMM tracker outputs. This validates that the system can run the camera measurement source and both trackers together in real time.

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

The main engineering value of GHOST is the complete validation chain. The project does not stop at a visual demo; it connects estimator design, ROS integration, measurement-noise calibration, live bag recording, and quantitative analysis.

The system demonstrates that a live camera measurement stream can drive two independent real-time trackers while preserving explicit status information during visibility loss. This makes the project useful as evidence of robotics software integration, estimation theory, hardware testing, and disciplined validation.

The final result is stronger than a basic AprilTag demo because it proves live tracking behavior through dropout and recovery, not just tag detection.

## 9. Limitations and Future Work

GHOST is hardware-validated with AprilTag measurements, but it is not yet a general object tracker. The current live perception source depends on a visible AprilTag target and calibrated camera geometry.

The stationary noise calibration validates measurement scale under controlled conditions, but additional testing is still needed for aggressive motion, motion blur, lighting changes, longer occlusions, and non-AprilTag targets.

Future work should include a dashboard/replay interface, larger hardware trial sets, NIS/innovation consistency checks, real object detection beyond AprilTags, and drone/PX4 integration behind safety gates.

## 10. Reproducibility

The committed hardware-validation state is available on GitHub main at commit 9c7873f.

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
