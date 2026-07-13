#pragma once

#include <Eigen/Dense>

#include <cmath>
#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace ghost_x {

using State = Eigen::Matrix<double, 4, 1>;
using Covariance = Eigen::Matrix<double, 4, 4>;
using Measurement = Eigen::Matrix<double, 2, 1>;
using MeasurementCovariance = Eigen::Matrix<double, 2, 2>;
using MeasurementMatrix = Eigen::Matrix<double, 2, 4>;

struct Estimate {
  bool initialized{false};
  State state{State::Zero()};
  Covariance covariance{Covariance::Identity()};
  std::string status{"WAITING"};
};

struct MotionModel {
  std::string name;
  double acceleration_std_mps2{0.5};
  double ax_mps2{0.0};
  double ay_mps2{0.0};
  double speed_scale{1.0};
  double prior{1.0};
};

struct WeightedEstimate {
  std::string name;
  double weight{0.0};
  State state{State::Zero()};
  Covariance covariance{Covariance::Identity()};
  double age_s{0.0};
};

inline bool finite(const State &value) { return value.array().isFinite().all(); }
inline bool finite(const Covariance &value) { return value.array().isFinite().all(); }
inline bool finite(const Measurement &value) { return value.array().isFinite().all(); }
inline bool finite(const MeasurementCovariance &value) { return value.array().isFinite().all(); }

template <typename Derived>
inline auto symmetrize(const Eigen::MatrixBase<Derived> &value)
    -> Eigen::Matrix<double, Derived::RowsAtCompileTime, Derived::ColsAtCompileTime> {
  static_assert(Derived::RowsAtCompileTime == Derived::ColsAtCompileTime,
                "symmetrize requires a square matrix");
  return (0.5 * (value.derived() + value.derived().transpose())).eval();
}

bool covariance_is_psd(const Covariance &value, double tolerance = 1.0e-10);
bool covariance_is_spd(const MeasurementCovariance &value, double tolerance = 1.0e-12);

}  // namespace ghost_x
