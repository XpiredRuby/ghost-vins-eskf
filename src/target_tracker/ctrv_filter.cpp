#include "ctrv_filter.hpp"
#include <chrono>
#include <cmath>

CTRVFilter::CTRVFilter()
    : x_(Eigen::VectorXd::Zero(5))
    , P_(Eigen::MatrixXd::Identity(5, 5))
    , Q_(Eigen::MatrixXd::Zero(5, 5))
    , R_(Eigen::MatrixXd::Identity(2, 2))
    , initialized_(false)
    , sigma_a_(1.0)
    , sigma_psi_dot_(0.1)
    , sigma_buf_(Eigen::Matrix<double, kN_, kNSigma_>::Zero())
    , sigma_pred_buf_(Eigen::Matrix<double, kN_, kNSigma_>::Zero())
    , z_sigma_buf_(Eigen::Matrix<double, 2, kNSigma_>::Zero())
{}

void CTRVFilter::initialize(const Eigen::Vector2d& pos_init, double v_init, double psi_init)
{
    x_.setZero();
    x_(0) = pos_init(0);  // px
    x_(1) = pos_init(1);  // py
    x_(2) = v_init;       // v
    x_(3) = psi_init;     // psi
    x_(4) = 0.0;          // psi_dot — unknown at init, start at zero

    P_.setZero();
    P_(0, 0) = 1.0;   // px      — 1 m std dev
    P_(1, 1) = 1.0;   // py      — 1 m std dev
    P_(2, 2) = 4.0;   // v       — 2 m/s std dev
    P_(3, 3) = 1.0;   // psi     — ~57 deg std dev
    P_(4, 4) = 0.1;   // psi_dot — 0.316 rad/s std dev

    if (!nis_log_.is_open()) {
        nis_log_.open("logs/nis_target_tracker.csv", std::ios::app);
    }

    initialized_ = true;
}

void CTRVFilter::setProcessNoise(double sigma_a, double sigma_psi_dot)
{
    sigma_a_       = sigma_a;
    sigma_psi_dot_ = sigma_psi_dot;
}

void CTRVFilter::setMeasurementNoise(double sigma_r)
{
    R_ = Eigen::Matrix2d::Identity() * (sigma_r * sigma_r);
}

CTRVFilter::State5d CTRVFilter::ctrvPredictSingle(
    const Eigen::Ref<const State5d>& x, double dt) const
{
    State5d xp = x;

    const double v       = x(2);
    const double psi     = x(3);
    const double psi_dot = x(4);

    if (std::abs(psi_dot) < 1e-4) {
        // Singularity guard — revert to CV straight-line equations
        xp(0) += v * std::cos(psi) * dt;
        xp(1) += v * std::sin(psi) * dt;
    } else {
        xp(0) += (v / psi_dot) * (std::sin(psi + psi_dot * dt) - std::sin(psi));
        xp(1) += (v / psi_dot) * (std::cos(psi) - std::cos(psi + psi_dot * dt));
    }

    xp(3) += psi_dot * dt;
    // x(2) v and x(4) psi_dot propagate unchanged
    return xp;
}

void CTRVFilter::generateSigmaPoints()
{
    // Fixed-size Cholesky: Pscaled and LLT are stack-allocated — no heap
    const Eigen::Matrix<double, kN_, kN_> Pscaled =
        static_cast<double>(kN_ + kLambda_) * P_;

    Eigen::LLT<Eigen::Matrix<double, kN_, kN_>> llt(Pscaled);
    const Eigen::Matrix<double, kN_, kN_> L = llt.matrixL();

    // Copy x_ once to fixed-size so x_fixed + L.col(i) stays fixed-size (no heap)
    const State5d x_fixed = x_;

    sigma_buf_.col(0) = x_fixed;
    for (int i = 0; i < kN_; ++i) {
        sigma_buf_.col(i + 1)        = x_fixed + L.col(i);
        sigma_buf_.col(kN_ + i + 1)  = x_fixed - L.col(i);
    }
}

void CTRVFilter::predict(double dt)
{
    if (!initialized_) return;

    // Build Q from stored noise params, scaled by dt
    const double qa = sigma_a_       * dt;
    const double qw = sigma_psi_dot_ * dt;
    Q_.setZero();
    Q_(2, 2) = qa * qa;   // velocity noise
    Q_(4, 4) = qw * qw;   // yaw-rate noise

    generateSigmaPoints();

    // Propagate each sigma point — results are fixed-size State5d on the stack
    for (int i = 0; i <= 2 * kN_; ++i) {
        sigma_pred_buf_.col(i) = ctrvPredictSingle(sigma_buf_.col(i), dt);
    }

    // Recover predicted mean — all fixed-size arithmetic, no heap
    State5d x_pred = kWm0_ * sigma_pred_buf_.col(0);
    for (int i = 1; i <= 2 * kN_; ++i) {
        x_pred += kWi_ * sigma_pred_buf_.col(i);
    }

    // Recover predicted covariance — fixed-size 5x5, stack-allocated
    Eigen::Matrix<double, kN_, kN_> P_pred = Eigen::Matrix<double, kN_, kN_>::Zero();
    {
        const State5d d = sigma_pred_buf_.col(0) - x_pred;
        P_pred.noalias() += kWc0_ * d * d.transpose();
    }
    for (int i = 1; i <= 2 * kN_; ++i) {
        const State5d d = sigma_pred_buf_.col(i) - x_pred;
        P_pred.noalias() += kWi_ * d * d.transpose();
    }
    P_pred += Q_;

    x_ = x_pred;
    P_ = P_pred;
}

void CTRVFilter::update(const Eigen::Vector2d& z_pos)
{
    if (!initialized_) return;

    generateSigmaPoints();

    // Project sigma points through h(x) = [px, py] — fixed-size [2 x 11] buffer
    for (int i = 0; i <= 2 * kN_; ++i) {
        z_sigma_buf_.col(i) = sigma_buf_.col(i).head<2>();
    }

    // Predicted measurement mean
    Eigen::Vector2d z_pred = kWm0_ * z_sigma_buf_.col(0);
    for (int i = 1; i <= 2 * kN_; ++i) {
        z_pred += kWi_ * z_sigma_buf_.col(i);
    }

    // Innovation covariance S — fixed-size 2x2, stack-allocated
    Eigen::Matrix2d S = Eigen::Matrix2d::Zero();
    {
        const Eigen::Vector2d d = z_sigma_buf_.col(0) - z_pred;
        S.noalias() += kWc0_ * d * d.transpose();
    }
    for (int i = 1; i <= 2 * kN_; ++i) {
        const Eigen::Vector2d d = z_sigma_buf_.col(i) - z_pred;
        S.noalias() += kWi_ * d * d.transpose();
    }
    S += R_;

    // Cross-correlation T — fixed-size [5 x 2], stack-allocated
    Eigen::Matrix<double, kN_, 2> T = Eigen::Matrix<double, kN_, 2>::Zero();
    {
        const State5d         dx = sigma_buf_.col(0) - x_;
        const Eigen::Vector2d dz = z_sigma_buf_.col(0) - z_pred;
        T.noalias() += kWc0_ * dx * dz.transpose();
    }
    for (int i = 1; i <= 2 * kN_; ++i) {
        const State5d         dx = sigma_buf_.col(i) - x_;
        const Eigen::Vector2d dz = z_sigma_buf_.col(i) - z_pred;
        T.noalias() += kWi_ * dx * dz.transpose();
    }

    // Kalman gain K — fixed-size [5 x 2], stack-allocated
    const Eigen::Matrix2d           S_inv = S.inverse();
    const Eigen::Matrix<double, kN_, 2> K = T * S_inv;

    const Eigen::Vector2d innov = z_pos - z_pred;
    x_ += K * innov;
    P_ -= K * S * K.transpose();

    logNIS(static_cast<double>(innov.transpose() * S_inv * innov));
}

Eigen::VectorXd CTRVFilter::getState() const { return x_; }
Eigen::MatrixXd CTRVFilter::getCovariance() const { return P_; }
bool CTRVFilter::isInitialized() const { return initialized_; }

void CTRVFilter::logNIS(double nis)
{
    if (!nis_log_.is_open()) return;
    const double ts = std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    nis_log_ << ts << "," << nis << "\n";
}
