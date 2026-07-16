from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from pathlib import Path
from typing import Any

TRIAL_ID = "guided_relative_motion_dropout_01"


def iso_ts(value: str) -> float:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def analyze_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    trial_dir = run_dir / "trial_directories" / TRIAL_ID
    recorder_dir = max(
        (path for path in (run_dir / "recorder_trials").iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
    )

    conductor_events = load_jsonl(trial_dir / "conductor_events.jsonl")
    vision = load_jsonl(recorder_dir / "vision_pose.jsonl")
    events = load_jsonl(recorder_dir / "events.jsonl")

    phases: dict[str, dict[str, float]] = {}
    for event in conductor_events:
        cue = event.get("cue")
        if not isinstance(cue, str):
            continue
        if event.get("type") == "phase_started":
            phases.setdefault(cue, {})["start"] = iso_ts(str(event["client_iso"]))
        elif event.get("type") == "phase_completed":
            phases.setdefault(cue, {})["end"] = iso_ts(str(event["client_iso"]))

    sequence_start = phases["ALIGN CENTER"]["start"]
    sequence_end = iso_ts(
        str(next(event["client_iso"] for event in conductor_events if event.get("type") == "cue_sequence_completed"))
    )

    def hold(cue: str) -> dict[str, Any]:
        start = phases[cue]["start"]
        end = phases[cue]["end"]
        samples = [sample for sample in vision if start <= float(sample["wall_time_s"]) <= end]
        xs = [float(sample["position"]["x_m"]) for sample in samples]
        ys = [float(sample["position"]["y_m"]) for sample in samples]
        times = [float(sample["wall_time_s"]) for sample in samples]
        gaps = [b - a for a, b in zip(times, times[1:])]
        return {
            "sample_count": len(samples),
            "mean_x_m": statistics.fmean(xs) if xs else None,
            "mean_y_m": statistics.fmean(ys) if ys else None,
            "std_x_m": statistics.pstdev(xs) if len(xs) > 1 else None,
            "std_y_m": statistics.pstdev(ys) if len(ys) > 1 else None,
            "max_internal_gap_s": max(gaps) if gaps else None,
        }

    baseline = hold("CENTER BASELINE")
    closer = hold("HOLD CLOSER")
    final_center = hold("FINAL CENTER HOLD")
    if baseline["mean_x_m"] is None or closer["mean_x_m"] is None or final_center["mean_x_m"] is None:
        raise RuntimeError("missing valid pose samples in one or more required holds")
    closer_delta = float(closer["mean_x_m"]) - float(baseline["mean_x_m"])
    final_delta = float(final_center["mean_x_m"]) - float(baseline["mean_x_m"])
    reset_count = sum(
        1
        for event in events
        if event.get("event") == "RESET" and sequence_start <= float(event["wall_time_s"]) <= sequence_end
    )
    occlusion_count = sum(
        1
        for event in events
        if event.get("event") == "OCCLUSION_START" and sequence_start <= float(event["wall_time_s"]) <= sequence_end
    )
    reacquire_count = sum(
        1
        for event in events
        if event.get("event") == "REACQUIRED" and sequence_start <= float(event["wall_time_s"]) <= sequence_end
    )

    passed = bool(
        int(closer["sample_count"]) >= 20
        and closer["max_internal_gap_s"] is not None
        and float(closer["max_internal_gap_s"]) < 0.5
        and closer_delta < -0.05
        and reset_count == 0
        and int(final_center["sample_count"]) >= 20
        and abs(final_delta) < 0.05
    )

    return {
        "run_dir": str(run_dir),
        "pass": passed,
        "baseline": baseline,
        "closer": closer,
        "final_center": final_center,
        "closer_delta_x_m": closer_delta,
        "final_center_delta_x_m": final_delta,
        "reset_count_during_sequence": reset_count,
        "occlusion_count_during_sequence": occlusion_count,
        "reacquire_count_during_sequence": reacquire_count,
        "claim_limit": "Relative closer-response coverage only; no absolute ground-truth accuracy claim.",
    }


def write_summary(run_dir: Path) -> dict[str, Any]:
    result = analyze_run(run_dir)
    (run_dir / "closer_only_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: analyze_closer_only_run.py <run-dir>")
    result = write_summary(Path(args[0]))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
