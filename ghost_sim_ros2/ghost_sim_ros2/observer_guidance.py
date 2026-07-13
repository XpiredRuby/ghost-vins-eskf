"""Obstacle-aware observer guidance using GHOST tracker estimates."""

from __future__ import annotations

import json
import math
from typing import Any

import rclpy
from geometry_msgs.msg import Point, PoseStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from visualization_msgs.msg import Marker

from .ghost_world import (
    GuidanceController,
    GuidanceLimits,
    ObserverState,
    RectObstacle,
    Vec2,
    WorldModel,
)


class GhostObserverGuidance(Node):
    def __init__(self) -> None:
        super().__init__("ghost_observer_guidance")
        self.declare_parameter("tracker_source", "mh")
        self.declare_parameter("rate_hz", 20.0)
        self.declare_parameter("frame_id", "ghost_local")
        self.declare_parameter("max_speed_mps", 1.15)
        self.declare_parameter("max_accel_mps2", 1.4)
        self.declare_parameter("max_yaw_rate_rps", 1.5)
        self.declare_parameter("standoff_m", 2.2)
        self.declare_parameter("obstacle_clearance_m", 0.38)
        self.declare_parameter("goal_tolerance_m", 0.20)
        self.declare_parameter("grid_resolution_m", 0.25)
        self.declare_parameter("estimate_timeout_s", 1.0)
        self.declare_parameter("initial_observation_hold_s", 8.0)

        self.tracker_source = str(self.get_parameter("tracker_source").value).strip().lower()
        if self.tracker_source not in {"mh", "imm"}:
            raise ValueError("tracker_source must be 'mh' or 'imm'")
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.rate_hz = float(self.get_parameter("rate_hz").value)
        self.estimate_timeout_s = float(self.get_parameter("estimate_timeout_s").value)
        self.initial_observation_hold_s = float(self.get_parameter("initial_observation_hold_s").value)
        self.start_s = self.now_s()
        self.world = WorldModel()
        self.limits = GuidanceLimits(
            max_speed_mps=float(self.get_parameter("max_speed_mps").value),
            max_accel_mps2=float(self.get_parameter("max_accel_mps2").value),
            max_yaw_rate_rps=float(self.get_parameter("max_yaw_rate_rps").value),
            standoff_m=float(self.get_parameter("standoff_m").value),
            obstacle_clearance_m=float(self.get_parameter("obstacle_clearance_m").value),
            goal_tolerance_m=float(self.get_parameter("goal_tolerance_m").value),
            grid_resolution_m=float(self.get_parameter("grid_resolution_m").value),
        )
        self.controller = GuidanceController(self.world, self.limits)
        self.observer: ObserverState | None = None
        self.target_position: Vec2 | None = None
        self.target_velocity = Vec2(0.0, 0.0)
        self.target_update_s = -math.inf
        self.visible = False
        self.visibility_received = False
        self.visibility_reason = "WAITING"
        self.blocking_obstacle_name: str | None = None
        self.hidden_start_s: float | None = None
        self.last_visible_target_position: Vec2 | None = None
        self.last_visible_target_velocity = Vec2(0.0, 0.0)
        self.mission_complete = False
        self.last_tick_s = self.now_s()
        self.last_output: Any = None

        qos = QoSProfile(depth=10)
        transient_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        selected_topic = (
            "/ghost/tracker_mh/target_odom"
            if self.tracker_source == "mh"
            else "/ghost/tracker_imm/target_odom"
        )
        self.create_subscription(Odometry, selected_topic, self.on_target_estimate, qos)
        self.create_subscription(Odometry, "/ghost/sim/observer_odom", self.on_observer, qos)
        self.create_subscription(String, "/ghost/sim/visibility_json", self.on_visibility, qos)
        self.create_subscription(String, "/ghost/sim/mission_status_json", self.on_mission_status, qos)
        self.create_subscription(String, "/ghost/sim/world_json", self.on_world, transient_qos)
        self.command_pub = self.create_publisher(Twist, "/ghost/nav/cmd_vel", qos)
        self.goal_pub = self.create_publisher(PoseStamped, "/ghost/nav/goal", qos)
        self.status_pub = self.create_publisher(String, "/ghost/nav/status_json", qos)
        self.path_pub = self.create_publisher(Marker, "/ghost/nav/path_marker", qos)
        self.timer = self.create_timer(1.0 / max(self.rate_hz, 1.0), self.tick)
        self.get_logger().info(
            f"GHOST observer guidance active using tracker={self.tracker_source}; "
            "obstacle-aware A* vantage reposition enabled"
        )

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1.0e-9

    def on_observer(self, msg: Odometry) -> None:
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.observer = ObserverState(
            position=Vec2(float(msg.pose.pose.position.x), float(msg.pose.pose.position.y)),
            velocity=Vec2(float(msg.twist.twist.linear.x), float(msg.twist.twist.linear.y)),
            yaw=yaw,
        )

    def on_target_estimate(self, msg: Odometry) -> None:
        self.target_position = Vec2(float(msg.pose.pose.position.x), float(msg.pose.pose.position.y))
        self.target_velocity = Vec2(float(msg.twist.twist.linear.x), float(msg.twist.twist.linear.y))
        self.target_update_s = self.now_s()
        if self.visible:
            self.last_visible_target_position = self.target_position
            speed = self.target_velocity.norm()
            if speed > 1.2:
                self.last_visible_target_velocity = self.target_velocity.normalized() * 1.2
            else:
                self.last_visible_target_velocity = self.target_velocity

    def on_visibility(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        previous_visible = self.visible if self.visibility_received else None
        new_visible = bool(payload.get("visible", False))
        self.visible = new_visible
        self.visibility_received = True
        self.visibility_reason = str(payload.get("visibility_reason", "UNKNOWN"))
        blocker = payload.get("blocking_obstacle")
        if blocker:
            self.blocking_obstacle_name = str(blocker)
        if previous_visible is True and not new_visible:
            self.hidden_start_s = self.now_s()
        elif new_visible:
            self.hidden_start_s = None
            self.blocking_obstacle_name = None

    def on_mission_status(self, msg: String) -> None:
        try:
            self.mission_complete = bool(json.loads(msg.data).get("mission_complete", False))
        except json.JSONDecodeError:
            return

    def on_world(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            bounds = payload["bounds"]
            obstacles = tuple(
                RectObstacle(
                    str(row["name"]),
                    float(row["xmin"]),
                    float(row["xmax"]),
                    float(row["ymin"]),
                    float(row["ymax"]),
                )
                for row in payload["obstacles"]
            )
            self.world = WorldModel(
                xmin=float(bounds[0]),
                xmax=float(bounds[1]),
                ymin=float(bounds[2]),
                ymax=float(bounds[3]),
                obstacles=obstacles,
            )
            self.controller = GuidanceController(self.world, self.limits)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.get_logger().warning("Ignoring malformed world JSON")

    def tick(self) -> None:
        now = self.now_s()
        dt_s = max(1.0e-3, min(0.15, now - self.last_tick_s))
        self.last_tick_s = now
        if self.mission_complete:
            self.publish_stop("MISSION_COMPLETE")
            return
        if not self.visibility_received:
            self.publish_stop("WAITING_FOR_VISIBILITY")
            return
        if now - self.start_s < self.initial_observation_hold_s and self.visible:
            self.publish_stop("INITIAL_OBSERVATION_HOLD")
            return
        if self.observer is None or self.target_position is None:
            self.publish_stop("WAITING_FOR_STATE")
            return
        estimate_age_s = now - self.target_update_s
        if estimate_age_s > self.estimate_timeout_s:
            self.publish_stop("TRACKER_ESTIMATE_STALE")
            return
        guidance_target = self.target_position
        guidance_velocity = self.target_velocity
        hidden_age_s = 0.0
        if not self.visible and self.last_visible_target_position is not None:
            if self.hidden_start_s is not None:
                hidden_age_s = max(0.0, now - self.hidden_start_s)
            prediction_horizon_s = min(hidden_age_s, 6.0)
            guidance_target = self.last_visible_target_position + self.last_visible_target_velocity * prediction_horizon_s
            guidance_target = Vec2(
                max(self.world.xmin + 0.25, min(self.world.xmax - 0.25, guidance_target.x)),
                max(self.world.ymin + 0.25, min(self.world.ymax - 0.25, guidance_target.y)),
            )
            guidance_velocity = self.last_visible_target_velocity
        output = self.controller.compute(
            self.observer,
            guidance_target,
            guidance_velocity,
            self.visible,
            dt_s,
            self.blocking_obstacle_name,
        )
        # Final safety gate: never command a one-step move into inflated geometry.
        predicted = self.observer.position + output.velocity_command * dt_s
        command_velocity = output.velocity_command
        safety_intervened = False
        if not self.world.point_clear(predicted, self.limits.obstacle_clearance_m * 0.70):
            command_velocity = Vec2(0.0, 0.0)
            safety_intervened = True
        command = Twist()
        command.linear.x = command_velocity.x
        command.linear.y = command_velocity.y
        command.angular.z = output.yaw_rate_command
        self.command_pub.publish(command)
        self.publish_goal(output.final_goal)
        self.publish_path(output.path)
        payload = {
            "stamp_s": now,
            "tracker_source": self.tracker_source,
            "mode": output.mode,
            "visible": self.visible,
            "visibility_reason": self.visibility_reason,
            "estimate_age_s": estimate_age_s,
            "observer_position_m": self.observer.position.as_list(),
            "target_estimate_m": self.target_position.as_list(),
            "guidance_target_m": guidance_target.as_list(),
            "hidden_age_s": hidden_age_s,
            "blocking_obstacle": self.blocking_obstacle_name,
            "target_velocity_mps": self.target_velocity.as_list(),
            "navigation_goal_m": output.final_goal.as_list(),
            "active_waypoint_m": output.active_waypoint.as_list(),
            "command_velocity_mps": command_velocity.as_list(),
            "command_yaw_rate_rps": output.yaw_rate_command,
            "planned_path_m": [point.as_list() for point in output.path],
            "safety_intervened": safety_intervened,
        }
        self.status_pub.publish(String(data=json.dumps(payload, separators=(",", ":"))))
        self.last_output = output

    def publish_stop(self, reason: str) -> None:
        self.command_pub.publish(Twist())
        self.status_pub.publish(
            String(
                data=json.dumps(
                    {
                        "stamp_s": self.now_s(),
                        "tracker_source": self.tracker_source,
                        "mode": reason,
                        "visible": self.visible,
                        "visibility_reason": self.visibility_reason,
                        "command_velocity_mps": [0.0, 0.0],
                        "command_yaw_rate_rps": 0.0,
                    },
                    separators=(",", ":"),
                )
            )
        )

    def publish_goal(self, goal: Vec2) -> None:
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.pose.position.x = goal.x
        msg.pose.position.y = goal.y
        msg.pose.orientation.w = 1.0
        self.goal_pub.publish(msg)

    def publish_path(self, path: tuple[Vec2, ...]) -> None:
        marker = Marker()
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.header.frame_id = self.frame_id
        marker.ns = "ghost_navigation_path"
        marker.id = 0
        marker.type = Marker.LINE_STRIP
        marker.action = Marker.ADD
        marker.scale.x = 0.045
        marker.color.r = 1.0
        marker.color.g = 0.15
        marker.color.b = 0.8
        marker.color.a = 0.9
        for value in path:
            point = Point()
            point.x = value.x
            point.y = value.y
            point.z = 0.08
            marker.points.append(point)
        self.path_pub.publish(marker)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = GhostObserverGuidance()
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
