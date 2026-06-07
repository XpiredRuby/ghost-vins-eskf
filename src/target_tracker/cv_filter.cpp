#include "cv_filter.hpp"
#include <chrono>

CVFilter::CVFilter()
    : x_(Eigen::Matrix<double,6,1>::Zero())
    , P_(Eigen::Matrix<double,6,6>::Identity())
    , Q_(Eigen::Matrix<double,6,6>::Zero())
    , R_(Eigen::Matrix<double,3,3>::Identity())
    , F_(Eigen::Matrix<double,6,6>::Identity())
    , H_(Eigen::Matrix<double,3,6>::Zero())
    , initialized_(false)
    , sigma_a_(1.0)
{
    // H = [I3 | 0_{3x3}] — observe position only, not velocity
    H_.block<3,3>(0,0) = Eigen::Matrix3d::Identity();
}

void CVFilter::initialize(const Eigen::Vector3d& pos_init)
{
    x_.setZero();
    x_.head<3>() = pos_init;

    // Default P₀ — overridden by setInitialCovariance() if filter.yaml values are loaded
    P_.setZero();
    P_.block<3,3>(0,0) = Eigen::Matrix3d::Identity();         // 1 m position uncertainty
    P_.block<3,3>(3,3) = Eigen::Matrix3d::Identity() * 10.0;  // ~3.16 m/s velocity uncertainty

    if (!nis_log_.is_open()) {
        nis_log_.open("logs/nis_cv_tracker.csv", std::ios::app);
    }

    initialized_ = true;
}

void CVFilter::setProcessNoise(double sigma_a)
{
    sigma_a_ = sigma_a;
}

void CVFilter::setMeasurementNoise(double sigma_r)
{
    R_ = Eigen::Matrix3d::Identity() * (sigma_r * sigma_r);
}

void CVFilter::setInitialCovariance(double sigma_pos_m, double sigma_vel_m_per_s)
{
    // Overrides the hardcoded P₀ written by initialize() with YAML-configured values.
    // Call after initialize() and before the first predict()/update().
    P_.setZero();
    P_.block<3,3>(0,0) = Eigen::Matrix3d::Identity() * (sigma_pos_m         * sigma_pos_m);
    P_.block<3,3>(3,3) = Eigen::Matrix3d::Identity() * (sigma_vel_m_per_s   * sigma_vel_m_per_s);
}

void CVFilter::predict(double dt)
{
    if (!initialized_) return;

    // Build F with current dt — all fixed-size, stack-allocated
    F_.setIdentity();
    F_.block<3,3>(0,3) = Eigen::Matrix3d::Identity() * dt;

    // Discrete-time white-noise acceleration (DWPA) process noise:
    // σ_a² drives position (dt⁴/4) and velocity (dt²) terms.
    // σ_a is computed from the Singer model: σ_a² = 2·α·a_max²/3 — in tracker_node.cpp.
    const double dt2 = dt * dt;
    const double dt3 = dt2 * dt;
    const double dt4 = dt3 * dt;
    const double sa2 = sigma_a_ * sigma_a_;

    Q_.setZero();
    Q_.block<3,3>(0,0) = Eigen::Matrix3d::Identity() * (sa2 * dt4 / 4.0);
    Q_.block<3,3>(0,3) = Eigen::Matrix3d::Identity() * (sa2 * dt3 / 2.0);
    Q_.block<3,3>(3,0) = Eigen::Matrix3d::Identity() * (sa2 * dt3 / 2.0);
    Q_.block<3,3>(3,3) = Eigen::Matrix3d::Identity() * (sa2 * dt2);

    x_ = F_ * x_;
    P_ = F_ * P_ * F_.transpose() + Q_;
}

void CVFilter::update(const Eigen::Vector3d& z_pos)
{
    if (!initialized_) return;

    const Eigen::Vector3d             y     = z_pos - H_ * x_;
    const Eigen::Matrix<double,3,3>   S     = H_ * P_ * H_.transpose() + R_;
    const Eigen::Matrix<double,3,3>   S_inv = S.inverse();
    const Eigen::Matrix<double,6,3>   K     = P_ * H_.transpose() * S_inv;

    x_ += K * y;

    // Joseph stabilized form: P = (I−KH)·P·(I−KH)ᵀ + K·R·Kᵀ
    // Guarantees symmetry regardless of floating-point rounding in K.
    const Eigen::Matrix<double,6,6> IKH =
        Eigen::Matrix<double,6,6>::Identity() - K * H_;
    P_ = IKH * P_ * IKH.transpose() + K * R_ * K.transpose();

    logNIS(static_cast<double>(y.transpose() * S_inv * y));
}

Eigen::Matrix<double,6,1> CVFilter::getState()      const { return x_; }
Eigen::Matrix<double,6,6> CVFilter::getCovariance() const { return P_; }
bool CVFilter::isInitialized() const { return initialized_; }

void CVFilter::logNIS(double nis)
{
    if (!nis_log_.is_open()) return;
    const double ts = std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    nis_log_ << ts << "," << nis << "\n";
}
