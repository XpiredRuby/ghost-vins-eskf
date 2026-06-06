#pragma once

#include <memory>

#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/bool.hpp>

#include <Eigen/Dense>

// Filter and ZARU helpers — pure Eigen, no ROS2 dependency
#include "attitude_filter/eskf.hpp"
#include "attitude_filter/zaru.hpp"

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// EskfNode
//
// ROS2 Humble node that runs the 9-state attitude ESKF at 1000 Hz and
// publishes the camera platform orientation for downstream consumers.
//
// Subscription layout:
//   /ghost/imu/primary   sensor_msgs/msg/Imu    1000 Hz — drives predict()
//   /ghost/imu/fault     std_msgs/msg/Bool              — suspends gravity update
//
// Publication layout:
//   /ghost/eskf/pose         geometry_msgs/msg/PoseWithCovarianceStamped
//                            q_cam + 6×6 covariance (position block = 0, static tripod)
//   /ghost/eskf/R_cam_to_ned geometry_msgs/msg/TransformStamped
//                            R_cam_to_NED as quaternion, consumed by target tracker node
//
// Update schedule:
//   Predict       every /ghost/imu/primary message  (1000 Hz, callback thread)
//   Gravity       every IMU message where |‖a‖ − 9.81| ≤ accel_gate [m/s²]
//   ZARU          1 Hz rclcpp::TimerBase, only when ‖ω‖ < gyro_static_threshold
//
// All ESKF calls execute on the ROS2 callback thread — no mutex required.
// Use a SingleThreadedExecutor (or the default spin()) with this node.
//
// Parameters (loaded from config/filter.yaml via ROS2 parameter server):
//   eskf.process_noise.sigma_g_rad_per_s_per_sqrthz  double  4.887e-5
//   eskf.process_noise.sigma_a_m_per_s2_per_sqrthz   double  0.0025
//   eskf.gravity_update.sigma_accel_meas_m_per_s2    double  0.30
//   eskf.gravity_magnitude_m_per_s2                  double  9.81
//   eskf.zaru.arw_deg_per_sqrthz                     double  0.0028
//   eskf.zaru.accel_gate_m_per_s2                    double  0.5
//   eskf.zaru.rate_hz                                double  1.0
//   eskf.zaru.gyro_static_threshold_rps              double  0.01
// ─────────────────────────────────────────────────────────────────────────────
class EskfNode : public rclcpp::Node {
public:
    explicit EskfNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions{});

private:
    // ── Callbacks ─────────────────────────────────────────────────────────────
    void imuCallback(const sensor_msgs::msg::Imu::ConstSharedPtr& msg);
    void faultCallback(const std_msgs::msg::Bool::ConstSharedPtr& msg);
    void zaruTimerCallback();

    // ── Helpers ───────────────────────────────────────────────────────────────
    void publishPose(const rclcpp::Time& stamp);
    void publishTransform(const rclcpp::Time& stamp);

    // ── Filter state ──────────────────────────────────────────────────────────
    ESKF eskf_;
    ZARU zaru_;

    // Last raw IMU measurements, cached for ZARU and gravity gating
    Eigen::Vector3d last_omega_m_{Eigen::Vector3d::Zero()};
    Eigen::Vector3d last_accel_m_{Eigen::Vector3d::Zero()};

    // Timestamp of the last IMU message, used to compute dt for predict()
    rclcpp::Time    last_imu_stamp_;
    bool            first_imu_{true};

    // Watchdog fault flag — set by /ghost/imu/fault subscriber
    bool imu_fault_{false};

    // ── Subscriptions ─────────────────────────────────────────────────────────
    rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr   imu_sub_;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr     fault_sub_;

    // ── Publishers ────────────────────────────────────────────────────────────
    rclcpp::Publisher<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr pose_pub_;
    rclcpp::Publisher<geometry_msgs::msg::TransformStamped>::SharedPtr          tf_pub_;

    // ── ZARU timer ────────────────────────────────────────────────────────────
    rclcpp::TimerBase::SharedPtr zaru_timer_;

    // ── Parameters ────────────────────────────────────────────────────────────
    double sigma_g_;               // gyro process noise  [rad/s/√Hz]
    double sigma_a_;               // accel process noise [m/s²/√Hz]
    double gravity_m_per_s2_;      // local gravity reference [m/s²]
    double accel_gate_m_per_s2_;   // gravity update gate (|‖a‖−g| ≤ this)
    double arw_deg_per_sqrthz_;    // Allan Variance ARW for ZARU R_zaru
    double gyro_static_threshold_; // ZARU fires only when ‖ω‖ < this [rad/s]
    double zaru_rate_hz_;          // ZARU timer rate; used in zaruTimerCallback
};

}  // namespace ghost
