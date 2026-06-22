from glob import glob
from setuptools import setup


package_name = "ghost_sim_ros2"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Vinayak Manoj Nair",
    maintainer_email="vinayak@example.com",
    description="Simulation-only ROS2 tools for GHOST target tracking.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "synthetic_measurements = ghost_sim_ros2.synthetic_measurements:main",
            "cv_tracker = ghost_sim_ros2.cv_tracker:main",
            "evidence_logger = ghost_sim_ros2.evidence_logger:main",
        ],
    },
)
