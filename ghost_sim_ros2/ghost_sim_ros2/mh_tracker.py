import json
import math
from typing import Any

import numpy as np
import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import String

from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.ghost_mh_mode_bank import mode_bank


class GhostMHTrackerNode(Node):
    """Live ROS2 wrapper for the calibrated GHOST-MH probability tracker.

    Input:
        /ghost/vision/target_pose       geometry_msgs/PoseWithCovarianceStamped

    Outputs:
        /ghost/tracker_mh/target_odom   nav_msgs/Odometry
        /ghost/tracker_mh/futures_json  std_msgs/String JSON payload
        /ghost/tracker_mh/status        std_msgs/String human-readable status
    """

    def __init__(self) -> None:
        super().__init__("ghost_mh_tracker")

        self.declare_parameter("input_topic", "/ghost/vision/target_pose")
        self.declare_parameter("odom_topic", "/ghost/tracker_mh/target_odom")
        self.declare_parameter("futures_topic", "/ghost/tracker_mh/futures_json")
        self.declare_parameter("status_topic", "/ghost/tracker_mh/status")
        self.declare_parameter("frame_id", "camera")
        self.declare_parameter("child_frame_id", "ghost_target_mh")
        self.declare_parameter("tick_hz", 20.0)
        self.declare_parameter("measurement_timeout_s", 0.25)
        self.declare_parameter("measurement_std_m", 0.04)
        self.declare_parameter("max_occlusion_s", 3.0)
        self.declare_parameter("max_workspace_range_m", 5.0)
        self.declare_parameter("top_n", 5)
        self.declare_parameter("future_horizon_s", 1.5)
        self.declare_parameter("future_dt_s", 0.25)
        self.declare_parameter("accel_temperature", 0.30)

        self.input_topic = str(self.get_parameter("input_topic").value)
        self.odom_topic = str(self.get_parameter("odom_topic").value)
        self.futures_topic = str(self.get_parameter("futures_topic").value)
        self.status_topic = str(self.get_parameter("status_topic").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.child_frame_id = str(self.get_parameter("child_frame_id").value)
        self.tick_hz = float(self.get_parameter("tick_hz").value)
        self.measurement_timeout_s = float(self.get_parameter("measurement_timeout_s").value)
        self.top_n = int(self.get_parameter("top_n").value)
        self.future_horizon_s = float(self.get_parameter("future_horizon_s").value)
        self.future_dt_s = float(self.get_parameter("future_dt_s").value)

        self.tracker = CalibratedModeBankTracker(
            measurement_std_m=float(self.get_parameter("measurement_std_m").value),
            max_occlusion_s=float(self.get_parameter("max_occlusion_s").value),
            max_workspace_range_m=float(self.get_parameter("max_workspace_range_m").value),
            accel_temperature=float(self.get_parameter("accel_temperature").value),
        )
        self.model_lookup = {model.name: model for model in mode_bank()}

        self.latest_xy: tuple[float, float] | None = None
        self.latest_stamp_s: float | None = None
        self.last_tick_s: float | None = None
        self.last_log_s: float = 0.0

        self.sub = self.create_subscription(
            PoseWithCovarianceStamped,
            self.input_topic,
            self.on_measurement,
            10,
        )
        self.odom_pub = self.create_publisher(Odometry, self.odom_topic, 10)
        self.futures_pub = self.create_publisher(String, self.futures_topic, 10)
        self.status_pub = self.create_publisher(String, self.status_topic, 10)

        period = 1.0 / max(self.tick_hz, 1.0)
        self.timer = self.create_timer(period, self.on_timer)

        self.get_logger().info(
            "GHOST-MH tracker listening on "
            f"{self.input_topic}; publishing {self.odom_topic}, "
            f"{self.futures_topic}; timeout={self.measurement_timeout_s:.2f}s"
        )

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def on_measurement(self, msg: PoseWithCovarianceStamped) -> None:
        x = float(msg.pose.pose.position.x)
        y = float(msg.pose.pose.position.y)
        if not math.isfinite(x) or not math.isfinite(y):
            return
        if x < 0.0 or math.hypot(x, y) > float(self.get_parameter("max_workspace_range_m").value):
            return
        self.latest_xy = (x, y)
        self.latest_stamp_s = self.now_s()

    def on_timer(self) -> None:
        now = self.now_s()
        if self.last_tick_s is None:
            self.last_tick_s = now
            return

        dt = max(1e-3, min(0.2, now - self.last_tick_s))
        self.last_tick_s = now

        measurement = None
        visible = False
        measurement_age_s = math.inf
        if self.latest_xy is not None and self.latest_stamp_s is not None:
            measurement_age_s = now - self.latest_stamp_s
            if measurement_age_s <= self.measurement_timeout_s:
                measurement = list(self.latest_xy)
                visible = True

        self.tracker.step(dt, measurement)
        estimate = self.tracker.estimate()

        if estimate.initialized:
            self.publish_odom(now, estimate)
        self.publish_futures(now, visible, measurement_age_s, estimate)
        self.publish_status(now, visible, measurement_age_s, estimate)

    def publish_odom(self, now: float, estimate: Any) -> None:
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.child_frame_id = self.child_frame_id
        msg.pose.pose.position.x = float(estimate.x[0, 0])
        msg.pose.pose.position.y = float(estimate.x[1, 0])
        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation.w = 1.0
        msg.twist.twist.linear.x = float(estimate.x[2, 0])
        msg.twist.twist.linear.y = float(estimate.x[3, 0])

        cov = [0.0] * 36
        cov[0] = float(estimate.p[0, 0])
        cov[1] = float(estimate.p[0, 1])
        cov[6] = float(estimate.p[1, 0])
        cov[7] = float(estimate.p[1, 1])
        cov[14] = 1e-4
        cov[21] = 1e-3
        cov[28] = 1e-3
        cov[35] = 1e-3
        msg.pose.covariance = cov

        twist_cov = [0.0] * 36
        twist_cov[0] = float(estimate.p[2, 2])
        twist_cov[7] = float(estimate.p[3, 3])
        twist_cov[14] = 1e-4
        twist_cov[21] = 1e-3
        twist_cov[28] = 1e-3
        twist_cov[35] = 1e-3
        msg.twist.covariance = twist_cov
        self.odom_pub.publish(msg)

    def publish_futures(self, now: float, visible: bool, measurement_age_s: float, estimate: Any) -> None:
        payload: dict[str, Any] = {
            "stamp_s": now,
            "visible": visible,
            "measurement_age_s": finite_or_none(measurement_age_s),
            "initialized": bool(estimate.initialized),
            "frame_id": self.frame_id,
            "top_n": self.top_n,
            "estimate": None,
            "hypotheses": [],
        }

        if estimate.initialized:
            payload["estimate"] = {
                "x_m": float(estimate.x[0, 0]),
                "y_m": float(estimate.x[1, 0]),
                "vx_mps": float(estimate.x[2, 0]),
                "vy_mps": float(estimate.x[3, 0]),
                "cov_xx": float(estimate.p[0, 0]),
                "cov_xy": float(estimate.p[0, 1]),
                "cov_yy": float(estimate.p[1, 1]),
            }
            for rank, hyp in enumerate(self.tracker.top_hypotheses(self.top_n), start=1):
                payload["hypotheses"].append(
                    {
                        "rank": rank,
                        "model": str(hyp.model),
                        "probability": float(hyp.weight),
                        "x_m": float(hyp.x[0, 0]),
                        "y_m": float(hyp.x[1, 0]),
                        "vx_mps": float(hyp.x[2, 0]),
                        "vy_mps": float(hyp.x[3, 0]),
                        "cov_xx": float(hyp.p[0, 0]),
                        "cov_xy": float(hyp.p[0, 1]),
                        "cov_yy": float(hyp.p[1, 1]),
                        "path": self.project_path(hyp),
                    }
                )

        self.futures_pub.publish(String(data=json.dumps(payload, separators=(",", ":"))))

    def publish_status(self, now: float, visible: bool, measurement_age_s: float, estimate: Any) -> None:
        if now - self.last_log_s < 0.5:
            return
        self.last_log_s = now

        if not estimate.initialized:
            text = "WAITING_FOR_TARGET"
        elif visible:
            text = "VISIBLE"
        else:
            tops = self.tracker.top_hypotheses(min(3, self.top_n))
            top_text = ", ".join(f"{h.model}:{100.0*h.weight:.1f}%" for h in tops)
            text = f"OCCLUDED age={finite_or_none(measurement_age_s)} top=[{top_text}]"
        self.status_pub.publish(String(data=text))

    def project_path(self, hyp: Any) -> list[dict[str, float]]:
        model = self.model_lookup.get(str(hyp.model))
        x = np.asarray(hyp.x, dtype=float).copy()
        points = []
        t = 0.0
        while t <= self.future_horizon_s + 1e-9:
            points.append({"t_s": round(t, 3), "x_m": float(x[0, 0]), "y_m": float(x[1, 0])})
            step = min(self.future_dt_s, self.future_horizon_s - t)
            if step <= 1e-9:
                break
            if model is None:
                x[0, 0] += x[2, 0] * step
                x[1, 0] += x[3, 0] * step
            else:
                x[0, 0] += x[2, 0] * step + 0.5 * model.ax_mps2 * step * step
                x[1, 0] += x[3, 0] * step + 0.5 * model.ay_mps2 * step * step
                x[2, 0] = model.speed_scale * (x[2, 0] + model.ax_mps2 * step)
                x[3, 0] = model.speed_scale * (x[3, 0] + model.ay_mps2 * step)
            t += step
        return points


def finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = GhostMHTrackerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
