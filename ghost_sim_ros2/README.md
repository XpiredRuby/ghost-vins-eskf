# GHOST ROS2 Simulation Package

This package runs the GHOST software path without camera hardware or IMU hardware.

It provides:

- synthetic AprilTag-like position measurements on `/ghost/vision/target_pose`
- simulated ground truth on `/ghost/sim/target_truth`
- a 2D constant-velocity Kalman tracker on `/ghost/tracker/target_odom`
- RViz/Gazebo-friendly markers on `/ghost/sim/target_marker` and `/ghost/tracker/target_marker`
- CSV evidence logging to `~/ghost_logs/sim_tracking.csv`

## Build

From the ROS2 workspace root:

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-select ghost_sim_ros2
source install/setup.bash
```

## Run

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py
```

Optional:

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py noise_std_m:=0.04 dropout_duration_s:=5.0
```

## Inspect

```bash
ros2 topic list
ros2 topic echo /ghost/tracker/target_odom
```

For RViz2, set the fixed frame to:

```text
ghost_floor
```

Then add:

- Marker: `/ghost/sim/target_marker`
- Marker: `/ghost/tracker/target_marker`
- Odometry: `/ghost/tracker/target_odom`

## Why This Exists

This package is the hardware-free development path for GHOST V12. It lets the tracker, logging, validation plots, and Gazebo/RViz visualization be built before the camera and IMU tests are complete.
