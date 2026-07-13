#pragma once

#include "ghost_x/imm.hpp"
#include "ghost_x/kalman_filter.hpp"
#include "ghost_x/mode_bank.hpp"

#include <filesystem>
#include <map>
#include <string>

namespace ghost_x {

struct EstimatorConfiguration {
  KalmanConfig cv;
  ImmConfig imm;
  ModeBankConfig mh;
  std::map<std::string, double> scalar_values;
  std::string source_digest_fnv1a64;
};

EstimatorConfiguration default_estimator_configuration();
EstimatorConfiguration load_estimator_configuration(const std::filesystem::path &path);
std::string digest_file_fnv1a64(const std::filesystem::path &path);

}  // namespace ghost_x
