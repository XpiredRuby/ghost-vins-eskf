import math

import numpy as np
import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from visualization_msgs.msg import Marker


class CvTracker(Node):
    """2D constant-velocity Kalman tracker for GHOST target measurements."""

    def __init__(self):
        super().__init__("ghost_cv_tracker")

        self.declare_parameter("frame_id", "ghost_floor")
        self.declare_parameter("process_accel_std_mps2", 0.8)
        self.declare_parameter("default_measurement_std_m", 0.05)
        self.declare_parameter("stale_timeout_s", 0.5)
        self.declare_parameter("gate_chi2_95_2d", 5.991)

        self.frame_id = str(self.get_parameter("frame_id").value)
        self.process_accel_std = float(self.get_parameter("process_accel_std_mps2").value)
        self.default_measurement_std = float(self.get_parameter("default_measurement_std_m").value)
        self.stale_timeout_s = float(self.get_parameter("stale_timeout_s").value)
        self.gate_chi2 = float(self.get_parameter("gate_chi2_95_2d").value)

        self.x = np.zeros((4, 1), dtype=float)  # [x, y, vx, vy]
        self.P = np.eye(4, dtype=float) * 1e3
        self.initialized = False
        self.last_time = None
        self.last_meas_time = None
        self.last_nis = math.nan
        self.last_update_accepted = False

        self.sub = self.create_subscription(
            PoseWithCovarianceStamped,
            "/ghost/vision/target_pose",
            self.on_measurement,
            20,
        )
        self.odom_pub = self.create_publisher(Odometry, "/ghost/tracker/target_odom", 10)
        self.marker_pub = self.create_publisher(Marker, "/ghost/tracker/target_marker", 10)
        self.timer = self.create_timer(0.05, self.publish_prediction)

        self.get_logger().info("CV tracker listening on /ghost/vision/target_pose")

    def stamp_to_sec(self, stamp) -> float:
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    def now_sec(self) -> float:
        now = self.get_clock().now().to_msg()
        return self.stamp_to_sec(now)

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        dt = min(dt, 0.5)
        F = np.array(
            [
                [1.0, 0.0, dt, 0.0],
                [0.0, 1.0, 0.0, dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        q = self.process_accel_std * self.process_accel_std
        Q = q * np.array(
            [
                [dt**4 / 4.0, 0.0, dt**3 / 2.0, 0.0],
                [0.0, dt**4 / 4.0, 0.0, dt**3 / 2.0],
                [dt**3 / 2.0, 0.0, dt**2, 0.0],
                [0.0, dt**3 / 2.0, 0.0, dt**2],
            ]
        )
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def measurement_covariance(self, msg: PoseWithCovarianceStamped) -> np.ndarray:
        rx = float(msg.pose.covariance[0])
        ry = float(msg.pose.covariance[7])
        fallback = self.default_measurement_std * self.default_measurement_std
        if rx <= 0.0 or not math.isfinite(rx):
            rx = fallback
        if ry <= 0.0 or not math.isfinite(ry):
            ry = fallback
        return np.diag([rx, ry])

    def on_measurement(self, msg: PoseWithCovarianceStamped) -> None:
        t = self.stamp_to_sec(msg.header.stamp)
        z = np.array([[msg.pose.pose.position.x], [msg.pose.pose.position.y]], dtype=float)

        if not self.initialized:
            self.x[:, :] = 0.0
            self.x[0, 0] = z[0, 0]
            self.x[1, 0] = z[1, 0]
            self.P = np.diag([0.05, 0.05, 1.0, 1.0])
            self.initialized = True
            self.last_time = t
            self.last_meas_time = t
            self.last_nis = 0.0
            self.last_update_accepted = True
            return

        dt = t - self.last_time if self.last_time is not None else 0.0
        self.predict(dt)
        self.last_time = t

        H = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        R = self.measurement_covariance(msg)
        innovation = z - H @ self.x
        S = H @ self.P @ H.T + R

        try:
            nis = float(innovation.T @ np.linalg.inv(S) @ innovation)
        except np.linalg.LinAlgError:
            self.get_logger().warn("Skipping update: singular innovation covariance")
            return

        self.last_nis = nis
        if nis > self.gate_chi2:
            self.last_update_accepted = False
            self.get_logger().warn(f"Rejected measurement by NIS gate: {nis:.2f}")
            return

        K = self.P @ H.T @ np.linalg.inv(S)
        I = np.eye(4)
        self.x = self.x + K @ innovation
        self.P = (I - K @ H) @ self.P @ (I - K @ H).T + K @ R @ K.T
        self.last_meas_time = t
        self.last_update_accepted = True

    def make_odom(self, stamp) -> Odometry:
        msg = Odometry()
        msg.header.stamp = stamp
        msg.header.frame_id = self.frame_id
        msg.child_frame_id = "ghost_target"
        msg.pose.pose.position.x = float(self.x[0, 0])
        msg.pose.pose.position.y = float(self.x[1, 0])
        msg.pose.pose.position.z = 0.0
        msg.pose.pose.orientation.w = 1.0
        msg.twist.twist.linear.x = float(self.x[2, 0])
        msg.twist.twist.linear.y = float(self.x[3, 0])

        msg.pose.covariance[0] = float(self.P[0, 0])
        msg.pose.covariance[7] = float(self.P[1, 1])
        msg.pose.covariance[14] = 0.01
        msg.twist.covariance[0] = float(self.P[2, 2])
        msg.twist.covariance[7] = float(self.P[3, 3])
        return msg

    def publish_marker(self, stamp, stale: bool) -> None:
        marker = Marker()
        marker.header.stamp = stamp
        marker.header.frame_id = self.frame_id
        marker.ns = "ghost_tracker"
        marker.id = 0
        marker.type = Marker.SPHERE
        marker.action = Marker.ADD
        marker.pose.position.x = float(self.x[0, 0])
        marker.pose.position.y = float(self.x[1, 0])
        marker.pose.position.z = 0.12
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.16
        marker.scale.y = 0.16
        marker.scale.z = 0.16
        marker.color.r = 1.0 if stale else 0.0
        marker.color.g = 0.5 if stale else 1.0
        marker.color.b = 0.0
        marker.color.a = 1.0
        self.marker_pub.publish(marker)

    def publish_prediction(self) -> None:
        if not self.initialized:
            return

        now_msg = self.get_clock().now().to_msg()
        now_sec = self.stamp_to_sec(now_msg)
        dt = now_sec - self.last_time if self.last_time is not None else 0.0
        self.predict(dt)
        self.last_time = now_sec

        stale = False
        if self.last_meas_time is not None:
            stale = (now_sec - self.last_meas_time) > self.stale_timeout_s

        self.odom_pub.publish(self.make_odom(now_msg))
        self.publish_marker(now_msg, stale)


def main():
    rclpy.init()
    node = CvTracker()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
