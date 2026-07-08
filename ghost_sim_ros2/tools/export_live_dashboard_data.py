#!/usr/bin/env python3
import argparse
import json
import math
import re
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


STATUS_RE = re.compile(r"FORMAL_IMM\s+(\S+)")
MH_STATUS_RE = re.compile(r"^([A-Z_ -]+)")

TOPICS = {
    "vision": "/ghost/vision/target_pose",
    "imm_odom": "/ghost/tracker_imm/target_odom",
    "mh_odom": "/ghost/tracker_mh/target_odom",
    "imm_status": "/ghost/tracker_imm/status",
    "mh_status": "/ghost/tracker_mh/status",
    "imm_futures": "/ghost/tracker_imm/futures_json",
    "mh_futures": "/ghost/tracker_mh/futures_json",
}


def open_reader(bag_path):
    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(bag_path), storage_id="mcap"),
        rosbag2_py.ConverterOptions("", ""),
    )
    type_map = {t.name: t.type for t in reader.get_all_topics_and_types()}
    return reader, type_map


def pose_point(t, msg):
    p = msg.pose.pose.position
    return {"t": round(t, 4), "x": float(p.x), "y": float(p.y)}


def odom_point(t, msg):
    p = msg.pose.pose.position
    return {"t": round(t, 4), "x": float(p.x), "y": float(p.y)}


def trim_path(path, max_points=18):
    out = []
    for p in path[:max_points]:
        out.append({
            "dt": float(p.get("t_s", 0.0)),
            "x": float(p.get("x_m", 0.0)),
            "y": float(p.get("y_m", 0.0)),
        })
    return out


def nonnegative_float(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, number)


def nonnegative_int(value):
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, number)


def parse_futures(t, msg, tracker):
    try:
        obj = json.loads(msg.data)
    except Exception:
        return None

    item = {
        "t": round(t, 4),
        "visible": bool(obj.get("visible", False)),
        "measurement_age_s": nonnegative_float(obj.get("measurement_age_s")),
        "prediction_only_steps": nonnegative_int(obj.get("prediction_only_steps")),
        "live_status": obj.get("live_status"),
        "mode_probabilities": obj.get("mode_probabilities", {}),
        "hypotheses": [],
    }

    for h in obj.get("hypotheses", [])[:4]:
        item["hypotheses"].append({
            "model": h.get("model", "unknown"),
            "probability": h.get("probability"),
            "x": h.get("x_m"),
            "y": h.get("y_m"),
            "vx": h.get("vx_mps"),
            "vy": h.get("vy_mps"),
            "path": trim_path(h.get("path", [])),
        })

    return item


def downsample(items, max_n):
    if len(items) <= max_n:
        return items
    step = max(1, len(items) // max_n)
    return items[::step][:max_n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bag")
    ap.add_argument("--out", default="docs/assets/ghost_live_dashboard/live_camera_calibrated_R_01_dashboard.json")
    args = ap.parse_args()

    bag = Path(args.bag).expanduser()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    reader, type_map = open_reader(bag)

    raw = []
    while reader.has_next():
        topic, data, t_ns = reader.read_next()
        raw.append((topic, data, t_ns))

    if not raw:
        raise RuntimeError(f"No messages in bag: {bag}")

    t0 = min(t for _, _, t in raw)
    t1 = max(t for _, _, t in raw)
    duration_s = (t1 - t0) * 1e-9

    data = {
        "meta": {
            "bag": str(bag),
            "duration_s": duration_s,
            "title": "GHOST final calibrated hardware replay",
        },
        "vision": [],
        "imm": [],
        "mh": [],
        "imm_status": [],
        "mh_status": [],
        "imm_futures": [],
        "mh_futures": [],
    }

    last_imm_future_t = -999.0
    last_mh_future_t = -999.0
    future_sample_dt = 0.25

    for topic, blob, t_ns in raw:
        if topic not in TOPICS.values():
            continue

        t = (t_ns - t0) * 1e-9
        msg = deserialize_message(blob, get_message(type_map[topic]))

        if topic == TOPICS["vision"]:
            data["vision"].append(pose_point(t, msg))

        elif topic == TOPICS["imm_odom"]:
            data["imm"].append(odom_point(t, msg))

        elif topic == TOPICS["mh_odom"]:
            data["mh"].append(odom_point(t, msg))

        elif topic == TOPICS["imm_status"]:
            text = msg.data
            m = STATUS_RE.search(text)
            data["imm_status"].append({
                "t": round(t, 4),
                "status": m.group(1) if m else text[:80],
                "raw": text,
            })

        elif topic == TOPICS["mh_status"]:
            text = msg.data
            m = MH_STATUS_RE.search(text)
            data["mh_status"].append({
                "t": round(t, 4),
                "status": m.group(1).strip() if m else text[:80],
                "raw": text,
            })

        elif topic == TOPICS["imm_futures"] and (t - last_imm_future_t) >= future_sample_dt:
            item = parse_futures(t, msg, "imm")
            if item:
                data["imm_futures"].append(item)
                last_imm_future_t = t

        elif topic == TOPICS["mh_futures"] and (t - last_mh_future_t) >= future_sample_dt:
            item = parse_futures(t, msg, "mh")
            if item:
                data["mh_futures"].append(item)
                last_mh_future_t = t

    data["imm"] = downsample(data["imm"], 1200)
    data["mh"] = downsample(data["mh"], 1200)

    out.write_text(json.dumps(data, indent=2))
    print(f"wrote: {out}")
    print(f"duration_s: {duration_s:.3f}")
    print(f"vision_points: {len(data['vision'])}")
    print(f"imm_points: {len(data['imm'])}")
    print(f"mh_points: {len(data['mh'])}")
    print(f"imm_status: {len(data['imm_status'])}")
    print(f"mh_status: {len(data['mh_status'])}")
    print(f"imm_futures_samples: {len(data['imm_futures'])}")
    print(f"mh_futures_samples: {len(data['mh_futures'])}")


if __name__ == "__main__":
    main()
