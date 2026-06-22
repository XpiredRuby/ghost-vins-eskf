import math
import random

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from rclpy.node import Node
from visualization_msgs.msg import Marker


class SyntheticMeasurements(Node):
    """Publish camera-like target position measurements with occlusions."""

    def __init__(self):
        super().__init__("ghost_synthetic_measurements")

        self.declare_parameter("rate_hz", 20.0)
        self.declare_parameter("radius_m", 1.25)
        self.declare_parameter("speed_rad_s", 0.45)
        self.declare_parameter("noise_std_m", 0.025)
        self.declare_parameter("dropout_start_s", 12.0)
        self.declare_parameter("dropout_duration_s", 3.0)
        self.declare_parameter("frame_id", "ghost_floor")

        self.rate_hz = float(self.get_parameter("rate_hz").value)
        self.radius_m = float(self.get_parameter("radius_m").value)
        self.speed_rad_s = float(self.get_parameter("speed_rad_s").value)
        self.noise_std_m = float(self.get_parameter("noise_std_m").value)
        self.dropout_start_s = float(self.get_parameter("dropout_start_s").value)
        self.dropout_duration_s = float(self.get_parameter("dropout_duration_s").value)
        self.frame_id = str(self.get_parameter("frame_id").value)

        self.measurement_pub = self.create_publisher(
            PoseWithCovarianceStamped,
            "/ghost/vision/target_pose",
            10,
        )
        self.truth_pub = self.create_publisher(
            PoseWithCovarianceStamped,
            "/ghost/sim/target_truth",
            10,
        )
        self.marker_pub = self.create_publisher(Marker, "/ghost/sim/target_marker", 10)

        self.t0 = self.get_clock().now()
        self.timer = self.create_timer(1.0 / self.rate_hz, self.tick)

        self.get_logger().info(
            "Publishing synthetic target measurements on /ghost/vision/target_pose"
        )

    def elapsed_s(self) -> float:
        return (self.get_clock().now() - self.t0).nanoseconds * 1e-9

    def target_state(self, t: float) -> tuple[float, float, float, float]:
        # Smooth oval trajectory in the floor frame.
        x = self.radius_m * math.cos(self.speed_rad_s * t)
        y = 0.65 * self.radius_m * math.sin(self.speed_rad_s * t)
        vx = -self.radius_m * self.speed_rad_s * math.sin(self.speed_rad_s * t)
        vy = 0.65 * self.radius_m * self.speed_rad_s * math.cos(self.speed_rad_s * t)
        return x, y, vx, vy

    def in_dropout(self, t: float) -> bool:
        if self.dropout_duration_s <= 0.0:
            return False
        period = self.dropout_start_s + self.dropout_duration_s + 8.0
        phase = t % period
        return self.dropout_start_s <= phase < self.dropout_start_s + self.dropout_duration_s

    def make_pose_msg(self, x: float, y: float, stamp) -> PoseWithCovarianceStamped:
        msg = PoseWithCovarianceStamped()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.pose.pose.position.x = x
        msg.pose.pose.position.y = y
        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation.w = 1.0

        var = self.noise_std_m * self.noise_std_m
        msg.pose.covariance[0] = var
        msg.pose.covariance[7] = var
        msg.pose.covariance[14] = 0.01
        msg.pose.covariance[21] = 999.0
        msg.pose.covariance[28] = 999.0
        msg.pose.covariance[35] = 999.0
        return msg

    def publish_marker(self, x: float, y: float, stamp) -> None:
        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = self.frame_id
        marker.ns = "ghost_truth"
        marker.id = 0
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        marker.pose.position.x = x
        marker.pose.position.y = y
        marker.pose.position.z = 0.05
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.12
        marker.scale.y = 0.12
        marker.scale.z = 0.12
        marker.color.r = 0.0
        marker.color.g = 0.8
        marker.color.b = 1.0
        marker.color.a = 1.0
        self.marker_pub.publish(marker)

    def tick(self) -> None:
        stamp = self.get_clock().now().to_msg()
        t = self.elapsed_s()
        x, y, _, _ = self.target_state(t)

        truth = self.make_pose_msg(x, y, stamp)
        truth.pose.covariance[0] = 0.0
        truth.pose.covariance[7] = 0.0
        self.truth_pub.publish(truth)
        self.publish_marker(x, y, stamp)

        if self.in_dropout(t):
            return

        noisy_x = x + random.gauss(0.0, self.noise_std_m)
        noisy_y = y + random.gauss(0.0, self.noise_std_m)
        self.measurement_pub.publish(self.make_pose_msg(noisy_x, noisy_y, stamp))


def main():
    rclpy.init()
    node = SyntheticMeasurements()
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
