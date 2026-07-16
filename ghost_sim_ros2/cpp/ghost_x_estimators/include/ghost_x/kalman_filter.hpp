#pragma once

#include "ghost_x/types.hpp"

#include <optional>

namespace ghost_x {

struct KalmanConfig {
  double acceleration_std_mps2{0.65};
  MeasurementCovariance measurement_covariance{MeasurementCovariance::Identity() * 4.0e-4};
  Covariance initial_covariance{(Covariance() << 0.04, 0.0, 0.0, 0.0,
                                               0.0, 0.04, 0.0, 0.0,
                                               0.0, 0.0, 0.8, 0.0,
                                               0.0, 0.0, 0.0, 0.8).finished()};
};

class CvKalmanFilter {
 public:
  explicit CvKalmanFilter(KalmanConfig config = {});

  Estimate step(double dt_s, const std::optional<Measurement> &measurement);
  void initialize(const Measurement &measurement, const State &initial_state = State::Zero());
  void set_state(const State &state, const Covariance &covariance);
  [[nodiscard]] bool initialized() const noexcept { return initialized_; }
  [[nodiscard]] const State &state() const { return state_; }
  [[nodiscard]] const Covariance &covariance() const { return covariance_; }
  [[nodiscard]] const KalmanConfig &config() const noexcept { return config_; }

 private:
  KalmanConfig config_;
  bool initialized_{false};
  State state_{State::Zero()};
  Covariance covariance_{Covariance::Identity()};
};

}  // namespace ghost_x
