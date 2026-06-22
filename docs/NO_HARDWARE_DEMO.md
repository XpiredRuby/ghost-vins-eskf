# GHOST No-Hardware ROS2 Demo

This document describes the hardware-free GHOST V12 demo path. It validates the ROS2 tracking architecture before camera, AprilTag print, and IMU hardware are used.

## Scope

The no-hardware demo covers:

- synthetic camera-like target measurements
- constant-velocity Kalman target tracking
- occlusion/dropout coasting
- CSV evidence logging
- offline tracker parameter sweep
- Gazebo/PX4-facing bridge topics
- RViz configuration for later GUI visualization

It does not claim:

- real AprilTag camera accuracy
- real rolling-shutter behavior
- real IMU watchdog performance
- PX4 offboard control authority

Those are separate hardware validation steps.

## Architecture

```text
synthetic target truth
        |
        v
/ghost/sim/target_truth
        |
        +--> synthetic measurement noise + dropout
                         |
                         v
              /ghost/vision/target_pose
                         |
                         v
                  CV Kalman tracker
                         |
                         v
              /ghost/tracker/target_odom
                         |
             +-----------+------------+
             |                        |
             v                        v
   evidence CSV logger        Gazebo/PX4 bridge topics
```

## ROS2 Topics

The no-hardware launch publishes:

```text
/ghost/vision/target_pose
/ghost/sim/target_truth
/ghost/tracker/target_odom
/ghost/sim/target_marker
/ghost/tracker/target_marker
/ghost/gazebo/target_pose
/ghost/gazebo/target_twist
/ghost/px4/target_setpoint
```

The `/ghost/px4/target_setpoint` topic is intentionally only a target-state setpoint placeholder. It does not arm, command, or control a drone. A real PX4 offboard controller must be implemented as a later safety-gated node.

## Reproduce

From the Pi:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2
source install/setup.bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py
```

In a second Pi terminal while the launch is running:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
source install/setup.bash
ros2 topic list | grep ghost
```

Expected result:

```text
/ghost/gazebo/target_pose
/ghost/gazebo/target_twist
/ghost/px4/target_setpoint
/ghost/sim/target_marker
/ghost/sim/target_truth
/ghost/tracker/target_marker
/ghost/tracker/target_odom
/ghost/vision/target_pose
```

## Evidence

The launch writes:

```text
~/ghost_logs/sim_tracking.csv
```

The evidence plot script generates:

```text
~/ghost_logs/ghost_tracking_evidence.png
```

The current committed evidence plot is:

![GHOST tracking evidence](../analysis/ghost_tracking_evidence.png)

The offline tracker sweep writes:

```text
~/ghost_logs/tracker_sweep.csv
```

The current sweep result showed:

```text
best RMS error: 0.188 m
best max error: 1.316 m
rejected measurements: 0
```

The max error is dominated by intentional occlusion/dropout coasting, not measurement rejection.

## Tracker Sweep

Run:

```bash
python3 ~/ghost_ws/src/ghost_sim_ros2/analysis/ghost_offline_tracker_sweep.py
```

This ranks CV tracker parameter sets by RMS error and max error:

```text
acceleration process noise
measurement noise assumption
NIS gate threshold
RMS position error
max position error
accepted/rejected updates
```

## Current No-Hardware Completion

Status: complete for software-only MVP.

Remaining work is hardware-bound:

- printed AprilTag real-pose validation
- real webcam measurement publishing into ROS2
- MPU-6050 watchdog wiring and noise characterization
- final real-world validation report/video
