from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package="ghost_sim_ros2",
            executable="imu_watchdog",
            name="ghost_imu_watchdog",
            output="screen",
        )
    ])
