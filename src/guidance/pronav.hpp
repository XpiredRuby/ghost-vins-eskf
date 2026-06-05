#pragma once
#include <Eigen/Dense>

class ProNav {
public:
    ProNav(double N = 3.0, double r_cutoff_meters = 1.5, double K_sim = 1.0);

    Eigen::Vector3d compute(
        const Eigen::Vector3d& x_target_NED,
        const Eigen::Vector3d& x_drone_NED,
        double dt
    );

    void reset();

private:
    double N_;
    double r_cutoff_;
    double K_sim_;
    Eigen::Vector3d prev_delta_x_rel_;
    bool initialized_;
};