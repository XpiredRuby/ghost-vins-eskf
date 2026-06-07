#include "icm42688p.hpp"

// Linux SPI userspace interface
#include <linux/spi/spidev.h>  // SPI_IOC_MESSAGE, spi_ioc_transfer, SPI_MODE_3

// Linux GPIO character device v2 API (kernel ≥ 5.10; Ubuntu 22.04 = 5.15)
#include <linux/gpio.h>        // gpio_v2_line_request, GPIO_V2_GET_LINE_IOCTL, etc.

// POSIX I/O
#include <fcntl.h>
#include <poll.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <stdexcept>
#include <string>

namespace ghost {

// ── Construction / Destruction ────────────────────────────────────────────────

ICM42688P::ICM42688P(const std::string& spi_dev, int spi_speed_hz, int drdy_gpio_pin)
    : spi_dev_(spi_dev), spi_speed_hz_(spi_speed_hz), drdy_gpio_pin_(drdy_gpio_pin) {}

ICM42688P::~ICM42688P() { close(); }

// ── Public API ────────────────────────────────────────────────────────────────

void ICM42688P::initialize() {
    openSPI();
    openGPIO();
    configureDevice();
}

void ICM42688P::readBlocking(Eigen::Vector3d& accel_mps2,
                             Eigen::Vector3d& gyro_rps,
                             uint64_t&        hw_timestamp_ns) {
    // ── Wait for DRDY rising edge ─────────────────────────────────────────────
    // poll() allows a timeout so a stuck DRDY line is detected rather than hanging
    // the guidance thread forever. At 1000 Hz, a 200 ms timeout = 200 missed edges.
    struct pollfd pfd{};
    pfd.fd     = gpio_line_fd_;
    pfd.events = POLLIN;

    const int ret = ::poll(&pfd, 1, DRDY_POLL_TIMEOUT_MS);
    if (ret < 0) {
        throw std::runtime_error(
            "ICM42688P: poll() on GPIO DRDY failed: " + std::string(std::strerror(errno)));
    }
    if (ret == 0) {
        throw std::runtime_error(
            "ICM42688P: DRDY timeout after " + std::to_string(DRDY_POLL_TIMEOUT_MS) +
            " ms. Check GPIO17 wiring and that ICM-42688-P WHO_AM_I = 0x47.");
    }

    // Consume the edge event — mandatory before the next poll() call.
    // event.timestamp_ns is CLOCK_MONOTONIC nanoseconds latched by the kernel GPIO
    // interrupt handler at the exact hardware edge — this is the true measurement time.
    // Propagated to the caller so the IMU message stamp uses this value instead of
    // a post-read this->now() call, which adds ≥50 μs software jitter at 1000 Hz.
    struct gpio_v2_line_event event{};
    if (::read(gpio_line_fd_, &event, sizeof(event)) != static_cast<ssize_t>(sizeof(event))) {
        throw std::runtime_error(
            "ICM42688P: failed to read GPIO edge event: " + std::string(std::strerror(errno)));
    }
    hw_timestamp_ns = event.timestamp_ns;

    // ── 14-byte SPI burst: TEMP_DATA1 (0x1D) → GYRO_DATA_Z0 (0x2A) ──────────
    // Layout (DS-000347 §14):
    //   byte  0–1:  TEMP_DATA1, TEMP_DATA0    (temperature,  discarded here)
    //   byte  2–3:  ACCEL_DATA_X1, X0
    //   byte  4–5:  ACCEL_DATA_Y1, Y0
    //   byte  6–7:  ACCEL_DATA_Z1, Z0
    //   byte  8–9:  GYRO_DATA_X1, X0
    //   byte 10–11: GYRO_DATA_Y1, Y0
    //   byte 12–13: GYRO_DATA_Z1, Z0
    uint8_t buf[14]{};
    readBurst(REG_TEMP_DATA1, buf, 14);

    // ── Raw → 16-bit signed ───────────────────────────────────────────────────
    // Big-endian: MSB register is the higher address byte in the struct.
    // Cast through int16_t to preserve sign extension.
    const auto raw_ax = static_cast<int16_t>((static_cast<uint16_t>(buf[2]) << 8) | buf[3]);
    const auto raw_ay = static_cast<int16_t>((static_cast<uint16_t>(buf[4]) << 8) | buf[5]);
    const auto raw_az = static_cast<int16_t>((static_cast<uint16_t>(buf[6]) << 8) | buf[7]);
    const auto raw_gx = static_cast<int16_t>((static_cast<uint16_t>(buf[8])  << 8) | buf[9]);
    const auto raw_gy = static_cast<int16_t>((static_cast<uint16_t>(buf[10]) << 8) | buf[11]);
    const auto raw_gz = static_cast<int16_t>((static_cast<uint16_t>(buf[12]) << 8) | buf[13]);

    // ── LSB → SI units ────────────────────────────────────────────────────────
    // Accel ±16g:     sensitivity = 2048 LSB/g   → ACCEL_SCALE_MPS2 = 9.80665/2048
    // Gyro ±2000 dps: sensitivity = 16.4 LSB/dps → GYRO_SCALE_RPS   = π/(180×16.4)
    accel_mps2.x() = static_cast<double>(raw_ax) * ACCEL_SCALE_MPS2;
    accel_mps2.y() = static_cast<double>(raw_ay) * ACCEL_SCALE_MPS2;
    accel_mps2.z() = static_cast<double>(raw_az) * ACCEL_SCALE_MPS2;

    gyro_rps.x() = static_cast<double>(raw_gx) * GYRO_SCALE_RPS;
    gyro_rps.y() = static_cast<double>(raw_gy) * GYRO_SCALE_RPS;
    gyro_rps.z() = static_cast<double>(raw_gz) * GYRO_SCALE_RPS;

}

void ICM42688P::close() {
    if (gpio_line_fd_ >= 0) { ::close(gpio_line_fd_); gpio_line_fd_ = -1; }
    if (gpio_chip_fd_ >= 0) { ::close(gpio_chip_fd_); gpio_chip_fd_ = -1; }
    if (spi_fd_       >= 0) { ::close(spi_fd_);       spi_fd_       = -1; }
}

// ── Private: openSPI ──────────────────────────────────────────────────────────

void ICM42688P::openSPI() {
    spi_fd_ = ::open(spi_dev_.c_str(), O_RDWR);
    if (spi_fd_ < 0) {
        throw std::runtime_error(
            "ICM42688P: cannot open " + spi_dev_ + ": " + std::strerror(errno) +
            "\nTo enable SPI on Raspberry Pi, add 'dtparam=spi=on' to "
            "/boot/firmware/config.txt and reboot. "
            "Verify with: ls /dev/spidev*");
    }

    // SPI mode 3: CPOL=1, CPHA=1 — required by ICM-42688-P (DS-000347 §4.1)
    const uint8_t mode = SPI_MODE_3;
    if (::ioctl(spi_fd_, SPI_IOC_WR_MODE, &mode) < 0) {
        throw std::runtime_error(
            "ICM42688P: SPI_IOC_WR_MODE failed: " + std::string(std::strerror(errno)));
    }

    // 8-bit word width
    const uint8_t bits = 8;
    if (::ioctl(spi_fd_, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0) {
        throw std::runtime_error(
            "ICM42688P: SPI_IOC_WR_BITS_PER_WORD failed: " + std::string(std::strerror(errno)));
    }

    // Clock speed
    const uint32_t speed = static_cast<uint32_t>(spi_speed_hz_);
    if (::ioctl(spi_fd_, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0) {
        throw std::runtime_error(
            "ICM42688P: SPI_IOC_WR_MAX_SPEED_HZ failed: " + std::string(std::strerror(errno)));
    }
}

// ── Private: openGPIO ─────────────────────────────────────────────────────────

void ICM42688P::openGPIO() {
    // Open the GPIO chip character device
    gpio_chip_fd_ = ::open("/dev/gpiochip0", O_RDONLY);
    if (gpio_chip_fd_ < 0) {
        throw std::runtime_error(
            "ICM42688P: cannot open /dev/gpiochip0: " + std::string(std::strerror(errno)) +
            "\nVerify 'dtparam=spi=on' is in /boot/firmware/config.txt and the "
            "kernel GPIO character device is loaded (modprobe gpio-generic).");
    }

    // Request GPIO line with rising-edge detection using the v2 API
    // (GPIO v2 API requires kernel ≥ 5.10; Ubuntu 22.04 ships ≥ 5.15)
    struct gpio_v2_line_request req{};
    req.offsets[0]      = static_cast<uint32_t>(drdy_gpio_pin_);
    req.num_lines       = 1;
    req.config.flags    = GPIO_V2_LINE_FLAG_INPUT | GPIO_V2_LINE_FLAG_EDGE_RISING;
    req.config.num_attrs = 0;
    std::strncpy(req.consumer, "icm42688p-drdy", sizeof(req.consumer) - 1);

    if (::ioctl(gpio_chip_fd_, GPIO_V2_GET_LINE_IOCTL, &req) < 0) {
        throw std::runtime_error(
            "ICM42688P: GPIO_V2_GET_LINE_IOCTL failed for GPIO" +
            std::to_string(drdy_gpio_pin_) + ": " + std::strerror(errno) +
            "\nEnsure no other process owns GPIO" + std::to_string(drdy_gpio_pin_) +
            " and that the DRDY pin is wired to the ICM-42688-P INT1 output.");
    }

    gpio_line_fd_ = req.fd;
}

// ── Private: configureDevice ──────────────────────────────────────────────────

void ICM42688P::configureDevice() {
    // 1. Soft reset — sets all registers to reset values
    writeRegister(REG_DEVICE_CONFIG, 0x01);
    ::usleep(2000);  // DS-000347 §12.1: wait ≥ 1 ms after reset

    // 2. Verify WHO_AM_I — halt immediately if wrong chip or wrong register map
    //    GHOST_V10.md: "WHO_AM_I: must return 0x47 (not ICM-20689 register map)"
    const uint8_t who = readRegister(REG_WHO_AM_I);
    if (who != WHO_AM_I_EXPECTED) {
        throw std::runtime_error(
            "ICM42688P: WHO_AM_I = 0x" + [who]() {
                char buf[8]; std::snprintf(buf, sizeof(buf), "%02X", who); return std::string(buf);
            }() + ", expected 0x47. Wrong chip or wiring error. "
            "ICM-20689 is discontinued — the correct part is ICM-42688-P.");
    }

    // 3. Clear INT_CONFIG1 async reset bit (DS-000347 §12.7 errata)
    //    Must be written before enabling interrupts or edge may not fire.
    writeRegister(REG_INT_CONFIG1, 0x00);

    // 4. Gyroscope: ±2000 dps, 1000 Hz ODR
    //    GYRO_CONFIG0 [7:5] GYRO_FS_SEL = 000 (±2000 dps)  → sensitivity 16.4 LSB/dps
    //    GYRO_CONFIG0 [3:0] GYRO_ODR    = 0110 (1 kHz)
    //    GHOST_V10.md: "ICM-42688-P ... ODR: 1000Hz"
    writeRegister(REG_GYRO_CONFIG0, 0x06);

    // 5. Accelerometer: ±16g, 1000 Hz ODR
    //    ACCEL_CONFIG0 [7:5] ACCEL_FS_SEL = 000 (±16g)      → sensitivity 2048 LSB/g
    //    ACCEL_CONFIG0 [3:0] ACCEL_ODR    = 0110 (1 kHz)
    writeRegister(REG_ACCEL_CONFIG0, 0x06);

    // 6. INT1 pin: push-pull, active-high, pulsed (8 μs pulse width)
    //    INT_CONFIG [2:0] = 0b011: MODE=pulsed, DRIVE=push-pull, POL=active-high
    writeRegister(REG_INT_CONFIG, 0x03);

    // 7. Route UI data-ready interrupt to INT1
    //    INT_SOURCE0 bit 3: UI_DRDY_INT1_EN = 1
    writeRegister(REG_INT_SOURCE0, 0x08);

    // 8. Power management: accel + gyro in low-noise mode
    //    PWR_MGMT0 [3:2] ACCEL_MODE = 11 (low-noise)
    //    PWR_MGMT0 [1:0] GYRO_MODE  = 11 (low-noise)
    writeRegister(REG_PWR_MGMT0, 0x0F);

    // 9. Wait for sensor startup — DS-000347 §12.9: gyro ready after 45 ms
    ::usleep(50000);
}

// ── Private: SPI primitives ───────────────────────────────────────────────────

void ICM42688P::writeRegister(uint8_t reg, uint8_t value) {
    // SPI write: MSB of address byte = 0 (write direction)
    uint8_t tx[2] = {static_cast<uint8_t>(reg & 0x7F), value};
    uint8_t rx[2] = {0, 0};

    struct spi_ioc_transfer tr{};
    tr.tx_buf        = reinterpret_cast<unsigned long>(tx);
    tr.rx_buf        = reinterpret_cast<unsigned long>(rx);
    tr.len           = 2;
    tr.speed_hz      = static_cast<uint32_t>(spi_speed_hz_);
    tr.bits_per_word = 8;
    tr.delay_usecs   = 0;

    if (::ioctl(spi_fd_, SPI_IOC_MESSAGE(1), &tr) < 1) {
        throw std::runtime_error(
            "ICM42688P: SPI write reg 0x" +
            [reg]() { char b[8]; std::snprintf(b, sizeof(b), "%02X", reg); return std::string(b); }()
            + " failed: " + std::strerror(errno));
    }
}

uint8_t ICM42688P::readRegister(uint8_t reg) {
    // SPI read: MSB of address byte = 1 (read direction)
    uint8_t tx[2] = {static_cast<uint8_t>(reg | 0x80), 0x00};
    uint8_t rx[2] = {0, 0};

    struct spi_ioc_transfer tr{};
    tr.tx_buf        = reinterpret_cast<unsigned long>(tx);
    tr.rx_buf        = reinterpret_cast<unsigned long>(rx);
    tr.len           = 2;
    tr.speed_hz      = static_cast<uint32_t>(spi_speed_hz_);
    tr.bits_per_word = 8;
    tr.delay_usecs   = 0;

    if (::ioctl(spi_fd_, SPI_IOC_MESSAGE(1), &tr) < 1) {
        throw std::runtime_error(
            "ICM42688P: SPI read reg 0x" +
            [reg]() { char b[8]; std::snprintf(b, sizeof(b), "%02X", reg); return std::string(b); }()
            + " failed: " + std::strerror(errno));
    }
    return rx[1];
}

void ICM42688P::readBurst(uint8_t start_reg, uint8_t* buf, uint8_t len) {
    // Stack-allocate the maximum transfer buffer (1 address + 14 data = 15 bytes).
    // No heap allocation — this function is on the 1000 Hz hot path.
    static constexpr uint8_t kMaxBurstLen = 15;
    if (len > kMaxBurstLen - 1) {
        throw std::runtime_error("ICM42688P: readBurst length exceeds maximum");
    }

    uint8_t tx[kMaxBurstLen]{};
    uint8_t rx[kMaxBurstLen]{};
    tx[0] = static_cast<uint8_t>(start_reg | 0x80);  // read bit set; remaining bytes = 0x00

    struct spi_ioc_transfer tr{};
    tr.tx_buf        = reinterpret_cast<unsigned long>(tx);
    tr.rx_buf        = reinterpret_cast<unsigned long>(rx);
    tr.len           = static_cast<uint32_t>(len + 1);  // +1 for the address byte
    tr.speed_hz      = static_cast<uint32_t>(spi_speed_hz_);
    tr.bits_per_word = 8;
    tr.delay_usecs   = 0;

    if (::ioctl(spi_fd_, SPI_IOC_MESSAGE(1), &tr) < 1) {
        throw std::runtime_error(
            "ICM42688P: SPI burst read failed: " + std::string(std::strerror(errno)));
    }

    // Skip rx[0] — it is the response during the address byte (undefined)
    std::memcpy(buf, rx + 1, len);
}

}  // namespace ghost
