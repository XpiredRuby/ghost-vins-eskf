#pragma once

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <std_msgs/msg/bool.hpp>

#include <Eigen/Dense>

// Forward-declare the driver classes to avoid pulling Linux-only SPI/GPIO
// headers into every translation unit that includes this header.
namespace ghost {
class ICM42688P;
class MPU6050;
}  // namespace ghost

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// ImuNode
//
// ROS2 Humble node that drives the primary ICM-42688-P (1000 Hz, SPI) and
// watchdog MPU-6050 (400 Hz, I2C) IMUs, publishes raw sensor_msgs/Imu messages,
// and publishes a fault flag when the two IMUs disagree beyond threshold for
// more than 100 ms.
//
// Topic layout:
//   /ghost/imu/primary    sensor_msgs/msg/Imu   1000 Hz  — ICM-42688-P output
//   /ghost/imu/watchdog   sensor_msgs/msg/Imu    400 Hz  — MPU-6050 output
//   /ghost/imu/fault      std_msgs/msg/Bool              — watchdog fault flag
//
// Lifecycle:
//   1. Construct node (declares parameters, creates publishers).
//   2. Call initialize() once after node construction to open hardware
//      and start reader threads. Hardware is never touched in the constructor.
//   3. spin() or spin_some() as normal.
//   4. Destructor joins threads and closes hardware.
//
// Parameters (loaded from config/imu.yaml via ROS2 parameter server):
//   icm42688p.spi_device           string  "/dev/spidev0.0"
//   icm42688p.spi_clock_hz         int     10000000
//   icm42688p.drdy_gpio            int     17
//   mpu6050.i2c_bus                int     1        → "/dev/i2c-1"
//   mpu6050.drdy_gpio              int     27
//   mpu6050.fault_detection.accel_disagreement_threshold_m_per_s2  double  1.0
//   mpu6050.fault_detection.rate_disagreement_threshold_rad_per_s   double  0.05
// ─────────────────────────────────────────────────────────────────────────────
class ImuNode : public rclcpp::Node {
public:
    explicit ImuNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions{});
    ~ImuNode() override;

    // Open hardware (SPI, I2C, GPIO), configure both IMUs, and start reader
    // threads. Must be called exactly once after construction, before spinning.
    // Throws std::runtime_error if any hardware step fails.
    void initialize();

private:
    // ── Reader threads ────────────────────────────────────────────────────────

    // Primary IMU thread — calls ICM42688P::readBlocking() at 1000 Hz
    void primaryLoop();

    // Watchdog IMU thread — calls MPU6050::readBlocking() at 400 Hz,
    // then compares against the latest primary reading
    void watchdogLoop();

    // ── Helpers ───────────────────────────────────────────────────────────────

    // Build a sensor_msgs::msg::Imu from accel + gyro vectors.
    // Orientation covariance is set to -1 (unknown) — ESKF computes attitude.
    static sensor_msgs::msg::Imu buildImuMsg(
        const std_msgs::msg::Header& header,
        const Eigen::Vector3d& accel_mps2,
        const Eigen::Vector3d& gyro_rps);

    // ── Hardware drivers ──────────────────────────────────────────────────────
    std::unique_ptr<ICM42688P> icm_;
    std::unique_ptr<MPU6050>   mpu_;

    // ── Publishers ────────────────────────────────────────────────────────────
    rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr primary_pub_;
    rclcpp::Publisher<sensor_msgs::msg::Imu>::SharedPtr watchdog_pub_;
    rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr   fault_pub_;

    // ── Reader threads ────────────────────────────────────────────────────────
    std::thread           primary_thread_;
    std::thread           watchdog_thread_;
    std::atomic<bool>     running_{false};

    // ── Cross-thread primary IMU data (primary → watchdog for agreement check) ──
    // Protected by primary_mutex_. Watchdog thread reads this to call
    // MPU6050::checkAgreement() without blocking the primary thread.
    mutable std::mutex  primary_mutex_;
    Eigen::Vector3d     shared_primary_accel_{Eigen::Vector3d::Zero()};
    Eigen::Vector3d     shared_primary_gyro_{Eigen::Vector3d::Zero()};
    bool                primary_data_valid_{false};

    // ── Parameters ────────────────────────────────────────────────────────────
    std::string spi_device_;
    int         spi_clock_hz_{0};
    int         icm_drdy_gpio_{0};
    int         i2c_bus_{0};
    int         mpu_drdy_gpio_{0};
    double      accel_threshold_mps2_{0.0};
    double      gyro_threshold_rps_{0.0};
};

}  // namespace ghost
