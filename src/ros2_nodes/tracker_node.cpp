#include "tracker_node.hpp"

#include <chrono>
#include <cmath>

namespace ghost {

// ── Constructor ───────────────────────────────────────────────────────────────

TrackerNode::TrackerNode(const rclcpp::NodeOptions& options)
    : rclcpp::Node("tracker_node", options)
{
    // ── Declare parameters — mirror config/filter.yaml key hierarchy ──────────
    // CV filter — Singer model process noise
    this->declare_parameter("cv_filter.process_noise.singer_alpha",          2.0);
    this->declare_parameter("cv_filter.process_noise.singer_a_max_m_per_s2", 2.0);
    this->declare_parameter("cv_filter.measurement_noise.sigma_r_m",         0.02);

    // CTRV filter
    this->declare_parameter("ctrv_filter.process_noise.sigma_a_m_per_s2",        0.50);
    this->declare_parameter("ctrv_filter.process_noise.sigma_psi_dot_rad_per_s", 0.20);
    this->declare_parameter("ctrv_filter.measurement_noise.sigma_r_m",           0.02);

    // Tracker
    this->declare_parameter("tracker.occlusion_timeout_s",    0.5);
    this->declare_parameter("tracker.coast_predict_rate_hz",  30.0);

    // ── Read parameters ───────────────────────────────────────────────────────
    const double singer_alpha   = this->get_parameter(
        "cv_filter.process_noise.singer_alpha").as_double();
    const double singer_a_max   = this->get_parameter(
        "cv_filter.process_noise.singer_a_max_m_per_s2").as_double();
    const double cv_sigma_r     = this->get_parameter(
        "cv_filter.measurement_noise.sigma_r_m").as_double();

    const double ctrv_sigma_a       = this->get_parameter(
        "ctrv_filter.process_noise.sigma_a_m_per_s2").as_double();
    const double ctrv_sigma_psi_dot = this->get_parameter(
        "ctrv_filter.process_noise.sigma_psi_dot_rad_per_s").as_double();
    const double ctrv_sigma_r       = this->get_parameter(
        "ctrv_filter.measurement_noise.sigma_r_m").as_double();

    occlusion_timeout_s_ = this->get_parameter("tracker.occlusion_timeout_s").as_double();
    const double coast_rate_hz = this->get_parameter("tracker.coast_predict_rate_hz").as_double();

    // ── Configure filters ─────────────────────────────────────────────────────
    // CV Singer model: sigma_a² = 2 * alpha * a_max² / 3
    // GHOST_V10.md: "Q_target from Singer model: sigma_a² = 2·alpha·a_max²/3"
    const double cv_sigma_a = std::sqrt(2.0 * singer_alpha * singer_a_max * singer_a_max / 3.0);
    cv_.setProcessNoise(cv_sigma_a);
    cv_.setMeasurementNoise(cv_sigma_r);

    ctrv_.setProcessNoise(ctrv_sigma_a, ctrv_sigma_psi_dot);
    ctrv_.setMeasurementNoise(ctrv_sigma_r);

    RCLCPP_INFO(this->get_logger(),
        "TrackerNode configured. CV sigma_a=%.4f m/s², CTRV sigma_a=%.4f m/s² "
        "sigma_psi_dot=%.4f rad/s, occlusion_timeout=%.2f s, coast=%.0f Hz",
        cv_sigma_a, ctrv_sigma_a, ctrv_sigma_psi_dot,
        occlusion_timeout_s_, coast_rate_hz);

    // ── Subscriptions ─────────────────────────────────────────────────────────
    transform_sub_ = this->create_subscription<geometry_msgs::msg::TransformStamped>(
        "/ghost/eskf/R_cam_to_ned",
        rclcpp::SensorDataQoS(),
        [this](const geometry_msgs::msg::TransformStamped::ConstSharedPtr& msg) {
            transformCallback(msg);
        });

    // TODO: replace PoseStamped with apriltag_ros DetectionArray once the vision
    //       pipeline node (src/vision/apriltag_detector) is written and publishing
    //       detections. Until then, PoseStamped is a suitable stand-in for testing.
    apriltag_sub_ = this->create_subscription<geometry_msgs::msg::PoseStamped>(
        "/ghost/vision/apriltag_pose",
        rclcpp::SensorDataQoS(),
        [this](const geometry_msgs::msg::PoseStamped::ConstSharedPtr& msg) {
            apriltagCallback(msg);
        });

    // ── Publishers ────────────────────────────────────────────────────────────
    pose_pub_ = this->create_publisher<geometry_msgs::msg::PoseWithCovarianceStamped>(
        "/ghost/tracker/pose", rclcpp::SensorDataQoS());

    vel_pub_ = this->create_publisher<geometry_msgs::msg::TwistWithCovarianceStamped>(
        "/ghost/tracker/velocity", rclcpp::SensorDataQoS());

    occluded_pub_ = this->create_publisher<std_msgs::msg::Bool>(
        "/ghost/tracker/occluded", rclcpp::QoS(1).reliable());

    // ── Coast predict timer — always running at 30 Hz ─────────────────────────
    const auto period = std::chrono::duration<double>(1.0 / coast_rate_hz);
    coast_timer_ = this->create_wall_timer(
        std::chrono::duration_cast<std::chrono::nanoseconds>(period),
        [this]() { coastTimerCallback(); });
}

// ── transformCallback — store R_cam_to_ned ───────────────────────────────────

void TrackerNode::transformCallback(
    const geometry_msgs::msg::TransformStamped::ConstSharedPtr& msg)
{
    // Extract quaternion and convert to rotation matrix
    const Eigen::Quaterniond q(
        msg->transform.rotation.w,
        msg->transform.rotation.x,
        msg->transform.rotation.y,
        msg->transform.rotation.z);
    R_cam_to_ned_ = q.toRotationMatrix();
    R_valid_      = true;
}

// ── apriltagCallback — measurement update ────────────────────────────────────

void TrackerNode::apriltagCallback(
    const geometry_msgs::msg::PoseStamped::ConstSharedPtr& msg)
{
    if (!R_valid_) {
        RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
            "AprilTag detection received but R_cam_to_ned not yet available — "
            "waiting for /ghost/eskf/R_cam_to_ned");
        return;
    }

    // ── Convert camera-frame pose to NED ─────────────────────────────────────
    // GHOST_V10.md: "pose in camera frame → NED via R_cam_to_NED"
    // GHOST_V10.md: "NEVER use desk IMU to propagate car motion — strapdown constraint"
    const Eigen::Vector3d pos_cam(
        msg->pose.position.x,
        msg->pose.position.y,
        msg->pose.position.z);
    const Eigen::Vector3d pos_NED = R_cam_to_ned_ * pos_cam;

    // ── Initialize filters on first detection ────────────────────────────────
    if (!cv_.isInitialized()) {
        cv_.initialize(pos_NED);
        RCLCPP_INFO(this->get_logger(),
            "CVFilter initialized at NED [%.3f, %.3f, %.3f] m",
            pos_NED.x(), pos_NED.y(), pos_NED.z());
    }
    if (!ctrv_.isInitialized()) {
        const Eigen::Vector2d pos_xy(pos_NED.x(), pos_NED.y());
        ctrv_.initialize(pos_xy, /*v_init=*/0.0, /*psi_init=*/0.0);
        RCLCPP_INFO(this->get_logger(),
            "CTRVFilter initialized at NED [%.3f, %.3f] m",
            pos_NED.x(), pos_NED.y());
    }

    // ── Measurement update on both filters ────────────────────────────────────
    // predict() is handled by the 30 Hz coast timer; update() is called here.
    cv_.update(pos_NED);
    ctrv_.update(Eigen::Vector2d(pos_NED.x(), pos_NED.y()));

    // ── Occlusion bookkeeping ─────────────────────────────────────────────────
    last_detection_time_ = this->now();
    ever_detected_       = true;

    if (occluded_) {
        RCLCPP_INFO(this->get_logger(),
            "Target reacquired — exiting occlusion coast mode.");
        occluded_ = false;
    }

    const rclcpp::Time stamp(msg->header.stamp);
    publishState(stamp);
}

// ── coastTimerCallback — predict + occlusion check ───────────────────────────

void TrackerNode::coastTimerCallback()
{
    const rclcpp::Time now = this->now();

    // Compute dt from wall clock
    double dt = 0.0;
    if (first_predict_) {
        first_predict_      = false;
        last_predict_time_  = now;
        return;
    }
    dt = (now - last_predict_time_).seconds();
    last_predict_time_ = now;

    if (dt <= 0.0 || dt > 1.0) { return; }  // guard against clock jump

    // ── Predict step — both filters, always ───────────────────────────────────
    // GHOST_V10.md: "occluded: CV or CTRV kinematic propagation (no IMU)"
    // Predict runs during both vision-available and occlusion phases.
    // The update() step in apriltagCallback() corrects drift when vision returns.
    if (cv_.isInitialized())   { cv_.predict(dt);   }
    if (ctrv_.isInitialized()) { ctrv_.predict(dt); }

    // ── Occlusion detection ───────────────────────────────────────────────────
    if (ever_detected_) {
        const double since_detection = (now - last_detection_time_).seconds();
        const bool   newly_occluded  = (since_detection > occlusion_timeout_s_) && !occluded_;

        if (newly_occluded) {
            RCLCPP_WARN(this->get_logger(),
                "Target occluded — no detection for %.2f s. "
                "Coasting on %s kinematic model.",
                since_detection, useCTRV() ? "CTRV" : "CV");
            occluded_ = true;
        }

        // Publish occlusion flag
        std_msgs::msg::Bool occ_msg;
        occ_msg.data = occluded_;
        occluded_pub_->publish(occ_msg);
    }

    // Publish state at predict rate (30 Hz)
    if (cv_.isInitialized() || ctrv_.isInitialized()) {
        publishState(now);
    }
}

// ── useCTRV — model selection ─────────────────────────────────────────────────

bool TrackerNode::useCTRV() const
{
    if (!ctrv_.isInitialized()) { return false; }

    // CTRV state: [px, py, v, psi, psi_dot]
    // Model selection: CTRV when |psi_dot| > singularity guard threshold.
    // GHOST_V10.md: "CV vs CTRV by lower NIS on rosbag — not intuition"
    // This runtime check is the coarse selector; fine tuning via NIS comparison.
    const double psi_dot = ctrv_.getState()(4);
    return std::abs(psi_dot) > kPsiDotThreshold;
}

// ── publishState ──────────────────────────────────────────────────────────────

void TrackerNode::publishState(const rclcpp::Time& stamp)
{
    const bool use_ctrv = useCTRV();

    // ── Position and velocity in NED ──────────────────────────────────────────
    Eigen::Vector3d pos_NED(0.0, 0.0, 0.0);
    Eigen::Vector3d vel_NED(0.0, 0.0, 0.0);
    Eigen::MatrixXd pos_cov;  // 3x3 position covariance
    Eigen::MatrixXd vel_cov;  // 3x3 velocity covariance

    if (use_ctrv && ctrv_.isInitialized()) {
        // CTRV state: [px, py, v, psi, psi_dot]
        const Eigen::VectorXd x = ctrv_.getState();
        const Eigen::MatrixXd P = ctrv_.getCovariance();

        const double v   = x(2);
        const double psi = x(3);

        pos_NED = {x(0), x(1), 0.0};

        // Velocity: decompose speed into NED components using heading
        vel_NED = {v * std::cos(psi), v * std::sin(psi), 0.0};

        // 3x3 position covariance from 5x5 P — take the [px, py] block
        pos_cov = Eigen::Matrix3d::Zero();
        pos_cov.topLeftCorner<2, 2>() = P.topLeftCorner<2, 2>();

        // Velocity covariance: approximate from v and psi variances
        // P(2,2) = var(v), P(3,3) = var(psi) — use speed variance as diagonal
        vel_cov = Eigen::Matrix3d::Identity() * P(2, 2);

    } else if (cv_.isInitialized()) {
        // CV state: [px, py, pz, vx, vy, vz]
        const Eigen::VectorXd x = cv_.getState();
        const Eigen::MatrixXd P = cv_.getCovariance();

        pos_NED = {x(0), x(1), x(2)};
        vel_NED = {x(3), x(4), x(5)};

        pos_cov = P.topLeftCorner<3, 3>();      // position block
        vel_cov = P.bottomRightCorner<3, 3>();  // velocity block

    } else {
        return;  // neither filter initialized yet
    }

    // ── PoseWithCovarianceStamped ─────────────────────────────────────────────
    geometry_msgs::msg::PoseWithCovarianceStamped pose_msg;
    pose_msg.header.stamp    = stamp;
    pose_msg.header.frame_id = "ned";

    pose_msg.pose.pose.position.x = pos_NED.x();
    pose_msg.pose.pose.position.y = pos_NED.y();
    pose_msg.pose.pose.position.z = pos_NED.z();

    // Orientation unknown — RC car heading not directly observable as quaternion
    pose_msg.pose.pose.orientation.w = 1.0;

    // Fill 6x6 covariance [x,y,z, rx,ry,rz] — position block only (rows/cols 0-2)
    pose_msg.pose.covariance.fill(0.0);
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            pose_msg.pose.covariance[i * 6 + j] = pos_cov(i, j);
        }
    }
    pose_pub_->publish(pose_msg);

    // ── TwistWithCovarianceStamped ────────────────────────────────────────────
    geometry_msgs::msg::TwistWithCovarianceStamped vel_msg;
    vel_msg.header.stamp    = stamp;
    vel_msg.header.frame_id = "ned";

    vel_msg.twist.twist.linear.x = vel_NED.x();
    vel_msg.twist.twist.linear.y = vel_NED.y();
    vel_msg.twist.twist.linear.z = vel_NED.z();

    // Fill 6x6 covariance [vx,vy,vz, wx,wy,wz] — linear velocity block only
    vel_msg.twist.covariance.fill(0.0);
    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            vel_msg.twist.covariance[i * 6 + j] = vel_cov(i, j);
        }
    }
    vel_pub_->publish(vel_msg);
}

}  // namespace ghost

// ── main ──────────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);

    // SingleThreadedExecutor: all filter calls on one thread — no mutex needed.
    // CVFilter and CTRVFilter are not thread-safe; do not use MultiThreadedExecutor.
    rclcpp::spin(std::make_shared<ghost::TrackerNode>());

    rclcpp::shutdown();
    return 0;
}
