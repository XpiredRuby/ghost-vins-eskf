from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package_share = FindPackageShare("ghost_sim_ros2")
    return LaunchDescription(
        [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    PathJoinSubstitution(
                        [package_share, "launch", "sim_tracking.launch.py"]
                    )
                )
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                name="ghost_rviz",
                output="screen",
                arguments=[
                    "-d",
                    PathJoinSubstitution([package_share, "rviz", "ghost_sim.rviz"]),
                ],
            ),
        ]
    )
