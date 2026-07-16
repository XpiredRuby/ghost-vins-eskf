from __future__ import annotations

import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

TRIAL_ID = "guided_relative_motion_dropout_01"


def ts(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def summarize_hold(name: str, start: float, end: float, vision: list[dict[str, Any]]) -> dict[str, Any]:
    window_start = min(end, start + 1.0)
    rows = [r for r in vision if window_start <= float(r.get("wall_time_s", -math.inf)) <= end]
    xs = [float(r["position"]["x_m"]) for r in rows]
    ys = [float(r["position"]["y_m"]) for r in rows]
    times = [float(r["wall_time_s"]) for r in rows]
    gaps = [b - a for a, b in zip(times, times[1:])]
    return {
        "cue": name,
        "sample_count": len(rows),
        "mean_x_m": statistics.fmean(xs) if xs else None,
        "mean_y_m": statistics.fmean(ys) if ys else None,
        "std_x_m": statistics.pstdev(xs) if len(xs) >= 2 else None,
        "std_y_m": statistics.pstdev(ys) if len(ys) >= 2 else None,
        "max_internal_gap_s": max(gaps, default=None),
    }


def analyze_run(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.expanduser().resolve()
    trial_dir = run_dir / "trial_directories" / TRIAL_ID
    conductor = read_jsonl(trial_dir / "conductor_events.jsonl")
    recorder_root = run_dir / "recorder_trials"
    recorder_trial = max((p for p in recorder_root.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    vision = read_jsonl(recorder_trial / "vision_pose.jsonl")
    events = read_jsonl(recorder_trial / "events.jsonl")

    phase_starts: list[tuple[str, float]] = []
    sequence_end = None
    for event in conductor:
        kind = event.get("type")
        if kind == "phase_started":
            phase_starts.append((str(event.get("cue")), ts(str(event["server_received_at_utc"]))))
        elif kind == "cue_sequence_completed":
            sequence_end = ts(str(event["server_received_at_utc"]))
    if not phase_starts or sequence_end is None:
        raise RuntimeError("incomplete conductor event log")

    phases: list[tuple[str, float, float]] = []
    for index, (name, start) in enumerate(phase_starts):
        end = phase_starts[index + 1][1] if index + 1 < len(phase_starts) else sequence_end
        phases.append((name, start, end))

    hold_names = {"CENTER BASELINE", "HOLD CLOSER", "HOLD CENTER", "HOLD FARTHER", "FINAL CENTER HOLD"}
    holds = [summarize_hold(name, start, end, vision) for name, start, end in phases if name in hold_names]
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in holds:
        by_name.setdefault(str(item["cue"]), []).append(item)

    baseline = by_name["CENTER BASELINE"][0]
    closer = by_name["HOLD CLOSER"][0]
    farther = by_name["HOLD FARTHER"][0]
    final_center = by_name["FINAL CENTER HOLD"][0]

    sequence_start = phase_starts[0][1]
    sequence_events = [e for e in events if sequence_start <= float(e.get("wall_time_s", -math.inf)) <= sequence_end]
    resets = [e for e in sequence_events if e.get("event") == "RESET"]

    def stable(item: dict[str, Any]) -> bool:
        return (
            int(item["sample_count"]) >= 20
            and item["std_x_m"] is not None
            and float(item["std_x_m"]) <= 0.02
            and item["max_internal_gap_s"] is not None
            and float(item["max_internal_gap_s"]) <= 0.5
        )

    baseline_x = float(baseline["mean_x_m"])
    closer_x = float(closer["mean_x_m"]) if closer["mean_x_m"] is not None else math.nan
    farther_x = float(farther["mean_x_m"]) if farther["mean_x_m"] is not None else math.nan
    final_x = float(final_center["mean_x_m"]) if final_center["mean_x_m"] is not None else math.nan

    closer_direction = math.isfinite(closer_x) and closer_x <= baseline_x - 0.08
    farther_direction = math.isfinite(farther_x) and farther_x >= baseline_x + 0.08
    return_center = math.isfinite(final_x) and abs(final_x - baseline_x) <= 0.08

    return {
        "run_dir": str(run_dir),
        "sequence_duration_s": sequence_end - sequence_start,
        "reset_count_during_sequence": len(resets),
        "holds": holds,
        "baseline_x_m": baseline_x,
        "closer_delta_x_m": closer_x - baseline_x if math.isfinite(closer_x) else None,
        "farther_delta_x_m": farther_x - baseline_x if math.isfinite(farther_x) else None,
        "final_center_delta_x_m": final_x - baseline_x if math.isfinite(final_x) else None,
        "closer_stable": stable(closer),
        "farther_stable": stable(farther),
        "closer_direction_correct": closer_direction,
        "farther_direction_correct": farther_direction,
        "return_center_pass": return_center,
        "pass": stable(closer) and stable(farther) and closer_direction and farther_direction and return_center and not resets,
        "claim_limit": "Relative distance-response coverage only; no absolute ground-truth accuracy claim.",
    }


def write_summary(run_dir: Path) -> dict[str, Any]:
    result = analyze_run(run_dir)
    (run_dir / "distance_only_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: analyze_distance_only_run.py <run-dir>")
    result = write_summary(Path(args[0]))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
