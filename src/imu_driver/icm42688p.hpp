#pragma once

// ── Platform guard ────────────────────────────────────────────────────────────
// This driver uses Linux SPI userspace (/dev/spidev) and the Linux GPIO
// character device API (/dev/gpiochip0). It will not compile on Windows or macOS.
#ifndef __linux__
#  error "icm42688p.hpp is Linux-only. Compile on the Raspberry Pi target."
#endif

#include <cstdint>
#include <string>

#include <Eigen/Dense>

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// ICM42688P
//
// SPI driver for the ICM-42688-P 6-axis IMU.
// Target: Raspberry Pi 4B, Ubuntu 22.04, PREEMPT_RT kernel.
//
// Hardware wiring (GHOST_V10.md §IMU Driver):
//   SPI0 CS0   → /dev/spidev0.0   (ICM-42688-P CE pin)
//   DRDY       → GPIO17            (edge-triggered rising interrupt)
//   SPI clock  → 24 MHz, mode 3 (CPOL=1, CPHA=1)
//
// To enable SPI on Raspberry Pi add to /boot/firmware/config.txt:
//   dtparam=spi=on
// then reboot. Verify with: ls /dev/spidev*
//
// The constructor does not open hardware; call initialize() explicitly.
// ─────────────────────────────────────────────────────────────────────────────
class ICM42688P {
public:
    // spi_dev:       SPI device node, e.g. "/dev/spidev0.0"
    // spi_speed_hz:  SPI clock [Hz]. ICM-42688-P max is 24 MHz (DS-000347 §4.1).
    // drdy_gpio_pin: BCM pin number for DRDY. GHOST uses GPIO17.
    ICM42688P(const std::string& spi_dev, int spi_speed_hz, int drdy_gpio_pin);
    ~ICM42688P();

    // Non-copyable — owns POSIX file descriptors
    ICM42688P(const ICM42688P&)            = delete;
    ICM42688P& operator=(const ICM42688P&) = delete;

    // Open /dev/spidev and /dev/gpiochip0, configure SPI mode 3 and clock,
    // arm DRDY edge interrupt, soft-reset the sensor, verify WHO_AM_I = 0x47,
    // configure ±16g / ±2000 dps at 1000 Hz ODR, and enable DRDY on INT1.
    // Throws std::runtime_error if any step fails.
    void initialize();

    // Block until the next DRDY rising edge on GPIO17, then execute a single
    // 14-byte SPI burst read covering TEMP_DATA1 → GYRO_DATA_Z0.
    //
    // accel_mps2: accelerometer [m/s²], sensor body frame X/Y/Z
    // gyro_rps:   gyroscope    [rad/s], sensor body frame X/Y/Z
    //
    // TODO: connect to ESKF input once ROS2 node is written
    //       (pass accel_mps2 and gyro_rps into ESKF::predict())
    void readBlocking(Eigen::Vector3d& accel_mps2, Eigen::Vector3d& gyro_rps);

    // Release all file descriptors. Safe to call even if initialize() was not called.
    void close();

    // ── Register map — ICM-42688-P datasheet DS-000347 §14 ───────────────────
    static constexpr uint8_t REG_DEVICE_CONFIG  = 0x11;  // soft reset
    static constexpr uint8_t REG_INT_CONFIG     = 0x14;  // INT1/INT2 pin config
    static constexpr uint8_t REG_TEMP_DATA1     = 0x1D;  // temperature MSB
    static constexpr uint8_t REG_TEMP_DATA0     = 0x1E;  // temperature LSB
    static constexpr uint8_t REG_ACCEL_DATA_X1  = 0x1F;  // accel X MSB
    static constexpr uint8_t REG_ACCEL_DATA_X0  = 0x20;  // accel X LSB
    static constexpr uint8_t REG_ACCEL_DATA_Y1  = 0x21;  // accel Y MSB
    static constexpr uint8_t REG_ACCEL_DATA_Y0  = 0x22;  // accel Y LSB
    static constexpr uint8_t REG_ACCEL_DATA_Z1  = 0x23;  // accel Z MSB
    static constexpr uint8_t REG_ACCEL_DATA_Z0  = 0x24;  // accel Z LSB
    static constexpr uint8_t REG_GYRO_DATA_X1   = 0x25;  // gyro X MSB
    static constexpr uint8_t REG_GYRO_DATA_X0   = 0x26;  // gyro X LSB
    static constexpr uint8_t REG_GYRO_DATA_Y1   = 0x27;  // gyro Y MSB
    static constexpr uint8_t REG_GYRO_DATA_Y0   = 0x28;  // gyro Y LSB
    static constexpr uint8_t REG_GYRO_DATA_Z1   = 0x29;  // gyro Z MSB
    static constexpr uint8_t REG_GYRO_DATA_Z0   = 0x2A;  // gyro Z LSB
    static constexpr uint8_t REG_PWR_MGMT0      = 0x4E;  // power management
    static constexpr uint8_t REG_GYRO_CONFIG0   = 0x4F;  // gyro FS and ODR
    static constexpr uint8_t REG_ACCEL_CONFIG0  = 0x50;  // accel FS and ODR
    static constexpr uint8_t REG_INT_CONFIG1    = 0x64;  // interrupt timing
    static constexpr uint8_t REG_INT_SOURCE0    = 0x65;  // INT1 source select
    static constexpr uint8_t REG_WHO_AM_I       = 0x75;  // identity register

    // WHO_AM_I expected value (DS-000347 §14.1). Halt at startup if not 0x47.
    // GHOST_V10.md: "WHO_AM_I: must return 0x47 (not ICM-20689 register map)"
    static constexpr uint8_t WHO_AM_I_EXPECTED  = 0x47;

private:
    // ── Sensitivity — DS-000347 §3.1 ─────────────────────────────────────────
    // Accel ±16g:     2048 LSB/g    → scale = 9.80665 / 2048   [m/s² per LSB]
    // Gyro ±2000 dps: 16.4 LSB/dps → scale = π / (180 × 16.4) [rad/s per LSB]
    static constexpr double kPi               = 3.14159265358979323846;
    static constexpr double ACCEL_SCALE_MPS2  = 9.80665 / 2048.0;
    static constexpr double GYRO_SCALE_RPS    = kPi / (180.0 * 16.4);

    // ── DRDY poll timeout ─────────────────────────────────────────────────────
    // At 1000 Hz ODR, a DRDY edge fires every 1 ms. 200 ms timeout = 200 missed
    // edges — indicates hardware failure, not transient jitter.
    static constexpr int DRDY_POLL_TIMEOUT_MS = 200;

    std::string spi_dev_;
    int         spi_speed_hz_;
    int         drdy_gpio_pin_;

    int spi_fd_{-1};        // /dev/spidev file descriptor
    int gpio_chip_fd_{-1};  // /dev/gpiochip0 file descriptor
    int gpio_line_fd_{-1};  // GPIO line file descriptor (edge event source)

    void    openSPI();
    void    openGPIO();
    void    configureDevice();
    void    writeRegister(uint8_t reg, uint8_t value);
    uint8_t readRegister(uint8_t reg);

    // Burst read: reads `len` bytes from consecutive registers starting at
    // `start_reg`. Caller must provide a stack-allocated buffer of at least `len` bytes.
    // SPI protocol: TX = [0x80 | start_reg, 0x00×len], RX = [dummy, data×len].
    void readBurst(uint8_t start_reg, uint8_t* buf, uint8_t len);
};

}  // namespace ghost
