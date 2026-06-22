from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    rate_hz = LaunchConfiguration("rate_hz")
    noise_std_m = LaunchConfiguration("noise_std_m")
    dropout_start_s = LaunchConfiguration("dropout_start_s")
    dropout_duration_s = LaunchConfiguration("dropout_duration_s")
    log_out = LaunchConfiguration("log_out")

    return LaunchDescription(
        [
            DeclareLaunchArgument("rate_hz", default_value="20.0"),
            DeclareLaunchArgument("noise_std_m", default_value="0.025"),
            DeclareLaunchArgument("dropout_start_s", default_value="12.0"),
            DeclareLaunchArgument("dropout_duration_s", default_value="3.0"),
            DeclareLaunchArgument("log_out", default_value="~/ghost_logs/sim_tracking.csv"),
            Node(
                package="ghost_sim_ros2",
                executable="synthetic_measurements",
                name="ghost_synthetic_measurements",
                output="screen",
                parameters=[
                    {
                        "rate_hz": rate_hz,
                        "noise_std_m": noise_std_m,
                        "dropout_start_s": dropout_start_s,
                        "dropout_duration_s": dropout_duration_s,
                    }
                ],
            ),
            Node(
                package="ghost_sim_ros2",
                executable="cv_tracker",
                name="ghost_cv_tracker",
                output="screen",
            ),
            Node(
                package="ghost_sim_ros2",
                executable="evidence_logger",
                name="ghost_evidence_logger",
                output="screen",
                parameters=[{"out": log_out}],
            ),
        ]
    )
