import json
import math
import os
from typing import Any

import numpy as np
import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile, qos_profile_sensor_data
from std_msgs.msg import String

from ghost_sim_ros2.data_contract import (
    build_run_identity,
    build_timestamps,
    build_validity,
    contract_envelope,
    short_identifier,
)
from analysis.ghost_mh_calibrated import CalibratedModeBankTracker
from analysis.measurement_covariance_config import build_measurement_r_xy
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
    "software-regime scaffold, not a calibrated probability. It must remain tunable "
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
        self.declare_parameter("status_json_topic", "/ghost/tracker_mh/status_json")
        self.declare_parameter(
            "calibration_artifact_path", os.environ.get("GHOST_CALIBRATION_ARTIFACT", "")
        )
        self.declare_parameter("configuration_label", "ghost-mh-live-v1")
        self.declare_parameter("frame_id", "camera")
        self.declare_parameter("child_frame_id", "ghost_target_mh")
        self.declare_parameter("tick_hz", 30.0)
        self.declare_parameter("measurement_timeout_s", 0.30)
        self.declare_parameter("measurement_std_m", 0.005)
        self.declare_parameter("measurement_r_xx_m2", -1.0)
        self.declare_parameter("measurement_r_xy_m2", 0.0)
        self.declare_parameter("measurement_r_yy_m2", -1.0)
        self.declare_parameter("max_occlusion_s", 3.0)
        self.declare_parameter("max_workspace_range_m", 5.0)
        self.declare_parameter("allow_signed_local_coordinates", False)
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
        self.status_json_topic = str(self.get_parameter("status_json_topic").value)
        self.calibration_artifact_path = str(self.get_parameter("calibration_artifact_path").value)
        self.configuration_label = str(self.get_parameter("configuration_label").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.child_frame_id = str(self.get_parameter("child_frame_id").value)
        self.tick_hz = float(self.get_parameter("tick_hz").value)
        self.measurement_timeout_s = float(self.get_parameter("measurement_timeout_s").value)
        self.top_n = int(self.get_parameter("top_n").value)
        self.allow_signed_local_coordinates = bool(self.get_parameter("allow_signed_local_coordinates").value)
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

        measurement_std_m = float(self.get_parameter("measurement_std_m").value)
        r_xx = float(self.get_parameter("measurement_r_xx_m2").value)
        r_xy = float(self.get_parameter("measurement_r_xy_m2").value)
        r_yy = float(self.get_parameter("measurement_r_yy_m2").value)
        measurement_covariance_xy = None
        if r_xx > 0.0 and r_yy > 0.0:
            measurement_covariance_xy = build_measurement_r_xy(measurement_std_m, r_xx, r_xy, r_yy)

        self.max_occlusion_s = float(self.get_parameter("max_occlusion_s").value)
        self.max_workspace_range_m = float(self.get_parameter("max_workspace_range_m").value)
        self.accel_temperature = float(self.get_parameter("accel_temperature").value)
        self.tracker = CalibratedModeBankTracker(
            measurement_std_m=measurement_std_m,
            measurement_covariance_xy=measurement_covariance_xy,
            max_occlusion_s=self.max_occlusion_s,
            max_workspace_range_m=self.max_workspace_range_m,
            accel_temperature=self.accel_temperature,
            allow_signed_local_coordinates=self.allow_signed_local_coordinates,
        )
        self.model_lookup = {model.name: model for model in mode_bank()}
        self.provenance = build_run_identity(
            node_name="ghost_mh_tracker",
            frame_id=self.frame_id,
            configuration_label=self.configuration_label,
            configuration={
                "tick_hz": self.tick_hz,
                "measurement_timeout_s": self.measurement_timeout_s,
                "measurement_std_m": measurement_std_m,
                "measurement_r_xx_m2": r_xx,
                "measurement_r_xy_m2": r_xy,
                "measurement_r_yy_m2": r_yy,
                "max_occlusion_s": self.max_occlusion_s,
                "max_workspace_range_m": self.max_workspace_range_m,
                "allow_signed_local_coordinates": self.allow_signed_local_coordinates,
                "top_n": self.top_n,
                "future_horizon_s": self.future_horizon_s,
                "future_dt_s": self.future_dt_s,
                "accel_temperature": self.accel_temperature,
                "stationary_gate_enabled": self.stationary_gate_enabled,
                "stationary_window_s": self.stationary_window_s,
                "stationary_enter_speed_mps": self.stationary_enter_speed_mps,
                "stationary_exit_speed_mps": self.stationary_exit_speed_mps,
                "stationary_min_samples": self.stationary_min_samples,
                "stationary_hold_prior": self.stationary_hold_prior,
                "stationary_hold_max_s": self.stationary_hold_max_s,
            },
            calibration_artifact_path=self.calibration_artifact_path,
        )

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
        self.rejected_measurement_count: int = 0
        self.last_rejection_reason: str | None = None
        self.sequence: int = 0

        # Camera measurements use sensor-data QoS so a slow consumer cannot
        # backpressure the live detector. Tracker outputs remain reliable.
        output_qos = QoSProfile(depth=1)
        self.sub = self.create_subscription(
            PoseWithCovarianceStamped,
            self.input_topic,
            self.on_measurement,
            qos_profile_sensor_data,
        )
        self.odom_pub = self.create_publisher(Odometry, self.odom_topic, output_qos)
        self.futures_pub = self.create_publisher(String, self.futures_topic, output_qos)
        self.status_pub = self.create_publisher(String, self.status_topic, output_qos)
        self.status_json_pub = self.create_publisher(String, self.status_json_topic, output_qos)

        period = 1.0 / max(self.tick_hz, 1.0)
        self.timer = self.create_timer(period, self.on_timer)

        self.get_logger().info(
            "GHOST V1 heuristic tracker listening on "
            f"{self.input_topic}; publishing {self.odom_topic}, "
            f"{self.futures_topic}; tick={self.tick_hz:.1f}Hz; "
            f"timeout={self.measurement_timeout_s:.2f}s; future_dt={self.future_dt_s:.2f}s; "
            f"stationary_gate={self.stationary_gate_enabled}; "
            f"measurement_r_source={self.tracker.measurement_r_source}; "
            f"measurement_r_xy={self.tracker.measurement_r_xy}; "
            f"stationary_enter={self.stationary_enter_speed_mps:.3f}m/s; "
            f"stationary_exit={self.stationary_exit_speed_mps:.3f}m/s; "
            f"cal={short_identifier(self.provenance['calibration_id'])}; "
            f"cfg={short_identifier(self.provenance['configuration_id'])}"
        )

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1e-9

    def on_measurement(self, msg: PoseWithCovarianceStamped) -> None:
        now = self.now_s()
        x = float(msg.pose.pose.position.x)
        y = float(msg.pose.pose.position.y)
        if not math.isfinite(x) or not math.isfinite(y):
            self.rejected_measurement_count += 1
            self.last_rejection_reason = "REJECT_NONFINITE_MEASUREMENT"
            return
        # V1 AprilTag pose uses camera-frame forward range as +x. Negative x is
        # behind the camera/invalid for the current single-camera bench geometry;
        # y is lateral and may legitimately be positive or negative.
        if ((not self.allow_signed_local_coordinates) and x < 0.0) or math.hypot(x, y) > self.max_workspace_range_m:
            self.rejected_measurement_count += 1
            self.last_rejection_reason = (
                "REJECT_BEHIND_CAMERA_MEASUREMENT"
                if ((not self.allow_signed_local_coordinates) and x < 0.0)
                else "REJECT_OUT_OF_WORKSPACE_MEASUREMENT"
            )
            return

        msg_stamp_s = float(msg.header.stamp.sec) + 1e-9 * float(msg.header.stamp.nanosec)
        if msg_stamp_s <= 0.0 or abs(now - msg_stamp_s) > 30.0:
            msg_stamp_s = now

        self.latest_xy = (x, y)
        self.latest_stamp_s = msg_stamp_s
        self.latest_arrival_s = now
        self.measurement_count += 1
        self.last_rejection_reason = None

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

        processing_time_s = self.now_s()
        if estimate.initialized:
            self.publish_odom(processing_time_s, estimate)
        self.publish_futures(processing_time_s, visible, measurement_age_s, estimate)
        self.publish_status(processing_time_s, visible, measurement_age_s, estimate)

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

    def validity_for_output(self, visible: bool, measurement_age_s: float, estimate: Any) -> dict[str, Any]:
        if not estimate.initialized:
            if self.latest_xy is None:
                return build_validity(
                    is_valid=False,
                    state="WAITING_FOR_TARGET",
                    reason="Tracker has not accepted an initialization measurement.",
                )
            return build_validity(
                is_valid=False,
                state="DEGRADED",
                reason="No bounded hypotheses remain inside the declared occlusion envelope.",
            )
        if visible:
            return build_validity(is_valid=True, state="VALID_TRACKING")
        if measurement_age_s > self.max_occlusion_s:
            return build_validity(
                is_valid=False,
                state="DEGRADED",
                reason="Measurement age exceeded max_occlusion_s.",
            )
        return build_validity(is_valid=True, state="VALID_PREDICTION_ONLY")

    def contract_fields(
        self,
        processing_time_s: float,
        visible: bool,
        measurement_age_s: float,
        estimate: Any,
    ) -> dict[str, Any]:
        return contract_envelope(
            frame_id=self.frame_id,
            provenance=self.provenance,
            timestamps=build_timestamps(
                source_time_s=self.latest_stamp_s,
                receipt_time_s=self.latest_arrival_s,
                processing_time_s=processing_time_s,
                publication_time_s=self.now_s(),
            ),
            validity=self.validity_for_output(visible, measurement_age_s, estimate),
        )

    def publish_futures(self, processing_time_s: float, visible: bool, measurement_age_s: float, estimate: Any) -> None:
        self.sequence += 1
        rx_latency_s = math.inf
        if self.latest_stamp_s is not None and self.latest_arrival_s is not None:
            rx_latency_s = self.latest_arrival_s - self.latest_stamp_s

        payload: dict[str, Any] = {
            **self.contract_fields(processing_time_s, visible, measurement_age_s, estimate),
            "tracker": "ghost_mh",
            "sequence": self.sequence,
            "stamp_s": processing_time_s,
            "visible": visible,
            "measurement_age_s": finite_or_none(measurement_age_s),
            "measurement_rx_latency_s": finite_or_none(rx_latency_s),
            "measurement_count": self.measurement_count,
            "rejected_measurement_count": self.rejected_measurement_count,
            "last_rejection_reason": self.last_rejection_reason,
            "initialized": bool(estimate.initialized),
            "top_n": self.top_n,
            "tick_hz": self.tick_hz,
            "future_horizon_s": self.future_horizon_s,
            "future_dt_s": self.future_dt_s,
            "stationary_gate_enabled": bool(self.stationary_gate_enabled),
            "measurement_r_xy": self.tracker.measurement_r_xy,
            "measurement_r_source": self.tracker.measurement_r_source,
            "measurement_r_status": self.tracker.measurement_r_status,
            "measurement_r_provenance": self.tracker.measurement_r_provenance,
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
                            "relative_hypothesis_weight": float(hyp.weight),
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

    def publish_status(self, processing_time_s: float, visible: bool, measurement_age_s: float, estimate: Any) -> None:
        if processing_time_s - self.last_log_s < 0.25:
            return
        self.last_log_s = processing_time_s

        if not estimate.initialized:
            if self.latest_xy is None:
                live_status = "WAITING_FOR_TARGET"
                text = "WAITING_FOR_TARGET"
            else:
                live_status = "DEGRADED_NO_HYPOTHESES"
                text = "DEGRADED - NO BOUNDED HYPOTHESES"
        elif visible:
            live_status = "VISIBLE_MEASUREMENT_LOCK"
            text = (
                "VISIBLE - MEASUREMENT LOCK "
                f"stationary={self.stationary_state.active} "
                f"window_speed={finite_or_none(self.stationary_state.speed_mps)}"
            )
        elif self.hidden_stationary_hold_active:
            live_status = "HIDDEN_STATIONARY_HOLD"
            text = (
                "HIDDEN - STATIONARY HOLD "
                f"age={finite_or_none(measurement_age_s)} "
                f"window_speed={finite_or_none(self.stationary_state.speed_mps)}"
            )
        else:
            live_status = "OCCLUDED_HYPOTHESIS_BANK"
            tops = self.tracker.top_hypotheses(min(3, self.top_n))
            top_text = ", ".join(f"{h.model}:{100.0*h.weight:.1f}%" for h in tops)
            text = f"OCCLUDED - HYPOTHESIS BANK age={finite_or_none(measurement_age_s)} top=[{top_text}]"
        if self.last_rejection_reason is not None:
            text += f" rejected={self.last_rejection_reason} rejected_count={self.rejected_measurement_count}"
        text += (
            f" cal={short_identifier(self.provenance['calibration_id'])}"
            f" cfg={short_identifier(self.provenance['configuration_id'])}"
        )
        self.status_pub.publish(String(data=text))
        status_payload = {
            **self.contract_fields(processing_time_s, visible, measurement_age_s, estimate),
            "tracker": "ghost_mh",
            "sequence": self.sequence,
            "visible": visible,
            "status_text": text,
            "live_status": live_status,
            "measurement_age_s": finite_or_none(measurement_age_s),
            "rejected_measurement_count": self.rejected_measurement_count,
            "last_rejection_reason": self.last_rejection_reason,
        }
        self.status_json_pub.publish(String(data=json.dumps(status_payload, separators=(",", ":"))))


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
                "relative_hypothesis_weight": stationary_prior,
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
                    "relative_hypothesis_weight": residual_prior,
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
