#include "ghost_x/mode_bank.hpp"

#include <Eigen/Cholesky>

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace ghost_x {

std::vector<MotionModel> default_mode_bank() {
  return {
      {"constant_velocity", 0.65, 0.0, 0.0, 1.0, 0.34},
      {"brake_or_hover", 0.45, 0.0, 0.0, 0.88, 0.16},
      {"coordinated_turn_left", 0.55, -0.07, 0.11, 1.0, 0.16},
      {"coordinated_turn_right", 0.55, -0.07, -0.11, 1.0, 0.14},
      {"accelerate_forward", 0.90, 0.28, 0.0, 1.0, 0.08},
      {"lateral_left", 0.90, 0.0, 0.26, 1.0, 0.05},
      {"lateral_right", 0.90, 0.0, -0.26, 1.0, 0.05},
      {"evasive_maneuver", 1.80, 0.0, 0.0, 1.0, 0.02},
  };
}

ModeBankTracker::ModeBankTracker(ModeBankConfig config) : config_(std::move(config)) {
  if (config_.models.empty()) {
    config_.models = default_mode_bank();
  }
  if (!covariance_is_spd(config_.measurement_covariance)) {
    throw std::invalid_argument("measurement covariance must be symmetric positive definite");
  }
  if (!covariance_is_psd(config_.initial_covariance)) {
    throw std::invalid_argument("initial covariance must be positive semidefinite");
  }
  if (!std::isfinite(config_.gate_chi2) || config_.gate_chi2 <= 0.0 ||
      !std::isfinite(config_.max_occlusion_s) || config_.max_occlusion_s <= 0.0 ||
      !std::isfinite(config_.max_workspace_range_m) || config_.max_workspace_range_m <= 0.0) {
    throw std::invalid_argument("mode-bank limits must be finite and positive");
  }
  double prior_sum = 0.0;
  for (const auto &model : config_.models) {
    if (model.name.empty() || !std::isfinite(model.prior) || model.prior < 0.0 ||
        !std::isfinite(model.acceleration_std_mps2) || model.acceleration_std_mps2 <= 0.0) {
      throw std::invalid_argument("invalid motion model");
    }
    prior_sum += model.prior;
  }
  if (prior_sum <= 0.0) {
    throw std::invalid_argument("motion-model priors must sum positive");
  }
}

void ModeBankTracker::initialize(const Measurement &measurement) {
  if (!finite(measurement)) {
    throw std::invalid_argument("measurement must be finite");
  }
  State state = State::Zero();
  state(0) = measurement(0);
  state(1) = measurement(1);
  hypotheses_ = {{"visible_cv", 1.0, state, config_.initial_covariance, 0.0}};
}

ModeBankEstimate ModeBankTracker::step(
    double dt_s, const std::optional<Measurement> &measurement) {
  if (!std::isfinite(dt_s) || dt_s <= 0.0) {
    throw std::invalid_argument("dt_s must be finite and positive");
  }
  const bool visible = measurement.has_value();
  if (hypotheses_.empty()) {
    if (!visible) {
      return ModeBankEstimate{};
    }
    initialize(*measurement);
    was_visible_ = true;
    return combined("TRACKING");
  }

  predict(dt_s, visible);
  if (hypotheses_.empty()) {
    was_visible_ = false;
    return ModeBankEstimate{};
  }

  if (!visible) {
    hypotheses_.erase(
        std::remove_if(hypotheses_.begin(), hypotheses_.end(), [this](const auto &hypothesis) {
          return hypothesis.age_s > config_.max_occlusion_s;
        }),
        hypotheses_.end());
    normalize();
    was_visible_ = false;
    return combined(hypotheses_.empty() ? "EXPIRED" : "HYPOTHESIS_PREDICTION");
  }

  const bool accepted = update(*measurement);
  was_visible_ = true;
  return combined(accepted ? "TRACKING" : "MEASUREMENT_REJECTED");
}

void ModeBankTracker::predict(double dt_s, bool visible) {
  if (hypotheses_.empty()) {
    return;
  }
  std::vector<WeightedEstimate> predicted;
  const Covariance f = cv_transition(dt_s);

  auto propagate = [&](const WeightedEstimate &source, const MotionModel &model, double age_s) {
    WeightedEstimate result = source;
    result.name = model.name;
    result.state = f * source.state;
    result.state(0) += 0.5 * model.ax_mps2 * dt_s * dt_s;
    result.state(1) += 0.5 * model.ay_mps2 * dt_s * dt_s;
    result.state(2) = model.speed_scale * (source.state(2) + model.ax_mps2 * dt_s);
    result.state(3) = model.speed_scale * (source.state(3) + model.ay_mps2 * dt_s);
    result.covariance = symmetrize(
        f * source.covariance * f.transpose() +
        white_acceleration_process_noise(dt_s, model.acceleration_std_mps2));
    result.age_s = age_s;
    if (reasonable(result)) {
      predicted.push_back(result);
    }
  };

  if (visible) {
    const MotionModel visible_model{"visible_cv", 0.70, 0.0, 0.0, 1.0, 1.0};
    for (const auto &hypothesis : hypotheses_) {
      propagate(hypothesis, visible_model, 0.0);
    }
  } else if (was_visible_) {
    const ModeBankEstimate source = combined("BRANCH_SOURCE");
    double prior_sum = 0.0;
    for (const auto &model : config_.models) {
      prior_sum += model.prior;
    }
    for (const auto &model : config_.models) {
      WeightedEstimate root{model.name, model.prior / prior_sum, source.state, source.covariance, 0.0};
      propagate(root, model, dt_s);
    }
  } else {
    for (const auto &hypothesis : hypotheses_) {
      const auto found = std::find_if(config_.models.begin(), config_.models.end(), [&](const auto &model) {
        return model.name == hypothesis.name;
      });
      const MotionModel &model = found == config_.models.end() ? config_.models.front() : *found;
      propagate(hypothesis, model, hypothesis.age_s + dt_s);
    }
  }
  hypotheses_ = std::move(predicted);
  normalize();
}

bool ModeBankTracker::update(const Measurement &measurement) {
  std::vector<WeightedEstimate> updated;
  for (const auto &hypothesis : hypotheses_) {
    const Measurement innovation = measurement - measurement_matrix_ * hypothesis.state;
    const MeasurementCovariance innovation_covariance = symmetrize(
        measurement_matrix_ * hypothesis.covariance * measurement_matrix_.transpose() +
        config_.measurement_covariance);
    Eigen::LDLT<MeasurementCovariance> ldlt(innovation_covariance);
    if (ldlt.info() != Eigen::Success || !ldlt.isPositive()) {
      continue;
    }
    const double nis = innovation.dot(ldlt.solve(innovation));
    if (!std::isfinite(nis) || nis > config_.gate_chi2) {
      continue;
    }
    const Eigen::Matrix<double, 4, 2> gain =
        ldlt.solve((hypothesis.covariance * measurement_matrix_.transpose()).transpose()).transpose();
    WeightedEstimate result = hypothesis;
    result.state += gain * innovation;
    const Covariance eye = Covariance::Identity();
    const Covariance joseph = eye - gain * measurement_matrix_;
    result.covariance = symmetrize(
        joseph * hypothesis.covariance * joseph.transpose() +
        gain * config_.measurement_covariance * gain.transpose());
    result.weight *= std::exp(gaussian_log_likelihood(innovation, innovation_covariance));
    result.age_s = 0.0;
    if (reasonable(result)) {
      updated.push_back(result);
    }
  }
  if (updated.empty()) {
    return false;
  }
  hypotheses_ = std::move(updated);
  normalize();
  const ModeBankEstimate collapsed = combined("COLLAPSE");
  hypotheses_ = {{"visible_cv", 1.0, collapsed.state, collapsed.covariance, 0.0}};
  return true;
}

ModeBankEstimate ModeBankTracker::combined(std::string status) const {
  ModeBankEstimate result;
  if (hypotheses_.empty()) {
    result.status = std::move(status);
    return result;
  }
  result.initialized = true;
  result.status = std::move(status);
  result.hypotheses = hypotheses_;
  for (const auto &hypothesis : hypotheses_) {
    result.state += hypothesis.weight * hypothesis.state;
  }
  result.covariance = Covariance::Zero();
  for (const auto &hypothesis : hypotheses_) {
    const State delta = hypothesis.state - result.state;
    result.covariance += hypothesis.weight *
        (hypothesis.covariance + delta * delta.transpose());
  }
  result.covariance = symmetrize(result.covariance);
  return result;
}

void ModeBankTracker::normalize() {
  if (hypotheses_.empty()) {
    return;
  }
  double total = 0.0;
  for (const auto &hypothesis : hypotheses_) {
    total += std::max(0.0, hypothesis.weight);
  }
  if (!std::isfinite(total) || total <= 0.0) {
    const double uniform = 1.0 / static_cast<double>(hypotheses_.size());
    for (auto &hypothesis : hypotheses_) {
      hypothesis.weight = uniform;
    }
  } else {
    for (auto &hypothesis : hypotheses_) {
      hypothesis.weight = std::max(0.0, hypothesis.weight) / total;
    }
  }
  std::sort(hypotheses_.begin(), hypotheses_.end(), [](const auto &left, const auto &right) {
    return left.weight > right.weight;
  });
}

bool ModeBankTracker::reasonable(const WeightedEstimate &hypothesis) const {
  return finite(hypothesis.state) && covariance_is_psd(hypothesis.covariance, 1.0e-8) &&
      hypothesis.age_s <= config_.max_occlusion_s + 1.0e-12 &&
      std::hypot(hypothesis.state(0), hypothesis.state(1)) <= config_.max_workspace_range_m;
}

}  // namespace ghost_x
