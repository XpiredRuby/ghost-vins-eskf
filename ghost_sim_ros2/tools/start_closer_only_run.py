from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

LAUNCHER_PATH = Path(__file__).with_name("guided_hardware_launcher.py")
SPEC = importlib.util.spec_from_file_location("guided_hardware_launcher", LAUNCHER_PATH)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)

ROOT = launcher.DEFAULT_ROOT
HOST = launcher.normalize_public_host(None)
CONDUCTOR_PORT = 8765
PREVIEW_PORT = 8081
TRIAL_ID = launcher.TRIAL_ID


def p(cue: str, duration: float, instruction: str, phase_type: str, speak: str) -> dict:
    return {"cue": cue, "duration_s": float(duration), "instruction": instruction, "phase_type": phase_type, "speak": speak}


def main() -> int:
    conflicts = launcher.find_conflicts()
    if conflicts:
        print(json.dumps({"error": "conflicting processes", "conflicts": conflicts}, indent=2), file=sys.stderr)
        return 2

    run_dir, browser_url = launcher.create_run(ROOT, HOST, CONDUCTOR_PORT, PREVIEW_PORT)
    plan_path = run_dir / "trial_directories" / TRIAL_ID / "conductor_plan.json"
    plan = launcher.read_json(plan_path)
    plan.update({
        "condition_id": "guided_closer_only_retest",
        "motion_profile": "operator_guided_small_closer_retest",
        "target_occlusion_duration_s": 0.0,
        "phases": [
            p("ALIGN CENTER", 10, "Use the preview. Keep the entire AprilTag centered with all four corners clearly visible.", "hold", "Align center. Keep the entire AprilTag clearly visible."),
            p("CENTER BASELINE", 5, "Hold the webcam and tag completely still.", "sample", "Center baseline. Hold everything still."),
            p("MOVE SLIGHTLY CLOSER", 6, "Move the webcam slowly only eight to ten centimeters closer. Stop immediately if any corner approaches the image edge.", "move", "Move only eight to ten centimeters closer. Keep all four corners visible. Stop if the tag approaches an image edge."),
            p("HOLD CLOSER", 8, "Stop moving and hold the closer position completely still with all four corners visible.", "hold", "Hold closer. Keep all four corners visible and hold completely still."),
            p("RETURN CENTER", 6, "Move slowly back to the original centered distance.", "move", "Return slowly to the original center distance."),
            p("FINAL CENTER HOLD", 5, "Hold the original center position completely still.", "hold", "Final center hold. Keep still."),
            p("POST-ROLL", 3, "Remain still while recording finishes.", "post", "Post roll. Remain still."),
            p("DONE", 0, "Closer-only retest complete.", "done", "Closer only retest complete."),
        ],
        "acceptance_note": "Closer-only relative response retest. Require at least 20 valid stable hold samples, correct range direction, no reset, and successful return to center.",
    })
    launcher.atomic_write_json(plan_path, plan)

    order_path = run_dir / "randomized_trial_order.csv"
    with order_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sequence", "trial_id", "condition_id", "repetition", "target_occlusion_duration_s", "motion_profile", "primary_metric"])
        writer.writerow([1, TRIAL_ID, "guided_closer_only_retest", 1, 0.0, "operator_guided_small_closer_retest", "stable_closer_hold_samples"])

    supervisor_log = run_dir / "logs" / "supervisor.log"
    command = [sys.executable, str(LAUNCHER_PATH), "run-supervisor", "--run-dir", str(run_dir), "--public-host", HOST, "--conductor-port", str(CONDUCTOR_PORT), "--preview-port", str(PREVIEW_PORT)]
    with supervisor_log.open("ab", buffering=0) as handle:
        process = subprocess.Popen(command, cwd=launcher.REPO_ROOT, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
    launcher.update_state(run_dir, lifecycle_status="DETACHED_SUPERVISOR_STARTED", supervisor_pid=process.pid)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        time.sleep(0.25)
        state = launcher.read_json(launcher.state_path(run_dir))
        status = str(state.get("lifecycle_status"))
        if status == "RUNNING":
            print(f"browser_url={browser_url}")
            print(f"run_dir={run_dir}")
            print(f"supervisor_pid={process.pid}")
            return 0
        if status.startswith("FAILED") or process.poll() is not None:
            print(f"failed; see {supervisor_log}", file=sys.stderr)
            return 1
    print(f"browser_url={browser_url}")
    print(f"run_dir={run_dir}")
    print(f"supervisor_pid={process.pid}")
    print("status=STARTING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
