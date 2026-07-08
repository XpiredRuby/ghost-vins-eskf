#!/usr/bin/env python3
import math
import sys
from pathlib import Path

import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message


def sample_std(values):
    n = len(values)
    if n < 2:
        return math.nan
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def sample_cov(xs, ys):
    n = len(xs)
    if n < 2:
        return math.nan
    mx = sum(xs) / n
    my = sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: analyze_stationary_R.py BAG_DIR")

    bag = Path(sys.argv[1]).expanduser()
    if not bag.exists():
        raise SystemExit(f"bag does not exist: {bag}")

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(bag), storage_id="mcap"),
        rosbag2_py.ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
    )

    topic_types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    topic = "/ghost/vision/target_pose"
    if topic not in topic_types:
        raise SystemExit(f"{topic} not found in bag")

    msg_type = get_message(topic_types[topic])
    xs = []
    ys = []
    stamps = []

    while reader.has_next():
        name, data, t_ns = reader.read_next()
        if name != topic:
            continue
        msg = deserialize_message(data, msg_type)
        xs.append(float(msg.pose.pose.position.x))
        ys.append(float(msg.pose.pose.position.y))
        stamps.append(t_ns * 1e-9)

    if not xs:
        raise SystemExit("no pose samples found")

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    std_x = sample_std(xs)
    std_y = sample_std(ys)
    var_x = std_x * std_x
    var_y = std_y * std_y
    cov_xy = sample_cov(xs, ys)
    corr_xy = cov_xy / (std_x * std_y) if std_x > 0 and std_y > 0 else math.nan
    duration = max(stamps) - min(stamps) if len(stamps) > 1 else 0.0

    print(f"bag: {bag}")
    print(f"samples: {len(xs)}")
    print(f"duration_s: {duration:.3f}")
    print(f"rate_hz: {len(xs) / duration:.2f}" if duration > 0 else "rate_hz: NA")
    print(f"mean_x_m: {mean_x:.6f}")
    print(f"mean_y_m: {mean_y:.6f}")
    print(f"std_x_m: {std_x:.6f}")
    print(f"std_y_m: {std_y:.6f}")
    print(f"var_x_m2: {var_x:.9f}")
    print(f"var_y_m2: {var_y:.9f}")
    print(f"cov_xy_m2: {cov_xy:.9f}")
    print(f"corr_xy: {corr_xy:.4f}")
    print("recommended_R_xy:")
    print(f"  [[{var_x:.9f}, {cov_xy:.9f}],")
    print(f"   [{cov_xy:.9f}, {var_y:.9f}]]")


if __name__ == "__main__":
    main()
