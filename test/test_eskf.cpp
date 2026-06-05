#include <gtest/gtest.h>
#include <random>
#include "attitude_filter/eskf.hpp"
#include "attitude_filter/zaru.hpp"
#include "attitude_filter/sage_husa.hpp"

// Test 1: predict() — zero angular rate for 1 second → quaternion stays at identity
TEST(ESKFTest, PredictZeroRateStaysIdentity)
{
    ESKF eskf;
    eskf.initialize(Eigen::Quaterniond::Identity());
    eskf.setProcessNoise(1e-5, 1e-5);

    const Eigen::Vector3d omega_m = Eigen::Vector3d::Zero();
    const Eigen::Vector3d accel_m(0.0, 0.0, 9.81);  // passed but unused in predict()

    for (int i = 0; i < 100; ++i) {
        eskf.predict(omega_m, accel_m, 0.01);   // 100 × 10ms = 1 second
    }

    // With zero angular rate and zero biases, rotation must not drift
    bool rot_identity_1 = eskf.getR_cam_to_NED().isApprox(Eigen::Matrix3d::Identity(), 1e-9);
    EXPECT_TRUE(rot_identity_1) << "Rotation matrix must stay identity after zero-rate predict";
    EXPECT_LT(eskf.getGyroBias().norm(),  1e-9);
    EXPECT_LT(eskf.getAccelBias().norm(), 1e-9);
}

// Test 2: updateGravity() — perfect gravity measurement → state unchanged, P decreases
TEST(ESKFTest, UpdateGravityPerfectMeasurementReducesCovariance)
{
    ESKF eskf;
    eskf.initialize(Eigen::Quaterniond::Identity());
    eskf.setProcessNoise(1e-4, 1e-4);

    // With identity q_, g_pred = R^T * [0,0,9.81] = [0,0,9.81]
    // Perfect measurement: innovation y = accel_m - g_pred = 0
    const Eigen::Vector3d accel_perfect(0.0, 0.0, 9.81);

    const Eigen::Matrix<double,9,9> P_before = eskf.getCovariance();
    eskf.updateGravity(accel_perfect);
    const Eigen::Matrix<double,9,9> P_after  = eskf.getCovariance();

    // Zero innovation → state must not change
    bool rot_identity_2 = eskf.getR_cam_to_NED().isApprox(Eigen::Matrix3d::Identity(), 1e-9);
    EXPECT_TRUE(rot_identity_2) << "Rotation matrix must stay identity after zero-innovation update";
    EXPECT_LT(eskf.getAccelBias().norm(), 1e-9);
    EXPECT_LT(eskf.getGyroBias().norm(),  1e-9);

    // Information was gained — covariance trace must decrease
    EXPECT_LT(P_after.trace(), P_before.trace());
}

// Test 3: ZARU getH() — last 3x3 block must be I3, first 6 columns must be zero
TEST(ZARUTest, HMatrixExtractsGyroBiasLastBlock)
{
    ZARU zaru;
    const Eigen::Matrix<double,3,9> H = zaru.getH();

    // Columns 6-8: I3 — extracts delta_b_g (gyro bias)
    bool h_gyro_ok = H.block<3,3>(0,6).isApprox(Eigen::Matrix3d::Identity());
    EXPECT_TRUE(h_gyro_ok) << "H last block (gyro bias, cols 6-8) must be I3";

    // Columns 0-5: zero — must NOT touch delta_theta or delta_b_a
    bool h_zero_ok = H.block<3,6>(0,0).isZero();
    EXPECT_TRUE(h_zero_ok) << "H first 6 columns (attitude + accel bias) must be zero";
}

// Test 4: SageHusa — R stays positive definite after 100 random innovation updates
TEST(SageHusaTest, RRemainsPositiveDefiniteAfterRandomUpdates)
{
    SageHusa sh(3);

    std::mt19937 rng(42);
    std::normal_distribution<double> dist(0.0, 0.1);

    // Simulate a 3x9 measurement matrix (gravity update style)
    Eigen::MatrixXd H = Eigen::MatrixXd::Zero(3, 9);
    H.block<3,3>(0,0) = Eigen::Matrix3d::Identity();

    const Eigen::MatrixXd P = Eigen::MatrixXd::Identity(9, 9) * 0.01;

    for (int i = 0; i < 100; ++i) {
        Eigen::Vector3d innov;
        innov << dist(rng), dist(rng), dist(rng);

        const Eigen::MatrixXd R_updated = sh.updateR(innov, H, P);

        // R must remain positive definite after every update
        const Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> es(R_updated);
        EXPECT_GT(es.eigenvalues().minCoeff(), 0.0)
            << "R not positive definite at iteration " << i;
    }
}

int main(int argc, char** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
