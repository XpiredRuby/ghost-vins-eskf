#include <gtest/gtest.h>
#include "guidance/pronav.hpp"

// Test 1: Target ahead, drone closing — a_cmd nonzero and finite
TEST(ProNavTest, ClosingTarget_NonzeroCommand) {
    ProNav pn(3.0, 1.5, 1.0);

    Eigen::Vector3d x_target(10.0, 2.0, 0.0);
    Eigen::Vector3d x_drone(0.0, 0.0, 0.0);

    // First call initializes — returns zero
    pn.compute(x_target, x_drone, 0.01);

    // Move drone closer
    x_drone = Eigen::Vector3d(1.0, 0.0, 0.0);

    Eigen::Vector3d a_cmd = pn.compute(x_target, x_drone, 0.01);

    EXPECT_TRUE(a_cmd.allFinite());
    EXPECT_GT(a_cmd.norm(), 0.0);
}

// Test 2: Range below cutoff — a_cmd must be exactly zero
TEST(ProNavTest, TerminalCoast_ZeroCommand) {
    ProNav pn(3.0, 1.5, 1.0);

    // Target is only 1.0m away — below r_cutoff of 1.5m
    Eigen::Vector3d x_target(1.0, 0.0, 0.0);
    Eigen::Vector3d x_drone(0.0, 0.0, 0.0);

    pn.compute(x_target, x_drone, 0.01);
    Eigen::Vector3d a_cmd = pn.compute(x_target, x_drone, 0.01);

    EXPECT_EQ(a_cmd, Eigen::Vector3d::Zero());
}

// Test 3: Z component of delta_x_rel always zero
TEST(ProNavTest, ZComponent_AlwaysZero) {
    ProNav pn(3.0, 1.5, 1.0);

    // Target has nonzero Z — should be zeroed out
    Eigen::Vector3d x_target(10.0, 0.0, 50.0);
    Eigen::Vector3d x_drone(0.0, 0.0, 10.0);

    pn.compute(x_target, x_drone, 0.01);
    x_drone = Eigen::Vector3d(1.0, 0.0, 10.0);
    Eigen::Vector3d a_cmd = pn.compute(x_target, x_drone, 0.01);

    // Z acceleration must be zero — lateral intercept only
    EXPECT_NEAR(a_cmd.z(), 0.0, 1e-9);
}

// Test 4: reset() clears state
TEST(ProNavTest, Reset_ClearsState) {
    ProNav pn(3.0, 1.5, 1.0);

    Eigen::Vector3d x_target(10.0, 0.0, 0.0);
    Eigen::Vector3d x_drone(0.0, 0.0, 0.0);

    pn.compute(x_target, x_drone, 0.01);
    pn.compute(x_target, x_drone, 0.01);

    pn.reset();

    // First call after reset should return zero (uninitialized)
    Eigen::Vector3d a_cmd = pn.compute(x_target, x_drone, 0.01);
    EXPECT_EQ(a_cmd, Eigen::Vector3d::Zero());
}

int main(int argc, char **argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}