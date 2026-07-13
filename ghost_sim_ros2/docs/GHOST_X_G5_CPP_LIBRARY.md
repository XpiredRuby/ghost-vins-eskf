# GHOST-X G5 — Modern C++ Estimator Library

## Scope

G5 provides a ROS-independent C++20 estimator library under `cpp/ghost_x_estimators` with:

- constant-velocity Kalman filtering;
- a two-mode formal interacting multiple-model estimator;
- a persistent multi-hypothesis mode bank;
- separated linear dynamics, process noise, measurement update, likelihood, IMM mixing, and hypothesis logic;
- deterministic configuration loading;
- a CSV replay CLI;
- GoogleTest mathematical/property verification;
- AddressSanitizer and UndefinedBehaviorSanitizer builds;
- independent Python reference-vector comparison.

The library uses Eigen fixed-size matrices and Joseph-form covariance updates. Configuration parsing rejects unknown keys, duplicate keys, non-finite values, invalid covariance matrices, and transition rows that do not sum to one.

## Build and test

```bash
cmake -S ghost_sim_ros2/cpp/ghost_x_estimators \
  -B /tmp/ghost_x_cpp_build \
  -DGHOST_X_BUILD_TESTS=ON
cmake --build /tmp/ghost_x_cpp_build -j2
/tmp/ghost_x_cpp_build/ghost_x_cpp_tests
```

Sanitized build:

```bash
cmake -S ghost_sim_ros2/cpp/ghost_x_estimators \
  -B /tmp/ghost_x_cpp_sanitized \
  -DGHOST_X_BUILD_TESTS=ON \
  -DGHOST_X_ENABLE_SANITIZERS=ON
cmake --build /tmp/ghost_x_cpp_sanitized -j2
/tmp/ghost_x_cpp_sanitized/ghost_x_cpp_tests
```

## Deterministic replay

```bash
/tmp/ghost_x_cpp_build/ghost_x_estimator_cli \
  imm input.csv output.csv \
  ghost_sim_ros2/cpp/ghost_x_estimators/config/default_estimator.cfg
```

The CSV contract is:

```text
t_s,visible,x_m,y_m
```

## Verification evidence

- 10 C++ tests cover transition/process-noise construction, CV tracking, prediction-only covariance growth, IMM probability normalization, covariance PSD/symmetry, mode-bank branching and normalization, deterministic repeatability, stress sequences, and configuration rejection.
- Python/C++ comparison covers 24 canonical G4 trials and all three estimators.
- Maximum observed state and covariance differences are recorded in `GHOST_X_G5_EQUIVALENCE.json`.
- The equivalence validator refuses partial coverage or a failing estimator.

## Claims boundary

The G5 evidence demonstrates deterministic software equivalence on pinned synthetic streams. It does not prove physical accuracy, measurement-model validity, hard real-time behavior, or flight qualification. Those claims remain gated by G3/G4 physical collection, G6 consistency validity, and G9 timing evidence.
