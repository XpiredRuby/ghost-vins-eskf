#pragma once

#include "ghost_x/kalman_filter.hpp"

#include <Eigen/Dense>
#include <array>
#include <optional>
#include <string>

namespace ghost_x {

struct ImmConfig {
  KalmanConfig smooth;
  KalmanConfig maneuver;
  Eigen::Matrix2d transition{(Eigen::Matrix2d() << 0.97, 0.03, 0.08, 0.92).finished()};
  Eigen::Vector2d initial_probabilities{0.8, 0.2};
};

struct ImmEstimate : Estimate {
  std::array<double, 2> mode_probabilities{0.5, 0.5};
  std::array<std::string, 2> mode_names{"smooth_cv", "maneuver_cv"};
};

class InteractingMultipleModel {
 public:
  explicit InteractingMultipleModel(ImmConfig config = {});
  ImmEstimate step(double dt_s, const std::optional<Measurement> &measurement);
  [[nodiscard]] bool initialized() const noexcept { return initialized_; }

 private:
  void initialize(const Measurement &measurement);
  void validate_config() const;
  ImmConfig config_;
  bool initialized_{false};
  std::array<CvKalmanFilter, 2> filters_;
  Eigen::Vector2d probabilities_{0.8, 0.2};
};

}  // namespace ghost_x
