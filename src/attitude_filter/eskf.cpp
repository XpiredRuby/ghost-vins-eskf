#include "eskf.hpp"
#include <chrono>

ESKF::ESKF()
    : q_(Eigen::Quaterniond::Identity())
    , b_a_(Eigen::Vector3d::Zero())
    , b_g_(Eigen::Vector3d::Zero())
    , P_(Eigen::Matrix<double,9,9>::Identity() * 0.1)
    , Q_(Eigen::Matrix<double,9,9>::Zero())
    , initialized_(false)
    , sigma_accel_meas_(0.3)
{}

void ESKF::initialize(const Eigen::Quaterniond& q_init)
{
    q_  = q_init.normalized();
    b_a_.setZero();
    b_g_.setZero();
    P_  = Eigen::Matrix<double,9,9>::Identity() * 0.1;

    if (!nis_log_.is_open()) {
        nis_log_.open("logs/nis_camera_gravity.csv", std::ios::app);
    }
    initialized_ = true;
}

void ESKF::setProcessNoise(double sigma_a, double sigma_g)
{
    Q_.setZero();
    // Attitude noise driven by gyro noise
    Q_.block<3,3>(0,0) = Eigen::Matrix3d::Identity() * (sigma_g * sigma_g);
    // Accelerometer bias random walk
    Q_.block<3,3>(3,3) = Eigen::Matrix3d::Identity() * (sigma_a * sigma_a);
    // Gyro bias random walk
    Q_.block<3,3>(6,6) = Eigen::Matrix3d::Identity() * (sigma_g * sigma_g);
}

void ESKF::predict(const Eigen::Vector3d& omega_m,
                   const Eigen::Vector3d& accel_m,
                   double dt)
{
    if (!initialized_) return;
    (void)accel_m;  // not used in propagation — applied only in updateGravity()

    const Eigen::Vector3d omega_corr = omega_m - b_g_;

    // Quaternion kinematics: q_dot = 0.5 * q_ * [0, omega_corr]
    // Integrate: q_new = q_ + q_dot * dt, then normalize
    const Eigen::Quaterniond q_omega(0.0,
                                     omega_corr.x(),
                                     omega_corr.y(),
                                     omega_corr.z());
    Eigen::Quaterniond q_new;
    q_new.coeffs() = q_.coeffs() + 0.5 * dt * (q_ * q_omega).coeffs();
    q_ = q_new.normalized();

    // Error-state F matrix (9x9), columns: [delta_theta | delta_b_a | delta_b_g]
    // Attitude error is driven by gyro bias: d(delta_theta)/dt = -skew(w)*delta_theta - delta_b_g
    Eigen::Matrix<double,9,9> F = Eigen::Matrix<double,9,9>::Zero();
    F.block<3,3>(0,0) = -skew(omega_corr);            // attitude ← attitude
    F.block<3,3>(0,6) = -Eigen::Matrix3d::Identity();  // attitude ← gyro bias (LAST block)

    // First-order discrete transition: Phi = I + F*dt
    const Eigen::Matrix<double,9,9> Phi =
        Eigen::Matrix<double,9,9>::Identity() + F * dt;

    P_ = Phi * P_ * Phi.transpose() + Q_;
}

void ESKF::updateGravity(const Eigen::Vector3d& accel_m)
{
    if (!initialized_) return;

    const Eigen::Matrix3d R     = q_.toRotationMatrix();   // R_cam_to_NED
    const Eigen::Vector3d g_NED(0.0, 0.0, 9.81);
    const Eigen::Vector3d g_pred = R.transpose() * g_NED;  // expected gravity in camera frame

    const Eigen::Vector3d y = accel_m - g_pred;  // innovation

    // H = [skew(g_pred) | I3 | 0_{3x3}]  (3x9)
    // Middle block I3 couples accel bias error to the measurement.
    Eigen::Matrix<double,3,9> H = Eigen::Matrix<double,3,9>::Zero();
    H.block<3,3>(0,0) = skew(g_pred);
    H.block<3,3>(0,3) = Eigen::Matrix3d::Identity();   // accel bias (MIDDLE block)

    const Eigen::Matrix3d R_meas =
        Eigen::Matrix3d::Identity() * (sigma_accel_meas_ * sigma_accel_meas_);

    const Eigen::Matrix3d S     = H * P_ * H.transpose() + R_meas;
    const Eigen::Matrix3d S_inv = S.inverse();

    const Eigen::Matrix<double,9,3> K      = P_ * H.transpose() * S_inv;
    const Eigen::Matrix<double,9,1> delta_x = K * y;

    // Inject error state into nominal state
    const Eigen::Vector3d delta_theta = delta_x.head<3>();
    const Eigen::Quaterniond dq(1.0,
                                0.5 * delta_theta.x(),
                                0.5 * delta_theta.y(),
                                0.5 * delta_theta.z());
    q_  = (q_ * dq).normalized();
    b_a_ += delta_x.segment<3>(3);
    b_g_ += delta_x.segment<3>(6);

    // Joseph stabilized form — guarantees symmetry
    const Eigen::Matrix<double,9,9> IKH =
        Eigen::Matrix<double,9,9>::Identity() - K * H;
    P_ = IKH * P_ * IKH.transpose() + K * R_meas * K.transpose();

    logNIS(static_cast<double>(y.transpose() * S_inv * y));
}

void ESKF::applyUpdate(const Eigen::Matrix<double,3,9>& H,
                        const Eigen::Vector3d&           y,
                        const Eigen::Matrix3d&           R)
{
    if (!initialized_) return;

    const Eigen::Matrix3d S     = H * P_ * H.transpose() + R;
    const Eigen::Matrix<double,9,3> K = P_ * H.transpose() * S.inverse();
    const Eigen::Matrix<double,9,1> delta_x = K * y;

    const Eigen::Vector3d delta_theta = delta_x.head<3>();
    const Eigen::Quaterniond dq(1.0,
                                0.5 * delta_theta.x(),
                                0.5 * delta_theta.y(),
                                0.5 * delta_theta.z());
    q_   = (q_ * dq).normalized();
    b_a_ += delta_x.segment<3>(3);
    b_g_ += delta_x.segment<3>(6);

    // Joseph stabilized form
    const Eigen::Matrix<double,9,9> IKH =
        Eigen::Matrix<double,9,9>::Identity() - K * H;
    P_ = IKH * P_ * IKH.transpose() + K * R * K.transpose();
}

Eigen::Matrix3d           ESKF::getR_cam_to_NED() const { return q_.toRotationMatrix(); }
Eigen::Vector3d           ESKF::getGyroBias()     const { return b_g_; }
Eigen::Vector3d           ESKF::getAccelBias()    const { return b_a_; }
Eigen::Matrix<double,9,9> ESKF::getCovariance()   const { return P_; }
bool                      ESKF::isInitialized()   const { return initialized_; }

Eigen::Matrix3d ESKF::skew(const Eigen::Vector3d& v) const
{
    Eigen::Matrix3d S;
    S <<   0.0, -v(2),  v(1),
          v(2),   0.0, -v(0),
         -v(1),  v(0),   0.0;
    return S;
}

void ESKF::normalizeQuaternion()
{
    q_.normalize();
}

void ESKF::logNIS(double nis)
{
    if (!nis_log_.is_open()) return;
    const double ts = std::chrono::duration<double>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    nis_log_ << ts << "," << nis << "\n";
}
