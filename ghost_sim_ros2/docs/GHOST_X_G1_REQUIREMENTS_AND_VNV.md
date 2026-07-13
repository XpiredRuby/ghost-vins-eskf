# GHOST-X Phase G1 — Requirements and V&V Architecture

## Status

**Phase status:** COMPLETE — INTERNAL SRR APPROVED  
**Requirements:** 34  
**Verification tests:** 34  
**Nominal scenarios:** 10  
**Fault scenarios:** 12  
**Controlled claims:** 6

Machine-readable sources:

- `config/ghost_x_requirements.yaml`
- `config/ghost_x_test_catalog.yaml`
- `config/ghost_x_claims.yaml`
- `docs/GHOST_X_TRACEABILITY.csv`
- `docs/GHOST_X_G1_VALIDATION.json`

Validation command:

```bash
python3 ghost_sim_ros2/tools/validate_ghost_x_g1.py \
  --requirements ghost_sim_ros2/config/ghost_x_requirements.yaml \
  --tests ghost_sim_ros2/config/ghost_x_test_catalog.yaml \
  --claims ghost_sim_ros2/config/ghost_x_claims.yaml \
  --report ghost_sim_ros2/docs/GHOST_X_G1_VALIDATION.json \
  --traceability ghost_sim_ros2/docs/GHOST_X_TRACEABILITY.csv
```

## Engineering objectives

GHOST-X shall determine how reliably a resource-constrained autonomous system can estimate and predict target state under visibility loss, changing dynamics, latency, false or out-of-sequence data, calibration uncertainty, compute overload, sensor degradation, and model mismatch.

All formal estimator comparisons use identical accepted measurements, timestamps, calibration/configuration identifiers, and truth records.

## Quantitative acceptance targets

These targets are frozen before the formal controlled-truth campaign. Any later revision requires a documented discrepancy and shall not be applied retroactively to previously collected formal trials.

| Metric | Acceptance target |
|---|---:|
| Visible position RMSE | `<= 0.10 m` |
| Occlusion endpoint RMSE, gaps `<= 2.0 s` | `<= 0.30 m` |
| Visible velocity RMSE, where truth is defensible | `<= 0.20 m/s` |
| Prediction velocity RMSE, gaps `<= 2.0 s` | `<= 0.50 m/s` |
| Median reacquisition time | `<= 0.40 s` |
| Reacquisition p95 | `<= 0.75 s` |
| Persistent false-track time | `<= 1%` of evaluated time |
| Longest unannunciated false lock | `<= 0.50 s` |
| Fault annunciation | `<= 0.50 s` |
| Recovery after valid measurements resume | `<= 2.0 s` |
| Nominal latency p95 | `<= 150 ms` |
| Nominal latency p99 | `<= 250 ms` |
| 30 Hz publication deadline miss rate | `<= 1%` |
| Covariance symmetry tolerance | `1e-10` |
| Covariance minimum-eigenvalue tolerance | `-1e-10` |
| C++/Python state agreement | `1e-8` absolute |
| C++/Python covariance agreement | `1e-7` absolute |
| C++/Python normalized probability agreement | `1e-8` absolute |
| Accepted nominal Pi trial thermal throttling | none |
| Accepted nominal Pi trial OOM termination | none |

NIS and NEES are not unconditional pass/fail decorations. NIS reporting requires measurement covariance provenance and residual-assumption review. NEES is valid only where state truth and truth uncertainty are defensible. Invalid conditions must be explicitly labeled.

## Requirement architecture

### System and execution

- identical inputs across compared estimators;
- live camera, bag replay, simulation, fault replay, Monte Carlo, and Pi real-time modes;
- versioned machine-readable outputs;
- no-purchase mandatory completion path.

### Estimation

- formal IMM;
- persistent GHOST-MH;
- independent constant-velocity/Kalman baseline;
- deterministic configuration and replay;
- covariance property testing;
- modern C++ and independent Python equivalence.

### Data contracts

- explicit frame, axes, handedness, SI units, and transform provenance;
- source, receipt, processing, and publication timestamps;
- calibration/configuration hashes in formal evidence;
- explicit rejection and status for stale, duplicate, nonfinite, invalid, and out-of-order data.

### Physical V&V

- defensible truth method and uncertainty before collection;
- at least 20 accepted paired trials;
- retention of failed and invalid trials;
- position, velocity, reacquisition, false-track, and dropout-growth metrics.

### Consistency

- innovations and NIS with validity conditions;
- NEES only when truth covariance is defensible;
- no unsupported covariance-consistency claim.

### Faults and real-time behavior

- at least 10 reproducible faults;
- detection/status/recovery evidence;
- latency, jitter, CPU, RSS memory, execution time, temperature, and throttling evidence;
- worst-case and percentile reporting rather than averages alone.

### Reproducibility and claims

- canonical one-command replay;
- CI acceptance bands and negative regression tests;
- every public claim mapped to requirement, test, evidence, and limitation;
- public failure gallery.

## Verification methods

| Method | Use |
|---|---|
| Inspection/review | Requirements, protocols, frames, assumptions, claim wording |
| Unit/property test | Estimator mathematics, covariance, schemas |
| Equivalence test | C++ versus Python frozen vectors |
| Demonstration | Execution modes, dashboard, real-time path |
| Controlled experiment | Hardware accuracy, reacquisition, timing, faults |
| Deterministic replay | Regression and identical-input comparison |
| Statistical analysis | RMSE uncertainty, paired comparison, calibration |
| Campaign audit | Trial counts, invalid-trial retention, evidence integrity |

## Evidence hierarchy

1. Immutable raw bag/trial data and truth records.
2. Calibration, configuration, commit, and environment manifests.
3. Deterministic derived metrics and statistical outputs.
4. Generated figures and tables.
5. Public claims and résumé wording.

Higher layers may never override missing or contradictory lower-layer evidence.

## G1 exit review

| Exit item | Result |
|---|---|
| System, estimator, timing, evidence requirements written | PASS |
| Quantitative metrics and thresholds frozen | PASS |
| Nominal scenarios predeclared | PASS |
| Failure scenarios predeclared | PASS |
| Requirements-to-test traceability generated | PASS |
| Approved/qualified claims mapped to requirements and tests | PASS |
| Future gated claims explicitly prohibited | PASS |
| Machine validation of IDs and references | PASS |
| Internal SRR record completed | PASS |

**G1 exit decision:** APPROVED TO ENTER G2.
