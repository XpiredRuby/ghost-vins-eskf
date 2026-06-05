#pragma once
#include <Eigen/Dense>
#include <fstream>

class CVFilter {
public:
    CVFilter();

    void initialize(const Eigen::Vector3d& pos_init);
    void predict(double dt);
    void update(const Eigen::Vector3d& z_pos);

    Eigen::VectorXd getState() const;
    Eigen::MatrixXd getCovariance() const;
    bool isInitialized() const;

    void setProcessNoise(double sigma_a);
    void setMeasurementNoise(double sigma_r);

private:
    Eigen::VectorXd x_;   // 6-state: [px, py, pz, vx, vy, vz]
    Eigen::MatrixXd P_;   // 6x6 covariance
    Eigen::MatrixXd Q_;   // 6x6 process noise
    Eigen::MatrixXd R_;   // 3x3 measurement noise
    Eigen::MatrixXd F_;   // 6x6 state transition
    Eigen::MatrixXd H_;   // 3x6 measurement matrix
    bool initialized_;
    double sigma_a_;
    std::ofstream nis_log_;   // opened once in initialize(), kept open

    void logNIS(double nis);
};
