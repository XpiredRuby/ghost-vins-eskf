#include "mpu6050.hpp"

// Linux I2C userspace interface
#include <linux/i2c-dev.h>  // I2C_SLAVE

// Linux GPIO character device v2 API (kernel ≥ 5.10; Ubuntu 22.04 = 5.15)
#include <linux/gpio.h>     // gpio_v2_line_request, GPIO_V2_GET_LINE_IOCTL, etc.

// POSIX I/O
#include <fcntl.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include <cerrno>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <string>

namespace ghost {

// ── Helpers ───────────────────────────────────────────────────────────────────

// Elapsed milliseconds between two CLOCK_MONOTONIC timespec values.
static double elapsedMs(const struct timespec& start, const struct timespec& end) {
    return (end.tv_sec  - start.tv_sec)  * 1000.0
         + (end.tv_nsec - start.tv_nsec) / 1.0e6;
}

// ── Construction / Destruction ────────────────────────────────────────────────

MPU6050::MPU6050(const std::string& i2c_dev, int drdy_gpio_pin)
    : i2c_dev_(i2c_dev), drdy_gpio_pin_(drdy_gpio_pin) {}

MPU6050::~MPU6050() { close(); }

// ── Public API ────────────────────────────────────────────────────────────────

void MPU6050::initialize() {
    openI2C();
    openGPIO();
    configureDevice();
}

void MPU6050::readBlocking(Eigen::Vector3d& accel_mps2,
                           Eigen::Vector3d& gyro_rps,
                           uint64_t&        hw_timestamp_ns) {
    // ── Wait for DRDY rising edge ─────────────────────────────────────────────
    struct pollfd pfd{};
    pfd.fd     = gpio_line_fd_;
    pfd.events = POLLIN;

    const int ret = ::poll(&pfd, 1, DRDY_POLL_TIMEOUT_MS);
    if (ret < 0) {
        throw std::runtime_error(
            "MPU6050: poll() on GPIO DRDY failed: " + std::string(std::strerror(errno)));
    }
    if (ret == 0) {
        throw std::runtime_error(
            "MPU6050: DRDY timeout after " + std::to_string(DRDY_POLL_TIMEOUT_MS) +
            " ms. Check GPIO27 wiring and that MPU-6050 WHO_AM_I = 0x68.");
    }

    // Consume the edge event — required before the next poll() call.
    // event.timestamp_ns is CLOCK_MONOTONIC nanoseconds latched by the kernel
    // GPIO interrupt handler at the exact hardware edge.
    struct gpio_v2_line_event event{};
    if (::read(gpio_line_fd_, &event, sizeof(event)) != static_cast<ssize_t>(sizeof(event))) {
        throw std::runtime_error(
            "MPU6050: failed to read GPIO edge event: " + std::string(std::strerror(errno)));
    }
    hw_timestamp_ns = event.timestamp_ns;

    // ── 14-byte I2C burst: ACCEL_XOUT_H (0x3B) → GYRO_ZOUT_L (0x48) ─────────
    // Layout (RM-MPU-6000A-00 §4.17):
    //   byte  0–1:  ACCEL_XOUT_H, L
    //   byte  2–3:  ACCEL_YOUT_H, L
    //   byte  4–5:  ACCEL_ZOUT_H, L
    //   byte  6–7:  TEMP_OUT_H, L    (temperature — discarded)
    //   byte  8–9:  GYRO_XOUT_H, L
    //   byte 10–11: GYRO_YOUT_H, L
    //   byte 12–13: GYRO_ZOUT_H, L
    uint8_t buf[14]{};
    readBytes(REG_ACCEL_XOUT_H, buf, 14);

    // ── Raw → 16-bit signed ───────────────────────────────────────────────────
    const auto raw_ax = static_cast<int16_t>((static_cast<uint16_t>(buf[0])  << 8) | buf[1]);
    const auto raw_ay = static_cast<int16_t>((static_cast<uint16_t>(buf[2])  << 8) | buf[3]);
    const auto raw_az = static_cast<int16_t>((static_cast<uint16_t>(buf[4])  << 8) | buf[5]);
    // buf[6..7] = temperature — skip
    const auto raw_gx = static_cast<int16_t>((static_cast<uint16_t>(buf[8])  << 8) | buf[9]);
    const auto raw_gy = static_cast<int16_t>((static_cast<uint16_t>(buf[10]) << 8) | buf[11]);
    const auto raw_gz = static_cast<int16_t>((static_cast<uint16_t>(buf[12]) << 8) | buf[13]);

    // ── LSB → SI units ────────────────────────────────────────────────────────
    // Accel ±8g:    4096 LSB/g    → ACCEL_SCALE_MPS2 = 9.80665 / 4096.0
    // Gyro ±1000dps: 32.8 LSB/dps → GYRO_SCALE_RPS   = π / (180 × 32.8)
    accel_mps2.x() = static_cast<double>(raw_ax) * ACCEL_SCALE_MPS2;
    accel_mps2.y() = static_cast<double>(raw_ay) * ACCEL_SCALE_MPS2;
    accel_mps2.z() = static_cast<double>(raw_az) * ACCEL_SCALE_MPS2;

    gyro_rps.x() = static_cast<double>(raw_gx) * GYRO_SCALE_RPS;
    gyro_rps.y() = static_cast<double>(raw_gy) * GYRO_SCALE_RPS;
    gyro_rps.z() = static_cast<double>(raw_gz) * GYRO_SCALE_RPS;

    // Cache for checkAgreement()
    last_accel_ = accel_mps2;
    last_gyro_  = gyro_rps;
}

bool MPU6050::checkAgreement(const Eigen::Vector3d& ref_accel,
                              const Eigen::Vector3d& ref_gyro,
                              double accel_threshold_mps2,
                              double gyro_threshold_rps) {
    // GHOST_V10.md: "Run both IMUs through independent attitude integration.
    // 100ms moving window — fault if persistent disagreement."
    //
    // Implementation: compare raw vector norm differences against thresholds.
    // This is a simplified version of the full attitude-disagreement computation
    // described in GHOST_V10.md; the production implementation should compute
    // theta_err = 2·arccos(|delta_q.w|) from independent quaternion integrations.
    //
    // The 100 ms window is implemented via CLOCK_MONOTONIC wall-clock timestamps:
    //   - When disagreement first appears, arm the fault timer.
    //   - If disagreement persists continuously for ≥ FAULT_WINDOW_MS, set fault.
    //   - If agreement is restored before the window expires, reset the timer.
    // GHOST_V10.md FMEA: "Transient spikes (vibration) clear in < 100ms — no false fault."

    const double accel_diff = (ref_accel - last_accel_).norm();
    const double gyro_diff  = (ref_gyro  - last_gyro_).norm();
    const bool   exceeded   = (accel_diff > accel_threshold_mps2)
                           || (gyro_diff  > gyro_threshold_rps);

    if (exceeded) {
        if (!fault_timer_armed_) {
            // First sample of a new disagreement window — start the clock
            ::clock_gettime(CLOCK_MONOTONIC, &fault_start_);
            fault_timer_armed_ = true;
        } else {
            // Disagreement is persisting — check elapsed time
            struct timespec now{};
            ::clock_gettime(CLOCK_MONOTONIC, &now);
            if (elapsedMs(fault_start_, now) >= FAULT_WINDOW_MS) {
                faulted_ = true;
            }
        }
    } else {
        // Agreement restored — reset the 100 ms window
        // Fault clears automatically: MPU-6050 is a warning-only watchdog
        // GHOST_V10.md: "Primary (ICM-42688-P) always trusted — MPU-6050 fault = warning only"
        fault_timer_armed_ = false;
        faulted_           = false;
    }

    return !faulted_;
}

void MPU6050::close() {
    if (gpio_line_fd_ >= 0) { ::close(gpio_line_fd_); gpio_line_fd_ = -1; }
    if (gpio_chip_fd_ >= 0) { ::close(gpio_chip_fd_); gpio_chip_fd_ = -1; }
    if (i2c_fd_       >= 0) { ::close(i2c_fd_);       i2c_fd_       = -1; }
}

// ── Private: openI2C ──────────────────────────────────────────────────────────

void MPU6050::openI2C() {
    i2c_fd_ = ::open(i2c_dev_.c_str(), O_RDWR);
    if (i2c_fd_ < 0) {
        throw std::runtime_error(
            "MPU6050: cannot open " + i2c_dev_ + ": " + std::strerror(errno) +
            "\nTo enable I2C on Raspberry Pi, add 'dtparam=i2c_arm=on' to "
            "/boot/firmware/config.txt and reboot. "
            "Verify with: ls /dev/i2c*");
    }

    // Set the target I2C slave address for all subsequent read()/write() calls
    if (::ioctl(i2c_fd_, I2C_SLAVE, static_cast<long>(I2C_ADDR)) < 0) {
        throw std::runtime_error(
            "MPU6050: I2C_SLAVE ioctl failed for address 0x68: " +
            std::string(std::strerror(errno)));
    }
}

// ── Private: openGPIO ─────────────────────────────────────────────────────────

void MPU6050::openGPIO() {
    gpio_chip_fd_ = ::open("/dev/gpiochip0", O_RDONLY);
    if (gpio_chip_fd_ < 0) {
        throw std::runtime_error(
            "MPU6050: cannot open /dev/gpiochip0: " + std::string(std::strerror(errno)) +
            "\nVerify the GPIO character device is available on this kernel.");
    }

    struct gpio_v2_line_request req{};
    req.offsets[0]       = static_cast<uint32_t>(drdy_gpio_pin_);
    req.num_lines        = 1;
    req.config.flags     = GPIO_V2_LINE_FLAG_INPUT | GPIO_V2_LINE_FLAG_EDGE_RISING;
    req.config.num_attrs = 0;
    std::strncpy(req.consumer, "mpu6050-drdy", sizeof(req.consumer) - 1);

    if (::ioctl(gpio_chip_fd_, GPIO_V2_GET_LINE_IOCTL, &req) < 0) {
        throw std::runtime_error(
            "MPU6050: GPIO_V2_GET_LINE_IOCTL failed for GPIO" +
            std::to_string(drdy_gpio_pin_) + ": " + std::strerror(errno));
    }

    gpio_line_fd_ = req.fd;
}

// ── Private: configureDevice ──────────────────────────────────────────────────

void MPU6050::configureDevice() {
    // 1. Wake device from sleep — default state after power-on is SLEEP=1
    //    PWR_MGMT_1 = 0x01: SLEEP=0, CLKSEL=001 (X-axis gyroscope PLL reference)
    //    RM-MPU-6000A §8.1: "It is highly recommended to configure the device to
    //    use one of the gyroscope references as the clock source."
    //    CLKSEL=0 (internal 8 MHz RC oscillator) is less stable and less accurate.
    writeRegister(REG_PWR_MGMT_1, 0x01);
    ::usleep(10000);  // wait 10 ms for gyro PLL to lock

    // 2. Verify WHO_AM_I = 0x68
    const uint8_t who = readRegister(REG_WHO_AM_I);
    if (who != WHO_AM_I_EXPECTED) {
        throw std::runtime_error(
            "MPU6050: WHO_AM_I = 0x" + [who]() {
                char buf[8]; std::snprintf(buf, sizeof(buf), "%02X", who); return std::string(buf);
            }() + ", expected 0x68. Wrong chip, wrong I2C address, or wiring error.");
    }

    // 3. Sample rate divider for 400 Hz ODR
    //    With DLPF disabled: internal gyro rate = 8 kHz
    //    Sample Rate = 8000 / (1 + SMPLRT_DIV) → SMPLRT_DIV = 19 → 400 Hz
    writeRegister(REG_SMPLRT_DIV, 19);

    // 4. Disable DLPF (CONFIG = 0x00) — keeps 8 kHz internal gyro rate
    writeRegister(REG_CONFIG, 0x00);

    // 5. Gyroscope: ±1000 dps
    //    GYRO_CONFIG bits [4:3] FS_SEL = 10 → 0x10
    writeRegister(REG_GYRO_CONFIG, 0x10);

    // 6. Accelerometer: ±8g
    //    ACCEL_CONFIG bits [4:3] AFS_SEL = 10 → 0x10
    writeRegister(REG_ACCEL_CONFIG, 0x10);

    // 7. INT pin: push-pull, active-high, 50 μs pulse, clear on any read
    //    INT_PIN_CFG bit 4: INT_RD_CLEAR=1 — reading any data register clears INT
    writeRegister(REG_INT_PIN_CFG, 0x10);

    // 8. Enable data-ready interrupt on INT pin
    //    INT_ENABLE bit 0: DATA_RDY_EN=1
    writeRegister(REG_INT_ENABLE, 0x01);
}

// ── Private: I2C primitives ───────────────────────────────────────────────────

void MPU6050::writeRegister(uint8_t reg, uint8_t value) {
    uint8_t buf[2] = {reg, value};
    if (::write(i2c_fd_, buf, 2) != 2) {
        throw std::runtime_error(
            "MPU6050: I2C write reg 0x" +
            [reg]() { char b[8]; std::snprintf(b, sizeof(b), "%02X", reg); return std::string(b); }()
            + " failed: " + std::strerror(errno));
    }
}

uint8_t MPU6050::readRegister(uint8_t reg) {
    uint8_t value = 0;
    if (::write(i2c_fd_, &reg, 1) != 1) {
        throw std::runtime_error(
            "MPU6050: I2C write address for read failed: " + std::string(std::strerror(errno)));
    }
    if (::read(i2c_fd_, &value, 1) != 1) {
        throw std::runtime_error(
            "MPU6050: I2C read failed: " + std::string(std::strerror(errno)));
    }
    return value;
}

void MPU6050::readBytes(uint8_t reg, uint8_t* buf, uint8_t len) {
    // No heap allocation — caller provides a stack-allocated buffer.
    // I2C burst read: write the start register address, then read `len` bytes.
    // The MPU-6050 auto-increments the register pointer on each byte read.
    if (::write(i2c_fd_, &reg, 1) != 1) {
        throw std::runtime_error(
            "MPU6050: I2C burst read address write failed: " + std::string(std::strerror(errno)));
    }
    const ssize_t nread = ::read(i2c_fd_, buf, len);
    if (nread != static_cast<ssize_t>(len)) {
        throw std::runtime_error(
            "MPU6050: I2C burst read returned " + std::to_string(nread) +
            " bytes, expected " + std::to_string(len) + ": " + std::strerror(errno));
    }
}

}  // namespace ghost
