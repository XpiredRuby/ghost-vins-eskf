#include "ghost_x/config.hpp"

#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <string>

namespace {

std::filesystem::path write_temp(const std::string &name, const std::string &content) {
  const auto path = std::filesystem::temp_directory_path() / name;
  std::ofstream output(path);
  output << content;
  output.close();
  return path;
}

TEST(Configuration, LoadsDeterministically) {
  const auto path = write_temp(
      "ghost_x_config_valid.cfg",
      "measurement_r_xx_m2=0.0004\n"
      "measurement_r_xy_m2=0.00005\n"
      "measurement_r_yy_m2=0.00025\n"
      "cv_acceleration_std_mps2=0.65\n"
      "imm_smooth_acceleration_std_mps2=0.015\n"
      "imm_maneuver_acceleration_std_mps2=0.75\n"
      "imm_transition_00=0.97\n"
      "imm_transition_01=0.03\n"
      "imm_transition_10=0.08\n"
      "imm_transition_11=0.92\n"
      "imm_initial_probability_smooth=0.8\n"
      "imm_initial_probability_maneuver=0.2\n"
      "mh_gate_chi2=16\n"
      "mh_max_occlusion_s=20\n"
      "mh_max_workspace_range_m=100\n");
  const auto first = ghost_x::load_estimator_configuration(path);
  const auto second = ghost_x::load_estimator_configuration(path);
  EXPECT_EQ(first.source_digest_fnv1a64, second.source_digest_fnv1a64);
  EXPECT_DOUBLE_EQ(first.cv.measurement_covariance(0, 1), 5.0e-5);
  EXPECT_DOUBLE_EQ(first.imm.transition(1, 0), 0.08);
  EXPECT_DOUBLE_EQ(first.mh.gate_chi2, 16.0);
  std::filesystem::remove(path);
}

TEST(Configuration, RejectsUnknownAndDuplicateKeys) {
  const auto unknown = write_temp("ghost_x_config_unknown.cfg", "unknown=1\n");
  EXPECT_THROW(ghost_x::load_estimator_configuration(unknown), std::invalid_argument);
  std::filesystem::remove(unknown);

  const auto duplicate = write_temp(
      "ghost_x_config_duplicate.cfg",
      "cv_acceleration_std_mps2=0.65\ncv_acceleration_std_mps2=0.66\n");
  EXPECT_THROW(ghost_x::load_estimator_configuration(duplicate), std::invalid_argument);
  std::filesystem::remove(duplicate);
}

TEST(Configuration, RejectsInvalidCovarianceAndTransitionRows) {
  const auto covariance = write_temp(
      "ghost_x_config_bad_cov.cfg",
      "measurement_r_xx_m2=0.0001\nmeasurement_r_xy_m2=0.001\nmeasurement_r_yy_m2=0.0001\n");
  EXPECT_THROW(ghost_x::load_estimator_configuration(covariance), std::invalid_argument);
  std::filesystem::remove(covariance);

  const auto transition = write_temp(
      "ghost_x_config_bad_transition.cfg",
      "imm_transition_00=0.5\nimm_transition_01=0.4\n");
  EXPECT_THROW(ghost_x::load_estimator_configuration(transition), std::invalid_argument);
  std::filesystem::remove(transition);
}

}  // namespace
