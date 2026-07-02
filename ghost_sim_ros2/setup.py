from glob import glob
from setuptools import setup


package_name = "ghost_sim_ros2"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name, "analysis"],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/rviz", glob("rviz/*.rviz")),
        (f"share/{package_name}/analysis", glob("analysis/*.py")),
    ],
    install_requires=["setuptools", "numpy"],
    zip_safe=True,
    maintainer="Vinayak Manoj Nair",
    maintainer_email="vinayak@example.com",
    description="Simulation-only ROS2 tools for GHOST target tracking.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "synthetic_measurements = ghost_sim_ros2.synthetic_measurements:main",
            "cv_tracker = ghost_sim_ros2.cv_tracker:main",
            "mh_tracker = ghost_sim_ros2.mh_tracker:main",
            "mh_monitor = ghost_sim_ros2.mh_monitor:main",
            "mh_web_dashboard = ghost_sim_ros2.mh_web_dashboard:main",
            "trial_recorder = ghost_sim_ros2.trial_recorder:main",
            "evidence_logger = ghost_sim_ros2.evidence_logger:main",
            "gazebo_bridge = ghost_sim_ros2.gazebo_bridge:main",
            "imu_watchdog = ghost_sim_ros2.imu_watchdog:main",
            "stationary_noise_analysis = analysis.stationary_noise_analysis:main",
        ],
    },
)
