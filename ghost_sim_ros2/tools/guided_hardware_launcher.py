"""Single-command browser-guided GHOST physical-validation supervisor.

This tool launches the calibrated AprilTag publisher with live preview, the formal
IMM tracker, the GHOST-MH tracker, the trial recorder, and the existing browser
conductor.  It intentionally records guided relative-motion/dropout evidence;
it does not convert approximate hand motions into absolute ground truth.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_ROOT = Path(
    "/home/xpired/ghost_trials/physical_validation_20260711T183400Z/browser_guided_runs"
)
REPO_ROOT = Path("/home/xpired/ghost_ws/src/ghost-vins-eskf")
WORKSPACE_ROOT = Path("/home/xpired/ghost_ws")
ROS_SETUP = Path("/opt/ros/jazzy/setup.bash")
WORKSPACE_SETUP = WORKSPACE_ROOT / "install/setup.bash"
VENV_PYTHON = Path("/home/xpired/ghost_venv/bin/python")
CALIBRATION = Path("/home/xpired/ghost_camera_calibration.json")
PARAMS_FILE = REPO_ROOT / "ghost_sim_ros2/config/phase2_candidate_parameters.yaml"
CAMERA_SCRIPT = REPO_ROOT / "ghost_sim_ros2/ghost_sim_ros2/apriltag_ros_only.py"
CONDUCTOR_SCRIPT = REPO_ROOT / "ghost_sim_ros2/tools/trial_conductor.py"
TRIAL_ID = "guided_relative_motion_dropout_01"
CONDITION_ID = "guided_relative_motion_dropout"
STATE_NAME = "launcher_state.json"
LATEST_NAME = "latest_run.json"
SUMMARY_NAME = "launcher_summary.json"
CONFLICT_MARKERS = (
    "apriltag_ros_only.py",
    "ghost_live_apriltag_pose_calibrated.py",
    "direct_controlled_r_capture.py",
    "formal_imm_tracker",
    "mh_tracker",
    "trial_recorder",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def timestamp_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def phase(cue: str, duration_s: float, instruction: str, phase_type: str, speak: str) -> dict[str, Any]:
    return {
        "cue": cue,
        "duration_s": float(duration_s),
        "instruction": instruction,
        "phase_type": phase_type,
        "speak": speak,
    }


def guided_phases() -> list[dict[str, Any]]:
    return [
        phase(
            "ALIGN CENTER",
            10.0,
            "Use the live preview. Center the full AprilTag, keep every corner visible, and hold the webcam still.",
            "hold",
            "Align center. Use the live preview. Keep the full AprilTag visible and hold the webcam still.",
        ),
        phase(
            "CENTER BASELINE",
            5.0,
            "Do not move the webcam or AprilTag. This is the centered baseline sample.",
            "sample",
            "Center baseline. Hold everything still for five seconds.",
        ),
        phase(
            "MOVE LEFT",
            4.0,
            "Move the webcam smoothly to your left while keeping the complete AprilTag visible.",
            "move",
            "Move the webcam left now. Keep the complete tag visible.",
        ),
        phase("HOLD LEFT", 5.0, "Hold the webcam still at the left position.", "hold", "Hold left and keep still."),
        phase("RETURN CENTER", 4.0, "Move the webcam smoothly back to the centered position.", "move", "Return the webcam to center."),
        phase("HOLD CENTER", 3.0, "Hold the centered position still.", "hold", "Hold center."),
        phase(
            "MOVE RIGHT",
            4.0,
            "Move the webcam smoothly to your right while keeping the complete AprilTag visible.",
            "move",
            "Move the webcam right now. Keep the complete tag visible.",
        ),
        phase("HOLD RIGHT", 5.0, "Hold the webcam still at the right position.", "hold", "Hold right and keep still."),
        phase("RETURN CENTER", 4.0, "Move the webcam smoothly back to the centered position.", "move", "Return the webcam to center."),
        phase("HOLD CENTER", 3.0, "Hold the centered position still.", "hold", "Hold center."),
        phase(
            "MOVE CLOSER",
            4.0,
            "Move the webcam smoothly closer to the AprilTag without changing its tilt.",
            "move",
            "Move the webcam closer now. Keep the complete tag visible.",
        ),
        phase("HOLD CLOSER", 5.0, "Hold the closer position still.", "hold", "Hold the closer position."),
        phase("RETURN CENTER", 4.0, "Move the webcam back to the centered starting distance.", "move", "Return to the center distance."),
        phase("HOLD CENTER", 3.0, "Hold the centered position still.", "hold", "Hold center."),
        phase(
            "MOVE FARTHER",
            4.0,
            "Move the webcam smoothly farther from the AprilTag while keeping the complete tag visible.",
            "move",
            "Move the webcam farther now. Keep the complete tag visible.",
        ),
        phase("HOLD FARTHER", 5.0, "Hold the farther position still.", "hold", "Hold the farther position."),
        phase("RETURN CENTER", 4.0, "Move the webcam back to the centered starting position.", "move", "Return the webcam to center."),
        phase("HOLD CENTER", 5.0, "Hold the centered position still before occlusion.", "hold", "Hold center before the dropout test."),
        phase(
            "PREPARE OCCLUSION",
            5.0,
            "Prepare an opaque card beside the AprilTag. Cover the full tag only. Do not cover the webcam lens.",
            "occlude",
            "Prepare to cover the entire AprilTag only. Do not cover the camera lens.",
        ),
        phase(
            "OCCLUDE TAG",
            2.0,
            "Cover the entire AprilTag with the opaque card for exactly two seconds. Leave the webcam lens uncovered.",
            "occlude",
            "Occlude the entire AprilTag now for exactly two seconds. Do not cover the camera lens.",
        ),
        phase(
            "REVEAL",
            0.0,
            "Remove the card immediately and reveal the complete AprilTag. Keep the webcam still.",
            "reveal",
            "Reveal the AprilTag now and keep the webcam still.",
        ),
        phase(
            "RECOVERY HOLD",
            7.0,
            "Keep the revealed tag and webcam completely still while both trackers recover.",
            "hold",
            "Recovery hold. Keep everything still for seven seconds.",
        ),
        phase("POST-ROLL", 3.0, "Remain still while the recorder finishes.", "post", "Post roll. Remain still."),
        phase("DONE", 0.0, "The guided cue sequence is complete.", "done", "Guided validation sequence complete."),
    ]


def normalize_public_host(value: str | None) -> str:
    if value:
        host = value.strip()
    else:
        host = socket.gethostname().strip()
        if host and "." not in host:
            host = f"{host}.local"
    if not host or any(char in host for char in "/\\ "):
        raise ValueError("public host must be a hostname or IP address without a URL scheme or path")
    return host


def build_plan(public_host: str, preview_port: int = 8081) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": "browser_guided_physical_validation",
        "protocol_commit": "WORKING_TREE_GUIDED_RUN",
        "sequence": 1,
        "trial_id": TRIAL_ID,
        "condition_id": CONDITION_ID,
        "repetition": 1,
        "motion_profile": "operator_guided_relative_camera_motion_and_short_tag_occlusion",
        "target_occlusion_duration_s": 2.0,
        "preview_stream_url": f"http://{public_host}:{preview_port}/stream",
        "phases": guided_phases(),
        "acceptance_note": (
            "Measured vision timestamps and recorder events are the source of truth. "
            "Hand-guided positions provide relative-motion coverage only, not absolute ground truth."
        ),
    }


def write_conductor_files(run_dir: Path, public_host: str, preview_port: int = 8081) -> dict[str, Any]:
    trial_dir = run_dir / "trial_directories" / TRIAL_ID
    trial_dir.mkdir(parents=True, exist_ok=False)
    plan = build_plan(public_host, preview_port)
    atomic_write_json(trial_dir / "conductor_plan.json", plan)
    atomic_write_json(
        trial_dir / "trial_metadata.json",
        {
            "schema_version": 1,
            "trial_id": TRIAL_ID,
            "condition_id": CONDITION_ID,
            "status": "planned",
            "created_at_utc": utc_now(),
            "evidence_scope": "GUIDED_RELATIVE_MOTION_AND_DROPOUT_NOT_ABSOLUTE_GROUND_TRUTH",
        },
    )
    order_path = run_dir / "randomized_trial_order.csv"
    with order_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "sequence",
                "trial_id",
                "condition_id",
                "repetition",
                "target_occlusion_duration_s",
                "motion_profile",
                "primary_metric",
            ]
        )
        writer.writerow(
            [
                1,
                TRIAL_ID,
                CONDITION_ID,
                1,
                2.0,
                plan["motion_profile"],
                "measured_vision_gap_and_reacquisition",
            ]
        )
    return plan


def command_map(run_dir: Path, conductor_port: int = 8765, preview_port: int = 8081) -> dict[str, list[str]]:
    recorder_root = run_dir / "recorder_trials"
    return {
        "camera": [
            str(VENV_PYTHON),
            str(CAMERA_SCRIPT),
            "--device",
            "/dev/video0",
            "--width",
            "640",
            "--height",
            "480",
            "--fps",
            "30",
            "--port",
            str(preview_port),
            "--tag-size",
            "0.100",
            "--calib",
            str(CALIBRATION),
            "--use-controlled-r-candidate",
            "--enable-preview-jpeg",
            "--preview-fps",
            "5",
        ],
        "imm": [
            "ros2",
            "run",
            "ghost_sim_ros2",
            "formal_imm_tracker",
            "--ros-args",
            "--params-file",
            str(PARAMS_FILE),
        ],
        "mh": [
            "ros2",
            "run",
            "ghost_sim_ros2",
            "mh_tracker",
            "--ros-args",
            "--params-file",
            str(PARAMS_FILE),
        ],
        "recorder": [
            "ros2",
            "run",
            "ghost_sim_ros2",
            "trial_recorder",
            "--ros-args",
            "-p",
            f"trial_root:={recorder_root}",
            "-p",
            "relative_time_origin:=first_vision",
        ],
        "conductor": [
            sys.executable,
            str(CONDUCTOR_SCRIPT),
            "--campaign-dir",
            str(run_dir),
            "--sequence",
            "1",
            "--host",
            "0.0.0.0",
            "--port",
            str(conductor_port),
        ],
    }


def parse_process_table(text: str, own_pid: int | None = None) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        pid = int(parts[0])
        command = parts[1]
        if own_pid is not None and pid == own_pid:
            continue
        marker = next((item for item in CONFLICT_MARKERS if item in command), None)
        if marker:
            conflicts.append({"pid": pid, "marker": marker, "command": command})
    return conflicts


def find_conflicts() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_process_table(result.stdout, own_pid=os.getpid())


def pid_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def load_ros_environment() -> dict[str, str]:
    command = (
        f"source {shlex.quote(str(ROS_SETUP))} && "
        f"source {shlex.quote(str(WORKSPACE_SETUP))} && env -0"
    )
    result = subprocess.run(
        ["bash", "-c", command],
        check=True,
        capture_output=True,
    )
    environment: dict[str, str] = {}
    for item in result.stdout.split(b"\0"):
        if not item or b"=" not in item:
            continue
        key, value = item.split(b"=", 1)
        environment[key.decode()] = value.decode()
    environment["PYTHONUNBUFFERED"] = "1"
    environment["PATH"] = f"{VENV_PYTHON.parent}:{environment.get('PATH', os.environ.get('PATH', ''))}"
    return environment


def wait_http(url: str, processes: Iterable[subprocess.Popen[Any]], timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = "not attempted"
    while time.monotonic() < deadline:
        failed = [process for process in processes if process.poll() is not None]
        if failed:
            raise RuntimeError(f"child process exited during readiness check with code {failed[0].returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise TimeoutError(f"timed out waiting for {url}: {last_error}")


def terminate_process_group(process: subprocess.Popen[Any], first_signal: signal.Signals, wait_s: float = 8.0) -> int | None:
    if process.poll() is not None:
        return process.returncode
    try:
        os.killpg(process.pid, first_signal)
    except ProcessLookupError:
        return process.poll()
    try:
        return process.wait(timeout=wait_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return process.poll()
    try:
        return process.wait(timeout=4.0)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return process.poll()
        return process.wait(timeout=3.0)


def latest_run_pointer(root: Path) -> Path:
    return root / LATEST_NAME


def state_path(run_dir: Path) -> Path:
    return run_dir / STATE_NAME


def update_state(run_dir: Path, **changes: Any) -> dict[str, Any]:
    path = state_path(run_dir)
    current = read_json(path) if path.exists() else {}
    current.update(changes)
    current["updated_at_utc"] = utc_now()
    atomic_write_json(path, current)
    return current


def read_latest_state(root: Path) -> tuple[Path, dict[str, Any]]:
    pointer = read_json(latest_run_pointer(root))
    run_dir = Path(str(pointer["run_dir"]))
    return run_dir, read_json(state_path(run_dir))


def event_types(event_path: Path) -> list[str]:
    if not event_path.exists():
        return []
    result: list[str] = []
    for line in event_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        value = event.get("type")
        if isinstance(value, str):
            result.append(value)
    return result


def discover_recorder_trial(run_dir: Path) -> Path | None:
    root = run_dir / "recorder_trials"
    if not root.exists():
        return None
    directories = [path for path in root.iterdir() if path.is_dir()]
    return max(directories, key=lambda path: path.stat().st_mtime, default=None)


def child_state(processes: dict[str, subprocess.Popen[Any]]) -> dict[str, Any]:
    return {
        name: {
            "pid": process.pid,
            "process_group_id": process.pid,
            "running": process.poll() is None,
            "exit_code": process.poll(),
        }
        for name, process in processes.items()
    }


def launch_child(
    name: str,
    argv: list[str],
    run_dir: Path,
    environment: dict[str, str],
    log_handles: dict[str, Any],
) -> subprocess.Popen[Any]:
    log_path = run_dir / "logs" / f"{name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab", buffering=0)
    log_handles[name] = handle
    header = f"[{utc_now()}] argv={json.dumps(argv)}\n".encode()
    handle.write(header)
    return subprocess.Popen(
        argv,
        cwd=REPO_ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def cleanup_processes(processes: dict[str, subprocess.Popen[Any]]) -> dict[str, int | None]:
    exits: dict[str, int | None] = {}
    order = (
        ("recorder", signal.SIGINT),
        ("conductor", signal.SIGINT),
        ("mh", signal.SIGINT),
        ("imm", signal.SIGINT),
        ("camera", signal.SIGINT),
    )
    for name, first_signal in order:
        process = processes.get(name)
        if process is not None:
            exits[name] = terminate_process_group(process, first_signal)
    return exits


def run_supervisor(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    public_host = normalize_public_host(args.public_host)
    browser_url = f"http://{public_host}:{args.conductor_port}"
    preview_health = f"http://127.0.0.1:{args.preview_port}/"
    conductor_health = f"http://127.0.0.1:{args.conductor_port}/api/health"
    event_path = run_dir / "trial_directories" / TRIAL_ID / "conductor_events.jsonl"
    commands = command_map(run_dir, args.conductor_port, args.preview_port)
    stop_requested = False
    stop_reason = "unknown"
    processes: dict[str, subprocess.Popen[Any]] = {}
    log_handles: dict[str, Any] = {}

    def request_stop(signum: int, _frame: Any) -> None:
        nonlocal stop_requested, stop_reason
        stop_requested = True
        stop_reason = signal.Signals(signum).name

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    update_state(
        run_dir,
        lifecycle_status="SUPERVISOR_STARTING",
        supervisor_pid=os.getpid(),
        browser_url=browser_url,
    )

    final_status = "FAILED"
    terminal_event: str | None = None
    failure: str | None = None
    exit_codes: dict[str, int | None] = {}
    try:
        environment = load_ros_environment()
        processes["camera"] = launch_child("camera", commands["camera"], run_dir, environment, log_handles)
        update_state(run_dir, children=child_state(processes), lifecycle_status="WAITING_FOR_CAMERA")
        wait_http(preview_health, processes.values(), timeout_s=25.0)

        processes["imm"] = launch_child("imm", commands["imm"], run_dir, environment, log_handles)
        processes["mh"] = launch_child("mh", commands["mh"], run_dir, environment, log_handles)
        time.sleep(2.0)
        dead = [name for name in ("imm", "mh") if processes[name].poll() is not None]
        if dead:
            raise RuntimeError(f"tracker startup failed: {dead}")

        processes["recorder"] = launch_child("recorder", commands["recorder"], run_dir, environment, log_handles)
        time.sleep(1.0)
        if processes["recorder"].poll() is not None:
            raise RuntimeError("trial recorder exited during startup")

        processes["conductor"] = launch_child("conductor", commands["conductor"], run_dir, environment, log_handles)
        update_state(run_dir, children=child_state(processes), lifecycle_status="WAITING_FOR_CONDUCTOR")
        wait_http(conductor_health, processes.values(), timeout_s=15.0)
        update_state(
            run_dir,
            lifecycle_status="RUNNING",
            ready_at_utc=utc_now(),
            children=child_state(processes),
            browser_url=browser_url,
        )

        while not stop_requested:
            dead = {name: process.returncode for name, process in processes.items() if process.poll() is not None}
            if dead:
                raise RuntimeError(f"child process exited unexpectedly: {dead}")
            types = event_types(event_path)
            if "trial_rejected" in types:
                terminal_event = "trial_rejected"
                stop_reason = "BROWSER_REJECTED"
                final_status = "REJECTED"
                break
            if "cue_sequence_completed" in types:
                terminal_event = "cue_sequence_completed"
                stop_reason = "BROWSER_SEQUENCE_COMPLETE"
                final_status = "COMPLETED"
                time.sleep(3.0)
                break
            update_state(run_dir, lifecycle_status="RUNNING", children=child_state(processes))
            time.sleep(0.5)

        if stop_requested:
            final_status = "STOPPED"
    except Exception as exc:  # noqa: BLE001 - supervisor must preserve failure evidence
        failure = f"{type(exc).__name__}: {exc}"
        final_status = "FAILED"
        update_state(run_dir, lifecycle_status="FAILED_STARTUP_OR_RUNTIME", failure=failure, children=child_state(processes))
    finally:
        exit_codes = cleanup_processes(processes)
        for handle in log_handles.values():
            try:
                handle.close()
            except OSError:
                pass

        recorder_trial = discover_recorder_trial(run_dir)
        recorder_summary: dict[str, Any] | None = None
        if recorder_trial is not None:
            recorder_summary_path = recorder_trial / "summary.json"
            if recorder_summary_path.exists():
                try:
                    recorder_summary = read_json(recorder_summary_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    recorder_summary = None

        guided_sequence_summary: dict[str, Any] | None = None
        guided_sequence_failure: str | None = None
        guided_sequence_summary_path: Path | None = None
        try:
            plan = read_json(run_dir / "trial_directories" / TRIAL_ID / "conductor_plan.json")
            condition_id = str(plan.get("condition_id", ""))
            if condition_id == "guided_distance_only_retest":
                from analyze_distance_only_run import write_summary as write_guided_sequence_summary

                guided_sequence_summary_path = run_dir / "distance_only_summary.json"
            elif condition_id == "guided_closer_only_retest":
                from analyze_closer_only_run import write_summary as write_guided_sequence_summary

                guided_sequence_summary_path = run_dir / "closer_only_summary.json"
            else:
                from guided_run_analysis import write_summary as write_guided_sequence_summary

                guided_sequence_summary_path = run_dir / "guided_sequence_summary.json"
            guided_sequence_summary = write_guided_sequence_summary(run_dir)
        except Exception as exc:  # noqa: BLE001 - preserve raw evidence if post-processing fails
            guided_sequence_failure = f"{type(exc).__name__}: {exc}"

        summary = {
            "schema_version": 1,
            "run_dir": str(run_dir),
            "browser_url": browser_url,
            "final_status": final_status,
            "terminal_event": terminal_event,
            "stop_reason": stop_reason,
            "failure": failure,
            "finished_at_utc": utc_now(),
            "exit_codes": exit_codes,
            "recorder_trial_dir": str(recorder_trial) if recorder_trial else None,
            "recorder_summary": recorder_summary,
            "recorder_summary_scope": "FULL_SUPERVISOR_RUNTIME_MAY_INCLUDE_PRESTART_IDLE_TIME",
            "guided_sequence_summary_path": str(guided_sequence_summary_path) if guided_sequence_summary else None,
            "guided_sequence_summary": guided_sequence_summary,
            "guided_sequence_postprocess_failure": guided_sequence_failure,
            "evidence_scope": "GUIDED_RELATIVE_MOTION_AND_DROPOUT_NOT_ABSOLUTE_GROUND_TRUTH",
            "claim_limit": (
                "Approximate operator motion supports relative response and coverage evidence only. "
                "Measured recorder timestamps determine dropout/reacquisition acceptance."
            ),
        }
        atomic_write_json(run_dir / SUMMARY_NAME, summary)
        update_state(
            run_dir,
            lifecycle_status=final_status,
            terminal_event=terminal_event,
            stop_reason=stop_reason,
            failure=failure,
            children={
                name: {
                    "pid": process.pid,
                    "process_group_id": process.pid,
                    "running": False,
                    "exit_code": exit_codes.get(name),
                }
                for name, process in processes.items()
            },
            summary_path=str(run_dir / SUMMARY_NAME),
            finished_at_utc=utc_now(),
        )
    return 0 if final_status in {"COMPLETED", "REJECTED", "STOPPED"} else 1


def create_run(root: Path, public_host: str, conductor_port: int, preview_port: int) -> tuple[Path, str]:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = root / timestamp_id()
    suffix = 1
    while run_dir.exists():
        run_dir = root / f"{timestamp_id()}_{suffix:02d}"
        suffix += 1
    run_dir.mkdir(parents=False)
    (run_dir / "logs").mkdir()
    write_conductor_files(run_dir, public_host, preview_port)
    browser_url = f"http://{public_host}:{conductor_port}"
    state = {
        "schema_version": 1,
        "lifecycle_status": "CREATED",
        "created_at_utc": utc_now(),
        "run_dir": str(run_dir),
        "browser_url": browser_url,
        "public_host": public_host,
        "conductor_port": conductor_port,
        "preview_port": preview_port,
        "supervisor_pid": None,
        "children": {},
    }
    atomic_write_json(state_path(run_dir), state)
    atomic_write_json(latest_run_pointer(root), {"run_dir": str(run_dir), "updated_at_utc": utc_now()})
    return run_dir, browser_url


def start_detached(args: argparse.Namespace) -> int:
    root = Path(args.root)
    public_host = normalize_public_host(args.public_host)
    conflicts = find_conflicts()
    if conflicts and not args.force:
        print("Refusing to start because conflicting GHOST camera/tracker/recorder processes are running:", file=sys.stderr)
        for item in conflicts:
            print(f"  pid={item['pid']} marker={item['marker']} command={item['command']}", file=sys.stderr)
        print("Stop the manually launched processes, then run start again. --force skips only this refusal and does not kill anything.", file=sys.stderr)
        return 2

    run_dir, browser_url = create_run(root, public_host, args.conductor_port, args.preview_port)
    supervisor_log = run_dir / "logs/supervisor.log"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "run-supervisor",
        "--run-dir",
        str(run_dir),
        "--public-host",
        public_host,
        "--conductor-port",
        str(args.conductor_port),
        "--preview-port",
        str(args.preview_port),
    ]
    with supervisor_log.open("ab", buffering=0) as handle:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    update_state(run_dir, lifecycle_status="DETACHED_SUPERVISOR_STARTED", supervisor_pid=process.pid)

    deadline = time.monotonic() + args.startup_wait_s
    last_state = read_json(state_path(run_dir))
    while time.monotonic() < deadline:
        time.sleep(0.25)
        last_state = read_json(state_path(run_dir))
        status = str(last_state.get("lifecycle_status"))
        if status == "RUNNING":
            print(f"browser_url={browser_url}")
            print(f"run_dir={run_dir}")
            print(f"supervisor_pid={process.pid}")
            return 0
        if status.startswith("FAILED") or status == "FAILED":
            print(f"Launcher failed. See {supervisor_log}", file=sys.stderr)
            return 1
        if process.poll() is not None:
            print(f"Supervisor exited with code {process.returncode}. See {supervisor_log}", file=sys.stderr)
            return 1

    print(f"browser_url={browser_url}")
    print(f"run_dir={run_dir}")
    print(f"supervisor_pid={process.pid}")
    print(f"status={last_state.get('lifecycle_status')} (use status to continue checking)")
    return 0


def status_command(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    try:
        run_dir, state = read_latest_state(root)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"No readable launcher state under {root}: {exc}", file=sys.stderr)
        return 1
    supervisor_pid = state.get("supervisor_pid")
    output = dict(state)
    output["supervisor_running"] = pid_alive(supervisor_pid if isinstance(supervisor_pid, int) else None)
    children = output.get("children")
    if isinstance(children, dict):
        for item in children.values():
            if isinstance(item, dict):
                pid = item.get("pid")
                item["observed_running"] = pid_alive(pid if isinstance(pid, int) else None)
    output["run_dir"] = str(run_dir)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def signal_pid_group(pid: int, signum: signal.Signals) -> None:
    try:
        os.killpg(pid, signum)
    except ProcessLookupError:
        pass


def stop_command(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    try:
        run_dir, state = read_latest_state(root)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"No readable launcher state under {root}: {exc}", file=sys.stderr)
        return 1

    supervisor_pid = state.get("supervisor_pid")
    if isinstance(supervisor_pid, int) and pid_alive(supervisor_pid):
        os.kill(supervisor_pid, signal.SIGTERM)
        deadline = time.monotonic() + args.wait_s
        while time.monotonic() < deadline and pid_alive(supervisor_pid):
            time.sleep(0.25)
        if pid_alive(supervisor_pid):
            print(f"Supervisor {supervisor_pid} did not stop within {args.wait_s:.1f}s", file=sys.stderr)
            return 1
        print(f"Stopped launcher for {run_dir}")
        return 0

    children = state.get("children") if isinstance(state.get("children"), dict) else {}
    for name in ("recorder", "conductor", "mh", "imm", "camera"):
        item = children.get(name)
        if not isinstance(item, dict):
            continue
        pgid = item.get("process_group_id")
        if isinstance(pgid, int) and pid_alive(pgid):
            signal_pid_group(pgid, signal.SIGINT)
            time.sleep(0.5)
    update_state(run_dir, lifecycle_status="STOP_REQUESTED_WITHOUT_LIVE_SUPERVISOR", stop_reason="CLI_FALLBACK_STOP")
    print(f"Issued fallback stop only to recorded child process groups for {run_dir}")
    return 0


def plan_command(args: argparse.Namespace) -> int:
    public_host = normalize_public_host(args.public_host)
    value = {
        "plan": build_plan(public_host, args.preview_port),
        "commands": command_map(Path("/tmp/GHOST_DRY_RUN"), args.conductor_port, args.preview_port),
        "browser_url": f"http://{public_host}:{args.conductor_port}",
        "dry_run": True,
    }
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-command browser-guided GHOST physical validation launcher.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=str(DEFAULT_ROOT))
    common.add_argument("--public-host", help="Hostname or IP used by the browser; default is <Pi-hostname>.local")
    common.add_argument("--conductor-port", type=int, default=8765)
    common.add_argument("--preview-port", type=int, default=8081)

    start = subparsers.add_parser("start", parents=[common], help="Start the detached supervisor.")
    start.add_argument("--force", action="store_true", help="Skip conflict refusal without killing existing processes.")
    start.add_argument("--startup-wait-s", type=float, default=30.0)
    start.set_defaults(func=start_detached)

    status = subparsers.add_parser("status", parents=[common], help="Show the latest launcher state.")
    status.set_defaults(func=status_command)

    stop = subparsers.add_parser("stop", parents=[common], help="Gracefully stop the latest launcher.")
    stop.add_argument("--wait-s", type=float, default=20.0)
    stop.set_defaults(func=stop_command)

    dry_run = subparsers.add_parser("dry-run", parents=[common], help="Print the plan and commands without hardware access.")
    dry_run.set_defaults(func=plan_command)

    supervisor = subparsers.add_parser("run-supervisor", help=argparse.SUPPRESS)
    supervisor.add_argument("--run-dir", required=True)
    supervisor.add_argument("--public-host", required=True)
    supervisor.add_argument("--conductor-port", type=int, default=8765)
    supervisor.add_argument("--preview-port", type=int, default=8081)
    supervisor.set_defaults(func=run_supervisor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "conductor_port", 8765) <= 0 or getattr(args, "preview_port", 8081) <= 0:
        raise SystemExit("ports must be positive")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
