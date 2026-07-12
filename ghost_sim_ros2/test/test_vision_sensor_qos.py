from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "ghost_sim_ros2"


def source(name: str) -> str:
    return (ROOT / name).read_text()


def test_apriltag_publisher_uses_sensor_data_qos():
    text = source("apriltag_ros_only.py")
    assert "qos_profile_sensor_data" in text
    assert '"/ghost/vision/target_pose",\n        qos_profile_sensor_data' in text


def test_vision_consumers_use_sensor_data_qos():
    for name in (
        "trial_recorder.py",
        "formal_imm_tracker.py",
        "mh_tracker.py",
        "cv_tracker.py",
        "evidence_logger.py",
    ):
        text = source(name)
        assert "qos_profile_sensor_data" in text


def test_tracker_outputs_keep_separate_reliable_qos():
    for name in ("formal_imm_tracker.py", "mh_tracker.py"):
        text = source(name)
        assert "output_qos = QoSProfile(depth=1)" in text
        assert "create_publisher(Odometry" in text
        assert "output_qos" in text


def test_apriltag_tracking_path_avoids_preview_work_by_default():
    text = source("apriltag_ros_only.py")
    assert '"--enable-preview-jpeg"' in text
    assert "cv2.setNumThreads(1)" in text
    assert "if args.enable_preview_jpeg:" in text
    assert "tag = max(tags" in text
