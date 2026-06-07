cmake_minimum_required(VERSION 3.16)
project(ghost-vins-eskf LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── Required dependencies ──────────────────────────────────────────────────────
find_package(Eigen3 REQUIRED NO_MODULE)
find_package(GTest  REQUIRED)

# ── MAVLink C headers (optional — required for mavlink_bridge) ────────────────
# Clone with: git clone --depth 1 --recursive \
#     https://github.com/mavlink/c_library_v2.git third_party/mavlink_c
# The clone exposes: #include <common/mavlink.h>
set(MAVLINK_INCLUDE_DIR "${CMAKE_SOURCE_DIR}/third_party/mavlink_c"
    CACHE PATH "Path to MAVLink C library v2 headers (c_library_v2 clone root)")

if(EXISTS "${MAVLINK_INCLUDE_DIR}/common/mavlink.h")
    set(MAVLINK_FOUND TRUE)
    message(STATUS "MAVLink headers found: ${MAVLINK_INCLUDE_DIR}")
else()
    set(MAVLINK_FOUND FALSE)
    message(WARNING
        "MAVLink headers NOT found at ${MAVLINK_INCLUDE_DIR}. "
        "mavlink_bridge will not compile. "
        "Run: git clone --depth 1 --recursive "
        "https://github.com/mavlink/c_library_v2.git third_party/mavlink_c")
endif()

# ── ghost_core static library ─────────────────────────────────────────────────
# Core GNC files — no ROS2, no libcamera, no apriltag.
# vision_node.cpp is intentionally excluded: it is a standalone executable.
set(GHOST_CORE_SOURCES
    src/attitude_filter/eskf.cpp
    src/attitude_filter/sage_husa.cpp
    src/attitude_filter/zaru.cpp
    src/target_tracker/cv_filter.cpp
    src/target_tracker/ctrv_filter.cpp
    src/guidance/pronav.cpp
    src/imu_driver/icm42688p.cpp
    src/imu_driver/mpu6050.cpp
)

if(MAVLINK_FOUND)
    list(APPEND GHOST_CORE_SOURCES src/mavlink_bridge/mavlink_bridge.cpp)
endif()

add_library(ghost_core STATIC ${GHOST_CORE_SOURCES})

target_include_directories(ghost_core PUBLIC
    ${CMAKE_SOURCE_DIR}/src
)

if(MAVLINK_FOUND)
    target_include_directories(ghost_core PUBLIC ${MAVLINK_INCLUDE_DIR})
endif()

target_link_libraries(ghost_core PUBLIC
    Eigen3::Eigen
)

# ── vision_node — standalone executable (optional, Pi-only) ───────────────────
# Requires libcamera (camera driver) and apriltag (tag detection).
# Install on Raspberry Pi OS:  sudo apt install libcamera-dev libapriltag-dev
#
# vision_node.cpp is NOT added to ghost_core — it has hard ROS2 and hardware
# dependencies that must not infect the portable GNC library.
#
# Note: find_package(PkgConfig) sets PKG_CONFIG_FOUND (all-caps), not
# PkgConfig_FOUND.  The guard below uses the correct variable name.
find_package(PkgConfig QUIET)
if(PKG_CONFIG_FOUND)
    pkg_check_modules(LIBCAMERA QUIET libcamera)
    pkg_check_modules(APRILTAG  QUIET apriltag)
endif()

if(LIBCAMERA_FOUND AND APRILTAG_FOUND)
    message(STATUS
        "libcamera ${LIBCAMERA_VERSION} and apriltag ${APRILTAG_VERSION} found "
        "— building vision_node")
    add_executable(vision_node
        src/ros2_nodes/vision_node.cpp
    )
    target_include_directories(vision_node PRIVATE
        ${CMAKE_SOURCE_DIR}/src
        ${LIBCAMERA_INCLUDE_DIRS}
        ${APRILTAG_INCLUDE_DIRS}
    )
    target_link_libraries(vision_node PRIVATE
        ghost_core
        ${LIBCAMERA_LIBRARIES}
        ${APRILTAG_LIBRARIES}
    )
    target_compile_options(vision_node PRIVATE ${LIBCAMERA_CFLAGS_OTHER})
else()
    message(WARNING
        "libcamera or apriltag NOT found — vision_node will not be built. "
        "On Raspberry Pi: sudo apt install libcamera-dev libapriltag-dev")
endif()

# ── ROS2 Humble node executables ──────────────────────────────────────────────
# Each node is a standalone executable that links against ghost_core (the
# portable GNC library) plus rclcpp and the message packages it actually uses.
#
# IMPORTANT: ROS2 node sources are NEVER added to ghost_core — ghost_core stays
# free of any ROS2 / hardware-framework dependency so it remains portable and
# unit-testable.  These targets only wrap the core library for deployment.
#
# The entire section is gated behind GHOST_BUILD_ROS2_NODES so the project can
# still be configured and built (ghost_core + tests + vision_node) on a machine
# without a sourced ROS2 Humble environment.  Disable with:
#     cmake -DGHOST_BUILD_ROS2_NODES=OFF ..
option(GHOST_BUILD_ROS2_NODES
    "Build ROS2 node executables (requires sourced ROS2 Humble)" ON)

if(GHOST_BUILD_ROS2_NODES)
    find_package(rclcpp        REQUIRED)
    find_package(std_msgs      REQUIRED)
    find_package(geometry_msgs REQUIRED)
    find_package(sensor_msgs   REQUIRED)

    # imu_node — primary ICM-42688-P (SPI) + watchdog MPU-6050 (I2C).
    # Messages: sensor_msgs/Imu, std_msgs/Bool.
    add_executable(imu_node src/ros2_nodes/imu_node.cpp)
    target_include_directories(imu_node PRIVATE ${CMAKE_SOURCE_DIR}/src)
    target_link_libraries(imu_node PRIVATE
        ghost_core
        rclcpp::rclcpp
        ${sensor_msgs_TARGETS}
        ${std_msgs_TARGETS}
    )

    # eskf_node — 9-state attitude ESKF, ZARU, gravity update.
    # Messages: geometry_msgs (PoseWithCovarianceStamped, TransformStamped),
    #           sensor_msgs/Imu, std_msgs/Bool.
    add_executable(eskf_node src/ros2_nodes/eskf_node.cpp)
    target_include_directories(eskf_node PRIVATE ${CMAKE_SOURCE_DIR}/src)
    target_link_libraries(eskf_node PRIVATE
        ghost_core
        rclcpp::rclcpp
        ${geometry_msgs_TARGETS}
        ${sensor_msgs_TARGETS}
        ${std_msgs_TARGETS}
    )

    # tracker_node — CV/CTRV target tracking filters.
    # Messages: geometry_msgs (PoseStamped, PoseWithCovarianceStamped,
    #           TransformStamped, TwistWithCovarianceStamped), std_msgs/Bool.
    add_executable(tracker_node src/ros2_nodes/tracker_node.cpp)
    target_include_directories(tracker_node PRIVATE ${CMAKE_SOURCE_DIR}/src)
    target_link_libraries(tracker_node PRIVATE
        ghost_core
        rclcpp::rclcpp
        ${geometry_msgs_TARGETS}
        ${std_msgs_TARGETS}
    )

    # guidance_node — TPN ProNav + MAVLink bridge to PX4 SITL.
    # Messages: geometry_msgs (AccelStamped, PoseWithCovarianceStamped), std_msgs/Bool.
    #
    # Guarded by MAVLINK_FOUND: guidance_node.cpp includes mavlink_bridge.hpp, which
    # issues #error when the MAVLink C headers are absent, and the MavlinkBridge
    # implementation is only compiled into ghost_core under MAVLINK_FOUND.  Building
    # it without MAVLink would fail to compile and link, so it is conditional —
    # mirroring the vision_node pattern.  Clone the MAVLink headers (see top of this
    # file) to enable it.
    if(MAVLINK_FOUND)
        add_executable(guidance_node src/ros2_nodes/guidance_node.cpp)
        target_include_directories(guidance_node PRIVATE
            ${CMAKE_SOURCE_DIR}/src
            ${MAVLINK_INCLUDE_DIR}
        )
        target_link_libraries(guidance_node PRIVATE
            ghost_core
            rclcpp::rclcpp
            ${geometry_msgs_TARGETS}
            ${std_msgs_TARGETS}
        )
    else()
        message(WARNING
            "MAVLink headers NOT found — guidance_node will not be built. "
            "Clone https://github.com/mavlink/c_library_v2.git into third_party/mavlink_c "
            "to enable it.")
    endif()
else()
    message(STATUS
        "GHOST_BUILD_ROS2_NODES=OFF — skipping ROS2 node executables "
        "(imu_node, eskf_node, tracker_node, guidance_node). "
        "Building ghost_core, tests, and vision_node (if libcamera/apriltag found).")
endif()

# ── Test executables ──────────────────────────────────────────────────────────
enable_testing()

add_executable(test_eskf test/test_eskf.cpp)
target_link_libraries(test_eskf PRIVATE ghost_core GTest::GTest GTest::Main)
add_test(NAME test_eskf COMMAND test_eskf)

add_executable(test_pronav test/test_pronav.cpp)
target_link_libraries(test_pronav PRIVATE ghost_core GTest::GTest GTest::Main)
add_test(NAME test_pronav COMMAND test_pronav)
