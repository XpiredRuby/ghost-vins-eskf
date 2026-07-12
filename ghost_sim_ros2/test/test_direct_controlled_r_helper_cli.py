import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "collect_controlled_r_direct_trial.sh"
CAPTURE = ROOT / "tools" / "direct_controlled_r_capture.py"


def run_helper(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TRIAL_ROOT"] = str(tmp_path)
    return subprocess.run(
        ["bash", str(SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )


def test_help_exits_zero_without_evidence(tmp_path: Path):
    result = run_helper(tmp_path, "--help")

    assert result.returncode == 0
    assert "Direct" in result.stdout or "direct" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_unknown_argument_fails_without_evidence(tmp_path: Path):
    result = run_helper(tmp_path, "--not-valid")

    assert result.returncode != 0
    assert "unknown argument" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_capture_cli_help_does_not_open_camera():
    result = subprocess.run(
        ["python3", str(CAPTURE), "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0
    assert "--duration-s" in result.stdout
    assert "--out-dir" in result.stdout


def test_direct_source_mapping_is_explicit():
    source = CAPTURE.read_text()

    assert "cam_x = float(tvec[0][0])" in source
    assert "cam_z = float(tvec[2][0])" in source
    assert "'x_m': cam_z" in source
    assert "'y_m': cam_x" in source
    assert "DIRECT_CAMERA_APRILTAG_SOLVEPNP_NO_ROS_TRANSPORT" in source
