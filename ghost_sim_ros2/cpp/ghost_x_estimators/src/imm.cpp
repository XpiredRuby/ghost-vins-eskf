#include "ghost_x/imm.hpp"

#include "ghost_x/linear_model.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace ghost_x {

InteractingMultipleModel::InteractingMultipleModel(ImmConfig config)
    : config_(std::move(config)),
      filters_{CvKalmanFilter(config_.smooth), CvKalmanFilter(config_.maneuver)},
      probabilities_(config_.initial_probabilities) {
  validate_config();
  probabilities_ /= probabilities_.sum();
}

void InteractingMultipleModel::validate_config() const {
  if (!config_.transition.array().isFinite().all() || (config_.transition.array() < 0.0).any()) {
    throw std::invalid_argument("transition matrix must be finite and nonnegative");
  }
  for (Eigen::Index row = 0; row < config_.transition.rows(); ++row) {
    if (std::abs(config_.transition.row(row).sum() - 1.0) > 1.0e-12) {
      throw std::invalid_argument("each transition-matrix row must sum to one");
    }
  }
  if (!config_.initial_probabilities.array().isFinite().all() ||
      (config_.initial_probabilities.array() < 0.0).any() ||
      config_.initial_probabilities.sum() <= 0.0) {
    throw std::invalid_argument("initial probabilities must be finite, nonnegative and sum positive");
  }
}

void InteractingMultipleModel::initialize(const Measurement &measurement) {
  State initial = State::Zero();
  initial(0) = measurement(0);
  initial(1) = measurement(1);
  filters_[0].set_state(initial, config_.smooth.initial_covariance);
  filters_[1].set_state(initial, config_.maneuver.initial_covariance);
  initialized_ = true;
}

ImmEstimate InteractingMultipleModel::step(
    double dt_s, const std::optional<Measurement> &measurement) {
  if (!std::isfinite(dt_s) || dt_s <= 0.0) {
    throw std::invalid_argument("dt_s must be finite and positive");
  }
  if (!initialized_) {
    if (!measurement.has_value()) {
      return ImmEstimate{};
    }
    initialize(*measurement);
  }

  const Eigen::Vector2d normalization = config_.transition.transpose() * probabilities_;
  std::array<State, 2> mixed_states{State::Zero(), State::Zero()};
  std::array<Covariance, 2> mixed_covariances{Covariance::Zero(), Covariance::Zero()};

  for (std::size_t destination = 0; destination < 2; ++destination) {
    const double denominator = std::max(normalization(static_cast<Eigen::Index>(destination)), 1.0e-15);
    Eigen::Vector2d mixing;
    for (std::size_t source = 0; source < 2; ++source) {
      mixing(static_cast<Eigen::Index>(source)) =
          config_.transition(static_cast<Eigen::Index>(source), static_cast<Eigen::Index>(destination)) *
          probabilities_(static_cast<Eigen::Index>(source)) / denominator;
      mixed_states[destination] += mixing(static_cast<Eigen::Index>(source)) * filters_[source].state();
    }
    for (std::size_t source = 0; source < 2; ++source) {
      const State delta = filters_[source].state() - mixed_states[destination];
      mixed_covariances[destination] += mixing(static_cast<Eigen::Index>(source)) *
          (filters_[source].covariance() + delta * delta.transpose());
    }
    mixed_covariances[destination] = symmetrize(mixed_covariances[destination]);
  }

  std::array<double, 2> log_likelihoods{0.0, 0.0};
  std::array<Estimate, 2> mode_estimates;
  const MeasurementMatrix h = position_measurement_matrix();
  for (std::size_t mode = 0; mode < 2; ++mode) {
    filters_[mode].set_state(mixed_states[mode], mixed_covariances[mode]);
    if (measurement.has_value()) {
      const KalmanConfig &kalman_config = filters_[mode].config();
      const Covariance f = cv_transition(dt_s);
      const State predicted_state = f * mixed_states[mode];
      const Covariance predicted_covariance = symmetrize(
          f * mixed_covariances[mode] * f.transpose() +
          white_acceleration_process_noise(dt_s, kalman_config.acceleration_std_mps2));
      const Measurement innovation = *measurement - h * predicted_state;
      const MeasurementCovariance innovation_covariance = symmetrize(
          h * predicted_covariance * h.transpose() + kalman_config.measurement_covariance);
      log_likelihoods[mode] = gaussian_log_likelihood(innovation, innovation_covariance);
    }
    mode_estimates[mode] = filters_[mode].step(dt_s, measurement);
    if (!mode_estimates[mode].initialized) {
      initialized_ = false;
      return ImmEstimate{};
    }
  }

  Eigen::Vector2d updated = normalization;
  if (measurement.has_value()) {
    const double max_log = std::max(log_likelihoods[0], log_likelihoods[1]);
    for (std::size_t mode = 0; mode < 2; ++mode) {
      updated(static_cast<Eigen::Index>(mode)) *= std::exp(log_likelihoods[mode] - max_log);
    }
  }
  if (!updated.array().isFinite().all() || updated.sum() <= 0.0) {
    updated = Eigen::Vector2d::Constant(0.5);
  } else {
    updated /= updated.sum();
  }
  probabilities_ = updated;

  State combined_state = State::Zero();
  for (std::size_t mode = 0; mode < 2; ++mode) {
    combined_state += probabilities_(static_cast<Eigen::Index>(mode)) * mode_estimates[mode].state;
  }
  Covariance combined_covariance = Covariance::Zero();
  for (std::size_t mode = 0; mode < 2; ++mode) {
    const State delta = mode_estimates[mode].state - combined_state;
    combined_covariance += probabilities_(static_cast<Eigen::Index>(mode)) *
        (mode_estimates[mode].covariance + delta * delta.transpose());
  }
  combined_covariance = symmetrize(combined_covariance);

  ImmEstimate result;
  result.initialized = true;
  result.state = combined_state;
  result.covariance = combined_covariance;
  result.status = measurement.has_value() ? "TRACKING" : "PREDICTION_ONLY";
  result.mode_probabilities = {probabilities_(0), probabilities_(1)};
  return result;
}

}  // namespace ghost_x
