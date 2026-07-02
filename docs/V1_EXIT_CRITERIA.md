# GHOST V1 Exit Criteria

V1 is complete only when the following criteria are satisfied. These criteria are fixed before final validation to avoid post-hoc threshold selection.

## 18.1 Documentation Scope Correction

- [ ] README labels the current system as V1: vision-only calibrated AprilTag occlusion tracker with a heuristic hypothesis bank.
- [ ] Top-level documentation states the V1/V2/V3 roadmap.
- [ ] V1 documentation does not claim active IMU fusion, active ESKF, formal MHT, or formal IMM.

## 18.2 Stationary Noise Characterization

Status: **blocked on controlled hardware runs**.

- [ ] 30–60 s stationary AprilTag log collected with the tag physically motionless.
- [ ] Position jitter reported for x/y.
- [ ] Apparent velocity noise floor computed from windowed velocity estimates.
- [ ] Autocorrelation, PSD, and Allan deviation reported.
- [ ] Camera exposure, gain, white balance, and dynamic framerate settings recorded.
- [ ] Stationary threshold derived from measured data, not guessed.

## 18.3 Stationary-Hold Fix Implementation

- [ ] Stationary gate implemented as a standalone tested module.
- [ ] Gate uses configurable window length and enter/exit hysteresis thresholds.
- [ ] Unit tests cover stationary data, slow constant motion, and transition cases.
- [ ] ROS integration suppresses dynamic futures when stationary lock is active during occlusion.
- [ ] Dashboard/status clearly reports stationary hold rather than generic prediction.

## 18.4 Independent Ground-Truth Grid Validation

Status: **blocked on hardware runs**.

- [ ] Measured floor/grid coordinates established.
- [ ] Pass/fail threshold written before the validation run.
- [ ] Bias, RMSE, standard deviation, and 95th percentile error reported.
- [ ] Results explicitly marked pass/fail against the pre-stated threshold.

## 18.5 Nonlinear Trial Suite

Status: **blocked on hardware runs**.

- [ ] Conditions include stationary occlusion, sudden stop, direction change, and lateral hidden motion.
- [ ] Minimum 5–8 repetitions per condition.
- [ ] Constant-velocity baseline compared against V1 heuristic bank.
- [ ] Statistical comparison or confidence interval reported per condition.

## 18.6 Complexity Justification Gate

- [ ] At least one nonlinear condition shows the heuristic bank outperforming constant velocity with statistical support.
- [ ] If no condition clears this gate, the report states that V1 complexity is not yet justified over the simpler baseline.

## 18.7 Contribution Weighting and Reframing

- [ ] Dashboard/replay described as supporting evidence infrastructure, not the main technical contribution.
- [ ] Main technical contribution framed around estimator honesty, bounded uncertainty, validation, and baseline comparison.

## V1 to V2 Transition Rule

V2 IMM work should not replace the live V1 heuristic bank until V1 has completed the documentation, stationary-hold, validation, and complexity-justification gates above. V2 can be developed in parallel as a separate simulation-validated module.
