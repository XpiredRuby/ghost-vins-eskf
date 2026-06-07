#include "guidance_node.hpp"

#include <chrono>
#include <cstdint>

namespace ghost {

// ── Constructor ───────────────────────────────────────────────────────────────

GuidanceNode::GuidanceNode(const rclcpp::NodeOptions& options)
    : rclcpp::Node("guidance_node", options)
{
    // ── Declare parameters — mirror config/guidance.yaml key hierarchy ────────
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
    rate_hz_                = this->get_parameter("guidance.rate_hz").as_double();

    // ── Construct guidance objects ────────────────────────────────────────────
    pronav_ = ProNav(N, r_cutoff, K_sim);

    // MavlinkBridge opens the UDP socket in its constructor; throws on failure.
    // The exception is caught in main() — do not suppress it here.
    bridge_ = std::make_unique<MavlinkBridge>(host, static_cast<uint16_t>(port));

    RCLCPP_INFO(this->get_logger(),
        "GuidanceNode: N=%.1f, r_cutoff=%.2f m, K_sim=%.4f, "
        "MAVLink → %s:%d, %.0f Hz",
        N, r_cutoff, K_sim, host.c_str(), port, rate_hz_);

    // ── Subscriptions ─────────────────────────────────────────────────────────
    const auto sensor_qos = rclcpp::SensorDataQoS();

    target_pose_sub_ = this->create_subscription<
        geometry_msgs::msg::PoseWithCovarianceStamped>(
        "/ghost/tracker/pose", sensor_qos,
        [this](const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr& msg) {
            targetPoseCallback(msg);
        });

    // NOTE: /ghost/tracker/velocity is intentionally NOT subscribed here.
    // TPN ProNav computes its closing velocity V_c by finite-differencing
    // the received NED positions internally (V_c = -delta_x_rel_dot).
    // The Kalman-filtered tracker velocity is not required for TPN.
    // If a future guidance law (BiasPN, APN) needs tracker velocity, add the
    // subscription back and extend ProNav::compute() accordingly.

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

    // ── Guidance timer — rate_hz_ Hz ──────────────────────────────────────────
    const auto period = std::chrono::duration<double>(1.0 / rate_hz_);
    guidance_timer_ = this->create_wall_timer(
        std::chrono::duration_cast<std::chrono::nanoseconds>(period),
        [this]() { guidanceTimerCallback(); });
}

// ── Destructor ────────────────────────────────────────────────────────────────
// MavlinkBridge owns the UDP socket; its destructor closes it.
// Send a zero command before that so PX4 SITL has a chance to exit OFFBOARD
// cleanly. Use steady_clock so time_boot_ms is a valid monotonic value that
// PX4 will not immediately discard as stale (timestamp=0 would appear ~boot
// seconds old, exceeding the 500ms stale threshold and causing PX4 to drop
// the packet before processing the zero command).

GuidanceNode::~GuidanceNode()
{
    if (bridge_ && bridge_->isOpen()) {
        const uint64_t ts_us = static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now().time_since_epoch()).count());
        bridge_->send(Eigen::Vector3d::Zero(), ts_us);
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

// ── guidanceTimerCallback — rate_hz_ Hz ──────────────────────────────────────

void GuidanceNode::guidanceTimerCallback()
{
    // ── Compute dt using steady_clock — monotonic, no epoch overflow ──────────
    // Use std::chrono::steady_clock rather than this->now() (CLOCK_REALTIME).
    // this->now().nanoseconds() is seconds since Unix epoch 1970; dividing to
    // milliseconds and casting to uint32_t overflows at ~49 days post-epoch,
    // producing a wrapped time_boot_ms that PX4 cannot interpret correctly.
    // steady_clock gives microseconds from process start — a valid time_boot_ms.
    const auto now_steady = std::chrono::steady_clock::now();

    if (first_tick_) {
        first_tick_     = false;
        last_tick_time_ = now_steady;
        return;
    }

    const double dt = std::chrono::duration<double>(now_steady - last_tick_time_).count();
    last_tick_time_ = now_steady;

    // Guard: drop samples with non-positive or excessively large dt.
    // Upper bound = 4 × nominal period: generous enough to survive a missed
    // tick but tight enough to reject pathological scheduler stalls that would
    // produce a near-zero finite-difference LOS rate (delta_x_rel_dot ≈ 0
    // despite real target motion) and a misleading zero command.
    if (dt <= 0.0 || dt > 4.0 / rate_hz_) { return; }

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

        // ── NaN / Inf guard ───────────────────────────────────────────────────
        // If the tracker publishes a non-finite position (e.g., degenerate
        // AprilTag pose), ProNav's finite difference and cross-product chain
        // silently produces NaN in a_cmd and permanently contaminates
        // prev_delta_x_rel_. Detect early, reset state, and send zero.
        if (!a_cmd.allFinite()) {
            RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
                "ProNav::compute() returned non-finite a_cmd "
                "(target=[%.3f,%.3f,%.3f] drone=[%.3f,%.3f,%.3f]) — "
                "resetting ProNav and sending zero.",
                x_target_NED_.x(), x_target_NED_.y(), x_target_NED_.z(),
                x_drone_NED_.x(), x_drone_NED_.y(), x_drone_NED_.z());
            pronav_.reset();
            a_cmd = Eigen::Vector3d::Zero();
        }
    }

    // ── MAVLink send ──────────────────────────────────────────────────────────
    // TODO: swap SET_ATTITUDE_TARGET (msg ID 82) for SET_POSITION_TARGET_LOCAL_NED
    //       (msg ID 84, mask 0b0000110000111111) once PX4 firmware acceleration
    //       feedforward path is confirmed against the Gazebo SITL model.
    //       See src/mavlink_bridge/mavlink_bridge.hpp for the mapping rationale.
    if (bridge_ && bridge_->isOpen()) {
        const uint64_t timestamp_us = static_cast<uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                now_steady.time_since_epoch()).count());
        bridge_->send(a_cmd, timestamp_us);
    }

    // ── Publish /ghost/guidance/a_cmd for logging and debug ──────────────────
    // Stamp with ROS2 wall time for bag playback and visualisation compatibility.
    geometry_msgs::msg::AccelStamped accel_msg;
    accel_msg.header.stamp    = this->now();
    accel_msg.header.frame_id = "ned";
    accel_msg.accel.linear.x  = a_cmd.x();   // North [m/s²]
    accel_msg.accel.linear.y  = a_cmd.y();   // East  [m/s²]
    accel_msg.accel.linear.z  = a_cmd.z();   // Down  [m/s²]
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
    try {
        rclcpp::spin(std::make_shared<ghost::GuidanceNode>());
    } catch (const std::exception& e) {
        // MavlinkBridge constructor throws std::runtime_error if socket() or
        // fcntl() fail — log via the static logger before rclcpp::shutdown().
        RCLCPP_FATAL(rclcpp::get_logger("guidance_node"),
            "Fatal error during GuidanceNode startup: %s", e.what());
    }

    rclcpp::shutdown();
    return 0;
}
