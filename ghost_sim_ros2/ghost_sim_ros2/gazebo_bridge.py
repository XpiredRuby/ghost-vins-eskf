import rclpy
from geometry_msgs.msg import PoseStamped, TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node


class GazeboBridge(Node):
    """Convert tracker odometry into simple sim-facing pose and twist topics."""

    def __init__(self):
        super().__init__("ghost_gazebo_bridge")

        self.declare_parameter("input_odom", "/ghost/tracker/target_odom")
        self.declare_parameter("pose_topic", "/ghost/gazebo/target_pose")
        self.declare_parameter("twist_topic", "/ghost/gazebo/target_twist")
        self.declare_parameter("px4_setpoint_topic", "/ghost/px4/target_setpoint")

        input_odom = str(self.get_parameter("input_odom").value)
        pose_topic = str(self.get_parameter("pose_topic").value)
        twist_topic = str(self.get_parameter("twist_topic").value)
        px4_setpoint_topic = str(self.get_parameter("px4_setpoint_topic").value)

        self.pose_pub = self.create_publisher(PoseStamped, pose_topic, 10)
        self.twist_pub = self.create_publisher(TwistStamped, twist_topic, 10)
        self.px4_setpoint_pub = self.create_publisher(PoseStamped, px4_setpoint_topic, 10)
        self.sub = self.create_subscription(Odometry, input_odom, self.on_odom, 20)

        self.get_logger().info(
            f"Bridge listening on {input_odom}; publishing {pose_topic}, "
            f"{twist_topic}, {px4_setpoint_topic}"
        )

    def on_odom(self, odom: Odometry) -> None:
        pose = PoseStamped()
        pose.header = odom.header
        pose.pose = odom.pose.pose

        twist = TwistStamped()
        twist.header = odom.header
        twist.twist = odom.twist.twist

        # This is intentionally a target-state setpoint topic, not a PX4 command.
        # Actual PX4 offboard control should be implemented as a separate safety-gated node.
        px4_target = PoseStamped()
        px4_target.header = odom.header
        px4_target.pose = odom.pose.pose

        self.pose_pub.publish(pose)
        self.twist_pub.publish(twist)
        self.px4_setpoint_pub.publish(px4_target)


def main():
    rclpy.init()
    node = GazeboBridge()
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
