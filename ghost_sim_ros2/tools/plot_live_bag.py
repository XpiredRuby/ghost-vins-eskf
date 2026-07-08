#!/usr/bin/env python3
import argparse
import math
import re
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
}


def open_reader(bag_path):
    reader = rosbag2_py.SequentialReader()
    storage_options = rosbag2_py.StorageOptions(uri=str(bag_path), storage_id="mcap")
    converter_options = rosbag2_py.ConverterOptions("", "")
    reader.open(storage_options, converter_options)
    type_map = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
    return reader, type_map


def append_pose(series, t, msg, stamped_pose=False):
    if stamped_pose:
        p = msg.pose.pose.position
    else:
        p = msg.pose.pose.position
    series["t"].append(t)
    series["x"].append(float(p.x))
    series["y"].append(float(p.y))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bag")
    ap.add_argument("--out", default="docs/assets/ghost_live_plots")
    args = ap.parse_args()

    bag = Path(args.bag).expanduser()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    reader, type_map = open_reader(bag)

    raw = []
    while reader.has_next():
        topic, data, t_ns = reader.read_next()
        raw.append((topic, data, t_ns))

    if not raw:
        raise RuntimeError(f"No messages found in bag: {bag}")

    t0 = min(t for _, _, t in raw)

    vision = {"t": [], "x": [], "y": []}
    imm = {"t": [], "x": [], "y": []}
    mh = {"t": [], "x": [], "y": []}
    imm_status_t = []
    imm_status_name = []
    mh_status_t = []
    mh_status_name = []

    counts = Counter()

    for topic, data, t_ns in raw:
        counts[topic] += 1
        t = (t_ns - t0) * 1e-9
        msg_type = get_message(type_map[topic])
        msg = deserialize_message(data, msg_type)

        if topic == TOPICS["vision"]:
            append_pose(vision, t, msg, stamped_pose=True)

        elif topic == TOPICS["imm_odom"]:
            append_pose(imm, t, msg)

        elif topic == TOPICS["mh_odom"]:
            append_pose(mh, t, msg)

        elif topic == TOPICS["imm_status"]:
            text = msg.data
            m = STATUS_RE.search(text)
            name = m.group(1) if m else text[:40]
            imm_status_t.append(t)
            imm_status_name.append(name)

        elif topic == TOPICS["mh_status"]:
            text = msg.data
            m = MH_STATUS_RE.search(text)
            name = m.group(1).strip() if m else text[:40]
            mh_status_t.append(t)
            mh_status_name.append(name)

    duration_s = (max(t for _, _, t in raw) - t0) * 1e-9

    # 1) XY path plot
    plt.figure(figsize=(9, 6))
    if vision["x"]:
        plt.plot(vision["x"], vision["y"], ".", markersize=3, label="Vision AprilTag measurements")
    if imm["x"]:
        plt.plot(imm["x"], imm["y"], "-", linewidth=1.5, label="Formal IMM estimate")
    if mh["x"]:
        plt.plot(mh["x"], mh["y"], "-", linewidth=1.2, label="Heuristic MH estimate")
    plt.xlabel("x position (m)")
    plt.ylabel("y position (m)")
    plt.title("GHOST final hardware run: measured and estimated target path")
    plt.grid(True, alpha=0.3)
    plt.axis("equal")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out / "ghost_live_xy_path.png", dpi=180)
    plt.close()

    # 2) x/y over time
    plt.figure(figsize=(11, 6))
    if vision["t"]:
        plt.plot(vision["t"], vision["x"], ".", markersize=3, label="Vision x")
        plt.plot(vision["t"], vision["y"], ".", markersize=3, label="Vision y")
    if imm["t"]:
        plt.plot(imm["t"], imm["x"], "-", linewidth=1.4, label="IMM x")
        plt.plot(imm["t"], imm["y"], "-", linewidth=1.4, label="IMM y")
    if mh["t"]:
        plt.plot(mh["t"], mh["x"], "--", linewidth=1.1, label="MH x")
        plt.plot(mh["t"], mh["y"], "--", linewidth=1.1, label="MH y")
    plt.xlabel("time since bag start (s)")
    plt.ylabel("position (m)")
    plt.title("GHOST final hardware run: position tracks over time")
    plt.grid(True, alpha=0.3)
    plt.legend(ncol=3, fontsize=8)
    plt.tight_layout()
    plt.savefig(out / "ghost_live_position_vs_time.png", dpi=180)
    plt.close()

    # 3) IMM status timeline
    if imm_status_t:
        labels = list(dict.fromkeys(imm_status_name))
        label_to_y = {label: i for i, label in enumerate(labels)}
        y = [label_to_y[s] for s in imm_status_name]

        plt.figure(figsize=(11, 4.5))
        plt.step(imm_status_t, y, where="post", linewidth=2)
        plt.yticks(range(len(labels)), labels)
        plt.xlabel("time since bag start (s)")
        plt.ylabel("IMM status")
        plt.title("Formal IMM status timeline during final hardware run")
        plt.grid(True, axis="x", alpha=0.3)
        plt.tight_layout()
        plt.savefig(out / "ghost_live_imm_status_timeline.png", dpi=180)
        plt.close()

    # 4) MH status timeline
    if mh_status_t:
        labels = list(dict.fromkeys(mh_status_name))
        label_to_y = {label: i for i, label in enumerate(labels)}
        y = [label_to_y[s] for s in mh_status_name]

        plt.figure(figsize=(11, 4.5))
        plt.step(mh_status_t, y, where="post", linewidth=2)
        plt.yticks(range(len(labels)), labels)
        plt.xlabel("time since bag start (s)")
        plt.ylabel("MH status")
        plt.title("Heuristic MH status timeline during final hardware run")
        plt.grid(True, axis="x", alpha=0.3)
        plt.tight_layout()
        plt.savefig(out / "ghost_live_mh_status_timeline.png", dpi=180)
        plt.close()

    # 5) Topic-rate summary
    rate_topics = [
        TOPICS["vision"],
        TOPICS["imm_odom"],
        TOPICS["mh_odom"],
        TOPICS["imm_status"],
        TOPICS["mh_status"],
    ]
    names = [
        "Vision pose",
        "IMM odom",
        "MH odom",
        "IMM status",
        "MH status",
    ]
    rates = [counts[t] / duration_s if duration_s > 0 else math.nan for t in rate_topics]

    plt.figure(figsize=(9, 5))
    plt.bar(names, rates)
    plt.ylabel("rate (Hz)")
    plt.title("GHOST final hardware run: ROS topic publish rates")
    plt.xticks(rotation=20, ha="right")
    plt.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out / "ghost_live_topic_rates.png", dpi=180)
    plt.close()

    print(f"bag: {bag}")
    print(f"duration_s: {duration_s:.3f}")
    print(f"output_dir: {out}")
    for p in sorted(out.glob('*.png')):
        print(f"created: {p}")


if __name__ == "__main__":
    main()
