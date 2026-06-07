#pragma once

#include <chrono>
#include <memory>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/accel_stamped.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <std_msgs/msg/bool.hpp>

#include <Eigen/Dense>

#include "guidance/pronav.hpp"
#include "mavlink_bridge/mavlink_bridge.hpp"

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// GuidanceNode
//
// ROS2 Humble node that closes the guidance loop: subscribes to the target
// tracker and ESKF outputs, runs TPN ProNav at rate_hz_, and delivers the
// resulting acceleration command to PX4 SITL via UDP MAVLink.
//
// GHOST_V10.md §ProNav — True Proportional Navigation (TPN):
//   a_cmd = N · Omega × V_c   (Omega × V_c — NOT V_c × Omega)
//   Omega = (delta_x_rel × delta_x_rel_dot) / range²   ← internal finite difference
//   V_c   = -delta_x_rel_dot                            ← derived from position history
//   Terminal coast: range < r_cutoff → a_cmd = 0
//   K_sim applied to XY only — raw drone altitude for Z
//
// NOTE: /ghost/tracker/velocity is NOT subscribed here. ProNav computes its
// closing velocity V_c by finite-differencing the received NED positions; the
// Kalman-filtered velocity from the tracker is not consumed by TPN. If a
// future guidance law (BiasPN, APN) requires tracker velocity, add the
// subscription and pass v_target_NED_ to the updated compute() signature.
//
// Subscription layout:
//   /ghost/tracker/pose     geometry_msgs/msg/PoseWithCovarianceStamped  target NED position
//   /ghost/tracker/occluded std_msgs/msg/Bool   — suspend ProNav when true
//   /ghost/eskf/pose        geometry_msgs/msg/PoseWithCovarianceStamped  drone NED origin
//
// Publication layout:
//   /ghost/guidance/a_cmd   geometry_msgs/msg/AccelStamped  [m/s²]  (log/debug)
//
// MAVLink:
//   Host: 127.0.0.1, Port: 14540 (PX4 SITL default)
//   MavlinkBridge::send() called at rate_hz_ on the guidance timer
//   TODO: swap SET_ATTITUDE_TARGET for SET_POSITION_TARGET_LOCAL_NED once
//         PX4 firmware acceleration feedforward path is confirmed.
//
// Parameters (loaded from config/guidance.yaml via ROS2 parameter server):
//   guidance.N                   double   3.0    ProNav navigation gain
//   guidance.r_cutoff_m          double   1.5    terminal coast range [m]
//   guidance.K_sim               double   1.0    sim-to-reality scale (XY only)
//   guidance.mavlink_host        string  "127.0.0.1"
//   guidance.mavlink_port        int      14540
//   guidance.rate_hz             double   30.0
//
// All ProNav and MAVLink calls execute on the timer callback thread.
// Use SingleThreadedExecutor — no mutex required.
// ─────────────────────────────────────────────────────────────────────────────
class GuidanceNode : public rclcpp::Node {
public:
    explicit GuidanceNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions{});
    ~GuidanceNode() override;

private:
    // ── Callbacks ─────────────────────────────────────────────────────────────
    void targetPoseCallback(
        const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr& msg);
    void occludedCallback(const std_msgs::msg::Bool::ConstSharedPtr& msg);
    void dronePoseCallback(
        const geometry_msgs::msg::PoseWithCovarianceStamped::ConstSharedPtr& msg);

    // rate_hz_ guidance timer — runs ProNav and sends MAVLink
    void guidanceTimerCallback();

    // ── Guidance objects ──────────────────────────────────────────────────────
    ProNav                         pronav_;
    std::unique_ptr<MavlinkBridge> bridge_;

    // ── Latest state snapshots (updated by subscriber callbacks) ─────────────
    Eigen::Vector3d x_target_NED_{Eigen::Vector3d::Zero()};
    Eigen::Vector3d x_drone_NED_{Eigen::Vector3d::Zero()};

    bool target_pose_valid_{false};
    bool drone_pose_valid_{false};
    bool occluded_{false};

    // Steady-clock time of last guidance timer tick — used to compute dt for ProNav.
    // Stored as a duration since epoch so dt arithmetic stays in steady_clock domain.
    std::chrono::steady_clock::time_point last_tick_time_;
    bool                                   first_tick_{true};

    // Guidance loop rate — stored as member so dt guard can reference it.
    double rate_hz_{30.0};

    // ── Subscriptions ─────────────────────────────────────────────────────────
    rclcpp::Subscription<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr target_pose_sub_;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr                            occluded_sub_;
    rclcpp::Subscription<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr drone_pose_sub_;

    // ── Publishers ────────────────────────────────────────────────────────────
    rclcpp::Publisher<geometry_msgs::msg::AccelStamped>::SharedPtr accel_pub_;

    // ── Guidance timer ────────────────────────────────────────────────────────
    rclcpp::TimerBase::SharedPtr guidance_timer_;
};

}  // namespace ghost
