#pragma once

#include "ghost_x/types.hpp"

namespace ghost_x {

Covariance cv_transition(double dt_s);
Covariance white_acceleration_process_noise(double dt_s, double acceleration_std_mps2);
MeasurementMatrix position_measurement_matrix();
double gaussian_log_likelihood(const Measurement &innovation, const MeasurementCovariance &innovation_covariance);

}  // namespace ghost_x
