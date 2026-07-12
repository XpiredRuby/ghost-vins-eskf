import importlib

import pytest


ROS_RUNTIME_MODULES = ("rclpy", "geometry_msgs", "nav_msgs", "std_msgs")
NODE_MODULES = (
    "ghost_sim_ros2.cv_tracker",
    "ghost_sim_ros2.evidence_logger",
    "ghost_sim_ros2.gazebo_bridge",
    "ghost_sim_ros2.synthetic_measurements",
)


def test_ros_node_imports_when_runtime_dependencies_are_available():
    for dependency in ROS_RUNTIME_MODULES:
        pytest.importorskip(
            dependency,
            reason=f"ROS runtime dependency {dependency} is unavailable in this test environment",
        )
    for module_name in NODE_MODULES:
        importlib.import_module(module_name)
