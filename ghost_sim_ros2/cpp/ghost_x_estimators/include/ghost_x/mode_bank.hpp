#pragma once

#include "ghost_x/linear_model.hpp"
#include "ghost_x/types.hpp"

#include <optional>
#include <vector>

namespace ghost_x {

struct ModeBankConfig {
  std::vector<MotionModel> models;
  MeasurementCovariance measurement_covariance{MeasurementCovariance::Identity() * 4.0e-4};
  double gate_chi2{16.0};
  double max_occlusion_s{20.0};
  double max_workspace_range_m{100.0};
  Covariance initial_covariance{(Covariance() << 0.04, 0.0, 0.0, 0.0,
                                               0.0, 0.04, 0.0, 0.0,
                                               0.0, 0.0, 0.8, 0.0,
                                               0.0, 0.0, 0.0, 0.8).finished()};
};

struct ModeBankEstimate : Estimate {
  std::vector<WeightedEstimate> hypotheses;
};

std::vector<MotionModel> default_mode_bank();

class ModeBankTracker {
 public:
  explicit ModeBankTracker(ModeBankConfig config = {});
  ModeBankEstimate step(double dt_s, const std::optional<Measurement> &measurement);
  [[nodiscard]] bool initialized() const noexcept { return !hypotheses_.empty(); }

 private:
  void initialize(const Measurement &measurement);
  void predict(double dt_s, bool visible);
  bool update(const Measurement &measurement);
  ModeBankEstimate combined(std::string status) const;
  void normalize();
  bool reasonable(const WeightedEstimate &hypothesis) const;

  ModeBankConfig config_;
  MeasurementMatrix measurement_matrix_{position_measurement_matrix()};
  std::vector<WeightedEstimate> hypotheses_;
  bool was_visible_{false};
};

}  // namespace ghost_x
