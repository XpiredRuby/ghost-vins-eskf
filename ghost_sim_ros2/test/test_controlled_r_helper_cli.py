import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "collect_controlled_r_trial.sh"


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


def assert_no_evidence(tmp_path: Path) -> None:
    assert list(tmp_path.iterdir()) == []


def test_help_exits_zero_without_filesystem_side_effects(tmp_path: Path):
    result = run_helper(tmp_path, "--help")

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "Major environment variables:" in result.stdout
    assert_no_evidence(tmp_path)


def test_unknown_argument_fails_without_filesystem_side_effects(tmp_path: Path):
    result = run_helper(tmp_path, "--not-a-real-option")

    assert result.returncode != 0
    assert "unknown argument" in result.stderr
    assert_no_evidence(tmp_path)


def test_ros_setup_is_nounset_safe_and_does_not_start_collection(tmp_path: Path):
    result = run_helper(tmp_path, "--check-ros-environment")

    assert result.returncode == 0, result.stderr
    assert "nounset restored" in result.stdout
    assert_no_evidence(tmp_path)

def test_rejected_redundant_control_write_uses_matching_readback():
    source = SCRIPT.read_text()

    assert "SET_REJECTED_BUT_READBACK_OK" in source
    assert 'if [[ "$actual" == "$value" ]]' in source
    assert "READBACK_OK_AFTER_REJECTED_WRITE" in source
    assert 'CONTROL_FAILURE=1' in source

def test_recorder_timeout_includes_predeclared_startup_margin():
    source = SCRIPT.read_text()

    assert 'RECORDER_STARTUP_MARGIN_S="${RECORDER_STARTUP_MARGIN_S:-4}"' in source
    assert '"${RECORDER_TIMEOUT_S}s"' in source
    assert 'recorder_timeout_s=$RECORDER_TIMEOUT_S' in source

def test_controlled_r_uses_first_vision_time_origin():
    source = SCRIPT.read_text()

    assert '-p relative_time_origin:=first_vision' in source
    assert 'recorder_relative_time_origin=first_vision' in source


def test_modern_uvc_controls_are_locked_when_supported():
    source = SCRIPT.read_text()

    for control in (
        "auto_exposure",
        "exposure_time_absolute",
        "exposure_dynamic_framerate",
        "white_balance_automatic",
        "power_line_frequency",
    ):
        assert f"set_control_if_supported {control}" in source
        assert f"verify_control_if_supported \"$stage\" {control}" in source


def test_menu_control_readback_uses_numeric_token_only():
    source = SCRIPT.read_text()

    assert 'split(value, parts, /[[:space:]]+/)' in source
    assert 'print parts[1]' in source
