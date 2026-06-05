#include "zaru.hpp"
#include <cmath>

ZARU::ZARU(double rate_hz, double accel_gate)
    : rate_hz_(rate_hz)
    , accel_gate_(accel_gate)
{}

bool ZARU::shouldUpdate(double elapsed_since_last_s,
                        const Eigen::Vector3d& accel_m) const
{
    const bool time_ok   = elapsed_since_last_s >= (1.0 / rate_hz_);
    const bool motion_ok = std::abs(accel_m.norm() - 9.81) <= accel_gate_;
    return time_ok && motion_ok;
}

Eigen::Vector3d ZARU::computeInnovation(const Eigen::Vector3d& omega_m,
                                         const Eigen::Vector3d& b_g_hat) const
{
    // True angular rate is zero on a static tripod.
    // innovation = z_true - z_predicted = 0 - (omega_m - b_g_hat)
    return -(omega_m - b_g_hat);
}

Eigen::Matrix<double,3,9> ZARU::getH() const
{
    Eigen::Matrix<double,3,9> H = Eigen::Matrix<double,3,9>::Zero();
    // LAST 3x3 block (columns 6-8) = I3 — extracts delta_b_g (gyro bias)
    // NOT the middle block [0,I,0] which would extract delta_b_a (wrong physics)
    H.block<3,3>(0,6) = Eigen::Matrix3d::Identity();
    return H;
}

Eigen::Matrix3d ZARU::getR(double arw_deg_per_sqrthz) const
{
    // sigma_gyro (rad/s) = ARW (deg/√Hz) × √(rate_hz) × (π/180)
    const double sigma_gyro =
        arw_deg_per_sqrthz * std::sqrt(rate_hz_) * (M_PI / 180.0);
    return Eigen::Matrix3d::Identity() * (sigma_gyro * sigma_gyro);
}
