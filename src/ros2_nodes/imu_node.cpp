#include "imu_node.hpp"

// Driver headers — Linux-only; this TU only compiles on the Pi target
#include "imu_driver/icm42688p.hpp"
#include "imu_driver/mpu6050.hpp"

#include <stdexcept>
#include <string>

namespace ghost {

// ── Constructor ───────────────────────────────────────────────────────────────
// Declares ROS2 parameters and creates publishers.
// No hardware is touched here — call initialize() after construction.

ImuNode::ImuNode(const rclcpp::NodeOptions& options)
    : rclcpp::Node("imu_node", options)
{
    // ── Declare parameters (values come from config/imu.yaml at launch) ───────
    this->declare_parameter("icm42688p.spi_device",  "/dev/spidev0.0");
    this->declare_parameter("icm42688p.spi_clock_hz", 10000000);
    this->declare_parameter("icm42688p.drdy_gpio",    17);

    this->declare_parameter("mpu6050.i2c_bus",   1);
    this->declare_parameter("mpu6050.drdy_gpio", 27);

    // Fault thresholds — must be characterised from a static baseline run.
    // Defaults match config/imu.yaml placeholders; override via parameter server.
    this->declare_parameter(
        "mpu6050.fault_detection.accel_disagreement_threshold_m_per_s2", 1.0);
    this->declare_parameter(
        "mpu6050.fault_detection.rate_disagreement_threshold_rad_per_s",  0.05);

    // ── Read parameters ───────────────────────────────────────────────────────
    spi_device_   = this->get_parameter("icm42688p.spi_device").as_string();
    spi_clock_hz_ = static_cast<int>(
        this->get_parameter("icm42688p.spi_clock_hz").as_int());
    icm_drdy_gpio_ = static_cast<int>(
        this->get_parameter("icm42688p.drdy_gpio").as_int());

    i2c_bus_       = static_cast<int>(this->get_parameter("mpu6050.i2c_bus").as_int());
    mpu_drdy_gpio_ = static_cast<int>(this->get_parameter("mpu6050.drdy_gpio").as_int());

    accel_threshold_mps2_ = this->get_parameter(
        "mpu6050.fault_detection.accel_disagreement_threshold_m_per_s2").as_double();
    gyro_threshold_rps_ = this->get_parameter(
        "mpu6050.fault_detection.rate_disagreement_threshold_rad_per_s").as_double();

    // ── Publishers ────────────────────────────────────────────────────────────
    // QoS: SensorDataQoS — best-effort, volatile, depth 10 (matches ROS2 sensor convention)
    const auto qos = rclcpp::SensorDataQoS();

    primary_pub_  = this->create_publisher<sensor_msgs::msg::Imu>(
        "/ghost/imu/primary",  qos);
    watchdog_pub_ = this->create_publisher<sensor_msgs::msg::Imu>(
        "/ghost/imu/watchdog", qos);
    fault_pub_    = this->create_publisher<std_msgs::msg::Bool>(
        "/ghost/imu/fault", rclcpp::QoS(1).reliable());

    RCLCPP_INFO(this->get_logger(),
        "ImuNode constructed. SPI: %s @ %d Hz, ICM DRDY: GPIO%d, "
        "I2C: /dev/i2c-%d, MPU DRDY: GPIO%d",
        spi_device_.c_str(), spi_clock_hz_, icm_drdy_gpio_,
        i2c_bus_, mpu_drdy_gpio_);
}

// ── Destructor ────────────────────────────────────────────────────────────────

ImuNode::~ImuNode() {
    running_.store(false);

    // Threads are blocked on DRDY poll(). Signal them to wake by closing the
    // hardware — readBlocking() will throw, the catch in each loop exits.
    if (icm_) { icm_->close(); }
    if (mpu_) { mpu_->close(); }

    if (primary_thread_.joinable())  { primary_thread_.join();  }
    if (watchdog_thread_.joinable()) { watchdog_thread_.join(); }

    RCLCPP_INFO(this->get_logger(), "ImuNode shut down cleanly.");
}

// ── initialize() ──────────────────────────────────────────────────────────────

void ImuNode::initialize() {
    // Construct drivers — no hardware calls yet (constructors are trivial)
    const std::string i2c_dev = "/dev/i2c-" + std::to_string(i2c_bus_);

    icm_ = std::make_unique<ICM42688P>(spi_device_, spi_clock_hz_, icm_drdy_gpio_);
    mpu_ = std::make_unique<MPU6050>(i2c_dev, mpu_drdy_gpio_);

    // Open hardware, configure registers, arm DRDY interrupts
    RCLCPP_INFO(this->get_logger(), "Initializing ICM-42688-P...");
    icm_->initialize();
    RCLCPP_INFO(this->get_logger(), "ICM-42688-P OK (WHO_AM_I = 0x47)");

    RCLCPP_INFO(this->get_logger(), "Initializing MPU-6050...");
    mpu_->initialize();
    RCLCPP_INFO(this->get_logger(), "MPU-6050 OK (WHO_AM_I = 0x68)");

    // Start reader threads
    running_.store(true);
    primary_thread_  = std::thread(&ImuNode::primaryLoop,  this);
    watchdog_thread_ = std::thread(&ImuNode::watchdogLoop, this);

    RCLCPP_INFO(this->get_logger(),
        "ImuNode initialized. Publishing on /ghost/imu/primary (1000 Hz) "
        "and /ghost/imu/watchdog (400 Hz).");
}

// ── Primary IMU thread — ICM-42688-P at 1000 Hz ───────────────────────────────

void ImuNode::primaryLoop() {
    Eigen::Vector3d accel;
    Eigen::Vector3d gyro;

    while (running_.load()) {
        try {
            // Blocks until DRDY rising edge on GPIO17 (PREEMPT_RT < 50μs jitter)
            icm_->readBlocking(accel, gyro);
        } catch (const std::exception& e) {
            if (!running_.load()) { break; }  // normal shutdown path
            RCLCPP_ERROR(this->get_logger(),
                "ICM-42688-P read error: %s", e.what());
            continue;
        }

        // TODO: wire primary IMU output directly into ESKF once filter node is written.
        //       Call eskf_->predict(gyro, accel, dt) here using the hardware-timestamped
        //       CLOCK_MONOTONIC time from the DRDY ISR (not this->now()).

        // Share latest reading with watchdog thread for agreement check
        {
            std::lock_guard<std::mutex> lock(primary_mutex_);
            shared_primary_accel_ = accel;
            shared_primary_gyro_  = gyro;
            primary_data_valid_   = true;
        }

        // Publish /ghost/imu/primary
        auto header = std_msgs::msg::Header{};
        header.stamp    = this->now();
        header.frame_id = "imu_link";

        primary_pub_->publish(buildImuMsg(header, accel, gyro));
    }
}

// ── Watchdog IMU thread — MPU-6050 at 400 Hz ─────────────────────────────────

void ImuNode::watchdogLoop() {
    Eigen::Vector3d accel;
    Eigen::Vector3d gyro;

    // Issue 3 fix: track whether we were in a fault state on the previous
    // iteration so we can publish data=false exactly once when the fault clears.
    // Without this, eskf_node::faultCallback never receives data=false and
    // imu_fault_ becomes a permanent one-way latch.
    bool prev_faulted = false;

    while (running_.load()) {
        try {
            // Blocks until DRDY rising edge on GPIO27
            mpu_->readBlocking(accel, gyro);
        } catch (const std::exception& e) {
            if (!running_.load()) { break; }  // normal shutdown path
            RCLCPP_ERROR(this->get_logger(),
                "MPU-6050 read error: %s", e.what());
            continue;
        }

        // Publish /ghost/imu/watchdog
        auto header = std_msgs::msg::Header{};
        header.stamp    = this->now();
        header.frame_id = "imu_link_watchdog";

        watchdog_pub_->publish(buildImuMsg(header, accel, gyro));

        // Agreement check — requires at least one primary reading to be available
        Eigen::Vector3d ref_accel;
        Eigen::Vector3d ref_gyro;
        bool            valid = false;
        {
            std::lock_guard<std::mutex> lock(primary_mutex_);
            valid     = primary_data_valid_;
            ref_accel = shared_primary_accel_;
            ref_gyro  = shared_primary_gyro_;
        }

        if (!valid) { continue; }  // primary not yet running

        // GHOST_V10.md: "100ms moving window on attitude disagreement.
        // Transient spikes (vibration) clear in < 100ms — no false fault.
        // Primary (ICM-42688-P) always trusted — MPU-6050 fault = warning only."
        const bool agreed = mpu_->checkAgreement(
            ref_accel, ref_gyro, accel_threshold_mps2_, gyro_threshold_rps_);

        if (!agreed) {
            RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
                "IMU watchdog FAULT: persistent disagreement > 100 ms "
                "(accel_thr=%.3f m/s², gyro_thr=%.4f rad/s). "
                "Primary ICM-42688-P continues as trusted source.",
                accel_threshold_mps2_, gyro_threshold_rps_);

            auto fault_msg = std_msgs::msg::Bool{};
            fault_msg.data = true;
            fault_pub_->publish(fault_msg);
            prev_faulted = true;

        } else if (prev_faulted) {
            // Fault cleared: sensors agree again.  Publish data=false exactly
            // once so eskf_node can re-enable the gravity update.
            // Without this publish, eskf_node::imu_fault_ is a permanent latch.
            RCLCPP_INFO(this->get_logger(),
                "IMU watchdog fault cleared — sensors agree again.");
            auto fault_msg = std_msgs::msg::Bool{};
            fault_msg.data = false;
            fault_pub_->publish(fault_msg);
            prev_faulted = false;
        }
    }
}

// ── buildImuMsg ───────────────────────────────────────────────────────────────

sensor_msgs::msg::Imu ImuNode::buildImuMsg(
    const std_msgs::msg::Header& header,
    const Eigen::Vector3d& accel_mps2,
    const Eigen::Vector3d& gyro_rps)
{
    sensor_msgs::msg::Imu msg;
    msg.header = header;

    msg.angular_velocity.x = gyro_rps.x();
    msg.angular_velocity.y = gyro_rps.y();
    msg.angular_velocity.z = gyro_rps.z();

    msg.linear_acceleration.x = accel_mps2.x();
    msg.linear_acceleration.y = accel_mps2.y();
    msg.linear_acceleration.z = accel_mps2.z();

    // Orientation is unknown — ESKF computes it from IMU integration.
    // REP-145: covariance[0] = -1 signals "orientation not available".
    msg.orientation_covariance[0] = -1.0;

    // Leave angular_velocity_covariance and linear_acceleration_covariance as
    // zero (unknown). Set from Allan Variance ARW after Phase 1 characterisation.

    return msg;
}

}  // namespace ghost

// ── main ──────────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    rclcpp::init(argc, argv);

    auto node = std::make_shared<ghost::ImuNode>();

    try {
        node->initialize();
    } catch (const std::exception& e) {
        RCLCPP_FATAL(node->get_logger(),
            "Hardware initialization failed: %s", e.what());
        rclcpp::shutdown();
        return 1;
    }

    rclcpp::spin(node);
    rclcpp::shutdown();
    return 0;
}
