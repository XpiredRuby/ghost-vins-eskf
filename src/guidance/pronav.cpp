#include "pronav.hpp"

ProNav::ProNav(double N, double r_cutoff_meters, double K_sim)
    : N_(N)
    , r_cutoff_(r_cutoff_meters)
    , K_sim_(K_sim)
    , prev_delta_x_rel_(Eigen::Vector3d::Zero())
    , initialized_(false)
{}

void ProNav::reset() {
    prev_delta_x_rel_ = Eigen::Vector3d::Zero();
    initialized_ = false;
}

Eigen::Vector3d ProNav::compute(
    const Eigen::Vector3d& x_target_NED,
    const Eigen::Vector3d& x_drone_NED,
    double dt)
{
    // Step 1: Apply K_sim to XY only — Z forced to zero exactly
    Eigen::Vector3d x_target_scaled;
    x_target_scaled.x() = K_sim_ * x_target_NED.x();
    x_target_scaled.y() = K_sim_ * x_target_NED.y();
    x_target_scaled.z() = x_drone_NED.z();  // raw drone Z — delta will be zero

    Eigen::Vector3d delta_x_rel = x_target_scaled - x_drone_NED;
    delta_x_rel.z() = 0.0;  // enforce exactly zero — no numerical drift

    // Step 2: Range
    double range = delta_x_rel.norm();

    // Step 3: Terminal coast guard
    if (range < r_cutoff_) {
        prev_delta_x_rel_ = delta_x_rel;
        return Eigen::Vector3d::Zero();
    }

    // Step 4: First call — no finite difference yet, return zero
    if (!initialized_) {
        prev_delta_x_rel_ = delta_x_rel;
        initialized_ = true;
        return Eigen::Vector3d::Zero();
    }

    // Step 5: LOS rate
    Eigen::Vector3d delta_x_rel_dot = (delta_x_rel - prev_delta_x_rel_) / dt;
    Eigen::Vector3d Omega = delta_x_rel.cross(delta_x_rel_dot) / (range * range);

    // Step 6: Closing velocity
    Eigen::Vector3d V_c = -delta_x_rel_dot;

    // Step 7: TPN command — Omega x V_c (NOT V_c x Omega — that inverts direction)
    Eigen::Vector3d a_cmd = N_ * Omega.cross(V_c);

    prev_delta_x_rel_ = delta_x_rel;
    return a_cmd;
}