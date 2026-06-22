import csv
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node


class EvidenceLogger(Node):
    """Log GHOST sim measurements, truth, and tracker output to CSV."""

    def __init__(self):
        super().__init__("ghost_evidence_logger")

        self.declare_parameter("out", str(Path.home() / "ghost_logs" / "sim_tracking.csv"))
        self.out_path = Path(str(self.get_parameter("out").value)).expanduser()
        self.out_path.parent.mkdir(parents=True, exist_ok=True)

        self.latest_meas = None
        self.latest_truth = None
        self.latest_odom = None

        self.file = self.out_path.open("w", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow(
            [
                "time_s",
                "meas_x_m",
                "meas_y_m",
                "truth_x_m",
                "truth_y_m",
                "est_x_m",
                "est_y_m",
                "est_vx_mps",
                "est_vy_mps",
                "p_xx",
                "p_yy",
            ]
        )

        self.create_subscription(
            PoseWithCovarianceStamped,
            "/ghost/vision/target_pose",
            self.on_measurement,
            20,
        )
        self.create_subscription(
            PoseWithCovarianceStamped,
            "/ghost/sim/target_truth",
            self.on_truth,
            20,
        )
        self.create_subscription(Odometry, "/ghost/tracker/target_odom", self.on_odom, 20)
        self.timer = self.create_timer(0.1, self.flush_row)

        self.get_logger().info(f"Logging sim evidence to {self.out_path}")

    def stamp_to_sec(self, stamp) -> float:
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    def on_measurement(self, msg: PoseWithCovarianceStamped) -> None:
        self.latest_meas = msg

    def on_truth(self, msg: PoseWithCovarianceStamped) -> None:
        self.latest_truth = msg

    def on_odom(self, msg: Odometry) -> None:
        self.latest_odom = msg

    @staticmethod
    def pose_xy(msg):
        if msg is None:
            return "", ""
        return msg.pose.pose.position.x, msg.pose.pose.position.y

    def flush_row(self) -> None:
        if self.latest_odom is None:
            return

        stamp = self.latest_odom.header.stamp
        meas_x, meas_y = self.pose_xy(self.latest_meas)
        truth_x, truth_y = self.pose_xy(self.latest_truth)
        odom = self.latest_odom

        self.writer.writerow(
            [
                self.stamp_to_sec(stamp),
                meas_x,
                meas_y,
                truth_x,
                truth_y,
                odom.pose.pose.position.x,
                odom.pose.pose.position.y,
                odom.twist.twist.linear.x,
                odom.twist.twist.linear.y,
                odom.pose.covariance[0],
                odom.pose.covariance[7],
            ]
        )
        self.file.flush()

    def destroy_node(self):
        try:
            self.file.close()
        finally:
            super().destroy_node()


def main():
    rclpy.init()
    node = EvidenceLogger()
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
