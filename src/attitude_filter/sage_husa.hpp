#pragma once
#include <Eigen/Dense>

class SageHusa {
public:
    SageHusa(int meas_dim, double forgetting_factor = 0.98);

    Eigen::MatrixXd updateR(const Eigen::VectorXd& innovation,
                            const Eigen::MatrixXd& H,
                            const Eigen::MatrixXd& P_prior);

private:
    int             dim_;
    double          d_;          // forgetting factor
    Eigen::MatrixXd R_hat_;      // current adaptive R estimate
    double          R_min_eig_;  // eigenvalue floor — never let R go singular

    void enforcePositiveDefinite();
};
