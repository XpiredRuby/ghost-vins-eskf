from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "tools" / "guided_hardware_launcher.py"
SPEC = importlib.util.spec_from_file_location("guided_hardware_launcher", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_guided_plan_has_predeclared_order_and_exact_short_occlusion():
    plan = launcher.build_plan("ghost-pi.local", 8081)
    cues = [item["cue"] for item in plan["phases"]]

    assert cues == [
        "ALIGN CENTER",
        "CENTER BASELINE",
        "MOVE LEFT",
        "HOLD LEFT",
        "RETURN CENTER",
        "HOLD CENTER",
        "MOVE RIGHT",
        "HOLD RIGHT",
        "RETURN CENTER",
        "HOLD CENTER",
        "MOVE CLOSER",
        "HOLD CLOSER",
        "RETURN CENTER",
        "HOLD CENTER",
        "MOVE FARTHER",
        "HOLD FARTHER",
        "RETURN CENTER",
        "HOLD CENTER",
        "PREPARE OCCLUSION",
        "OCCLUDE TAG",
        "REVEAL",
        "RECOVERY HOLD",
        "POST-ROLL",
        "DONE",
    ]
    occlusion = next(item for item in plan["phases"] if item["cue"] == "OCCLUDE TAG")
    assert occlusion["duration_s"] == 2.0
    assert "Do not cover the camera lens" in occlusion["speak"]
    assert plan["preview_stream_url"] == "http://ghost-pi.local:8081/stream"
    assert "not absolute ground truth" in plan["acceptance_note"]


def test_atomic_state_round_trip_replaces_existing_content(tmp_path):
    path = tmp_path / "state.json"
    launcher.atomic_write_json(path, {"status": "one", "value": 1})
    launcher.atomic_write_json(path, {"status": "two", "value": 2})

    assert launcher.read_json(path) == {"status": "two", "value": 2}
    assert not list(tmp_path.glob(".*.tmp"))


def test_process_conflict_matching_is_specific_and_excludes_own_pid():
    table = """
      101 /usr/bin/python3 unrelated_program.py
      202 /home/xpired/ghost_venv/bin/python apriltag_ros_only.py --device /dev/video0
      303 ros2 run ghost_sim_ros2 formal_imm_tracker
      404 ros2 topic echo /ghost/tracker_mh/status
      505 ros2 run ghost_sim_ros2 trial_recorder
    """
    conflicts = launcher.parse_process_table(table, own_pid=303)

    assert [(item["pid"], item["marker"]) for item in conflicts] == [
        (202, "apriltag_ros_only.py"),
        (505, "trial_recorder"),
    ]


def test_command_map_uses_preview_controlled_r_and_run_scoped_recorder(tmp_path):
    commands = launcher.command_map(tmp_path, conductor_port=9000, preview_port=9001)

    assert commands["camera"][0] == str(launcher.VENV_PYTHON)
    assert "--use-controlled-r-candidate" in commands["camera"]
    assert "--enable-preview-jpeg" in commands["camera"]
    assert commands["camera"][commands["camera"].index("--port") + 1] == "9001"
    assert str(tmp_path / "recorder_trials") in " ".join(commands["recorder"])
    assert commands["conductor"][-1] == "9000"
    assert commands["imm"][3] == "formal_imm_tracker"
    assert commands["mh"][3] == "mh_tracker"


def test_conductor_files_are_compatible_and_scoped(tmp_path):
    plan = launcher.write_conductor_files(tmp_path, "ghost-pi.local", 8081)
    order = (tmp_path / "randomized_trial_order.csv").read_text(encoding="utf-8")
    saved = json.loads(
        (tmp_path / "trial_directories" / launcher.TRIAL_ID / "conductor_plan.json").read_text(
            encoding="utf-8"
        )
    )

    assert launcher.TRIAL_ID in order
    assert saved == plan
    assert saved["sequence"] == 1
    assert saved["condition_id"] == launcher.CONDITION_ID


def test_dry_run_prints_plan_without_creating_hardware_state(capsys):
    args = argparse.Namespace(
        public_host="ghost-pi.local",
        conductor_port=8765,
        preview_port=8081,
    )

    assert launcher.plan_command(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["browser_url"] == "http://ghost-pi.local:8765"
    assert payload["plan"]["trial_id"] == launcher.TRIAL_ID
