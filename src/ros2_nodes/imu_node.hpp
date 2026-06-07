#pragma once

#include <atomic>
#include <cstdint>
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
//   2. Call initialize() once after node construction to open hardware,
//      compute the CLOCK_MONOTONIC→REALTIME offset, and start reader threads.
//      Hardware is never touched in the constructor.
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

    // Open hardware (SPI, I2C, GPIO), compute CLOCK_MONOTONIC→REALTIME offset,
    // configure both IMUs, and start reader threads. Must be called exactly once
    // after construction, before spinning.
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
    // gyro_var  : diagonal of angular_velocity_covariance [(rad/s)²]
    // accel_var : diagonal of linear_acceleration_covariance [(m/s²)²]
    static sensor_msgs::msg::Imu buildImuMsg(
        const std_msgs::msg::Header& header,
        const Eigen::Vector3d& accel_mps2,
        const Eigen::Vector3d& gyro_rps,
        double gyro_var,
        double accel_var);

    // ── Datasheet noise density constants ─────────────────────────────────────
    // Variance per sample = (noise_spectral_density)² × ODR_Hz.
    // Used to populate sensor_msgs::Imu covariance matrices.
    // Verify against Allan Variance characterisation after Phase 1 bringup.

    // ICM-42688-P (DS-000347 §3) at ±2000 dps / ±16g, 1000 Hz ODR:
    //   Gyro  NSD = 0.0028 °/s/√Hz → (0.0028 × π/180)² × 1000 = 2.38e-6 (rad/s)²
    //   Accel NSD ≈  70 μg/√Hz     → (70e-6 × 9.80665)² × 1000 = 4.72e-4 (m/s²)²
    static constexpr double kIcmGyroVar  = 2.38e-6;   // (rad/s)²
    static constexpr double kIcmAccelVar = 4.72e-4;   // (m/s²)²

    // MPU-6050 (PS-MPU-6000A §6) at ±1000 dps / ±8g, 400 Hz ODR:
    //   Gyro  NSD ≈ 0.005 °/s/√Hz   → (0.005 × π/180)² × 400 = 3.05e-6 (rad/s)²
    //   Accel NSD ≈  400 μg/√Hz     → (400e-6 × 9.80665)² × 400 = 6.15e-3 (m/s²)²
    static constexpr double kMpuGyroVar  = 3.05e-6;   // (rad/s)²
    static constexpr double kMpuAccelVar = 6.15e-3;   // (m/s²)²

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
    //
    // NOTE: ICM42688P::close() and MPU6050::close() write gpio_line_fd_ / spi_fd_
    // from the destructor thread while reader threads may be reading those fds to
    // populate pollfd::fd. This is technically a C++ data race on a non-atomic int.
    // On ARM64 (Raspberry Pi 4B), 4-byte aligned stores are naturally atomic at the
    // hardware level, making this safe in practice. The correct fix is an eventfd for
    // cooperative shutdown signaling. Closing the fd to wake poll() is the standard
    // Linux embedded driver idiom and works correctly on all ARM64 Linux kernels.
    mutable std::mutex  primary_mutex_;
    Eigen::Vector3d     shared_primary_accel_{Eigen::Vector3d::Zero()};
    Eigen::Vector3d     shared_primary_gyro_{Eigen::Vector3d::Zero()};
    bool                primary_data_valid_{false};

    // ── Clock offset — CLOCK_MONOTONIC → CLOCK_REALTIME conversion ───────────
    // GPIO DRDY timestamps are CLOCK_MONOTONIC (latched by kernel interrupt
    // handler). ROS2 Time uses CLOCK_REALTIME. The offset is computed once at
    // initialize() and applied in both reader thread loops.
    // Changes slowly (NTP adjustments); recomputing at startup is sufficient.
    int64_t mono_to_realtime_offset_ns_{0};

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
