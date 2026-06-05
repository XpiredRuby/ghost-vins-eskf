#include "mavlink_bridge.hpp"

// POSIX socket headers — Raspberry Pi / Ubuntu 22.04 only
// These headers do not exist on Windows; this file is intentionally Linux-only.
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <cmath>
#include <cstring>
#include <stdexcept>

namespace ghost {

// ── Helpers ───────────────────────────────────────────────────────────────────

// Reinterpret the opaque byte buffer as a sockaddr_in reference.
// Layout is guaranteed by C: sockaddr_in is a POD struct, 16 bytes on ARMv8.
static sockaddr_in& destAddr(uint8_t* buf) {
    return *reinterpret_cast<sockaddr_in*>(buf);
}

static const sockaddr_in& destAddr(const uint8_t* buf) {
    return *reinterpret_cast<const sockaddr_in*>(buf);
}

// ── Constructor / Destructor ──────────────────────────────────────────────────

MavlinkBridge::MavlinkBridge(const std::string& host, uint16_t port) {
    openSocket(host, port);
}

MavlinkBridge::~MavlinkBridge() {
    if (sock_fd_ >= 0) {
        ::close(sock_fd_);
        sock_fd_ = -1;
    }
}

// ── openSocket ────────────────────────────────────────────────────────────────

void MavlinkBridge::openSocket(const std::string& host, uint16_t port) {
    sock_fd_ = ::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock_fd_ < 0) {
        throw std::runtime_error("MavlinkBridge: socket() failed: " +
                                 std::string(std::strerror(errno)));
    }

    // Set O_NONBLOCK so that send() never stalls the guidance loop even if the
    // kernel send buffer is momentarily full.
    const int flags = ::fcntl(sock_fd_, F_GETFL, 0);
    if (flags < 0 || ::fcntl(sock_fd_, F_SETFL, flags | O_NONBLOCK) < 0) {
        ::close(sock_fd_);
        sock_fd_ = -1;
        throw std::runtime_error("MavlinkBridge: fcntl(O_NONBLOCK) failed: " +
                                 std::string(std::strerror(errno)));
    }

    sockaddr_in& addr = destAddr(dest_addr_buf_);
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port   = htons(port);

    if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) != 1) {
        ::close(sock_fd_);
        sock_fd_ = -1;
        throw std::runtime_error("MavlinkBridge: invalid host address: " + host);
    }
}

// ── send ─────────────────────────────────────────────────────────────────────

void MavlinkBridge::send(const Eigen::Vector3d& a_cmd_NED, uint64_t timestamp_us) {
    if (sock_fd_ < 0) { return; }

    // ── Acceleration → SET_ATTITUDE_TARGET mapping ────────────────────────────
    //
    // GHOST_V10.md specifies SET_POSITION_TARGET_LOCAL_NED (msg ID 84) with
    // mask 0b0000110000111111 as the target message — it has dedicated afx/afy/afz
    // fields for direct acceleration feedforward.  This implementation uses
    // SET_ATTITUDE_TARGET (msg ID 82) as a pragmatic placeholder because it
    // exercises OFFBOARD mode without requiring firmware acceleration-path
    // verification.  Switch to SET_POSITION_TARGET_LOCAL_NED once confirmed.
    //
    // Mapping rationale (small-angle, NED frame, FRD body frame assumed):
    //
    //   a_North [m/s²]: produce northward thrust → pitch nose down
    //     body_pitch_rate = -a_North / g   (negative: nose-down in FRD = neg. pitch)
    //
    //   a_East [m/s²]: produce eastward thrust → roll right
    //     body_roll_rate  = +a_East / g
    //
    //   a_Down [m/s², NED positive-down]:
    //     hover: a_Down = 0 → thrust = 0.5 (50%)
    //     upward cmd: a_Down < 0 → thrust > 0.5
    //     downward cmd: a_Down > 0 → thrust < 0.5
    //     thrust = clamp((g - a_Down) / (2g), 0, 1)
    //
    //   Yaw: ProNav does not command yaw → body_yaw_rate = 0.
    //
    //   type_mask = 0x80:
    //     bit 7 = 1: IGNORE attitude quaternion
    //     bits 0-2 = 0: USE body roll/pitch/yaw rates
    //     bit 6 = 0: USE thrust
    //
    // Limitation: PX4 interprets these as rate commands through its inner-loop
    // rate controller, not as direct acceleration setpoints.  The mapping is
    // an approximation valid for small a_cmd magnitudes relative to g.
    //
    // TODO: replace with SET_POSITION_TARGET_LOCAL_NED (msg ID 84) or
    //       ACTUATOR_CONTROL / TRAJECTORY_SETPOINT once PX4 firmware
    //       acceleration feedforward path is confirmed against Gazebo SITL.

    constexpr double g = 9.81;

    const auto body_roll_rate  = static_cast<float>( a_cmd_NED.y() / g);
    const auto body_pitch_rate = static_cast<float>(-a_cmd_NED.x() / g);
    constexpr float body_yaw_rate = 0.0f;

    const float thrust = static_cast<float>(
        std::clamp((g - a_cmd_NED.z()) / (2.0 * g), 0.0, 1.0));

    // Attitude quaternion: identity — ignored by type_mask but must be valid.
    float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};  // w, x, y, z

    // bit 7 = ignore attitude; bits 0-2 = use body rates; bit 6 = use thrust
    constexpr uint8_t type_mask = 0x80;

    // time_boot_ms: PX4 uses this for stale-command detection (> 500ms → OFFBOARD exits)
    const auto time_boot_ms = static_cast<uint32_t>(timestamp_us / 1000ULL);

    // thrust_body: required by MAVLink c_library_v2 newer API.
    // [0] = body-x thrust (unused), [1] = body-y thrust (unused),
    // [2] = body-z thrust (positive = down in FRD; matches the scalar thrust field).
    float thrust_body[3] = {0.0f, 0.0f, static_cast<float>(thrust)};

    mavlink_message_t msg;
    mavlink_msg_set_attitude_target_pack(
        system_id_,
        component_id_,
        &msg,
        time_boot_ms,
        target_system_,
        target_component_,
        type_mask,
        q,
        body_roll_rate,
        body_pitch_rate,
        body_yaw_rate,
        thrust,
        thrust_body);

    uint8_t buf[MAVLINK_MAX_PACKET_LEN];
    const uint16_t len = mavlink_msg_to_send_buffer(buf, &msg);

    // MSG_DONTWAIT: if kernel send buffer is full, drop silently.
    // EAGAIN / EWOULDBLOCK are expected under transient UDP congestion and must
    // not stall the guidance loop.  All other errors are silently ignored here;
    // add telemetry logging if a persistent send-failure counter is needed.
    ::sendto(sock_fd_,
             buf,
             len,
             MSG_DONTWAIT,
             reinterpret_cast<const sockaddr*>(&destAddr(dest_addr_buf_)),
             sizeof(sockaddr_in));
}

}  // namespace ghost
