#pragma once

// ── MAVLink header detection ──────────────────────────────────────────────────
// The MAVLink C headers are not a system package on Ubuntu 22.04.
// To install:
//   git clone --depth 1 --recursive https://github.com/mavlink/c_library_v2.git \
//       third_party/mavlink_c
//   then in CMakeLists.txt:
//     target_include_directories(ghost_core PUBLIC third_party/mavlink_c)
//   which exposes: #include <common/mavlink.h>
//
// Alternatively: pip install pymavlink (installs headers under site-packages/pymavlink/dialects)
// but the C library path above is the canonical source.
#if __has_include(<common/mavlink.h>)
#  include <common/mavlink.h>
#elif __has_include(<mavlink/v2.0/common/mavlink.h>)
#  include <mavlink/v2.0/common/mavlink.h>
#elif __has_include(<mavlink/common/mavlink.h>)
#  include <mavlink/common/mavlink.h>
#else
#  error "MAVLink C headers not found. " \
         "Clone https://github.com/mavlink/c_library_v2.git into third_party/mavlink_c " \
         "and add: target_include_directories(ghost_core PUBLIC third_party/mavlink_c) " \
         "to CMakeLists.txt. See src/mavlink_bridge/mavlink_bridge.hpp for details."
#endif

#include <cstdint>
#include <string>

#include <Eigen/Dense>

namespace ghost {

// ─────────────────────────────────────────────────────────────────────────────
// MavlinkBridge
//
// Accepts a ProNav acceleration command in NED frame and delivers it to PX4
// SITL over a non-blocking UDP socket.
//
// NOTE — Message type used here vs. GHOST_V10.md spec:
//   GHOST_V10.md §ProNav specifies SET_POSITION_TARGET_LOCAL_NED (msg ID 84)
//   with type_mask 0b0000110000111111 to command pure acceleration feedforward.
//   That message has a dedicated afz/afy/afx acceleration field — ideal mapping.
//
//   This implementation uses SET_ATTITUDE_TARGET (msg ID 82) as a temporary
//   placeholder that works with the default PX4 SITL OFFBOARD mode profile
//   before the firmware acceleration-control path is verified.
//
//   The mapping used here is:
//     body_roll_rate  = a_East  / g   [rad/s equivalent]  — small-angle approx
//     body_pitch_rate = -a_North / g  [rad/s equivalent]  — negative: nose-down
//     body_yaw_rate   = 0.0
//     thrust          = clamp((g - a_Down_NED) / (2g), 0, 1)
//   type_mask = 0x80: ignore attitude quaternion, use body rates + thrust.
//
// TODO: replace with SET_POSITION_TARGET_LOCAL_NED (msg ID 84) or
//       ACTUATOR_CONTROL / TRAJECTORY_SETPOINT once PX4 firmware acceleration
//       feedforward path is confirmed against the Gazebo SITL model.
//       See GHOST_V10.md §ProNav — MAVLink delivery for the target mask value.
// ─────────────────────────────────────────────────────────────────────────────
class MavlinkBridge {
public:
    // host: IP address string of PX4 SITL machine — "127.0.0.1" for localhost SITL
    // port: MAVLink UDP listen port — PX4 SITL default is 14540
    MavlinkBridge(const std::string& host, uint16_t port);
    ~MavlinkBridge();

    // Non-copyable — owns a POSIX socket file descriptor
    MavlinkBridge(const MavlinkBridge&)            = delete;
    MavlinkBridge& operator=(const MavlinkBridge&) = delete;

    // Send the ProNav acceleration command to PX4 SITL.
    //
    // a_cmd_NED:    acceleration command [m/s²], North-East-Down frame
    // timestamp_us: CLOCK_MONOTONIC source timestamp [microseconds]
    //
    // Non-blocking: uses MSG_DONTWAIT. If the kernel socket buffer is full
    // (EAGAIN / EWOULDBLOCK), the packet is silently dropped. The guidance
    // loop must not be stalled waiting for network I/O.
    void send(const Eigen::Vector3d& a_cmd_NED, uint64_t timestamp_us);

    // Returns true if the UDP socket opened successfully.
    bool isOpen() const { return sock_fd_ >= 0; }

private:
    void openSocket(const std::string& host, uint16_t port);

    int sock_fd_{-1};

    // sockaddr_in stored as raw bytes to avoid pulling <netinet/in.h> into
    // every translation unit that includes this header.
    // sizeof(sockaddr_in) == 16 on all Linux/ARM targets.
    alignas(8) uint8_t dest_addr_buf_[16]{};

    uint8_t  system_id_{255};       // GCS system ID — PX4 SITL expects source != 1
    uint8_t  component_id_{0};      // MAVLink_COMP_ID_ALL
    uint8_t  target_system_{1};     // PX4 SITL default system ID
    uint8_t  target_component_{1};  // PX4 autopilot component ID
};

}  // namespace ghost
