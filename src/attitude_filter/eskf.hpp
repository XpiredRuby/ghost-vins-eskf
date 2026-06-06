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

    // ── Post-initialize configuration setters ─────────────────────────────────
    // Call after initialize() to apply values loaded from config/filter.yaml.
    // (initialize() sets P_ to Identity×0.1 and sigma_accel_meas_ to 0.3 as
    //  safe defaults; these setters override those defaults with YAML values.)

    // Override the gravity-update measurement noise (σ_accel_meas, m/s²).
    // Affects R_meas = σ² × I₃ inside updateGravity().
    void setSigmaAccelMeas(double sigma);

    // Override the initial error-state covariance P₀.
    // Replaces the Identity×0.1 default set by initialize().
    void setInitialCovariance(const Eigen::Matrix<double,9,9>& P0);

    // Override the gravity reference used in updateGravity().
    // Replaces the hardcoded 9.81 m/s² with the site-specific value.
    void setGravity(double g_m_per_s2);

    bool isInitialized() const;

private:
    Eigen::Quaterniond        q_;    // camera platform quaternion (NED←cam)
    Eigen::Vector3d           b_a_;  // accelerometer bias
    Eigen::Vector3d           b_g_;  // gyro bias
    Eigen::Matrix<double,9,9> P_;    // error-state covariance
    Eigen::Matrix<double,9,9> Q_;    // process noise

    bool   initialized_;
    double sigma_accel_meas_;   // measurement noise for gravity update R_meas [m/s²]
    double gravity_;            // local gravity reference [m/s²], default 9.81
    std::ofstream nis_log_;     // opened once in initialize(), kept open

    Eigen::Matrix3d skew(const Eigen::Vector3d& v) const;
    void normalizeQuaternion();
    void logNIS(double nis);    // appends to logs/nis_camera_gravity.csv
};
