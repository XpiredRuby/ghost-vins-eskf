cmake_minimum_required(VERSION 3.16)
project(ghost_x_estimators LANGUAGES CXX)

option(GHOST_X_ENABLE_SANITIZERS "Enable address/undefined sanitizers" OFF)
option(GHOST_X_WARNINGS_AS_ERRORS "Treat compiler warnings as errors" ON)
option(GHOST_X_BUILD_TESTS "Build GoogleTest verification" ON)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(Eigen3 3.3 REQUIRED NO_MODULE)

set(GHOST_X_WARNING_FLAGS -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Wformat=2)
if(GHOST_X_WARNINGS_AS_ERRORS)
  list(APPEND GHOST_X_WARNING_FLAGS -Werror)
endif()

add_library(ghost_x_estimators
  src/config.cpp
  src/linear_model.cpp
  src/kalman_filter.cpp
  src/imm.cpp
  src/mode_bank.cpp
)
target_include_directories(ghost_x_estimators PUBLIC include)
target_link_libraries(ghost_x_estimators PUBLIC Eigen3::Eigen)
target_compile_options(ghost_x_estimators PRIVATE ${GHOST_X_WARNING_FLAGS})

if(GHOST_X_ENABLE_SANITIZERS AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(ghost_x_estimators PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(ghost_x_estimators PUBLIC -fsanitize=address,undefined)
endif()

add_executable(ghost_x_estimator_cli src/estimator_cli.cpp)
target_link_libraries(ghost_x_estimator_cli PRIVATE ghost_x_estimators)
target_compile_options(ghost_x_estimator_cli PRIVATE ${GHOST_X_WARNING_FLAGS})

if(GHOST_X_BUILD_TESTS)
  enable_testing()
  find_package(GTest REQUIRED)
  add_executable(ghost_x_cpp_tests test/test_estimators.cpp test/test_config.cpp)
  target_link_libraries(ghost_x_cpp_tests PRIVATE ghost_x_estimators GTest::gtest_main)
  target_compile_options(ghost_x_cpp_tests PRIVATE ${GHOST_X_WARNING_FLAGS})
  include(GoogleTest)
  gtest_discover_tests(ghost_x_cpp_tests)
endif()

install(TARGETS ghost_x_estimators ghost_x_estimator_cli)
install(DIRECTORY include/ DESTINATION include)
install(FILES config/default_estimator.cfg DESTINATION share/ghost_x_estimators/config)
