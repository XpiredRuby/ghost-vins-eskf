#!/usr/bin/env python3
import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


STATUS_RE = re.compile(r"FORMAL_IMM\s+(\S+)")
MH_STATUS_RE = re.compile(r"^([A-Z_ -]+)")


def open_reader(bag_path):
    reader = rosbag2_py.SequentialReader()
    storage_options = rosbag2_py.StorageOptions(uri=str(bag_path), storage_id="mcap")
    converter_options = rosbag2_py.ConverterOptions("", "")
    reader.open(storage_options, converter_options)
    type_map = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
    return reader, type_map


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bag")
    args = ap.parse_args()

    bag = Path(args.bag).expanduser()
    reader, type_map = open_reader(bag)

    counts = Counter()
    first_t = {}
    last_t = {}
    imm_status = Counter()
    mh_status = Counter()
    imm_prediction_only_steps_max = 0
    imm_age_max = 0.0
    vision_x = []
    vision_y = []

    while reader.has_next():
        topic, data, t_ns = reader.read_next()
        counts[topic] += 1
        first_t.setdefault(topic, t_ns)
        last_t[topic] = t_ns

        msg_type = get_message(type_map[topic])
        msg = deserialize_message(data, msg_type)

        if topic == "/ghost/tracker_imm/status":
            text = msg.data
            m = STATUS_RE.search(text)
            if m:
                imm_status[m.group(1)] += 1
            m_steps = re.search(r"prediction_only_steps=(\d+)", text)
            if m_steps:
                imm_prediction_only_steps_max = max(imm_prediction_only_steps_max, int(m_steps.group(1)))
            m_age = re.search(r"age=([0-9.]+)", text)
            if m_age:
                imm_age_max = max(imm_age_max, float(m_age.group(1)))

        elif topic == "/ghost/tracker_mh/status":
            text = msg.data
            m = MH_STATUS_RE.search(text)
            if m:
                mh_status[m.group(1).strip()] += 1

        elif topic == "/ghost/vision/target_pose":
            vision_x.append(float(msg.pose.pose.position.x))
            vision_y.append(float(msg.pose.pose.position.y))

    bag_first = min(first_t.values()) if first_t else 0
    bag_last = max(last_t.values()) if last_t else 0
    duration_s = (bag_last - bag_first) * 1e-9 if bag_last >= bag_first else math.nan

    print(f"bag: {bag}")
    print(f"duration_s: {duration_s:.3f}")
    print("topic_counts:")
    for topic, count in sorted(counts.items()):
        hz = count / duration_s if duration_s > 0 else math.nan
        print(f"  {topic}: {count} ({hz:.2f} Hz)")

    print("imm_status_counts:")
    for k, v in imm_status.items():
        print(f"  {k}: {v}")

    print("mh_status_counts:")
    for k, v in mh_status.items():
        print(f"  {k}: {v}")

    print(f"imm_prediction_only_steps_max: {imm_prediction_only_steps_max}")
    print(f"imm_age_max_s: {imm_age_max:.3f}")

    if vision_x:
        mean_x = sum(vision_x) / len(vision_x)
        mean_y = sum(vision_y) / len(vision_y)
        std_x = math.sqrt(sum((x - mean_x) ** 2 for x in vision_x) / len(vision_x))
        std_y = math.sqrt(sum((y - mean_y) ** 2 for y in vision_y) / len(vision_y))
        print(f"vision_pose_count: {len(vision_x)}")
        print(f"vision_x_range_m: {min(vision_x):.4f} to {max(vision_x):.4f}")
        print(f"vision_y_range_m: {min(vision_y):.4f} to {max(vision_y):.4f}")
        print(f"vision_raw_std_all_x_m: {std_x:.4f}")
        print(f"vision_raw_std_all_y_m: {std_y:.4f}")


if __name__ == "__main__":
    main()
