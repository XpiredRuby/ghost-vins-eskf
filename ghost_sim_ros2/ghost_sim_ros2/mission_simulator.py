"""GPS-denied planar drone/robot observer mission simulator for GHOST.

The simulator owns a local mission frame, target truth, observer dynamics,
obstacle geometry, and a camera-like line-of-sight sensor.  It never publishes a
target measurement when range, field of view, or obstacle visibility fails.
"""

from __future__ import annotations

import json
import math
import random
from typing import Any

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped, Twist
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from std_msgs.msg import String
from visualization_msgs.msg import Marker, MarkerArray

from .ghost_world import (
    CameraModel,
    ObserverState,
    Vec2,
    WorldModel,
    camera_visibility,
    default_target_trajectory,
    wrap_angle,
)


class GhostMissionSimulator(Node):
    def __init__(self) -> None:
        super().__init__("ghost_mission_simulator")
        self.declare_parameter("rate_hz", 30.0)
        self.declare_parameter("mission_duration_s", 42.0)
        self.declare_parameter("random_seed", 20260712)
        self.declare_parameter("frame_id", "ghost_local")
        self.declare_parameter("target_speed_mps", 0.55)
        self.declare_parameter("measurement_std_m", 0.025)
        self.declare_parameter("camera_range_m", 8.0)
        self.declare_parameter("camera_fov_deg", 118.0)
        self.declare_parameter("observer_radius_m", 0.22)
        self.declare_parameter("observer_initial_x_m", -4.55)
        self.declare_parameter("observer_initial_y_m", -2.45)
        self.declare_parameter("observer_initial_yaw_rad", 0.55)
        self.declare_parameter("status_rate_hz", 10.0)

        self.rate_hz = float(self.get_parameter("rate_hz").value)
        self.mission_duration_s = float(self.get_parameter("mission_duration_s").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.measurement_std_m = float(self.get_parameter("measurement_std_m").value)
        self.observer_radius_m = float(self.get_parameter("observer_radius_m").value)
        self.camera = CameraModel(
            range_m=float(self.get_parameter("camera_range_m").value),
            fov_deg=float(self.get_parameter("camera_fov_deg").value),
        )
        self.rng = random.Random(int(self.get_parameter("random_seed").value))
        self.world = WorldModel()
        self.trajectory = default_target_trajectory(float(self.get_parameter("target_speed_mps").value))
        self.observer = ObserverState(
            position=Vec2(
                float(self.get_parameter("observer_initial_x_m").value),
                float(self.get_parameter("observer_initial_y_m").value),
            ),
            velocity=Vec2(0.0, 0.0),
            yaw=float(self.get_parameter("observer_initial_yaw_rad").value),
        )
        if not self.world.point_clear(self.observer.position, self.observer_radius_m):
            raise RuntimeError("observer initial position is not collision-free")

        self.latest_command = Twist()
        self.collision_count = 0
        self.out_of_bounds_count = 0
        self.measurement_count = 0
        self.visibility_transition_count = 0
        self.last_visible: bool | None = None
        self.last_tick_s = self.now_s()
        self.t0_s = self.last_tick_s
        self.target_trail: list[Vec2] = []
        self.observer_trail: list[Vec2] = []
        self.last_status_s = -math.inf
        self.last_world_s = -math.inf
        self.complete_latched = False

        transient_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        output_qos = QoSProfile(depth=10)
        self.measurement_pub = self.create_publisher(
            PoseWithCovarianceStamped, "/ghost/vision/target_pose", qos_profile_sensor_data
        )
        self.target_truth_pub = self.create_publisher(
            PoseWithCovarianceStamped, "/ghost/sim/target_truth", output_qos
        )
        self.observer_odom_pub = self.create_publisher(
            Odometry, "/ghost/sim/observer_odom", output_qos
        )
        self.visibility_pub = self.create_publisher(
            String, "/ghost/sim/visibility_json", output_qos
        )
        self.status_pub = self.create_publisher(String, "/ghost/sim/mission_status_json", output_qos)
        self.world_pub = self.create_publisher(String, "/ghost/sim/world_json", transient_qos)
        self.marker_pub = self.create_publisher(MarkerArray, "/ghost/sim/mission_markers", output_qos)
        self.command_sub = self.create_subscription(
            Twist, "/ghost/nav/cmd_vel", self.on_command, output_qos
        )
        self.timer = self.create_timer(1.0 / max(self.rate_hz, 1.0), self.tick)
        self.get_logger().info(
            "GHOST mission simulator active: local-frame camera sensing, obstacle LOS gating, "
            f"duration={self.mission_duration_s:.1f}s frame={self.frame_id}"
        )

    def now_s(self) -> float:
        return self.get_clock().now().nanoseconds * 1.0e-9

    def elapsed_s(self) -> float:
        return self.now_s() - self.t0_s

    def on_command(self, msg: Twist) -> None:
        self.latest_command = msg

    def integrate_observer(self, dt_s: float) -> None:
        vx = float(self.latest_command.linear.x)
        vy = float(self.latest_command.linear.y)
        yaw_rate = float(self.latest_command.angular.z)
        proposed = self.observer.position + Vec2(vx, vy) * dt_s
        if self.world.point_clear(proposed, self.observer_radius_m):
            self.observer.position = proposed
            self.observer.velocity = Vec2(vx, vy)
        else:
            if not self.world.inside_bounds(proposed, self.observer_radius_m):
                self.out_of_bounds_count += 1
            else:
                self.collision_count += 1
            self.observer.velocity = Vec2(0.0, 0.0)
        self.observer.yaw = wrap_angle(self.observer.yaw + yaw_rate * dt_s)

    def tick(self) -> None:
        now = self.now_s()
        dt_s = max(1.0e-3, min(0.10, now - self.last_tick_s))
        self.last_tick_s = now
        elapsed = now - self.t0_s
        self.integrate_observer(dt_s)
        target = self.trajectory.sample(elapsed)
        visibility = camera_visibility(
            self.world,
            self.observer.position,
            self.observer.yaw,
            target.position,
            self.camera,
        )
        if self.last_visible is None or visibility.visible != self.last_visible:
            self.visibility_transition_count += 1
        self.last_visible = visibility.visible

        stamp = self.get_clock().now().to_msg()
        self.target_truth_pub.publish(self.pose_message(target.position, stamp, zero_covariance=True))
        self.observer_odom_pub.publish(self.observer_message(stamp))
        if visibility.visible:
            noisy = Vec2(
                target.position.x + self.rng.gauss(0.0, self.measurement_std_m),
                target.position.y + self.rng.gauss(0.0, self.measurement_std_m),
            )
            self.measurement_pub.publish(self.pose_message(noisy, stamp, zero_covariance=False))
            self.measurement_count += 1

        self.append_trail(self.target_trail, target.position)
        self.append_trail(self.observer_trail, self.observer.position)
        mission_complete = elapsed >= self.mission_duration_s
        self.complete_latched = self.complete_latched or mission_complete
        if now - self.last_world_s >= 1.0:
            self.last_world_s = now
            self.world_pub.publish(String(data=json.dumps(self.world_payload(), separators=(",", ":"))))
        if now - self.last_status_s >= 1.0 / max(float(self.get_parameter("status_rate_hz").value), 1.0):
            self.last_status_s = now
            visibility_payload = self.visibility_payload(elapsed, target, visibility)
            self.visibility_pub.publish(String(data=json.dumps(visibility_payload, separators=(",", ":"))))
            status_payload = dict(visibility_payload)
            status_payload.update(
                {
                    "mission_complete": self.complete_latched,
                    "target_finished": target.finished,
                    "target_segment_index": target.segment_index,
                    "measurement_count": self.measurement_count,
                    "collision_count": self.collision_count,
                    "out_of_bounds_count": self.out_of_bounds_count,
                    "observer_velocity_mps": self.observer.velocity.as_list(),
                    "command_velocity_mps": [
                        float(self.latest_command.linear.x),
                        float(self.latest_command.linear.y),
                    ],
                    "command_yaw_rate_rps": float(self.latest_command.angular.z),
                }
            )
            self.status_pub.publish(String(data=json.dumps(status_payload, separators=(",", ":"))))
        self.marker_pub.publish(self.marker_array(stamp, target.position, visibility.visible))

    @staticmethod
    def append_trail(trail: list[Vec2], point: Vec2, max_points: int = 700) -> None:
        if not trail or trail[-1].distance(point) > 0.025:
            trail.append(point)
        if len(trail) > max_points:
            del trail[: len(trail) - max_points]

    def pose_message(self, position: Vec2, stamp: Any, zero_covariance: bool) -> PoseWithCovarianceStamped:
        msg = PoseWithCovarianceStamped()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.pose.pose.position.x = position.x
        msg.pose.pose.position.y = position.y
        msg.pose.pose.orientation.w = 1.0
        variance = 0.0 if zero_covariance else self.measurement_std_m**2
        msg.pose.covariance[0] = variance
        msg.pose.covariance[7] = variance
        msg.pose.covariance[14] = 1.0e-4
        msg.pose.covariance[21] = 999.0
        msg.pose.covariance[28] = 999.0
        msg.pose.covariance[35] = 999.0
        return msg

    def observer_message(self, stamp: Any) -> Odometry:
        msg = Odometry()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.child_frame_id = "ghost_observer"
        msg.pose.pose.position.x = self.observer.position.x
        msg.pose.pose.position.y = self.observer.position.y
        msg.pose.pose.orientation.z = math.sin(0.5 * self.observer.yaw)
        msg.pose.pose.orientation.w = math.cos(0.5 * self.observer.yaw)
        msg.twist.twist.linear.x = self.observer.velocity.x
        msg.twist.twist.linear.y = self.observer.velocity.y
        msg.twist.twist.angular.z = float(self.latest_command.angular.z)
        return msg

    def world_payload(self) -> dict[str, object]:
        payload = self.world.to_dict()
        payload.update(
            {
                "frame_id": self.frame_id,
                "camera_range_m": self.camera.range_m,
                "camera_fov_deg": self.camera.fov_deg,
                "observer_radius_m": self.observer_radius_m,
                "target_waypoints": [p.as_list() for p in self.trajectory.waypoints],
                "target_speed_mps": self.trajectory.speed_mps,
                "mission_duration_s": self.mission_duration_s,
                "claim_boundary": "Local-frame software simulation; no GPS target measurement and no real flight-control claim.",
            }
        )
        return payload

    def visibility_payload(self, elapsed: float, target: Any, visibility: Any) -> dict[str, object]:
        return {
            "elapsed_s": elapsed,
            "frame_id": self.frame_id,
            "visible": visibility.visible,
            "visibility_reason": visibility.reason,
            "blocking_obstacle": visibility.blocker,
            "range_m": visibility.distance_m,
            "bearing_error_rad": visibility.bearing_error_rad,
            "target_position_m": target.position.as_list(),
            "target_velocity_mps": target.velocity.as_list(),
            "observer_position_m": self.observer.position.as_list(),
            "observer_yaw_rad": self.observer.yaw,
        }

    def marker_array(self, stamp: Any, target: Vec2, visible: bool) -> MarkerArray:
        markers: list[Marker] = []
        for index, obstacle in enumerate(self.world.obstacles):
            marker = Marker()
            marker.header.stamp = stamp
            marker.header.frame_id = self.frame_id
            marker.ns = "ghost_obstacles"
            marker.id = index
            marker.type = Marker.CUBE
            marker.action = Marker.ADD
            marker.pose.position.x = 0.5 * (obstacle.xmin + obstacle.xmax)
            marker.pose.position.y = 0.5 * (obstacle.ymin + obstacle.ymax)
            marker.pose.position.z = 0.45
            marker.pose.orientation.w = 1.0
            marker.scale.x = obstacle.xmax - obstacle.xmin
            marker.scale.y = obstacle.ymax - obstacle.ymin
            marker.scale.z = 0.9
            marker.color.r = 0.35
            marker.color.g = 0.36
            marker.color.b = 0.42
            marker.color.a = 0.95
            markers.append(marker)
        markers.append(self.sphere_marker(stamp, 100, "target", target, 0.16, 0.0, 0.85, 1.0))
        observer_marker = Marker()
        observer_marker.header.stamp = stamp
        observer_marker.header.frame_id = self.frame_id
        observer_marker.ns = "observer"
        observer_marker.id = 101
        observer_marker.type = Marker.ARROW
        observer_marker.action = Marker.ADD
        observer_marker.pose.position.x = self.observer.position.x
        observer_marker.pose.position.y = self.observer.position.y
        observer_marker.pose.position.z = 0.12
        observer_marker.pose.orientation.z = math.sin(0.5 * self.observer.yaw)
        observer_marker.pose.orientation.w = math.cos(0.5 * self.observer.yaw)
        observer_marker.scale.x = 0.48
        observer_marker.scale.y = 0.20
        observer_marker.scale.z = 0.16
        observer_marker.color.r = 1.0
        observer_marker.color.g = 0.75
        observer_marker.color.b = 0.05
        observer_marker.color.a = 1.0
        markers.append(observer_marker)
        los = Marker()
        los.header.stamp = stamp
        los.header.frame_id = self.frame_id
        los.ns = "line_of_sight"
        los.id = 102
        los.type = Marker.LINE_STRIP
        los.action = Marker.ADD
        los.scale.x = 0.025
        los.color.r = 0.1 if visible else 1.0
        los.color.g = 0.9 if visible else 0.2
        los.color.b = 0.2
        los.color.a = 0.9
        from geometry_msgs.msg import Point

        for p in (self.observer.position, target):
            point = Point()
            point.x = p.x
            point.y = p.y
            point.z = 0.12
            los.points.append(point)
        markers.append(los)
        markers.extend(
            [
                self.trail_marker(stamp, 110, "target_trail", self.target_trail, 0.025, 0.0, 0.65, 1.0),
                self.trail_marker(stamp, 111, "observer_trail", self.observer_trail, 0.035, 1.0, 0.65, 0.0),
            ]
        )
        return MarkerArray(markers=markers)

    def sphere_marker(
        self, stamp: Any, marker_id: int, namespace: str, position: Vec2, size: float, r: float, g: float, b: float
    ) -> Marker:
        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = self.frame_id
        marker.ns = namespace
        marker.id = marker_id
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        marker.pose.position.x = position.x
        marker.pose.position.y = position.y
        marker.pose.position.z = 0.10
        marker.pose.orientation.w = 1.0
        marker.scale.x = size
        marker.scale.y = size
        marker.scale.z = size
        marker.color.r = r
        marker.color.g = g
        marker.color.b = b
        marker.color.a = 1.0
        return marker

    def trail_marker(
        self,
        stamp: Any,
        marker_id: int,
        namespace: str,
        trail: list[Vec2],
        width: float,
        r: float,
        g: float,
        b: float,
    ) -> Marker:
        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = self.frame_id
        marker.ns = namespace
        marker.id = marker_id
        marker.type = Marker.LINE_STRIP
        marker.action = Marker.ADD
        marker.scale.x = width
        marker.color.r = r
        marker.color.g = g
        marker.color.b = b
        marker.color.a = 0.85
        from geometry_msgs.msg import Point

        for p in trail:
            point = Point()
            point.x = p.x
            point.y = p.y
            point.z = 0.03
            marker.points.append(point)
        return marker


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = GhostMissionSimulator()
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
