#include "ghost_x/config.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

namespace ghost_x {
namespace {

std::string trim(std::string value) {
  auto not_space = [](unsigned char ch) { return !std::isspace(ch); };
  value.erase(value.begin(), std::find_if(value.begin(), value.end(), not_space));
  value.erase(std::find_if(value.rbegin(), value.rend(), not_space).base(), value.end());
  return value;
}

double parse_finite(const std::string &key, const std::string &text) {
  std::size_t consumed = 0;
  double value = 0.0;
  try {
    value = std::stod(text, &consumed);
  } catch (const std::exception &) {
    throw std::invalid_argument("invalid numeric value for " + key);
  }
  if (consumed != text.size() || !std::isfinite(value)) {
    throw std::invalid_argument("non-finite or malformed numeric value for " + key);
  }
  return value;
}

void require_positive(const std::string &key, double value) {
  if (!std::isfinite(value) || value <= 0.0) {
    throw std::invalid_argument(key + " must be finite and positive");
  }
}

void require_probability(const std::string &key, double value) {
  if (!std::isfinite(value) || value < 0.0 || value > 1.0) {
    throw std::invalid_argument(key + " must be in [0,1]");
  }
}

void apply(EstimatorConfiguration &config, const std::string &key, double value) {
  config.scalar_values[key] = value;
  if (key == "measurement_r_xx_m2") {
    config.cv.measurement_covariance(0, 0) = value;
    config.imm.smooth.measurement_covariance(0, 0) = value;
    config.imm.maneuver.measurement_covariance(0, 0) = value;
    config.mh.measurement_covariance(0, 0) = value;
  } else if (key == "measurement_r_xy_m2") {
    config.cv.measurement_covariance(0, 1) = value;
    config.cv.measurement_covariance(1, 0) = value;
    config.imm.smooth.measurement_covariance(0, 1) = value;
    config.imm.smooth.measurement_covariance(1, 0) = value;
    config.imm.maneuver.measurement_covariance(0, 1) = value;
    config.imm.maneuver.measurement_covariance(1, 0) = value;
    config.mh.measurement_covariance(0, 1) = value;
    config.mh.measurement_covariance(1, 0) = value;
  } else if (key == "measurement_r_yy_m2") {
    config.cv.measurement_covariance(1, 1) = value;
    config.imm.smooth.measurement_covariance(1, 1) = value;
    config.imm.maneuver.measurement_covariance(1, 1) = value;
    config.mh.measurement_covariance(1, 1) = value;
  } else if (key == "cv_acceleration_std_mps2") {
    config.cv.acceleration_std_mps2 = value;
  } else if (key == "imm_smooth_acceleration_std_mps2") {
    config.imm.smooth.acceleration_std_mps2 = value;
  } else if (key == "imm_maneuver_acceleration_std_mps2") {
    config.imm.maneuver.acceleration_std_mps2 = value;
  } else if (key == "imm_transition_00") {
    config.imm.transition(0, 0) = value;
  } else if (key == "imm_transition_01") {
    config.imm.transition(0, 1) = value;
  } else if (key == "imm_transition_10") {
    config.imm.transition(1, 0) = value;
  } else if (key == "imm_transition_11") {
    config.imm.transition(1, 1) = value;
  } else if (key == "imm_initial_probability_smooth") {
    config.imm.initial_probabilities(0) = value;
  } else if (key == "imm_initial_probability_maneuver") {
    config.imm.initial_probabilities(1) = value;
  } else if (key == "mh_gate_chi2") {
    config.mh.gate_chi2 = value;
  } else if (key == "mh_max_occlusion_s") {
    config.mh.max_occlusion_s = value;
  } else if (key == "mh_max_workspace_range_m") {
    config.mh.max_workspace_range_m = value;
  } else {
    throw std::invalid_argument("unknown configuration key: " + key);
  }
}

void validate(EstimatorConfiguration &config) {
  require_positive("measurement_r_xx_m2", config.cv.measurement_covariance(0, 0));
  require_positive("measurement_r_yy_m2", config.cv.measurement_covariance(1, 1));
  if (!covariance_is_spd(config.cv.measurement_covariance)) {
    throw std::invalid_argument("measurement covariance must be symmetric positive definite");
  }
  require_positive("cv_acceleration_std_mps2", config.cv.acceleration_std_mps2);
  require_positive("imm_smooth_acceleration_std_mps2", config.imm.smooth.acceleration_std_mps2);
  require_positive("imm_maneuver_acceleration_std_mps2", config.imm.maneuver.acceleration_std_mps2);
  for (Eigen::Index row = 0; row < 2; ++row) {
    for (Eigen::Index col = 0; col < 2; ++col) {
      require_probability("imm_transition", config.imm.transition(row, col));
    }
    if (std::abs(config.imm.transition.row(row).sum() - 1.0) > 1.0e-12) {
      throw std::invalid_argument("each IMM transition row must sum to one");
    }
  }
  require_probability("imm_initial_probability_smooth", config.imm.initial_probabilities(0));
  require_probability("imm_initial_probability_maneuver", config.imm.initial_probabilities(1));
  if (std::abs(config.imm.initial_probabilities.sum() - 1.0) > 1.0e-12) {
    throw std::invalid_argument("IMM initial probabilities must sum to one");
  }
  require_positive("mh_gate_chi2", config.mh.gate_chi2);
  require_positive("mh_max_occlusion_s", config.mh.max_occlusion_s);
  require_positive("mh_max_workspace_range_m", config.mh.max_workspace_range_m);
}

}  // namespace

EstimatorConfiguration default_estimator_configuration() {
  EstimatorConfiguration config;
  MeasurementCovariance r;
  r << 4.0e-4, 5.0e-5, 5.0e-5, 2.5e-4;
  config.cv.measurement_covariance = r;
  config.cv.acceleration_std_mps2 = 0.65;
  config.imm.smooth.measurement_covariance = r;
  config.imm.smooth.acceleration_std_mps2 = 0.015;
  config.imm.maneuver.measurement_covariance = r;
  config.imm.maneuver.acceleration_std_mps2 = 0.75;
  config.mh.measurement_covariance = r;
  config.mh.models = default_mode_bank();
  return config;
}

EstimatorConfiguration load_estimator_configuration(const std::filesystem::path &path) {
  std::ifstream input(path);
  if (!input) {
    throw std::runtime_error("cannot open estimator configuration: " + path.string());
  }
  EstimatorConfiguration config = default_estimator_configuration();
  std::set<std::string> seen;
  std::string line;
  std::size_t line_number = 0;
  while (std::getline(input, line)) {
    ++line_number;
    const auto comment = line.find('#');
    if (comment != std::string::npos) {
      line.erase(comment);
    }
    line = trim(line);
    if (line.empty()) {
      continue;
    }
    const auto separator = line.find('=');
    if (separator == std::string::npos || line.find('=', separator + 1) != std::string::npos) {
      throw std::invalid_argument("expected key=value at line " + std::to_string(line_number));
    }
    const std::string key = trim(line.substr(0, separator));
    const std::string text = trim(line.substr(separator + 1));
    if (key.empty() || text.empty()) {
      throw std::invalid_argument("empty key or value at line " + std::to_string(line_number));
    }
    if (!seen.insert(key).second) {
      throw std::invalid_argument("duplicate configuration key: " + key);
    }
    apply(config, key, parse_finite(key, text));
  }
  validate(config);
  config.source_digest_fnv1a64 = digest_file_fnv1a64(path);
  return config;
}

std::string digest_file_fnv1a64(const std::filesystem::path &path) {
  std::ifstream input(path, std::ios::binary);
  if (!input) {
    throw std::runtime_error("cannot open file for digest: " + path.string());
  }
  std::uint64_t hash = 14695981039346656037ULL;
  char byte = 0;
  while (input.get(byte)) {
    hash ^= static_cast<unsigned char>(byte);
    hash *= 1099511628211ULL;
  }
  std::ostringstream stream;
  stream << "fnv1a64:" << std::hex << std::setfill('0') << std::setw(16) << hash;
  return stream.str();
}

}  // namespace ghost_x
