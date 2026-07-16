# GHOST-X G10 Deterministic Replay and CI

Overall: `PASS`
Checks: `47/47`
Deterministic files: `123`
Deterministic tree hash: `sha256:f8a928a3afec99f690bb434413adf9fd46bdc24b2e974c2db80df5b5e49ae82e`

## Regression gates

| Gate | Result | Actual | Expected |
|---|---|---|---|
| `G4_PLANNED_TRIALS` | PASS | `24` | `24` |
| `G4_ACCEPTED_TRIALS` | PASS | `24` | `24` |
| `G4_INVALID_TRIALS` | PASS | `0` | `0` |
| `G4_SCENARIO_FAMILIES` | PASS | `8` | `8` |
| `G4_ESTIMATORS` | PASS | `3` | `3` |
| `G4_CV_KALMAN_POSITION_RMSE` | PASS | `0.05010579701434604` | `{"max": 0.3}` |
| `G4_FORMAL_IMM_POSITION_RMSE` | PASS | `0.03442351202869739` | `{"max": 0.15}` |
| `G4_GHOST_MH_POSITION_RMSE` | PASS | `0.12414750666117878` | `{"max": 0.4}` |
| `G4_CV_KALMAN_HIDDEN_RMSE` | PASS | `0.18211336358696475` | `{"max": 1.0}` |
| `G4_FORMAL_IMM_HIDDEN_RMSE` | PASS | `0.13049749093036478` | `{"max": 0.4}` |
| `G4_GHOST_MH_HIDDEN_RMSE` | PASS | `0.4666416857961139` | `{"max": 0.9}` |
| `G4_IDENTICAL_ESTIMATOR_INPUTS` | PASS | `true` | `true` |
| `G10_DETERMINISTIC_REPLAY_HASHES` | PASS | `{"difference_count": 0, "first": "sha256:f8a928a3afec99f690bb434413adf9fd46bdc24b2e974c2db80df5b5e49ae82e", "second": "sha256:f8a928a3afec99f690bb434413adf9fd46bdc24b2e974c2db80df5b5e49ae82e"}` | `{"difference_count": 0, "tree_hashes_identical": true}` |
| `G10_NEGATIVE_HASH_REGRESSION_REJECTED` | PASS | `1` | `{"minimum_detected_differences": 1}` |
| `G10_NEGATIVE_METRIC_REGRESSION_REJECTED` | PASS | `true` | `true` |
| `G5_REPORT_PASS` | PASS | `true` | `true` |
| `G5_CANONICAL_TRIALS` | PASS | `24` | `{"min": 24}` |
| `G5_CV_STATE_EQUIVALENCE` | PASS | `6.661338147750939e-15` | `{"max": 1e-10}` |
| `G5_CV_COVARIANCE_EQUIVALENCE` | PASS | `2.220446049250313e-15` | `{"max": 1e-10}` |
| `G5_IMM_STATE_EQUIVALENCE` | PASS | `7.549516567451064e-15` | `{"max": 1e-10}` |
| `G5_IMM_COVARIANCE_EQUIVALENCE` | PASS | `2.1649348980190553e-15` | `{"max": 1e-10}` |
| `G5_MH_STATE_EQUIVALENCE` | PASS | `9.325873406851315e-15` | `{"max": 1e-10}` |
| `G5_MH_COVARIANCE_EQUIVALENCE` | PASS | `7.105427357601002e-15` | `{"max": 1e-10}` |
| `G6_CANONICAL_TRIALS` | PASS | `24` | `24` |
| `G6_MH_NIS_VALIDITY_BOUNDARY` | PASS | `{"reason": "MULTIMODAL_NON_GAUSSIAN_BELIEF", "valid": false}` | `{"valid": false}` |
| `G7_IMM_CANDIDATES` | PASS | `36` | `36` |
| `G7_MH_CANDIDATES` | PASS | `27` | `27` |
| `G7_IMM_SELECTION_VALID` | PASS | `true` | `true` |
| `G7_MH_SELECTION_VALID` | PASS | `true` | `true` |
| `G8_FAULT_COUNT` | PASS | `12` | `12` |
| `G8_PASSED_FAULTS` | PASS | `12` | `12` |
| `G8_REPORT_PASS` | PASS | `true` | `true` |
| `G9_QOS_SCENARIOS` | PASS | `8` | `8` |
| `G9_QOS_PASSED` | PASS | `8` | `8` |
| `G9_CAMPAIGN_COMPLETED` | PASS | `true` | `true` |
| `G9_ESTIMATOR_DEADLINE_REPORTED` | PASS | `{"all_max_below_deadline": false, "deadline_ms": 33.333, "row_count": 12}` | `{"deadline_ms": 33.333, "result_may_pass_or_fail_but_must_be_reported": true}` |
| `G9_RESOURCE_THERMAL_REQUIREMENT` | PASS | `true` | `true` |
| `G9_CLAIM_STATUS_MATCHES_REQUIREMENTS` | PASS | `{"claim_status": "HARD_REAL_TIME_NOT_CLAIMED_REQUIREMENTS_NOT_MET", "requirements_all_passed": false}` | `"Claim status must withhold hard-real-time wording whenever a runtime requirement fails."` |
| `G11_ABLATION_COUNT` | PASS | `15` | `15` |
| `G11_CLASSICAL_BASELINE` | PASS | `true` | `true` |
| `G11_FROZEN_EVALUATION_VALID` | PASS | `true` | `true` |
| `G11_OOD_VALID` | PASS | `true` | `true` |
| `G6_REPLAY_TRIAL_COUNT` | PASS | `24` | `24` |
| `G8_REPLAY_PASS` | PASS | `{"passed": true, "passed_faults": 12}` | `{"passed": true, "passed_faults": 12}` |
| `COMMAND_CPP_TESTS` | PASS | `0` | `0` |
| `COMMAND_G5_EQUIVALENCE` | PASS | `0` | `0` |
| `COMMAND_PYTHON_GHOST_X_TESTS` | PASS | `0` | `0` |

## Command gates

- `cpp_tests`: `PASS`
- `g5_equivalence`: `PASS`
- `python_ghost_x_tests`: `PASS`

## Boundary

These gates prevent silent regression in pinned synthetic scenarios and stored Pi evidence. They do not replace controlled physical truth, measurement characterization, or flight qualification.
