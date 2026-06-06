#include "guidance_node.hpp"

#include <chrono>
#include <cstdint>

namespace ghost {

// ── Constructor ───────────────────────────────────────────────────────────────

GuidanceNode::GuidanceNode(const rclcpp::NodeOptions& options)
    : rclcpp::Node("guidance_node", options)
{
    // ── Declare parameters ────────────────────────────────────────────────────
    this->declare_parameter("guidance.N",            3.0);
    this->declare_parameter("guidance.r_cutoff_m",   1.5);
    this->declare_parameter("guidance.K_sim",        1.0);
    this->declare_parameter("guidance.mavlink_host", std::string("127.0.0.1"));
    this->declare_parameter("guidance.mavlink_port", 14540);
    this->declare_parameter("guidance.rate_hz",      30.0);

    // ── Read parameters ───────────────────────────────────────────────────────
    const double N          = this->get_parameter("guidance.N").as_double();
    const double r_cutoff   = this->get_parameter("guidance.r_cutoff_m").as_double();
    const double K_sim      = this->get_parameter("guidance.K_sim").as_double();
    const std::string host  = this->get_parameter("guidance.mavlink_host").as_string();
    const int port          = static_cast<int>(this->get_parameter("guidance.mavlink_port").as_int());
    const double rate_hz    = this->get_parameter("guidance.rate_hz").as_double();

    // ── Construct guidance objects ────────────────────────────────────────────
    pronav_ = ProNav(N, r_cutoff, K_sim);

    // MavlinkBridge opens the UDP socket in its constructor; throws on failure
    bridge_ = std::make_unique<MavlinkBridge>(host, static_cast<uint16_t>(port));

    RCLCPP_INFO(this->get_logger(),
        "GuidanceNode: N=%.1f, r_cutoff=%.2f m, K_sim=%.4f, "
        "MAVLink → %s:%d, %.0f Hz",
        N, r_cutoff, K_sim, host.c_str(), port, rate_hz);

    // ── Subscriptions ─────────────────────────────────────────────────────────
    const auto sensor_qos = rclcpp::SensorDataQoS();

    target_pose_sub_ = this->create_subscription<
        geometry_msgs::msg::PoseWithCovarianceStamped>(
        "/ghost/tracker/pose", sensor_qos,
        [this](const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr& msg) {
            targetPoseCallback(msg);
        });

    target_vel_sub_ = this->create_subscription<
        geometry_msgs::msg::TwistWithCovarianceStamped>(
        "/ghost/tracker/velocity", sensor_qos,
        [this](const geometry_msgs::msg::TwistWithCovarianceStamped::ConstSharedPtr& msg) {
            targetVelocityCallback(msg);
        });

    occluded_sub_ = this->create_subscription<std_msgs::msg::Bool>(
        "/ghost/tracker/occluded",
        rclcpp::QoS(1).reliable(),
        [this](const std_msgs::msg::Bool::ConstSharedPtr& msg) {
            occludedCallback(msg);
        });

    // /ghost/eskf/pose is the camera platform pose (static tripod).
    // Its NED position provides the "drone" origin for ProNav — the tripod
    // is treated as the interceptor platform until Gazebo drone position
    // is wired in during Phase 4.
    drone_pose_sub_ = this->create_subscription<
        geometry_msgs::msg::PoseWithCovarianceStamped>(
        "/ghost/eskf/pose", sensor_qos,
        [this](const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr& msg) {
            dronePoseCallback(msg);
        });

    // ── Publisher ─────────────────────────────────────────────────────────────
    accel_pub_ = this->create_publisher<geometry_msgs::msg::AccelStamped>(
        "/ghost/guidance/a_cmd", sensor_qos);

    // ── Guidance timer — 30 Hz ────────────────────────────────────────────────
    const auto period = std::chrono::duration<double>(1.0 / rate_hz);
    guidance_timer_ = this->create_wall_timer(
        std::chrono::duration_cast<std::chrono::nanoseconds>(period),
        [this]() { guidanceTimerCallback(); });
}

// ── Destructor ────────────────────────────────────────────────────────────────
// MavlinkBridge owns the UDP socket; its destructor closes it.
// unique_ptr destruction happens automatically here — explicit only for logging.

GuidanceNode::~GuidanceNode()
{
    // Send a zero command before shutdown so PX4 SITL exits OFFBOARD cleanly
    if (bridge_ && bridge_->isOpen()) {
        bridge_->send(Eigen::Vector3d::Zero(), 0);
    }
    RCLCPP_INFO(this->get_logger(), "GuidanceNode shut down — zero command sent.");
}

// ── Subscriber callbacks — store latest state snapshots ──────────────────────

void GuidanceNode::targetPoseCallback(
    const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr& msg)
{
    x_target_NED_ = {
        msg->pose.pose.position.x,
        msg->pose.pose.position.y,
        msg->pose.pose.position.z};
    target_pose_valid_ = true;
}

void GuidanceNode::targetVelocityCallback(
    const geometry_msgs::msg::TwistWithCovarianceStamped::ConstSharedPtr& msg)
{
    v_target_NED_ = {
        msg->twist.twist.linear.x,
        msg->twist.twist.linear.y,
        msg->twist.twist.linear.z};
}

void GuidanceNode::occludedCallback(const std_msgs::msg::Bool::ConstSharedPtr& msg)
{
    if (msg->data && !occluded_) {
        RCLCPP_WARN(this->get_logger(),
            "Target occluded — suspending ProNav, sending zero acceleration.");
        pronav_.reset();   // clear LOS rate history; stale delta avoids command spike on reacquisition
        occluded_ = true;
    } else if (!msg->data && occluded_) {
        RCLCPP_INFO(this->get_logger(),
            "Target reacquired — resuming ProNav.");
        occluded_ = false;
    }
}

void GuidanceNode::dronePoseCallback(
    const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr& msg)
{
    x_drone_NED_ = {
        msg->pose.pose.position.x,
        msg->pose.pose.position.y,
        msg->pose.pose.position.z};
    drone_pose_valid_ = true;
}

// ── guidanceTimerCallback — 30 Hz ────────────────────────────────────────────

void GuidanceNode::guidanceTimerCallback()
{
    const rclcpp::Time now = this->now();

    // ── Compute dt ────────────────────────────────────────────────────────────
    if (first_tick_) {
        first_tick_     = false;
        last_tick_time_ = now;
        return;
    }
    const double dt = (now - last_tick_time_).seconds();
    last_tick_time_ = now;

    if (dt <= 0.0 || dt > 0.5) { return; }  // guard against timer skew

    // ── Zero command path — occlusion or stale data ───────────────────────────
    Eigen::Vector3d a_cmd = Eigen::Vector3d::Zero();

    const bool data_ready = target_pose_valid_ && drone_pose_valid_;

    if (!occluded_ && data_ready) {
        // ── TPN ProNav ────────────────────────────────────────────────────────
        // GHOST_V10.md §ProNav:
        //   a_cmd = N · Omega × V_c
        //   Omega = (delta_x_rel × delta_x_rel_dot) / range²
        //   Terminal coast: range < r_cutoff → a_cmd = [0,0,0]
        //   K_sim applied to XY only — raw drone altitude for Z
        a_cmd = pronav_.compute(x_target_NED_, x_drone_NED_, dt);
    }

    // ── MAVLink send ──────────────────────────────────────────────────────────
    // TODO: swap SET_ATTITUDE_TARGET (msg ID 82) for SET_POSITION_TARGET_LOCAL_NED
    //       (msg ID 84, mask 0b0000110000111111) once PX4 firmware acceleration
    //       feedforward path is confirmed against the Gazebo SITL model.
    //       See src/mavlink_bridge/mavlink_bridge.hpp for the mapping rationale.
    if (bridge_ && bridge_->isOpen()) {
        const uint64_t timestamp_us = static_cast<uint64_t>(
            now.nanoseconds() / 1000ULL);
        bridge_->send(a_cmd, timestamp_us);
    }

    // ── Publish /ghost/guidance/a_cmd for logging and debug ──────────────────
    geometry_msgs::msg::AccelStamped accel_msg;
    accel_msg.header.stamp    = now;
    accel_msg.header.frame_id = "ned";
    accel_msg.accel.linear.x  = a_cmd.x();
    accel_msg.accel.linear.y  = a_cmd.y();
    accel_msg.accel.linear.z  = a_cmd.z();
    // Angular acceleration is not commanded by ProNav
    accel_msg.accel.angular.x = 0.0;
    accel_msg.accel.angular.y = 0.0;
    accel_msg.accel.angular.z = 0.0;
    accel_pub_->publish(accel_msg);

    // Throttled status log — 1 Hz to avoid spamming
    RCLCPP_DEBUG_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
        "ProNav: a_cmd=[%.3f, %.3f, %.3f] m/s², occluded=%s",
        a_cmd.x(), a_cmd.y(), a_cmd.z(), occluded_ ? "YES" : "no");
}

}  // namespace ghost

// ── main ──────────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);

    // SingleThreadedExecutor: all ProNav and MAVLink calls on one thread.
    // ProNav::compute() is not thread-safe; do not use MultiThreadedExecutor.
    rclcpp::spin(std::make_shared<ghost::GuidanceNode>());

    rclcpp::shutdown();
    return 0;
}
