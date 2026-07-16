#include "ghost_x/imm.hpp"
#include "ghost_x/kalman_filter.hpp"
#include "ghost_x/linear_model.hpp"
#include "ghost_x/mode_bank.hpp"

#include <gtest/gtest.h>

#include <cmath>
#include <optional>

namespace {

ghost_x::Measurement measurement(double x, double y) {
  ghost_x::Measurement value;
  value << x, y;
  return value;
}

TEST(LinearModel, TransitionAndNoiseAreValid) {
  const auto f = ghost_x::cv_transition(0.1);
  EXPECT_DOUBLE_EQ(f(0, 2), 0.1);
  EXPECT_DOUBLE_EQ(f(1, 3), 0.1);
  const auto q = ghost_x::white_acceleration_process_noise(0.1, 0.65);
  EXPECT_TRUE(q.isApprox(q.transpose(), 1.0e-14));
  EXPECT_TRUE(ghost_x::covariance_is_psd(q));
}

TEST(CvKalman, TracksAndMaintainsPsdCovariance) {
  ghost_x::MeasurementCovariance r;
  r << 4.0e-4, 5.0e-5, 5.0e-5, 2.5e-4;
  ghost_x::KalmanConfig config;
  config.measurement_covariance = r;
  ghost_x::CvKalmanFilter filter(config);
  ghost_x::Estimate estimate;
  for (int index = 0; index < 100; ++index) {
    const double t = 0.1 * static_cast<double>(index);
    estimate = filter.step(0.1, measurement(1.0 + 0.2 * t, -0.3 + 0.05 * t));
    ASSERT_TRUE(estimate.initialized);
    EXPECT_TRUE(ghost_x::covariance_is_psd(estimate.covariance, 1.0e-8));
    EXPECT_TRUE(estimate.covariance.isApprox(estimate.covariance.transpose(), 1.0e-12));
  }
  EXPECT_NEAR(estimate.state(2), 0.2, 0.02);
  EXPECT_NEAR(estimate.state(3), 0.05, 0.02);
}

TEST(CvKalman, PredictionOnlyCovarianceGrows) {
  ghost_x::CvKalmanFilter filter;
  auto estimate = filter.step(0.1, measurement(1.0, 0.0));
  const double initial_trace = estimate.covariance.block<2, 2>(0, 0).trace();
  for (int index = 0; index < 20; ++index) {
    estimate = filter.step(0.1, std::nullopt);
  }
  const double predicted_trace = estimate.covariance.block<2, 2>(0, 0).trace();
  EXPECT_GT(predicted_trace, initial_trace);
  EXPECT_EQ(estimate.status, "PREDICTION_ONLY");
}

TEST(Imm, ProbabilitiesNormalizeAndCovarianceRemainsPsd) {
  ghost_x::InteractingMultipleModel imm;
  ghost_x::ImmEstimate estimate;
  for (int index = 0; index < 80; ++index) {
    const double t = 0.1 * static_cast<double>(index);
    const std::optional<ghost_x::Measurement> z =
        (index >= 35 && index < 50) ? std::nullopt : std::optional(measurement(0.5 + 0.15 * t, 0.1));
    estimate = imm.step(0.1, z);
    ASSERT_TRUE(estimate.initialized);
    EXPECT_NEAR(estimate.mode_probabilities[0] + estimate.mode_probabilities[1], 1.0, 1.0e-12);
    EXPECT_GE(estimate.mode_probabilities[0], 0.0);
    EXPECT_GE(estimate.mode_probabilities[1], 0.0);
    EXPECT_TRUE(ghost_x::covariance_is_psd(estimate.covariance, 1.0e-7));
  }
}

TEST(ModeBank, BranchesAndNormalizesDuringOcclusion) {
  ghost_x::ModeBankTracker tracker;
  for (int index = 0; index < 20; ++index) {
    const double t = 0.1 * static_cast<double>(index);
    ASSERT_TRUE(tracker.step(0.1, measurement(1.0 + 0.2 * t, 0.05 * t)).initialized);
  }
  const auto hidden = tracker.step(0.1, std::nullopt);
  ASSERT_TRUE(hidden.initialized);
  EXPECT_GT(hidden.hypotheses.size(), 1U);
  double total = 0.0;
  for (const auto &hypothesis : hidden.hypotheses) {
    total += hypothesis.weight;
    EXPECT_TRUE(ghost_x::covariance_is_psd(hypothesis.covariance, 1.0e-7));
  }
  EXPECT_NEAR(total, 1.0, 1.0e-12);
}

TEST(ModeBank, DeterministicForIdenticalInputs) {
  ghost_x::ModeBankTracker first;
  ghost_x::ModeBankTracker second;
  for (int index = 0; index < 80; ++index) {
    const double t = 0.1 * static_cast<double>(index);
    const std::optional<ghost_x::Measurement> z =
        (index >= 30 && index < 55) ? std::nullopt : std::optional(measurement(0.4 + 0.1 * t, -0.2 + 0.04 * t));
    const auto a = first.step(0.1, z);
    const auto b = second.step(0.1, z);
    EXPECT_EQ(a.initialized, b.initialized);
    if (a.initialized) {
      EXPECT_TRUE(a.state.isApprox(b.state, 1.0e-14));
      EXPECT_TRUE(a.covariance.isApprox(b.covariance, 1.0e-14));
    }
  }
}

TEST(Property, CovarianceSymmetryAndPsdAcrossStressSequence) {
  ghost_x::CvKalmanFilter cv;
  ghost_x::InteractingMultipleModel imm;
  ghost_x::ModeBankTracker mh;
  for (int index = 0; index < 300; ++index) {
    const double t = 0.05 * static_cast<double>(index);
    const bool hidden = (index % 73) >= 45 && (index % 73) < 60;
    const std::optional<ghost_x::Measurement> z = hidden
        ? std::nullopt
        : std::optional(measurement(1.0 + 0.12 * t + 0.01 * std::sin(t), -0.2 + 0.05 * t));
    const ghost_x::Estimate a = cv.step(0.05, z);
    const ghost_x::Estimate b = imm.step(0.05, z);
    const ghost_x::Estimate c = mh.step(0.05, z);
    for (const auto *estimate : {&a, &b, &c}) {
      if (estimate->initialized) {
        EXPECT_TRUE(estimate->covariance.isApprox(estimate->covariance.transpose(), 1.0e-10));
        EXPECT_TRUE(ghost_x::covariance_is_psd(estimate->covariance, 1.0e-6));
      }
    }
  }
}

}  // namespace
