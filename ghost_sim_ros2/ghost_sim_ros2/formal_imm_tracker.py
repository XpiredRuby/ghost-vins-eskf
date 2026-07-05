"""ROS2 live wrapper for the formal IMM tracker.

This node is additive and side-by-side with the existing heuristic
``mh_tracker`` node. It consumes the same vision pose topic and publishes IMM
odometry plus a futures JSON payload under ``/ghost/tracker_imm/*``.
"""

from __future__ import annotations

import json
import math
from typing import Any

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String

from analysis.imm_live_bridge import (
    FormalImmLiveAdapter,
    FormalImmLiveConfig,
    LIVE_IMM_NOT_HARDWARE_CALIBRATED,
)


class FormalImmTrackerNode(Node):
    """Live ROS2 node for the regression-hardened formal IMM cycle."""

    def __init__(self) -> None:
        super().__init__("ghost_formal_imm_tracker")

        self.declare_parameter("input_topic", "/ghost/vision/target_pose")
        self.declare_parameter("odom_topic", "/ghost/tracker_imm/target_odom")
        self.declare_parameter("futures_topic", "/ghost/tracker_imm/futures_json")
        self.declare_parameter("status_topic", "/ghost/tracker_imm/status")
        self.declare_parameter("frame_id", "camera")
        self.declare_parameter("child_frame_id", "ghost_target_imm")
        self.declare_parameter("tick_hz", 30.0)
        self.declare_parameter("measurement_timeout_s", 0.30)
        self.declare_parameter("measurement_std_m", 0.04)
        self.declare_parameter("smooth_acceleration_std_mps2", 0.015)
        self.declare_parameter("maneuver_acceleration_std_mps2", 0.75)
        self.declare_parameter("future_horizon_s", 1.5)
        self.declare_parameter("future_dt_s", 0.10)
        self.declare_parameter("max_workspace_range_m", 5.0)

        self.input_topic = str(self.get_parameter("input_topic").value)
        self.odom_topic = str(self.get_parameter("odom_topic").value)
        self.futures_topic = str(self.get_parameter("futures_topic").value)
        self.status_topic = str(self.get_parameter("status_topic").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.child_frame_id = str(self.get_parameter("child_frame_id").value)
        self.tick_hz = float(self.get_parameter("tick_hz").value)
        self.measurement_timeout_s = float(self.get_parameter("measurement_timeout_s").value)
        self.max_workspace_range_m = float(self.get_parameter("max_workspace_range_m").value)

        dt_s = 1.0 / max(self.tick_hz, 1.0)
        self.bridge = FormalImmLiveAdapter(
            FormalImmLiveConfig(
                dt_s=dt_s,
                measurement_std_m=float(self.get_parameter("measurement_std_m").value),
                smooth_acceleration_std_mps2=float(self.get_parameter("smooth_acceleration_std_mps2").value),
                maneuver_acceleration_std_mps2=float(self.get_parameter("maneuver_acceleration_std_mps2").value),
                future_horizon_s=float(self.get_parameter("future_horizon_s").value),
                future_dt_s=float(self.get_parameter("future_dt_s").value),
            )
        )

        self.latest_xy: tuple[float, float] | None = None
        self.latest_stamp_s: float | None = None
        self.latest_arrival_s: float | None = None
        self.measurement_count = 0
        self.sequence = 0
        self.last_log_s = 0.0

        live_qos = QoSProfile(depth=1)
        self.sub = self.create_subscription(PoseWithCovarianceStamped, self.input_topic, self.on_measurement, live_qos)
        self.odom_pub = self.create_publisher(Odometry, self.odom_topic, live_qos)
        self.futures_pub = self.create_publisher(String, self.futures_topic, live_qos)
        self.status_pub = self.create_publisher(String, self.status_topic, live_qos)
        self.timer = self.create_timer(dt_s, self.on_timer)

        self.get_logger().info(
            "GHOST formal IMM tracker listening on "
            f"{self.input_topic}; publishing {self.odom_topic}, {self.futures_topic}; "
            f"tick={self.tick_hz:.1f}Hz; timeout={self.measurement_timeout_s:.2f}s; "
            f"status={LIVE_IMM_NOT_HARDWARE_CALIBRATED}"
        )

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def on_measurement(self, msg: PoseWithCovarianceStamped) -> None:
        now = self.now_s()
        x = float(msg.pose.pose.position.x)
        y = float(msg.pose.pose.position.y)
        if not math.isfinite(x) or not math.isfinite(y):
            return
        if x < 0.0 or math.hypot(x, y) > self.max_workspace_range_m:
            return

        msg_stamp_s = float(msg.header.stamp.sec) + 1e-9 * float(msg.header.stamp.nanosec)
        if msg_stamp_s <= 0.0 or abs(now - msg_stamp_s) > 30.0:
            msg_stamp_s = now

        self.latest_xy = (x, y)
        self.latest_stamp_s = msg_stamp_s
        self.latest_arrival_s = now
        self.measurement_count += 1

    def on_timer(self) -> None:
        now = self.now_s()
        measurement = None
        visible = False
        measurement_age_s = math.inf
        if self.latest_xy is not None and self.latest_stamp_s is not None:
            measurement_age_s = now - self.latest_stamp_s
            if measurement_age_s <= self.measurement_timeout_s:
                measurement = list(self.latest_xy)
                visible = True

        output = self.bridge.step(measurement)
        if output.initialized and output.estimate is not None:
            self.publish_odom(output)
        self.publish_futures(now, visible, measurement_age_s, output)
        self.publish_status(now, visible, measurement_age_s, output)

    def publish_odom(self, output: Any) -> None:
        estimate = output.estimate
        if estimate is None:
            return
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.child_frame_id = self.child_frame_id
        msg.pose.pose.position.x = float(estimate["x_m"])
        msg.pose.pose.position.y = float(estimate["y_m"])
        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation.w = 1.0
        msg.twist.twist.linear.x = float(estimate["vx_mps"])
        msg.twist.twist.linear.y = float(estimate["vy_mps"])

        pose_cov = [0.0] * 36
        pose_cov[0] = float(estimate["cov_xx"])
        pose_cov[1] = float(estimate["cov_xy"])
        pose_cov[6] = float(estimate["cov_xy"])
        pose_cov[7] = float(estimate["cov_yy"])
        pose_cov[14] = 1e-4
        pose_cov[21] = 1e-3
        pose_cov[28] = 1e-3
        pose_cov[35] = 1e-3
        msg.pose.covariance = pose_cov

        twist_cov = [0.0] * 36
        twist_cov[0] = float(estimate["cov_vxvx"])
        twist_cov[7] = float(estimate["cov_vyvy"])
        twist_cov[14] = 1e-4
        twist_cov[21] = 1e-3
        twist_cov[28] = 1e-3
        twist_cov[35] = 1e-3
        msg.twist.covariance = twist_cov
        self.odom_pub.publish(msg)

    def publish_futures(self, now: float, visible: bool, measurement_age_s: float, output: Any) -> None:
        self.sequence += 1
        rx_latency_s = math.inf
        if self.latest_stamp_s is not None and self.latest_arrival_s is not None:
            rx_latency_s = self.latest_arrival_s - self.latest_stamp_s
        payload = {
            "sequence": self.sequence,
            "stamp_s": now,
            "visible": visible,
            "measurement_age_s": finite_or_none(measurement_age_s),
            "measurement_rx_latency_s": finite_or_none(rx_latency_s),
            "measurement_count": self.measurement_count,
            "frame_id": self.frame_id,
            "tracker": "formal_imm",
            "integration_status": output.integration_status,
            "parameter_status": output.parameter_status,
            "covariance_validity_status": output.covariance_validity_status,
            "measurement_assumption_label": output.measurement_assumption_label,
            "covariance_caveat": output.covariance_caveat,
            "integration_caveat": output.integration_caveat,
            "initialized": output.initialized,
            "estimate": output.estimate,
            "mode_probabilities": output.mode_probabilities,
            "hypotheses": output.hypotheses,
        }
        self.futures_pub.publish(String(data=json.dumps(payload, separators=(",", ":"))))

    def publish_status(self, now: float, visible: bool, measurement_age_s: float, output: Any) -> None:
        if now - self.last_log_s < 0.25:
            return
        self.last_log_s = now
        if not output.initialized:
            text = f"FORMAL_IMM WAITING_FOR_TARGET status={LIVE_IMM_NOT_HARDWARE_CALIBRATED}"
        else:
            probs = ", ".join(f"{k}:{100.0*v:.1f}%" for k, v in output.mode_probabilities.items())
            text = (
                f"FORMAL_IMM {'VISIBLE' if visible else 'PREDICT'} "
                f"age={finite_or_none(measurement_age_s)} modes=[{probs}] "
                f"covariance={output.covariance_validity_status}"
            )
        self.status_pub.publish(String(data=text))


def finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = FormalImmTrackerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
