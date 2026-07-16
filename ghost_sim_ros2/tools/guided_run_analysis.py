"""Post-process one browser-guided GHOST run using the browser cue window only."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

TRIAL_ID = "guided_relative_motion_dropout_01"


def _timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _phase_windows(events: list[dict[str, Any]]) -> tuple[float, float, list[dict[str, Any]]]:
    starts = [event for event in events if event.get("type") == "phase_started"]
    start_event = next(event for event in starts if event.get("cue") == "ALIGN CENTER")
    end_event = next(event for event in reversed(events) if event.get("type") == "cue_sequence_completed")
    start_s = _timestamp(str(start_event["server_received_at_utc"]))
    end_s = _timestamp(str(end_event["server_received_at_utc"]))
    selected = [event for event in starts if start_s <= _timestamp(str(event["server_received_at_utc"])) <= end_s]
    windows: list[dict[str, Any]] = []
    for index, event in enumerate(selected):
        phase_start = _timestamp(str(event["server_received_at_utc"]))
        phase_end = (
            _timestamp(str(selected[index + 1]["server_received_at_utc"]))
            if index + 1 < len(selected)
            else end_s
        )
        windows.append(
            {
                "index": index,
                "cue": str(event.get("cue")),
                "start_wall_time_s": phase_start,
                "end_wall_time_s": phase_end,
                "observed_duration_s": phase_end - phase_start,
            }
        )
    return start_s, end_s, windows


def _mean_hold(rows: list[dict[str, Any]], start_s: float, end_s: float) -> dict[str, Any]:
    stable_start = max(start_s, end_s - 2.2)
    stable_end = end_s - 0.2
    selected = [row for row in rows if stable_start <= float(row.get("wall_time_s", -1.0)) <= stable_end]
    if not selected:
        return {"sample_count": 0, "stable": False, "mean_x_m": None, "mean_y_m": None, "std_x_m": None, "std_y_m": None}
    xs = [float(row["position"]["x_m"]) for row in selected]
    ys = [float(row["position"]["y_m"]) for row in selected]
    return {
        "sample_count": len(selected),
        "stable": len(selected) >= 5,
        "mean_x_m": statistics.fmean(xs),
        "mean_y_m": statistics.fmean(ys),
        "std_x_m": statistics.stdev(xs) if len(xs) > 1 else 0.0,
        "std_y_m": statistics.stdev(ys) if len(ys) > 1 else 0.0,
    }


def _find_recorder_trial(run_dir: Path) -> Path:
    root = run_dir / "recorder_trials"
    trials = [path for path in root.iterdir() if path.is_dir()]
    if not trials:
        raise FileNotFoundError(f"no recorder trial under {root}")
    return max(trials, key=lambda path: path.stat().st_mtime)


def analyze_guided_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    conductor_path = run_dir / "trial_directories" / TRIAL_ID / "conductor_events.jsonl"
    recorder_dir = _find_recorder_trial(run_dir)
    conductor = _jsonl(conductor_path)
    recorder_events = _jsonl(recorder_dir / "events.jsonl")
    vision = _jsonl(recorder_dir / "vision_pose.jsonl")
    start_s, end_s, phases = _phase_windows(conductor)

    browser_completed = any(event.get("type") == "cue_sequence_completed" for event in conductor)
    sequence_events = [
        event
        for event in recorder_events
        if start_s - 1.0 <= float(event.get("wall_time_s", -1.0)) <= end_s + 3.0
    ]
    sequence_vision = [
        row for row in vision if start_s - 1.0 <= float(row.get("wall_time_s", -1.0)) <= end_s + 1.0
    ]

    occlude_phase = next(phase for phase in phases if phase["cue"] == "OCCLUDE TAG")
    reveal_phase = next(phase for phase in phases if phase["cue"] == "REVEAL")
    recovery_phase = next(phase for phase in phases if phase["cue"] == "RECOVERY HOLD")
    occlusion_starts = [
        event
        for event in sequence_events
        if event.get("event") == "OCCLUSION_START"
        and occlude_phase["start_wall_time_s"] - 1.0
        <= float(event.get("wall_time_s", -1.0))
        <= reveal_phase["end_wall_time_s"] + 1.0
    ]
    intended_start = min(
        occlusion_starts,
        key=lambda event: abs(float(event["wall_time_s"]) - occlude_phase["start_wall_time_s"]),
        default=None,
    )
    intended_reacquire = None
    if intended_start is not None:
        intended_reacquire = next(
            (
                event
                for event in sequence_events
                if event.get("event") == "REACQUIRED"
                and float(event.get("wall_time_s", -1.0)) >= float(intended_start["wall_time_s"])
                and float(event.get("wall_time_s", -1.0)) <= recovery_phase["end_wall_time_s"] + 2.0
            ),
            None,
        )

    intended: dict[str, Any] = {
        "browser_cue_duration_s": occlude_phase["observed_duration_s"],
        "measurement_loss_detected": intended_start is not None,
        "reacquired": intended_reacquire is not None,
        "measured_occlusion_duration_s": None,
        "reset_during_occlusion": None,
        "metrics": None,
        "pass": False,
    }
    if intended_start is not None and intended_reacquire is not None:
        start_wall = float(intended_start["wall_time_s"])
        end_wall = float(intended_reacquire["wall_time_s"])
        details = intended_reacquire.get("details", {})
        measured = float(details.get("occlusion_duration_s", end_wall - start_wall))
        resets = [
            event
            for event in sequence_events
            if event.get("event") == "RESET" and start_wall <= float(event.get("wall_time_s", -1.0)) <= end_wall
        ]
        cv_error = details.get("baselines", {}).get("constant_velocity", {}).get("error_m")
        hold_error = details.get("baselines", {}).get("last_seen_hold", {}).get("error_m")
        top1_error = details.get("ghost_mh", {}).get("top1_error_m")
        improvement = None
        if isinstance(cv_error, (int, float)) and cv_error > 0 and isinstance(top1_error, (int, float)):
            improvement = 100.0 * (float(cv_error) - float(top1_error)) / float(cv_error)
        intended.update(
            {
                "measured_occlusion_duration_s": measured,
                "reset_during_occlusion": bool(resets),
                "metrics": {
                    "last_seen_hold_error_m": hold_error,
                    "constant_velocity_error_m": cv_error,
                    "ghost_top1_error_m": top1_error,
                    "ghost_top3_best_error_m": details.get("ghost_mh", {}).get("top3_best_error_m"),
                    "ghost_top1_beats_constant_velocity": details.get("comparisons", {}).get("top1_beats_cv"),
                    "ghost_top1_improvement_vs_constant_velocity_percent": improvement,
                },
                "pass": measured < 3.0 and not resets,
            }
        )

    holds: list[dict[str, Any]] = []
    for phase in phases:
        cue = str(phase["cue"])
        if cue not in {"CENTER BASELINE", "HOLD LEFT", "HOLD CENTER", "HOLD RIGHT", "HOLD CLOSER", "HOLD FARTHER", "RECOVERY HOLD"}:
            continue
        result = _mean_hold(sequence_vision, phase["start_wall_time_s"], phase["end_wall_time_s"])
        holds.append({"phase_index": phase["index"], "cue": cue, **result})

    baseline = next((hold for hold in holds if hold["cue"] == "CENTER BASELINE" and hold["stable"]), None)
    left = next((hold for hold in holds if hold["cue"] == "HOLD LEFT"), None)
    right = next((hold for hold in holds if hold["cue"] == "HOLD RIGHT"), None)
    closer = next((hold for hold in holds if hold["cue"] == "HOLD CLOSER"), None)
    farther = next((hold for hold in holds if hold["cue"] == "HOLD FARTHER"), None)
    movement = {
        "left_response_pass": bool(
            baseline and left and left["stable"] and float(left["mean_y_m"]) > float(baseline["mean_y_m"]) + 0.05
        ),
        "right_response_pass": bool(
            baseline and right and right["stable"] and float(right["mean_y_m"]) < float(baseline["mean_y_m"]) - 0.05
        ),
        "closer_response_pass": bool(
            baseline and closer and closer["stable"] and float(closer["mean_x_m"]) < float(baseline["mean_x_m"]) - 0.05
        ),
        "farther_response_pass": bool(
            baseline and farther and farther["stable"] and float(farther["mean_x_m"]) > float(baseline["mean_x_m"]) + 0.05
        ),
    }

    timestamps = [float(row["wall_time_s"]) for row in sequence_vision]
    gaps = [b - a for a, b in zip(timestamps, timestamps[1:]) if b - a > 0.2]
    resets = [event for event in sequence_events if event.get("event") == "RESET"]
    reacquires = [event for event in sequence_events if event.get("event") == "REACQUIRED"]
    summary = {
        "schema_version": 1,
        "run_dir": str(run_dir),
        "recorder_trial_dir": str(recorder_dir),
        "scope": "BROWSER_CUE_WINDOW_ONLY",
        "sequence_start_wall_time_s": start_s,
        "sequence_end_wall_time_s": end_s,
        "sequence_duration_s": end_s - start_s,
        "browser_sequence_completed": browser_completed,
        "vision_sample_count": len(sequence_vision),
        "vision_rate_over_sequence_hz": len(sequence_vision) / (end_s - start_s),
        "vision_gap_count_over_0_2_s": len(gaps),
        "max_vision_gap_s": max(gaps, default=0.0),
        "sequence_event_counts": {
            "resets": len(resets),
            "reacquisitions": len(reacquires),
            "occlusions": sum(1 for event in sequence_events if event.get("event") == "OCCLUSION_START"),
        },
        "intended_dropout": intended,
        "movement_response": movement,
        "stable_hold_measurements": holds,
        "overall_verdict": (
            "PASS_DROPOUT_AND_LATERAL_PARTIAL_DISTANCE"
            if intended["pass"] and movement["left_response_pass"] and movement["right_response_pass"]
            else "INCOMPLETE_OR_FAILED"
        ),
        "claim_limit": (
            "This report isolates the browser cue window. Hand-guided positions support relative response only, "
            "not absolute ground-truth accuracy. The intended dropout is assessed from recorder timestamps."
        ),
    }
    return summary


def write_summary(run_dir: Path) -> dict[str, Any]:
    result = analyze_guided_run(run_dir)
    output = run_dir / "guided_sequence_summary.json"
    temp = output.with_suffix(".json.tmp")
    temp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(write_summary(args.run_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
