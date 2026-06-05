#include "cv_filter.hpp"
#include <chrono>

CVFilter::CVFilter()
    : x_(Eigen::VectorXd::Zero(6))
    , P_(Eigen::MatrixXd::Identity(6, 6))
    , Q_(Eigen::MatrixXd::Zero(6, 6))
    , R_(Eigen::MatrixXd::Identity(3, 3))
    , F_(Eigen::MatrixXd::Identity(6, 6))
    , H_(Eigen::MatrixXd::Zero(3, 6))
    , initialized_(false)
    , sigma_a_(1.0)
{
    // H = [I3 | 0_{3x3}] — observe position only, not velocity
    H_.block<3, 3>(0, 0) = Eigen::Matrix3d::Identity();
}

void CVFilter::initialize(const Eigen::Vector3d& pos_init)
{
    x_.setZero();
    x_.head<3>() = pos_init;

    P_.setZero();
    P_.block<3, 3>(0, 0) = Eigen::Matrix3d::Identity();        // 1 m position uncertainty
    P_.block<3, 3>(3, 3) = Eigen::Matrix3d::Identity() * 10.0; // ~3.16 m/s velocity uncertainty

    if (!nis_log_.is_open()) {
        nis_log_.open("logs/nis_target_tracker.csv", std::ios::app);
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

void CVFilter::predict(double dt)
{
    if (!initialized_) return;

    // Build F with current dt
    F_ = Eigen::MatrixXd::Identity(6, 6);
    F_.block<3, 3>(0, 3) = Eigen::Matrix3d::Identity() * dt;

    // Discrete-time Singer model Q: constant-velocity + white acceleration noise
    const double dt2 = dt * dt;
    const double dt3 = dt2 * dt;
    const double dt4 = dt3 * dt;
    const double sa2 = sigma_a_ * sigma_a_;

    Q_.setZero();
    Q_.block<3, 3>(0, 0) = Eigen::Matrix3d::Identity() * (sa2 * dt4 / 4.0);
    Q_.block<3, 3>(0, 3) = Eigen::Matrix3d::Identity() * (sa2 * dt3 / 2.0);
    Q_.block<3, 3>(3, 0) = Eigen::Matrix3d::Identity() * (sa2 * dt3 / 2.0);
    Q_.block<3, 3>(3, 3) = Eigen::Matrix3d::Identity() * (sa2 * dt2);

    x_ = F_ * x_;
    P_ = F_ * P_ * F_.transpose() + Q_;
}

void CVFilter::update(const Eigen::Vector3d& z_pos)
{
    if (!initialized_) return;

    const Eigen::Vector3d y     = z_pos - H_ * x_;
    const Eigen::Matrix3d S     = H_ * P_ * H_.transpose() + R_;
    const Eigen::Matrix3d S_inv = S.inverse();
    const Eigen::MatrixXd K     = P_ * H_.transpose() * S_inv;

    x_ += K * y;

    // Joseph stabilized form: P = (I-KH)*P*(I-KH)^T + K*R*K^T
    // Guarantees symmetry regardless of floating-point rounding in K.
    // The standard form (I-KH)*P accumulates asymmetry on long runs.
    const Eigen::MatrixXd IKH = Eigen::MatrixXd::Identity(6, 6) - K * H_;
    P_ = IKH * P_ * IKH.transpose() + K * R_ * K.transpose();

    logNIS(static_cast<double>(y.transpose() * S_inv * y));
}

Eigen::VectorXd CVFilter::getState() const { return x_; }
Eigen::MatrixXd CVFilter::getCovariance() const { return P_; }
bool CVFilter::isInitialized() const { return initialized_; }

void CVFilter::logNIS(double nis)
{
    if (!nis_log_.is_open()) return;
    const double ts = std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    nis_log_ << ts << "," << nis << "\n";
}
