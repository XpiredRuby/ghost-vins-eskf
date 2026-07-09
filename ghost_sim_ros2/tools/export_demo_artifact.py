#!/usr/bin/env python3
"""Export a downsampled static demo.json from GHOST trial-recorder logs."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VISION_FILES = ("vision_pose.jsonl",)
IMM_FILES = ("tracker_imm_futures.jsonl", "imm_futures.jsonl")
MH_FILES = ("tracker_mh_futures.jsonl", "mh_futures.jsonl")
STATUS_FILES = ("tracker_status.jsonl", "status.jsonl")


def export_demo_artifact(trial_dir: Path, out_path: Path | None = None, hz: float = 10.0) -> dict[str, Any]:
    if hz <= 0.0 or not math.isfinite(hz):
        raise ValueError("hz must be a positive finite value")
    trial_dir = trial_dir.expanduser()
    out_path = out_path.expanduser() if out_path else trial_dir / "demo.json"

    vision = _read_jsonl(_first_existing(trial_dir, VISION_FILES))
    imm = _read_jsonl(_first_existing(trial_dir, IMM_FILES))
    mh = _read_jsonl(_first_existing(trial_dir, MH_FILES))
    status = _read_jsonl(_first_existing(trial_dir, STATUS_FILES))

    frames = _downsample(_build_frames(vision, imm, mh, status), hz=hz)
    artifact = {
        "metadata": {
            "demo_status": "integration_telemetry_demo",
            "accuracy_validation_status": "pending_ground_truth_grid_validation",
            "source_trial_dir": str(trial_dir),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "downsample_hz": hz,
        },
        "frames": frames,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


def _build_frames(
    vision_rows: list[dict[str, Any]],
    imm_rows: list[dict[str, Any]],
    mh_rows: list[dict[str, Any]],
    status_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[tuple[float, str, dict[str, Any]]] = []
    for row in vision_rows:
        events.append((_time(row), "vision", row))
    for row in imm_rows:
        events.append((_time(row), "imm", row))
    for row in mh_rows:
        events.append((_time(row), "mh", row))
    for row in status_rows:
        events.append((_time(row), "status", row))
    events.sort(key=lambda item: item[0])

    state: dict[str, Any] = {}
    frames = []
    index = 0
    while index < len(events):
        t_s = events[index][0]
        same_time = []
        while index < len(events) and events[index][0] == t_s:
            same_time.append(events[index])
            index += 1
        for _, kind, row in same_time:
            if kind == "vision":
                xy = _xy_from_position(row.get("position"))
                if xy:
                    state["measured_xy_m"] = xy
            elif kind == "imm":
                payload = _payload(row)
                state["imm_xy_m"] = _xy_from_estimate(payload.get("estimate"))
                state["imm_visible"] = bool(payload.get("visible", False))
            elif kind == "mh":
                payload = _payload(row)
                state["mh_visible"] = bool(payload.get("visible", False))
                state["visible"] = bool(payload.get("visible", False))
                state["hidden"] = bool(payload.get("initialized", False)) and not bool(payload.get("visible", False))
                state["mh_hypotheses"] = [_normalize_hypothesis(hyp) for hyp in payload.get("hypotheses", [])]
            elif kind == "status":
                state["status"] = row.get("status")

        frame = {"t_rel_s": t_s, **{key: value for key, value in state.items() if value is not None}}
        frames.append(frame)
    return frames


def _downsample(frames: list[dict[str, Any]], hz: float) -> list[dict[str, Any]]:
    interval = 1.0 / hz
    out = []
    last_t: float | None = None
    for frame in frames:
        t_s = float(frame["t_rel_s"])
        if last_t is None or t_s - last_t >= interval - 1e-12:
            out.append(frame)
            last_t = t_s
    return out


def _normalize_hypothesis(hyp: dict[str, Any]) -> dict[str, Any]:
    out = {
        key: value
        for key, value in hyp.items()
        if key not in {"probability", "relative_hypothesis_weight"}
    }
    out["relative_hypothesis_weight"] = hyp.get("relative_hypothesis_weight", hyp.get("probability"))
    if "path" in hyp and isinstance(hyp["path"], list):
        out["path"] = hyp["path"]
    return out


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload", row)
    return payload if isinstance(payload, dict) else {}


def _xy_from_position(position: Any) -> dict[str, float] | None:
    if not isinstance(position, dict):
        return None
    x = _maybe_float(position.get("x_m", position.get("x")))
    y = _maybe_float(position.get("y_m", position.get("y")))
    if x is None or y is None:
        return None
    return {"x_m": x, "y_m": y}


def _xy_from_estimate(estimate: Any) -> dict[str, float] | None:
    if not isinstance(estimate, dict):
        return None
    x = _maybe_float(estimate.get("x_m", estimate.get("x")))
    y = _maybe_float(estimate.get("y_m", estimate.get("y")))
    if x is None or y is None:
        return None
    return {"x_m": x, "y_m": y}


def _time(row: dict[str, Any]) -> float:
    value = row.get("t_rel_s", row.get("t", row.get("time_s", 0.0)))
    parsed = _maybe_float(value)
    return parsed if parsed is not None else 0.0


def _maybe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _first_existing(directory: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        path = directory / name
        if path.exists():
            return path
    return None


def _read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{lineno}: {exc}") from exc
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export static demo.json from GHOST trial logs.")
    parser.add_argument("trial_dir", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--hz", type=float, default=10.0)
    args = parser.parse_args(argv)

    artifact = export_demo_artifact(args.trial_dir, args.out, hz=args.hz)
    out_path = args.out.expanduser() if args.out else args.trial_dir.expanduser() / "demo.json"
    print(f"frames: {len(artifact['frames'])}")
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
