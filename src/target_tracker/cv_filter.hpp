#pragma once
#include <Eigen/Dense>
#include <fstream>

class CVFilter {
public:
    CVFilter();

    void initialize(const Eigen::Vector3d& pos_init);
    void predict(double dt);
    void update(const Eigen::Vector3d& z_pos);

    // State and covariance accessors — fixed-size return avoids heap allocation
    Eigen::Matrix<double,6,1> getState()      const;
    Eigen::Matrix<double,6,6> getCovariance() const;
    bool isInitialized() const;

    void setProcessNoise(double sigma_a);
    void setMeasurementNoise(double sigma_r);

    // Override the hardcoded P₀ written by initialize() with YAML-loaded values.
    // sigma values are std devs; stored as variances on the diagonal.
    void setInitialCovariance(double sigma_pos_m, double sigma_vel_m_per_s);

private:
    // All matrices are fixed-size — zero heap allocation on the hot path.
    // (previously Eigen::MatrixXd / Eigen::VectorXd, which heap-allocate on every call)
    Eigen::Matrix<double,6,1> x_;   // 6-state: [px, py, pz, vx, vy, vz]
    Eigen::Matrix<double,6,6> P_;   // 6x6 covariance
    Eigen::Matrix<double,6,6> Q_;   // 6x6 process noise
    Eigen::Matrix<double,3,3> R_;   // 3x3 measurement noise
    Eigen::Matrix<double,6,6> F_;   // 6x6 state transition
    Eigen::Matrix<double,3,6> H_;   // 3x6 measurement matrix

    bool   initialized_;
    double sigma_a_;
    std::ofstream nis_log_;   // opened once in initialize(), kept open

    void logNIS(double nis);
};
