#pragma once

#include <memory>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <geometry_msgs/msg/twist_with_covariance_stamped.hpp>
#include <std_msgs/msg/bool.hpp>

#include <Eigen/Dense>

#include "target_tracker/cv_filter.hpp"
#include "target_tracker/ctrv_filter.hpp"

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// TrackerNode
//
// ROS2 Humble node that runs the CV and CTRV target tracking filters and
// publishes the RC car's estimated position and velocity in NED frame.
//
// Subscription layout:
//   /ghost/eskf/R_cam_to_ned     geometry_msgs/msg/TransformStamped
//       Rotation matrix from camera frame → NED. Updated at 1000 Hz by eskf_node.
//       Required before any AprilTag detection can be processed.
//
//   /ghost/vision/apriltag_pose  geometry_msgs/msg/PoseStamped
//       AprilTag pose in camera frame. Converted to NED, then used to call
//       CVFilter::update() and CTRVFilter::update().
//       TODO: replace PoseStamped with apriltag_ros DetectionArray once vision
//             pipeline node is written.
//
// Publication layout:
//   /ghost/tracker/pose      geometry_msgs/msg/PoseWithCovarianceStamped   (NED)
//   /ghost/tracker/velocity  geometry_msgs/msg/TwistWithCovarianceStamped  (NED)
//   /ghost/tracker/occluded  std_msgs/msg/Bool
//       true when no AprilTag detection received for > occlusion_timeout_s.
//
// Update schedule (single-threaded executor — no mutex needed):
//   Predict   30 Hz wall-clock timer, always running.
//             During occlusion the filter coasts on its own velocity estimate.
//             GHOST_V10.md: "occluded: CV or CTRV kinematic propagation (no IMU)"
//   Update    on each /ghost/vision/apriltag_pose message.
//
// Model selection:
//   |psi_dot| > 1e-4 rad/s → use CTRV output (car is turning)
//   |psi_dot| ≤ 1e-4 rad/s → use CV output  (car is going straight)
//   GHOST_V10.md: "CV vs CTRV model selection by lower NIS on rosbag — not intuition"
//
// Parameters (loaded from config/filter.yaml):
//   cv_filter.process_noise.singer_alpha              double  2.0
//   cv_filter.process_noise.singer_a_max_m_per_s2     double  2.0
//   cv_filter.measurement_noise.sigma_r_m             double  0.02
//   ctrv_filter.process_noise.sigma_a_m_per_s2        double  0.50
//   ctrv_filter.process_noise.sigma_psi_dot_rad_per_s double  0.20
//   ctrv_filter.measurement_noise.sigma_r_m           double  0.02
//   tracker.occlusion_timeout_s                       double  0.5
//   tracker.coast_predict_rate_hz                     double  30.0
// ─────────────────────────────────────────────────────────────────────────────
class TrackerNode : public rclcpp::Node {
public:
    explicit TrackerNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions{});

private:
    // ── Callbacks ─────────────────────────────────────────────────────────────

    // Store latest R_cam_to_ned for coordinate conversion
    void transformCallback(const geometry_msgs::msg::TransformStamped::ConstSharedPtr& msg);

    // Convert detection to NED, call update() on both filters, publish
    void apriltagCallback(const geometry_msgs::msg::PoseStamped::ConstSharedPtr& msg);

    // 30 Hz: predict(), check occlusion, publish state
    void coastTimerCallback();

    // ── Helpers ───────────────────────────────────────────────────────────────

    // True if |psi_dot| > 1e-4 rad/s (CTRV singularity guard threshold)
    bool useCTRV() const;

    // Build and publish pose + velocity from whichever model is active
    void publishState(const rclcpp::Time& stamp);

    // ── Filters ───────────────────────────────────────────────────────────────
    CVFilter   cv_;
    CTRVFilter ctrv_;

    // Latest rotation matrix from ESKF — populated by /ghost/eskf/R_cam_to_ned
    Eigen::Matrix3d R_cam_to_ned_{Eigen::Matrix3d::Identity()};
    bool            R_valid_{false};  // false until first transform received

    // Wall-clock time of last predict() call, used to compute dt for coast timer
    rclcpp::Time last_predict_time_;
    bool         first_predict_{true};

    // Wall-clock time of last AprilTag detection, used for occlusion detection
    rclcpp::Time last_detection_time_;
    bool         ever_detected_{false};

    // Occlusion state — published on /ghost/tracker/occluded
    bool occluded_{false};

    // ── Subscriptions ─────────────────────────────────────────────────────────
    rclcpp::Subscription<geometry_msgs::msg::TransformStamped>::SharedPtr transform_sub_;
    rclcpp::Subscription<geometry_msgs::msg::PoseStamped>::SharedPtr      apriltag_sub_;

    // ── Publishers ────────────────────────────────────────────────────────────
    rclcpp::Publisher<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr  pose_pub_;
    rclcpp::Publisher<geometry_msgs::msg::TwistWithCovarianceStamped>::SharedPtr vel_pub_;
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr                            occluded_pub_;

    // ── Coast timer ───────────────────────────────────────────────────────────
    rclcpp::TimerBase::SharedPtr coast_timer_;

    // ── Parameters ────────────────────────────────────────────────────────────
    double occlusion_timeout_s_;
    static constexpr double kPsiDotThreshold = 1e-4;  // CTRV singularity guard
};

}  // namespace ghost
