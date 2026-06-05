#include "sage_husa.hpp"

SageHusa::SageHusa(int meas_dim, double forgetting_factor)
    : dim_(meas_dim)
    , d_(forgetting_factor)
    , R_hat_(Eigen::MatrixXd::Identity(meas_dim, meas_dim))
    , R_min_eig_(1e-6)
{}

Eigen::MatrixXd SageHusa::updateR(const Eigen::VectorXd& innovation,
                                   const Eigen::MatrixXd& H,
                                   const Eigen::MatrixXd& P_prior)
{
    const Eigen::MatrixXd correction =
        innovation * innovation.transpose() - H * P_prior * H.transpose();

    R_hat_ = (1.0 - d_) * R_hat_ + d_ * correction;

    enforcePositiveDefinite();
    return R_hat_;
}

void SageHusa::enforcePositiveDefinite()
{
    // Symmetrize first to eliminate floating-point asymmetry
    R_hat_ = 0.5 * (R_hat_ + R_hat_.transpose());

    // Find minimum eigenvalue and add floor if needed
    const Eigen::SelfAdjointEigenSolver<Eigen::MatrixXd> es(R_hat_);
    const double min_eig = es.eigenvalues().minCoeff();

    if (min_eig < R_min_eig_) {
        R_hat_ += (R_min_eig_ - min_eig) * Eigen::MatrixXd::Identity(dim_, dim_);
    }
}
