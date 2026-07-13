from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from pathlib import Path


def generate_launch_description() -> LaunchDescription:
    share = Path(get_package_share_directory("ghost_sim_ros2"))
    config = str(share / "config" / "ghost_drone_mission.yaml")

    tracker_source = LaunchConfiguration("tracker_source")
    dashboard_host = LaunchConfiguration("dashboard_host")
    dashboard_port = LaunchConfiguration("dashboard_port")
    dashboard_enabled = LaunchConfiguration("dashboard_enabled")
    mission_duration_s = LaunchConfiguration("mission_duration_s")
    metrics_path = LaunchConfiguration("metrics_path")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "tracker_source",
                default_value="mh",
                description="Observer guidance source: mh or imm",
            ),
            DeclareLaunchArgument(
                "dashboard_host",
                default_value="0.0.0.0",
                description="Dashboard bind address",
            ),
            DeclareLaunchArgument(
                "dashboard_port",
                default_value="8088",
                description="Dashboard TCP port",
            ),
            DeclareLaunchArgument(
                "dashboard_enabled",
                default_value="true",
                description="Start the recruiter-facing web dashboard",
            ),
            DeclareLaunchArgument(
                "mission_duration_s",
                default_value="42.0",
                description="Mission evaluation duration",
            ),
            DeclareLaunchArgument(
                "metrics_path",
                default_value="",
                description="Optional absolute JSON output path for mission metrics",
            ),
            Node(
                package="ghost_sim_ros2",
                executable="mission_simulator",
                name="ghost_mission_simulator",
                output="screen",
                parameters=[config, {"mission_duration_s": mission_duration_s}],
            ),
            Node(
                package="ghost_sim_ros2",
                executable="formal_imm_tracker",
                name="ghost_formal_imm_tracker",
                output="screen",
                parameters=[config],
            ),
            Node(
                package="ghost_sim_ros2",
                executable="mh_tracker",
                name="ghost_mh_tracker",
                output="screen",
                parameters=[config],
            ),
            Node(
                package="ghost_sim_ros2",
                executable="observer_guidance",
                name="ghost_observer_guidance",
                output="screen",
                parameters=[config, {"tracker_source": tracker_source}],
            ),
            Node(
                package="ghost_sim_ros2",
                executable="mission_evaluator",
                name="ghost_mission_evaluator",
                output="screen",
                parameters=[config, {"metrics_path": metrics_path}],
            ),
            Node(
                package="ghost_sim_ros2",
                executable="mission_dashboard",
                name="ghost_mission_dashboard",
                output="screen",
                condition=IfCondition(dashboard_enabled),
                parameters=[config, {"host": dashboard_host, "port": dashboard_port}],
            ),
        ]
    )
