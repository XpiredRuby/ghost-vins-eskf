#include "ghost_x/kalman_filter.hpp"

#include "ghost_x/linear_model.hpp"

#include <Eigen/Cholesky>

#include <cmath>
#include <stdexcept>

namespace ghost_x {

CvKalmanFilter::CvKalmanFilter(KalmanConfig config) : config_(std::move(config)) {
  if (!std::isfinite(config_.acceleration_std_mps2) || config_.acceleration_std_mps2 <= 0.0) {
    throw std::invalid_argument("acceleration_std_mps2 must be finite and positive");
  }
  if (!covariance_is_spd(config_.measurement_covariance)) {
    throw std::invalid_argument("measurement covariance must be symmetric positive definite");
  }
  if (!covariance_is_psd(config_.initial_covariance)) {
    throw std::invalid_argument("initial covariance must be symmetric positive semidefinite");
  }
}

void CvKalmanFilter::initialize(const Measurement &measurement, const State &initial_state) {
  if (!finite(measurement) || !finite(initial_state)) {
    throw std::invalid_argument("initial measurement/state must be finite");
  }
  state_ = initial_state;
  state_(0) = measurement(0);
  state_(1) = measurement(1);
  covariance_ = config_.initial_covariance;
  initialized_ = true;
}

void CvKalmanFilter::set_state(const State &state, const Covariance &covariance) {
  if (!finite(state) || !covariance_is_psd(covariance)) {
    throw std::invalid_argument("state/covariance is invalid");
  }
  state_ = state;
  covariance_ = symmetrize(covariance);
  initialized_ = true;
}

Estimate CvKalmanFilter::step(double dt_s, const std::optional<Measurement> &measurement) {
  if (!std::isfinite(dt_s) || dt_s <= 0.0) {
    throw std::invalid_argument("dt_s must be finite and positive");
  }
  if (!initialized_) {
    if (!measurement.has_value()) {
      return Estimate{};
    }
    initialize(*measurement);
    return Estimate{true, state_, covariance_, "TRACKING"};
  }

  const Covariance f = cv_transition(dt_s);
  state_ = f * state_;
  covariance_ = symmetrize(
      f * covariance_ * f.transpose() +
      white_acceleration_process_noise(dt_s, config_.acceleration_std_mps2));

  if (!measurement.has_value()) {
    return Estimate{true, state_, covariance_, "PREDICTION_ONLY"};
  }
  if (!finite(*measurement)) {
    throw std::invalid_argument("measurement must be finite");
  }

  const MeasurementMatrix h = position_measurement_matrix();
  const Measurement innovation = *measurement - h * state_;
  const MeasurementCovariance s = symmetrize(h * covariance_ * h.transpose() + config_.measurement_covariance);
  Eigen::LDLT<MeasurementCovariance> ldlt(s);
  if (ldlt.info() != Eigen::Success || !ldlt.isPositive()) {
    initialized_ = false;
    return Estimate{false, State::Zero(), Covariance::Identity(), "NUMERICAL_RESET"};
  }
  const Eigen::Matrix<double, 4, 2> gain =
      ldlt.solve((covariance_ * h.transpose()).transpose()).transpose();
  state_ += gain * innovation;
  const Covariance eye = Covariance::Identity();
  const Covariance joseph = eye - gain * h;
  covariance_ = symmetrize(
      joseph * covariance_ * joseph.transpose() +
      gain * config_.measurement_covariance * gain.transpose());

  if (!finite(state_) || !covariance_is_psd(covariance_, 1.0e-8)) {
    initialized_ = false;
    return Estimate{false, State::Zero(), Covariance::Identity(), "NONFINITE_OR_NONPSD_RESET"};
  }
  return Estimate{true, state_, covariance_, "TRACKING"};
}

}  // namespace ghost_x
