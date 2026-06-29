# GHOST Full Integrated Demo Evidence

## Result
The full GHOST ROS2 demo launches the synthetic vision pipeline, CV tracker, evidence logger, Gazebo/PX4 bridge, and physical MPU-6050 watchdog together.

## Launch Command
    ros2 launch ghost_sim_ros2 ghost_full_demo.launch.py

## Confirmed Topics
- /ghost/vision/target_pose
- /ghost/tracker/target_odom
- /ghost/gazebo/target_pose
- /ghost/gazebo/target_twist
- /ghost/px4/target_setpoint
- /ghost/imu/watchdog_state

## IMU Watchdog Sample
    data: STABLE, gyro_dps=1.27, accel_delta_g=0.009

## Interpretation
This validates that the software tracking stack and real physical IMU watchdog run together in one ROS2 launch.
