# GHOST ROS2 Simulation Package

## Hardware-Validated Status

GHOST now includes live Raspberry Pi AprilTag tracking with side-by-side heuristic MH tracking and formal IMM tracking.

Final calibrated hardware run:
- Bag: `~/ghost_ws/bags/live_camera_calibrated_R_01`
- Duration: `48.280 s`
- Camera pose rate: `13.57 Hz`
- IMM tracker rate: `30.01 Hz`
- MH tracker rate: `29.99 Hz`
- Max IMM measurement age during dropout: `2.849 s`

See `HARDWARE_CALIBRATION_EVIDENCE.md` for calibration and live-bag evidence.

Final project report: `docs/GHOST_PROJECT_REPORT.md`

Final hardware bag plots: `docs/GHOST_LIVE_BAG_PLOTS.md`

This package runs the GHOST software path without camera hardware or IMU hardware.

It provides:

- synthetic AprilTag-like position measurements on `/ghost/vision/target_pose`
- simulated ground truth on `/ghost/sim/target_truth`
- a 2D constant-velocity Kalman tracker on `/ghost/tracker/target_odom`
- RViz/Gazebo-friendly markers on `/ghost/sim/target_marker` and `/ghost/tracker/target_marker`
- Gazebo/PX4-facing bridge topics on `/ghost/gazebo/target_pose`, `/ghost/gazebo/target_twist`, and `/ghost/px4/target_setpoint`
- CSV evidence logging to `~/ghost_logs/sim_tracking.csv`
- offline filter tuning sweep output to `~/ghost_logs/tracker_sweep.csv`

## Build

From the ROS2 workspace root:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/ghost_ws
colcon build --packages-select ghost_sim_ros2
source install/setup.bash
```

## Run The No-Hardware Pipeline

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py
```

Optional:

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py noise_std_m:=0.04 dropout_duration_s:=5.0
```

Strict validation mode with visible NIS gate rejections:

```bash
ros2 launch ghost_sim_ros2 sim_tracking.launch.py warn_on_reject:=true gate_chi2_2d:=9.210
```

This starts:

- `ghost_synthetic_measurements`
- `ghost_cv_tracker`
- `ghost_evidence_logger`
- `ghost_gazebo_bridge`

## Inspect

```bash
ros2 topic list
ros2 topic echo /ghost/tracker/target_odom
ros2 topic echo /ghost/gazebo/target_pose
```

Expected core topics:

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

## Evidence Plot

After running the launch file for at least 20 seconds:

```bash
python3 ~/ghost_plot_tracking_evidence.py
```

Expected output:

```text
~/ghost_logs/ghost_tracking_evidence.png
```

## Offline Tracker Sweep

Run this without ROS launch:

```bash
python3 ~/ghost_ws/src/ghost_sim_ros2/analysis/ghost_offline_tracker_sweep.py
```

Expected output:

```text
~/ghost_logs/tracker_sweep.csv
```

The CSV ranks CV tracker parameter sets by RMS error and max error.

## RViz

Option A, launch RViz with the sim:

```bash
ros2 launch ghost_sim_ros2 sim_tracking_rviz.launch.py
```

Option B, open RViz separately:

```bash
rviz2 -d ~/ghost_ws/install/ghost_sim_ros2/share/ghost_sim_ros2/rviz/ghost_sim.rviz
```

Fixed frame:

```text
ghost_floor
```

Blue/cyan marker is simulated truth. Green/orange marker is tracker output. Orange indicates stale/coasting state during occlusion.

## Bridge Scope

`ghost_gazebo_bridge` intentionally publishes target-state topics only. It does not command a drone and does not arm/control PX4.

Real PX4 offboard control should be a later safety-gated node that consumes:

```text
/ghost/px4/target_setpoint
```

and applies geofencing, mode checks, rate limits, and kill-switch logic.

## Why This Exists

This package is the hardware-free development path for GHOST V12. It lets the tracker, logging, validation plots, and Gazebo/RViz visualization be built before the camera and IMU tests are complete.
