#include "eskf_node.hpp"

#include <chrono>
#include <cmath>

namespace ghost {

// ── Constructor ───────────────────────────────────────────────────────────────

EskfNode::EskfNode(const rclcpp::NodeOptions& options)
    : rclcpp::Node("eskf_node", options)
{
    // ── Declare parameters — mirror config/filter.yaml key hierarchy ──────────
    this->declare_parameter("eskf.process_noise.sigma_g_rad_per_s_per_sqrthz", 4.887e-5);
    this->declare_parameter("eskf.process_noise.sigma_a_m_per_s2_per_sqrthz",  2.5e-3);
    this->declare_parameter("eskf.gravity_update.sigma_accel_meas_m_per_s2",   0.30);
    this->declare_parameter("eskf.gravity_magnitude_m_per_s2",                 9.81);
    this->declare_parameter("eskf.zaru.arw_deg_per_sqrthz",                    0.0028);
    this->declare_parameter("eskf.zaru.accel_gate_m_per_s2",                   0.5);
    this->declare_parameter("eskf.zaru.rate_hz",                               1.0);
    this->declare_parameter("eskf.zaru.gyro_static_threshold_rps",             0.01);

    // ── Read parameters ───────────────────────────────────────────────────────
    sigma_g_ = this->get_parameter(
        "eskf.process_noise.sigma_g_rad_per_s_per_sqrthz").as_double();
    sigma_a_ = this->get_parameter(
        "eskf.process_noise.sigma_a_m_per_s2_per_sqrthz").as_double();
    gravity_m_per_s2_ = this->get_parameter(
        "eskf.gravity_magnitude_m_per_s2").as_double();
    accel_gate_m_per_s2_ = this->get_parameter(
        "eskf.zaru.accel_gate_m_per_s2").as_double();
    arw_deg_per_sqrthz_ = this->get_parameter(
        "eskf.zaru.arw_deg_per_sqrthz").as_double();
    gyro_static_threshold_ = this->get_parameter(
        "eskf.zaru.gyro_static_threshold_rps").as_double();

    const double zaru_rate_hz = this->get_parameter("eskf.zaru.rate_hz").as_double();

    // ── Configure and initialize ESKF ─────────────────────────────────────────
    eskf_.setProcessNoise(sigma_a_, sigma_g_);
    eskf_.initialize(Eigen::Quaterniond::Identity());

    RCLCPP_INFO(this->get_logger(),
        "ESKF initialized. sigma_g=%.2e rad/s/√Hz, sigma_a=%.2e m/s²/√Hz, "
        "gravity=%.3f m/s²",
        sigma_g_, sigma_a_, gravity_m_per_s2_);

    // ── Subscriptions ─────────────────────────────────────────────────────────
    imu_sub_ = this->create_subscription<sensor_msgs::msg::Imu>(
        "/ghost/imu/primary",
        rclcpp::SensorDataQoS(),
        [this](const sensor_msgs::msg::Imu::ConstSharedPtr& msg) {
            imuCallback(msg);
        });

    fault_sub_ = this->create_subscription<std_msgs::msg::Bool>(
        "/ghost/imu/fault",
        rclcpp::QoS(1).reliable(),
        [this](const std_msgs::msg::Bool::ConstSharedPtr& msg) {
            faultCallback(msg);
        });

    // ── Publishers ────────────────────────────────────────────────────────────
    pose_pub_ = this->create_publisher<geometry_msgs::msg::PoseWithCovarianceStamped>(
        "/ghost/eskf/pose", rclcpp::SensorDataQoS());

    tf_pub_ = this->create_publisher<geometry_msgs::msg::TransformStamped>(
        "/ghost/eskf/R_cam_to_ned", rclcpp::SensorDataQoS());

    // ── ZARU timer at configured rate ─────────────────────────────────────────
    const auto zaru_period = std::chrono::duration<double>(1.0 / zaru_rate_hz);
    zaru_timer_ = this->create_wall_timer(
        std::chrono::duration_cast<std::chrono::nanoseconds>(zaru_period),
        [this]() { zaruTimerCallback(); });

    RCLCPP_INFO(this->get_logger(),
        "EskfNode ready. ZARU at %.1f Hz, gyro_static_thr=%.4f rad/s, "
        "accel_gate=%.2f m/s²",
        zaru_rate_hz, gyro_static_threshold_, accel_gate_m_per_s2_);
}

// ── IMU callback — predict() + optional gravity update ───────────────────────

void EskfNode::imuCallback(const sensor_msgs::msg::Imu::ConstSharedPtr& msg)
{
    // Extract measurements from message
    last_omega_m_ = Eigen::Vector3d{
        msg->angular_velocity.x,
        msg->angular_velocity.y,
        msg->angular_velocity.z};

    last_accel_m_ = Eigen::Vector3d{
        msg->linear_acceleration.x,
        msg->linear_acceleration.y,
        msg->linear_acceleration.z};

    // Compute dt from message timestamps for accurate integration
    const rclcpp::Time stamp(msg->header.stamp);
    double dt = 0.0;
    if (first_imu_) {
        first_imu_      = false;
        last_imu_stamp_ = stamp;
        return;  // skip predict on first message — no valid dt yet
    }
    dt = (stamp - last_imu_stamp_).seconds();
    last_imu_stamp_ = stamp;

    // Guard against stale or out-of-order messages
    if (dt <= 0.0 || dt > 0.1) {
        RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
            "ESKF: abnormal dt=%.4f s — skipping predict()", dt);
        return;
    }

    // ── Predict step — always runs at 1000 Hz ─────────────────────────────────
    eskf_.predict(last_omega_m_, last_accel_m_, dt);

    // ── Gravity update — gated on platform not accelerating ──────────────────
    // GHOST_V10.md: "Gate: suspend if |accel_norm - 9.81| > 0.5 m/s²"
    const double accel_norm = last_accel_m_.norm();
    const bool   platform_static = std::abs(accel_norm - gravity_m_per_s2_)
                                   <= accel_gate_m_per_s2_;

    if (platform_static && !imu_fault_) {
        eskf_.updateGravity(last_accel_m_);

        // TODO: add Sage-Husa adaptive noise update once characterization data
        //       is available. Call SageHusa::updateR(innovation, H, P_prior) here
        //       and pass the returned R_hat to updateGravity() instead of the
        //       fixed sigma_accel_meas parameter.
    }

    // ── Publish at 1000 Hz ────────────────────────────────────────────────────
    publishPose(stamp);
    publishTransform(stamp);
}

// ── Fault callback ────────────────────────────────────────────────────────────

void EskfNode::faultCallback(const std_msgs::msg::Bool::ConstSharedPtr& msg)
{
    if (msg->data && !imu_fault_) {
        RCLCPP_WARN(this->get_logger(),
            "IMU watchdog fault received — suspending ESKF gravity update. "
            "GHOST_V10.md: primary ICM-42688-P continues as predict() source.");
        imu_fault_ = true;
    } else if (!msg->data && imu_fault_) {
        RCLCPP_INFO(this->get_logger(),
            "IMU watchdog fault cleared — resuming ESKF gravity update.");
        imu_fault_ = false;
    }
}

// ── ZARU timer callback — 1 Hz ────────────────────────────────────────────────

void EskfNode::zaruTimerCallback()
{
    if (!eskf_.isInitialized()) { return; }

    // Gate 1: IMU fault active — ZARU still valid (tripod is static regardless)
    // but skip if primary IMU data has never arrived
    if (first_imu_) { return; }

    // Gate 2: platform must be angularly static
    // GHOST_V10.md: ZARU fires only on static tripod — if gyro norm is large,
    // a vibration or bump is happening; skip this cycle
    if (last_omega_m_.norm() >= gyro_static_threshold_) {
        RCLCPP_DEBUG(this->get_logger(),
            "ZARU skipped: gyro_norm=%.4f rad/s >= threshold=%.4f",
            last_omega_m_.norm(), gyro_static_threshold_);
        return;
    }

    // Gate 3: ZARU::shouldUpdate — checks timing interval and accel gate
    // GHOST_V10.md: "Gate: suspend if |accel_norm - 9.81| > 0.5 m/s²"
    const double elapsed_s = first_zaru_
        ? 1.0  // force fire on very first ZARU tick after startup
        : (this->now() - last_zaru_stamp_).seconds();

    if (!zaru_.shouldUpdate(elapsed_s, last_accel_m_)) {
        return;
    }

    // ── Apply ZARU measurement update ─────────────────────────────────────────
    // GHOST_V10.md: "H_ZARU = [0|0|I] — LAST block extracts delta_b_g (gyro bias)
    //               innovation: y = 0 − (omega_m − b_g_hat)"
    const Eigen::Vector3d           y = zaru_.computeInnovation(
                                            last_omega_m_, eskf_.getGyroBias());
    const Eigen::Matrix<double,3,9> H = zaru_.getH();
    const Eigen::Matrix3d           R = zaru_.getR(arw_deg_per_sqrthz_);

    // applyUpdate(): Joseph-form KF update, injects into delta_theta, b_a, b_g
    // NIS for ZARU is logged to logs/nis_camera_zaru.csv (NOT CI-gated)
    // GHOST_V10.md: "ZARU NIS logged separately — not valid for dynamic chi²(3) gate"
    eskf_.applyUpdate(H, y, R);

    last_zaru_stamp_ = this->now();
    first_zaru_      = false;

    RCLCPP_DEBUG(this->get_logger(),
        "ZARU fired: gyro_bias=[%.4f, %.4f, %.4f] rad/s",
        eskf_.getGyroBias().x(),
        eskf_.getGyroBias().y(),
        eskf_.getGyroBias().z());
}

// ── publishPose ───────────────────────────────────────────────────────────────

void EskfNode::publishPose(const rclcpp::Time& stamp)
{
    const Eigen::Quaterniond q = Eigen::Quaterniond{eskf_.getR_cam_to_NED()};
    const Eigen::Matrix<double,9,9> P = eskf_.getCovariance();

    geometry_msgs::msg::PoseWithCovarianceStamped msg;
    msg.header.stamp    = stamp;
    msg.header.frame_id = "ned";

    // Position: (0, 0, 0) — camera platform is on a static tripod
    msg.pose.pose.position.x = 0.0;
    msg.pose.pose.position.y = 0.0;
    msg.pose.pose.position.z = 0.0;

    // Orientation: q_cam (NED ← camera)
    msg.pose.pose.orientation.w = q.w();
    msg.pose.pose.orientation.x = q.x();
    msg.pose.pose.orientation.y = q.y();
    msg.pose.pose.orientation.z = q.z();

    // 6×6 covariance: [x, y, z, rot_x, rot_y, rot_z] (row-major, 36 elements)
    // REP-103: position rows/cols 0-2 = 0 (known static position)
    //          orientation rows/cols 3-5 = P[0:3, 0:3] (delta_theta covariance)
    msg.pose.covariance.fill(0.0);
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            msg.pose.covariance[(3 + i) * 6 + (3 + j)] = P(i, j);
        }
    }

    pose_pub_->publish(msg);
}

// ── publishTransform ──────────────────────────────────────────────────────────

void EskfNode::publishTransform(const rclcpp::Time& stamp)
{
    // R_cam_to_NED expressed as a quaternion in a TransformStamped.
    // Consumers (target tracker node): extract R = tf2::transformToEigen(msg).rotation()
    const Eigen::Quaterniond q = Eigen::Quaterniond{eskf_.getR_cam_to_NED()};

    geometry_msgs::msg::TransformStamped msg;
    msg.header.stamp    = stamp;
    msg.header.frame_id = "ned";          // parent frame
    msg.child_frame_id  = "camera_link";  // child frame

    // No translation — IMU and camera share the same tripod origin
    msg.transform.translation.x = 0.0;
    msg.transform.translation.y = 0.0;
    msg.transform.translation.z = 0.0;

    msg.transform.rotation.w = q.w();
    msg.transform.rotation.x = q.x();
    msg.transform.rotation.y = q.y();
    msg.transform.rotation.z = q.z();

    tf_pub_->publish(msg);
}

}  // namespace ghost

// ── main ──────────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);

    // SingleThreadedExecutor: all ESKF calls happen on one thread — no mutex needed.
    // GHOST_V10.md: ESKF runs at 1000 Hz; do not use a MultiThreadedExecutor here.
    auto node = std::make_shared<ghost::EskfNode>();
    rclcpp::spin(node);

    rclcpp::shutdown();
    return 0;
}
