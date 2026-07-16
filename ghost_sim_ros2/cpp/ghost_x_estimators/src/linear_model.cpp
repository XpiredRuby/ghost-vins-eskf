#include "ghost_x/linear_model.hpp"

#include <Eigen/Cholesky>
#include <Eigen/Eigenvalues>

#include <cmath>
#include <numbers>
#include <stdexcept>

namespace ghost_x {

bool covariance_is_psd(const Covariance &value, double tolerance) {
  if (!finite(value) || !value.isApprox(value.transpose(), 1.0e-10)) {
    return false;
  }
  Eigen::SelfAdjointEigenSolver<Covariance> solver(symmetrize(value), Eigen::EigenvaluesOnly);
  return solver.info() == Eigen::Success && solver.eigenvalues().minCoeff() >= -std::abs(tolerance);
}

bool covariance_is_spd(const MeasurementCovariance &value, double tolerance) {
  if (!finite(value) || !value.isApprox(value.transpose(), 1.0e-12)) {
    return false;
  }
  Eigen::SelfAdjointEigenSolver<MeasurementCovariance> solver(symmetrize(value), Eigen::EigenvaluesOnly);
  return solver.info() == Eigen::Success && solver.eigenvalues().minCoeff() > std::abs(tolerance);
}

Covariance cv_transition(double dt_s) {
  if (!std::isfinite(dt_s) || dt_s <= 0.0) {
    throw std::invalid_argument("dt_s must be finite and positive");
  }
  Covariance f = Covariance::Identity();
  f(0, 2) = dt_s;
  f(1, 3) = dt_s;
  return f;
}

Covariance white_acceleration_process_noise(double dt_s, double acceleration_std_mps2) {
  if (!std::isfinite(acceleration_std_mps2) || acceleration_std_mps2 <= 0.0) {
    throw std::invalid_argument("acceleration_std_mps2 must be finite and positive");
  }
  const double dt2 = dt_s * dt_s;
  const double dt3 = dt2 * dt_s;
  const double dt4 = dt2 * dt2;
  const double q = acceleration_std_mps2 * acceleration_std_mps2;
  Covariance out = Covariance::Zero();
  out(0, 0) = dt4 / 4.0;
  out(0, 2) = dt3 / 2.0;
  out(2, 0) = dt3 / 2.0;
  out(2, 2) = dt2;
  out(1, 1) = dt4 / 4.0;
  out(1, 3) = dt3 / 2.0;
  out(3, 1) = dt3 / 2.0;
  out(3, 3) = dt2;
  return q * out;
}

MeasurementMatrix position_measurement_matrix() {
  MeasurementMatrix h = MeasurementMatrix::Zero();
  h(0, 0) = 1.0;
  h(1, 1) = 1.0;
  return h;
}

double gaussian_log_likelihood(
    const Measurement &innovation, const MeasurementCovariance &innovation_covariance) {
  if (!finite(innovation) || !covariance_is_spd(innovation_covariance)) {
    throw std::invalid_argument("innovation or covariance is invalid");
  }
  Eigen::LDLT<MeasurementCovariance> ldlt(innovation_covariance);
  if (ldlt.info() != Eigen::Success || !ldlt.isPositive()) {
    throw std::runtime_error("innovation covariance factorization failed");
  }
  const double mahalanobis = innovation.dot(ldlt.solve(innovation));
  const Eigen::Vector2d diagonal = ldlt.vectorD();
  if ((diagonal.array() <= 0.0).any()) {
    throw std::runtime_error("innovation covariance is not positive definite");
  }
  const double log_determinant = diagonal.array().log().sum();
  return -0.5 * (2.0 * std::log(2.0 * std::numbers::pi) + log_determinant + mahalanobis);
}

}  // namespace ghost_x
