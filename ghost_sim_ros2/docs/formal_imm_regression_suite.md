# Formal IMM Regression Suite

This document defines the permanent regression contract for the GHOST formal IMM work from steps 4a-4d.

The suite is intentionally synthetic and hardware-independent. It proves that the estimator math remains internally correct and that known caveats remain visible. It does not claim hardware-calibrated covariance performance.

## Scope

The standing pytest gate is:

```bash
pytest -q ghost_sim_ros2/test/test_formal_imm_regression_suite.py
```

It consolidates the validation checkpoints from:

| Step | Regression Coverage |
|---|---|
| 4a | CV/CA mode-matched Kalman filter convergence and 2-sigma coverage |
| 4b | Mode probability prediction, likelihood update, and unambiguous CV convergence |
| 4c | IMM mixing probabilities, mixed covariance, and mixed-vs-non-mixed switch comparison |
| 4d | Combined IMM output and white, colored AR(1), and maneuver-switch scenarios |

## Acceptance Criteria

| Check | Threshold |
|---|---:|
| CV 4a final position RMSE | `< 0.025 m` |
| CV 4a final velocity RMSE | `< 0.09 m/s` |
| CV 4a 2-sigma coverage | `[0.93, 0.98]` |
| CA 4a final position RMSE | `< 0.03 m` |
| CA 4a final velocity RMSE | `< 0.11 m/s` |
| CA 4a final acceleration RMSE | `< 0.09 m/s^2` |
| CA 4a 2-sigma coverage | `[0.93, 0.98]` |
| 4b unambiguous CV final mode probability | `>= 0.99` |
| 4c mixed mean post-switch error ratio | `<= 0.50` of non-mixed |
| 4c mixed peak post-switch error ratio | `<= 0.50` of non-mixed |
| 4c mixed maneuver-probability lag | faster than non-mixed |
| 4d white CV RMSE | `<= 0.02 m` |
| 4d white CV 2-sigma coverage | `>= 0.90` |
| 4d colored AR(1) RMSE | `<= 0.02 m` |
| 4d colored AR(1) 2-sigma coverage | `<= 0.90` |
| 4d maneuver RMSE | `< 0.05 m` |
| 4d maneuver final position error | `< 0.02 m` |
| 4d maneuver active-mode accuracy | `>= 0.75` |
| 4d maneuver probability lag to threshold | `<= 3 steps` |

## Burn-In Rationale

Coverage metrics exclude the first 20 steps. With `dt = 0.05 s`, this is:

```text
20 steps * 0.05 s = 1.0 s
```

That first second removes the deliberately broad candidate initial-covariance transient before judging covariance behavior. Mode-switch lag is not burn-in filtered; it is measured from the switch instant because the switch transient is the point of that test.

## Colored Noise Caveat

The colored case uses the same AR(1) drift pattern as `ghost_software_regime.py`:

```text
rho = 0.985
process_std = 0.0012 m
white_std = 0.0025 m
```

The expected behavior is not "good-looking calibrated covariance." The expected behavior is that position tracking can remain numerically close while 2-sigma coverage degrades because the Kalman update assumes white residuals. This is why the IMM combined covariance remains labeled `INVALID_IF_NOISE_IS_COLORED`.

## Maneuver Coverage Gap

The maneuver case is white-noise driven, but its 2-sigma coverage is lower than the steady CV case because the scored window includes an intentional model-switch transient.

During the switch, posterior mode mass moves between smooth and maneuver filters while the combined covariance is adapting. The metric is therefore a transient tracking regression, not a steady-state covariance calibration claim. The standing gate emphasizes position RMSE, final position error, active-mode accuracy, and mode-probability lag.

## Transition Matrix Invariants

Every IMM transition matrix must satisfy:

```text
- square matrix
- finite, nonnegative probabilities
- rows sum to 1
- shape matches filter count
```

These invariants are tested in the 4d and 4e pytest gates.
