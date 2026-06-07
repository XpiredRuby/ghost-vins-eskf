#pragma once
#include <Eigen/Dense>
#include <fstream>

class CTRVFilter {
public:
    CTRVFilter();

    void initialize(const Eigen::Vector2d& pos_init, double v_init, double psi_init);
    void predict(double dt);
    void update(const Eigen::Vector2d& z_pos);

    Eigen::VectorXd getState() const;
    Eigen::MatrixXd getCovariance() const;
    bool isInitialized() const;

    void setProcessNoise(double sigma_a, double sigma_psi_dot);
    void setMeasurementNoise(double sigma_r);

    // Override the hardcoded P₀ written by initialize() with YAML-loaded values.
    void setInitialCovariance(double sigma_pos_m,
                              double sigma_vel_m_per_s,
                              double sigma_psi_rad,
                              double sigma_psi_dot_rad_per_s);

    // Override the singularity guard threshold loaded from filter.yaml.
    // Controls both ctrvPredictSingle() branch point and (via tracker_node) useCTRV().
    void setSingularityGuard(double eps_rad_per_s);

private:
    // ── UKF compile-time constants (alpha=0.001, kappa=0, beta=2, n=5) ─────────
    // Declared first so the fixed-size member types below can use kN_ / kNSigma_.
    static constexpr int    kN_      = 5;
    static constexpr int    kNSigma_ = 2 * kN_ + 1;   // 11 sigma points
    static constexpr double kAlpha_  = 0.001;
    static constexpr double kKappa_  = 0.0;
    static constexpr double kBeta_   = 2.0;
    static constexpr double kLambda_ = kAlpha_ * kAlpha_ * (kN_ + kKappa_) - kN_;
    static constexpr double kWm0_    = kLambda_ / (kN_ + kLambda_);
    static constexpr double kWc0_    = kWm0_ + (1.0 - kAlpha_ * kAlpha_ + kBeta_);
    static constexpr double kWi_     = 1.0 / (2.0 * (kN_ + kLambda_));

    using State5d = Eigen::Matrix<double, kN_, 1>;

    // ── State — all fixed-size; zero heap allocation on the predict/update path ─
    // (previously Eigen::VectorXd / Eigen::MatrixXd, which heap-allocate on every
    //  assignment such as x_ = x_pred and P_ = P_pred inside predict()/update().)
    State5d                   x_;   // 5-state: [px, py, v, psi, psi_dot]
    Eigen::Matrix<double,5,5> P_;   // 5x5 covariance
    Eigen::Matrix<double,5,5> Q_;   // 5x5 process noise
    Eigen::Matrix<double,2,2> R_;   // 2x2 measurement noise

    bool   initialized_;
    double sigma_a_;
    double sigma_psi_dot_;
    double singularity_guard_eps_{1e-4};   // loaded from filter.yaml via setSingularityGuard()
    std::ofstream nis_log_;                // opened once in initialize(), kept open

    // Fixed-size sigma point buffers — zero per-call heap allocation
    Eigen::Matrix<double, kN_, kNSigma_> sigma_buf_;        // [5 x 11] current sigma pts
    Eigen::Matrix<double, kN_, kNSigma_> sigma_pred_buf_;   // [5 x 11] propagated
    Eigen::Matrix<double, 2,   kNSigma_> z_sigma_buf_;      // [2 x 11] projected to meas space

    // Takes Ref<> so column views of sigma_buf_ bind without a copy
    State5d ctrvPredictSingle(const Eigen::Ref<const State5d>& x, double dt) const;
    void generateSigmaPoints();   // fills sigma_buf_ from x_, P_
    void logNIS(double nis);
};
