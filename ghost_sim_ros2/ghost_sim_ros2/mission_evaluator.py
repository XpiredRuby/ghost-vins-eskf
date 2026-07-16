"""Mission-level evidence and acceptance evaluator for the GHOST software demo."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String

from ghost_sim_ros2.data_contract import (
    build_run_identity,
    build_timestamps,
    build_validity,
    contract_envelope,
)


class GhostMissionEvaluator(Node):
    def __init__(self) -> None:
        super().__init__("ghost_mission_evaluator")
        self.declare_parameter("metrics_path", "")
        self.declare_parameter("publish_rate_hz", 4.0)
        self.declare_parameter("minimum_occlusion_s", 0.25)
        self.declare_parameter("frame_id", "ghost_local")
        self.declare_parameter(
            "calibration_artifact_path", os.environ.get("GHOST_CALIBRATION_ARTIFACT", "")
        )
        self.declare_parameter("configuration_label", "ghost-drone-mission-evaluator-v1")
        self.metrics_path = str(self.get_parameter("metrics_path").value).strip()
        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self.minimum_occlusion_s = float(self.get_parameter("minimum_occlusion_s").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.calibration_artifact_path = str(self.get_parameter("calibration_artifact_path").value)
        self.configuration_label = str(self.get_parameter("configuration_label").value)
        self.provenance = build_run_identity(
            node_name="ghost_mission_evaluator",
            frame_id=self.frame_id,
            configuration_label=self.configuration_label,
            configuration={
                "publish_rate_hz": self.publish_rate_hz,
                "minimum_occlusion_s": self.minimum_occlusion_s,
            },
            calibration_artifact_path=self.calibration_artifact_path,
        )

        self.start_s: float | None = None
        self.elapsed_s = 0.0
        self.visible: bool | None = None
        self.visibility_reason = "WAITING"
        self.hidden_obstacle_active = False
        self.hidden_start_elapsed_s: float | None = None
        self.obstacle_occlusion_count = 0
        self.reacquisition_count = 0
        self.occlusion_durations_s: list[float] = []
        self.imm_outputs_during_obstacle_occlusion = 0
        self.mh_outputs_during_obstacle_occlusion = 0
        self.imm_total_outputs = 0
        self.mh_total_outputs = 0
        self.collision_count = 0
        self.out_of_bounds_count = 0
        self.measurement_count = 0
        self.target_finished = False
        self.mission_complete = False
        self.finalized = False
        self.latest_truth: tuple[float, float] | None = None
        self.latest_observer: tuple[float, float] | None = None
        self.observer_distance_traveled_m = 0.0
        self.observer_update_count = 0
        self.navigation_command_count = 0
        self.hidden_vantage_command_count = 0
        self.navigation_safety_intervention_count = 0
        self.max_commanded_speed_mps = 0.0
        self.latest_imm: tuple[float, float] | None = None
        self.latest_mh: tuple[float, float] | None = None
        self.error_sums = {"imm_all": 0.0, "mh_all": 0.0, "imm_hidden": 0.0, "mh_hidden": 0.0}
        self.error_counts = {key: 0 for key in self.error_sums}
        self.max_errors = {"imm_all": 0.0, "mh_all": 0.0, "imm_hidden": 0.0, "mh_hidden": 0.0}
        self.last_write_s = -math.inf

        qos = QoSProfile(depth=50)
        self.create_subscription(String, "/ghost/sim/visibility_json", self.on_visibility, qos)
        self.create_subscription(String, "/ghost/sim/mission_status_json", self.on_mission_status, qos)
        # Simulator truth is published as PoseWithCovarianceStamped.
        from geometry_msgs.msg import PoseWithCovarianceStamped

        self.create_subscription(PoseWithCovarianceStamped, "/ghost/sim/target_truth", self.on_truth_pose, qos)
        self.create_subscription(Odometry, "/ghost/sim/observer_odom", self.on_observer, qos)
        self.create_subscription(String, "/ghost/nav/status_json", self.on_nav_status, qos)
        self.create_subscription(Odometry, "/ghost/tracker_imm/target_odom", self.on_imm, qos)
        self.create_subscription(Odometry, "/ghost/tracker_mh/target_odom", self.on_mh, qos)
        self.status_pub = self.create_publisher(String, "/ghost/evaluation/status_json", qos)
        self.timer = self.create_timer(
            1.0 / max(self.publish_rate_hz, 1.0), self.tick
        )
        self.get_logger().info(
            f"GHOST mission evaluator active; metrics_path={self.metrics_path or 'disabled'}"
        )

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1.0e-9

    def on_visibility(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        elapsed = float(payload.get("elapsed_s", self.elapsed_s))
        new_visible = bool(payload.get("visible", False))
        reason = str(payload.get("visibility_reason", "UNKNOWN"))
        if self.start_s is None:
            self.start_s = self.now_s() - elapsed
        if not self.mission_complete:
            self.elapsed_s = max(self.elapsed_s, elapsed)

        if self.visible is not None:
            if self.visible and not new_visible and reason == "OCCLUDED_BY_OBSTACLE":
                self.hidden_obstacle_active = True
                self.hidden_start_elapsed_s = elapsed
                self.obstacle_occlusion_count += 1
            elif self.hidden_obstacle_active and new_visible:
                duration = 0.0
                if self.hidden_start_elapsed_s is not None:
                    duration = max(0.0, elapsed - self.hidden_start_elapsed_s)
                if duration >= self.minimum_occlusion_s:
                    self.occlusion_durations_s.append(duration)
                    self.reacquisition_count += 1
                else:
                    self.obstacle_occlusion_count = max(0, self.obstacle_occlusion_count - 1)
                self.hidden_obstacle_active = False
                self.hidden_start_elapsed_s = None
            elif self.hidden_obstacle_active and not new_visible and reason != "OCCLUDED_BY_OBSTACLE":
                # Preserve the obstacle-loss interval until visibility returns; the reason may
                # briefly transition through FOV at the obstacle edge.
                pass
        self.visible = new_visible
        self.visibility_reason = reason

    def on_mission_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        incoming_elapsed_s = float(payload.get("elapsed_s", 0.0))
        if not self.mission_complete:
            self.elapsed_s = max(self.elapsed_s, incoming_elapsed_s)
        self.collision_count = max(self.collision_count, int(payload.get("collision_count", 0)))
        self.out_of_bounds_count = max(self.out_of_bounds_count, int(payload.get("out_of_bounds_count", 0)))
        self.measurement_count = max(self.measurement_count, int(payload.get("measurement_count", 0)))
        self.target_finished = bool(payload.get("target_finished", self.target_finished))
        self.mission_complete = bool(payload.get("mission_complete", self.mission_complete))
        if self.mission_complete and not self.finalized:
            self.finalize()

    def on_observer(self, msg: Odometry) -> None:
        current = (float(msg.pose.pose.position.x), float(msg.pose.pose.position.y))
        if self.latest_observer is not None:
            step = math.hypot(current[0] - self.latest_observer[0], current[1] - self.latest_observer[1])
            if step < 0.50:
                self.observer_distance_traveled_m += step
        self.latest_observer = current
        self.observer_update_count += 1

    def on_nav_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        mode = str(payload.get("mode", ""))
        velocity = payload.get("command_velocity_mps", [0.0, 0.0])
        try:
            speed = math.hypot(float(velocity[0]), float(velocity[1]))
        except (TypeError, ValueError, IndexError):
            speed = 0.0
        self.max_commanded_speed_mps = max(self.max_commanded_speed_mps, speed)
        if speed > 1.0e-3:
            self.navigation_command_count += 1
        if mode == "HIDDEN_VANTAGE_REPOSITION":
            self.hidden_vantage_command_count += 1
        if bool(payload.get("safety_intervened", False)):
            self.navigation_safety_intervention_count += 1

    def on_truth_pose(self, msg: Any) -> None:
        self.latest_truth = (float(msg.pose.pose.position.x), float(msg.pose.pose.position.y))
        self.update_errors()

    def on_imm(self, msg: Odometry) -> None:
        self.latest_imm = (float(msg.pose.pose.position.x), float(msg.pose.pose.position.y))
        self.imm_total_outputs += 1
        if self.hidden_obstacle_active:
            self.imm_outputs_during_obstacle_occlusion += 1

    def on_mh(self, msg: Odometry) -> None:
        self.latest_mh = (float(msg.pose.pose.position.x), float(msg.pose.pose.position.y))
        self.mh_total_outputs += 1
        if self.hidden_obstacle_active:
            self.mh_outputs_during_obstacle_occlusion += 1

    def update_errors(self) -> None:
        if self.latest_truth is None:
            return
        for name, estimate in (("imm", self.latest_imm), ("mh", self.latest_mh)):
            if estimate is None:
                continue
            error = math.hypot(estimate[0] - self.latest_truth[0], estimate[1] - self.latest_truth[1])
            key = f"{name}_all"
            self.error_sums[key] += error * error
            self.error_counts[key] += 1
            self.max_errors[key] = max(self.max_errors[key], error)
            if self.hidden_obstacle_active:
                hidden_key = f"{name}_hidden"
                self.error_sums[hidden_key] += error * error
                self.error_counts[hidden_key] += 1
                self.max_errors[hidden_key] = max(self.max_errors[hidden_key], error)

    def rms(self, key: str) -> float | None:
        count = self.error_counts[key]
        if count <= 0:
            return None
        return math.sqrt(self.error_sums[key] / count)

    def acceptance(self) -> dict[str, bool]:
        return {
            "mission_completed": self.mission_complete,
            "obstacle_occlusion_observed": self.obstacle_occlusion_count >= 1,
            "target_reacquired": self.reacquisition_count >= 1,
            "imm_predicted_during_occlusion": self.imm_outputs_during_obstacle_occlusion > 0,
            "mh_predicted_during_occlusion": self.mh_outputs_during_obstacle_occlusion > 0,
            "observer_collision_free": self.collision_count == 0,
            "observer_inside_bounds": self.out_of_bounds_count == 0,
            "camera_measurements_received": self.measurement_count > 0,
            "observer_navigated": self.observer_distance_traveled_m >= 1.0,
            "hidden_vantage_reposition_used": self.hidden_vantage_command_count > 0,
        }

    def result(self) -> dict[str, object]:
        acceptance = self.acceptance()
        passed = all(acceptance.values())
        now = self.now_s()
        if self.mission_complete:
            validity = build_validity(
                is_valid=passed,
                state="MISSION_COMPLETE" if passed else "DEGRADED",
                reason=None if passed else "One or more mission acceptance criteria failed.",
            )
        elif self.measurement_count > 0:
            validity = build_validity(is_valid=True, state="VALID_TRACKING")
        else:
            validity = build_validity(
                is_valid=False,
                state="WAITING_FOR_TARGET",
                reason="Mission evaluator has not observed target measurements.",
            )
        return {
            **contract_envelope(
                frame_id=self.frame_id,
                provenance=self.provenance,
                timestamps=build_timestamps(
                    source_time_s=self.start_s,
                    receipt_time_s=now,
                    processing_time_s=now,
                    publication_time_s=now,
                ),
                validity=validity,
            ),
            "system": "GHOST GPS-denied occlusion-aware target tracking and prediction software demo",
            "elapsed_s": self.elapsed_s,
            "visible": self.visible,
            "visibility_reason": self.visibility_reason,
            "mission_complete": self.mission_complete,
            "target_finished": self.target_finished,
            "obstacle_occlusion_count": self.obstacle_occlusion_count,
            "reacquisition_count": self.reacquisition_count,
            "occlusion_durations_s": self.occlusion_durations_s,
            "longest_obstacle_occlusion_s": max(self.occlusion_durations_s, default=0.0),
            "imm_outputs_during_obstacle_occlusion": self.imm_outputs_during_obstacle_occlusion,
            "mh_outputs_during_obstacle_occlusion": self.mh_outputs_during_obstacle_occlusion,
            "imm_total_outputs": self.imm_total_outputs,
            "mh_total_outputs": self.mh_total_outputs,
            "measurement_count": self.measurement_count,
            "observer_distance_traveled_m": self.observer_distance_traveled_m,
            "observer_update_count": self.observer_update_count,
            "navigation_command_count": self.navigation_command_count,
            "hidden_vantage_command_count": self.hidden_vantage_command_count,
            "navigation_safety_intervention_count": self.navigation_safety_intervention_count,
            "max_commanded_speed_mps": self.max_commanded_speed_mps,
            "final_target_observer_separation_m": (
                math.hypot(self.latest_truth[0] - self.latest_observer[0], self.latest_truth[1] - self.latest_observer[1])
                if self.latest_truth is not None and self.latest_observer is not None
                else None
            ),
            "collision_count": self.collision_count,
            "out_of_bounds_count": self.out_of_bounds_count,
            "errors_m": {
                "imm_rms_all": self.rms("imm_all"),
                "mh_rms_all": self.rms("mh_all"),
                "imm_rms_hidden": self.rms("imm_hidden"),
                "mh_rms_hidden": self.rms("mh_hidden"),
                "imm_max_all": self.max_errors["imm_all"],
                "mh_max_all": self.max_errors["mh_all"],
                "imm_max_hidden": self.max_errors["imm_hidden"],
                "mh_max_hidden": self.max_errors["mh_hidden"],
            },
            "acceptance": acceptance,
            "passed": passed,
            "claim_boundary": (
                "Deterministic local-frame software simulation with camera LOS gating. "
                "It demonstrates tracking, prediction, navigation, and reacquisition logic; "
                "it does not claim GPS-denied self-localization or real autonomous flight."
            ),
        }

    def tick(self) -> None:
        result = self.result()
        self.status_pub.publish(String(data=json.dumps(result, separators=(",", ":"))))
        now = self.now_s()
        if self.metrics_path and now - self.last_write_s >= 1.0:
            self.last_write_s = now
            self.write_result(result)

    def write_result(self, result: dict[str, object]) -> None:
        path = Path(self.metrics_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)

    def finalize(self) -> None:
        self.finalized = True
        result = self.result()
        if self.metrics_path:
            self.write_result(result)
        verdict = "PASS" if bool(result["passed"]) else "FAIL"
        self.get_logger().info(
            f"GHOST mission evaluation {verdict}: occlusions={self.obstacle_occlusion_count} "
            f"reacquisitions={self.reacquisition_count} collisions={self.collision_count}"
        )

    def destroy_node(self) -> bool:
        if self.hidden_obstacle_active and self.hidden_start_elapsed_s is not None:
            duration = max(0.0, self.elapsed_s - self.hidden_start_elapsed_s)
            if duration >= self.minimum_occlusion_s:
                self.occlusion_durations_s.append(duration)
        if self.metrics_path:
            self.write_result(self.result())
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = GhostMissionEvaluator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
