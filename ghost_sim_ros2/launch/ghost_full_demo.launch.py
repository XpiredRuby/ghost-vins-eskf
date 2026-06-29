from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(package="ghost_sim_ros2", executable="synthetic_measurements", name="ghost_synthetic_measurements"),
        Node(package="ghost_sim_ros2", executable="cv_tracker", name="ghost_cv_tracker"),
        Node(package="ghost_sim_ros2", executable="evidence_logger", name="ghost_evidence_logger"),
        Node(package="ghost_sim_ros2", executable="gazebo_bridge", name="ghost_gazebo_bridge"),
        Node(package="ghost_sim_ros2", executable="imu_watchdog", name="ghost_imu_watchdog"),
    ])
