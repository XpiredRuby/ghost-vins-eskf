from glob import glob
from setuptools import setup


package_name = "ghost_sim_ros2"

setup(
    name=package_name,
    version="0.2.0",
    packages=[package_name, "analysis"],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
        (f"share/{package_name}/rviz", glob("rviz/*.rviz")),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/schemas", glob("schemas/*.json")),
        (f"share/{package_name}/analysis", glob("analysis/*.py")),
        (f"share/{package_name}/docs", glob("docs/*.md")),
    ],
    install_requires=["setuptools", "numpy", "jsonschema"],
    tests_require=["pytest"],
    zip_safe=True,
    maintainer="Vinayak Manoj Nair",
    maintainer_email="vinayak@example.com",
    description=(
        "ROS 2 GPS-denied occlusion-aware target tracking, prediction, navigation, "
        "hardware validation, and evidence tools for GHOST."
    ),
    license="MIT",
    entry_points={
        "console_scripts": [
            "synthetic_measurements = ghost_sim_ros2.synthetic_measurements:main",
            "mission_simulator = ghost_sim_ros2.mission_simulator:main",
            "observer_guidance = ghost_sim_ros2.observer_guidance:main",
            "mission_evaluator = ghost_sim_ros2.mission_evaluator:main",
            "mission_dashboard = ghost_sim_ros2.mission_dashboard:main",
            "cv_tracker = ghost_sim_ros2.cv_tracker:main",
            "mh_tracker = ghost_sim_ros2.mh_tracker:main",
            "formal_imm_tracker = ghost_sim_ros2.formal_imm_tracker:main",
            "mh_monitor = ghost_sim_ros2.mh_monitor:main",
            "mh_web_dashboard = ghost_sim_ros2.mh_web_dashboard:main",
            "trial_recorder = ghost_sim_ros2.trial_recorder:main",
            "evidence_logger = ghost_sim_ros2.evidence_logger:main",
            "gazebo_bridge = ghost_sim_ros2.gazebo_bridge:main",
            "imu_watchdog = ghost_sim_ros2.imu_watchdog:main",
            "stationary_noise_analysis = analysis.stationary_noise_analysis:main",
            "measurement_covariance = analysis.measurement_covariance:main",
            "observability_crlb = analysis.observability_crlb:main",
            "imm_tracker = analysis.imm_tracker:main",
            "stats_harness = analysis.stats_harness:main",
            "tracker_comparison = analysis.tracker_comparison:main",
        ],
    },
)
