#include "imu_node.hpp"

// Driver headers — Linux-only; this TU only compiles on the Pi target
#include "imu_driver/icm42688p.hpp"
#include "imu_driver/mpu6050.hpp"

#include <cerrno>      // errno
#include <cstring>     // std::strerror
#include <ctime>       // clock_gettime, CLOCK_REALTIME, CLOCK_MONOTONIC
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

    // Threads are blocked on DRDY poll(). Closing the hardware fd causes
    // poll() to return with POLLNVAL, waking the thread so it can check
    // running_ == false and exit. See note in imu_node.hpp regarding the
    // ARM64 fd data-race analysis.
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

    // ── Compute CLOCK_MONOTONIC → CLOCK_REALTIME offset ──────────────────────
    // GPIO v2 DRDY event timestamps are CLOCK_MONOTONIC (latched by the kernel
    // interrupt handler at the exact hardware edge). ROS2 Time uses CLOCK_REALTIME.
    // The two clocks differ by a near-constant offset. We measure it once here
    // by issuing back-to-back clock_gettime() calls to minimise the cross-clock
    // measurement error (on a PREEMPT_RT kernel this is < 1 μs).
    // The offset is applied in both reader thread loops to convert each hardware
    // DRDY timestamp to a correct ROS2 wall-clock Time value.
    {
        struct timespec rt{}, mono{};
        if (::clock_gettime(CLOCK_REALTIME, &rt) < 0) {
            throw std::runtime_error(
                "ImuNode: clock_gettime(CLOCK_REALTIME) failed while computing "
                "the MONOTONIC→REALTIME offset: " + std::string(std::strerror(errno)));
        }
        if (::clock_gettime(CLOCK_MONOTONIC, &mono) < 0) {
            throw std::runtime_error(
                "ImuNode: clock_gettime(CLOCK_MONOTONIC) failed while computing "
                "the MONOTONIC→REALTIME offset: " + std::string(std::strerror(errno)));
        }
        mono_to_realtime_offset_ns_ =
            (static_cast<int64_t>(rt.tv_sec)   * 1'000'000'000LL + rt.tv_nsec)
          - (static_cast<int64_t>(mono.tv_sec) * 1'000'000'000LL + mono.tv_nsec);
    }
    RCLCPP_INFO(this->get_logger(),
        "CLOCK_MONOTONIC→REALTIME offset: %lld ns",
        static_cast<long long>(mono_to_realtime_offset_ns_));

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
    uint64_t        hw_ts_ns = 0;

    // Outer catch: any exception from publish(), get_logger(), get_clock(), or
    // other ROS2 calls that escapes the inner hardware-error catch would otherwise
    // propagate out of the thread function and call std::terminate(). Log it and
    // exit cleanly so the destructor can join the thread.
    try {
        while (running_.load()) {
            try {
                // Blocks until DRDY rising edge on GPIO17 (PREEMPT_RT < 50μs jitter).
                // hw_ts_ns is CLOCK_MONOTONIC nanoseconds latched by the kernel
                // interrupt handler — the true measurement time.
                icm_->readBlocking(accel, gyro, hw_ts_ns);
            } catch (const std::exception& e) {
                if (!running_.load()) { break; }  // normal shutdown path
                RCLCPP_ERROR(this->get_logger(),
                    "ICM-42688-P read error: %s", e.what());
                continue;
            }

            // Share latest reading with watchdog thread for agreement check.
            {
                std::lock_guard<std::mutex> lock(primary_mutex_);
                shared_primary_accel_ = accel;
                shared_primary_gyro_  = gyro;
                primary_data_valid_   = true;
            }

            // Stamp using the hardware DRDY timestamp (CLOCK_MONOTONIC) converted
            // to CLOCK_REALTIME via the offset computed in initialize().
            // This eliminates the SPI transfer latency (~12 μs at 10 MHz) and
            // PREEMPT_RT scheduler jitter (≤50 μs) that this->now() would add,
            // making the ESKF predict() dt accurate to within the kernel ISR latency.
            auto header = std_msgs::msg::Header{};
            header.frame_id = "imu_link";
            header.stamp    = rclcpp::Time(
                static_cast<int64_t>(hw_ts_ns) + mono_to_realtime_offset_ns_);

            primary_pub_->publish(
                buildImuMsg(header, accel, gyro, kIcmGyroVar, kIcmAccelVar));
        }
    } catch (const std::exception& e) {
        if (running_.load()) {
            RCLCPP_ERROR(this->get_logger(),
                "primaryLoop: unexpected exception — thread exiting: %s", e.what());
        }
    } catch (...) {
        if (running_.load()) {
            RCLCPP_ERROR(this->get_logger(),
                "primaryLoop: unknown exception — thread exiting.");
        }
    }
}

// ── Watchdog IMU thread — MPU-6050 at 400 Hz ─────────────────────────────────

void ImuNode::watchdogLoop() {
    Eigen::Vector3d accel;
    Eigen::Vector3d gyro;
    uint64_t        hw_ts_ns = 0;

    // Track whether we were in a fault state on the previous iteration so we
    // can publish data=false exactly once when the fault clears.
    // Without this, eskf_node::imu_fault_ becomes a permanent one-way latch.
    bool prev_faulted = false;

    // Outer catch: same rationale as primaryLoop(). publish(), get_logger(), and
    // get_clock() can throw; without this the thread would call std::terminate().
    try {
        while (running_.load()) {
            try {
                // Blocks until DRDY rising edge on GPIO27
                mpu_->readBlocking(accel, gyro, hw_ts_ns);
            } catch (const std::exception& e) {
                if (!running_.load()) { break; }  // normal shutdown path
                RCLCPP_ERROR(this->get_logger(),
                    "MPU-6050 read error: %s", e.what());
                continue;
            }

            // Stamp using the hardware DRDY timestamp (CLOCK_MONOTONIC converted
            // to CLOCK_REALTIME). Consistent with primaryLoop() stamping so
            // timestamp deltas between the two IMU streams are meaningful.
            auto header = std_msgs::msg::Header{};
            header.frame_id = "imu_link_watchdog";
            header.stamp    = rclcpp::Time(
                static_cast<int64_t>(hw_ts_ns) + mono_to_realtime_offset_ns_);

            watchdog_pub_->publish(
                buildImuMsg(header, accel, gyro, kMpuGyroVar, kMpuAccelVar));

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
    } catch (const std::exception& e) {
        if (running_.load()) {
            RCLCPP_ERROR(this->get_logger(),
                "watchdogLoop: unexpected exception — thread exiting: %s", e.what());
        }
    } catch (...) {
        if (running_.load()) {
            RCLCPP_ERROR(this->get_logger(),
                "watchdogLoop: unknown exception — thread exiting.");
        }
    }
}

// ── buildImuMsg ───────────────────────────────────────────────────────────────

sensor_msgs::msg::Imu ImuNode::buildImuMsg(
    const std_msgs::msg::Header& header,
    const Eigen::Vector3d& accel_mps2,
    const Eigen::Vector3d& gyro_rps,
    double gyro_var,
    double accel_var)
{
    sensor_msgs::msg::Imu msg;
    msg.header = header;

    msg.angular_velocity.x = gyro_rps.x();
    msg.angular_velocity.y = gyro_rps.y();
    msg.angular_velocity.z = gyro_rps.z();

    msg.linear_acceleration.x = accel_mps2.x();
    msg.linear_acceleration.y = accel_mps2.y();
    msg.linear_acceleration.z = accel_mps2.z();

    // REP-145: orientation_covariance[0] = -1 signals orientation not available.
    // ESKF computes attitude from IMU integration — no orientation in raw messages.
    msg.orientation_covariance[0] = -1.0;

    // Diagonal noise covariance from datasheet noise spectral density at the
    // configured ODR: variance = NSD² × ODR_Hz. Off-diagonal elements are zero
    // (axes assumed uncorrelated). The caller passes sensor-specific constants
    // (kIcmGyroVar / kIcmAccelVar for the primary, kMpuGyroVar / kMpuAccelVar
    // for the watchdog). Verify against Allan Variance after Phase 1 bringup.
    //
    // Covariance layout: row-major 3×3 stored as std::array<double,9>.
    // Diagonal indices: [0]=XX, [4]=YY, [8]=ZZ.
    msg.angular_velocity_covariance[0] = gyro_var;
    msg.angular_velocity_covariance[4] = gyro_var;
    msg.angular_velocity_covariance[8] = gyro_var;

    msg.linear_acceleration_covariance[0] = accel_var;
    msg.linear_acceleration_covariance[4] = accel_var;
    msg.linear_acceleration_covariance[8] = accel_var;

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
