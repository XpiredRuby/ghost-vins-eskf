#!/usr/bin/env python3
"""Export GHOST vision pose samples to stationary-noise CSV schema.

Inputs:
- trial-recorder ``vision_pose.jsonl`` rows containing ``t_rel_s`` and
  ``position.x_m/y_m/z_m``
- ROS 2 bag directory containing ``/ghost/vision/target_pose``

Output CSV schema is exactly: ``t,x,y,z``. This tool preserves raw samples; it
intentionally does not detrend, filter, resample, or normalize positions.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable

CSV_HEADER = ("t", "x", "y", "z")
DEFAULT_TOPIC = "/ghost/vision/target_pose"


def _finite_float(value: object, field: str) -> float:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric; got {value!r}") from exc
    if out != out or out in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite; got {value!r}")
    return out


def rows_from_jsonl(path: Path) -> list[tuple[float, float, float, float]]:
    rows: list[tuple[float, float, float, float]] = []
    with path.expanduser().open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{lineno}: {exc}") from exc
            pos = obj.get("position")
            if not isinstance(pos, dict):
                raise ValueError(f"Missing position object on {path}:{lineno}")
            rows.append(
                (
                    _finite_float(obj.get("t_rel_s"), f"{path}:{lineno} t_rel_s"),
                    _finite_float(pos.get("x_m"), f"{path}:{lineno} position.x_m"),
                    _finite_float(pos.get("y_m"), f"{path}:{lineno} position.y_m"),
                    _finite_float(pos.get("z_m"), f"{path}:{lineno} position.z_m"),
                )
            )
    return rows


def _pose_position(msg: object) -> object:
    # PoseWithCovarianceStamped: msg.pose.pose.position
    pose = getattr(msg, "pose", None)
    if pose is not None and hasattr(pose, "pose") and hasattr(pose.pose, "position"):
        return pose.pose.position
    # PoseStamped/Pose: msg.pose.position
    if pose is not None and hasattr(pose, "position"):
        return pose.position
    # Odometry-like fallback: msg.pose.pose.position
    raise ValueError(f"Unsupported pose message layout: {type(msg)!r}")


def rows_from_bag(bag_dir: Path, topic: str = DEFAULT_TOPIC, storage_id: str = "mcap") -> list[tuple[float, float, float, float]]:
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise RuntimeError("ROS bag export requires rosbag2_py, rclpy, and rosidl_runtime_py") from exc

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(bag_dir.expanduser()), storage_id=storage_id),
        rosbag2_py.ConverterOptions("", ""),
    )
    type_map = {t.name: t.type for t in reader.get_all_topics_and_types()}
    if topic not in type_map:
        available = ", ".join(sorted(type_map))
        raise ValueError(f"Topic {topic!r} not found in bag. Available topics: {available}")

    msg_type = get_message(type_map[topic])
    raw_rows: list[tuple[int, float, float, float]] = []
    while reader.has_next():
        bag_topic, data, t_ns = reader.read_next()
        if bag_topic != topic:
            continue
        msg = deserialize_message(data, msg_type)
        p = _pose_position(msg)
        raw_rows.append((int(t_ns), float(p.x), float(p.y), float(p.z)))

    if not raw_rows:
        return []
    t0 = min(t for t, *_ in raw_rows)
    return [((t_ns - t0) * 1e-9, x, y, z) for t_ns, x, y, z in raw_rows]


def write_csv(rows: Iterable[tuple[float, float, float, float]], out_path: Path) -> int:
    out_path = out_path.expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for row in rows:
            writer.writerow([f"{row[0]:.9f}", f"{row[1]:.9f}", f"{row[2]:.9f}", f"{row[3]:.9f}"])
            count += 1
    return count


def export_input(input_path: Path, out_path: Path, topic: str = DEFAULT_TOPIC, storage_id: str = "mcap") -> int:
    input_path = input_path.expanduser()
    if input_path.is_file():
        rows = rows_from_jsonl(input_path)
    elif input_path.is_dir():
        rows = rows_from_bag(input_path, topic=topic, storage_id=storage_id)
    else:
        raise FileNotFoundError(f"Input path does not exist: {input_path}")
    return write_csv(rows, out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export GHOST vision pose logs to t,x,y,z CSV.")
    parser.add_argument("input", type=Path, help="vision_pose.jsonl file or ROS 2 bag directory")
    parser.add_argument("--out", required=True, type=Path, help="Output CSV path with schema t,x,y,z")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="Bag topic to export when input is a bag directory")
    parser.add_argument("--storage-id", default="mcap", help="rosbag2 storage id for bag input, default: mcap")
    args = parser.parse_args(argv)

    count = export_input(args.input, args.out, topic=args.topic, storage_id=args.storage_id)
    print(f"samples: {count}")
    print(f"wrote: {args.out.expanduser()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
