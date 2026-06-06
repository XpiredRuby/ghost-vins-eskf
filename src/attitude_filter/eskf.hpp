#pragma once
#include <Eigen/Dense>
#include <fstream>

class ESKF {
public:
    ESKF();

    void initialize(const Eigen::Quaterniond& q_init);
    void predict(const Eigen::Vector3d& omega_m,
                 const Eigen::Vector3d& accel_m,
                 double dt);
    void updateGravity(const Eigen::Vector3d& accel_m);

    // Generic measurement update — used by ZARU and any future sensor.
    // Applies Joseph-form KF update with the provided H, innovation y, and R.
    // State injection order: delta_theta → q_, delta_b_a → b_a_, delta_b_g → b_g_.
    void applyUpdate(const Eigen::Matrix<double,3,9>& H,
                     const Eigen::Vector3d&           y,
                     const Eigen::Matrix3d&           R);

    Eigen::Matrix3d           getR_cam_to_NED() const;
    Eigen::Vector3d           getGyroBias()     const;
    Eigen::Vector3d           getAccelBias()    const;
    Eigen::Matrix<double,9,9> getCovariance()   const;

    void setProcessNoise(double sigma_a, double sigma_g);
    bool isInitialized() const;

private:
    Eigen::Quaterniond        q_;    // camera platform quaternion (NED←cam)
    Eigen::Vector3d           b_a_;  // accelerometer bias
    Eigen::Vector3d           b_g_;  // gyro bias
    Eigen::Matrix<double,9,9> P_;    // error-state covariance
    Eigen::Matrix<double,9,9> Q_;    // process noise

    bool   initialized_;
    double sigma_accel_meas_;   // accelerometer noise for gravity update R_meas
    std::ofstream nis_log_;     // opened once in initialize(), kept open

    Eigen::Matrix3d skew(const Eigen::Vector3d& v) const;
    void normalizeQuaternion();
    void logNIS(double nis);    // appends to logs/nis_camera_gravity.csv
};
