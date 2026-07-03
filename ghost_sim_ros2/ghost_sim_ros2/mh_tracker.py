import json
import math
from typing import Any

import numpy as np
import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import String
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String

from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.ghost_mh_mode_bank import mode_bank
from analysis.stationary_gate import StationaryGateConfig, WindowedVelocityGate


STATIONARY_THRESHOLD_STATUS = "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R"
STATIONARY_THRESHOLD_PROVENANCE = (
    "Live ROS stationary gate uses the reviewed candidate range from the offline "
    "software-regime scaffold: enter=0.065 m/s at a 1.5 s window, exit=0.090 m/s. "
    "These values still require committed hardware-calibrated noise artifacts before "
    "being cited as report-grade validation."
)
STATIONARY_HOLD_PRIOR_STATUS = "CANDIDATE_PLACEHOLDER_PENDING_HARDWARE_R"
STATIONARY_HOLD_PRIOR_PROVENANCE = (
    "stationary_hold_prior=0.95 is a candidate V1 design prior from the reviewed "
    "software-regime scaffold, not a measured probability. It must remain tunable "
    "and should be revisited after live hardware trials."
)


class GhostMHTrackerNode(Node):
    """Live ROS2 wrapper for the calibrated V1 heuristic hypothesis tracker.

    Input:
        /ghost/vision/target_pose       geometry_msgs/PoseWithCovarianceStamped

    Outputs:
        /ghost/tracker_mh/target_odom   nav_msgs/Odometry
        /ghost/tracker_mh/futures_json  std_msgs/String JSON payload
        /ghost/tracker_mh/status        std_msgs/String human-readable status

    Important:
        Stationary-hold behavior here is an integration of the reviewed offline
        scaffold. It is still a candidate live behavior until hardware-calibrated
        noise replay and live Pi trials are reviewed.
    """

    def __init__(self) -> None:
        super().__init__("ghost_mh_tracker")

        self.declare_parameter("input_topic", "/ghost/vision/target_pose")
        self.declare_parameter("odom_topic", "/ghost/tracker_mh/target_odom")
        self.declare_parameter("futures_topic", "/ghost/tracker_mh/futures_json")
        self.declare_parameter("status_topic", "/ghost/tracker_mh/status")
        self.declare_parameter("frame_id", "camera")
        self.declare_parameter("child_frame_id", "ghost_target_mh")
        self.declare_parameter("tick_hz", 30.0)
        self.declare_parameter("measurement_timeout_s", 0.30)
        self.declare_parameter("measurement_std_m", 0.04)
        self.declare_parameter("max_occlusion_s", 3.0)
        self.declare_parameter("max_workspace_range_m", 5.0)
        self.declare_parameter("top_n", 5)
        self.declare_parameter("future_horizon_s", 1.5)
        self.declare_parameter("future_dt_s", 0.10)
        self.declare_parameter("accel_temperature", 0.30)

        # Reviewed candidate values from the offline software-regime scaffold.
        # These are intentionally parameters so live trials can sweep them without
        # changing code. They remain placeholders pending hardware-calibrated R.
        self.declare_parameter("stationary_gate_enabled", True)
        self.declare_parameter("stationary_window_s", 1.5)
        self.declare_parameter("stationary_enter_speed_mps", 0.065)
        self.declare_parameter("stationary_exit_speed_mps", 0.090)
        self.declare_parameter("stationary_min_samples", 5)
        self.declare_parameter("stationary_hold_prior", 0.95)
        self.declare_parameter("stationary_hold_max_s", 4.0)

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
        self.stationary_gate_enabled = bool(self.get_parameter("stationary_gate_enabled").value)
        self.stationary_window_s = float(self.get_parameter("stationary_window_s").value)
        self.stationary_enter_speed_mps = float(self.get_parameter("stationary_enter_speed_mps").value)
        self.stationary_exit_speed_mps = float(self.get_parameter("stationary_exit_speed_mps").value)
        self.stationary_min_samples = int(self.get_parameter("stationary_min_samples").value)
        self.stationary_hold_max_s = float(self.get_parameter("stationary_hold_max_s").value)
        self.stationary_hold_prior = float(self.get_parameter("stationary_hold_prior").value)
        self.stationary_hold_prior = min(max(self.stationary_hold_prior, 0.50), 1.0)

        self.tracker = CalibratedModeBankTracker(
            measurement_std_m=float(self.get_parameter("measurement_std_m").value),
            max_occlusion_s=float(self.get_parameter("max_occlusion_s").value),
            max_workspace_range_m=float(self.get_parameter("max_workspace_range_m").value),
            accel_temperature=float(self.get_parameter("accel_temperature").value),
        )
        self.model_lookup = {model.name: model for model in mode_bank()}

        self.stationary_gate = WindowedVelocityGate(
            StationaryGateConfig(
                window_s=self.stationary_window_s,
                enter_speed_mps=self.stationary_enter_speed_mps,
                exit_speed_mps=self.stationary_exit_speed_mps,
                min_samples=self.stationary_min_samples,
            )
        )
        self.stationary_state = self.stationary_gate.state
        self.hidden_stationary_hold_active = False

        self.latest_xy: tuple[float, float] | None = None
        self.latest_stamp_s: float | None = None
        self.latest_arrival_s: float | None = None
        self.last_tick_s: float | None = None
        self.last_log_s: float = 0.0
        self.measurement_count: int = 0
        self.sequence: int = 0

        # Depth-1 QoS is intentional for live tracking: use the newest sample and
        # do not let old camera measurements build up in the ROS queue.
        live_qos = QoSProfile(depth=1)
        self.sub = self.create_subscription(
            PoseWithCovarianceStamped,
            self.input_topic,
            self.on_measurement,
            live_qos,
        )
        self.odom_pub = self.create_publisher(Odometry, self.odom_topic, live_qos)
        self.futures_pub = self.create_publisher(String, self.futures_topic, live_qos)
        self.status_pub = self.create_publisher(String, self.status_topic, live_qos)

        period = 1.0 / max(self.tick_hz, 1.0)
        self.timer = self.create_timer(period, self.on_timer)

        self.get_logger().info(
            "GHOST V1 heuristic tracker listening on "
            f"{self.input_topic}; publishing {self.odom_topic}, "
            f"{self.futures_topic}; tick={self.tick_hz:.1f}Hz; "
            f"timeout={self.measurement_timeout_s:.2f}s; future_dt={self.future_dt_s:.2f}s; "
            f"stationary_gate={self.stationary_gate_enabled}; "
            f"stationary_enter={self.stationary_enter_speed_mps:.3f}m/s; "
            f"stationary_exit={self.stationary_exit_speed_mps:.3f}m/s"
        )

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def on_measurement(self, msg: PoseWithCovarianceStamped) -> None:
        now = self.now_s()
        x = float(msg.pose.pose.position.x)
        y = float(msg.pose.pose.position.y)
        if not math.isfinite(x) or not math.isfinite(y):
            return
        # V1 AprilTag pose uses camera-frame forward range as +x. Negative x is
        # behind the camera/invalid for the current single-camera bench geometry;
        # y is lateral and may legitimately be positive or negative.
        if x < 0.0 or math.hypot(x, y) > float(self.get_parameter("max_workspace_range_m").value):
            return

        msg_stamp_s = float(msg.header.stamp.sec) + 1e-9 * float(msg.header.stamp.nanosec)
        if msg_stamp_s <= 0.0 or abs(now - msg_stamp_s) > 30.0:
            msg_stamp_s = now

        self.latest_xy = (x, y)
        self.latest_stamp_s = msg_stamp_s
        self.latest_arrival_s = now
        self.measurement_count += 1

        if self.stationary_gate_enabled:
            self.stationary_state = self.stationary_gate.update(msg_stamp_s, x, y)

    def on_timer(self) -> None:
        now = self.now_s()
        if self.last_tick_s is None:
            self.last_tick_s = now
            return

        dt = max(1e-3, min(0.15, now - self.last_tick_s))
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

        # The stationary gate is updated only by real visible measurements. During
        # occlusion its state intentionally freezes at the last visible decision,
        # which answers: "was the target stationary immediately before hiding?"
        # The separate measurement_age_s bound below prevents holding forever.
        self.hidden_stationary_hold_active = bool(
            self.stationary_gate_enabled
            and estimate.initialized
            and (not visible)
            and self.stationary_state.active
            and self.latest_xy is not None
            and measurement_age_s <= self.stationary_hold_max_s
        )

        if estimate.initialized:
            self.publish_odom(now, estimate)
        self.publish_futures(now, visible, measurement_age_s, estimate)
        self.publish_status(now, visible, measurement_age_s, estimate)

    def publish_odom(self, now: float, estimate: Any) -> None:
        msg = Odometry()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.child_frame_id = self.child_frame_id

        if self.hidden_stationary_hold_active and self.latest_xy is not None:
            msg.pose.pose.position.x = float(self.latest_xy[0])
            msg.pose.pose.position.y = float(self.latest_xy[1])
            msg.twist.twist.linear.x = 0.0
            msg.twist.twist.linear.y = 0.0
        else:
            msg.pose.pose.position.x = float(estimate.x[0, 0])
            msg.pose.pose.position.y = float(estimate.x[1, 0])
            msg.twist.twist.linear.x = float(estimate.x[2, 0])
            msg.twist.twist.linear.y = float(estimate.x[3, 0])

        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation.w = 1.0

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
        self.sequence += 1
        rx_latency_s = math.inf
        if self.latest_stamp_s is not None and self.latest_arrival_s is not None:
            rx_latency_s = self.latest_arrival_s - self.latest_stamp_s

        payload: dict[str, Any] = {
            "sequence": self.sequence,
            "stamp_s": now,
            "visible": visible,
            "measurement_age_s": finite_or_none(measurement_age_s),
            "measurement_rx_latency_s": finite_or_none(rx_latency_s),
            "measurement_count": self.measurement_count,
            "initialized": bool(estimate.initialized),
            "frame_id": self.frame_id,
            "top_n": self.top_n,
            "tick_hz": self.tick_hz,
            "future_horizon_s": self.future_horizon_s,
            "future_dt_s": self.future_dt_s,
            "stationary_gate_enabled": bool(self.stationary_gate_enabled),
            "stationary_threshold_status": STATIONARY_THRESHOLD_STATUS,
            "stationary_threshold_provenance": STATIONARY_THRESHOLD_PROVENANCE,
            "stationary_window_s": self.stationary_window_s,
            "stationary_enter_speed_mps": self.stationary_enter_speed_mps,
            "stationary_exit_speed_mps": self.stationary_exit_speed_mps,
            "stationary_min_samples": self.stationary_min_samples,
            "stationary_hold_prior": self.stationary_hold_prior,
            "stationary_hold_prior_status": STATIONARY_HOLD_PRIOR_STATUS,
            "stationary_hold_prior_provenance": STATIONARY_HOLD_PRIOR_PROVENANCE,
            "stationary_hold_max_s": self.stationary_hold_max_s,
            "stationary_hold_active": bool(self.stationary_state.active),
            "hidden_stationary_hold_active": bool(self.hidden_stationary_hold_active),
            "stationary_window_speed_mps": finite_or_none(self.stationary_state.speed_mps),
            "stationary_window_span_s": finite_or_none(self.stationary_state.span_s),
            "stationary_gate_reason": self.stationary_state.reason,
            "estimate": None,
            "hypotheses": [],
        }

        if estimate.initialized:
            est_x, est_y, est_vx, est_vy = self.current_output_state(estimate)
            payload["estimate"] = {
                "x_m": est_x,
                "y_m": est_y,
                "vx_mps": est_vx,
                "vy_mps": est_vy,
                "cov_xx": float(estimate.p[0, 0]),
                "cov_xy": float(estimate.p[0, 1]),
                "cov_yy": float(estimate.p[1, 1]),
            }

            if self.hidden_stationary_hold_active:
                payload["hypotheses"] = self.stationary_hold_hypotheses(estimate)
            else:
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
        if now - self.last_log_s < 0.25:
            return
        self.last_log_s = now

        if not estimate.initialized:
            text = "WAITING_FOR_TARGET"
        elif visible:
            text = (
                "VISIBLE - MEASUREMENT LOCK "
                f"stationary={self.stationary_state.active} "
                f"window_speed={finite_or_none(self.stationary_state.speed_mps)}"
            )
        elif self.hidden_stationary_hold_active:
            text = (
                "HIDDEN - STATIONARY HOLD "
                f"age={finite_or_none(measurement_age_s)} "
                f"window_speed={finite_or_none(self.stationary_state.speed_mps)}"
            )
        else:
            tops = self.tracker.top_hypotheses(min(3, self.top_n))
            top_text = ", ".join(f"{h.model}:{100.0*h.weight:.1f}%" for h in tops)
            text = f"OCCLUDED - HYPOTHESIS BANK age={finite_or_none(measurement_age_s)} top=[{top_text}]"
        self.status_pub.publish(String(data=text))

    def current_output_state(self, estimate: Any) -> tuple[float, float, float, float]:
        if self.hidden_stationary_hold_active and self.latest_xy is not None:
            return float(self.latest_xy[0]), float(self.latest_xy[1]), 0.0, 0.0
        return (
            float(estimate.x[0, 0]),
            float(estimate.x[1, 0]),
            float(estimate.x[2, 0]),
            float(estimate.x[3, 0]),
        )

    def stationary_hold_hypotheses(self, estimate: Any) -> list[dict[str, Any]]:
        if self.latest_xy is not None:
            x_m = float(self.latest_xy[0])
            y_m = float(self.latest_xy[1])
        else:
            x_m = float(estimate.x[0, 0])
            y_m = float(estimate.x[1, 0])

        stationary_prior = self.stationary_hold_prior
        residual_prior = max(0.0, 1.0 - stationary_prior)
        path = self.stationary_hold_path(x_m, y_m)
        cov_xx = float(estimate.p[0, 0])
        cov_xy = float(estimate.p[0, 1])
        cov_yy = float(estimate.p[1, 1])

        hypotheses = [
            {
                "rank": 1,
                "model": "stationary_hold",
                "probability": stationary_prior,
                "x_m": x_m,
                "y_m": y_m,
                "vx_mps": 0.0,
                "vy_mps": 0.0,
                "cov_xx": cov_xx,
                "cov_xy": cov_xy,
                "cov_yy": cov_yy,
                "path": path,
            }
        ]
        if self.top_n > 1 and residual_prior > 0.0:
            hypotheses.append(
                {
                    "rank": 2,
                    "model": "bounded_uncertainty_hold",
                    "probability": residual_prior,
                    "x_m": x_m,
                    "y_m": y_m,
                    "vx_mps": 0.0,
                    "vy_mps": 0.0,
                    "cov_xx": cov_xx,
                    "cov_xy": cov_xy,
                    "cov_yy": cov_yy,
                    "path": path,
                }
            )
        return hypotheses[: self.top_n]

    def stationary_hold_path(self, x_m: float, y_m: float) -> list[dict[str, float]]:
        points = []
        t = 0.0
        while t <= self.future_horizon_s + 1e-9:
            points.append({"t_s": round(t, 3), "x_m": float(x_m), "y_m": float(y_m)})
            step = min(self.future_dt_s, self.future_horizon_s - t)
            if step <= 1e-9:
                break
            t += step
        return points

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
