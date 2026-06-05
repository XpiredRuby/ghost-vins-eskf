#pragma once
#include <Eigen/Dense>

class ZARU {
public:
    ZARU(double rate_hz = 1.0, double accel_gate = 0.5);

    // Returns true when both timing and motion conditions are satisfied
    bool shouldUpdate(double elapsed_since_last_s,
                      const Eigen::Vector3d& accel_m) const;

    // innovation = 0 - (omega_m - b_g_hat)  (zero angular rate pseudo-measurement)
    Eigen::Vector3d computeInnovation(const Eigen::Vector3d& omega_m,
                                      const Eigen::Vector3d& b_g_hat) const;

    // H = [0_{3x3} | 0_{3x3} | I_{3x3}]  — LAST block extracts delta_b_g (gyro bias)
    Eigen::Matrix<double,3,9> getH() const;

    // R_zaru = sigma_gyro^2 * I3, sigma derived from Allan Variance ARW
    Eigen::Matrix3d getR(double arw_deg_per_sqrthz) const;

private:
    double rate_hz_;
    double accel_gate_;
};
