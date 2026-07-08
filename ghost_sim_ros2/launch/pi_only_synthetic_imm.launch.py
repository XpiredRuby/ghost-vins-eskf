from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package="ghost_sim_ros2",
            executable="synthetic_measurements",
            name="ghost_synthetic_measurements",
            output="screen",
        ),
        Node(
            package="ghost_sim_ros2",
            executable="mh_tracker",
            name="ghost_mh_tracker",
            output="screen",
        ),
        Node(
            package="ghost_sim_ros2",
            executable="formal_imm_tracker",
            name="ghost_formal_imm_tracker",
            output="screen",
        ),
    ])
