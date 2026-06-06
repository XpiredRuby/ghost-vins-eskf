cmake_minimum_required(VERSION 3.16)
project(ghost-vins-eskf LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── Dependencies ──────────────────────────────────────────────────────────────
find_package(Eigen3 REQUIRED NO_MODULE)
find_package(GTest REQUIRED)

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

# ── Test executables ──────────────────────────────────────────────────────────
enable_testing()

add_executable(test_eskf test/test_eskf.cpp)
target_link_libraries(test_eskf PRIVATE ghost_core GTest::GTest GTest::Main)
add_test(NAME test_eskf COMMAND test_eskf)

add_executable(test_pronav test/test_pronav.cpp)
target_link_libraries(test_pronav PRIVATE ghost_core GTest::GTest GTest::Main)
add_test(NAME test_pronav COMMAND test_pronav)
