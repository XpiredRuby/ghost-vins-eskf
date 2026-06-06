#pragma once

// ── Platform guard ────────────────────────────────────────────────────────────
// This driver uses Linux I2C userspace (/dev/i2c-1) and the Linux GPIO
// character device API (/dev/gpiochip0). It will not compile on Windows or macOS.
#ifndef __linux__
#  error "mpu6050.hpp is Linux-only. Compile on the Raspberry Pi target."
#endif

#include <cstdint>
#include <ctime>
#include <string>

#include <Eigen/Dense>

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// MPU6050
//
// I2C driver for the MPU-6050 watchdog IMU.
// Target: Raspberry Pi 4B, Ubuntu 22.04, PREEMPT_RT kernel.
//
// Hardware wiring (GHOST_V10.md §IMU Driver):
//   I2C1 SDA/SCL → /dev/i2c-1   (400 kHz fast mode)
//   AD0           → GND           (I2C address = 0x68)
//   DRDY (INT)    → GPIO27        (edge-triggered rising interrupt)
//
// Role: fault-detection watchdog only.
//   "MPU-6050 fault = warning only. Never enters target tracking propagation."
//   GHOST_V10.md: "100ms moving window on attitude disagreement — not raw IMU threshold"
//
// To enable I2C on Raspberry Pi add to /boot/firmware/config.txt:
//   dtparam=i2c_arm=on
// then reboot. Verify with: ls /dev/i2c*
// ─────────────────────────────────────────────────────────────────────────────
class MPU6050 {
public:
    // i2c_dev:       I2C device node, e.g. "/dev/i2c-1"
    // drdy_gpio_pin: BCM pin number for DRDY interrupt. GHOST uses GPIO27.
    MPU6050(const std::string& i2c_dev, int drdy_gpio_pin);
    ~MPU6050();

    // Non-copyable — owns POSIX file descriptors
    MPU6050(const MPU6050&)            = delete;
    MPU6050& operator=(const MPU6050&) = delete;

    // Open /dev/i2c-1 and /dev/gpiochip0, arm DRDY edge interrupt,
    // wake the device, configure ±8g / ±1000 dps at 400 Hz ODR,
    // enable DRDY on INT pin. Verify WHO_AM_I = 0x68.
    // Throws std::runtime_error if any step fails.
    void initialize();

    // Block until the next DRDY rising edge on GPIO27, then execute a single
    // 14-byte I2C burst read from ACCEL_XOUT_H (0x3B) through GYRO_ZOUT_L (0x48).
    // Stores result internally for use by checkAgreement().
    //
    // accel_mps2: accelerometer [m/s²], sensor body frame X/Y/Z
    // gyro_rps:   gyroscope    [rad/s], sensor body frame X/Y/Z
    void readBlocking(Eigen::Vector3d& accel_mps2, Eigen::Vector3d& gyro_rps);

    // Compare last MPU-6050 reading against reference values from ICM-42688-P.
    // Sets the internal fault flag if disagreement exceeds either threshold
    // continuously for ≥ 100 ms.
    // GHOST_V10.md: "100ms moving window — fault if persistent disagreement"
    //
    // ref_accel / ref_gyro: ICM-42688-P output from the same time step
    // accel_threshold_mps2: disagreement limit for accel vector norm difference
    // gyro_threshold_rps:   disagreement limit for gyro vector norm difference
    //
    // Returns true if within thresholds (no fault), false if fault is active.
    bool checkAgreement(const Eigen::Vector3d& ref_accel,
                        const Eigen::Vector3d& ref_gyro,
                        double accel_threshold_mps2,
                        double gyro_threshold_rps);

    // Returns true if the persistent disagreement fault flag is set.
    bool isFaulted() const { return faulted_; }

    // Release all file descriptors. Safe to call even if initialize() was not called.
    void close();

    // ── Register map — MPU-6050 datasheet RM-MPU-6000A-00 §4 ─────────────────
    static constexpr uint8_t REG_SMPLRT_DIV    = 0x19;  // sample rate divider
    static constexpr uint8_t REG_CONFIG         = 0x1A;  // DLPF and FSYNC config
    static constexpr uint8_t REG_GYRO_CONFIG    = 0x1B;  // gyro full-scale
    static constexpr uint8_t REG_ACCEL_CONFIG   = 0x1C;  // accel full-scale
    static constexpr uint8_t REG_INT_PIN_CFG    = 0x37;  // interrupt pin behavior
    static constexpr uint8_t REG_INT_ENABLE      = 0x38;  // interrupt enable
    static constexpr uint8_t REG_ACCEL_XOUT_H   = 0x3B;  // burst read start
    static constexpr uint8_t REG_ACCEL_XOUT_L   = 0x3C;
    static constexpr uint8_t REG_ACCEL_YOUT_H   = 0x3D;
    static constexpr uint8_t REG_ACCEL_YOUT_L   = 0x3E;
    static constexpr uint8_t REG_ACCEL_ZOUT_H   = 0x3F;
    static constexpr uint8_t REG_ACCEL_ZOUT_L   = 0x40;
    static constexpr uint8_t REG_TEMP_OUT_H      = 0x41;  // temperature MSB (discarded)
    static constexpr uint8_t REG_TEMP_OUT_L      = 0x42;  // temperature LSB (discarded)
    static constexpr uint8_t REG_GYRO_XOUT_H    = 0x43;
    static constexpr uint8_t REG_GYRO_XOUT_L    = 0x44;
    static constexpr uint8_t REG_GYRO_YOUT_H    = 0x45;
    static constexpr uint8_t REG_GYRO_YOUT_L    = 0x46;
    static constexpr uint8_t REG_GYRO_ZOUT_H    = 0x47;
    static constexpr uint8_t REG_GYRO_ZOUT_L    = 0x48;
    static constexpr uint8_t REG_PWR_MGMT_1     = 0x6B;  // power management
    static constexpr uint8_t REG_WHO_AM_I        = 0x75;  // identity register

    // WHO_AM_I returns bits [6:1] of I2C address. With AD0=0: 0x68.
    static constexpr uint8_t WHO_AM_I_EXPECTED   = 0x68;

    // I2C device address (AD0 pin = GND)
    static constexpr uint8_t I2C_ADDR            = 0x68;

private:
    // ── Sensitivity — MPU-6050 PS-MPU-6000A-00 §6.2 ─────────────────────────
    // Accel ±8g:     4096 LSB/g    → scale = 9.80665 / 4096.0   [m/s² per LSB]
    // Gyro ±1000dps: 32.8 LSB/dps → scale = π / (180.0 × 32.8) [rad/s per LSB]
    static constexpr double kPi              = 3.14159265358979323846;
    static constexpr double ACCEL_SCALE_MPS2 = 9.80665 / 4096.0;
    static constexpr double GYRO_SCALE_RPS   = kPi / (180.0 * 32.8);

    // DRDY poll timeout — at 400 Hz, 200 ms = 80 missed edges → hardware failure
    static constexpr int DRDY_POLL_TIMEOUT_MS = 200;

    // Persistent fault window — GHOST_V10.md: "100ms moving window"
    static constexpr double FAULT_WINDOW_MS = 100.0;

    std::string i2c_dev_;
    int         drdy_gpio_pin_;

    int i2c_fd_{-1};         // /dev/i2c-1 file descriptor
    int gpio_chip_fd_{-1};   // /dev/gpiochip0 file descriptor
    int gpio_line_fd_{-1};   // GPIO line event file descriptor

    // Last measurement — populated by readBlocking(), consumed by checkAgreement()
    Eigen::Vector3d last_accel_{Eigen::Vector3d::Zero()};
    Eigen::Vector3d last_gyro_{Eigen::Vector3d::Zero()};

    // Fault state — 100 ms sliding window via wall-clock timestamps
    bool            faulted_{false};
    bool            fault_timer_armed_{false};
    struct timespec fault_start_{0, 0};  // CLOCK_MONOTONIC time when fault first detected

    void    openI2C();
    void    openGPIO();
    void    configureDevice();
    void    writeRegister(uint8_t reg, uint8_t value);
    uint8_t readRegister(uint8_t reg);

    // Burst read: writes `reg` as start address, then reads `len` bytes.
    // Caller provides a stack-allocated buffer of at least `len` bytes.
    void readBytes(uint8_t reg, uint8_t* buf, uint8_t len);
};

}  // namespace ghost
